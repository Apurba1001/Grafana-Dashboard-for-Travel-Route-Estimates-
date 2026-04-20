"""S 45 trains from Wien Hernals toward Heiligenstadt.

Publishes the next N departures on commute/outbound/leg2/s45/hernals/departures.
"""
import json
import logging
import threading
import time

import sidecar
import config

log = logging.getLogger(__name__)

TOPIC = "commute/outbound/leg2/s45/hernals/departures"
POLL_INTERVAL_S = 30
LOOKAHEAD_MIN = 90
MAX_DEPARTURES_PUBLISHED = 5
QOS = 0
RETAIN = True

def is_outbound_s45(dep: dict) -> bool:
    line = dep.get("line") or ""
    direction = dep.get("direction") or ""
    return line.startswith("S 45") and "Heiligenstadt" in direction

def build_payload(deps: list[dict]) -> dict:
    return {
        "topic": TOPIC,
        "fetched_at": int(time.time()),
        "source": "hafas",
        "station_eva": config.WIEN_HERNALS_EVA,
        "station_name": "Wien Hernals",
        "direction_filter": "Heiligenstadt",
        "line_filter": "S 45",
        "count": len(deps),
        "departures": [
            {
                "when":         d.get("when"),
                "planned_when": d.get("plannedWhen"),
                "delay_s":      d.get("delay"),
                "line":         (d.get("line") or "").split(" (Zug-Nr")[0].strip(),
                "direction":    d.get("direction"),
                "platform":     d.get("platform"),
                "cancelled":    d.get("cancelled", False),
                "trip_id":      d.get("tripId"),
            }
            for d in deps
        ],
    }

def run_once(mqtt_client) -> None:
    try:
        all_deps = sidecar.departures(config.WIEN_HERNALS_EVA, LOOKAHEAD_MIN)
    except RuntimeError as e:
        log.error(f"fetch failed: {e}")
        return
    
    filtered = [d for d in all_deps if is_outbound_s45(d)]
    filtered = filtered[:MAX_DEPARTURES_PUBLISHED]
    
    payload = build_payload(filtered)
    info = mqtt_client.publish(TOPIC, json.dumps(payload), qos=QOS, retain=RETAIN)
    log.info(f"published {len(filtered)} S 45 outbound departures (mid={info.mid})")

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
        name="s45-outbound",
        daemon=True,
    )
    thread.start()
    return thread, stop_event