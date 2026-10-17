import json
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.engine import DomainError, Engine
from backend.files import atomic_write, encode, sha
from backend.main import create_app


PASSWORD = 'Only-for-isolated-test-runs'
NODE = 'ICU-Node-01'


@pytest.fixture
def engine(tmp_path):
    value = Engine(Settings(runtime=tmp_path, background=False, monitor_processes=False, demo_password=PASSWORD))
    yield value
    value.stop()
    value.store.db.close()


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(runtime=tmp_path, background=False, monitor_processes=False, demo_password=PASSWORD))
    with TestClient(app) as value:
        yield value
    app.state.engine.store.db.close()


def signin(client, role):
    result = client.post('/api/v1/auth/login', json={'username': role, 'password': PASSWORD})
    assert result.status_code == 200
    return {'x-csrf-token': result.json()['csrf']}


def approved_change(engine, targets=None):
    node = engine.get('nodes', NODE)
    baseline = engine.get('releases', node['release_id'])['config']
    change = engine.propose('operator', 'v2.0', {**baseline, 'demo_heart_rate_upper_bpm': 125}, targets or [NODE])
    engine.decide(change['id'], 'reviewer', 'review', 'accept', change['digest'], 'Fixture reviewed')
    engine.decide(change['id'], 'ccb', 'approve', 'accept', change['digest'], 'Demo deployment approved')
    return change


def test_three_pinned_nodes_and_head_does_not_deploy(engine):
    assignments = {n['id']: n['release_id'] for n in engine.store.all('nodes')}
    assert assignments[NODE] == assignments['ICU-Node-02'] != assignments['ICU-Node-03']
    base = engine.get('releases', assignments[NODE])['config']
    engine.commit_release({**base, 'demo_heart_rate_upper_bpm': 160}, 'unassigned-fixture')
    engine.scan_all()
    assert assignments == {n['id']: n['release_id'] for n in engine.store.all('nodes')}
    assert all(n['config_state'] == 'in_sync' for n in engine.store.all('nodes'))


@pytest.mark.parametrize('scenario,severity', [('drift', 'SEV-1'), ('malformed', 'SEV-1'), ('missing', 'SEV-1'), ('formatting', 'INFO')])
def test_detects_and_verifies_recovery(engine, scenario, severity):
    engine.scenario(NODE, scenario, 'operator')
    incident = engine.scan(NODE)
    assert incident['severity'] == severity
    assert incident['recovery'] == 'recovered_verified'
    assert incident['review'] == 'open'
    assert incident['actor'] == 'operator'
    assert engine.describe_node(NODE)['disk_digest'] == engine.describe_node(NODE)['effective']['digest']
    assert engine.store.all('outbox')[0]['state'] == 'pending'
    assert engine.store.verify_audit()


def test_external_file_editor_is_unknown(engine):
    node = engine.describe_node(NODE)
    atomic_write(engine.node_dir(NODE) / 'live.json', encode({**node['release']['config'], 'alarm_enabled': False}))
    incident = engine.scan(NODE)
    assert incident['actor'] == 'unknown'
    assert incident['provenance'] == 'unobserved_filesystem_change'


@pytest.mark.parametrize('scenario,error', [('cache_tamper', 'integrity'), ('expire_authorization', 'expired')])
def test_invalid_trust_prevents_install(engine, scenario, error):
    engine.scenario(NODE, scenario, 'operator')
    engine.scenario(NODE, 'drift', 'operator')
    digest = sha((engine.node_dir(NODE) / 'live.json').read_bytes())
    incident = engine.scan(NODE)
    assert incident['recovery'] == 'intervention_required'
    assert error in incident['error']
    assert sha((engine.node_dir(NODE) / 'live.json').read_bytes()) == digest


def test_signature_tampering_is_blocked(engine):
    path = engine.node_dir(NODE) / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['manifest']['generation'] += 1
    atomic_write(path, encode(manifest))
    engine.scenario(NODE, 'drift', 'operator')
    result = engine.scan(NODE)
    assert 'signature' in result['error']


@pytest.mark.parametrize('scenario', ['write_failure', 'reload_failure'])
def test_failed_recovery_is_bounded_and_latched(engine, scenario):
    engine.scenario(NODE, scenario, 'operator')
    incident = engine.scan(NODE)
    assert incident['recovery'] == 'intervention_required'
    assert len(incident['attempts']) == 2
    engine.scan(NODE)
    assert len(engine.store.all('incidents')) == 1
    assert engine.get('nodes', NODE)['config_state'] == 'intervention_required'
    engine.scenario(NODE, 'clear_faults', 'operator')
    result = engine.recover(incident['id'], 'operator', manual=True)
    assert result['recovery'] == 'recovered_verified'


