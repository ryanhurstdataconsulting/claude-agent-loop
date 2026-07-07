# Heuristics — rules over recorded task/score metrics

Heuristic scoring over recorded metrics. NOT model training. Each rule below
watches a window of recent task and score records (`~/.claude/metrics/`,
P2–P3) and fires one of three actions when its threshold is crossed.
`heuristics_eval.py` (P6) is the live engine that reads these rules: it computes
each rule's window over the metrics store and reports which fire, so the loop's
LEARN step can act on the highest-priority firing.

<!-- Rule grammar: one `## H<id> — <slug>` block per rule; H<id> unique.
     Required fields, in order: WHEN, WINDOW, THRESHOLD, THEN, CONFIDENCE,
     LAST-REVIEWED. THEN must be one of: improve-now, theme-note, no-action.
     Lint after any edit: python3 ~/.claude/tools/lint_heuristics.py (P6). -->

## H1 — resource-error-spike
- WHEN: the mean tool-error rate across tasks that deployed a given resource crosses the threshold
- WINDOW: last 10 tasks that deployed the resource
- THRESHOLD: mean error_rate > 0.25
- THEN: improve-now
- CONFIDENCE: seed
- LAST-REVIEWED: 2026-07-06

## H2 — interrupt-pressure
- WHEN: the user interrupts an unusually large share of recent tasks
- WINDOW: last 10 tasks, any resource
- THRESHOLD: interrupted / total > 0.30
- THEN: theme-note
- CONFIDENCE: seed
- LAST-REVIEWED: 2026-07-06

## H3 — test-fail-streak
- WHEN: consecutive tasks report at least one failing test
- WINDOW: last 5 tasks
- THRESHOLD: 3 or more consecutive tasks with tests.failed > 0
- THEN: theme-note
- CONFIDENCE: seed
- LAST-REVIEWED: 2026-07-06

## H4 — bare-match-streak
- WHEN: the ANNOUNCE line reads "proceeding bare" for tasks of a similar shape
- WINDOW: current session (falls back to recent project records when no session context is supplied)
- THRESHOLD: 3 or more similarly shaped "proceeding bare" announcements
- THEN: improve-now (files a `registry/candidates/` stub; the loop never auto-creates the resource itself)
- CONFIDENCE: seed
- LAST-REVIEWED: 2026-07-07

## H6 — cache-efficiency-floor
- WHEN: prompt-cache efficiency across recent tasks drops below a healthy floor
- WINDOW: last 10 tasks
- THRESHOLD: mean cache_efficiency < 0.50
- THEN: theme-note
- CONFIDENCE: seed
- LAST-REVIEWED: 2026-07-06

## H7 — rework-signal
- WHEN: the user's self-scored `rework` scale (see SCALES.md) comes back major
- WINDOW: last 10 scored tasks
- THRESHOLD: rework = major on 2 or more tasks
- THEN: improve-now
- CONFIDENCE: seed
- LAST-REVIEWED: 2026-07-06

## H8 — positive-streak
- WHEN: a resource sustains a long run of clean outcomes with no rework
- WINDOW: last 10 tasks that deployed the resource
- THRESHOLD: 8 or more consecutive tasks with outcome >= good and rework = none
- THEN: no-action (recorded as positive signal; the resource's own alert thresholds are raised as a side effect, not as a separate THEN value)
- CONFIDENCE: seed
- LAST-REVIEWED: 2026-07-06

## Planned (not yet computable)

These rules are fully specified but their metric is not in the store yet, so the
engine parses them as PLANNED and never evaluates them. Their ids stay reserved.

## H5 — route-cost-outlier
- WHEN: a task classified as mechanical work is routed to the Opus model tier
- WINDOW: last 10 tasks
- THRESHOLD: 2 or more mechanical tasks routed to Opus
- THEN: theme-note
- CONFIDENCE: seed
- LAST-REVIEWED: 2026-07-07
- NOTE: needs a task-shape/route-tier field at ANNOUNCE time — not in the metrics schema yet
