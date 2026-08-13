# Consensus Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Give gated actions (`git push`, publish/release commands, AWS
mutations) a queryable 2-of-3 consensus vote history on the blackboard's
`consensus_state` table — an audit log, not a new enforcement mechanism.

**Architecture:** One new tool, `consensus_vote.py`, with `--record` (cast
one voter's vote for one action instance) and `--tally` (count votes for
that instance, report whether the approval threshold is met). It writes
through `bb_common.insert_stamped()` (Phase 3) into `consensus_state`,
reads back through `bb_read.fetch()` (Phase 3).

**Tech Stack:** Python 3 stdlib only, plus this repo's own
`bb_common`/`bb_read` modules (same-dir cross-tool import, established in
Phases 3-4).

**Spec:** `docs/superpowers/specs/2026-08-06-agent-loop-v2-design.md`
(Phase 6 — "Consensus gate")

## Grounding correction (read before Task 1)

The spec's Phase 6 sentence names a specific existing mechanism —
*"any AWS mutation that would fire despite `REQUIRE_MUTATION_CONSENT=true`"*
— that does not exist. A repo-wide grep for `REQUIRE_MUTATION_CONSENT`
across every `.py`/`.sh`/`.md` file in this repo returns exactly one hit:
the spec doc itself. There is no such environment variable, flag, or gate
anywhere in `payload/`. Likewise "the existing never-auto-push rule" is not
a technical gate in this codebase either — the closest real artifact is
`loop_autocommit.sh`'s own header comment ("This tool NEVER pushes —
publication happens only at digest review, by hand"), which is a design
invariant of one specific tool, not a general enforcement mechanism with a
bypass flag that a vote tally could interact with.

This matches the pattern Phases 2 and 4 already found: the original external
proposal this spec reconciled described mechanisms that read as more
concrete than what actually exists. The spec's own words settle what to
build regardless: *"This is an audit-log addition — it does not relax the
existing... rule... it gives them a queryable vote history."* So this plan
builds exactly that and nothing more — `consensus_vote.py` is not wired into
any hook, any git operation, or any AWS call. It is a standalone tool an
agent (or a human) can use to record independent reviewers' votes on a
risky action *before* taking it, and query whether a 2-of-3 threshold was
reached — the recording and the tally are evidence for a decision a human
or agent still makes themselves, not a technical gate that blocks anything.
Do not wire this into `loop_autocommit.sh`, any hook, or any git/AWS command
as part of this plan — that would be inventing new enforcement the spec
never actually asked for.

## Global Constraints

- `action_type` is exactly one of `git-push`, `publish-release`,
  `aws-mutation` — no others, matching the spec's named list verbatim.
