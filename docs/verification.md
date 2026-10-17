# Verification report

This report records executed local checks. It does not claim that a live Phorge installation or GitHub-hosted CI has already passed.

## Executed checks

| Check | Observed result |
|---|---|
| Backend fault/workflow suite | 28 tests passed; no failures or errors |
| TypeScript and production build | Passed |
| Real browser journey | Passed: operator recovery, acknowledgement, CCB closure, proposal, reviewer acceptance, CCB deployment |
| Responsive browser checks | Passed at 320, 768 and 1440 pixels; no horizontal page overflow |
| JavaScript page errors in journey | 0 |
| Independent agent with API stopped | Passed with a separate agent and three monitor subprocesses |
| Audit corruption check | Modified event detected |
| Reporting outage and restart | Pending reports retained, then delivered in explicitly simulated mode |
| Source / measurement correlation | Recorded engine SHA-256 matches delivered engine source |

The browser run also caught and led to fixes for sign-out screen state and navigation accessibility naming. Internal browser screenshots were inspected for desktop and mobile layout; they are not checked into this repository.

## Measured polling run

Environment: `Linux-6.18.55-x86_64-with-glibc2.39`; Python 3.12.14. Three independent synthetic monitor processes. Configured polling interval: 10 seconds. Recorded at 2026-10-17T04:26:47.746332+00:00.

| Measure | Actual result |
|---|---|
| Drift injections | 20 |
| Verified recoveries | 20/20 |
| Maximum detection delay | 10.0111 seconds |
| Mean detection delay | 9.9973 seconds |
| Maximum recovery duration after detection | 0.1735 seconds |

See `acceptance-results.json` for all individual samples. Each injection used the same defined synthetic fault and an explicitly audited reset between samples. The result establishes behavior for that fixture and machine, not all configurations or hardware.

## Backend risk coverage

- Node-specific release assignment; repository HEAD cannot implicitly deploy.
- Field drift, formatting-only drift, malformed JSON and missing files.
- Unknown external-editor provenance.
- Cached artifact/signature tampering and expired authorization.
- Write failures, reload failures, bounded retry and failure latching.
- Symlink-target refusal and offline-state handling.
- Repeated-drift circuit breaker.
- Stale incident, stale digest and stale generation rejection.
- Approved deployment without false drift; failed deployment outcome reporting.
- Interrupted-operation reconciliation and audit-chain checks.
- Session authentication, CSRF and backend role enforcement.
- Acknowledgement/closure requirements and three-account approval workflow.
- Uncertain external creation held for reconciliation rather than blindly repeated.
- Concurrent operator acknowledgement preserved through recovery.

## Remaining external gate

No Phorge URL, token, project or CCB identity was supplied. Real Conduit creation/search, Differential response compatibility, installed Herald rules, host-side repository protection and an actual Phorge network outage have **not** been validated. See `../scm/phorge-setup.md` for the exact procedure. The included simulated adapter and injected transport tests do not replace live integration evidence.

The unit-test environment emitted one upstream Starlette/httpx deprecation warning. It did not fail the suite. The package versions used are pinned in `requirements.txt`; a future transport dependency update should repeat the suite.

## Reproduce

Follow README setup, then run `python -m pytest`, `npm --prefix frontend run build`, the frontend browser test, and `python scripts/measure_demo.py --samples 20 --poll-seconds 10`. The last command writes a new measured result for your machine.
