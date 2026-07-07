---
name: backup-recovery-runbook-authoring
description: Use when a database needs a documented, tested backup-and-restore or disaster-recovery procedure — a new database with no runbook, an audit finding that backups have never been restore-tested, or a postmortem action item to write one down. Covers RPO/RTO requirement gathering, backup-method selection (logical dump, physical base backup, WAL archiving, managed snapshot), a restore-drill script, and a post-restore verification checklist. Triggers on "write a backup runbook," "what's our RPO/RTO," "we've never tested a restore," or "document the disaster-recovery procedure for this database."
---

# backup-recovery-runbook-authoring

## Overview
Turns backup and disaster-recovery requirements into a documented, tested
runbook that someone unfamiliar with the system could execute under
pressure. The one job it owns: a backup that has never been restored is
unverified, so this skill does not consider a runbook done until a restore
drill has actually run.

## When to use
- A database has backups configured but no written restore procedure.
- An audit or postmortem surfaces that a backup has never been
  restore-tested.
- A new database or environment needs RPO/RTO targets defined before a
  backup strategy is chosen.
- An existing runbook is stale (points at a decommissioned host, references
  a tool no longer in use, or was written by someone no longer on the
  team).

## Workflow
1. **Gather RPO and RTO requirements before choosing a method.**
   - **RPO (Recovery Point Objective)** — the maximum acceptable data loss
     window, measured in time. A five-minute RPO rules out a nightly
     logical dump as the only backup method.
   - **RTO (Recovery Time Objective)** — the maximum acceptable downtime
     during a restore. A one-hour RTO on a multi-terabyte database rules
     out a slow logical restore as the primary path.
   - Get both numbers from whoever owns the service-level commitment, not
     from a default assumption — they drive every choice below.
2. **Select the backup method(s) against those targets:**
   - **Logical dump** (`pg_dump`/`pg_dumpall`) — portable across versions
     and engines, good for smaller databases or selective restores, but
     slow to restore at scale and only as fresh as the last dump.
   - **Physical base backup** (`pg_basebackup`) — fast full-instance
     restore, but an all-or-nothing snapshot in time by itself.
   - **Continuous WAL archiving + point-in-time recovery** — pairs with a
     physical base backup to restore to any moment within the retention
     window; the correct choice when RPO is near-zero.
   - **Managed snapshot** (a cloud provider's native database snapshot) —
     simplest to operate where the infrastructure supports it, but confirm
     its actual RPO/RTO characteristics rather than assuming "managed"
     means "solved."
   - Most production systems combine a periodic base backup with
     continuous WAL archiving; state the retention window for each
     explicitly (how many days/weeks of WAL are kept).
3. **Write the runbook so someone unfamiliar with the system can execute
   it.** Assume the primary is down and the person on call has never run
   this restore before:
   - Exact commands, in order, with the expected duration for each step.
   - Target host and where to find current connection details — reference
     a secrets manager or vault by name, never an inline credential.
   - The decision point for point-in-time recovery: how to pick the
     recovery target and where the WAL archive lives.
   - What "done" looks like at each step, so a stalled restore is obvious
     rather than silently hung.
4. **Write and run a restore drill**, not just the document. Automate a
   periodic restore into an isolated environment — a backup that has never
   been restored is not a backup, it is an unverified file. Log the actual
   duration achieved against the RTO target.
5. **Define the post-restore verification checklist** and exercise it
   during the drill:
   - Row counts on key tables against a known baseline.
   - A referential-integrity spot check (foreign keys resolve, no orphaned
     rows introduced by a partial restore).
   - An application-level smoke test against the restored instance.
   - Replication re-established, if the restored instance needs to rejoin
     a cluster.
6. **Version the runbook alongside infrastructure-as-code**, in source
   control, so it survives the person who wrote it moving on. Re-run the
   drill on a schedule (quarterly is a common baseline) and update the
   runbook whenever the backup method, host, or tooling changes.

## Checklist / quality gate
- [ ] RPO and RTO stated explicitly, and the chosen backup method(s)
      actually meet them.
- [ ] Runbook is executable by someone unfamiliar with the system — no
      step depends on tribal knowledge not written down.
- [ ] Credentials referenced by pointer to a secrets manager, never
      inlined in the document.
- [ ] A restore drill has actually run at least once, with its duration
      and output logged.
- [ ] Post-restore verification steps are defined and were exercised
      during the drill, not just described.
- [ ] The runbook is versioned in source control, not a standalone
      document no one owns.

## References
- [PostgreSQL — Backup and Restore documentation](https://www.postgresql.org/docs/current/backup.html)
- [PostgreSQL — Continuous archiving and point-in-time recovery](https://www.postgresql.org/docs/current/continuous-archiving.html)
- [KORE1 — Database Administrator skills and responsibilities](https://www.kore1.com/database-administrator-salary-guide/) (secondary, market-trend source)

## Composition
Consumes size and growth figures from `read-only-diagnostic-query-pack` to
ground the RTO estimate in actual data volume. Complements
`postmortem-generator` when a real restore was needed during an incident —
the drill results and the incident timeline should reconcile. Hands off to
`disaster-recovery-plan-authoring` when the scope extends beyond a single
database to the full application stack.
