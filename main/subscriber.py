"""Subscribes to all commute/# topics and feeds state.py.

Runs on the shared MQTT client's callback thread via paho's loop_start().
No separate thread needed here — paho is already threaded.
"""
import logging

import state

log = logging.getLogger(__name__)

SUBSCRIBE_TOPICS = [
    ("commute/outbound/#", 0),
    ("commute/return/#",   0),
    ("commute/weather/#",  0),
]

def on_message(client, userdata, msg) -> None:
    # Ignore our own derived-metric publishes to avoid feedback loops
    if msg.topic.startswith("commute/derived/"):
        return
    state.update(msg.topic, msg.payload)

def attach(mqtt_client) -> None:
    """Register subscriptions and the message handler on an existing client."""
    mqtt_client.on_message = on_message
    for topic, qos in SUBSCRIBE_TOPICS:
        mqtt_client.subscribe(topic, qos=qos)
        log.info(f"subscribed to {topic}")