"""AI request rate limiter for OCR API calls."""

import hashlib
import json
import math
import threading
import time
from typing import Any

# Rate limiter constants
_RATE_LIMITER_CUTOFF_WINDOW_S = 60.0  # Rate limiter cutoff window (seconds)
_RATE_LIMITER_MAX_WAIT_S = 60.0  # Rate limiter max wait (seconds)
_RATE_LIMITER_SLEEP_MIN_S = 0.05  # Rate limiter min sleep (seconds)
_RATE_LIMITER_SLEEP_MAX_S = 5.0  # Rate limiter max sleep (seconds)
_CHARS_PER_TOKEN = 4.0  # Chars per token estimate


# Private rate limiter classes
class _AiRequestReservation:
    def __init__(self, limiter: "_AiRequestRateLimiter", event: dict[str, Any]) -> None:
        self._limiter = limiter
        self._event = event
        self._finalized = False

    def finalize(self, *, actual_tokens: int | None) -> None:
        if self._finalized:
            return
        self._finalized = True
        self._limiter.finalize(self._event, actual_tokens=actual_tokens)


class _AiRequestRateLimiter:
    def __init__(
        self,
        *,
        key: str,
        requests_per_minute: int | None,
        tokens_per_minute: int | None,
    ) -> None:
        self.key = key
        self.requests_per_minute = requests_per_minute
        self.tokens_per_minute = tokens_per_minute
        self._events: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def _prune(self, *, now_monotonic: float) -> None:
        cutoff = float(now_monotonic) - _RATE_LIMITER_CUTOFF_WINDOW_S
        self._events = [
            event
            for event in self._events
            if float(event.get("at_monotonic") or 0.0) >= cutoff
        ]

    def acquire(self, *, estimated_tokens: int) -> _AiRequestReservation:
        estimated = max(1, int(estimated_tokens or 1))
        if self.tokens_per_minute is not None and estimated > int(
            self.tokens_per_minute
        ):
            estimated = int(self.tokens_per_minute)

        while True:
            with self._lock:
                now_monotonic = time.monotonic()
                self._prune(now_monotonic=now_monotonic)
                wait_s = 0.0

                if (
                    self.requests_per_minute is not None
                    and len(self._events) >= int(self.requests_per_minute)
                    and self._events
                ):
                    oldest = float(self._events[0].get("at_monotonic") or now_monotonic)
                    wait_s = max(wait_s, max(0.0, _RATE_LIMITER_MAX_WAIT_S - (now_monotonic - oldest)))

                if self.tokens_per_minute is not None and self._events:
                    token_budget = int(self.tokens_per_minute)
                    used_tokens = sum(
                        int(event.get("tokens") or 0) for event in self._events
                    )
                    if used_tokens + estimated > token_budget:
                        reclaimed = 0
                        for event in self._events:
                            reclaimed += int(event.get("tokens") or 0)
                            candidate_wait = max(
                                0.0,
                                _RATE_LIMITER_MAX_WAIT_S
                                - (
                                    now_monotonic
                                    - float(event.get("at_monotonic") or now_monotonic)
                                ),
                            )
                            if used_tokens - reclaimed + estimated <= token_budget:
                                wait_s = max(wait_s, candidate_wait)
                                break

                if wait_s <= 0.0:
                    event = {
                        "at_monotonic": now_monotonic,
                        "tokens": estimated,
                    }
                    self._events.append(event)
                    return _AiRequestReservation(self, event)

            time.sleep(max(_RATE_LIMITER_SLEEP_MIN_S, min(wait_s, _RATE_LIMITER_SLEEP_MAX_S)))

    def finalize(self, event: dict[str, Any], *, actual_tokens: int | None) -> None:
        if actual_tokens is None:
            return
        finalized_tokens = max(1, int(actual_tokens))
        if self.tokens_per_minute is not None and finalized_tokens > int(
            self.tokens_per_minute
        ):
            finalized_tokens = int(self.tokens_per_minute)
        with self._lock:
            event["tokens"] = finalized_tokens


_AI_REQUEST_LIMITERS_LOCK = threading.Lock()
_AI_REQUEST_LIMITERS: dict[str, _AiRequestRateLimiter] = {}


def _get_shared_ai_request_limiter(
    *,
    api_key: str | None,
    provider_id: str | None,
    base_url: str | None,
    model: str | None,
    requests_per_minute: int | None,
    tokens_per_minute: int | None,
) -> _AiRequestRateLimiter | None:
    if requests_per_minute is None and tokens_per_minute is None:
        return None
    api_key_hash = hashlib.sha1(str(api_key or "").encode("utf-8")).hexdigest()[:12]
    key_payload = {
        "api_key_hash": api_key_hash,
        "base_url": str(base_url or "").strip().lower(),
        "model": str(model or "").strip().lower(),
        "provider": str(provider_id or "").strip().lower(),
        "rpm": requests_per_minute,
        "tpm": tokens_per_minute,
    }
    key = json.dumps(key_payload, ensure_ascii=True, sort_keys=True)
    with _AI_REQUEST_LIMITERS_LOCK:
        limiter = _AI_REQUEST_LIMITERS.get(key)
        if limiter is None:
            limiter = _AiRequestRateLimiter(
                key=key,
                requests_per_minute=requests_per_minute,
                tokens_per_minute=tokens_per_minute,
            )
            _AI_REQUEST_LIMITERS[key] = limiter
        return limiter

# Token estimation
def _estimate_chat_completion_tokens(*, messages: Any, max_tokens: int | None) -> int:
    text_chars = 0
    image_items = 0

    def _walk(value: Any) -> None:
        nonlocal image_items, text_chars
        if isinstance(value, str):
            text_chars += len(value)
            return
        if isinstance(value, list):
            for item in value:
                _walk(item)
            return
        if not isinstance(value, dict):
            return

        item_type = str(value.get("type") or "").strip().lower()
        if item_type in {"image_url", "input_image"}:
            image_items += 1
            return
        if item_type == "text":
            _walk(value.get("text"))
            return
        if "text" in value:
            _walk(value.get("text"))
        if "content" in value:
            _walk(value.get("content"))

    _walk(messages)
    prompt_tokens = int(math.ceil(float(text_chars) / _CHARS_PER_TOKEN))
    image_tokens = int(image_items) * 512
    completion_budget = max(0, int(max_tokens or 0))
    return max(1, prompt_tokens + image_tokens + completion_budget)


def _extract_completion_total_tokens(completion: Any) -> int | None:
    usage = getattr(completion, "usage", None)
    if usage is None and isinstance(completion, dict):
        usage = completion.get("usage")
    total_tokens = None
    if isinstance(usage, dict):
        total_tokens = usage.get("total_tokens")
    elif usage is not None:
        total_tokens = getattr(usage, "total_tokens", None)
    try:
        if total_tokens is None:
            return None
        parsed = int(total_tokens)
    except Exception:
        return None
    return parsed if parsed > 0 else None
