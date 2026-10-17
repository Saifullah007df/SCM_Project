import csv
import io
import json
import re
import secrets
import subprocess
import tempfile
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.auth import check_password, create_session, password_hash, token_hash
from backend.config import Settings
from backend.engine import DomainError, Engine
from backend.files import encode, sha
from backend.storage import now


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class Proposal(BaseModel):
    version: str = Field(min_length=1, max_length=40, pattern=r'^[a-zA-Z0-9._-]+$')
    config: dict
    targets: list[str] = Field(min_length=1, max_length=3)
    differential_revision: int | None = Field(default=None, ge=1)


class Decision(BaseModel):
    digest: str = Field(min_length=64, max_length=64)
    decision: Literal['accept', 'reject'] = 'accept'
    reason: str = Field(min_length=3, max_length=1000)


class Reason(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class Scenario(BaseModel):
    node_id: Literal['ICU-Node-01', 'ICU-Node-02', 'ICU-Node-03']
    scenario: Literal['drift', 'malformed', 'missing', 'formatting', 'reload_failure', 'write_failure', 'offline', 'online', 'clear_faults', 'reset', 'cache_tamper', 'expire_authorization']


class IntegrationState(BaseModel):
    online: bool


class NewUser(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r'^[a-zA-Z0-9_-]+$')
    password: str = Field(min_length=12, max_length=256)
    role: Literal['operator', 'reviewer', 'ccb', 'viewer', 'admin']


def create_app(settings=None):
    settings = settings or Settings()
    engine = Engine(settings)
    store = engine.store
    failures = defaultdict(list)

    @asynccontextmanager
    async def lifespan(app):
        engine.start()
        yield
        engine.stop()

    app = FastAPI(title='AEGIS ICU — Synthetic SCM Demonstrator', version='1.0.0', lifespan=lifespan)
    app.state.engine = engine

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=exc.status)

    @app.middleware('http')
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        if request.url.path.startswith('/api'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def user(request: Request):
        token = request.cookies.get('aegis_session', '')
        session = store.get('sessions', token_hash(token))
        if not session or session['expires'] < time.time():
            raise HTTPException(401, 'Sign in required')
        account = store.get('users', session['user_id'])
        if not account:
            raise HTTPException(401, 'Account unavailable')
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            if not secrets.compare_digest(request.headers.get('x-csrf-token', ''), session['csrf']):
                raise HTTPException(403, 'CSRF token required')
        return {'id': account['id'], 'username': account['username'], 'roles': account['roles'], 'csrf': session['csrf']}

    def roles(*allowed):
        def dependency(account=Depends(user)):
            if not set(allowed).intersection(account['roles']):
                raise HTTPException(403, 'This role cannot perform that action')
            return account
        return dependency

    prefix = '/api/v1'

    @app.get(prefix + '/health')
    def health():
        return {'status': 'ok', 'service': 'aegis-icu', 'simulation_only': True}

    @app.post(prefix + '/auth/login')
    def login(body: Login, request: Request, response: Response):
        key = request.client.host if request.client else 'local'
        failures[key] = [t for t in failures[key] if time.time() - t < 300]
        if len(failures[key]) >= 10:
            raise HTTPException(429, 'Too many failed sign-ins; try again later')
        account = store.get('users', body.username)
        if not account or not check_password(body.password, account['password_hash']):
            failures[key].append(time.time())
            raise HTTPException(401, 'Incorrect username or password')
        failures[key] = []
        token, csrf = create_session(store, account)
        response.set_cookie('aegis_session', token, httponly=True, secure=settings.secure_cookie, samesite='strict', max_age=8 * 3600)
        store.audit('signed_in', account['id'])
        return {'id': account['id'], 'username': account['username'], 'roles': account['roles'], 'csrf': csrf}

    @app.post(prefix + '/auth/logout')
    def logout(request: Request, response: Response, account=Depends(user)):
        store.delete('sessions', token_hash(request.cookies.get('aegis_session', '')))
        response.delete_cookie('aegis_session')
        return {'signed_out': True}

    @app.get(prefix + '/auth/me')
    def me(account=Depends(user)):
        return account

    @app.get(prefix + '/overview')
    def overview(account=Depends(user)):
        nodes = [engine.describe_node(n['id']) for n in store.all('nodes')]
        incidents = store.all('incidents')
        return {'nodes': nodes, 'open_incidents': sum(i['review'] != 'closed' for i in incidents),
                'in_sync': sum(n['connectivity'] == 'online' and n['display_state'] in {'in_sync', 'recovered_verified'} for n in nodes),
                'integrity': store.verify_audit(), 'integration': engine.bridge.status(), 'poll_seconds': settings.poll_seconds,
                'demo': settings.demo, 'server_time': now(), 'simulation_only': True}

    @app.get(prefix + '/nodes')
    def nodes(account=Depends(user)):
        return [engine.describe_node(n['id']) for n in store.all('nodes')]

    @app.get(prefix + '/nodes/{ident}')
    def node(ident: str, account=Depends(user)):
        return engine.describe_node(ident)

    @app.post(prefix + '/scan')
    def scan(account=Depends(roles('operator'))):
        store.audit('scan_requested', account['id'])
        return engine.scan_all()

    @app.get(prefix + '/releases')
    def releases(account=Depends(user)):
        return store.all('releases')

    @app.get(prefix + '/releases/{ident}')
    def release(ident: str, account=Depends(user)):
        return engine.get('releases', ident)

    @app.get(prefix + '/incidents')
    def incidents(account=Depends(user)):
        return list(reversed(store.all('incidents')))

    @app.get(prefix + '/incidents/{ident}')
    def incident(ident: str, account=Depends(user)):
        return engine.get('incidents', ident)

    @app.post(prefix + '/incidents/{ident}/acknowledge')
    def acknowledge(ident: str, body: Reason, account=Depends(roles('operator', 'reviewer', 'ccb'))):
        with store.transaction():
            value = engine.get('incidents', ident)
            if value['review'] == 'closed':
                raise DomainError('Incident already closed')
            value.update(review='acknowledged', acknowledged_by=account['id'], acknowledgement=body.reason)
            store.put('incidents', value)
            store.audit('incident_acknowledged', account['id'], incident_id=ident, reason=body.reason)
            return value

    @app.post(prefix + '/incidents/{ident}/retry')
    def retry(ident: str, body: Reason, account=Depends(roles('operator'))):
        value = engine.get('incidents', ident)
        if value['review'] == 'closed' or value['recovery'] == 'recovered_verified':
            raise DomainError('Only an unresolved recovery may be retried')
        store.audit('manual_retry_requested', account['id'], incident_id=ident, reason=body.reason)
        return engine.recover(ident, account['id'], manual=True)

    @app.post(prefix + '/incidents/{ident}/close')
    def close(ident: str, body: Reason, account=Depends(roles('ccb'))):
        with store.transaction():
            value = engine.get('incidents', ident)
            if value['recovery'] != 'recovered_verified' or not value['acknowledged_by']:
                raise DomainError('Verified recovery and acknowledgement required before closure')
            value.update(review='closed', closed_by=account['id'], closed_at=now(), resolution=body.reason)
            store.put('incidents', value)
            store.audit('incident_closed', account['id'], incident_id=ident, reason=body.reason)
            return value

    @app.get(prefix + '/change-requests')
    def changes(account=Depends(user)):
        return list(reversed(store.all('changes')))

    @app.post(prefix + '/change-requests')
    def propose(body: Proposal, account=Depends(roles('operator', 'reviewer', 'ccb'))):
        try:
            return engine.propose(account['id'], body.version, body.config, body.targets, body.differential_revision)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post(prefix + '/change-requests/{ident}/review')
    def review(ident: str, body: Decision, account=Depends(roles('reviewer'))):
        return engine.decide(ident, account['id'], 'review', body.decision, body.digest, body.reason)

    @app.post(prefix + '/change-requests/{ident}/approve')
    def approve(ident: str, body: Decision, account=Depends(roles('ccb'))):
        return engine.decide(ident, account['id'], 'approve', body.decision, body.digest, body.reason)

    @app.post(prefix + '/change-requests/{ident}/verify-external-review')
    def external_review(ident: str, account=Depends(roles('reviewer'))):
        change = engine.get('changes', ident)
        if settings.phorge_mode != 'real' or not change.get('differential_revision'):
            raise DomainError('Configure real Phorge and a Differential revision first')
        revision = engine.bridge.call('differential.revision.search', {'constraints': {'ids': [change['differential_revision']]}})['data']
        if not revision or revision[0]['fields']['status']['value'] != 'accepted':
            raise DomainError('Differential revision is not accepted')
        diff_phid = revision[0]['fields']['diffPHID']
        diff = engine.bridge.call('differential.diff.search', {'constraints': {'phids': [diff_phid]}})['data'][0]
        raw_diff = engine.bridge.call('differential.getrawdiff', {'diffID': diff['id']})
        base = engine.get('releases', change['base_release_id'])
        with tempfile.TemporaryDirectory(prefix='aegis-review-') as tmp:
            file = Path(tmp) / base['git_path']
            file.parent.mkdir(parents=True)
            file.write_bytes(encode(base['config']))
            result = subprocess.run(['git', 'apply', '--include=' + base['git_path'], '-'], input=raw_diff.encode(), cwd=tmp, capture_output=True)
            if result.returncode or sha(file.read_bytes()) != change['digest']:
                raise DomainError('Accepted Differential patch does not match this exact proposal')
        with store.transaction():
            current = engine.get('changes', ident)
            if current['digest'] != change['digest']:
                raise DomainError('Proposal content changed during external verification')
            current.update(external_review_verified=True, external_diff_id=diff['id'], external_diff_phid=diff_phid)
            store.put('changes', current)
            store.audit('external_review_content_verified', account['id'], change_id=ident, diff_id=diff['id'], digest=current['digest'])
            return current

    @app.post(prefix + '/change-requests/{ident}/deploy')
    def deploy(ident: str, account=Depends(roles('ccb'))):
        return engine.deploy(ident, account['id'])

    @app.get(prefix + '/operations/{ident}')
    def operation(ident: str, account=Depends(user)):
        return engine.get('operations', ident)

    @app.get(prefix + '/audit')
    def audit(account=Depends(user)):
        return {'events': store.events(), 'chain_valid': store.verify_audit(), 'limitation': 'A privileged host administrator can rewrite the database and chain.'}

    @app.get(prefix + '/audit/export')
    def export(format: Literal['json', 'csv'] = 'json', account=Depends(user)):
        store.audit('audit_exported', account['id'], format=format)
        if format == 'json':
            raw = json.dumps({'exported_at': now(), 'simulation_only': True, 'events': store.events(),
                              'incidents': store.all('incidents'), 'operations': store.all('operations'),
                              'releases': store.all('releases'), 'approvals': store.all('approvals'),
                              'audit_chain_valid': store.verify_audit()}, indent=2)
            return Response(raw, media_type='application/json', headers={'Content-Disposition': 'attachment; filename="aegis-evidence.json"'})
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(['seq', 'time', 'action', 'actor', 'node_id', 'incident_id', 'hash'])
        for event in store.events():
            values = [event.get(k, '') for k in ['seq', 'time', 'action', 'actor', 'node_id', 'incident_id', 'hash']]
            writer.writerow(["'" + str(v) if str(v).startswith(('=', '+', '-', '@')) else v for v in values])
        return Response(stream.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="aegis-audit.csv"'})

    @app.get(prefix + '/integrations/phorge/status')
    def integration(account=Depends(user)):
        return engine.bridge.status()

    @app.post(prefix + '/demo/scenarios')
    def scenario(body: Scenario, account=Depends(roles('operator'))):
        return engine.scenario(body.node_id, body.scenario, account['id'])

    @app.post(prefix + '/demo/reporting')
    def reporting(body: IntegrationState, account=Depends(roles('operator'))):
        if not settings.demo:
            raise HTTPException(403, 'Demonstration controls disabled')
        with engine.bridge_lock:
            cfg = store.get('settings', 'integration')
            cfg['online'] = body.online
            store.put('settings', cfg)
            if body.online:
                for job in store.all('outbox'):
                    job['next_try'] = 0
                    store.put('outbox', job)
            store.audit('demo_reporting_connectivity', account['id'], online=body.online)
        return engine.bridge.status()

    @app.post(prefix + '/integrations/phorge/sync')
    def sync(account=Depends(roles('operator', 'admin'))):
        engine.flush_reporting()
        return engine.bridge.status()

    @app.get(prefix + '/admin/users')
    def users(account=Depends(roles('admin'))):
        return [{k: v for k, v in u.items() if k != 'password_hash'} for u in store.all('users')]

    @app.post(prefix + '/admin/users')
    def add_user(body: NewUser, account=Depends(roles('admin'))):
        with store.transaction():
            if store.get('users', body.username):
                raise DomainError('Username already exists')
            store.put('users', {'id': body.username, 'username': body.username, 'roles': [body.role], 'password_hash': password_hash(body.password)})
            store.audit('user_created', account['id'], username=body.username, role=body.role)
            return {'username': body.username, 'roles': [body.role]}

    build = Path(__file__).resolve().parents[1] / 'frontend' / 'dist'
    if (build / 'assets').exists():
        app.mount('/assets', StaticFiles(directory=build / 'assets'), name='assets')

    @app.get('/')
    def index():
        if (build / 'index.html').exists():
            return FileResponse(build / 'index.html')
        return JSONResponse({'message': 'Run npm install && npm run build in frontend, or use its Vite development server.'})

    return app
