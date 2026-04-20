"""Shared MQTT client for all fetchers to publish through."""
import logging
import paho.mqtt.client as mqtt

log = logging.getLogger(__name__)

MQTT_HOST = "localhost"
MQTT_PORT = 1883
CLIENT_ID = "commute-publisher"

def build_client() -> mqtt.Client:
    """Create, connect, and start the MQTT client. Returns it ready to publish."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    
    def on_connect(c, u, f, rc, props):
        log.info(f"MQTT connected (rc={rc})")
    def on_disconnect(c, u, f, rc, props):
        log.warning(f"MQTT disconnected (rc={rc})")
    
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()
    return client