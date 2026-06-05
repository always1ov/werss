"""AI 日报 API：配置管理与手动触发。"""
import json
import re
import threading
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field

from core.auth import get_current_user
from core.config import cfg
from core.db import DB
from core.models.config_management import ConfigManagement
from .base import success_response, error_response

router = APIRouter(prefix="/ai-digest", tags=["AI 日报"])

_VALID_FORMATS = {"by_topic", "by_feed", "overall"}
_CRON_RE = re.compile(r"^\d+\s+\d+\s+\*\s+\*\s+\*$")


def _config_bool(value, default=False) -> bool:
    if value is None or str(value).strip() == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _upsert_config(session, key: str, value: str, description: str) -> None:
    row = session.query(ConfigManagement).filter(ConfigManagement.config_key == key).first()
    if row:
        row.config_value = value
        row.description = description
    else:
        session.add(ConfigManagement(config_key=key, config_value=value, description=description))


def _reload() -> None:
    try:
        from core.config_overrides import invalidate_config_overrides_cache
        invalidate_config_overrides_cache()
    except Exception:
        pass
    cfg.reload()
    try:
        from jobs.mps import reload_job
        reload_job()
    except Exception:
        pass


class AiDigestConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    schedules: Optional[List[str]] = None   # cron 数组，每条 "MM HH * * *"
    window_hours: Optional[int] = Field(default=None, ge=1, le=168)
    max_articles: Optional[int] = Field(default=None, ge=10, le=500)
    formats: Optional[List[str]] = None
    webhook_url: Optional[str] = None


def _read_schedules() -> List[str]:
    """读取多条 cron 计划；兼容旧的单条 ai_digest.cron。"""
    raw = cfg.get("ai_digest.schedules", None, silent=True)
    if raw:
        try:
            schedules = json.loads(raw) if isinstance(raw, str) else list(raw)
            if schedules:
                return [s for s in schedules if _CRON_RE.match(str(s).strip())]
        except Exception:
            pass
    # 兼容旧配置
    cron = (cfg.get("ai_digest.cron", "0 8 * * *") or "0 8 * * *").strip()
    return [cron]


def _read_config() -> dict:
    enabled = _config_bool(cfg.get("ai_digest.enabled", False), False)
    schedules = _read_schedules()
    window_hours = max(1, min(int(cfg.get("ai_digest.window_hours", 24) or 24), 168))
    max_articles = max(10, min(int(cfg.get("ai_digest.max_articles", 100) or 100), 500))
    formats_raw = cfg.get("ai_digest.formats", '["by_topic"]') or '["by_topic"]'
    try:
        formats = json.loads(formats_raw) if isinstance(formats_raw, str) else list(formats_raw)
    except Exception:
        formats = ["by_topic"]
    webhook_url = (cfg.get("ai_digest.webhook_url", None, silent=True) or "").strip()

    next_runs: List[str] = []
    try:
        from jobs.mps import scheduler
        status = scheduler.get_scheduler_status()
        ids = {f"ai_digest_{i}" for i in range(len(schedules))} | {"ai_digest"}
        for job_id, nr in status.get("next_run_times", []):
            if job_id in ids and nr:
                next_runs.append(str(nr))
    except Exception:
        pass

    return {
        "enabled": enabled,
        "schedules": schedules,
        "window_hours": window_hours,
        "max_articles": max_articles,
        "formats": formats,
        "webhook_url": webhook_url,
        "next_runs": sorted(next_runs),
    }


@router.get("/config", summary="获取 AI 日报配置")
async def get_config(current_user: dict = Depends(get_current_user)):
    try:
        return success_response(data=_read_config())
    except Exception as e:
        return error_response(500, str(e))


@router.put("/config", summary="更新 AI 日报配置")
async def update_config(data: AiDigestConfigUpdate, current_user: dict = Depends(get_current_user)):
    db = DB.session_factory()
    try:
        if data.enabled is not None:
            _upsert_config(db, "ai_digest.enabled", "true" if data.enabled else "false", "AI 日报：是否启用定时推送")
        if data.schedules is not None:
            valid = [s.strip() for s in data.schedules if _CRON_RE.match(s.strip())]
            if not valid:
                valid = ["0 8 * * *"]
            _upsert_config(db, "ai_digest.schedules", json.dumps(valid, ensure_ascii=False), "AI 日报：cron 计划列表")
        if data.window_hours is not None:
            _upsert_config(db, "ai_digest.window_hours", str(data.window_hours), "AI 日报：时间窗口（小时）")
        if data.max_articles is not None:
            _upsert_config(db, "ai_digest.max_articles", str(data.max_articles), "AI 日报：最大文章数")
        if data.formats is not None:
            formats = [f for f in data.formats if f in _VALID_FORMATS]
            _upsert_config(db, "ai_digest.formats", json.dumps(formats, ensure_ascii=False), "AI 日报：摘要格式列表")
        if data.webhook_url is not None:
            _upsert_config(db, "ai_digest.webhook_url", data.webhook_url.strip(), "AI 日报：额外 webhook URL（可选）")
        db.flush()
        db.commit()
        _reload()
        return success_response(data=_read_config(), message="配置已保存")
    except Exception as e:
        db.rollback()
        from core.log import logger
        logger.error(f"AI 日报配置保存失败: {e}", exc_info=True)
        return error_response(500, str(e))
    finally:
        db.close()


_digest_lock = threading.Lock()


async def _bg_run_digest():
    if not _digest_lock.acquire(blocking=False):
        return
    try:
        window_hours = max(1, min(int(cfg.get("ai_digest.window_hours", 24) or 24), 168))
        max_articles = max(10, min(int(cfg.get("ai_digest.max_articles", 100) or 100), 500))
        formats_raw = cfg.get("ai_digest.formats", '["by_topic"]') or '["by_topic"]'
        try:
            formats = json.loads(formats_raw) if isinstance(formats_raw, str) else list(formats_raw)
        except Exception:
            formats = ["by_topic"]

        from core.ai_digest.service import run_ai_digest
        await run_ai_digest(window_hours=window_hours, max_articles=max_articles, formats=formats)
    finally:
        _digest_lock.release()


@router.post("/run", summary="立即触发 AI 日报（后台执行）")
async def run_now(background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    if _digest_lock.locked():
        return error_response(409, "AI 日报正在生成中，请稍后再试")
    background_tasks.add_task(_bg_run_digest)
    return success_response(message="AI 日报已开始生成，请查看服务器日志获取结果")
