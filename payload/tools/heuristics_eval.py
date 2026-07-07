#!/usr/bin/env python3
"""heuristics_eval.py — the loop's heuristic-scoring engine (P6).

This is HEURISTIC SCORING over recorded task/score metrics, NOT model training.
Every rule below is a hand-written threshold over a window of recent records; no
weights are learned and no model is fit. The engine reads the declarative rules
in ``learning/HEURISTICS.md`` (parsed by ``lint_heuristics.parse_heuristics``),
computes each rule's window over the metrics store, and reports which rules FIRE
so the Resource Loop's LEARN step can act (improve-now / theme-note / no-action).

CLI
---
* ``--task-id <id>`` — evaluate the rules relevant to one task: its own
  ``resources_deployed`` (for the per-resource rules) plus every global rule.
* ``--window`` — a global scan: per-resource rules run for every resource seen,
  global rules run once.
* ``--session-id <sid>`` — scopes the session-window rule (H4 bare-streak) to the
  current session; without it, H4 falls back to recent project records and says
  so in its evidence note.
* ``--emit-learn <action> --rule <Hid> --task-id <id>`` — append a
  ``kind:"learn"`` record logging the decision the loop took (even a no-action,
  which is stored as positive signal).
* ``--metrics-dir`` / ``--heuristics-file`` / ``--scales-file`` — overridable
  locations; ``--json`` switches the report from human-readable to machine JSON.

Store contract (BINDING)
------------------------
Records are read from the current and previous month shards and **deduped to the
LAST record per ``(task_id, kind)``** before ANY aggregation — never a raw line
count (``harvest_metrics`` is append-only and re-emits replacement records). The
per-resource rules weight attribution by ``resources_source``: a ``"task"``
record announced its own resources (PRECISE); a ``"session-backfill"`` record
inherited the session's ANNOUNCE and is therefore COARSE (session granularity,
not per task). Both are counted, but every backfill evidence row is annotated
coarse so the reader can discount it — they are never silently treated as equal.

Because ``session-backfill`` is the normal ~98% case (subagents rarely announce),
a per-resource improve-now rule (H1, H7) that fires on coarse-dominated or thin
evidence is DOWNGRADED to theme-note: the engine emits an ``effective_action``
(with a ``downgrade_reason``) that the loop acts on, keeping the raw ``action``
visible. See ``_apply_downgrade`` and the C1 constants below.

Exit codes
----------
Exit 0 always for an evaluation (this is an advisory engine; a rule whose signal
is unavailable, or that raises, is printed to stderr and SKIPPED, never fatal).
Exit 2 only on a programmer error: a missing heuristics file, a malformed
``--emit-learn`` request, or neither ``--task-id`` nor ``--window`` given.

Determinism: timestamps come from the same UTC helper the other tools write with;
there is no ``Date.now``-style nondeterminism and no randomness.
"""
import argparse
import datetime
import json
import math
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import harvest_metrics as hm  # noqa: E402
import lint_heuristics as lh  # noqa: E402
import lint_scales as ls  # noqa: E402

SCHEMA = 1
ACTIONS = {"improve-now", "theme-note", "no-action"}

# LEARN-step priority: which firing the loop acts on first. Priority sorts on
# the EFFECTIVE action (post-downgrade), never the raw THEN.
ACTION_PRIORITY = {"improve-now": 0, "theme-note": 1, "no-action": 2}
CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2, "seed": 3}

# --- coarse-evidence downgrade (C1) -----------------------------------------
# A per-resource improve-now rule (H1, H7) must NOT drive an autonomous
# improve-now on evidence dominated by session-backfill rows. A backfill row
# inherited the SESSION's ANNOUNCE; it does NOT establish that the resource ran
# on that specific task, so it cannot support an autonomous, resource-attributed
# commit. When a firing's evidence is coarse-dominated OR too thin on precise
# (resources_source == "task") rows, the engine downgrades improve-now to
# theme-note. This is engine-authoritative: the SKILL acts on effective_action,
# so it cannot diverge from this rule.
MIN_PRECISE_FOR_IMPROVE = 3   # >= this many precise ("task") rows to auto-act
COARSE_DOMINANCE = 0.5        # coarse/total above this = coarse-dominated
# The per-resource improve-now rules subject to the downgrade. H4 is EXEMPT: it
# is a resource-GAP signal (not resource-attributed) and already routes its
# improve-now to an owner-gated candidate stub, never an autonomous commit.
DOWNGRADE_RULES = {"H1", "H7"}

