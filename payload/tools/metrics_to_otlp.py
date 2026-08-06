#!/usr/bin/env python3
"""metrics_to_otlp.py — read-only retrofit exporter over the metrics shards.

Scans every monthly ``~/.claude/metrics/*.jsonl`` shard, applies the shards'
own ``(task_id, kind)`` last-wins dedup (the same in-memory pattern
``heuristics_eval.load_metrics()`` already implements), and emits OTel
metrics for the historical data via OTLP to a local collector
(localhost:4318 by default).

Out-of-tree sidecar: real opentelemetry-sdk dependency, run from its own venv
(~/.claude-agent-loop/obs-venv — see payload/observability/README.md),
scheduled via launchd, never imported from inside a hook. Every
``opentelemetry.*`` import in this module is deferred into a function body
(mirroring obs_ship.py's own convention) so importing this module itself
never requires the pip package to be installed — only actually exporting
does. This lets the pure aggregation functions below be unit-tested under a
bare interpreter, and lets ``payload/tools/tests/run_all.sh`` (which runs
every ``test_*.py`` with plain ``python3``, unlike
``payload/observability/tests/run.sh``'s venv-aware runner) exercise this
module's tests without a hard dependency failure.

Never mutates a shard — read-only, always. Idempotent via a cursor file
mapping ``"%s:%s" % (task_id, kind)`` to a content hash
(``sha256(json.dumps(record, sort_keys=True))``): a record whose hash is
unchanged since the last run is skipped; a record that is new, or whose
last-wins value changed since the last run, is (re-)included in this run's
aggregates and the cursor is updated with its new hash — but only once the
export actually succeeds (mirroring obs_ship.py: a failed export must not
advance the cursor, or the unexported delta is lost forever). "Idempotent"
means safe to re-run without double-counting, never "writes anything back to
the shard."

``verdict`` is not a universal ``kind:"task"`` field (only
``loop_close.py``'s workorder-emitted records carry it) — a missing key, or
an explicit ``null`` value, is bucketed separately as ``_MISSING``, never
coerced to the string ``"unknown"``. Heuristic firings (``kind:"learn"``
records) are counted by whatever literal ``rule`` string appears in the
data, never a hardcoded H1-H8 enum, so a retired or renumbered rule id (e.g.
``H0``, seen in real historical data) is still counted rather than dropped.
"""
import argparse
import glob
import hashlib
import json
import os
import pathlib
import sys

_MISSING = "<missing>"


# --- shard scanning + cursor -------------------------------------------------

def load_last_wins(metrics_dir):
    """Return ``{(task_id, kind): record}`` deduped to the LAST record per
    key, scanning every monthly shard in filename (chronological) order.

    Malformed lines and non-object JSON values are skipped silently, matching
    every other reader of this store (harvest_metrics, heuristics_eval).
    A record missing either ``task_id`` or ``kind`` is skipped — it cannot be
    addressed by the store's own key contract.
    """
    by_key = {}
    for path in sorted(glob.glob(os.path.join(metrics_dir, "*.jsonl"))):
        try:
            with open(path, "r") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        for raw in lines:
            if not raw.strip():
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            task_id, kind = rec.get("task_id"), rec.get("kind")
            if task_id is None or kind is None:
                continue
            by_key[(task_id, kind)] = rec   # last-wins
    return by_key


def _cursor_key(task_id, kind):
    return "%s:%s" % (task_id, kind)


def _content_hash(record):
    return hashlib.sha256(
        json.dumps(record, sort_keys=True).encode("utf-8")).hexdigest()


def _load_cursor(cursor_path):
    try:
        with open(cursor_path) as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_cursor(cursor_path, cursor):
    # Defensive: the default --cursor path is covered by install.sh's
    # mkdir -p, but a custom --cursor pointed at a not-yet-existing directory
    # would otherwise raise FileNotFoundError here (see obs_ship.py's
    # _save_cursor, which this mirrors exactly).
    cursor_dir = os.path.dirname(cursor_path)
    if cursor_dir:
        os.makedirs(cursor_dir, exist_ok=True)
    tmp = cursor_path + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as fh:
        json.dump(cursor, fh, indent=2, sort_keys=True)
    os.replace(tmp, cursor_path)


