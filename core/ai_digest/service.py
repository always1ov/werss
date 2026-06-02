"""AI 日报：将最近 N 小时的文章用 AI 高度概括后推送到 webhook。"""
import asyncio
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core.config import cfg
from core.log import logger
from core.print import print_info, print_error, print_success, print_warning

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from anthropic import AsyncAnthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

FORMAT_BY_TOPIC = "by_topic"
FORMAT_BY_FEED = "by_feed"
FORMAT_OVERALL = "overall"

FORMAT_LABELS = {
    FORMAT_BY_TOPIC: "按主题聚合",
    FORMAT_BY_FEED: "按公众号分组",
    FORMAT_OVERALL: "整体概述",
}


def _get_ai_config():
    """Return (provider, api_key, base_url, model)."""
    try:
        from core.env_loader import load_dev_env_if_needed
        load_dev_env_if_needed()
    except Exception:
        pass

    anthropic_key = cfg.get("anthropic.api_key", None, silent=True) or os.getenv("ANTHROPIC_API_KEY", "")
    if anthropic_key and ANTHROPIC_AVAILABLE:
        model = str(
            cfg.get("anthropic.model", None, silent=True)
            or os.getenv("ANTHROPIC_MODEL", "claude-opus-4-7")
            or "claude-opus-4-7"
        )
        base_url = str(cfg.get("anthropic.base_url", None, silent=True) or os.getenv("ANTHROPIC_BASE_URL", "") or "")
        return "anthropic", str(anthropic_key), base_url, model

    api_key = str(cfg.get("openai.api_key", None, silent=True) or os.getenv("OPENAI_API_KEY", "") or "")
    base_url = str(
        cfg.get("openai.base_url", None, silent=True)
        or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        or "https://api.openai.com/v1"
    )
    model = str(cfg.get("openai.model", None, silent=True) or os.getenv("OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini")
    if base_url and not base_url.endswith("/"):
        base_url += "/"
    return "openai", api_key, base_url, model


def _fetch_articles(window_hours: int, max_articles: int) -> List[Dict[str, Any]]:
    """从数据库获取最近 window_hours 小时的文章。"""
    from core.database import get_db
    from core.models.article import Article
    from core.models.feed import Feed
    from core.models.base import DATA_STATUS

    since_ts = int((datetime.now() - timedelta(hours=window_hours)).timestamp())
    db = get_db()
    try:
        rows = (
            db.query(Article, Feed)
            .join(Feed, Article.mp_id == Feed.id, isouter=True)
            .filter(
                Article.publish_time >= since_ts,
                Article.status != DATA_STATUS.DELETED,
            )
            .order_by(Article.publish_time.desc())
            .limit(max_articles)
            .all()
        )
        articles = []
        for article, feed in rows:
            articles.append({
                "title": article.title or "",
                "description": (article.description or "")[:200],
                "url": article.url or "",
                "mp_name": (feed.mp_name if feed else "") or "未知公众号",
                "publish_time": (
                    datetime.fromtimestamp(article.publish_time).strftime("%m-%d %H:%M")
                    if article.publish_time else ""
                ),
            })
        return articles
    finally:
        db.close()


async def _call_ai(system_prompt: str, user_prompt: str) -> str:
    """调用 AI 生成摘要。"""
    provider, api_key, base_url, model = _get_ai_config()
    if not api_key:
        raise ValueError("未配置 AI API（需要 ANTHROPIC_API_KEY 或 OPENAI_API_KEY）")

    if provider == "anthropic" and ANTHROPIC_AVAILABLE:
        client_kwargs: Dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = AsyncAnthropic(**client_kwargs)
        response = await client.messages.create(
            model=model,
            max_tokens=2000,
            temperature=0.3,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return next((b.text for b in response.content if hasattr(b, "text")), "") or ""

    if not OPENAI_AVAILABLE:
        raise RuntimeError("openai 模块未安装")
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    response = await client.chat.completions.create(
        model=model,
        temperature=0.3,
        max_tokens=2000,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content or ""


def _article_list_text(articles: List[Dict]) -> str:
    lines = []
    for a in articles:
        line = f"- [{a['mp_name']}] {a['title']}"
        if a.get("description"):
            line += f"：{a['description']}"
        lines.append(line)
    return "\n".join(lines)


async def _summarize_by_topic(articles: List[Dict]) -> str:
    system = (
        "你是资深新闻编辑，擅长从大量文章中提炼出关键热点主题。"
        "输出格式严格遵循 Markdown，层级清晰，语言简洁，不要废话。"
    )
    user = (
        f"以下是来自微信公众号的 {len(articles)} 篇文章列表：\n\n"
        f"{_article_list_text(articles)}\n\n"
        "请将这些文章按主题聚合，找出 3-8 个关键主题，每个主题写 1-3 条核心要点。\n"
        "输出格式（Markdown）：\n"
        "## 📌 主题名称（N篇）\n"
        "- 要点一\n"
        "- 要点二\n\n"
        "只输出 Markdown 内容，不要前言和后记。"
    )
    return await _call_ai(system, user)


async def _summarize_by_feed(articles: List[Dict]) -> str:
    by_feed: Dict[str, List[Dict]] = defaultdict(list)
    for a in articles:
        by_feed[a["mp_name"]].append(a)

    lines = []
    for mp_name, arts in by_feed.items():
        titles = "、".join(a["title"] for a in arts[:5] if a["title"])
        lines.append(f"**{mp_name}**（{len(arts)}篇）：{titles}")
    feed_text = "\n".join(lines)

    system = "你是简报助手，用简洁语言概括各公众号今日内容。"
    user = (
        f"以下是各公众号发布的文章情况：\n\n{feed_text}\n\n"
        "请为每个公众号写一句话概括今日内容重点（20字以内）。\n"
        "输出格式（Markdown）：\n"
        "**公众号名**：概括语句\n\n"
        "只输出 Markdown 内容。"
    )
    return await _call_ai(system, user)


async def _summarize_overall(articles: List[Dict]) -> str:
    system = "你是新闻摘要助手，善于从大量文章中提炼一段全局综述。"
    user = (
        f"以下是微信公众号的 {len(articles)} 篇文章（部分展示）：\n\n"
        f"{_article_list_text(articles[:50])}\n\n"
        "请用 150 字以内写一段今日资讯综述，涵盖主要领域和热点，语言简练。\n"
        "只输出综述文字，不要任何格式标记。"
    )
    return await _call_ai(system, user)


async def run_ai_digest(
    window_hours: int = 24,
    max_articles: int = 100,
    formats: Optional[List[str]] = None,
) -> str:
    """执行 AI 日报主流程，返回发送的消息内容。"""
    if formats is None:
        formats = [FORMAT_BY_TOPIC]

    print_info(f"AI 日报开始：window_hours={window_hours}, max_articles={max_articles}, formats={formats}")

    articles = _fetch_articles(window_hours, max_articles)
    if not articles:
        print_info("AI 日报：时间窗口内没有文章，跳过推送")
        return "no_articles"

    print_info(f"AI 日报：获取到 {len(articles)} 篇文章，开始生成摘要")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    sections = [f"**📰 AI 日报 · {now_str}**（共 {len(articles)} 篇，最近 {window_hours} 小时）"]

    for fmt in formats:
        try:
            if fmt == FORMAT_BY_TOPIC:
                text = await _summarize_by_topic(articles)
                sections.append(f"### 🔥 按主题聚合\n\n{text}")
            elif fmt == FORMAT_BY_FEED:
                text = await _summarize_by_feed(articles)
                sections.append(f"### 📋 按公众号概览\n\n{text}")
            elif fmt == FORMAT_OVERALL:
                text = await _summarize_overall(articles)
                sections.append(f"### 📝 综述\n\n{text}")
        except Exception as e:
            logger.warning(f"AI 日报生成 {fmt} 摘要失败: {e}")
            sections.append(f"### {FORMAT_LABELS.get(fmt, fmt)} 生成失败：{e}")

    full_message = "\n\n".join(sections)

    from core.notice import notice
    webhook_urls: List[str] = []
    for env_var in ["DINGDING_WEBHOOK", "FEISHU_WEBHOOK", "WECHAT_WEBHOOK"]:
        url = os.getenv(env_var, "").strip()
        if url:
            webhook_urls.append(url)
    extra_url = (cfg.get("ai_digest.webhook_url", None, silent=True) or os.getenv("AI_DIGEST_WEBHOOK_URL", "")).strip()
    if extra_url:
        webhook_urls.append(extra_url)

    if not webhook_urls:
        print_warning("AI 日报：未配置任何 webhook，仅生成内容不推送")
        return full_message

    sent = 0
    for url in webhook_urls:
        try:
            notice(url, "AI 每日日报", full_message)
            sent += 1
        except Exception as e:
            logger.warning(f"AI 日报推送失败（{url[:30]}...）: {e}")

    print_success(f"AI 日报：已推送到 {sent}/{len(webhook_urls)} 个 webhook")
    return full_message