# The rule ids the engine can actually evaluate — one per dispatch branch in
# ``evaluate_rule``. ``lint_heuristics`` imports this set to REFUSE an ACTIVE
# rule id with no evaluator (a self-added rule would otherwise commit clean then
# be silently skipped). Keep this in lockstep with ``evaluate_rule``.
EVALUABLE_RULES = {"H1", "H2", "H3", "H4", "H6", "H7", "H8"}

# Which rules read a per-resource window vs a global task window. H4 is
# session-scoped (bare-match streak, falls back to project-recent). H5 is
# PLANNED (parked in HEURISTICS.md's ## Planned section — no route-tier /
# task-shape signal in the metrics schema yet) and never reaches the engine.
PER_RESOURCE = {"H1", "H7", "H8"}
GLOBAL_TASK = {"H2", "H3", "H6"}
SESSION_RULES = {"H4"}

_OR_MORE = re.compile(r"(\d+)\s+or\s+more")
_CMP = re.compile(r"(>=|<=|>|<)\s*(\d+(?:\.\d+)?)")
_NUM = re.compile(r"(\d+(?:\.\d+)?)")
_LAST_N = re.compile(r"last\s+(\d+)")
_MIN_N = re.compile(r"min\s+(\d+)")


# --- timestamps -------------------------------------------------------------

def _now_iso():
    """Current UTC instant as an ISO-8601 string with a trailing Z (mirrors
    ``score_task._now_iso`` so learn records share the store's timestamp shape)."""
    return (datetime.datetime.now(datetime.timezone.utc)
            .isoformat().replace("+00:00", "Z"))


def _month_keys_now():
    """[previous-month, current-month] as YYYY-MM keys, oldest first."""
    now = datetime.datetime.now(datetime.timezone.utc)
    prev = (now.replace(day=1) - datetime.timedelta(days=1)).strftime("%Y-%m")
    return [prev, now.strftime("%Y-%m")]


# --- threshold + window parsing ---------------------------------------------

def parse_threshold(text):
    """Return ``(comparator, number)`` from a THRESHOLD field.

    A count rule ("3 or more …") returns ``(">=", 3.0)`` — the "or more" phrase
    is matched FIRST so a trailing ``> 0`` (as in "tests.failed > 0") never
    hijacks the count. Otherwise the first explicit comparator wins, then a bare
    number is treated as ``">"``.
    """
    m = _OR_MORE.search(text)
    if m:
        return (">=", float(m.group(1)))
    m = _CMP.search(text)
    if m:
        return (m.group(1), float(m.group(2)))
    m = _NUM.search(text)
    if m:
        return (">", float(m.group(1)))
    return (None, None)


def parse_window(text):
    """Return ``(window_size or None, explicit_min or None)`` from a WINDOW field.

    ``last N`` gives the window size; an optional ``(min M)`` gives an explicit
    minimum sample count.
    """
    w = _LAST_N.search(text)
    m = _MIN_N.search(text)
    return (int(w.group(1)) if w else None, int(m.group(1)) if m else None)


def _min_samples(window, explicit_min, count_threshold=None):
    """Per-rule minimum sample count, derived from the seed's prose.

    Priority: an explicit ``(min M)`` in the WINDOW wins; else, for a
    count/streak rule, the rule's own count threshold IS the floor (you need at
    least that many records to form the streak / reach the count); else half the
    window, rounded up, as a noise floor for a mean/ratio rule.
    """
    if explicit_min is not None:
        return explicit_min
    if count_threshold is not None:
        return int(count_threshold)
    if window:
        return int(math.ceil(window / 2.0))
    return 1


def _cmp(value, comparator, threshold):
    if comparator == ">":
        return value > threshold
    if comparator == "<":
        return value < threshold
    if comparator == ">=":
        return value >= threshold
    if comparator == "<=":
        return value <= threshold
    return False


# --- metrics store ----------------------------------------------------------

