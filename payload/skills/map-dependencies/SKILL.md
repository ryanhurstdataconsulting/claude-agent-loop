---
name: map-dependencies
description: Use when a multi-team initiative needs its cross-team hand-offs, blockers, and critical path made visible — building a dependency graph or table from linked tickets/epics (blocks/blocked-by relationships) or from elicited team commitments. Triggers include "what's the critical path," "who's blocked on whom," a program with more than two contributing teams and no visible sequencing, a request to check for circular dependencies, or a Jira/Linear epic tree that needs to become a readable dependency view before planning.
---

# map-dependencies

## Overview
Builds a cross-team dependency graph or table for a multi-team initiative, either
by crawling linked-ticket relationships (blocks/blocked-by) in a tracker or by
eliciting each team's deliverables and hand-off points directly. Surfaces the
critical path, single points of failure, and any dependency cycles before they
become schedule surprises.

## When to use
- A multi-team initiative kicks off and no one has a visible picture of who is
  waiting on whom.
- A tracker (Jira, Linear, GitHub Projects, etc.) has an epic tree with
  blocks/blocked-by links that need to become a readable graph or table.
- A sprint or program-planning session needs a critical-path view before
  committing to a sequence or a target date.
- Someone suspects a circular dependency (one team is blocked on a second team
  that is, in turn, blocked on the first) and needs it confirmed or ruled out.
- A dependency risk needs to graduate from a single RAID-log row into a full
  cross-team view — see the composition note below.

## Workflow

1. **Establish the data source first.** Two paths, pick based on what exists:
   - **Ticket-derived** — if the tracker has explicit `blocks` / `blocked by` /
     `relates to` links on epics or tickets, crawl those links via the tracker's
     API or export. This is the more reliable path; it is time to build directly
     from committed data, not conversation.
   - **Elicited** — if links are not modeled in the tracker, elicit each
     contributing team's deliverables and their hand-off points directly (what
     do they need from another team before they can start, and what do they
     hand off when done). Mark elicited edges as `unconfirmed` until a receiving
     team acknowledges them — do not present elicited dependencies with the same
     confidence as ticket-derived ones.
2. **Normalize into a directed graph**: node = deliverable/ticket/team milestone,
   edge = "depends on" (A → B means A cannot start/finish until B is done). Keep
   node metadata minimal but real: owning team, target date if known, current
   status.
3. **Detect cycles before anything else.** A cycle (A depends on B depends on A)
   is a logical impossibility in a real schedule — it means the relationship was
   mis-modeled, or there is a hidden partial-delivery agreement not captured in
   the ticket links. Flag every cycle explicitly and by name; do not silently
   break the cycle or pick a direction to resolve it — that is a human call.
4. **Compute the critical path.** The critical path is the longest chain of
   dependent work by duration (not by ticket count) from the current date to the
   initiative's target completion. Identify it explicitly, and separately flag
   any node on it that also has no assigned owner or no estimate — those are the
   nodes most likely to blow the date silently.
5. **Surface single points of failure**: any node with an unusually high
   fan-in (many things depend on it) or that sits on the critical path with no
   parallel path around it. These are the items worth extra risk attention even
   if their own individual severity looks moderate.
6. **Render for the audience.** A table (columns: item, owner, depends-on,
   depended-on-by, status, on-critical-path Y/N) works for a working session; a
   rendered graph (e.g., via a diagram-as-code tool) works better for a
   leadership readout where the shape of the bottleneck matters more than the
   detail. Do not default to a dense graph image for a working session where
   people need to scan and edit rows.
7. **Re-run on a cadence, not once.** Dependency graphs decay fast — a graph
   built at kickoff and never refreshed is actively misleading by week three.
   Tie the refresh cadence to the same reporting cycle as the status report.

## Checklist / quality gate
- [ ] Data source (ticket-derived vs. elicited) is stated, and elicited edges are
      marked `unconfirmed` until acknowledged by the receiving team.
- [ ] Cycles are explicitly detected and flagged by name, not silently resolved.
- [ ] The critical path is identified by duration, not just by longest ticket
      chain, with unowned/unestimated nodes on it called out.
- [ ] Single points of failure (high fan-in nodes, no-parallel-path nodes on the
      critical path) are surfaced separately from the general graph.
- [ ] Output format (table vs. rendered graph) matches the audience — a working
      session gets a scannable table, a leadership readout gets a rendered shape.
- [ ] The graph carries a "last refreshed" date so staleness is visible at a
      glance.

## References
- Mario Gerard — [Core Technical Program Management Skills](https://www.mariogerard.com/core-technical-program-manager-skills/)
- Smartsheet — [RAID in Project Management](https://www.smartsheet.com/content/raid-project-management) (dependency-tracking practice)

## Composition
Consumes tracker data the same way `raid-log-maintainer` consumes status notes —
when a Dependency row in a RAID log needs to become a full cross-team view rather
than a single line, promote it here. Feeds `status-report` at the program altitude
(critical-path and blocker sections draw directly from this skill's output).
Pairs with `run-raci-assignment` at initiative kickoff — a dependency graph is
more useful once every node also has a confirmed Accountable owner.
