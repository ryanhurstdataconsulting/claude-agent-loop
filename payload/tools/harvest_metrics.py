#!/usr/bin/env python3
"""harvest_metrics.py — objective metrics harvester for the Resource Loop (P2).

Consumes Claude Code JSONL transcripts and appends one JSON record per task or
session to a monthly shard under ``<metrics-dir>/YYYY-MM.jsonl``. Stdlib only.
It reuses ``distill_transcripts.redact()`` for any free text it persists and
mirrors that module's tolerant walk (malformed lines are skipped, not fatal).

Transcript kinds
----------------
* ``.../<slug>/<sid>/subagents/agent-<id>.jsonl`` -> a ``kind:"task"`` record
  keyed ``task_id="agent-<id>"``.
* ``.../<slug>/<sid>.jsonl`` (a main session file) -> a ``kind:"session"``
  rollup keyed ``task_id="session-<sid>"``. On ``--event SessionEnd`` it also
  catches up any sibling ``subagents/agent-*.jsonl`` not yet in the cursor,
  writing each as a ``kind:"task"`` record.

Last-wins convention
---------------------
Records are keyed by ``(task_id, kind)``. Re-harvesting a transcript that has
grown (its size or mtime changed) appends a REPLACEMENT record rather than
mutating the old one; **consumers MUST take the LAST record per
(task_id, kind)**. This keeps every write a single append and never rewrites
history.

Token-accounting note
----------------------
A single assistant API response is frequently split across several JSONL
records that share one ``message.id`` and repeat identical (often partial)
``usage``. Summing usage from every record would multiply-count tokens, so
token and web-tool sums are deduplicated by ``message.id`` — the final fragment
seen for an id wins (it carries the complete totals and ``server_tool_use``).
Content blocks (text / tool_use / tool_result) are NOT duplicated across
fragments, so they are counted per block. ``turns`` is the literal count of
assistant-type records (per the P2 spec), which may exceed the number of
distinct assistant messages when streaming splits a turn.
"""
import argparse
import collections
import datetime
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import distill_transcripts as dt  # noqa: E402

SCHEMA = 1

# Resource Loop ANNOUNCE grammar (see hooks/inject-resource-loop.sh). The dash
# class covers em dash, en dash, and hyphen so authored variants all parse.
_DASH = "—–-"
DEPLOY_RE = re.compile(r"Resource Loop\s*[%s]\s*deploying:\s*(.+)" % _DASH)
BARE_RE = re.compile(r"Resource Loop\s*[%s]\s*no registry match;\s*"
                     r"proceeding bare" % _DASH)
_REASON_SPLIT = re.compile(r"\s+[%s]\s+" % _DASH)   # " — reason" separator
_PAREN = re.compile(r"\([^)]*\)")                    # "(category)" to strip

# Test-runner output: pytest ("34 passed, 2 failed"), vitest ("3 passed (4)"),
# and generic "N passed / N failed" all match these.
PASSED_RE = re.compile(r"(\d+)\s+passed")
FAILED_RE = re.compile(r"(\d+)\s+failed")


def _redact(text):
    """Redact any free text before it is persisted (secrets/PII scrub)."""
    if not text:
        return text
    return dt.redact(text)[0]


def parse_tests(text):
    """Return (passed, failed, detected) for one tool-result text.

    The LAST ``N passed`` / ``N failed`` in the text wins (re-runs supersede
    earlier output); a result reporting both counts contributes both.
    """
    if not text:
        return (0, 0, False)
    passed_all = PASSED_RE.findall(text)
    failed_all = FAILED_RE.findall(text)
    passed = int(passed_all[-1]) if passed_all else 0
    failed = int(failed_all[-1]) if failed_all else 0
    detected = bool(passed_all or failed_all)
    return (passed, failed, detected)


def _resource_names(payload):
    """Extract redacted resource ids from a `deploying:` payload."""
    names = []
    for chunk in re.split(r"[;,]", payload):
        name = _REASON_SPLIT.split(chunk)[0]   # drop the "— reason" tail
        name = _PAREN.sub("", name)            # drop the "(category)"
        name = name.strip().strip(".").strip()
        if name:
            names.append(_redact(name))
    return names