def _read_shard(path):
    records = []
    for raw in path.read_text(errors="replace").splitlines():
        if not raw.strip():
            continue
        try:
            records.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return records


def load_metrics(metrics_dir):
    """Return ``{kind: {task_id: record}}`` deduped to the LAST per (task_id, kind).

    The previous then current month shard is read in order, and within a shard
    the records are read in append order, so the final assignment for a
    ``(kind, task_id)`` is the newest record — the store's last-wins contract.
    """
    metrics_dir = pathlib.Path(metrics_dir)
    by_kind = {}
    for key in _month_keys_now():
        shard = metrics_dir / ("%s.jsonl" % key)
        if not shard.is_file():
            continue
        for rec in _read_shard(shard):
            kind, tid = rec.get("kind"), rec.get("task_id")
            if kind is None or tid is None:
                continue
            by_kind.setdefault(kind, {})[tid] = rec   # last-wins
    return by_kind


def _ts_key(rec):
    return rec.get("ts_end") or ""   # ISO-8601 …Z strings sort in time order


def _tasks_sorted(by_kind):
    return sorted(by_kind.get("task", {}).values(), key=_ts_key)


def _tasks_for_resource(tasks, resource):
    return [t for t in tasks if resource in (t.get("resources_deployed") or [])]


def _ev_row(rec, value):
    src = rec.get("resources_source", "unknown")
    return {"task_id": rec.get("task_id"), "value": value,
            "resources_source": src, "coarse": src == "session-backfill"}


def _coarse_count(records):
    return sum(1 for r in records
               if r.get("resources_source") == "session-backfill")


def _precise_count(records):
    """Rows whose resources_deployed was announced by the task itself
    (``resources_source == "task"``) — the only PRECISE per-task attribution.
    A ``session-backfill`` or an absent source is not precise."""
    return sum(1 for r in records if r.get("resources_source") == "task")


def _apply_downgrade(firing):
    """Set ``effective_action`` (+ ``downgrade_reason``) on a firing, in place.

    C1 — engine-authoritative coarse-evidence guard. For a per-resource
    improve-now rule (H1, H7), an autonomous improve-now is downgraded to
    theme-note when the firing's evidence is coarse-dominated
    (``coarse/total > COARSE_DOMINANCE``) OR too thin on precise rows
    (``precise < MIN_PRECISE_FOR_IMPROVE``). Every other firing — theme-note,
    no-action, and the EXEMPT H4 improve-now (a resource-GAP signal, already
    owner-gated) — passes through unchanged. The raw ``action`` is preserved so
    the reader can see what was downgraded and why.
    """
    action = firing["action"]
    firing["downgrade_reason"] = None
    if firing["rule"] in DOWNGRADE_RULES and action == "improve-now":
        precise = firing.get("precise_samples", 0)
        coarse = firing.get("coarse_samples", 0)
        total = len(firing.get("evidence") or []) or firing.get("samples", 0)
        if coarse > COARSE_DOMINANCE * max(1, total):
            firing["effective_action"] = "theme-note"
            firing["downgrade_reason"] = ("coarse-dominated: %d/%d backfill"
                                          % (coarse, total))
            return
        if precise < MIN_PRECISE_FOR_IMPROVE:
            firing["effective_action"] = "theme-note"
            firing["downgrade_reason"] = (
                "insufficient precise samples: %d<%d"
                % (precise, MIN_PRECISE_FOR_IMPROVE))
            return
    firing["effective_action"] = action


# --- rule evaluators (each returns a firing dict or None) -------------------

def _eval_mean(rule, population, metric, scope):
    """H1 (per-resource error_rate) and H6 (global cache_efficiency): a mean over
    the most recent window compared to the threshold.

    M1: records MISSING the metric are EXCLUDED (not coerced to 0) — so an
    absent ``cache_efficiency`` no longer drags H6's mean below its floor and
    spuriously fires.
    """
    comparator, threshold = parse_threshold(rule["fields"]["THRESHOLD"])
    window, explicit_min = parse_window(rule["fields"]["WINDOW"])
    present = [r for r in population if r.get(metric) is not None]
    win = present[-window:] if window else present
    need = _min_samples(window, explicit_min)
    if len(win) < need:
        return None
    vals = [float(r.get(metric)) for r in win]
    mean = sum(vals) / len(vals)
    if not _cmp(mean, comparator, threshold):
        return None
    return {
        "rule": rule["id"], "action": rule["then"], "scope": scope,
        "metric": metric, "computed": round(mean, 4),
        "comparator": comparator, "threshold": threshold,
        "samples": len(win), "window": window, "min_samples": need,
        "coarse_samples": _coarse_count(win), "precise_samples": _precise_count(win),
        "evidence": [_ev_row(r, round(float(r.get(metric)), 4)) for r in win],
    }


