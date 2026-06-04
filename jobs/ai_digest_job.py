"""AI 日报定时任务注册。"""
import asyncio
import json
import os

from core.config import cfg
from core.log import logger
from core.print import print_info, print_warning
from core.task import TaskScheduler


def register_ai_digest_job(scheduler: TaskScheduler) -> None:
    """向 scheduler 注册 AI 日报定时任务（若未启用则静默跳过）。"""
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

    cron_expr = (cfg.get("ai_digest.cron", "0 8 * * *") or "0 8 * * *").strip()

    def run_digest():
        from apis.ai_digest import _digest_running
        import apis.ai_digest as _ai_digest_mod
        if _digest_running:
            logger.warning("AI 日报：上次任务仍在运行，跳过本次定时触发")
            return
        _ai_digest_mod._digest_running = True
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
            _ai_digest_mod._digest_running = False

    job_id = scheduler.add_cron_job(
        run_digest,
        cron_expr=cron_expr,
        job_id="ai_digest",
        tag="AI 日报",
    )
    print_info(f"AI 日报：已注册定时任务 (job_id={job_id}, cron={cron_expr})")

    if not scheduler.get_scheduler_status().get("running"):
        scheduler.start()
