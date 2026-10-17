# Demonstration script

Start `bash run.sh`, read the private generated credentials and open http://127.0.0.1:8000. Use a clean private runtime for a fresh presentation; preserve an existing runtime if you need its evidence. Never delete it merely to hide a failed result.

## A. Normal state and version assignment

Sign in as operator. Show nodes 01/02 on v1.2 and node 03 on v1.1. Open Baselines and explain that these are synthetic bootstrap fixtures with distinct profiles and exact Git commit IDs.

Expected: three online nodes, assigned revisions visible, no current configuration deviation.

## B. Unauthorized parameter edit

Open Demonstration controls, choose node 01 and Unauthorized parameter edit, then Apply scenario. Wait for polling or request a scan. Open the incident.

Show the arbitrary synthetic change from 120 to 180, the saved difference, actor provenance, recovery steps, effective digest and measured recovery duration. The value pair is an example, not a clinical recommendation.

Expected: verified recovery; incident remains open for review. Reporting is marked simulated unless a real instance has been configured.

## C. Governance closure

As operator, enter an acknowledgement reason. Sign out. As CCB, inspect the recorded evidence, enter a resolution and close the incident.

Expected: closure requires verified recovery plus acknowledgement; recovery alone does not close the task.

## D. Reporting outage

As operator, open Settings and Simulate reporting outage. Reset the demo node to clear the recent-fault window if appropriate, inject drift and observe verified local recovery. Reporting remains pending. Restore reporting and synchronize; inspect delivered simulated task status, or the real task when configured.

Expected: local recovery is independent of reporting availability. This scenario deliberately blocks reporting at the adapter boundary; it is not proof of a live Phorge server outage.

## E. Failed recovery

Reset the node first, then inject Simulator reload failure. Scan and inspect both attempts, failure reason and intervention-required status. Clear injected fault flags. Open the unresolved incident, provide a reason and retry recovery.

Expected: a successful file write is insufficient; effective-state verification is mandatory. Repeated scans do not retry the same latched failure forever.

## F. Invalid trust and offline state

Reset between independent examples. For cache tampering or expired authorization, inject that fault first and then a parameter edit. Scan.

Expected: automatic replacement is blocked. Reset is an explicit demo repair that restores a trusted current assignment and records an audit event.

For Node offline, apply the scenario and show unknown current configuration state. Bring it online afterwards. The UI must not claim that an offline node is currently compliant.

## G. Legitimate change

As operator, submit a unique release version for node 02. As a different reviewer, accept its exact digest with a reason. As a different CCB account, approve and deploy it.

Expected: the assigned release and generation advance only after verification. The new approved configuration is not rolled back as unauthorized drift. A new Git HEAD by itself does not change other node assignments.

Real mode additionally requires an accepted Differential patch whose resulting bytes match the proposal. See the Phorge setup guide.

## H. API outage and evidence

Run agent and API in separate terminals as described in README. Stop the API while leaving the agent running. Modify the allowlisted synthetic `runtime/nodes/ICU-Node-01/live.json` file directly. After the polling interval, inspect restoration on disk; restart the API and inspect the persistent incident. An unobserved direct editor is recorded as unknown.

Export JSON and CSV from Audit trail. Show incident IDs, generations, digests, decisions and operations. Keep successful and failed outcomes visible.
