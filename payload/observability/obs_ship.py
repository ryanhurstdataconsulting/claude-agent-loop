#!/usr/bin/env python3
"""obs_ship.py — folds the obs.v1 event log into an OTel span hierarchy and
exports it via OTLP to a local collector (localhost:4318 by default).

Out-of-tree sidecar: real opentelemetry-sdk dependency, run from its own venv
(~/.claude-agent-loop/obs-venv — see README.md), scheduled via launchd, never
imported from inside a hook. If the OTLP endpoint is unreachable (expected
until Phase 0 stands up a backend), export fails silently and the cursor does
NOT advance — the next scheduled run retries the same events once a backend
exists. A live Claude Code session never observes this either way; this
script runs entirely out-of-process.
"""
import argparse
import datetime
import glob
import hashlib
import json
import os
import pathlib
import sys


def _build_exporter(endpoint):
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    return OTLPSpanExporter(endpoint=endpoint + "/v1/traces")


def _load_cursor(cursor_path):
    try:
        with open(cursor_path) as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {"files": {}}
        data.setdefault("files", {})
        return data
    except Exception:
        return {"files": {}}


def _save_cursor(cursor_path, cursor):
    # Defensive: the default --cursor path is covered by install.sh's
    # mkdir -p, but a custom --cursor pointed at a not-yet-existing
    # directory would otherwise raise FileNotFoundError here.
    cursor_dir = os.path.dirname(cursor_path)
    if cursor_dir:
        os.makedirs(cursor_dir, exist_ok=True)
    tmp = cursor_path + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as fh:
        json.dump(cursor, fh, indent=2, sort_keys=True)
    os.replace(tmp, cursor_path)


def read_events(events_dir, cursor):
    """Yield (file, byte_offset_before, parsed_record) for every unread line
    across every *.ndjson file in events_dir, oldest file first."""
    files = cursor.get("files", {})
    for path in sorted(glob.glob(os.path.join(events_dir, "*.ndjson"))):
        start = int(files.get(path, 0))
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if start >= size:
            continue
        with open(path, "r") as fh:
            fh.seek(start)
            offset = start
            for line in fh:
                line_len = len(line.encode("utf-8"))
                stripped = line.strip()
                if stripped:
                    try:
                        rec = json.loads(stripped)
                    except Exception:
                        offset += line_len
                        continue
                    yield path, offset + line_len, rec
                else:
                    offset += line_len
                    continue
                offset += line_len


def fold_spans(events):
    """Fold obs.v1 events into a flat list of span dicts.

    Phase 2 scope: fold tool.pre/tool.post pairs (same span_id) into one span
    with a duration; every other event type becomes its own single-point
    span (zero duration). Full parent/child hierarchy (root-per-run,
    child-per-turn) is Phase 3+ work once kind:"run" records are consumable
    here as the root-span source — this function only builds the leaf layer.
    """
    by_span = {}
    order = []
    for _path, _offset, rec in events:
        if not isinstance(rec, dict):
            # Valid JSON, wrong shape (e.g. a bare `null`/`[]`/`"str"`/`42`
            # NDJSON line) — read_events() only guards against JSON that
            # fails to parse at all; this guards the "parsed fine, not an
            # object" case. Drop it silently rather than letting `.get()`
            # raise AttributeError and take the whole batch down with it.
            continue
        span_id = rec.get("span_id")
        if span_id not in by_span:
            by_span[span_id] = {"trace_id": rec.get("trace_id"), "span_id": span_id,
                                 "start_ts": rec.get("ts"), "end_ts": rec.get("ts"),
                                 "name": None, "duration_ms": 0, "events": []}
            order.append(span_id)
        span = by_span[span_id]
        span["events"].append(rec)
        span["end_ts"] = rec.get("ts")
        event = rec.get("event")
        attrs = rec.get("attrs") or {}
        if event in ("tool.pre", "tool.post"):
            span["name"] = "tool:%s" % attrs.get("tool_name", "unknown")
            if event == "tool.post" and attrs.get("duration_ms") is not None:
                span["duration_ms"] = attrs["duration_ms"]
        elif span["name"] is None:
            span["name"] = event
    return [by_span[sid] for sid in order]


