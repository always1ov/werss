"""AI 日报定时任务注册。"""
import asyncio
import json
import os
import re

from core.config import cfg
from core.log import logger
from core.print import print_info, print_warning
from core.task import TaskScheduler

_CRON_RE = re.compile(r"^\d+\s+\d+\s+\*\s+\*\s+\*$")


def _read_schedules() -> list:
    raw = cfg.get("ai_digest.schedules", None, silent=True)
    if raw:
        try:
            schedules = json.loads(raw) if isinstance(raw, str) else list(raw)
            valid = [s.strip() for s in schedules if _CRON_RE.match(str(s).strip())]
            if valid:
                return valid
        except Exception:
            pass
    cron = (cfg.get("ai_digest.cron", "0 8 * * *") or "0 8 * * *").strip()
    return [cron]


def register_ai_digest_job(scheduler: TaskScheduler) -> None:
    """向 scheduler 注册 AI 日报定时任务（多条计划各注册一个 job）。"""
    enabled = cfg.get("ai_digest.enabled", False)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() in ("1", "true", "yes", "on")
    if not enabled:
        return

    has_ai = bool(
        (cfg.get("anthropic.api_key", None) or os.getenv("ANTHROPIC_API_KEY", ""))
        or (cfg.get("openai.api_key", None) or os.getenv("OPENAI_API_KEY", ""))
    )
    if not has_ai:
        print_warning("AI 日报：未配置 AI API 密钥，跳过注册定时任务")
        return

    schedules = _read_schedules()

    def make_run_digest():
        def run_digest():
            import apis.ai_digest as _mod
            if _mod._digest_running:
                logger.warning("AI 日报：上次任务仍在运行，跳过本次定时触发")
                return
            _mod._digest_running = True
            try:
                window_hours = int(cfg.get("ai_digest.window_hours", 24) or 24)
                window_hours = max(1, min(window_hours, 168))
                max_articles = int(cfg.get("ai_digest.max_articles", 100) or 100)
                max_articles = max(10, min(max_articles, 500))
                formats_raw = cfg.get("ai_digest.formats", '["by_topic"]') or '["by_topic"]'
                try:
                    formats = json.loads(formats_raw) if isinstance(formats_raw, str) else list(formats_raw)
                except Exception:
                    formats = ["by_topic"]

                from core.ai_digest.service import run_ai_digest
                asyncio.run(run_ai_digest(window_hours=window_hours, max_articles=max_articles, formats=formats))
            except Exception as e:
                logger.error(f"AI 日报执行失败: {e}")
            finally:
                _mod._digest_running = False
        return run_digest

    for i, cron_expr in enumerate(schedules):
        job_id = f"ai_digest_{i}"
        scheduler.add_cron_job(
            make_run_digest(),
            cron_expr=cron_expr,
            job_id=job_id,
            tag="AI 日报",
        )
        print_info(f"AI 日报：已注册定时任务 #{i+1} (job_id={job_id}, cron={cron_expr})")

    if not scheduler.get_scheduler_status().get("running"):
        scheduler.start()
