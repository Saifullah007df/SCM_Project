import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.config import Settings
from backend.engine import Engine

if __name__ == '__main__':
    settings = Settings(background=False, monitor_processes=False)
    engine = Engine(settings)
    print('AEGIS synthetic workspace initialized at', settings.runtime)
    print('Private bootstrap credentials:', settings.runtime / 'bootstrap-credentials.txt')
    engine.store.db.close()