def _id_to_int(value, byte_len):
    """Convert an obs.v1 trace_id/span_id string into an int of the given
    byte width, for OTel's SpanContext.

    obs_emit.py's trace_id_for()/span_id_for() are sha256-derived hex of
    exactly the right width already (trace_id: 32 hex chars/16 bytes,
    span_id: 16 hex chars/8 bytes) and pass through unchanged here, so the
    exported span's IDs match the obs.v1 log verbatim for correlation. Any
    other shape (e.g. short mnemonic test-fixture IDs like "t1"/"spA", which
    are not valid hex of the right width) is hashed down deterministically
    to the right width instead of raising — this function must never fail
    on a malformed or non-conforming ID."""
    try:
        n = int(value, 16)
        if 0 < n < (1 << (byte_len * 8)):
            return n
    except (TypeError, ValueError):
        pass
    digest = hashlib.sha256(str(value).encode("utf-8")).digest()[:byte_len]
    return int.from_bytes(digest, "big") or 1


def _iso_to_ns(ts):
    """obs.v1's ISO-8601 `ts` string -> epoch nanoseconds, what OTel's
    start_time/end_time expect."""
    return int(datetime.datetime.fromisoformat(
        str(ts).replace("Z", "+00:00")).timestamp() * 1e9)


class _FixedIdGenerator:
    """IdGenerator (duck-typed: generate_trace_id/generate_span_id) that
    returns a pre-set trace_id/span_id on the next call.

    obs.v1's trace_id/span_id are deterministic (sha256-derived — see
    obs_emit.py) and must survive verbatim into the exported span for
    correlation with the enclosing run/turn. The stock Tracer only draws IDs
    from its TracerProvider's IdGenerator, and `opentelemetry.sdk.trace.Span`
    cannot be constructed directly on the installed SDK version (1.41.1):
    `Span.__new__` raises `TypeError: Span must be instantiated via a
    tracer.` whenever `cls is Span` — confirmed empirically, not assumed.
    Injecting a custom IdGenerator into a TracerProvider is the SDK's own
    sanctioned per-provider extension point (`TracerProvider(id_generator=)`),
    so calling `set_next()` immediately before each `tracer.start_span()`
    gives exact per-call ID control through a fully supported path, no
    private-API workarounds."""

    def __init__(self):
        self._trace_id = None
        self._span_id = None

    def set_next(self, trace_id, span_id):
        self._trace_id = trace_id
        self._span_id = span_id

    def generate_trace_id(self):
        return self._trace_id

    def generate_span_id(self):
        return self._span_id


def _build_tracer():
    """Build a throwaway TracerProvider + Tracer with a controllable
    IdGenerator, used only to obtain real, tracer-issued ReadableSpan objects
    carrying our own pre-computed trace_id/span_id/timing. No span processor
    is attached — export_spans() calls the OTLP exporter directly on the
    finished spans it collects, so nothing else should also try to export
    them. shutdown_on_exit=False: this provider is throwaway and scoped to
    one export_spans() call; it has no processors or live exporter attached
    to it, so there is nothing that needs an atexit-registered shutdown."""
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.sampling import ALWAYS_ON

    id_generator = _FixedIdGenerator()
    provider = TracerProvider(
        sampler=ALWAYS_ON,
        id_generator=id_generator,
        resource=Resource.create({"service.name": "claude-agent-loop"}),
        shutdown_on_exit=False,
    )
    return provider.get_tracer("obs_ship"), id_generator


