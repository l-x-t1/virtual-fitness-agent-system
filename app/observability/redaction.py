from __future__ import annotations

import json
import re
from typing import Any


SECRET_KEYS = {
    "api_key", "apikey", "authorization", "cookie", "jwt", "password",
    "secret", "secret_key", "token", "access_token", "refresh_token",
}
PRIVATE_BODY_KEYS = {
    "height", "height_cm", "weight", "weight_kg", "bmi", "body_fat",
    "body_fat_rate", "medical_history", "health_data",
}
SECRET_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[a-z0-9._~+\-/]+=*"),
    re.compile(r"(?i)((?:api[_-]?key|password|secret|token)\s*[:=]\s*)[^\s,;]+"),
)
PRIVATE_TEXT_PATTERNS = (
    re.compile(r"(?i)((?:体重|weight(?:_kg)?)\s*[\":：=]*\s*)\d+(?:\.\d+)?(?:\s*kg)?"),
    re.compile(r"(?i)((?:身高|height(?:_cm)?)\s*[\":：=]*\s*)\d+(?:\.\d+)?(?:\s*cm)?"),
    re.compile(r"(?i)((?:体脂(?:率)?|body_fat(?:_rate)?|bmi)\s*[\":：=]*\s*)\d+(?:\.\d+)?%?"),
)


def redact(value: Any, *, max_text: int = 1200) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if normalized in SECRET_KEYS or any(
                part in normalized for part in ("password", "secret", "api_key")
            ):
                cleaned[key] = "[REDACTED]"
            elif normalized in PRIVATE_BODY_KEYS:
                cleaned[key] = "[PRIVATE]"
            else:
                cleaned[key] = redact(item, max_text=max_text)
        return cleaned
    if isinstance(value, (list, tuple, set)):
        return [redact(item, max_text=max_text) for item in value]
    if isinstance(value, bytes):
        return f"[BYTES:{len(value)}]"
    if isinstance(value, str):
        text = value
        for pattern in SECRET_PATTERNS:
            text = pattern.sub(r"\1[REDACTED]", text)
        for pattern in PRIVATE_TEXT_PATTERNS:
            text = pattern.sub(r"\1[PRIVATE]", text)
        return text[:max_text] + ("…" if len(text) > max_text else "")
    if value is None or isinstance(value, (bool, int, float)):
        return value
    try:
        return redact(json.loads(json.dumps(value, default=str)), max_text=max_text)
    except Exception:
        return str(type(value).__name__)
