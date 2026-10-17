"""Measure real polling with three monitor subprocesses; outputs actual results."""
import argparse
import json
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.config import Settings
from backend.engine import Engine
from backend.storage import now
from backend.files import sha


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--samples', type=int, default=20)
    parser.add_argument('--poll-seconds', type=float, default=10)
    parser.add_argument('--output', type=Path, default=Path('docs/acceptance-results.json'))
    args = parser.parse_args()
    observations = []
    with tempfile.TemporaryDirectory(prefix='aegis-measure-') as runtime:
        engine = Engine(Settings(runtime=Path(runtime), poll_seconds=args.poll_seconds, monitor_processes=True))
        engine.start()
        try:
            for sample in range(args.samples):
                engine.scenario('ICU-Node-01', 'reset', 'measurement-runner')
                previous = len(engine.store.all('incidents'))
                started = time.monotonic()
                engine.scenario('ICU-Node-01', 'drift', 'measurement-runner')
                deadline = started + args.poll_seconds + 12
                incident = None
                while time.monotonic() < deadline:
                    records = engine.store.all('incidents')
                    if len(records) > previous and records[-1]['recovery'] != 'pending':
                        incident = records[-1]
                        break
                    time.sleep(.025)
                if not incident:
                    observations.append({'sample': sample + 1, 'outcome': 'timeout'})
                else:
                    observations.append({'sample': sample + 1, 'outcome': incident['recovery'],
                                         'detection_seconds': round(incident['detected_monotonic'] - started, 4),
                                         'recovery_seconds': round(incident.get('recovery_ms', 0) / 1000, 4)})
                print(json.dumps(observations[-1]), flush=True)
        finally:
            engine.stop()
    detections = [x['detection_seconds'] for x in observations if 'detection_seconds' in x]
    recoveries = [x['recovery_seconds'] for x in observations if 'recovery_seconds' in x]
    result = {'measured_at': now(), 'environment': platform.platform(), 'python': platform.python_version(),
              'engine_source_sha256': sha((Path(__file__).resolve().parents[1] / 'backend' / 'engine.py').read_bytes()),
              'poll_seconds': args.poll_seconds, 'simulated_nodes': 3, 'independent_monitor_processes': True,
              'samples': observations, 'all_verified': all(x['outcome'] == 'recovered_verified' for x in observations),
              'max_detection_seconds': max(detections, default=None), 'mean_detection_seconds': statistics.mean(detections) if detections else None,
              'max_recovery_seconds': max(recoveries, default=None), 'live_phorge_validated': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    return 0 if result['all_verified'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