def _to_readable_span(span_dict, tracer, id_generator):
    """Build one real OTel SDK ReadableSpan from a fold_spans() span dict."""
    from opentelemetry.trace import SpanKind

    id_generator.set_next(
        _id_to_int(span_dict.get("trace_id"), 16),
        _id_to_int(span_dict.get("span_id"), 8),
    )
    start_ns = _iso_to_ns(span_dict["start_ts"])
    end_ns = _iso_to_ns(span_dict.get("end_ts") or span_dict["start_ts"])
    span = tracer.start_span(
        name=span_dict.get("name") or "unknown",
        kind=SpanKind.INTERNAL,
        start_time=start_ns,
    )
    span.end(end_time=end_ns)
    return span


def export_spans(spans, endpoint):
    """Best-effort OTLP export. Returns True on success, False on any
    exporter-level failure — including an unreachable endpoint, which is
    the expected state until Phase 0 stands up a backend.

    Builds real opentelemetry.sdk.trace ReadableSpan objects (via
    _to_readable_span/_build_tracer) before calling the exporter — the real
    OTLPSpanExporter.export() is typed Sequence[ReadableSpan] and its
    protobuf encoder accesses `.resource` on each item; passing the plain
    span dicts fold_spans() returns raises `AttributeError: 'dict' object
    has no attribute 'resource'` before any network I/O, independent of
    whether an OTLP backend is reachable (confirmed empirically against
    opentelemetry-sdk 1.41.1). SpanExportResult is a plain Enum, not
    IntEnum — `bool(SpanExportResult.FAILURE)` is also True, so success is
    checked by explicit comparison to SpanExportResult.SUCCESS, never by
    truthiness.

    Span construction is deliberately OUTSIDE the network try/except and is
    per-record fault-tolerant: one malformed span dict (e.g. a record with a
    missing/unparseable `ts`, so fold_spans() left start_ts=None and
    _iso_to_ns(None) raises) is dropped silently rather than aborting the
    whole batch. Before this, _to_readable_span() ran INSIDE the same
    try/except that governs cursor advancement, so a single bad record made
    export_spans() report failure for the entire batch — indistinguishable
    from "no backend yet" — permanently, since the cursor never advances
    past a batch it thinks failed to export, and every future run hits the
    exact same unfixable record again. Only the actual network
    exporter.export() call is guarded by the try/except that decides cursor
    advancement now."""
    if not spans:
        return True
    try:
        tracer, id_generator = _build_tracer()
    except Exception:
        return False

    readable = []
    for span_dict in spans:
        try:
            readable.append(_to_readable_span(span_dict, tracer, id_generator))
        except Exception:
            continue  # drop the one bad span; don't wedge the whole batch

    if not readable:
        return True  # nothing left to export is not a failure

    try:
        from opentelemetry.sdk.trace.export import SpanExportResult

        exporter = _build_exporter(endpoint)
        result = exporter.export(readable)
        return result == SpanExportResult.SUCCESS
    except Exception:
        return False


def run_once(events_dir, cursor_path, endpoint="http://localhost:4318"):
    cursor = _load_cursor(cursor_path)
    events = list(read_events(events_dir, cursor))
    if not events:
        return {"exported": True, "count": 0}
    spans = fold_spans(events)
    ok = export_spans(spans, endpoint)
    if not ok:
        return {"exported": False, "count": len(events)}
    max_offset_by_file = {}
    for path, offset, _rec in events:
        max_offset_by_file[path] = max(max_offset_by_file.get(path, 0), offset)
    cursor.setdefault("files", {})
    cursor["files"].update(max_offset_by_file)
    _save_cursor(cursor_path, cursor)
    return {"exported": True, "count": len(events)}


def main(argv=None):
    home = pathlib.Path.home() / ".claude"
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--events-dir", default=str(home / "metrics" / "events"))
    p.add_argument("--cursor", default=str(home / "metrics" / "state" / "obs_ship.cursor.json"))
    p.add_argument("--endpoint", default=os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"))
    a = p.parse_args(argv)
    result = run_once(a.events_dir, a.cursor, endpoint=a.endpoint)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
