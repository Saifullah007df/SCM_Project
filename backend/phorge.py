"""Durable Conduit bridge; simulated reporting never pretends to be a real task."""
import json
import time
import httpx
from backend.storage import now


def flatten(value, prefix=''):
    if isinstance(value, dict):
        return {k2: v2 for k, v in value.items() for k2, v2 in flatten(v, f'{prefix}[{k}]' if prefix else k).items()}
    if isinstance(value, list):
        return {k2: v2 for k, v in enumerate(value) for k2, v2 in flatten(v, f'{prefix}[{k}]').items()}
    return {prefix: str(value)}


class PhorgeBridge:
    def __init__(self, settings, store):
        self.settings, self.store = settings, store

    def call(self, method, params):
        if not self.settings.phorge_url.startswith('https://'):
            raise ValueError('Real Phorge requires an HTTPS URL')
        data = flatten(params)
        data['api.token'] = self.settings.phorge_token
        response = httpx.post(self.settings.phorge_url.rstrip('/') + '/api/' + method, data=data, timeout=8, follow_redirects=False)
        response.raise_for_status()
        payload = response.json()
        if payload.get('error_code'):
            raise ValueError('Conduit rejected the request: ' + str(payload['error_code']))
        return payload['result']

    def status(self):
        pending = [x for x in self.store.all('outbox') if x['state'] != 'delivered']
        cfg = self.store.get('settings', 'integration') or {'online': True}
        return {'mode': self.settings.phorge_mode, 'pending': len(pending), 'simulated_online': cfg['online'],
                'configured': self.settings.phorge_mode == 'real', 'last_result': cfg.get('last_result', 'Not contacted'),
                'url': self.settings.phorge_url or None,
                'limitation': 'Live instance integration requires separate configuration and validation.'}

    def enqueue(self, incident):
        key = incident['id']
        if not self.store.get('outbox', key):
            self.store.put('outbox', {'id': key, 'state': 'pending', 'attempts': 0, 'next_try': 0, 'uncertain': False})

    def flush(self):
        cfg = self.store.get('settings', 'integration') or {'id': 'integration', 'online': True}
        for job in self.store.all('outbox'):
            if job['state'] == 'delivered' or job['next_try'] > time.time():
                continue
            incident = self.store.get('incidents', job['id'])
            try:
                if not cfg['online']:
                    raise ConnectionError('Demonstration reporting outage enabled')
                marker = 'AEGIS-INC-' + incident['id']
                if self.settings.phorge_mode == 'simulated':
                    task = {'id': 'SIM-' + incident['id'][:8], 'url': None, 'mode': 'simulated'}
                else:
                    found = self.call('maniphest.search', {'constraints': {'query': marker}}).get('data', [])
                    exact = [x for x in found if marker in x.get('fields', {}).get('description', {}).get('raw', '')]
                    if exact:
                        task = {'id': 'T' + str(exact[0]['id']), 'mode': 'real'}
                    elif job['uncertain']:
                        raise ValueError('Prior creation result uncertain; reconcile in Phorge before retrying creation')
                    else:
                        transactions = [
                            {'type': 'title', 'value': '[DRIFT] ' + incident['node_id'] + ' · ' + incident['severity']},
                            {'type': 'description', 'value': marker + '\nSynthetic monitor incident.\n' + json.dumps(incident, indent=2)},
                            {'type': 'priority', 'value': self.settings.phorge_priority if incident['severity'] == 'SEV-1' else 'low'}]
                        if self.settings.phorge_project:
                            transactions.append({'type': 'projects.add', 'value': [self.settings.phorge_project]})
                        if self.settings.phorge_owner:
                            transactions.append({'type': 'owner', 'value': self.settings.phorge_owner})
                        # Persist ambiguity BEFORE making the external mutation.
                        job['uncertain'] = True
                        self.store.put('outbox', job)
                        obj = self.call('maniphest.edit', {'transactions': transactions})['object']
                        task = {'id': 'T' + str(obj['id']), 'mode': 'real'}
                    task['url'] = self.settings.phorge_url.rstrip('/') + '/' + task['id']
                with self.store.transaction():
                    incident = self.store.get('incidents', incident['id'])
                    incident['task'] = task
                    self.store.put('incidents', incident)
                    job.update(state='delivered', delivered_at=now(), task=task)
                    self.store.put('outbox', job)
                    self.store.audit('incident_reported', incident_id=incident['id'], mode=task['mode'], task_id=task['id'])
                cfg['last_result'] = 'Delivered at ' + now()
            except Exception as exc:
                job.update(attempts=job['attempts'] + 1, error=str(exc)[:250], state='pending', next_try=time.time() + min(60, 2 ** min(job['attempts'] + 1, 6)))
                self.store.put('outbox', job)
                cfg['last_result'] = 'Pending: ' + str(exc)[:150]
        self.store.put('settings', cfg)
