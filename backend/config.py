"""Explicit local-demo configuration. No secrets or medical data in source control."""
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    runtime: Path = field(default_factory=lambda: Path(os.getenv('AEGIS_RUNTIME', 'runtime')).resolve())
    poll_seconds: float = field(default_factory=lambda: float(os.getenv('AEGIS_POLL_SECONDS', '10')))
    demo: bool = field(default_factory=lambda: os.getenv('AEGIS_DEMO', 'true').lower() == 'true')
    background: bool = True
    monitor_processes: bool = True
    embedded_agent: bool = field(default_factory=lambda: os.getenv('AEGIS_EMBEDDED_AGENT', 'true').lower() == 'true')
    demo_password: str | None = field(default_factory=lambda: os.getenv('AEGIS_BOOTSTRAP_PASSWORD'))
    secure_cookie: bool = field(default_factory=lambda: os.getenv('AEGIS_SECURE_COOKIE', 'false').lower() == 'true')
    phorge_url: str = field(default_factory=lambda: os.getenv('PHORGE_URL', ''))
    phorge_token: str = field(default_factory=lambda: os.getenv('PHORGE_TOKEN', ''))
    phorge_project: str = field(default_factory=lambda: os.getenv('PHORGE_PROJECT_PHID', ''))
    phorge_owner: str = field(default_factory=lambda: os.getenv('PHORGE_OWNER_PHID', ''))
    phorge_priority: str = field(default_factory=lambda: os.getenv('PHORGE_PRIORITY', 'high'))

    @property
    def phorge_mode(self):
        return 'real' if self.phorge_url and self.phorge_token else 'simulated'