- `vote` is exactly one of `approve`, `reject`.
- Default approval threshold is 2 (the spec's "2-of-3"), overridable via
  `--threshold` for a future action type that might need a different quorum
  — the tool does not hardcode "3 voters," only "2 approvals required by
  default," since nothing stops a real review from involving more or fewer
  reviewers than exactly three.
- `--db` takes the same explicit override every other blackboard-backed
  tool in this spec takes, so tests never touch the real
  `~/.claude/state/blackboard.db`.
- New tool needs one `payload/registry/REGISTRY.md` row (domain:
  `quality-security` — this is a safety/audit tool, alongside
  `sql-safety-reviewer` and the `audit-*` tools, not a
  `meta-orchestration` coordination tool like `bb-write`/`worktree-exec`)
  and one `payload/registry/guides/<name>.md`, plus one `payload/MANIFEST`
  line.

---

### Task 1: `consensus_vote.py` — record and tally

**Files:**
- Create: `payload/tools/consensus_vote.py`
- Test: `payload/tools/tests/test_consensus_vote.py`

**Interfaces:**
- Consumes: `bb_common.{connect, default_db_path, insert_stamped}`,
  `bb_read.fetch` (Phase 3).
- Produces:
  - `ACTION_TYPES: tuple[str]`, `VOTES: tuple[str]`, `DEFAULT_THRESHOLD: int`
  - `record(db_path, task_id, action_type, voter, vote, note="") -> int` (row
    id) — raises `ValueError` on a bad `action_type` or `vote`.
  - `tally(db_path, task_id, action_type, threshold=DEFAULT_THRESHOLD) ->
    dict` with keys `task_id, action_type, total_votes, approve, reject,
    threshold, quorum_met, voters`.
  - `main(argv=None) -> int`

- [ ] **Step 1: Write the failing tests**

Create `payload/tools/tests/test_consensus_vote.py`:

```python
import contextlib, io, pathlib, sys, tempfile, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import consensus_vote as cv


class TestConsensusVote(unittest.TestCase):
    def _db(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        return str(pathlib.Path(td.name) / "blackboard.db")

    def test_record_rejects_bad_action_type(self):
        db = self._db()
        with self.assertRaises(ValueError):
            cv.record(db, "t1", "delete-prod-db", "alice", "approve")

    def test_record_rejects_bad_vote(self):
        db = self._db()
        with self.assertRaises(ValueError):
            cv.record(db, "t1", "git-push", "alice", "maybe")

    def test_tally_counts_votes_by_action_type(self):
        db = self._db()
        cv.record(db, "t1", "git-push", "alice", "approve")
        cv.record(db, "t1", "git-push", "bob", "approve")
        cv.record(db, "t1", "git-push", "carol", "reject")
        cv.record(db, "t1", "aws-mutation", "alice", "approve")  # different action_type, must not count
        result = cv.tally(db, "t1", "git-push")
        self.assertEqual(result["total_votes"], 3)
        self.assertEqual(result["approve"], 2)
        self.assertEqual(result["reject"], 1)
        self.assertTrue(result["quorum_met"])
        self.assertEqual(sorted(result["voters"]), ["alice", "bob", "carol"])

    def test_tally_quorum_not_met_below_threshold(self):
        db = self._db()
        cv.record(db, "t1", "publish-release", "alice", "approve")
        result = cv.tally(db, "t1", "publish-release")
        self.assertFalse(result["quorum_met"])

    def test_tally_custom_threshold(self):
        db = self._db()
        cv.record(db, "t1", "aws-mutation", "alice", "approve")
        result = cv.tally(db, "t1", "aws-mutation", threshold=1)
        self.assertTrue(result["quorum_met"])

    def test_tally_scoped_to_task_id(self):
        db = self._db()
        cv.record(db, "t1", "git-push", "alice", "approve")
        cv.record(db, "t2", "git-push", "bob", "approve")
        result = cv.tally(db, "t1", "git-push")
        self.assertEqual(result["total_votes"], 1)

    def test_cli_record_and_tally(self):
        db = self._db()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc1 = cv.main(["--record", "--task-id", "t1", "--action-type", "git-push",
                           "--voter", "alice", "--vote", "approve", "--db", db])
        self.assertEqual(rc1, 0)
        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            rc2 = cv.main(["--tally", "--task-id", "t1", "--action-type", "git-push", "--db", db])
        self.assertEqual(rc2, 0)
        self.assertIn("1 approve", buf2.getvalue())

    def test_cli_record_requires_voter_and_vote(self):
        db = self._db()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = cv.main(["--record", "--task-id", "t1", "--action-type", "git-push", "--db", db])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the suite and confirm it fails**

Run: `python3 -m pytest payload/tools/tests/test_consensus_vote.py -v`
Expected: `ModuleNotFoundError: No module named 'consensus_vote'`.

- [ ] **Step 3: Write `payload/tools/consensus_vote.py`**

```python
#!/usr/bin/env python3
"""Record and tally consensus votes for gated actions (agent-loop-v2 design
spec, Phase 6) — an audit-log addition on top of the blackboard's
consensus_state table (Phase 3). This tool does NOT enforce anything: no
hook in this codebase currently blocks a git push, a publish/release
command, or an AWS mutation on a vote tally (the spec's own
REQUIRE_MUTATION_CONSENT=true does not correspond to any real flag or gate
anywhere in this repo — see the plan's Grounding section). Those actions
stay governed exactly as they are today — human judgment plus the
CLAUDE.md directives — this tool only gives that judgment a queryable
history: "2 of 3" is the default approval threshold, not an enforced one.

Usage:
  python3 consensus_vote.py --record --task-id ID --action-type {git-push,publish-release,aws-mutation} \
      --voter NAME --vote {approve,reject} [--note TEXT]
  python3 consensus_vote.py --tally --task-id ID --action-type {git-push,publish-release,aws-mutation} \
      [--threshold N]
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bb_common as bb  # noqa: E402
import bb_read  # noqa: E402

ACTION_TYPES = ("git-push", "publish-release", "aws-mutation")
VOTES = ("approve", "reject")
DEFAULT_THRESHOLD = 2
PHASE = "MERGE"


def record(db_path, task_id, action_type, voter, vote, note=""):
    if action_type not in ACTION_TYPES:
        raise ValueError("action_type must be one of %r, not %r" % (ACTION_TYPES, action_type))
    if vote not in VOTES:
        raise ValueError("vote must be one of %r, not %r" % (VOTES, vote))
    conn = bb.connect(db_path)
    try:
        row_id = bb.insert_stamped(conn, "consensus_state", task_id, PHASE, voter, {
            "action_type": action_type, "voter": voter, "vote": vote, "note": note,
        })
    finally:
        conn.close()
    return row_id


def tally(db_path, task_id, action_type, threshold=DEFAULT_THRESHOLD):
    conn = bb.connect(db_path)
    try:
        rows = bb_read.fetch(conn, "consensus_state", task_id=task_id)
    finally:
        conn.close()
    votes = [r["payload"] for r in rows if r["payload"].get("action_type") == action_type]
    approve = sum(1 for v in votes if v["vote"] == "approve")
    reject = sum(1 for v in votes if v["vote"] == "reject")
    return {
        "task_id": task_id, "action_type": action_type,
        "total_votes": len(votes), "approve": approve, "reject": reject,
        "threshold": threshold, "quorum_met": approve >= threshold,
        "voters": [v["voter"] for v in votes],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--record", action="store_true")
    mode.add_argument("--tally", action="store_true")
    p.add_argument("--task-id", required=True)
    p.add_argument("--action-type", required=True, choices=list(ACTION_TYPES))
    p.add_argument("--voter")
    p.add_argument("--vote", choices=list(VOTES))
    p.add_argument("--note", default="")
    p.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    p.add_argument("--db", default=str(bb.default_db_path()))
    a = p.parse_args(argv)

    if a.record:
        if not a.voter or not a.vote:
            print("error: --record requires --voter and --vote", file=sys.stderr)
            return 2
        try:
            record(a.db, a.task_id, a.action_type, a.voter, a.vote, note=a.note)
        except ValueError as e:
            print("error: %s" % e, file=sys.stderr)
            return 2
        print("recorded %s vote from %s for %s/%s" % (a.vote, a.voter, a.task_id, a.action_type))
        return 0

    result = tally(a.db, a.task_id, a.action_type, threshold=a.threshold)
    print("%s/%s: %d approve, %d reject (%d total) — quorum_met=%s (threshold=%d)"
          % (result["task_id"], result["action_type"], result["approve"], result["reject"],
             result["total_votes"], result["quorum_met"], result["threshold"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the suite and confirm it passes**

Run: `python3 -m pytest payload/tools/tests/test_consensus_vote.py -v`
Expected: PASS, 8 passed.

- [ ] **Step 5: Commit**

```bash
git add payload/tools/consensus_vote.py payload/tools/tests/test_consensus_vote.py
git commit -m "feat(consensus): consensus_vote.py — record/tally 2-of-3 gated-action votes"
```

---

### Task 2: Registry row, guide, and ARCHITECTURE.md

**Files:**
- Modify: `payload/registry/REGISTRY.md`
- Create: `payload/registry/guides/consensus-vote.md`
- Modify: `payload/MANIFEST`
- Modify: `ARCHITECTURE.md`

**Interfaces:** none — terminal task.

- [ ] **Step 1: Add the row** (`## Agents`/`## Tools` — this is a tool; add
  near `sql-safety-reviewer`'s neighborhood is an agent row, so add it at
  the end of the `## Tools` section, after `worktree-exec`)

```
| consensus-vote | tool | quality-security | Record/tally a 2-of-3 consensus vote (git-push, publish-release, aws-mutation) on the blackboard — an audit-log addition, not an enforcement gate |
```

- [ ] **Step 2: Write the guide**

Create `payload/registry/guides/consensus-vote.md`:

```markdown
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
```

- [ ] **Step 3: Run `lint_registry.py` and confirm it's clean**

Run: `python3 payload/tools/lint_registry.py payload/registry`
Expected: `lint_registry: OK (0 error(s))`

- [ ] **Step 4: Add the MANIFEST entry**

In `payload/MANIFEST`, add after `link-file tools/audit_store.py` (or
wherever the `bb_*.py`/`worktree_exec.py` lines from prior phases now sit):

```
link-file tools/consensus_vote.py
```

- [ ] **Step 5: Add the ARCHITECTURE.md note**

Immediately after the `worktree_exec.py` bullet added by the worktree plan
(still inside "### 2. Runtime loop layer"), add:

```
- **`payload/tools/consensus_vote.py`** records and tallies a 2-of-3
  consensus vote for a gated action (`git push`, publish/release, an AWS
  mutation) into the blackboard's `consensus_state` table — a queryable
  audit trail, not an enforcement mechanism; nothing in this codebase
  currently blocks any of those three action types on a vote tally.
```

- [ ] **Step 6: Run the full relevant test suite**

Run: `python3 -m pytest payload/tools/tests/ -v -k "consensus or registry"`
Expected: all PASS (8 consensus tests + 13 registry tests = 21).

- [ ] **Step 7: Commit**

```bash
git add payload/registry/REGISTRY.md payload/registry/guides/consensus-vote.md \
        payload/MANIFEST ARCHITECTURE.md
git commit -m "docs(consensus): registry row, guide, and architecture note for consensus-vote"
```

---

## Testing & rollback

Both commits are independently revertable via `git revert`.

Final check:

```bash
python3 -m pytest payload/tools/tests/ -v -k "consensus"
python3 payload/tools/lint_registry.py payload/registry
```

Expected: 8 tests passed; `lint_registry: OK (0 error(s))`.
