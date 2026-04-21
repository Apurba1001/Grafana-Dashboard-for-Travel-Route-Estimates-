"""Thin wrapper for calling the local hafas-sidecar."""
import logging
import requests

log = logging.getLogger(__name__)

SIDECAR_URL = "http://localhost:3000"
TIMEOUT_S = 20

def departures(eva: str, duration_min: int = 60) -> list[dict]:
    """Fetch departures for a station. Returns a list of departure dicts.
    
    Raises RuntimeError on any failure so callers can catch once.
    """
    url = f"{SIDECAR_URL}/departures/{eva}"
    params = {"duration": duration_min}
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT_S)
        r.raise_for_status()
        data = r.json()
        return data.get("departures", [])
    except requests.RequestException as e:
        raise RuntimeError(f"sidecar departures({eva}) failed: {e}") from e