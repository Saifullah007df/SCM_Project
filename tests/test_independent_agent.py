import os
import subprocess
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient
from backend.config import Settings
from backend.engine import Engine
from backend.files import atomic_write, encode
from backend.main import create_app


def test_agent_recovers_while_web_api_is_stopped(tmp_path):
    settings = Settings(runtime=tmp_path, embedded_agent=False, background=False, demo_password='Isolated-test-password')
    application = create_app(settings)
    environment = {**os.environ, 'AEGIS_RUNTIME': str(tmp_path), 'AEGIS_POLL_SECONDS': '0.25', 'PHORGE_URL': '', 'PHORGE_TOKEN': ''}
    process = subprocess.Popen([sys.executable, '-m', 'agent.daemon'], cwd=Path(__file__).resolve().parents[1], env=environment,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with TestClient(application) as client:
            assert client.get('/api/v1/health').status_code == 200
        application.state.engine.store.db.close()
        # No API server/lifespan remains. The separate agent owns the monitor processes.
        observer = Engine(settings)
        ident = 'ICU-Node-01'
        baseline = observer.describe_node(ident)['release']['config']
        atomic_write(observer.node_dir(ident) / 'live.json', encode({**baseline, 'alarm_enabled': False}))
        deadline = time.monotonic() + 8
        recovered = False
        while time.monotonic() < deadline:
            incidents = observer.store.all('incidents')
            if incidents and incidents[-1]['recovery'] == 'recovered_verified':
                recovered = True
                break
            time.sleep(.05)
        assert recovered, 'Independent daemon did not recover with API stopped'
        assert observer.describe_node(ident)['effective']['digest'] == observer.describe_node(ident)['release']['digest']
        observer.store.db.close()
    finally:
        process.terminate()
        process.wait(timeout=15)
