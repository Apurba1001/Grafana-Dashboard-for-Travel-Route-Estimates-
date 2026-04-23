"""Current weather and air quality for Vienna and Krems via Open-Meteo.

Publishes to:
  commute/weather/vienna/current
  commute/weather/krems/current
"""
import json
import logging
import threading
import time

import requests

import config

log = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIRQUAL_URL  = "https://air-quality-api.open-meteo.com/v1/air-quality"
TIMEOUT_S = 10
POLL_INTERVAL_S = 300   # 15 minutes - weather updates hourly upstream
QOS = 0
RETAIN = True

LOCATIONS = [
    {
        "key":   "vienna",
        "label": "Vienna",
        "lat":   config.HOME_VIENNA_LAT,
        "lon":   config.HOME_VIENNA_LON,
        "topic": "commute/weather/vienna/current",
    },
    {
        "key":   "krems",
        "label": "Krems",
        "lat":   config.KREMS_BAHNHOF_LAT,   # city-scale, so Bahnhof coords are fine
        "lon":   config.KREMS_BAHNHOF_LON,
        "topic": "commute/weather/krems/current",
    },
]

FORECAST_PARAMS = {
    "current": ",".join([
        "temperature_2m",
        "apparent_temperature",
        "precipitation",
        "weather_code",
        "wind_speed_10m",
        "wind_direction_10m",
        "relative_humidity_2m",
    ]),
    "minutely_15": "precipitation",      # 15-min resolution precip for next-hour forecast
    "forecast_minutely_15": 12,          # 12 * 15 min = next 3 hours
    "timezone": "Europe/Vienna",
    "wind_speed_unit": "kmh",
}

AIRQUAL_PARAMS = {
    "current": "european_aqi,pm2_5,pm10",
    "timezone": "Europe/Vienna",
}

# Weather code → human-readable summary (WMO code table, Open-Meteo subset)
# https://open-meteo.com/en/docs
WMO_CODES = {
    0: "clear",
    1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog",
    51: "light drizzle", 53: "drizzle", 55: "dense drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain (light)", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow",
    77: "snow grains",
    80: "light rain showers", 81: "rain showers", 82: "heavy rain showers",
    85: "light snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with heavy hail",
}

def fetch_forecast(lat: float, lon: float) -> dict:
    r = requests.get(
        FORECAST_URL,
        params={**FORECAST_PARAMS, "latitude": lat, "longitude": lon},
        timeout=TIMEOUT_S,
    )
    r.raise_for_status()
    return r.json()

def fetch_airquality(lat: float, lon: float) -> dict:
    r = requests.get(
        AIRQUAL_URL,
        params={**AIRQUAL_PARAMS, "latitude": lat, "longitude": lon},
        timeout=TIMEOUT_S,
    )
    r.raise_for_status()
    return r.json()

def summarize_precipitation(minutely: dict) -> dict:
    """Turn minutely_15 arrays into a summary: total mm, peak mm, whether any rain in next 3h."""
    times = minutely.get("time", [])
    precip = minutely.get("precipitation", [])
    if not precip:
        return {"next_3h_mm": 0.0, "peak_mm": 0.0, "any_rain": False, "series": []}
    
    total = sum(p for p in precip if p is not None)
    peak  = max((p for p in precip if p is not None), default=0.0)
    any_rain = total > 0.1
    
    # Zip time+precip for a compact series the dashboard can chart
    series = [
        {"t": t, "mm": p}
        for t, p in zip(times, precip)
        if p is not None
    ]
    
    return {
        "next_3h_mm": round(total, 2),
        "peak_mm":    round(peak, 2),
        "any_rain":   any_rain,
        "series":     series,
    }

def build_payload(loc: dict, forecast: dict | None, aq: dict | None) -> dict:
    now = int(time.time())
    
    payload = {
        "topic":      loc["topic"],
        "fetched_at": now,
        "source":     "open-meteo",
        "city":       loc["key"],
        "city_label": loc["label"],
        "lat":        loc["lat"],
        "lon":        loc["lon"],
    }
    
    if forecast:
        current = forecast.get("current", {}) or {}
        code = current.get("weather_code")
        payload["current"] = {
            "time":            current.get("time"),
            "temp_c":          current.get("temperature_2m"),
            "feels_c":         current.get("apparent_temperature"),
            "precipitation_mm": current.get("precipitation"),
            "weather_code":    code,
            "weather_text":    WMO_CODES.get(code, "unknown") if code is not None else None,
            "wind_kmh":        current.get("wind_speed_10m"),
            "wind_direction":  current.get("wind_direction_10m"),
            "humidity_pct":    current.get("relative_humidity_2m"),
        }
        payload["precip_forecast"] = summarize_precipitation(forecast.get("minutely_15", {}))
    else:
        payload["current"] = None
        payload["precip_forecast"] = None
    
    if aq:
        aq_current = aq.get("current", {}) or {}
        payload["air_quality"] = {
            "time":        aq_current.get("time"),
            "aqi_european": aq_current.get("european_aqi"),
            "pm2_5":       aq_current.get("pm2_5"),
            "pm10":        aq_current.get("pm10"),
        }
    else:
        payload["air_quality"] = None
    
    return payload

def run_once(mqtt_client) -> None:
    for loc in LOCATIONS:
        forecast = None
        aq = None
        
        try:
            forecast = fetch_forecast(loc["lat"], loc["lon"])
        except requests.RequestException as e:
            log.error(f"forecast fetch for {loc['label']} failed: {e}")
        
        try:
            aq = fetch_airquality(loc["lat"], loc["lon"])
        except requests.RequestException as e:
            log.error(f"air-quality fetch for {loc['label']} failed: {e}")
        
        # Publish whatever we got - partial data is better than no publish
        if forecast is None and aq is None:
            log.warning(f"no data for {loc['label']}, skipping publish")
            continue
        
        payload = build_payload(loc, forecast, aq)
        info = mqtt_client.publish(loc["topic"], json.dumps(payload), qos=QOS, retain=RETAIN)
        
        current = payload.get("current") or {}
        aq_data = payload.get("air_quality") or {}
        log.info(
            f"published {loc['label']}: "
            f"{current.get('temp_c', '?')}°C, "
            f"{current.get('weather_text', '?')}, "
            f"AQI={aq_data.get('aqi_european', '?')} (mid={info.mid})"
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
        name="weather",
        daemon=True,
    )
    thread.start()
    return thread, stop_event