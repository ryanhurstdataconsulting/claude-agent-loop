#!/usr/bin/env python3
"""Extract redacted user/assistant text from Claude Code JSONL transcripts.

Reads ~/.claude/projects/<dir>/*.jsonl, keeps only user/assistant text
blocks (tool results, tool calls, and summaries are dropped), redacts
credential patterns, and writes one corpus file per project directory.
The output is for scratchpad use only — never commit it.
"""
import argparse
import collections
import json
import pathlib
import re
import sys

SYSTEM_REMINDER = re.compile(r"<system-reminder>[\s\S]*?</system-reminder>")

REDACTIONS = [
    ("PEM", re.compile(r"-----BEGIN [A-Z ]+-----[\s\S]*?-----END [A-Z ]+-----")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.?[A-Za-z0-9_-]*")),
    ("DB-URI", re.compile(r"\bpostgres(?:ql)?://[^\s\"']+")),
    ("TOKEN", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")),
    ("SECRET", re.compile(
        r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|secret"
        r"|password|passwd|pwd)\b\s*[:=]\s*[\"']?[^\s\"']+")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("PHONE", re.compile(
        r"(?<!\w)(?:\+?\d{1,2}[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]?\d{4}(?!\d)")),
]


def redact(text):
    """Return (clean_text, Counter of redactions by type)."""
    counts = collections.Counter()
    for label, rx in REDACTIONS:
        if label == "SECRET":
            text, n = rx.subn(r"\1=[REDACTED-SECRET]", text)
        elif label == "TOKEN":
            text, n = rx.subn("Bearer [REDACTED-TOKEN]", text)
        else:
            text, n = rx.subn(f"[REDACTED-{label}]", text)
        counts[label] += n
    return text, counts


def extract_texts(record):
    """Text blocks from a user/assistant record; everything else is dropped."""
    if record.get("type") not in {"user", "assistant"}:
        return []
    content = (record.get("message") or {}).get("content")
    texts = []
    if isinstance(content, str):
        texts.append(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
    return [SYSTEM_REMINDER.sub("", t) for t in texts if t and t.strip()]


def distill(root, out, prefix=""):
    """Distill every project dir under root; return per-project stats."""
    out.mkdir(parents=True, exist_ok=True)
    stats = {}
    for proj in sorted(p for p in root.iterdir()
                       if p.is_dir() and p.name.startswith(prefix)):
        sessions = sorted(proj.glob("*.jsonl"))
        if not sessions:
            continue
        counts = collections.Counter()
        turns = 0
        lines_out = []
        for s in sessions:
            lines_out.append(f"\n=== SESSION {s.name} ===")
            for raw in s.read_text(errors="replace").splitlines():
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                role = "U" if rec.get("type") == "user" else "A"
                for t in extract_texts(rec):
                    clean, c = redact(t)
                    counts.update(c)
                    lines_out.append(f"{role}: {clean}")
                    turns += 1
        (out / f"{proj.name}.md").write_text("\n".join(lines_out) + "\n")
        stats[proj.name] = {
            "sessions": len(sessions),
            "turns": turns,
            "redactions": sum(counts.values()),
            "by_type": dict(counts),
        }
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--projects-root", type=pathlib.Path,
                    default=pathlib.Path.home() / ".claude" / "projects")
    ap.add_argument("--out-dir", type=pathlib.Path, required=True)
    ap.add_argument("--prefix", default="",
                    help="only project dirs whose name starts with this")
    args = ap.parse_args()
    stats = distill(args.projects_root, args.out_dir, args.prefix)
    for name, s in sorted(stats.items()):
        print(f"{name}: sessions={s['sessions']} turns={s['turns']} "
              f"redactions={s['redactions']}")
    print(f"TOTAL projects={len(stats)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