def select_changed(by_key, cursor):
    """Split ``by_key`` against the cursor.

    Returns ``(changed, new_hashes)``:

    * ``changed`` — ``{(task_id, kind): record}`` for entries whose content
      hash is absent from, or differs from, the cursor (new or updated since
      the last run).
    * ``new_hashes`` — ``{cursor_key: hash}`` for EVERY entry in ``by_key``
      (changed and unchanged alike), the value to persist to the cursor after
      a successful run so the next run's diff is against the current truth.
    """
    changed = {}
    new_hashes = {}
    for key, rec in by_key.items():
        task_id, kind = key
        ck = _cursor_key(task_id, kind)
        h = _content_hash(rec)
        new_hashes[ck] = h
        if cursor.get(ck) != h:
            changed[key] = rec
    return changed, new_hashes


# --- pure aggregation (no OTel dependency; unit-testable bare) --------------

def _bucket(value):
    """A field value, or ``_MISSING`` if the key was absent or explicitly
    null. Never coerces to the string "unknown" (design decision 2)."""
    return value if value is not None else _MISSING


def aggregate_tests(task_records):
    """``{"passed": N, "failed": N}`` summed over kind:"task" records'
    ``tests`` sub-object."""
    passed = failed = 0
    for rec in task_records:
        tests = rec.get("tests") or {}
        passed += tests.get("passed") or 0
        failed += tests.get("failed") or 0
    return {"passed": passed, "failed": failed}


def aggregate_error_rates(task_records):
    """The raw ``error_rate`` values present on kind:"task" records.

    A record missing ``error_rate`` (or carrying an explicit ``null``) is
    EXCLUDED, not coerced to 0 — the same M1 convention
    ``heuristics_eval._eval_mean`` uses, so an absent rate cannot silently
    drag the distribution toward zero.
    """
    return [r["error_rate"] for r in task_records
            if r.get("error_rate") is not None]


def aggregate_verdict(task_records):
    """``{verdict_bucket: count}`` over kind:"task" records. A missing
    ``verdict`` key, or an explicit ``null`` (loop_close.py sets ``verdict``
    to ``part.get("verdict")``, which can itself be ``None``), buckets as
    ``_MISSING`` — never the string ``"unknown"`` (design decision 2:
    verdict is not a universal kind:"task" field)."""
    counts = {}
    for rec in task_records:
        bucket = _bucket(rec.get("verdict"))
        counts[bucket] = counts.get(bucket, 0) + 1
    return counts


def aggregate_heuristics(learn_records):
    """``{rule: count}`` over kind:"learn" records, keyed by the LITERAL
    rule id string in the data (design decision 3) — never a hardcoded
    H1-H8 enum, so an id outside that set (e.g. "H0") is still counted."""
    counts = {}
    for rec in learn_records:
        bucket = _bucket(rec.get("rule"))
        counts[bucket] = counts.get(bucket, 0) + 1
    return counts


def aggregate_resources_source(task_records):
    """``{resources_source bucket: count}`` over kind:"task" records
    (``workorder`` / ``task`` / ``session`` / ``session-backfill`` / other)."""
    counts = {}
    for rec in task_records:
        bucket = _bucket(rec.get("resources_source"))
        counts[bucket] = counts.get(bucket, 0) + 1
    return counts


def build_aggregates(changed):
    """Run every aggregate_*() over the changed-records set, splitting by
    kind first. Records of any other kind (e.g. kind:"score") are read as
    part of the last-wins scan and cursor bookkeeping, but contribute to NO
    metric category — none of the five aggregates read them."""
    tasks = [rec for (task_id, kind), rec in changed.items() if kind == "task"]
    learns = [rec for (task_id, kind), rec in changed.items() if kind == "learn"]
    return {
        "tests": aggregate_tests(tasks),
        "error_rates": aggregate_error_rates(tasks),
        "verdicts": aggregate_verdict(tasks),
        "heuristics": aggregate_heuristics(learns),
        "resources_source": aggregate_resources_source(tasks),
    }


# --- OTel emission (real opentelemetry.sdk.metrics API) ---------------------

def _build_exporter(endpoint):
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
        OTLPMetricExporter,
    )
    return OTLPMetricExporter(endpoint=endpoint + "/v1/metrics")


