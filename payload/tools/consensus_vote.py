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