def _eval_interrupt(rule, tasks):
    """H2 interrupt-pressure (global): the share of recent tasks the user
    interrupted, over the window. M1: records MISSING ``interrupted`` are
    excluded from the ratio's denominator, not coerced to 0."""
    comparator, threshold = parse_threshold(rule["fields"]["THRESHOLD"])
    window, explicit_min = parse_window(rule["fields"]["WINDOW"])
    present = [r for r in tasks if r.get("interrupted") is not None]
    win = present[-window:] if window else present
    need = _min_samples(window, explicit_min)
    if len(win) < need:
        return None
    n_int = sum(1 for r in win if (r.get("interrupted") or 0) > 0)
    ratio = n_int / len(win)
    if not _cmp(ratio, comparator, threshold):
        return None
    return {
        "rule": rule["id"], "action": rule["then"], "scope": "global",
        "metric": "interrupted", "computed": round(ratio, 4),
        "comparator": comparator, "threshold": threshold,
        "samples": len(win), "window": window, "min_samples": need,
        "coarse_samples": _coarse_count(win), "precise_samples": _precise_count(win),
        "evidence": [_ev_row(r, r.get("interrupted", 0) or 0) for r in win],
    }


def _max_run(flags):
    """(longest run of True, index one-past the run's end) over a bool list."""
    best = run = end = 0
    for i, f in enumerate(flags):
        if f:
            run += 1
            if run > best:
                best, end = run, i + 1
        else:
            run = 0
    return best, end


def _eval_test_fail_streak(rule, tasks):
    """H3 test-fail-streak (global): a run of consecutive tasks with a failing
    test, within the window."""
    _cmp_op, count = parse_threshold(rule["fields"]["THRESHOLD"])
    window, explicit_min = parse_window(rule["fields"]["WINDOW"])
    win = tasks[-window:] if window else list(tasks)
    need = _min_samples(window, explicit_min, count_threshold=count)
    if len(win) < need:
        return None
    flags = [(r.get("tests") or {}).get("failed", 0) > 0 for r in win]
    run, end = _max_run(flags)
    if run < count:
        return None
    run_tasks = win[end - run:end]
    return {
        "rule": rule["id"], "action": rule["then"], "scope": "global",
        "metric": "tests.failed", "computed": run,
        "comparator": ">=", "threshold": int(count),
        "samples": len(win), "window": window, "min_samples": need,
        "coarse_samples": _coarse_count(run_tasks),
        "precise_samples": _precise_count(run_tasks),
        "evidence": [_ev_row(r, (r.get("tests") or {}).get("failed", 0))
                     for r in run_tasks],
    }


def _eval_rework_signal(rule, population, scores, scope):
    """H7 rework-signal (per-resource): scored tasks whose self-scored rework
    came back major, over the last N scored tasks that deployed the resource.

    ``population`` is the resource's own ``kind:"task"`` records, so each major
    evidence row IS the joined task record and carries its ``resources_source``
    directly — a score inherits its task's attribution (C1). A hypothetical
    score with no matching task record never enters this population, so it is
    coarse by omission. precise/coarse for the downgrade are computed over the
    ``majors`` — the specific tasks the improve-now would be predicated on.
    """
    _cmp_op, count = parse_threshold(rule["fields"]["THRESHOLD"])
    window, explicit_min = parse_window(rule["fields"]["WINDOW"])
    scored = [r for r in population if scores.get(r.get("task_id"))]
    win = scored[-window:] if window else scored
    need = _min_samples(window, explicit_min, count_threshold=count)
    if len(win) < need:
        return None
    majors = [r for r in win
              if (scores[r["task_id"]].get("scales") or {}).get("rework")
              == "major"]
    if len(majors) < count:
        return None
    return {
        "rule": rule["id"], "action": rule["then"], "scope": scope,
        "metric": "rework", "computed": len(majors),
        "comparator": ">=", "threshold": int(count),
        "samples": len(win), "window": window, "min_samples": need,
        "coarse_samples": _coarse_count(majors),
        "precise_samples": _precise_count(majors),
        "evidence": [_ev_row(r, "rework=major") for r in majors],
    }