def _build_meter():
    """Build a throwaway MeterProvider + Meter, backed by an
    InMemoryMetricReader, used only to obtain a real MetricsData snapshot
    from real Counter/Histogram instruments.

    InMemoryMetricReader (not PeriodicExportingMetricReader) starts no
    background export thread — emit_metrics() populates the instruments,
    reader.get_metrics_data() collects the current state synchronously, and
    export_aggregates() calls the OTLP exporter directly on that snapshot.
    Confirmed empirically (opentelemetry-sdk 1.41.1): a MeterProvider whose
    instruments were created but never recorded on yields
    ``get_metrics_data() is None`` — never an empty-but-non-None MetricsData
    — which export_aggregates() below treats as "nothing to export", not a
    failure. shutdown_on_exit=False: this provider is throwaway and scoped to
    one export_aggregates() call, so there is nothing that needs an
    atexit-registered shutdown (mirrors obs_ship.py's _build_tracer()).
    """
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    reader = InMemoryMetricReader()
    provider = MeterProvider(
        metric_readers=[reader],
        resource=Resource.create({"service.name": "claude-agent-loop"}),
        shutdown_on_exit=False,
    )
    return provider.get_meter("metrics_to_otlp"), reader


def emit_metrics(meter, aggregates):
    """Populate real OTel Counter/Histogram instruments from the
    pre-computed aggregate dicts (see aggregate_*() above)."""
    tests_counter = meter.create_counter(
        "claude_agent_loop.tests",
        description='test pass/fail counts from kind:"task" records')
    for result, count in aggregates["tests"].items():
        if count:
            tests_counter.add(count, attributes={"result": result})

    error_rate_hist = meter.create_histogram(
        "claude_agent_loop.error_rate",
        description='error_rate distribution across kind:"task" records')
    for value in aggregates["error_rates"]:
        error_rate_hist.record(value)

    verdict_counter = meter.create_counter(
        "claude_agent_loop.verdict",
        description="verdict counts; missing verdict bucketed separately")
    for verdict, count in aggregates["verdicts"].items():
        verdict_counter.add(count, attributes={"verdict": verdict})

    heuristics_counter = meter.create_counter(
        "claude_agent_loop.heuristic_firings",
        description='kind:"learn" firings by literal rule id string')
    for rule, count in aggregates["heuristics"].items():
        heuristics_counter.add(count, attributes={"rule": rule})

    resources_counter = meter.create_counter(
        "claude_agent_loop.resources_source",
        description='resources_source mix across kind:"task" records')
    for source, count in aggregates["resources_source"].items():
        resources_counter.add(count, attributes={"resources_source": source})


def export_aggregates(aggregates, endpoint):
    """Best-effort OTLP export of the aggregates. Returns ``(success,
    reason)``, the same contract as obs_ship.py's ``export_spans()``:

      - ``(True, "ok")``              — a normal successful export.
      - ``(True, "no-data-points")``  — every aggregate was empty (e.g. the
                                        only changed records this run were a
                                        kind that contributes to no metric
                                        category, such as kind:"score"); the
                                        network exporter is never even built.
      - ``(False, "meter-unavailable")`` — the SDK import/MeterProvider step
                                        failed (mirrors obs_ship.py's
                                        "tracer-unavailable").
      - ``(False, "export-failed")`` — instruments were built but the
                                        network export call failed or
                                        returned a non-SUCCESS result,
                                        including an unreachable endpoint.
    """
    try:
        meter, reader = _build_meter()
    except Exception:
        return False, "meter-unavailable"

    emit_metrics(meter, aggregates)
    metrics_data = reader.get_metrics_data()
    if metrics_data is None:
        return True, "no-data-points"

    try:
        from opentelemetry.sdk.metrics.export import MetricExportResult

        exporter = _build_exporter(endpoint)
        result = exporter.export(metrics_data)
        if result == MetricExportResult.SUCCESS:
            return True, "ok"
        return False, "export-failed"
    except Exception:
        return False, "export-failed"


# --- orchestration ------------------------------------------------------

def run_once(metrics_dir, cursor_path, endpoint="http://localhost:4318"):
    cursor = _load_cursor(cursor_path)
    by_key = load_last_wins(metrics_dir)
    changed, new_hashes = select_changed(by_key, cursor)
    if not changed:
        return {"exported": True, "count": 0, "reason": "ok"}

    aggregates = build_aggregates(changed)
    ok, reason = export_aggregates(aggregates, endpoint)
    if not ok:
        return {"exported": False, "count": len(changed), "reason": reason}

    cursor.update(new_hashes)
    _save_cursor(cursor_path, cursor)
    return {"exported": True, "count": len(changed), "reason": reason}


def main(argv=None):
    home = pathlib.Path.home() / ".claude"
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--metrics-dir", default=str(home / "metrics"))
    p.add_argument("--cursor", default=str(
        home / "metrics" / "state" / "metrics_to_otlp.cursor.json"))
    p.add_argument("--endpoint", default=os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"))
    a = p.parse_args(argv)
    result = run_once(a.metrics_dir, a.cursor, endpoint=a.endpoint)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
