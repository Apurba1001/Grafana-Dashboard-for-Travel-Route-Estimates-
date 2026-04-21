"""Kremser Stadtbus Line 1 from Undstraße/KLPU toward Krems Bahnhof.

Used on the return leg: campus walk → KLPU → bus → Krems Bahnhof → REX 4.
Publishes to commute/return/leg1/bus1/klpu/departures.
"""
import json
import logging
import threading
import time
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

import sidecar
import config

log = logging.getLogger(__name__)

TOPIC = "commute/return/leg1/bus1/klpu/departures"
POLL_INTERVAL_S = 60          # buses poll slower than trains - they move slower
LOOKAHEAD_MIN = 90
MAX_DEPARTURES_PUBLISHED = 5
QOS = 0
RETAIN = True

VIENNA_TZ = ZoneInfo("Europe/Vienna")

def is_bus1_toward_bahnhof(dep: dict) -> bool:
    line = dep.get("line") or ""
    direction = dep.get("direction") or ""
    return line == "Bus 1" and "Bahnhof" in direction

def in_service_window(now: datetime | None = None) -> bool:
    """True if Bus 1 is currently running (Vienna local time)."""
    now = now or datetime.now(VIENNA_TZ)
    first = dt_time(*config.BUS1_FIRST_DEPARTURE_HHMM)
    last  = dt_time(*config.BUS1_LAST_DEPARTURE_HHMM)
    current = now.time()
    return first <= current <= last

def build_payload(deps: list[dict], in_service: bool) -> dict:
    return {
        "topic":             TOPIC,
        "fetched_at":        int(time.time()),
        "source":            "hafas",
        "station_eva":       config.BUS1_KLPU_EVA,
        "station_name":      "Krems/Donau Undstraße/KLPU",
        "direction_filter":  "Bahnhof",
        "line_filter":       "Bus 1",
        "in_service_window": in_service,
        "service_window":    {
            "first_hhmm": list(config.BUS1_FIRST_DEPARTURE_HHMM),
            "last_hhmm":  list(config.BUS1_LAST_DEPARTURE_HHMM),
            "headway_min": config.BUS1_HEADWAY_MIN,
        },
        "count":             len(deps),
        "departures": [
            {
                "when":         d.get("when"),
                "planned_when": d.get("plannedWhen"),
                "delay_s":      d.get("delay"),
                "line":         d.get("line"),
                "direction":    d.get("direction"),
                "platform":     d.get("platform"),
                "cancelled":    d.get("cancelled", False),
                "trip_id":      d.get("tripId"),
            }
            for d in deps
        ],
    }

def run_once(mqtt_client) -> None:
    in_service = in_service_window()
    
    try:
        all_deps = sidecar.departures(config.BUS1_KLPU_EVA, LOOKAHEAD_MIN)
    except RuntimeError as e:
        log.error(f"fetch failed: {e}")
        return
    
    filtered = [d for d in all_deps if is_bus1_toward_bahnhof(d)]
    filtered = filtered[:MAX_DEPARTURES_PUBLISHED]
    
    payload = build_payload(filtered, in_service)
    info = mqtt_client.publish(TOPIC, json.dumps(payload), qos=QOS, retain=RETAIN)
    log.info(
        f"published {len(filtered)} Bus 1 departures, "
        f"in_service={in_service} (mid={info.mid})"
    )

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
        name="bus1-klpu",
        daemon=True,
    )
    thread.start()
    return thread, stop_event