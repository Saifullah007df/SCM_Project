# Phorge integration setup and live validation gate

No live instance credentials were supplied during implementation. The real adapter is implemented, but live Maniphest, Differential, Herald and repository enforcement remain deployment checks.

Use an instance you administer or are authorized to integrate. Follow the official installation documentation if you need a new instance:

- https://we.phorge.it/book/phorge/article/installation_guide/
- https://we.phorge.it/book/phorge/article/conduit/
- https://projects.clusterlabs.org/book/phorge/article/conduit_edit/
- https://we.phorge.it/book/phorge/article/diffusion_hosting/

## Configuration

Generate a limited account API token in the instance. Configure the dedicated demonstration project and CCB owner. Export these values in both the agent and API environments before starting them:

```bash
export PHORGE_URL='https://your-phorge-host.example'
export PHORGE_TOKEN='your-private-token'
export PHORGE_PROJECT_PHID='PHID-PROJ-your-project'
export PHORGE_OWNER_PHID='PHID-USER-your-authorized-ccb-owner'
export PHORGE_PRIORITY='high'
```

Do not commit the token or put it in a URL. HTTPS is required. The `.env.example` file is not auto-loaded. To return to simulated mode, unset `PHORGE_URL` and `PHORGE_TOKEN`, then restart both components. Use a fresh demonstration runtime when switching modes; already-delivered simulated jobs are historical simulated records and are not silently resent as real incidents.

The token needs permission to search/create relevant Maniphest tasks and read the intended Differential revisions/diffs. Confirm the instance's installed Conduit schemas before enabling the demonstration. Priority/project/owner values are instance configuration, not guaranteed universal constants.

## Real incident validation

1. Configure the project/owner and verify token visibility in the instance.
2. Inject one synthetic drift and let recovery finish.
3. Synchronize reporting and open the returned real T-number link.
4. Verify the exact `AEGIS-INC-<uuid>` marker, saved difference, outcome and node identity.
5. Inspect the task owner/project and the Herald transcript configured below.
6. Block/recover instance connectivity and measure queued delivery. Do not describe the built-in simulated outage switch as a live network outage test.

If creation times out, the queue marks the outcome uncertain. It searches for the exact marker before retrying. If no definitive task can be found, inspect the instance manually; do not blindly reset uncertainty. A manually reconciled task retaining the exact marker can be discovered on the next sync.

## Differential content validation

The baseline manager creates a **local runtime Git repository**, separate from the application's source repository. The approved configuration path is `profiles/demo-adult.json` or `profiles/demo-legacy.json` in that repository. Import/host/observe this baseline repository in Phorge as appropriate, and ensure the relevant base commit is available to reviewers.

Create a Differential revision of the exact proposed configuration change against the recorded base. Preserve the canonical JSON byte formatting produced by the application. Supply the numerical D revision ID when submitting the application proposal. A reviewer uses Verify Differential content after the external review is accepted.

The adapter reads `differential.revision.search`, `differential.diff.search` and `differential.getrawdiff`. It applies the raw patch to the recorded base in an isolated directory and checks the exact proposal digest. It then stores the verified diff PHID. Real-mode deployment checks that the current revision remains accepted and references that diff. Confirm these methods and response fields against the installed instance; no live compatibility claim is made yet.

## Herald rule specification

Configure through the actual instance UI using supported conditions/actions. A repository JSON file alone does not install a Herald rule.

Suggested task rule:

- Applies to Maniphest tasks.
- Matches the dedicated AEGIS demonstration project and/or task title prefix `[DRIFT]`, using conditions available on your instance.
- Routes to the explicitly configured CCB demonstration group or owner and adds the required project/tag using supported actions.
- Any email/notification recipients must be explicitly configured and authorized for the demonstration.

The bridge itself can set the owner/project. If those fields are set by the bridge, describe them as bridge routing. To prove Herald behavior, retain the rule configuration and actual Herald transcript separately.

## Repository protection

An observed repository is not automatically protected by Phorge's hosted repository controls. Apply restrictions at the actual host. For a hosted baseline repository, configure supported push policies/Herald rules; verify rejection of unauthorized direct pushes and acceptance of the intended reviewed workflow.

Git in the local runtime is not a protected remote service. It demonstrates immutable commit-based assignment, not remote branch protection. External protection is a separate live validation gate.

## Completion evidence to add later

Record instance/version, method compatibility, real task/revision links, exact diff validation, routing transcript, rejected unauthorized push and measured outage/reconnection results. Add evidence only after execution. Do not replace the checked-in synthetic execution report with hypothetical results.
