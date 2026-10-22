# Integrated Live ICU Monitoring demonstration

**Preferred interface:** Sign in to the existing AEGIS ICU dashboard at http://127.0.0.1:8000 as Operator, then click **Live ICU Monitoring** in the existing sidebar. This section contains exactly two side-by-side panels: **Server** (automatic drift detection, recovery status, incident evidence) and **Device** (editable actual deployed JSON file and Save). No separate browser pages are needed.

1. Start `bash run.sh` after `git pull`. Log in as Operator.
2. Open **Live ICU Monitoring**, select ICU-Node-01.
3. In **Device**, edit `"demo_heart_rate_upper_bpm": 120` to `160` and click **Save live.json**.
4. Do not click Run scan. Wait for the independent agent's polling cycle (10 seconds by default).
5. Observe the **Server** panel's latest incident, recovery timeline and effective-state verification. Recovery may be faster than the two-second UI refresh, so the persistent incident is stronger evidence than the brief drift indicator.
6. In **Device**, click **Reload from disk** to show the restored 120 BPM JSON.

The earlier standalone /demo/server and /demo/device pages remain as optional legacy demonstration views; the new integrated sidebar section is the recommended workflow.

---

# Two-window manual JSON drift demonstration

This is an **additive** demonstration of the existing independent monitoring and recovery engine. It is a **synthetic academic ICU monitor**, not a medical device.

## Start

Run `bash run.sh`, then sign in as **operator** at http://127.0.0.1:8000. Use two browser windows side by side:

- **Server:** http://127.0.0.1:8000/demo/server
- **Device:** http://127.0.0.1:8000/demo/device

The pages use the existing signed-in session. Choose **ICU-Node-01** in both windows.

## Demonstrate real unauthorized file editing

1. On **Device**, note the full path shown for `runtime/nodes/ICU-Node-01/live.json`. This is the *actual deployed JSON file*, not a UI-only mockup.
2. Change an existing numeric value in the JSON editor and click **Save live.json (unauthorized edit)**. Alternatively, open the displayed path directly in VS Code, edit the JSON and press Ctrl+S. Do not edit `configs/` or the Git release artifact: those are not the deployed file.
3. Do **not** press Run scan. The existing independent agent automatically checks the live file every ten seconds by default.
4. Observe the **Server** window. The disk may briefly show drift, followed by restored integrity and an incident with `recovered_verified`. Because recovery can be fast, the intermediate drift indicator may not appear between the two-second UI refreshes; the persistent incident is the evidence.
5. On **Device**, click **Reload file from disk** (or wait for automatic refresh when the editor has no unsaved changes). The approved JSON bytes are back. Verify that the server's effective digest matches its approved release digest.
6. Repeat. Use the existing Incidents and Audit pages for the full incident record and role-based closure.

**Important:** The approved JSON uses its actual existing schema; do not assume a key named `heart_rate_threshold`. The editor exposes the genuine file content. Changing a valid existing threshold is sufficient.

## What is and is not proven

- Proven in the local demo when successful: direct unauthorized filesystem changes can be detected and reversed to a pinned approved baseline, with effective simulator-state verification and persistent evidence.
- Not proven: monitoring or control of actual bedside ICU hardware, clinical suitability or Phorge's inability to integrate with external monitoring systems.
- The Device save API is available only in demo mode and only to the operator role. It is an intentionally insecure **fault-injection surface** for the local synthetic runtime; never expose this demo service publicly.

## Regression check

`python -m pytest tests/test_two_window_demo.py`

The preexisting tests should also be run with `python -m pytest` and `npm --prefix frontend run build`. The new views are served as a standalone HTML page and do not replace the existing React interface.