def _eval_positive_streak(rule, population, scores, outcome_order, scope):
    """H8 positive-streak (per-resource): a long run of clean scored outcomes
    (outcome >= good AND rework = none) — fires no-action (positive signal)."""
    _cmp_op, count = parse_threshold(rule["fields"]["THRESHOLD"])
    window, explicit_min = parse_window(rule["fields"]["WINDOW"])
    win = population[-window:] if window else list(population)
    need = _min_samples(window, explicit_min, count_threshold=count)
    if len(win) < need:
        return None
    good_idx = outcome_order.index("good") if "good" in outcome_order else None

    def clean(rec):
        sc = scores.get(rec.get("task_id"))
        if not sc:
            return False
        scales = sc.get("scales") or {}
        outcome, rework = scales.get("outcome"), scales.get("rework")
        if good_idx is None or outcome not in outcome_order:
            return False
        return outcome_order.index(outcome) <= good_idx and rework == "none"

    flags = [clean(r) for r in win]
    run, end = _max_run(flags)
    if run < count:
        return None
    run_tasks = win[end - run:end]
    return {
        "rule": rule["id"], "action": rule["then"], "scope": scope,
        "metric": "outcome+rework", "computed": run,
        "comparator": ">=", "threshold": int(count),
        "samples": len(win), "window": window, "min_samples": need,
        "coarse_samples": _coarse_count(run_tasks),
        "precise_samples": _precise_count(run_tasks),
        "evidence": [_ev_row(r, "outcome>=good,rework=none") for r in run_tasks],
    }


def _eval_bare_streak(rule, records, project, session_id):
    """H4 bare-match-streak (session-scoped): repeated "proceeding bare"
    announcements — improve-now, but the LEARN step files a candidates/ stub
    rather than auto-creating (owner-gated, so EXEMPT from the C1 downgrade).

    When a ``session_id`` is supplied the streak is counted within that session
    only. Without one, it falls back to recent records for the task's project
    and annotates the firing "no session context — project-recent".
    """
    _cmp_op, count = parse_threshold(rule["fields"]["THRESHOLD"])
    if session_id is not None:
        bare = [r for r in records
                if r.get("bare") and r.get("session_id") == session_id]
        scope = "session=%s" % session_id
        note = None
    else:
        bare = [r for r in records if r.get("bare")
                and (project is None or r.get("project") == project)]
        scope = "project=%s" % (project or "*")
        note = "no session context — project-recent"
    if len(bare) < count:
        return None
    firing = {
        "rule": rule["id"], "action": rule["then"], "scope": scope,
        "metric": "bare", "computed": len(bare),
        "comparator": ">=", "threshold": int(count),
        "samples": len(bare), "window": None,
        "min_samples": int(count), "coarse_samples": 0, "precise_samples": 0,
        "evidence": [_ev_row(r, "proceeding-bare") for r in bare],
    }
    if note:
        firing["note"] = note
    return firing


class Ctx(object):
    def __init__(self, tasks, scores, all_records, outcome_order, resources,
                 project, session_id=None):
        self.tasks = tasks
        self.scores = scores
        self.all_records = all_records
        self.outcome_order = outcome_order
        self.resources = resources
        self.project = project
        self.session_id = session_id


