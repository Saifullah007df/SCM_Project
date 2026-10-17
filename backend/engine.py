"""Local SCM enforcement engine for three explicitly synthetic monitor processes."""
import difflib
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backend.auth import password_hash
from backend.files import atomic_write, encode, sha, stable_read, validate
from backend.phorge import PhorgeBridge
from backend.locks import FileLock
from backend.storage import Store, canonical, now
from simulator.monitor import tick


class DomainError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


class Engine:
    def __init__(self, settings):
        self.settings = settings
        settings.runtime.mkdir(parents=True, exist_ok=True)
        os.chmod(settings.runtime, 0o700)
        self.store = Store(settings.runtime / 'aegis.sqlite3')
        key = settings.runtime / '.agent-key'
        if not key.exists():
            atomic_write(key, secrets.token_bytes(32))
        self.key = key.read_bytes()
        self.locks = {}
        self.release_lock = FileLock(settings.runtime / '.releases.lock')
        self.stop_event = threading.Event()
        self.processes = []
        self.thread = None
        self.reporting_thread = None
        self.bridge_lock = FileLock(settings.runtime / '.reporting.lock')
        self.bridge = PhorgeBridge(settings, self.store)
        self.seed()

    def git(self, *args):
        return subprocess.check_output(['git', '-c', 'user.name=AEGIS Demo', '-c', 'user.email=aegis@localhost', *args],
                                       cwd=self.settings.runtime / 'baseline-git', stderr=subprocess.PIPE).decode().strip()

    def commit_release(self, payload, version, approval=None):
        with self.release_lock:
            return self._commit_release(payload, version, approval)

    def _commit_release(self, payload, version, approval=None):
        raw = encode(payload)
        validate(raw)
        directory = self.settings.runtime / 'baseline-git'
        directory.mkdir(exist_ok=True)
        if not (directory / '.git').exists():
            self.git('init', '-b', 'main')
        relative = 'profiles/' + payload['profile_id'] + '.json'
        (directory / 'profiles').mkdir(exist_ok=True)
        atomic_write(directory / relative, raw)
        self.git('add', '--', relative)
        changed = self.git('status', '--porcelain')
        if changed:
            self.git('commit', '-m', 'Approved synthetic configuration ' + version)
        commit = self.git('rev-parse', 'HEAD')
        artifact = self.settings.runtime / 'artifacts'
        artifact.mkdir(exist_ok=True)
        digest = sha(raw)
        atomic_write(artifact / (digest + '.json'), raw)
        return {'id': 'rel-' + uuid.uuid4().hex[:12], 'version': version, 'profile_id': payload['profile_id'],
                'digest': digest, 'semantic_digest': sha(canonical(payload).encode()), 'git_commit': commit,
                'git_path': relative, 'config': payload, 'created_at': now(),
                'approval': approval or {'type': 'bootstrap_fixture', 'note': 'Initial synthetic fixture, not an externally approved clinical baseline'}}

    def seed(self):
        credentials = []
        for role in ['operator', 'reviewer', 'ccb', 'admin', 'viewer']:
            if not self.store.get('users', role):
                password = self.settings.demo_password or secrets.token_urlsafe(16)
                self.store.put('users', {'id': role, 'username': role, 'roles': [role], 'password_hash': password_hash(password)})
                credentials.append(role + ': ' + password)
        if credentials:
            atomic_write(self.settings.runtime / 'bootstrap-credentials.txt',
                         ('LOCAL DEMO ONLY — keep this file private.\n' + '\n'.join(credentials) + '\n').encode())
        if not self.store.all('nodes'):
            fixtures = Path(__file__).resolve().parents[1] / 'configs' / 'baselines'
            template = json.loads((fixtures / 'demo-legacy.json').read_text())
            legacy = self.commit_release(template, 'v1.1')
            adult = self.commit_release(json.loads((fixtures / 'demo-adult.json').read_text()), 'v1.2')
            self.store.put('releases', legacy)
            self.store.put('releases', adult)
            for i in range(1, 4):
                release = adult if i < 3 else legacy
                node = {'id': f'ICU-Node-{i:02}', 'profile_id': release['profile_id'], 'release_id': release['id'],
                        'generation': 1, 'config_state': 'in_sync', 'last_incident': None, 'circuit_open': False,
                        'last_scan': None, 'last_detection_ms': None, 'authorization_expires': time.time() + 7 * 86400}
                directory = self.node_dir(node['id'])
                (directory / 'cache').mkdir(parents=True, exist_ok=True)
                (directory / 'evidence').mkdir(exist_ok=True)
                atomic_write(directory / 'control.json', encode({'online': True, 'reload_failure': False, 'write_failure': False}))
                atomic_write(directory / 'live.json', encode(release['config']))
                self.cache(node, release)
                self.store.put('nodes', node)
                tick(directory)
            self.store.audit('demo_initialized', note='Three synthetic monitors; no patient data')
        self.store.put('settings', self.store.get('settings', 'integration') or {'id': 'integration', 'online': True})

    def node_dir(self, ident):
        if ident not in {'ICU-Node-01', 'ICU-Node-02', 'ICU-Node-03'}:
            raise DomainError('Unknown demo node', 404)
        path = self.settings.runtime / 'nodes' / ident
        if path.is_symlink() or not path.resolve().is_relative_to(self.settings.runtime.resolve()):
            raise DomainError('Node directory escapes sandbox')
        return path

    def lock(self, ident):
        # Nodes are fixed at initialization, and dictionary creation is serialized.
        with self.store.lock:
            return self.locks.setdefault(ident, FileLock(self.node_dir(ident) / '.operation.lock'))

    def get(self, kind, ident):
        result = self.store.get(kind, ident)
        if result is None:
            raise DomainError(f'{kind}: item not found', 404)
        return result

    def sign(self, manifest):
        return hmac.new(self.key, canonical(manifest).encode(), hashlib.sha256).hexdigest()

    def cache(self, node, release):
        directory = self.node_dir(node['id'])
        artifact = directory / 'cache' / (release['id'] + '.json')
        atomic_write(artifact, encode(release['config']))
        manifest = {'node_id': node['id'], 'release_id': release['id'], 'digest': release['digest'],
                    'profile_id': release['profile_id'], 'generation': node['generation'], 'expires': node['authorization_expires']}
        atomic_write(directory / 'manifest.json', encode({'manifest': manifest, 'signature': self.sign(manifest)}))

    def trusted(self, node):
        directory = self.node_dir(node['id'])
        bundle = json.loads(stable_read(directory / 'manifest.json'))
        manifest = bundle['manifest']
        if not hmac.compare_digest(bundle['signature'], self.sign(manifest)):
            raise DomainError('Cached authorization signature mismatch')
        expected = {'node_id': node['id'], 'release_id': node['release_id'], 'profile_id': node['profile_id'], 'generation': node['generation']}
        if any(manifest.get(k) != v for k, v in expected.items()):
            raise DomainError('Cached authorization scope or generation mismatch')
        if min(manifest['expires'], node['authorization_expires']) < time.time():
            raise DomainError('Cached recovery authorization expired')
        raw = stable_read(directory / 'cache' / (node['release_id'] + '.json'))
        release = self.get('releases', node['release_id'])
        if sha(raw) != release['digest'] or manifest['digest'] != release['digest']:
            raise DomainError('Baseline artifact integrity mismatch')
        if validate(raw)['profile_id'] != node['profile_id']:
            raise DomainError('Profile mismatch')
        return raw

    def start(self):
        if not self.settings.embedded_agent:
            return
        if self.settings.monitor_processes:
            for node in self.store.all('nodes'):
                process = subprocess.Popen([sys.executable, '-m', 'simulator.monitor', str(self.node_dir(node['id']))],
                                           cwd=Path(__file__).resolve().parents[1], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.processes.append(process)
            time.sleep(0.25)
        self.reconcile()
        if self.settings.background:
            self.thread = threading.Thread(target=self.loop, name='aegis-agent-supervisor', daemon=True)
            self.thread.start()
            self.reporting_thread = threading.Thread(target=self.reporting_loop, name='aegis-reporting-worker', daemon=True)
            self.reporting_thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=15)
        if self.reporting_thread:
            self.reporting_thread.join(timeout=10)
        for process in self.processes:
            process.terminate()
        for process in self.processes:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    def loop(self):
        next_scan = 0
        while not self.stop_event.is_set():
            try:
                if time.monotonic() >= next_scan:
                    self.scan_all()
                    next_scan = time.monotonic() + self.settings.poll_seconds
            except Exception as exc:
                # A supervisor fault is recorded, rather than silently passing.
                try:
                    self.store.audit('supervisor_fault', error=str(exc)[:200])
                except Exception:
                    print('AEGIS supervisor: evidence storage unavailable', file=sys.stderr)
            self.stop_event.wait(0.25)

    def reporting_loop(self):
        while not self.stop_event.is_set():
            try:
                self.flush_reporting()
            except Exception as exc:
                try:
                    self.store.audit('reporting_worker_fault', error=str(exc)[:200])
                except Exception:
                    print('AEGIS reporting worker: evidence storage unavailable', file=sys.stderr)
            self.stop_event.wait(1)

    def flush_reporting(self):
        with self.bridge_lock:
            self.bridge.flush()

    def scan_all(self):
        with ThreadPoolExecutor(max_workers=3) as pool:
            return list(pool.map(self.scan, [n['id'] for n in self.store.all('nodes')]))

    def controls(self, ident):
        return json.loads(stable_read(self.node_dir(ident) / 'control.json'))

    def effective(self, ident):
        try:
            return json.loads(stable_read(self.node_dir(ident) / 'effective.json'))
        except (OSError, ValueError):
            return {}

    def describe_node(self, ident):
        node = self.get('nodes', ident)
        directory = self.node_dir(ident)
        try:
            age = max(0, time.time() - json.loads(stable_read(directory / 'heartbeat.json'))['time'])
        except (OSError, ValueError):
            age = None
        online = self.controls(ident)['online'] and age is not None and age < 5
        release = self.get('releases', node['release_id'])
        try:
            raw = stable_read(directory / 'live.json')
            disk = sha(raw)
            try:
                config = validate(raw)
            except ValueError:
                config = None
        except (OSError, ValueError):
            disk, config = None, None
        display = node['config_state']
        if display in {'in_sync', 'recovered_verified'} and disk != release['digest']:
            display = 'awaiting_scan'
        return {**node, 'connectivity': 'online' if online else 'offline', 'heartbeat_age': round(age, 1) if age is not None else None,
                'display_state': display if online else 'unknown', 'release': release,
                'disk_digest': disk, 'live_config': config, 'effective': self.effective(ident)}

    def scan(self, ident):
        with self.lock(ident):
            node = self.get('nodes', ident)
            if not self.settings.monitor_processes and self.settings.embedded_agent:
                tick(self.node_dir(ident))
            if self.describe_node(ident)['connectivity'] != 'online':
                return {'node_id': ident, 'state': 'unknown'}
            node['last_scan'] = now()
            self.store.put('nodes', node)
            live = self.node_dir(ident) / 'live.json'
            try:
                raw = stable_read(live)
                fingerprint = sha(raw)
            except (OSError, ValueError) as exc:
                raw, fingerprint = b'', 'unreadable:' + type(exc).__name__
            release = self.get('releases', node['release_id'])
            if fingerprint == release['digest']:
                effective = self.effective(ident)
                if effective.get('digest') == release['digest'] and not self.controls(ident)['reload_failure']:
                    node['config_state'] = 'in_sync'
                    self.store.put('nodes', node)
                    return {'node_id': ident, 'state': 'in_sync'}
                reason = 'effective_state_mismatch'
            else:
                reason = 'configuration_drift'
            previous = self.store.get('incidents', node.get('last_incident') or '')
            if previous and previous['recovery'] == 'intervention_required' and node['config_state'] == 'intervention_required' and fingerprint in {previous['fingerprint'], release['digest']}:
                return previous
            if previous and previous['fingerprint'] == fingerprint and previous['generation'] == node['generation'] and previous['recovery'] != 'recovered_verified':
                return previous
            try:
                parsed = validate(raw)
                formatting = parsed == release['config']
            except ValueError:
                formatting = False
            incident_id = str(uuid.uuid4())
            actor = node.pop('pending_actor', 'unknown')
            provenance = 'authenticated_demo_action' if actor != 'unknown' else 'unobserved_filesystem_change'
            evidence = self.node_dir(ident) / 'evidence' / (incident_id + '.bin')
            atomic_write(evidence, raw)
            diff = ''.join(difflib.unified_diff(encode(release['config']).decode().splitlines(True), raw.decode('utf-8', errors='replace').splitlines(True), fromfile='approved', tofile='observed'))
            incident = {'id': incident_id, 'node_id': ident, 'release_id': node['release_id'], 'generation': node['generation'],
                        'fingerprint': fingerprint, 'reason': 'formatting_drift' if formatting else reason,
                        'severity': 'INFO' if formatting else 'SEV-1', 'detected_at': now(), 'detected_monotonic': time.monotonic(),
                        'actor': actor, 'provenance': provenance, 'diff': diff, 'before': release['config'],
                        'observed_text': raw.decode('utf-8', errors='replace'), 'recovery': 'pending', 'review': 'open',
                        'acknowledged_by': None, 'task': None, 'attempts': [], 'evidence_file': evidence.name}
            recent = [x for x in self.store.all('incidents') if x['node_id'] == ident and time.time() - x.get('detected_epoch', 0) < 60 and x.get('detected_epoch', 0) > node.get('circuit_reset_epoch', 0)]
            incident['detected_epoch'] = time.time()
            if len(recent) >= 3:
                node['circuit_open'] = True
            with self.store.transaction():
                node.update(last_incident=incident_id, config_state='drift_detected')
                self.store.put('nodes', node)
                self.store.put('incidents', incident)
                self.store.audit('drift_detected', actor, node_id=ident, incident_id=incident_id,
                                 provenance=provenance, digest=fingerprint, reason=incident['reason'])
            return self.recover(incident_id)

    def journal(self, ident, operation, phase):
        operation['phase'] = phase
        operation['updated_at'] = now()
        atomic_write(self.node_dir(ident) / 'journal.json', encode(operation))
        self.store.put('operations', operation)
        self.store.audit('operation_step', node_id=ident, operation_id=operation['id'], incident_id=operation.get('incident_id'), phase=phase, status=operation['status'])

    def install(self, ident, raw):
        validate(raw)
        controls = self.controls(ident)
        if controls['write_failure']:
            raise OSError('Simulated write permission failure')
        atomic_write(self.node_dir(ident) / 'live.json', raw)
        if sha(stable_read(self.node_dir(ident) / 'live.json')) != sha(raw):
            raise DomainError('Disk readback mismatch')
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if not self.settings.monitor_processes and self.settings.embedded_agent:
                tick(self.node_dir(ident))
            if not controls['reload_failure'] and self.effective(ident).get('digest') == sha(raw):
                return
            time.sleep(0.04)
        raise DomainError('Effective configuration reload verification failed')

    def recover(self, incident_id, actor='agent', manual=False):
        incident = self.get('incidents', incident_id)
        ident = incident['node_id']
        with self.lock(ident):
            node = self.get('nodes', ident)
            if node['generation'] != incident['generation'] or node['release_id'] != incident['release_id']:
                raise DomainError('Assignment changed; stale incident cannot restore an old release')
            operation = {'id': str(uuid.uuid4()), 'kind': 'recovery', 'node_id': ident, 'incident_id': incident_id,
                         'generation': node['generation'], 'status': 'running', 'created_at': now()}
            self.journal(ident, operation, 'intent_persisted')
            started = time.monotonic()
            try:
                if node['circuit_open'] and not manual:
                    raise DomainError('Repeated drift circuit breaker open')
                if self.describe_node(ident)['connectivity'] != 'online':
                    raise DomainError('Node is offline; effective recovery cannot be verified')
                raw = self.trusted(node)
                self.journal(ident, operation, 'artifact_verified')
                try:
                    current = sha(stable_read(self.node_dir(ident) / 'live.json'))
                except (OSError, ValueError) as exc:
                    current = 'unreadable:' + type(exc).__name__
                if not manual and current != incident['fingerprint']:
                    raise DomainError('Configuration changed after observation; rescan required')
                for number in range(2):
                    attempt = {'number': len(incident['attempts']) + 1, 'started_at': now(), 'actor': actor}
                    incident['attempts'].append(attempt)
                    self.save_incident(incident)
                    try:
                        self.journal(ident, operation, 'replacement_started')
                        self.install(ident, raw)
                        attempt.update(outcome='verified', finished_at=now())
                        break
                    except (OSError, ValueError, DomainError) as exc:
                        attempt.update(outcome='failed', error=str(exc), finished_at=now())
                        if number == 1:
                            raise
                incident.update(recovery='recovered_verified', recovered_at=now(), recovery_ms=round((time.monotonic() - started) * 1000, 2))
                node.update(config_state='recovered_verified', circuit_open=False)
                operation['status'] = 'succeeded'
                self.journal(ident, operation, 'effective_verified')
                self.store.audit('recovery_verified', actor, node_id=ident, incident_id=incident_id, digest=sha(raw), operation_id=operation['id'])
            except (OSError, ValueError, KeyError, DomainError) as exc:
                incident.update(recovery='intervention_required', error=str(exc))
                node['config_state'] = 'intervention_required'
                operation.update(status='failed', error=str(exc))
                self.journal(ident, operation, 'failed')
                self.store.audit('recovery_failed', actor, node_id=ident, incident_id=incident_id, error=str(exc), operation_id=operation['id'])
            with self.store.transaction():
                self.store.put('nodes', node)
                self.save_incident(incident)
                self.bridge.enqueue(incident)
            return incident

    def save_incident(self, incident):
        # Recovery must not erase a concurrent operator acknowledgement or report.
        with self.store.transaction():
            current = self.store.get('incidents', incident['id'])
            if current:
                for field in ['review', 'acknowledged_by', 'acknowledgement', 'closed_by', 'closed_at', 'resolution', 'task']:
                    if field in current:
                        incident[field] = current[field]
            self.store.put('incidents', incident)

    def reconcile(self):
        for operation in self.store.all('operations'):
            if operation['status'] != 'running':
                continue
            ident = operation['node_id']
            with self.lock(ident):
                try:
                    node = self.get('nodes', ident)
                    if operation['kind'] == 'deployment':
                        release = self.get('releases', node['release_id'])
                        git_raw = subprocess.check_output(['git', 'show', release['git_commit'] + ':' + release['git_path']], cwd=self.settings.runtime / 'baseline-git')
                        if sha(git_raw) != release['digest']:
                            raise DomainError('Persisted assignment does not match Git artifact')
                        self.cache(node, release)
                    raw = self.trusted(node)
                    self.install(ident, raw)
                    node['config_state'] = 'recovered_verified'
                    self.store.put('nodes', node)
                    operation.update(status='reconciled', result='Assigned approved baseline and effective state verified after interrupted operation')
                    if operation.get('incident_id'):
                        incident = self.get('incidents', operation['incident_id'])
                        incident.update(recovery='recovered_verified', recovered_at=now())
                        self.save_incident(incident)
                        self.bridge.enqueue(incident)
                except Exception as exc:
                    operation.update(status='failed', error='Startup reconciliation: ' + str(exc))
                    node = self.get('nodes', ident)
                    node['config_state'] = 'intervention_required'
                    self.store.put('nodes', node)
                self.journal(ident, operation, 'startup_reconciled')
                self.store.audit('startup_reconciled', node_id=ident, operation_id=operation['id'], status=operation['status'])

    def scenario(self, ident, scenario, actor):
        if not self.settings.demo:
            raise DomainError('Demonstration controls disabled', 403)
        with self.lock(ident):
            node = self.get('nodes', ident)
            directory = self.node_dir(ident)
            control = self.controls(ident)
            if scenario == 'reset':
                node.update(authorization_expires=time.time() + 7 * 86400, circuit_open=False, config_state='in_sync', circuit_reset_epoch=time.time())
                release = self.get('releases', node['release_id'])
                self.cache(node, release)
                control.update(online=True, write_failure=False, reload_failure=False)
                atomic_write(directory / 'control.json', encode(control))
                self.install(ident, encode(release['config']))
            elif scenario in {'offline', 'online'}:
                control['online'] = scenario == 'online'
            elif scenario == 'clear_faults':
                control.update(online=True, write_failure=False, reload_failure=False)
            elif scenario == 'expire_authorization':
                node['authorization_expires'] = time.time() - 1
            elif scenario == 'cache_tamper':
                atomic_write(directory / 'cache' / (node['release_id'] + '.json'), b'{"tampered": true}')
            elif scenario in {'drift', 'malformed', 'missing', 'formatting', 'reload_failure', 'write_failure'}:
                baseline = self.get('releases', node['release_id'])['config']
                raw = encode({**baseline, 'demo_heart_rate_upper_bpm': baseline['demo_heart_rate_upper_bpm'] + 60})
                if scenario == 'malformed':
                    raw = b'{ invalid synthetic JSON'
                if scenario == 'formatting':
                    raw = json.dumps(baseline).encode()
                if scenario in {'reload_failure', 'write_failure'}:
                    control[scenario] = True
                if scenario == 'missing':
                    (directory / 'live.json').unlink(missing_ok=True)
                else:
                    atomic_write(directory / 'live.json', raw)
                node['pending_actor'] = actor
                node['last_injected_epoch'] = time.time()
            else:
                raise DomainError('Unknown fixed demonstration scenario', 422)
            atomic_write(directory / 'control.json', encode(control))
            self.store.put('nodes', node)
            self.store.audit('demo_scenario', actor, node_id=ident, scenario=scenario)
            return self.describe_node(ident)

    def propose(self, actor, version, payload, targets, revision=None):
        with self.store.transaction():
            return self._propose(actor, version, payload, targets, revision)

    def _propose(self, actor, version, payload, targets, revision=None):
        validate(encode(payload))
        if not targets or len(set(targets)) != len(targets):
            raise DomainError('Choose a nonempty unique node scope', 422)
        generations = {}
        for ident in targets:
            node = self.get('nodes', ident)
            if node['profile_id'] != payload['profile_id']:
                raise DomainError('Profile does not match selected nodes', 422)
            generations[ident] = node['generation']
        if any(r['version'] == version for r in self.store.all('releases')):
            raise DomainError('Release version already exists')
        if any(c['version'] == version and c['state'] != 'rejected' for c in self.store.all('changes')):
            raise DomainError('A proposal already reserves this release version')
        request = {'id': 'CR-' + uuid.uuid4().hex[:8], 'author': actor, 'version': version, 'config': payload,
                   'digest': sha(encode(payload)), 'targets': targets, 'base_generations': generations,
                   'state': 'proposed', 'created_at': now(), 'differential_revision': revision,
                   'external_review_verified': False, 'base_release_id': self.get('nodes', targets[0])['release_id']}
        self.store.put('changes', request)
        self.store.audit('change_proposed', actor, change_id=request['id'], digest=request['digest'], targets=targets)
        return request

    def decide(self, change_id, actor, stage, decision, digest, reason):
        with self.store.transaction():
            change = self.get('changes', change_id)
            if digest != change['digest']:
                raise DomainError('Stale proposal digest')
            if actor == change['author'] or (stage == 'approve' and actor == change.get('reviewer')):
                raise DomainError('Submitter, reviewer and CCB approver must be different people', 403)
            expected = 'proposed' if stage == 'review' else 'reviewed'
            if change['state'] != expected:
                raise DomainError('Proposal is not ready for this decision')
            change['state'] = ('reviewed' if stage == 'review' else 'approved') if decision == 'accept' else 'rejected'
            change['reviewer' if stage == 'review' else 'approver'] = actor
            if stage == 'approve' and decision == 'accept':
                change['authorization_expires'] = time.time() + 3600
            record = {'id': str(uuid.uuid4()), 'change_id': change_id, 'actor': actor, 'stage': stage,
                      'decision': decision, 'digest': digest, 'reason': reason, 'time': now()}
            self.store.put('approvals', record)
            self.store.put('changes', change)
            self.store.audit('change_' + stage, actor, change_id=change_id, decision=decision, digest=digest)
            return change

    def deploy(self, change_id, actor):
        candidate = self.get('changes', change_id)
        if self.settings.phorge_mode == 'real':
            if not candidate.get('external_review_verified'):
                raise DomainError('Real integration requires verified accepted Differential content before deployment')
            revisions = self.bridge.call('differential.revision.search', {'constraints': {'ids': [candidate['differential_revision']]}})['data']
            if not revisions or revisions[0]['fields']['status']['value'] != 'accepted' or revisions[0]['fields']['diffPHID'] != candidate.get('external_diff_phid'):
                raise DomainError('Differential review changed after verification; reverify current accepted content')
        with self.store.transaction():
            change = self.get('changes', change_id)
            if change['digest'] != candidate['digest']:
                raise DomainError('Proposal content changed during verification')
            if change['state'] != 'approved' or change.get('authorization_expires', 0) < time.time():
                raise DomainError('Valid approved deployment authorization required')
            change['state'] = 'deploying'
            self.store.put('changes', change)
        # Never hold a SQLite write transaction while acquiring a node lock.
        operations = []
        try:
            release = self.commit_release(change['config'], change['version'], {'change_id': change_id, 'reviewer': change['reviewer'], 'approver': change['approver'], 'digest': change['digest'], 'differential_revision': change.get('differential_revision'), 'external_review_verified': change.get('external_review_verified', False)})
            self.store.put('releases', release)
            for ident in sorted(change['targets']):
                with self.lock(ident):
                    node = self.get('nodes', ident)
                    operation = {'id': str(uuid.uuid4()), 'kind': 'deployment', 'node_id': ident, 'change_id': change_id,
                                 'status': 'running', 'created_at': now(), 'prior_release_id': node['release_id'], 'target_release_id': release['id']}
                    operations.append(operation)
                    self.journal(ident, operation, 'intent_persisted')
                    replacement_started = False
                    try:
                        if node['generation'] != change['base_generations'][ident]:
                            raise DomainError('Node assignment generation changed since proposal')
                        if self.describe_node(ident)['connectivity'] != 'online':
                            raise DomainError('Deployment target offline')
                        old_raw = self.trusted(node)
                        replacement_started = True
                        self.install(ident, encode(release['config']))
                        # Assignment and operation are journaled; reconciliation restores the persisted assignment after a crash.
                        new_node = {**node, 'release_id': release['id'], 'generation': node['generation'] + 1,
                                    'authorization_expires': time.time() + 7 * 86400, 'config_state': 'in_sync'}
                        self.cache(new_node, release)
                        self.store.put('nodes', new_node)
                        operation.update(status='succeeded', generation=new_node['generation'])
                        self.journal(ident, operation, 'effective_verified')
                        self.store.audit('deployment_verified', actor, node_id=ident, change_id=change_id, release_id=release['id'])
                    except Exception as exc:
                        operation.update(status='failed', error=str(exc))
                        try:
                            if replacement_started:
                                prior = self.get('releases', node['release_id'])
                                self.cache(node, prior)
                                self.install(ident, old_raw)
                                operation['rollback'] = 'prior_release_verified'
                            else:
                                operation['rollback'] = 'not_needed_no_replacement'
                        except Exception as rollback:
                            operation['rollback'] = 'intervention_required: ' + str(rollback)
                            node['config_state'] = 'intervention_required'
                            self.store.put('nodes', node)
                        self.journal(ident, operation, 'failed')
                        self.store.audit('deployment_failed', actor, node_id=ident, change_id=change_id, error=str(exc), rollback=operation['rollback'])
            change.update(state='deployed' if all(op['status'] == 'succeeded' for op in operations) else 'deployment_failed', release_id=release['id'])
        except Exception as exc:
            change.update(state='deployment_failed', error=str(exc))
        self.store.put('changes', change)
        return {'change': change, 'operations': operations}
