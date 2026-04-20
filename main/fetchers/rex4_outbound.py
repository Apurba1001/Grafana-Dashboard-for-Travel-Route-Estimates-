"""REX 4 trains from Wien Heiligenstadt toward Krems.

Publishes the next N departures (filtered to REX 4 heading toward Krems) every
POLL_INTERVAL seconds on commute/outbound/leg3/rex4/heiligenstadt/departures.
"""
import json
import logging
import threading
import time

import sidecar
import config

log = logging.getLogger(__name__)

TOPIC = "commute/outbound/leg3/rex4/heiligenstadt/departures"
POLL_INTERVAL_S = 30
LOOKAHEAD_MIN = 90          # fetch 90 min of departures so filtered list is rarely empty
MAX_DEPARTURES_PUBLISHED = 5
QOS = 0                     # next poll in 30s, no need for delivery guarantee
RETAIN = True               # fresh dashboard connects should see current state

def is_outbound_to_krems(dep: dict) -> bool:
    line = dep.get("line") or ""
    direction = dep.get("direction") or ""
    return (
        line.startswith("REX 4")
        and "Krems" in direction
    )

def build_payload(deps: list[dict]) -> dict:
    return {
        "topic": TOPIC,
        "fetched_at": int(time.time()),
        "source": "hafas",
        "station_eva": config.WIEN_HEILIGENSTADT_EVA,
        "station_name": "Wien Heiligenstadt",
        "direction_filter": "Krems",
        "line_filter": "REX 4",
        "count": len(deps),
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
    """Single fetch-filter-publish cycle. Logs errors, never raises."""
    try:
        all_deps = sidecar.departures(config.WIEN_HEILIGENSTADT_EVA, LOOKAHEAD_MIN)
    except RuntimeError as e:
        log.error(f"fetch failed: {e}")
        return
    
    filtered = [d for d in all_deps if is_outbound_to_krems(d)]
    filtered = filtered[:MAX_DEPARTURES_PUBLISHED]
    
    payload = build_payload(filtered)
    info = mqtt_client.publish(TOPIC, json.dumps(payload), qos=QOS, retain=RETAIN)
    log.info(f"published {len(filtered)} REX 4 departures (mid={info.mid})")

def loop(mqtt_client, stop_event: threading.Event) -> None:
    """Run run_once every POLL_INTERVAL_S until stop_event is set."""
    log.info(f"starting loop (every {POLL_INTERVAL_S}s)")
    while not stop_event.is_set():
        run_once(mqtt_client)
        stop_event.wait(POLL_INTERVAL_S)
    log.info("loop stopped")

def start(mqtt_client) -> tuple[threading.Thread, threading.Event]:
    """Start the fetcher in a background thread. Returns (thread, stop_event)."""
    stop_event = threading.Event()
    thread = threading.Thread(
        target=loop,
        args=(mqtt_client, stop_event),
        name="rex4-heiligenstadt-outbound",
        daemon=True,
    )
    thread.start()
    return thread, stop_event