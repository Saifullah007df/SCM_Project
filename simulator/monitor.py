"""Independent synthetic monitor process; it never connects to medical devices."""
import json
import sys
import time
from pathlib import Path
from backend.files import atomic_write, encode, sha, stable_read, validate


def tick(directory):
    directory = Path(directory)
    control = json.loads((directory / 'control.json').read_text())
    if not control.get('online', True):
        return
    atomic_write(directory / 'heartbeat.json', encode({'time': time.time()}))
    if control.get('reload_failure'):
        return
    try:
        raw = stable_read(directory / 'live.json')
        payload = validate(raw)
        existing = json.loads((directory / 'effective.json').read_text()) if (directory / 'effective.json').exists() else {}
        if existing.get('digest') != sha(raw):
            atomic_write(directory / 'effective.json', encode({'digest': sha(raw), 'payload': payload, 'loaded_at': time.time(), 'healthy': True}))
    except (OSError, ValueError):
        # Invalid configuration is not loaded. The drift agent records it.
        return


if __name__ == '__main__':
    node = Path(sys.argv[1]).resolve()
    while True:
        try:
            tick(node)
        except (OSError, ValueError):
            pass
        time.sleep(0.15)
