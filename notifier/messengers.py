from __future__ import annotations

from typing import List, Optional
import httpx

import config
from collector.base import EnrichedJob
from notifier.kakao import build_briefing_text


def send_discord(jobs: List[EnrichedJob], new_count: int, briefing: Optional[dict] = None) -> bool:
    if not config.DISCORD_WEBHOOK_URL:
        return False
    text = build_briefing_text(jobs, new_count, briefing=briefing)
    if config.SITE_PUBLIC_URL:
        text += f"\n\n👉 전체 보기: {config.SITE_PUBLIC_URL}"
    try:
        r = httpx.post(config.DISCORD_WEBHOOK_URL, json={"content": text}, timeout=15.0)
        return r.status_code in (200, 204)
    except Exception:
        return False


def send_telegram(jobs: List[EnrichedJob], new_count: int, briefing: Optional[dict] = None) -> bool:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False
    text = build_briefing_text(jobs, new_count, briefing=briefing)
    if config.SITE_PUBLIC_URL:
        text += f"\n\n👉 전체 보기: {config.SITE_PUBLIC_URL}"
    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        r = httpx.post(
            url,
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text},
            timeout=15.0,
        )
        return r.status_code == 200
    except Exception:
        return False