def test_symlink_target_does_not_modify_outside_file(engine, tmp_path):
    target = tmp_path / 'outside.json'
    target.write_text('preserve me')
    live = engine.node_dir(NODE) / 'live.json'
    live.unlink()
    live.symlink_to(target)
    incident = engine.scan(NODE)
    assert incident['recovery'] == 'intervention_required'
    assert target.read_text() == 'preserve me'


def test_offline_is_unknown(engine):
    engine.scenario(NODE, 'offline', 'operator')
    result = engine.scan(NODE)
    assert result['state'] == 'unknown'
    assert engine.describe_node(NODE)['display_state'] == 'unknown'
    assert not engine.store.all('incidents')


def test_reporting_outage_does_not_block_recovery_or_restart(engine):
    engine.store.put('settings', {'id': 'integration', 'online': False})
    engine.scenario(NODE, 'drift', 'operator')
    incident = engine.scan(NODE)
    engine.flush_reporting()
    assert incident['recovery'] == 'recovered_verified'
    assert engine.get('outbox', incident['id'])['state'] == 'pending'
    restarted = Engine(engine.settings)
    restarted.store.put('settings', {'id': 'integration', 'online': True})
    job = restarted.get('outbox', incident['id'])
    job['next_try'] = 0
    restarted.store.put('outbox', job)
    restarted.flush_reporting()
    restarted.flush_reporting()
    assert restarted.get('outbox', incident['id'])['state'] == 'delivered'
    assert restarted.get('incidents', incident['id'])['task']['mode'] == 'simulated'
    assert sum(e['action'] == 'incident_reported' for e in restarted.store.events()) == 1
    restarted.store.db.close()


def test_circuit_breaker_stops_repeated_tampering(engine):
    for _ in range(4):
        engine.scenario(NODE, 'drift', 'operator')
        result = engine.scan(NODE)
    assert result['recovery'] == 'intervention_required'
    assert 'circuit breaker' in result['error']


def test_stale_incident_cannot_restore_old_assignment(engine):
    engine.scenario(NODE, 'drift', 'operator')
    incident = engine.scan(NODE)
    change = approved_change(engine)
    assert engine.deploy(change['id'], 'ccb')['change']['state'] == 'deployed'
    with pytest.raises(DomainError, match='stale incident'):
        engine.recover(incident['id'], 'operator', manual=True)
    assert engine.describe_node(NODE)['live_config']['demo_heart_rate_upper_bpm'] == 125
    assert engine.get('nodes', NODE)['config_state'] == 'in_sync'


def test_approved_deployment_does_not_trigger_drift(engine):
    change = approved_change(engine)
    result = engine.deploy(change['id'], 'ccb')
    assert result['change']['state'] == 'deployed'
    engine.scan_all()
    assert engine.describe_node(NODE)['release']['version'] == 'v2.0'
    assert not engine.store.all('incidents')


def test_stale_generation_does_not_overwrite(engine):
    change = approved_change(engine)
    node = engine.get('nodes', NODE)
    node['generation'] += 1
    engine.store.put('nodes', node)
    engine.cache(node, engine.get('releases', node['release_id']))
    before = engine.describe_node(NODE)['disk_digest']
    result = engine.deploy(change['id'], 'ccb')
    assert result['change']['state'] == 'deployment_failed'
    assert result['operations'][0]['rollback'] == 'not_needed_no_replacement'
    assert engine.describe_node(NODE)['disk_digest'] == before


def test_deployment_failure_keeps_assignment_and_reports_rollback(engine):
    change = approved_change(engine)
    prior = engine.get('nodes', NODE)['release_id']
    engine.scenario(NODE, 'reload_failure', 'operator')
    result = engine.deploy(change['id'], 'ccb')
    assert result['change']['state'] == 'deployment_failed'
    assert engine.get('nodes', NODE)['release_id'] == prior
    assert 'intervention_required' in result['operations'][0]['rollback']


def test_self_approval_and_stale_digest_are_denied(engine):
    node = engine.describe_node(NODE)
    change = engine.propose('reviewer', 'v2.0', node['release']['config'], [NODE])
    with pytest.raises(DomainError, match='different people'):
        engine.decide(change['id'], 'reviewer', 'review', 'accept', change['digest'], 'Self review')
    with pytest.raises(DomainError, match='Stale'):
        engine.decide(change['id'], 'other-reviewer', 'review', 'accept', '0' * 64, 'Changed content')


def test_startup_reconciles_interrupted_recovery(engine):
    engine.scenario(NODE, 'drift', 'operator')
    incident = engine.scan(NODE)
    op = engine.store.all('operations')[0]
    op['status'] = 'running'
    op['phase'] = 'replacement_started'
    engine.store.put('operations', op)
    engine.scenario(NODE, 'drift', 'operator')
    engine.reconcile()
    assert engine.get('operations', op['id'])['status'] == 'reconciled'
    assert engine.get('incidents', incident['id'])['recovery'] == 'recovered_verified'
    assert engine.describe_node(NODE)['disk_digest'] == engine.describe_node(NODE)['release']['digest']


