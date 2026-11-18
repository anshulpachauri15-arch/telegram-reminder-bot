"""
Natural language reminder parsing via GitHub Models.
Falls back gracefully if the token is not configured.
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

from openai import OpenAI

from config import TZ, TIMEZONE

log = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url="https://models.inference.ai.azure.com",
            api_key=GITHUB_TOKEN,
        )
    return _client


_SYSTEM = """\
You are a reminder parser. Extract reminder details from the user's message and return JSON.

{context}

Return ONLY valid JSON with exactly these fields:
- "remind_at": ISO datetime string (YYYY-MM-DDTHH:MM:SS) in the user's local timezone
- "message": clean reminder text — what to be reminded about, with no date/time words in it
- "recurrence": null, "daily", or "weekly"

Rules:
- Vague times: "morning"=09:00, "afternoon"=14:00, "evening"=18:00, "night"=21:00
- No date given → today if the time is still in the future, otherwise tomorrow
- "daily" → set remind_at to the next occurrence of that time
- "weekly" → set remind_at to the next occurrence of that weekday + time
- message must be concise and free of date/time phrases
"""


def parse_reminder(text: str) -> Optional[dict]:
    """
    Parse a free-text reminder into structured data.

    Returns a dict with keys:
        remind_at  (datetime, naive local time)
        message    (str)
        recurrence (str | None)

    Returns None if parsing fails or GITHUB_TOKEN is not set.
    """
    if not GITHUB_TOKEN:
        return None

    now = datetime.now(TZ)
    context = (
        f"Current date/time: {now.strftime('%A, %B %d, %Y at %I:%M %p')}\n"
        f"Timezone: {TIMEZONE}"
    )

    try:
        response = _get_client().chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM.format(context=context)},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
            max_tokens=150,
            temperature=0,
        )
        data = json.loads(response.choices[0].message.content)
        remind_at = datetime.fromisoformat(data["remind_at"])
        return {
            "remind_at": remind_at,
            "message": str(data.get("message") or text),
            "recurrence": data.get("recurrence"),
        }
    except Exception as exc:
        log.warning(f"LLM parse failed: {exc}")
        return None
