"""Thread-safe cache of latest MQTT payloads by topic.

Fetchers don't use this. Derived-metric subscribers do:
the subscriber thread writes, derived-metric threads read.
"""
import json
import logging
import threading
import time

log = logging.getLogger(__name__)

# Topic -> {"payload": dict, "received_at": unix_seconds}
_cache: dict[str, dict] = {}
_lock = threading.Lock()

# How stale a topic can be before derived metrics should treat it as missing.
# 5 minutes comfortably covers our slowest fetcher (weather at 15 min cadence
# publishes retained, so a subscriber sees it immediately on connect).
DEFAULT_STALE_AFTER_S = 5 * 60

def update(topic: str, raw_payload: bytes) -> None:
    """Called by the subscriber whenever a message lands on a topic we care about."""
    try:
        parsed = json.loads(raw_payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        log.warning(f"ignoring unparseable message on {topic}: {e}")
        return
    
    with _lock:
        _cache[topic] = {"payload": parsed, "received_at": int(time.time())}

def get(topic: str, stale_after_s: int = DEFAULT_STALE_AFTER_S) -> dict | None:
    """Return the latest payload for a topic, or None if missing/stale."""
    with _lock:
        entry = _cache.get(topic)
        if entry is None:
            return None
        age = int(time.time()) - entry["received_at"]
        if age > stale_after_s:
            return None
        return entry["payload"]

def snapshot() -> dict[str, dict]:
    """Return a copy of the whole cache, for debugging."""
    with _lock:
        return dict(_cache)