def test_audit_chain_detects_modified_event(engine):
    assert engine.store.verify_audit()
    engine.store.db.execute("UPDATE audit SET event='{}' WHERE seq=1")
    assert not engine.store.verify_audit()


def test_recovery_preserves_concurrent_acknowledgement(engine, monkeypatch):
    original = engine.install
    def install_with_acknowledgement(ident, raw):
        original(ident, raw)
        incident = engine.get('incidents', engine.get('nodes', ident)['last_incident'])
        incident.update(review='acknowledged', acknowledged_by='operator', acknowledgement='Investigated while recovery ran')
        engine.store.put('incidents', incident)
    monkeypatch.setattr(engine, 'install', install_with_acknowledgement)
    engine.scenario(NODE, 'drift', 'operator')
    result = engine.scan(NODE)
    assert result['recovery'] == 'recovered_verified'
    assert engine.get('incidents', result['id'])['review'] == 'acknowledged'
    assert engine.get('incidents', result['id'])['acknowledged_by'] == 'operator'


def test_auth_csrf_and_rbac_are_enforced_by_api(client):
    assert client.get('/api/v1/overview').status_code == 401
    headers = signin(client, 'viewer')
    assert client.get('/api/v1/overview').status_code == 200
    assert client.post('/api/v1/scan', headers=headers).status_code == 403
    headers = signin(client, 'operator')
    assert client.post('/api/v1/scan').status_code == 403
    assert client.post('/api/v1/scan', headers=headers).status_code == 200
    assert client.get('/api/v1/admin/users').status_code == 403


def test_incident_acknowledgement_and_closure_workflow(client):
    headers = signin(client, 'operator')
    client.post('/api/v1/demo/scenarios', headers=headers, json={'node_id': NODE, 'scenario': 'drift'})
    client.post('/api/v1/scan', headers=headers)
    incident = client.get('/api/v1/incidents').json()[0]
    ccb = signin(client, 'ccb')
    assert client.post('/api/v1/incidents/' + incident['id'] + '/close', headers=ccb, json={'reason': 'Review complete'}).status_code == 409
    operator = signin(client, 'operator')
    assert client.post('/api/v1/incidents/' + incident['id'] + '/acknowledge', headers=operator, json={'reason': 'Investigating drift'}).status_code == 200
    ccb = signin(client, 'ccb')
    assert client.post('/api/v1/incidents/' + incident['id'] + '/close', headers=ccb, json={'reason': 'Verified recovery and audit reviewed'}).json()['review'] == 'closed'


def test_api_three_person_change_and_evidence_export(client):
    op = signin(client, 'operator')
    config = client.get('/api/v1/nodes/' + NODE).json()['release']['config']
    config['demo_heart_rate_upper_bpm'] = 125
    proposal = client.post('/api/v1/change-requests', headers=op, json={'version': 'v1.3', 'config': config, 'targets': [NODE]}).json()
    payload = {'digest': proposal['digest'], 'reason': 'Reviewed synthetic fixture', 'decision': 'accept'}
    reviewer = signin(client, 'reviewer')
    assert client.post('/api/v1/change-requests/' + proposal['id'] + '/review', headers=reviewer, json=payload).status_code == 200
    ccb = signin(client, 'ccb')
    assert client.post('/api/v1/change-requests/' + proposal['id'] + '/approve', headers=ccb, json=payload).status_code == 200
    result = client.post('/api/v1/change-requests/' + proposal['id'] + '/deploy', headers=ccb).json()
    assert result['change']['state'] == 'deployed'
    assert client.get('/api/v1/audit/export').json()['audit_chain_valid']
    assert client.get('/api/v1/audit/export?format=csv').text.startswith('seq,time')


def test_real_adapter_uncertain_creation_is_not_blindly_repeated(engine, monkeypatch):
    engine.settings.phorge_url = 'https://phorge.example.invalid'
    engine.settings.phorge_token = 'isolated-test-token'
    engine.scenario(NODE, 'drift', 'operator')
    incident = engine.scan(NODE)
    creates = []
    def conduit(method, params):
        if method == 'maniphest.search':
            return {'data': []}
        creates.append(params)
        raise httpx.ReadTimeout('Simulated lost creation response')
    monkeypatch.setattr(engine.bridge, 'call', conduit)
    engine.flush_reporting()
    job = engine.get('outbox', incident['id'])
    assert job['uncertain']
    job['next_try'] = 0
    engine.store.put('outbox', job)
    engine.flush_reporting()
    assert len(creates) == 1
    assert 'reconcile' in engine.get('outbox', incident['id'])['error']
