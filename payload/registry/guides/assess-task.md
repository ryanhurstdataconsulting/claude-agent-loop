# Guide — assess-task

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
The loop's assessment channel was a subjective self-score, recorded on 74 of
1,596 subagent tasks — 4.6% — and written by the same agent that did the work.
Meanwhile the metrics store already carried a git branch on 100% of tasks and
test results on 64%, and nothing read either. This tool inverts that: the
verdict comes from recorded numbers, and no model touches it.

## When to deploy (triggers)
- After every part of a work order has been logged.
- Before running `heuristics_eval.py`, so LEARN sees objective evidence rather
  than a self-report.

## Interface (how to invoke)
```
assess_task.py <plan-id> [--repo DIR] [--propose-row] [--followup-hours N]
```
Fills `part.evidence` and `part.verdict` on the work order and prints a line per
part. `--repo` enables the git channel (commits, reverts, follow-up fixes);
without it only the metrics channel is read.

The verdict is deliberately conservative:

| Verdict | Means |
|---|---|
| `dirty` | a failed test, a revert, a follow-up fix, or a tool-error rate above 0.25 |
| `clean` | at least one real signal, and none of the above |
| `unknown` | no objective signal at all — **never** treated as success |

A part whose own log reported failure can never assess `clean`, whatever the
surrounding evidence says.

## Composition (pairs with / hands off to)
- Reads the work order that `plan-task` built and `make-brief` dispatched.
- Feeds LEARN. Because every part carries a role and skill list written by a
  tool, evidence is precise rather than session-backfilled, so `H1`/`H7`
  improve-now findings stop being downgraded for lack of precise rows.
- `--propose-row` prints a `.claude/SUBAGENTS.md` row for each non-clean part.
  It **prints only.** The local-improvement path never writes inside a client
  project, so client-tinged content can never reach `loop-contribute`.

## Build & maintenance notes
Lives at `payload/tools/assess_task.py`. Tests:
`payload/tools/tests/test_assess_task.py` (27 cases), including the full verdict
truth table, a real metrics shard on disk, a real temporary git repository with
a genuine revert and fix commit, and a filesystem snapshot around
`--propose-row` proving it writes nothing. `ERROR_RATE_MAX` is pinned to the
0.25 ceiling `H1` already uses — change both together or the two disagree.
