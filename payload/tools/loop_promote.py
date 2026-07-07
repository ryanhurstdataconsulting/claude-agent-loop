#!/usr/bin/env python3
"""loop_promote.py — diff local learning state against the repo seeds (P5).

The learning files (``SCALES.md``, ``HEURISTICS.md``) are copied from the repo
seeds once at install, then diverge as the loop learns on this machine. Promoting
a learned change BACK into the publishable repo seed is a deliberate,
owner-reviewed act — the diverged state can carry client-tinged content (a niche
scale named after a client task, a heuristic threshold tuned on client work).

This tool is the review surface: for each learning file it prints a unified diff
of the LOCAL file against its SEED, then the promotion instructions. It is
strictly READ-ONLY — it never writes a byte to either side. Promotion itself is
manual: copy the reviewed hunks into ``payload/learning/`` yourself, only after
running ``classify_visibility.py`` and ``secret_pii_scrub_gate.py`` over them and
generalizing anything they flag CLIENT or UNSURE.

Stdlib only.
"""
import argparse
import difflib
import pathlib
import sys

LEARNING_FILES = ["SCALES.md", "HEURISTICS.md"]


def _read(path):
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def diff_file(name, learning_dir, seeds_dir):
    """Return the unified-diff text for one file (empty string when identical)."""
    local = _read(pathlib.Path(learning_dir) / name)
    seed = _read(pathlib.Path(seeds_dir) / name)
    local_lines = (local or "").splitlines(keepends=True)
    seed_lines = (seed or "").splitlines(keepends=True)
    diff = difflib.unified_diff(
        seed_lines, local_lines,
        fromfile="seed/%s" % name, tofile="local/%s" % name)
    return "".join(diff), (local is not None), (seed is not None)


INSTRUCTIONS = (
    "Promotion into the repo seed is OWNER-reviewed and manual — this tool "
    "never writes.\n"
    "For any hunk you want to promote:\n"
    "  1. Run classify_visibility.py over the changed lines; anything CLIENT or "
    "UNSURE must be generalized before it can ship.\n"
    "  2. Run secret_pii_scrub_gate.py over the same lines.\n"
    "  3. Copy the reviewed, generalized hunk into payload/learning/ by hand, "
    "then commit it via loop_autocommit.sh.\n"
)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Diff local learning files against the repo seeds (read-only).")
    home = pathlib.Path.home()
    ap.add_argument("--learning-dir",
                    default=str(home / ".claude" / "learning"))
    ap.add_argument("--seeds-dir",
                    default=str(pathlib.Path(__file__).resolve().parents[1]
                                / "learning"))
    args = ap.parse_args(argv)

    print("loop_promote: local learning vs repo seeds (READ-ONLY)\n")
    for name in LEARNING_FILES:
        text, has_local, has_seed = diff_file(name, args.learning_dir,
                                              args.seeds_dir)
        print("=== %s ===" % name)
        if not has_local:
            print("(no local %s — nothing learned here yet)" % name)
        elif not has_seed:
            print("(no seed %s in the repo — this file has no upstream)" % name)
        elif not text:
            print("identical to the seed — no differences to promote.")
        else:
            sys.stdout.write(text)
            if not text.endswith("\n"):
                print()
        print()

    print(INSTRUCTIONS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
