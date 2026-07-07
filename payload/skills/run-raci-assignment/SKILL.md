---
name: run-raci-assignment
description: Use when a new program or initiative spans multiple contributing teams and needs role clarity before work starts — populating a RACI matrix (Responsible/Accountable/Consulted/Informed) from a task or workstream list. Triggers include "who owns this," a kickoff with no assigned Accountable owner per workstream, a task list with more than one team touching it, a RACI review before a launch, or a retro that surfaced "nobody knew who was supposed to decide this."
---

# run-raci-assignment

## Overview
Populates a RACI matrix — Responsible, Accountable, Consulted, Informed — from a
task or workstream list so that every piece of work has exactly one decision-maker
and a documented set of contributors before execution starts. Owns one job: turn
implicit "someone will figure it out" ownership into an explicit, reviewable
matrix.

## When to use
- A new program or cross-team initiative is starting and role clarity has not
  been established yet.
- A task list, epic breakdown, or workstream list exists but ownership is unclear
  or assumed rather than documented.
- A retro or postmortem surfaced a decision that stalled because no one knew who
  was supposed to make the call.
- A launch, migration, or release needs sign-off clarity — who must approve,
  who must be consulted, who just needs to know.
- An existing RACI has gone stale (new teams joined, ownership shifted) and needs
  a refresh pass.

## Workflow

1. **Start from a concrete task or workstream list**, not from an abstract org
   chart. RACI is assigned per deliverable or decision, not per person's general
   job description — "own the database migration" is assignable, "own backend"
   is not granular enough to populate a row.
2. **Populate all four roles per row, understanding the asymmetry between them:**
   - **Responsible (R)** — does the work. Can be more than one person or team.
   - **Accountable (A)** — owns the outcome and has final sign-off authority.
     **Exactly one** per task, never zero and never more than one. This is the
     single most common failure mode in a real RACI and the one to actively
     police (see gate step below).
   - **Consulted (C)** — two-way input before the work is done (subject-matter
     experts, dependent teams). Keep this list tight; an inflated Consulted list
     is a sign the task needs to be split, not that more people need pinging.
   - **Informed (I)** — one-way notification after a decision or delivery.
     Broader list is fine here since the cost of over-informing is low.
3. **Flag zero-Accountable and multi-Accountable rows as resolution items,
   never auto-resolve them.** If the source material does not make the
   Accountable owner clear, do not guess based on seniority or team size —
   surface the row explicitly (`Accountable: UNRESOLVED`) and route it back to
   the requester or the kickoff meeting for a human decision. Silently picking
   an owner is the single worst failure mode this skill can produce, because it
   looks resolved when it is not.
4. **Cross-check R against A.** A person or team can be both Responsible and
   Accountable for the same row (common on a small team), but if the same name
   appears as Accountable on a row where a *different* team is doing all the
   work, flag it for a sanity check — it may be correct (a lead owning outcomes
   their team executes) or it may be a stale assignment.
5. **Watch for Consulted-list bloat.** More than roughly four to five Consulted
   parties on a single row is a signal either that the task is too coarse-grained
   (split it) or that "Consulted" is being used as a substitute for "Informed"
   (demote the ones who do not actually need to weigh in before the decision).
6. **Render as a matrix (rows = tasks, columns = R/A/C/I) for review**, and
   call out the unresolved rows in a separate summary list at the top so they
   are not buried in an otherwise-complete-looking table.
7. **Route back for confirmation.** A populated matrix is a draft until every
   named owner has acknowledged their row, especially every Accountable
   assignment — this skill drafts the matrix; a human confirms it.

## Checklist / quality gate
- [ ] Every row has an entry in all four columns, or an explicit `UNRESOLVED`
      marker rather than a blank cell.
- [ ] Every row has exactly one Accountable owner — zero or multiple is flagged,
      never silently resolved by the agent.
- [ ] Consulted lists are checked for bloat (roughly more than four or five
      names) and flagged if a row likely needs splitting.
- [ ] Rows are granular enough to be assignable (a deliverable or decision, not
      a whole function or team).
- [ ] Unresolved rows are summarized at the top of the output, not buried in the
      full matrix.
- [ ] The matrix is marked as a draft pending named-owner confirmation before it
      is treated as final.

## References
- RACI is standard program-management practice (Responsible/Accountable/
  Consulted/Informed); no single canonical primary source is authoritative,
  but the framework is widely documented across project-management literature
  and tooling (e.g., Asana, Smartsheet, and PMI-aligned program-management
  guides cover it as a standard artifact).

## Composition
Runs naturally after `map-dependencies` at kickoff — once the cross-team
dependency graph exists, assigning an Accountable owner per node closes the
"who decides" gap the graph alone leaves open. Feeds `raid-log-maintainer`
indirectly: an `UNRESOLVED` Accountable row is itself a Risk or Issue worth
logging until it is resolved. Feeds `status-report` at the program altitude
when ownership gaps need to be called out to leadership.
