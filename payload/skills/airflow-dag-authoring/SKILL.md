---
name: airflow-dag-authoring
description: Use when building or modifying a scheduled data pipeline, DAG, or Airflow task graph — new DAG files, `dag_id` definitions, sensors, operators, retry/SLA configuration, or a request to "backfill this DAG" or "add a task to the pipeline." Triggers on Airflow scheduler errors, DAG import failures, task-instance retry storms, and requests to make a pipeline safe to rerun.
---

# airflow-dag-authoring

## Overview
Scaffolds a production-ready Apache Airflow DAG: idempotent tasks, correctly
configured retries and SLAs, and a task graph that is safe to backfill and
safe to rerun. Owns the "turn a pipeline requirement into a deployable DAG"
job — not general Python ETL logic, which lives in the task callables
themselves.

## When to use
- A task asks to create a new scheduled pipeline, DAG, or task graph.
- A task asks to add, remove, or reorder tasks in an existing DAG.
- A DAG needs retry policy, SLA, timeout, or alerting configuration added.
- A DAG import is failing, a task is stuck in retry loops, or a backfill run
  is producing duplicate or inconsistent output.
- A request explicitly mentions "backfill this DAG," "make this pipeline
  idempotent," or "add a sensor/dependency" between pipelines.

## Workflow

1. **Clarify the schedule and trigger semantics first.** Get the
   `schedule_interval`/`schedule` (cron string or dataset-driven), the
   `start_date`, and whether `catchup` should be `True` (historical
   backfill needed) or `False` (only run going forward). A wrong `catchup`
   default is the single most common DAG-authoring mistake — Airflow
   defaults to `True`, which silently fires every missed interval since
   `start_date` the moment the DAG is unpaused.

2. **Design tasks to be idempotent before writing any operator.** Every task
   must produce the same result no matter how many times it runs for the
   same `data_interval`/execution date:
   - Prefer `INSERT ... ON CONFLICT` / `MERGE` / partition-overwrite over
     naive `INSERT` or `INSERT INTO ... SELECT`.
   - Write to a partition or file path keyed by the logical date
     (`{{ ds }}`), and overwrite that partition wholesale rather than
     appending.
   - Never rely on wall-clock `now()` inside a task — use the DAG's
     logical/data interval (`{{ data_interval_start }}` /
     `{{ data_interval_end }}`) so a rerun three days later still produces
     the value that date would have produced.

3. **Pick the operator/sensor pattern:**
   - External dependency exists already → `ExternalTaskSensor` or a
     dataset-aware schedule (`Dataset` triggers), not a bare time delay.
   - Waiting on an external file/API/table → deferrable sensor
     (`mode="reschedule"` or a deferrable operator) so the worker slot is
     freed while waiting, not `mode="poke"` holding a slot for hours.
   - Heavy compute → push to an external executor (Kubernetes Pod
     Operator, a Spark submit operator, a dbt Cloud/CLI operator) rather
     than running the workload inside the Airflow worker process.

4. **Set retries, timeouts, and SLAs deliberately, not from a copy-pasted
   default:**
   ```python
   default_args = {
       "retries": 3,
       "retry_delay": timedelta(minutes=5),
       "retry_exponential_backoff": True,
       "execution_timeout": timedelta(minutes=30),
   }
   ```
   Set `sla` per task (or DAG-level `dagrun_timeout`) only where a missed
   SLA is actionable — an SLA with no on-call response is noise.

5. **Wire failure notification** (`on_failure_callback`, an SLA-miss
   callback, or a dedicated alerting task) so a silent failure is never the
   only failure mode. Route it to whatever the project's existing alert
   channel is — do not invent a new one.

6. **Test locally before deploying:**
   - `airflow dags list-import-errors` — catches syntax and import errors
     before the scheduler ever sees the file.
   - `airflow tasks test <dag_id> <task_id> <date>` — runs a single task in
     isolation without touching the scheduler or metadata database state
     for other tasks.
   - `airflow dags test <dag_id> <date>` — runs the full DAG for one
     logical date synchronously, good for catching cross-task dependency
     bugs.
   - For a change to an existing DAG, dry-run a backfill window
     (`airflow dags backfill -s <start> -e <end> --dry-run`) before running
     it for real.

7. **Confirm backfill safety explicitly.** If `catchup=True` or a manual
   backfill is expected, verify: tasks are idempotent (step 2), no task
   assumes it is the only run in flight (`max_active_runs` set
   appropriately), and no task has a hidden dependency on wall-clock
   ordering across dates.

## Checklist / quality gate
- [ ] `catchup` is set deliberately (not left at the implicit default).
- [ ] Every task is idempotent for a given logical date — reruns don't
      duplicate or corrupt output.
- [ ] No task uses `now()`/wall-clock time where the logical/data interval
      should be used instead.
- [ ] Retries, `retry_delay`, and `execution_timeout` are set per task, not
      omitted.
- [ ] Long-poll waits use a deferrable/reschedule sensor, not a
      worker-blocking poke.
- [ ] `airflow dags list-import-errors` is clean and
      `airflow tasks test`/`airflow dags test` were run for at least one
      logical date.
- [ ] A failure notification path exists and points at a real, monitored
      channel.
- [ ] If backfill is in scope, a dry-run backfill was performed for the
      target date range.

## References
- Apache Airflow documentation — DAGs, scheduling, and catchup:
  https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dags.html
- Apache Airflow — testing DAGs and tasks:
  https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/testing.html
- Apache Airflow — sensors and deferrable operators:
  https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/deferring.html
- Apache Airflow — backfill and catchup semantics:
  https://airflow.apache.org/docs/apache-airflow/stable/dag-run.html

## Composition
- Hands off to **idempotent-backfill-authoring** for the deep batch-sizing,
  UPSERT, and checkpointing design when a backfill spans a large date range
  or high row volume.
- Pairs with **data-quality-check-suite** to add validation tasks at the
  end of the DAG before downstream consumers read the output.
- Pairs with **ci-pipeline-authoring** when the DAG file itself needs a
  lint/import-error check wired into pull-request CI.
