# AEGIS ICU

### Configuration integrity. Verified recovery. Accountable change.

A working academic Software Configuration Management project implementing the REVIEW-01 proposal: detect configuration drift on **three synthetic ICU monitor processes**, restore a node's pinned baseline, verify the effective configuration, retain evidence, and route incidents into review.

**This is a local simulation, not medical-device software.** Thresholds are arbitrary fixtures. There are no patient connections or patient records.

## What is implemented

| Phase | Delivered |
|---|---|
| 1. Baselines and simulators | Two initial Git releases; three independent monitor processes; per-node release assignments |
| 2. Drift detection | 10-second agent polling; byte/semantic comparisons; malformed/missing file detection; actor provenance and evidence |
| 3. Recovery | Signed local manifests; cached artifacts; process locks; atomic replacement; effective-state verification; retry bound and circuit breaker |
| 4. Connected GUI | Sign-in, overview, fleet, baselines, incidents, change control, audit, settings and controlled fault injection |
| 5. Governance | Operator/reviewer/CCB separation; digest-bound decisions; scoped deployment; stale-generation rejection; acknowledgement/closure |
| 6. Phorge bridge | Real Conduit adapter, exact Differential patch verification, durable task queue, simulated adapter and outage controls |
| 7. Verification | Backend fault/workflow tests; browser journey; actual polling measurements; CI configuration and demo guide |

**External gate:** no live Phorge instance or credentials were supplied. Real Maniphest creation, your instance's supported Conduit schema, Herald routing and repository protections must be validated after configuration. Simulated reports are labelled `SIM-…` and never described as real tasks.

## Quick start — Linux / Fedora

Prerequisites: **Git, Python 3.12+ with venv support, Node.js 22.12+ and npm**. POSIX filesystem locks are used; Windows users should use WSL.

```bash
git clone https://github.com/Saifullah007df/SCM_Project.git
cd SCM_Project
bash run.sh
```

The script installs dependencies, builds the GUI, initializes private random demo accounts, starts an **independent agent daemon**, and starts the web API. Open:

**http://127.0.0.1:8000**

In a second terminal inside the repository:

```bash
cat runtime/bootstrap-credentials.txt
```

Use the `operator` account first. Separate `reviewer`, `ccb`, `admin` and `viewer` accounts are provided. The administrator role does not automatically grant CCB authority. Bootstrap passwords are generated on the first initialization; changing an environment variable later does not reset existing accounts.

GitHub authentication for a private clone is handled by your usual Git credential setup.

### Manual setup / development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
python scripts/init_demo.py
python -m uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000
```

This manual API command embeds the agent for convenience. For independent recovery when the API is stopped, use two terminals sharing the same runtime directory:

```bash
# Terminal 1: independent agent and three monitor processes
source .venv/bin/activate
python -m agent.daemon
```

```bash
# Terminal 2: API without a second agent
source .venv/bin/activate
AEGIS_EMBEDDED_AGENT=false python -m uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000
```

Do not start a second monitor/agent supervisor for the same workspace. For frontend editing, run `npm --prefix frontend run dev`; Vite proxies `/api` to port 8000. Restart the API after rebuilding the frontend because static asset mounting is established at startup. Avoid `--reload` watching the changing runtime tree.

## First demonstration

1. Sign in as **operator** and inspect the three nodes.
2. Open **Demonstration controls**, choose Node 01 and **Unauthorized parameter edit**, then apply it.
3. Wait for automatic polling or click **Run scan**.
4. Inspect the observed difference, measured recovery duration, effective revision and recorded timeline.
5. Open **Incidents**, enter a reason and acknowledge the incident.
6. Sign out, sign in as **ccb**, review the evidence and close it.
7. Sign in as **operator**, submit a new configuration in **Change control**.
8. Use **reviewer** to accept the exact proposal; then **ccb** to approve and deploy it.

See [the complete demonstration script](docs/demo-script.md) for failure scenarios and reporting outages.

## Tests and measured evidence

```bash
source .venv/bin/activate
python -m pytest
npm --prefix frontend run build

# Browser workflow starts its own isolated API and generated test credentials.
cd frontend
npx playwright install chromium
npm run test:e2e
cd ..

# Real timings: 20 samples at a 10-second polling interval; takes several minutes.
python scripts/measure_demo.py --samples 20 --poll-seconds 10
```

Browser tests require the active Python environment to contain the backend dependencies. They do not use your actual demo accounts or runtime. In an environment that already supplies Chromium, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to its executable.

Actual execution data is stored in [docs/acceptance-results.json](docs/acceptance-results.json). See [docs/verification.md](docs/verification.md) for the verified scope and remaining external gate. Timings describe this development machine and synthetic processes; they do not establish production or clinical performance.

## Project structure

```text
backend/
  main.py          FastAPI endpoints, sessions, role checks, evidence exports
  engine.py        Release, drift, recovery, approval and deployment workflow
  storage.py       SQLite repository, transactions and audit chain
  files.py         Configuration validation and atomic file operations
  locks.py         Reentrant thread + process filesystem locks
  phorge.py        Real/simulated Conduit reporting adapters and durable queue
agent/daemon.py    Independent monitoring supervisor
simulator/        Three synthetic monitor processes
frontend/         React + TypeScript console, bundled fonts and browser tests
configs/          Tracked demonstration fixtures and schema
tests/            Backend fault, permission, governance and independence tests
scripts/          Initialization and measured latency runner
scm/              Phorge/Herald and repository protection setup guides
docs/             Architecture, demonstration and actual verification evidence
runtime/          Generated private state — ignored by Git
```

## Design choices

- **Assigned release, not HEAD.** Committing a configuration does not deploy it.
- **Disk and effective state.** A successful write alone is not a successful recovery.
- **Independent monitoring.** The recommended launch keeps recovery running through a web API outage, while the local agent and storage remain available.
- **Independent reporting.** Conduit calls run outside the detector loop and outside database write transactions.
- **Explicit authority.** A maintenance window does not permit arbitrary edits.
- **Honest provenance.** Unobserved external editors are recorded as unknown.
- **Standard-library SQLite.** This build uses a versioned SQLite repository rather than the originally proposed ORM/Alembic stack; see the implementation notes for the tradeoff.

## Phorge setup

Follow [scm/phorge-setup.md](scm/phorge-setup.md). Export the environment variables before starting **both** the agent and API. `.env.example` is a reference file and is not automatically loaded. Keep tokens outside Git.

In real mode, deployment requires an accepted Differential patch that produces the **exact proposed artifact bytes** from the recorded base. The backend also checks the revision's current accepted diff before deploying. Instance permissions and method compatibility still require live validation.

## Boundaries

This is a single-host POSIX demonstration with three allowlisted nodes. It is not a remote-device fleet agent, a distributed transaction system, an immutable audit appliance, a guarantee of zero downtime, or evidence of regulatory compliance. A privileged host attacker can alter the code, key, database and files. The audit hash chain does not prevent that.

Recovery authority is scoped to a node/profile/generation and expires. The baseline fixtures and numeric validation are software demonstration rules, not clinical policy.
