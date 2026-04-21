"""Commute dashboard publisher entrypoint."""
import logging
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import mqtt_client
import subscriber
from fetchers import (
    rex4_outbound, rex4_return,
    s45_outbound, s45_return,
    nextbike_krems,
    bus1_klpu,
    weather,
)
from derived import outbound_leave_by, return_recommender

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-45s  %(levelname)-7s  %(message)s",
)
log = logging.getLogger("main")

def main() -> None:
    log.info("starting commute publisher")
    client = mqtt_client.build_client()
    time.sleep(0.5)
    
    # Attach the subscriber BEFORE starting fetchers so retained messages
    # fire on_message as soon as subscriptions are established.
    subscriber.attach(client)
    time.sleep(0.5)
    
    fetchers = []
    fetchers.append(rex4_outbound.start(client))
    fetchers.append(rex4_return.start(client))
    fetchers.append(s45_outbound.start(client))
    fetchers.append(s45_return.start(client))
    fetchers.append(nextbike_krems.start(client))
    fetchers.append(bus1_klpu.start(client))
    fetchers.append(weather.start(client))
    fetchers.append(outbound_leave_by.start(client))
    fetchers.append(return_recommender.start(client))
    
    
    def shutdown(signum, frame):
        log.info("shutting down, stopping fetchers...")
        for _thread, stop in fetchers:
            stop.set()
        for thread, _stop in fetchers:
            thread.join(timeout=5)
        client.loop_stop()
        client.disconnect()
        log.info("bye")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()