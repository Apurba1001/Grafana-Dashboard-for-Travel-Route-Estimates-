"""Outbound leave-by: when to walk out the door to catch the next viable REX 4 to Krems.

Reads latest S 45 (Hernals) and REX 4 (Heiligenstadt) departures from state.
Publishes to commute/derived/outbound/leave_by every POLL_INTERVAL_S.
"""
import json
import logging
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import state
import config

log = logging.getLogger(__name__)

TOPIC = "commute/derived/outbound/leave_by"
POLL_INTERVAL_S = 30
QOS = 0
RETAIN = True

VIENNA_TZ = ZoneInfo("Europe/Vienna")

INPUT_S45_TOPIC  = "commute/outbound/leg2/s45/hernals/departures"
INPUT_REX4_TOPIC = "commute/outbound/leg3/rex4/heiligenstadt/departures"


def parse_hafas_time(iso: str | None) -> datetime | None:
    """Parse HAFAS ISO timestamp to an aware datetime. Returns None on bad input."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return None


def effective_time(dep: dict) -> datetime | None:
    """Use realtime when available, fall back to scheduled."""
    return parse_hafas_time(dep.get("when")) or parse_hafas_time(dep.get("planned_when"))


def find_next_viable_plan(s45s, rex4s, now):
    walk_s     = config.WALK_HOME_TO_HERNALS_S
    ride_s     = config.RIDE_S45_HERNALS_TO_HEILIGENSTADT_S
    transfer_s = config.TRANSFER_HEILIGENSTADT_S45_TO_REX_S
    rex_ride_s = config.RIDE_REX4_HEILIGENSTADT_TO_KREMS_S
    
    s45_sorted  = sorted((d for d in s45s  if effective_time(d)), key=lambda d: effective_time(d))
    rex4_sorted = sorted((d for d in rex4s if effective_time(d)), key=lambda d: effective_time(d))
    
    reasons = {"leave_by_past": 0, "no_rex_chainable": 0, "cancelled": 0}
    
    for s45 in s45_sorted:
        if s45.get("cancelled"):
            reasons["cancelled"] += 1
            continue
        s45_dep = effective_time(s45)
        arrival_heiligenstadt  = s45_dep.timestamp() + ride_s
        earliest_rex_catchable = arrival_heiligenstadt + transfer_s
        
        chainable_rex = next(
            (r for r in rex4_sorted
             if not r.get("cancelled")
             and effective_time(r).timestamp() >= earliest_rex_catchable),
            None,
        )
        if chainable_rex is None:
            reasons["no_rex_chainable"] += 1
            continue
        
        leave_by_unix = s45_dep.timestamp() - walk_s
        if leave_by_unix < now.timestamp():
            reasons["leave_by_past"] += 1
            continue
        
        rex_dep = effective_time(chainable_rex)
        eta_krems_unix = rex_dep.timestamp() + rex_ride_s
        
        return {
            "leave_by":            datetime.fromtimestamp(leave_by_unix, tz=VIENNA_TZ).isoformat(),
            "leave_by_unix":       int(leave_by_unix),
            "minutes_until_leave": round((leave_by_unix - now.timestamp()) / 60, 1),
            "s45_departure":       s45_dep.isoformat(),
            "s45_direction":       s45.get("direction"),
            "s45_delay_s":         s45.get("delay_s"),
            "rex4_departure":      rex_dep.isoformat(),
            "rex4_direction":      chainable_rex.get("direction"),
            "rex4_delay_s":        chainable_rex.get("delay_s"),
            "eta_krems":           datetime.fromtimestamp(eta_krems_unix, tz=VIENNA_TZ).isoformat(),
            "eta_krems_unix":      int(eta_krems_unix),
            "total_minutes":       round((eta_krems_unix - leave_by_unix) / 60, 1),
        }
    
    return {"_diagnostic": reasons}


def compute(now: datetime) -> dict:
    """Compute the current outbound leave-by metric. Returns the MQTT payload."""
    s45_msg  = state.get(INPUT_S45_TOPIC)
    rex4_msg = state.get(INPUT_REX4_TOPIC)
    
    base = {
        "topic":       TOPIC,
        "computed_at": int(now.timestamp()),
        "now":         now.isoformat(),
    }
    
    if s45_msg is None or rex4_msg is None:
        missing = []
        if s45_msg is None:  missing.append("s45")
        if rex4_msg is None: missing.append("rex4")
        return {**base, "status": "input_missing", "missing_inputs": missing, "plan": None}
    
    s45s  = s45_msg.get("departures") or []
    rex4s = rex4_msg.get("departures") or []
    
    if not s45s or not rex4s:
        reason = []
        if not s45s:  reason.append("no S 45 in next 90 min")
        if not rex4s: reason.append("no REX 4 in next 180 min")
        return {**base, "status": "no_service", "reason": "; ".join(reason), "plan": None}
    
    plan = find_next_viable_plan(s45s, rex4s, now)
    
    if plan is None or "leave_by" not in plan:
        diag = (plan or {}).get("_diagnostic", {})
        return {
            **base,
            "status": "no_viable_plan",
            "diagnostic": diag,
            "s45_count": len(s45s),
            "rex4_count": len(rex4s),
            "plan": None,
        }
    
    # Viable plan found — classify urgency for the dashboard
    mins = plan["minutes_until_leave"]
    if mins < 2:    urgency = "critical"
    elif mins < 5:  urgency = "soon"
    elif mins < 15: urgency = "comfortable"
    else:           urgency = "relaxed"
    
    return {**base, "status": "ok", "urgency": urgency, "plan": plan}


def run_once(mqtt_client) -> None:
    now = datetime.now(VIENNA_TZ)
    try:
        payload = compute(now)
    except Exception as e:
        log.exception(f"compute() crashed: {e}")
        payload = {
            "topic":       TOPIC,
            "computed_at": int(now.timestamp()),
            "now":         now.isoformat(),
            "status":      "error",
            "error":       str(e),
            "plan":        None,
        }
    
    info = mqtt_client.publish(TOPIC, json.dumps(payload), qos=QOS, retain=RETAIN)
    
    status = payload.get("status")
    if status == "ok":
        plan = payload["plan"]
        log.info(
            f"leave_by: in {plan['minutes_until_leave']} min "
            f"({payload['urgency']}), ETA Krems {plan['eta_krems'][11:16]} "
            f"(mid={info.mid})"
        )
    else:
        log.info(f"leave_by: {status} (mid={info.mid})")


def loop(mqtt_client, stop_event: threading.Event) -> None:
    log.info(f"starting loop (every {POLL_INTERVAL_S}s)")
    while not stop_event.is_set():
        run_once(mqtt_client)
        stop_event.wait(POLL_INTERVAL_S)
    log.info("loop stopped")


def start(mqtt_client) -> tuple[threading.Thread, threading.Event]:
    stop_event = threading.Event()
    thread = threading.Thread(
        target=loop,
        args=(mqtt_client, stop_event),
        name="derived-outbound-leave-by",
        daemon=True,
    )
    thread.start()
    return thread, stop_event