def evaluate_rule(rule, ctx):
    """Return a list of firing dicts (0..n) for one active rule.

    A rule whose signal is unavailable, or that raises, is reported on stderr and
    skipped — the engine is advisory and never lets one rule abort the scan.
    """
    hid = rule["id"]
    out = []
    try:
        if hid == "H1":
            for res in ctx.resources:
                f = _eval_mean(rule, _tasks_for_resource(ctx.tasks, res),
                               "error_rate", "resource=%s" % res)
                if f:
                    out.append(f)
        elif hid == "H6":
            f = _eval_mean(rule, ctx.tasks, "cache_efficiency", "global")
            if f:
                out.append(f)
        elif hid == "H2":
            f = _eval_interrupt(rule, ctx.tasks)
            if f:
                out.append(f)
        elif hid == "H3":
            f = _eval_test_fail_streak(rule, ctx.tasks)
            if f:
                out.append(f)
        elif hid == "H7":
            for res in ctx.resources:
                f = _eval_rework_signal(rule, _tasks_for_resource(ctx.tasks, res),
                                        ctx.scores, "resource=%s" % res)
                if f:
                    out.append(f)
        elif hid == "H8":
            for res in ctx.resources:
                f = _eval_positive_streak(
                    rule, _tasks_for_resource(ctx.tasks, res), ctx.scores,
                    ctx.outcome_order, "resource=%s" % res)
                if f:
                    out.append(f)
        elif hid == "H4":
            f = _eval_bare_streak(rule, ctx.all_records, ctx.project,
                                  ctx.session_id)
            if f:
                out.append(f)
        else:
            # An ACTIVE rule with no evaluator is refused by lint_heuristics
            # before it can ever reach the engine (see EVALUABLE_RULES); this is
            # a defensive fallback for an unlinted rulebook only.
            sys.stderr.write("heuristics_eval: no evaluator for rule %s; "
                             "skipped\n" % hid)
    except Exception as exc:                       # advisory: never fatal
        sys.stderr.write("heuristics_eval: rule %s raised %r; skipped\n"
                         % (hid, exc))
    conf = lh._then_token(rule["fields"].get("CONFIDENCE", "")) or "seed"
    for f in out:
        f["confidence"] = conf
        _apply_downgrade(f)      # sets effective_action + downgrade_reason
    return out


def _hid_num(hid):
    m = re.search(r"\d+", hid)
    return int(m.group()) if m else 999


def _priority_key(f):
    # Priority sorts on the EFFECTIVE (post-downgrade) action, so a coarse
    # improve-now that was downgraded to theme-note no longer outranks a genuine
    # firing. Falls back to the raw action if a firing predates the downgrade.
    action = f.get("effective_action", f.get("action"))
    return (ACTION_PRIORITY.get(action, 9),
            CONFIDENCE_RANK.get(f.get("confidence", "seed"), 9),
            _hid_num(f["rule"]))


# --- scales -----------------------------------------------------------------

def _load_outcome_order(scales_file):
    try:
        scales = ls.parse_scales(pathlib.Path(scales_file))
    except OSError:
        scales = {}
    return scales.get("outcome", ["great", "good", "bad", "horrible"])


# --- context assembly + drivers ---------------------------------------------

def _task_context(by_kind, task_id):
    """Return ``(resources_deployed, project)`` for a --task-id, last-wins.

    A subagent's own record lives under kind ``task`` (``agent-<id>``); main
    thread work lives under kind ``session`` (``session-<sid>``); a score joins
    either. The first that carries the id supplies its resources + project.
    """
    for kind in ("task", "session", "score"):
        rec = by_kind.get(kind, {}).get(task_id)
        if rec is not None:
            return (rec.get("resources_deployed") or [], rec.get("project"))
    return ([], None)


def _all_resources(tasks):
    return sorted({res for t in tasks
                   for res in (t.get("resources_deployed") or [])})


def _evaluate(rules, ctx):
    firings = []
    for rule in rules:
        firings.extend(evaluate_rule(rule, ctx))
    firings.sort(key=_priority_key)
    return firings


def _render_text(firings):
    if not firings:
        print("heuristics_eval: no rules fired")
        return
    top = firings[0]
    print("heuristics_eval: %d rule(s) fired; recommended action: %s (%s)"
          % (len(firings), top["rule"], top["effective_action"]))
    for f in firings:
        marker = "  <- recommended" if f is top else ""
        down = ""
        if f.get("downgrade_reason"):
            down = ("  [downgraded from %s: %s]"
                    % (f["action"], f["downgrade_reason"]))
        print("")
        print("FIRING  %s (%s)  %s%s%s"
              % (f["rule"], f["effective_action"], f["scope"], down, marker))
        print("  computed: %s  threshold: %s %s  "
              "(samples %d, window %s, min %d, precise %d, coarse %d)"
              % (f["computed"], f["comparator"], f["threshold"], f["samples"],
                 f["window"], f["min_samples"], f.get("precise_samples", 0),
                 f["coarse_samples"]))
        if f.get("note"):
            print("  note: %s" % f["note"])
        print("  evidence:")
        for e in f["evidence"]:
            tag = "  [coarse: session-backfill]" if e["coarse"] else ""
            print("    %-26s value=%s  resources_source=%s%s"
                  % (e["task_id"], e["value"], e["resources_source"], tag))


