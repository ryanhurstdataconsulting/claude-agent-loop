# Guide — consensus-vote

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
Agent-loop-v2 design spec, Phase 6 — a queryable vote history for risky,
already-gated actions (`git push`, publish/release, an AWS mutation). This
is explicitly an audit-log addition: it does not relax the existing
never-auto-push norm or the AWS consent requirement, and it enforces
nothing on its own — no hook in this codebase currently blocks anything on
a vote tally. It gives a human or an orchestrating agent evidence to weigh
before deciding, not a technical gate.

## When to deploy (triggers)
Before a genuinely risky, hard-to-reverse action where more than one
independent opinion is worth having on record — e.g. dispatching 2-3
independent review passes before a force-push, a publish/release command,
or an AWS mutation, then recording each reviewer's vote and checking the
tally before proceeding.

## Interface (how to invoke)
```
python3 ~/.claude/tools/consensus_vote.py --record --task-id <id> \
    --action-type {git-push,publish-release,aws-mutation} --voter <name> --vote {approve,reject}

python3 ~/.claude/tools/consensus_vote.py --tally --task-id <id> \
    --action-type {git-push,publish-release,aws-mutation} [--threshold N]
```

## Composition (pairs with / hands off to)
Writes through `bb-write`'s underlying `bb_common.insert_stamped()`, reads
through `bb-read`'s `fetch()`, into the blackboard's `consensus_state` table
(Phase 3).

## Build & maintenance notes
Lives at `~/.claude/tools/consensus_vote.py`. Default approval threshold is
2 ("2-of-3"), overridable via `--threshold`. Not wired into any hook, git
command, or AWS call — deliberately, per the spec's own "audit-log
addition" framing.
