"""Nextbike station status for Krems Bahnhof and Krems Campus.

Polls the Lower Austria GBFS feed and publishes per-station pickup viability.
Publishes to:
  commute/outbound/leg4/bike/krems_bf/status  (one to watch for outbound pickup)
  commute/return/leg1/bike/campus/status      (one to watch for return pickup)
"""
import json
import logging
import threading
import time

import requests

import config

log = logging.getLogger(__name__)

STATION_STATUS_URL = f"{config.NEXTBIKE_SYSTEM_BASE}/station_status.json"
TIMEOUT_S = 10
POLL_INTERVAL_S = 60     # GBFS spec says near-realtime; 60s is the sweet spot
QOS = 0
RETAIN = True

# Each station gets its own topic; we track both in one fetcher since they share a feed
STATIONS = [
    {
        "station_id": config.KREMS_BAHNHOF_BIKE_ID,
        "name":       "Krems / Bahnhof",
        "topic":      "commute/outbound/leg4/bike/krems_bf/status",
        "role":       "outbound_pickup",
    },
    {
        "station_id": config.KREMS_CAMPUS_BIKE_ID,
        "name":       "Krems / Campus Donau Uni Krems",
        "topic":      "commute/return/leg1/bike/campus/status",
        "role":       "return_pickup",
    },
]

def fetch_all_statuses() -> list[dict]:
    """Fetch station_status.json. Returns the 'stations' array."""
    try:
        r = requests.get(STATION_STATUS_URL, timeout=TIMEOUT_S)
        r.raise_for_status()
        return r.json().get("data", {}).get("stations", [])
    except requests.RequestException as e:
        raise RuntimeError(f"nextbike fetch failed: {e}") from e

def build_payload(station_meta: dict, raw_status: dict | None) -> dict:
    """Build the MQTT payload for one station. raw_status is None if not found."""
    now = int(time.time())
    
    if raw_status is None:
        return {
            "topic":        station_meta["topic"],
            "fetched_at":   now,
            "source":       "nextbike",
            "station_id":   station_meta["station_id"],
            "station_name": station_meta["name"],
            "role":         station_meta["role"],
            "status":       "unknown",
            "pickup_viable": False,
            "reason":       "station not found in feed",
        }
    
    bikes = raw_status.get("num_bikes_available", 0)
    is_renting  = raw_status.get("is_renting", False)
    is_installed = raw_status.get("is_installed", False)
    last_reported = raw_status.get("last_reported")  # unix seconds
    
    pickup_viable = bool(bikes >= 1 and is_renting and is_installed)
    
    if pickup_viable:
        reason = f"{bikes} bike(s) available"
    elif bikes == 0:
        reason = "no bikes available"
    elif not is_renting:
        reason = "station not accepting rentals"
    elif not is_installed:
        reason = "station uninstalled"
    else:
        reason = "unknown"
    
    return {
        "topic":             station_meta["topic"],
        "fetched_at":        now,
        "source":            "nextbike",
        "station_id":        station_meta["station_id"],
        "station_name":      station_meta["name"],
        "role":              station_meta["role"],
        "status":            "ok",
        "bikes_available":   bikes,
        "docks_available":   raw_status.get("num_docks_available"),  # may be 0/meaningless
        "is_renting":        is_renting,
        "is_installed":      is_installed,
        "last_reported":     last_reported,
        "pickup_viable":     pickup_viable,
        "reason":            reason,
    }

def run_once(mqtt_client) -> None:
    try:
        all_stations = fetch_all_statuses()
    except RuntimeError as e:
        log.error(f"fetch failed: {e}")
        return
    
    by_id = {s.get("station_id"): s for s in all_stations}
    
    for station_meta in STATIONS:
        raw = by_id.get(station_meta["station_id"])
        payload = build_payload(station_meta, raw)
        info = mqtt_client.publish(
            station_meta["topic"],
            json.dumps(payload),
            qos=QOS,
            retain=RETAIN,
        )
        log.info(
            f"published {station_meta['name']}: "
            f"{payload.get('bikes_available', '?')} bikes, "
            f"pickup_viable={payload['pickup_viable']} (mid={info.mid})"
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
        name="nextbike-krems",
        daemon=True,
    )
    thread.start()
    return thread, stop_event