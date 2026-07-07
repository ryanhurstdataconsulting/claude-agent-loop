---
name: raid-log-maintainer
description: Use when risks, assumptions, issues, or dependencies surface from standup notes, meeting transcripts, chat threads, or tickets and need to be captured in a structured, owned, and tracked RAID log rather than left as scattered notes. Triggers include "add this to the risk log," "what's blocking us," a program kickoff that needs a RAID log started, a weekly program sync that needs a delta summary, or an item that has gone quiet and needs a staleness check before the next status report.
---

# raid-log-maintainer

## Overview
Turns unstructured status notes, meeting transcripts, or ticket comments into a
maintained RAID log — Risks, Assumptions/Actions, Issues, and Dependencies/Decisions
— with an owner, a severity, and a status on every entry. Owns one job: keep the
program's single source of truth for "what could go wrong, what are we assuming,
what's already gone wrong, and what are we waiting on" current and triage-ready.

## When to use
- A program or project kickoff needs a RAID log started from scratch.
- Raw inputs (standup notes, a meeting transcript, a Slack/chat export, a batch of
  tickets) contain new risks, issues, or blockers that have not been logged yet.
- A recurring status report or sync is coming up and the log needs a fresh triage
  pass — stale items flagged, resolved items closed out, severities re-checked.
- An incident or escalation produces a new tracked item that needs to enter the log
  alongside existing risks and dependencies.
- Someone asks "what are our top risks right now" or "what are we blocked on."

## Workflow

1. **Classify each raw item into exactly one RAID category.** Use the standard
   test, in order — an item can drift between categories as more is learned, but
   should have exactly one primary category at any time:
   - **Risk** — something that *might* happen and would hurt the program if it did.
     Always phrase as "if X, then Y" so the trigger condition is explicit.
   - **Assumption** — something being treated as true without current proof. If it
     turns out false, it typically converts into a Risk or an Issue.
   - **Action** — a discrete task someone owes, often paired with an Assumption
     ("validate assumption X by doing Y") or a Risk (mitigation step).
   - **Issue** — something that has *already* happened and is actively impacting
     the program now. This is the "risk realized" bucket — a Risk that fires
     becomes an Issue, not a second entry.
   - **Dependency** — a hand-off or precondition owned by another team, vendor, or
     workstream that this program's timeline relies on. Decisions-pending-owner
     items belong here too if a common Decisions column is not tracked separately.
2. **Populate the standard fields per entry** — do not log an item without these:
   - `ID` (stable, e.g. `R-014`, `I-003`) so entries can be referenced elsewhere.
   - `Description` — one or two sentences, specific enough to act on without
     needing the source transcript.
   - `Category` (R/A/I/D), `Owner` (a named person or team, never "TBD" left
     unresolved past one cycle), `Severity`/`Impact` (High/Medium/Low, or a
     probability × impact score if the program already uses one).
   - `Status` (Open / Mitigating / Monitoring / Closed / Escalated).
   - `Date raised`, `Date last updated`, `Target resolution date` where known.
3. **Flag resolution gaps rather than silently filling them.** If an item has no
   owner, or its severity cannot be determined from the source material, mark it
   `Needs owner` / `Needs severity` and surface it in the diff summary — do not
   invent an owner or guess a severity to make the row look complete.
4. **Run a staleness pass every cycle.** An item with no status change past its
   team's defined SLA (commonly one to two reporting cycles) gets flagged
   `STALE` and surfaced explicitly — it either gets re-triaged, escalated, or
   closed; it does not silently roll forward unexamined.
5. **Produce a weekly (or per-cycle) diff summary**, not just the full log: new
   items added, items that changed severity or status, items closed, and items
   newly flagged stale or escalated. This diff is what feeds a status report —
   see the `status-report` skill for the next step in the pipeline.
6. **Watch for risk-to-issue conversion.** When a raw input describes something
   that already happened and matches the trigger condition of an existing open
   Risk, close that Risk as "realized" and open (or link) the corresponding
   Issue — do not carry both as separate open entries describing the same event.

## Checklist / quality gate
- [ ] Every new item classified into exactly one RAID category, with the
      "if X, then Y" phrasing applied to Risks.
- [ ] Every entry has an owner and a severity, or is explicitly flagged
      `Needs owner` / `Needs severity` rather than left blank or guessed.
- [ ] No duplicate entries — a realized Risk is closed and linked to its Issue,
      not left open alongside it.
- [ ] Stale items (no update within the SLA window) are flagged, not silently
      carried forward.
- [ ] A diff summary (added / changed / closed / stale) accompanies the full log
      update, ready to feed a status report.
- [ ] Prose in the log (descriptions, summary narrative) passes a grammar check
      before it ships to stakeholders.

## References
- The Digital Project Manager — [RAID Logs](https://thedigitalprojectmanager.com/project-management/raid-log/)
- Asana — [RAID Log](https://asana.com/resources/raid-log)
- Smartsheet — [What Is RAID in Project Management?](https://www.smartsheet.com/content/raid-project-management)
- ProjectManager.com — [What Is a RAID Log and Why Should I Use One?](https://www.projectmanager.com/blog/raid-log-use-one)

## Composition
Feeds `status-report` (team/program/exec altitudes all draw from the RAID diff).
Pairs with `map-dependencies` for the Dependency category specifically — when a
dependency needs a full cross-team critical-path view rather than a single log
row, hand off to that skill. Shares its "classify an unstructured event into a
structured, owned, tracked item" pattern with incident-postmortem and
bug-escalation workflows — a realized Risk that triggers an incident should link
to that postmortem once it exists.