def _render_json(firings, task_id):
    print(json.dumps({
        "task_id": task_id,
        "fired": len(firings),
        "recommended": firings[0]["rule"] if firings else None,
        "firings": firings,
    }, indent=2, sort_keys=True))


def _emit_learn(args):
    action = args.emit_learn
    if action not in ACTIONS:
        sys.stderr.write("heuristics_eval: --emit-learn action %r not in {%s}\n"
                         % (action, ", ".join(sorted(ACTIONS))))
        return 2
    if not args.task_id:
        sys.stderr.write("heuristics_eval: --emit-learn requires --task-id\n")
        return 2
    if not args.rule:
        sys.stderr.write("heuristics_eval: --emit-learn requires --rule <Hid>\n")
        return 2
    record = {
        "schema": SCHEMA, "kind": "learn", "task_id": args.task_id,
        "ts_end": _now_iso(), "action": action, "rule": args.rule,
    }
    hm._append_record(args.metrics_dir, record)
    print("heuristics_eval: recorded learn action %r for rule %s on task %s"
          % (action, args.rule, args.task_id))
    return 0


def _build_parser():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task-id", help="evaluate the rules relevant to one task")
    ap.add_argument("--window", action="store_true",
                    help="global scan: every resource + every global rule")
    ap.add_argument("--session-id",
                    help="scope the session-window rule (H4) to this session; "
                         "without it H4 falls back to recent project records")
    ap.add_argument("--metrics-dir",
                    default=str(pathlib.Path.home() / ".claude" / "metrics"))
    ap.add_argument("--heuristics-file",
                    default=str(pathlib.Path.home() / ".claude" / "learning"
                                / "HEURISTICS.md"))
    ap.add_argument("--scales-file",
                    default=str(pathlib.Path.home() / ".claude" / "learning"
                                / "SCALES.md"))
    ap.add_argument("--json", action="store_true",
                    help="emit machine-readable JSON instead of text")
    ap.add_argument("--emit-learn", metavar="ACTION",
                    help="append a kind:'learn' record (with --rule, --task-id)")
    ap.add_argument("--rule", metavar="Hid",
                    help="the firing rule id, for --emit-learn")
    return ap


def main(argv=None):
    args = _build_parser().parse_args(argv)

    if args.emit_learn:
        return _emit_learn(args)

    hpath = pathlib.Path(args.heuristics_file)
    if not hpath.is_file():
        sys.stderr.write("heuristics_eval: heuristics file not found: %s\n"
                         % hpath)
        return 2

    rules = [r for r in lh.parse_heuristics(hpath)
             if not r["retired"] and not r["planned"]]
    by_kind = load_metrics(args.metrics_dir)
    tasks = _tasks_sorted(by_kind)
    scores = by_kind.get("score", {})
    all_records = (list(by_kind.get("task", {}).values())
                   + list(by_kind.get("session", {}).values()))
    outcome_order = _load_outcome_order(args.scales_file)

    if args.task_id:
        resources, project = _task_context(by_kind, args.task_id)
        ctx = Ctx(tasks, scores, all_records, outcome_order, resources, project,
                  args.session_id)
        firings = _evaluate(rules, ctx)
        if args.json:
            _render_json(firings, args.task_id)
        else:
            _render_text(firings)
        return 0

    if args.window:
        ctx = Ctx(tasks, scores, all_records, outcome_order,
                  _all_resources(tasks), None, args.session_id)
        firings = _evaluate(rules, ctx)
        if args.json:
            _render_json(firings, None)
        else:
            _render_text(firings)
        return 0

    sys.stderr.write("heuristics_eval: one of --task-id or --window is "
                     "required\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
