"""Subscribes to commute/# and persists every message to InfluxDB.

Uses the existing shared MQTT client - attaches as a second message handler.
Writes are batched by the influxdb-client library for efficiency.
"""
import json
import logging
import threading
import time

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import ASYNCHRONOUS

import config

log = logging.getLogger(__name__)

SUBSCRIBE_TOPICS = [
    ("commute/outbound/#", 0),
    ("commute/return/#",   0),
    ("commute/weather/#",  0),
    ("commute/derived/#",  0),
]

# Route each topic prefix to an Influx measurement name
MEASUREMENT_MAP = [
    ("commute/outbound/leg2/s45",      "train_departures"),
    ("commute/outbound/leg3/rex4",     "train_departures"),
    ("commute/return/leg2/rex4",       "train_departures"),
    ("commute/return/leg3/s45",        "train_departures"),
    ("commute/outbound/leg4/bike",     "bike_status"),
    ("commute/return/leg1/bike",       "bike_status"),
    ("commute/return/leg1/bus1",       "bus_departures"),
    ("commute/weather",                "weather"),
    ("commute/derived/outbound",       "derived_outbound"),
    ("commute/derived/return",         "derived_return"),
]


def pick_measurement(topic: str) -> str:
    for prefix, measurement in MEASUREMENT_MAP:
        if topic.startswith(prefix):
            return measurement
    return "other"


def payload_to_points(topic: str, payload: dict) -> list[Point]:
    """Convert a parsed MQTT payload to one or more Influx points.
    
    Different topics have different shapes. Returns list to support 
    multi-row cases (e.g. each of the N departures becomes its own point).
    """
    measurement = pick_measurement(topic)
    now_ns = int(time.time() * 1e9)
    points = []
    
    if measurement == "train_departures" or measurement == "bus_departures":
        # One point per departure, plus one "summary" point with the count
        station = payload.get("station_name", "?")
        line    = payload.get("line_filter", "?")
        summary = (
            Point(measurement + "_summary")
            .tag("topic", topic)
            .tag("station", station)
            .tag("line", line)
            .field("count", payload.get("count", 0))
            .time(now_ns, WritePrecision.NS)
        )
        points.append(summary)
        
        for dep in (payload.get("departures") or []):
            p = (
                Point(measurement)
                .tag("topic", topic)
                .tag("station", station)
                .tag("line", dep.get("line") or line)
                .tag("direction", dep.get("direction") or "?")
                .field("delay_s", dep.get("delay_s") if dep.get("delay_s") is not None else 0)
                .field("cancelled", int(bool(dep.get("cancelled"))))
                .field("planned_when", dep.get("planned_when") or "")
                .field("actual_when", dep.get("when") or "")
                .time(now_ns, WritePrecision.NS)
            )
            points.append(p)
    
    elif measurement == "bike_status":
        p = (
            Point(measurement)
            .tag("topic", topic)
            .tag("station_id", str(payload.get("station_id", "?")))
            .tag("station_name", payload.get("station_name", "?"))
            .tag("role", payload.get("role", "?"))
            .field("bikes_available", payload.get("bikes_available", 0))
            .field("pickup_viable", int(bool(payload.get("pickup_viable"))))
            .field("is_renting", int(bool(payload.get("is_renting"))))
            .field("is_installed", int(bool(payload.get("is_installed"))))
            .time(now_ns, WritePrecision.NS)
        )
        points.append(p)
    
    elif measurement == "weather":
        city = payload.get("city", "?")
        current = payload.get("current") or {}
        aq      = payload.get("air_quality") or {}
        precip  = payload.get("precip_forecast") or {}
        p = (
            Point(measurement)
            .tag("topic", topic)
            .tag("city", city)
            .field("temp_c",          current.get("temp_c")          or 0.0)
            .field("feels_c",         current.get("feels_c")         or 0.0)
            .field("precipitation_mm", current.get("precipitation_mm") or 0.0)
            .field("wind_kmh",        current.get("wind_kmh")        or 0.0)
            .field("humidity_pct",    current.get("humidity_pct")    or 0.0)
            .field("weather_code",    current.get("weather_code")    or 0)
            .field("weather_text",    current.get("weather_text")    or "")
            .field("aqi_european",    aq.get("aqi_european")         or 0.0)
            .field("pm2_5",           aq.get("pm2_5")                or 0.0)
            .field("pm10",            aq.get("pm10")                 or 0.0)
            .field("precip_next_3h_mm", precip.get("next_3h_mm")     or 0.0)
            .field("precip_any_rain", int(bool(precip.get("any_rain"))))
            .time(now_ns, WritePrecision.NS)
        )
        points.append(p)
    
    elif measurement == "derived_outbound":
        status = payload.get("status", "?")
        plan   = payload.get("plan") or {}
        p = (
            Point(measurement)
            .tag("topic", topic)
            .tag("status", status)
            .tag("urgency", payload.get("urgency", "?") if status == "ok" else "?")
            .field("minutes_until_leave", plan.get("minutes_until_leave") if plan else -1)
            .field("total_minutes",       plan.get("total_minutes")       if plan else -1)
            .field("s45_delay_s",         plan.get("s45_delay_s") or 0)
            .field("rex4_delay_s",        plan.get("rex4_delay_s") or 0)
            .field("leave_by",            plan.get("leave_by") or "")
            .field("eta_krems",           plan.get("eta_krems") or "")
            .time(now_ns, WritePrecision.NS)
        )
        points.append(p)
    
    elif measurement == "derived_return":
        status = payload.get("status", "?")
        rec    = payload.get("recommended") or {}
        p = (
            Point(measurement)
            .tag("topic", topic)
            .tag("status", status)
            .tag("recommended_mode", payload.get("recommended_mode", "?"))
            .field("eta",           rec.get("eta") or "")
            .field("duration_min",  rec.get("duration_min") or 0)
            .field("makes_target",  int(bool(payload.get("makes_target"))))
            .time(now_ns, WritePrecision.NS)
        )
        points.append(p)
    
    return points


