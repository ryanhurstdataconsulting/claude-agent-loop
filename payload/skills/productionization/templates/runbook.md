# Runbook — <project name>

> Written by the productionization skill's Operations phase (`sre`
> dispatch). Keep this current — a stale runbook is worse than none,
> because it's trusted during an incident.

## Rollout

- How a new version reaches production (steps, approvals, verification).

## Rollback

- The exact command/action to revert to the last known-good version.
- Who is authorized to execute it without further approval during an
  active incident.

## Top alerts

| Alert | Meaning | First action | Escalation |
| --- | --- | --- | --- |
| | | | |

## Logs and traces

- Where structured logs land (e.g. CloudWatch Logs group name).
- How to correlate a request across services (trace/correlation ID
  convention).

## Safe restart

- The command/action to restart the service without data loss or
  duplicate side effects.

## Backup and restore

- What's backed up, how often, and the exact restore procedure.

## Dependency outage

- What happens to this service if each state dependency (database,
  queue, third-party API) becomes unavailable, and what degrades
  gracefully versus fails hard.

## Incident communication

- Who gets notified, how, and what the first message should say.