def parse_announce(texts):
    """Scan assistant texts in order; parse the FIRST Resource Loop line.

    Returns (resources_deployed, announce_found, bare).
    """
    for text in texts:
        if not text:
            continue
        for line in text.splitlines():
            if BARE_RE.search(line):
                return ([], True, True)
            m = DEPLOY_RE.search(line)
            if m:
                return (_resource_names(m.group(1)), True, False)
    return ([], False, False)


def _parse_ts(value):
    """Parse an ISO-8601 timestamp (…Z) to an aware UTC datetime, or None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _month_shard(ts_end):
    """Month key (YYYY-MM, UTC) from the ts_end string; falls back to now."""
    dt_end = _parse_ts(ts_end)
    if dt_end is None:
        dt_end = datetime.datetime.now(datetime.timezone.utc)
    return dt_end.astimezone(datetime.timezone.utc).strftime("%Y-%m")


def _read_records(path):
    """Yield parsed JSON records, skipping malformed lines. Returns a list."""
    records = []
    for raw in path.read_text(errors="replace").splitlines():
        if not raw.strip():
            continue
        try:
            records.append(json.loads(raw))
        except json.JSONDecodeError:
            continue   # malformed line: skipped silently (spec)
    return records


def _project_slug(path):
    """The project dir slug — the path component directly under `projects/`."""
    p = pathlib.Path(path).resolve()
    for anc in p.parents:
        if anc.parent is not None and anc.parent.name == "projects":
            return anc.name
    return p.parent.name


def _content_blocks(message):
    content = message.get("content")
    if isinstance(content, list):
        return content
    return []


def _aggregate(records):
    """Fold a record list into the numeric aggregates for one transcript."""
    by_msg = {}                       # message.id -> (model, usage)  last-wins
    turns = 0
    tools = collections.Counter()
    total_tool_calls = 0
    tool_errors = 0
    interrupted = 0
    tests_passed = tests_failed = 0
    tests_detected = False
    ts_first = ts_last = None
    git_branch = None
    session_id = None
    assistant_texts = []

    for rec in records:
        rtype = rec.get("type")
        if session_id is None and rec.get("sessionId"):
            session_id = rec.get("sessionId")
        if rec.get("gitBranch"):
            git_branch = rec.get("gitBranch")
        ts = rec.get("timestamp")
        if ts:
            if ts_first is None:
                ts_first = ts
            ts_last = ts

        message = rec.get("message") if isinstance(rec.get("message"), dict) else {}

        if rtype == "assistant":
            turns += 1
            mid = message.get("id") or rec.get("uuid") or id(rec)
            usage = message.get("usage")
            model = message.get("model")
            if isinstance(usage, dict) and model != "<synthetic>":
                by_msg[mid] = (model, usage)   # last fragment wins
            content = message.get("content")
            if isinstance(content, str):
                assistant_texts.append(content)
            else:
                for block in _content_blocks(message):
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "tool_use":
                        tools[block.get("name") or "unknown"] += 1
                        total_tool_calls += 1
                    elif btype == "text":
                        assistant_texts.append(block.get("text", ""))

        elif rtype == "user":
            tr_texts = []
            for block in _content_blocks(message):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    if block.get("is_error"):
                        tool_errors += 1
                    c = block.get("content")
                    if isinstance(c, str):
                        tr_texts.append(c)
                    elif isinstance(c, list):
                        for x in c:
                            if isinstance(x, dict) and x.get("type") == "text":
                                tr_texts.append(x.get("text", ""))
            tur = rec.get("toolUseResult")
            if isinstance(tur, dict) and tur.get("interrupted"):
                interrupted += 1
            # Test parsing: prefer toolUseResult.stdout so we do not double-count
            # a Bash result whose stdout is echoed into tool_result.content.
            if (isinstance(tur, dict)
                    and isinstance(tur.get("stdout"), str)
                    and tur["stdout"].strip()):
                test_texts = [tur["stdout"]]
            else:
                test_texts = tr_texts
            for txt in test_texts:
                p, f, d = parse_tests(txt)
                tests_passed += p
                tests_failed += f
                tests_detected = tests_detected or d

    models = {}
    web_search = web_fetch = 0
    for _mid, (model, usage) in by_msg.items():
        m = models.setdefault(model, {"in": 0, "out": 0,
                                      "cache_read": 0, "cache_creation": 0})
        m["in"] += usage.get("input_tokens", 0) or 0
        m["out"] += usage.get("output_tokens", 0) or 0
        m["cache_read"] += usage.get("cache_read_input_tokens", 0) or 0
        m["cache_creation"] += usage.get("cache_creation_input_tokens", 0) or 0
        stu = usage.get("server_tool_use")
        if isinstance(stu, dict):
            web_search += stu.get("web_search_requests", 0) or 0
            web_fetch += stu.get("web_fetch_requests", 0) or 0

    tin = sum(v["in"] for v in models.values())
    tcr = sum(v["cache_read"] for v in models.values())
    tcc = sum(v["cache_creation"] for v in models.values())
    # cache_efficiency = cache_read / max(1, input + cache_read + cache_creation)
    cache_efficiency = round(tcr / max(1, tin + tcr + tcc), 4)
    error_rate = round(tool_errors / max(1, total_tool_calls), 4)

    resources, announce_found, bare = parse_announce(assistant_texts)

    return {
        "models": models,
        "turns": turns,
        "tools": dict(tools),
        "tool_errors": tool_errors,
        "error_rate": error_rate,
        "interrupted": interrupted,
        "tests": {"detected": tests_detected,
                  "passed": tests_passed, "failed": tests_failed},
        "web": {"search": web_search, "fetch": web_fetch},
        "cache_efficiency": cache_efficiency,
        "resources_deployed": resources,
        "announce_found": announce_found,
        "bare": bare,
        "ts_start": ts_first,
        "ts_end": ts_last,
        "git_branch": git_branch,
        "session_id": session_id,
    }


def build_record(path, event, kind, session_id=None, extra=None):
    """Read one transcript and return its metrics record dict (no I/O)."""
    path = pathlib.Path(path)
    agg = _aggregate(_read_records(path))

    sid = session_id or agg["session_id"]
    if not sid:
        sid = path.stem if kind == "session" else path.parent.parent.name

    if kind == "task":
        task_id = path.stem                     # agent-<id>
    else:
        task_id = "session-%s" % sid

    dt_start = _parse_ts(agg["ts_start"])
    dt_end = _parse_ts(agg["ts_end"])
    if dt_start and dt_end:
        duration_s = round((dt_end - dt_start).total_seconds(), 3)
    else:
        duration_s = 0.0

    record = {
        "schema": SCHEMA,
        "kind": kind,
        "task_id": task_id,
        "session_id": sid,
        "project": _project_slug(path),
        "git_branch": _redact(agg["git_branch"]),
        "ts_start": agg["ts_start"],
        "ts_end": agg["ts_end"],
        "duration_s": duration_s,
        "trigger": event,
        "turns": agg["turns"],
        "models": agg["models"],
        "cache_efficiency": agg["cache_efficiency"],
        "tools": agg["tools"],
        "tool_errors": agg["tool_errors"],
        "error_rate": agg["error_rate"],
        "interrupted": agg["interrupted"],
        "tests": agg["tests"],
        "web": agg["web"],
        "compactions": 0,   # PreCompact events land as separate lines, not here
        "resources_deployed": agg["resources_deployed"],
        "announce_found": agg["announce_found"],
        "bare": agg["bare"],
    }
    if extra:
        record.update(extra)
    return record


# --- storage + cursor -------------------------------------------------------

def _cursor_path(metrics_dir):
    return pathlib.Path(metrics_dir) / "state" / "harvest.cursor.json"


def _load_cursor(metrics_dir):
    try:
        return json.loads(_cursor_path(metrics_dir).read_text())
    except (FileNotFoundError, ValueError):
        return {}


def _save_cursor(metrics_dir, cursor):
    dst = _cursor_path(metrics_dir)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".tmp.%d" % os.getpid())
    tmp.write_text(json.dumps(cursor, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, dst)   # atomic rename


def _append_record(metrics_dir, record):
    shard = pathlib.Path(metrics_dir) / ("%s.jsonl" % _month_shard(record["ts_end"]))
    shard.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    # Single append write — atomic under PIPE_BUF for a one-line record.
    with open(shard, "a") as f:
        f.write(line)


def _maybe_harvest_file(path, event, kind, metrics_dir, cursor,
                        session_id=None, extra=None):
    """Harvest one transcript if new/changed; return the record or None."""
    path = pathlib.Path(path).resolve()
    try:
        st = path.stat()
    except OSError:
        return None
    key = str(path)
    prev = cursor.get(key)
    if prev and prev.get("mtime") == st.st_mtime_ns and prev.get("size") == st.st_size:
        return None   # unchanged and already harvested
    record = build_record(path, event, kind, session_id=session_id, extra=extra)
    _append_record(metrics_dir, record)
    cursor[key] = {
        "mtime": st.st_mtime_ns,
        "size": st.st_size,
        "records_emitted": (prev.get("records_emitted", 0) if prev else 0) + 1,
    }
    return record


def _subagents_dir(session_file):
    """`<slug>/<sid>/subagents` for a `<slug>/<sid>.jsonl` session file."""
    s = str(session_file)
    base = s[:-6] if s.endswith(".jsonl") else s
    return pathlib.Path(base) / "subagents"


def harvest(transcript, event, metrics_dir, session_id=None):
    """Harvest a transcript, updating the shard(s) and the cursor.

    Returns the list of records emitted this run (empty if nothing changed or
    the transcript is missing).
    """
    transcript = pathlib.Path(transcript).resolve()
    emitted = []
    if not transcript.is_file():
        print("harvest_metrics: transcript not found: %s" % transcript,
              file=sys.stderr)
        return emitted

    metrics_dir = str(metrics_dir)
    cursor = _load_cursor(metrics_dir)
    is_agent = transcript.name.startswith("agent-")

    if is_agent:
        rec = _maybe_harvest_file(transcript, event, "task", metrics_dir,
                                  cursor, session_id=session_id)
        if rec:
            emitted.append(rec)
    else:
        tasks_harvested = 0
        if event == "SessionEnd":
            subdir = _subagents_dir(transcript)
            if subdir.is_dir():
                for agent_file in sorted(subdir.glob("agent-*.jsonl")):
                    rec = _maybe_harvest_file(agent_file, event, "task",
                                              metrics_dir, cursor)
                    if rec:
                        emitted.append(rec)
                        tasks_harvested += 1
        rec = _maybe_harvest_file(transcript, event, "session", metrics_dir,
                                  cursor, session_id=session_id,
                                  extra={"tasks_harvested": tasks_harvested})
        if rec:
            emitted.append(rec)

    _save_cursor(metrics_dir, cursor)
    return emitted


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--transcript", required=True,
                    help="a session .jsonl or a subagents/agent-<id>.jsonl")
    ap.add_argument("--event", required=True,
                    help="SubagentStop | SessionEnd")
    ap.add_argument("--metrics-dir",
                    default=os.path.join(os.path.expanduser("~"),
                                         ".claude", "metrics"))
    ap.add_argument("--session-id", default=None,
                    help="override the session id (else read from records)")
    args = ap.parse_args(argv)

    if args.event not in ("SubagentStop", "SessionEnd"):
        print("harvest_metrics: unknown --event %r "
              "(expected SubagentStop or SessionEnd)" % args.event,
              file=sys.stderr)
        return 2   # programmer error

    try:
        emitted = harvest(args.transcript, args.event, args.metrics_dir,
                          session_id=args.session_id)
    except Exception as exc:   # a hook must never break the session
        print("harvest_metrics: error: %s" % exc, file=sys.stderr)
        return 0
    print("harvest_metrics: emitted %d record(s)" % len(emitted))
    return 0


if __name__ == "__main__":
    sys.exit(main())
