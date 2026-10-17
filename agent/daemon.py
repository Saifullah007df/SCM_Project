"""Run monitoring independently from the web API, with a durable local journal."""
import signal
import threading
from backend.config import Settings
from backend.engine import Engine


def main():
    settings = Settings(embedded_agent=True)
    engine = Engine(settings)
    stopped = threading.Event()
    def stop(*_):
        stopped.set()
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    engine.start()
    try:
        stopped.wait()
    finally:
        engine.stop()


if __name__ == '__main__':
    main()