class InfluxWriter:
    def __init__(self):
        self.client = InfluxDBClient(
            url=config.INFLUX_URL,
            token=config.INFLUX_TOKEN,
            org=config.INFLUX_ORG,
        )
        self.write_api = self.client.write_api(write_options=ASYNCHRONOUS)
        self.lock = threading.Lock()
        self.count_total = 0
        self.count_errors = 0
    
    def handle(self, topic: str, raw_payload: bytes) -> None:
        try:
            payload = json.loads(raw_payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            log.warning(f"can't parse {topic}: {e}")
            return
        
        try:
            points = payload_to_points(topic, payload)
            if not points:
                return
            self.write_api.write(bucket=config.INFLUX_BUCKET, record=points)
            with self.lock:
                self.count_total += len(points)
        except Exception as e:
            log.exception(f"influx write for {topic} failed: {e}")
            with self.lock:
                self.count_errors += 1
    
    def close(self) -> None:
        self.write_api.close()
        self.client.close()


_writer: InfluxWriter | None = None


def attach(mqtt_client) -> None:
    """Adds an Influx-writing message handler alongside the existing one.
    
    paho-mqtt only supports ONE on_message callback, so we need to chain.
    The subscriber.py on_message already exists; we wrap it.
    """
    global _writer
    _writer = InfluxWriter()
    
    existing_callback = mqtt_client.on_message
    
    def combined_on_message(client, userdata, msg):
        # Original cache update
        if existing_callback is not None:
            existing_callback(client, userdata, msg)
        # New influx write - skip derived topics to match cache behavior? 
        # Actually we DO want derived topics in influx, for historical trends
        _writer.handle(msg.topic, msg.payload)
    
    mqtt_client.on_message = combined_on_message
    
    for topic, qos in SUBSCRIBE_TOPICS:
        mqtt_client.subscribe(topic, qos=qos)
        log.info(f"influx subscribed to {topic}")
    
    # Periodically log throughput so we know it's working
    def stats_loop():
        while True:
            time.sleep(60)
            if _writer is None:
                break
            with _writer.lock:
                log.info(f"influx stats: {_writer.count_total} points written, {_writer.count_errors} errors")
    
    t = threading.Thread(target=stats_loop, name="influx-stats", daemon=True)
    t.start()


def shutdown() -> None:
    global _writer
    if _writer is not None:
        _writer.close()
        _writer = None