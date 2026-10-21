"""Focused regression tests for additive two-window manual-file demonstration."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app


def test_two_window_routes_and_existing_recovery(tmp_path):
    settings = Settings(runtime=tmp_path / 'runtime', background=False,
                        monitor_processes=False, embedded_agent=True, demo=True)
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get('/demo/server').status_code == 200
        assert client.get('/demo/device').status_code == 200
        assert 'Server' in client.get('/demo/server').text
        engine = app.state.engine
        path = engine.node_dir('ICU-Node-01') / 'live.json'
        original = path.read_bytes()
        changed = json.loads(original)
        changed['heart_rate']['upper_bpm'] = 160
        path.write_text(json.dumps(changed))
        assert path.read_bytes() != original
        engine.scan('ICU-Node-01')
        assert path.read_bytes() == original
        state = engine.describe_node('ICU-Node-01')
        assert state['effective']['digest'] == state['release']['digest']
