"""Return recommender: bike vs bus vs walk from campus to Krems Bahnhof.

Reads:
  commute/return/leg1/bike/campus/status
  commute/return/leg1/bus1/klpu/departures
  commute/return/leg2/rex4/krems/departures
Publishes:
  commute/derived/return/recommendation
"""
import json
import logging
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import state
import config

log = logging.getLogger(__name__)

TOPIC = "commute/derived/return/recommendation"
POLL_INTERVAL_S = 30
QOS = 0
RETAIN = True

VIENNA_TZ = ZoneInfo("Europe/Vienna")

BIKE_TOPIC = "commute/return/leg1/bike/campus/status"
BUS_TOPIC  = "commute/return/leg1/bus1/klpu/departures"
REX4_TOPIC = "commute/return/leg2/rex4/krems/departures"


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def evaluate_walk(now: datetime) -> dict:
    eta_unix = now.timestamp() + config.WALK_CAMPUS_TO_BAHNHOF_S
    return {
        "mode":     "walk",
        "viable":   True,
        "eta":      datetime.fromtimestamp(eta_unix, tz=VIENNA_TZ).isoformat(),
        "eta_unix": int(eta_unix),
        "duration_min": round(config.WALK_CAMPUS_TO_BAHNHOF_S / 60, 1),
        "reason":   "always available",
    }


def evaluate_bike(now: datetime, bike_status: dict | None) -> dict:
    if bike_status is None:
        return {"mode": "bike", "viable": False, "reason": "no bike data"}
    
    if not bike_status.get("pickup_viable"):
        return {
            "mode":   "bike",
            "viable": False,
            "reason": bike_status.get("reason", "pickup not viable"),
            "bikes_available": bike_status.get("bikes_available"),
        }
    
    eta_unix = now.timestamp() + config.BIKE_CAMPUS_TO_BAHNHOF_S
    return {
        "mode":     "bike",
        "viable":   True,
        "eta":      datetime.fromtimestamp(eta_unix, tz=VIENNA_TZ).isoformat(),
        "eta_unix": int(eta_unix),
        "duration_min": round(config.BIKE_CAMPUS_TO_BAHNHOF_S / 60, 1),
        "bikes_available": bike_status.get("bikes_available"),
        "reason":   f"{bike_status.get('bikes_available')} bike(s) at campus",
    }


def evaluate_bus(now: datetime, bus_msg: dict | None) -> dict:
    if bus_msg is None:
        return {"mode": "bus", "viable": False, "reason": "no bus data"}
    
    if not bus_msg.get("in_service_window"):
        return {"mode": "bus", "viable": False, "reason": "outside Bus 1 service window"}
    
    deps = bus_msg.get("departures") or []
    if not deps:
        return {"mode": "bus", "viable": False, "reason": "no Bus 1 in view"}
    
    earliest_arrival_at_klpu = now.timestamp() + config.WALK_CAMPUS_TO_KLPU_S
    
    for dep in deps:
        if dep.get("cancelled"):
            continue
        bus_dep_time = parse_iso(dep.get("when")) or parse_iso(dep.get("planned_when"))
        if bus_dep_time is None:
            continue
        if bus_dep_time.timestamp() >= earliest_arrival_at_klpu:
            eta_unix = bus_dep_time.timestamp() + config.BUS_KLPU_TO_BAHNHOF_S
            return {
                "mode":     "bus",
                "viable":   True,
                "eta":      datetime.fromtimestamp(eta_unix, tz=VIENNA_TZ).isoformat(),
                "eta_unix": int(eta_unix),
                "duration_min": round((eta_unix - now.timestamp()) / 60, 1),
                "bus_departure_klpu": bus_dep_time.isoformat(),
                "bus_delay_s":       dep.get("delay_s"),
                "reason":   f"next Bus 1 at {bus_dep_time.strftime('%H:%M')}",
            }
    
    return {"mode": "bus", "viable": False, "reason": "no Bus 1 catchable after walk to KLPU"}


def find_target_rex4(now: datetime, rex4_msg: dict | None) -> dict | None:
    """Next REX 4 we'd realistically try to catch. Returns its payload dict, or None."""
    if rex4_msg is None:
        return None
    deps = rex4_msg.get("departures") or []
    for dep in deps:
        if dep.get("cancelled"):
            continue
        t = parse_iso(dep.get("when")) or parse_iso(dep.get("planned_when"))
        if t is None:
            continue
        # Pick the earliest REX 4 that leaves at least 3 minutes from now (need time to board)
        if t.timestamp() >= now.timestamp() + 3 * 60:
            return {
                "when":         dep.get("when"),
                "planned_when": dep.get("planned_when"),
                "delay_s":      dep.get("delay_s"),
                "direction":    dep.get("direction"),
                "platform":     dep.get("platform"),
                "unix":         int(t.timestamp()),
            }
    return None


def compute(now: datetime) -> dict:
    bike_status = state.get(BIKE_TOPIC)
    bus_msg     = state.get(BUS_TOPIC)
    rex4_msg    = state.get(REX4_TOPIC)
    
    base = {
        "topic":       TOPIC,
        "computed_at": int(now.timestamp()),
        "now":         now.isoformat(),
    }
    
    options = [
        evaluate_walk(now),
        evaluate_bike(now, bike_status),
        evaluate_bus(now, bus_msg),
    ]
    
    viable = [o for o in options if o.get("viable")]
    
    if not viable:
        return {**base, "status": "no_options", "options": options, "recommended": None}
    
    # Recommendation: fastest ETA wins
    recommended = min(viable, key=lambda o: o["eta_unix"])
    
    # Does it make the next REX 4?
    target = find_target_rex4(now, rex4_msg)
    makes_target = None
    if target is not None:
        # Need to be at Bahnhof at least 2 min before REX 4 departs
        buffer_s = 2 * 60
        makes_target = recommended["eta_unix"] + buffer_s <= target["unix"]
    
    return {
        **base,
        "status":          "ok",
        "recommended_mode": recommended["mode"],
        "recommended":     recommended,
        "options":         options,
        "target_rex4":     target,
        "makes_target":    makes_target,
    }


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
        }
    
    info = mqtt_client.publish(TOPIC, json.dumps(payload), qos=QOS, retain=RETAIN)
    
    status = payload.get("status")
    if status == "ok":
        mode = payload["recommended_mode"]
        dur  = payload["recommended"].get("duration_min", "?")
        makes = payload.get("makes_target")
        makes_str = "?" if makes is None else ("yes" if makes else "no")
        log.info(f"recommend: {mode} ({dur} min), makes REX 4: {makes_str} (mid={info.mid})")
    else:
        log.info(f"recommend: {status} (mid={info.mid})")


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
        name="derived-return-recommender",
        daemon=True,
    )
    thread.start()
    return thread, stop_event