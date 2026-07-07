---
name: streaming-pipeline-scaffolding
description: Use when building a Kafka/Kinesis producer-consumer pair, a change-data-capture (CDC) pipeline, or any event-streaming feature — new topic/stream definitions, schema-registry wiring, or a request to "stream this table into the pipeline" or "consume from this topic." Triggers on consumer-lag alerts, dead-letter-queue design questions, exactly-once vs. at-least-once delivery decisions, and schema-compatibility errors from a registry.
---

# streaming-pipeline-scaffolding

## Overview
Scaffolds a producer/consumer pair or CDC pipeline on a streaming platform
(Kafka, Kinesis, or an equivalent), with schema-registry wiring, an explicit
delivery-guarantee decision, and dead-letter handling. Owns the streaming
data-motion layer — not the batch orchestration that `airflow-dag-authoring`
covers, and not the downstream feature-serving layer that a feature-store
skill would own.

## When to use
- A task asks to build a Kafka or Kinesis producer, consumer, or
  producer-consumer pair.
- A task asks to set up change-data-capture (CDC) from a source database
  into a stream.
- A consumer is falling behind (growing lag) or a producer is failing to
  publish.
- A schema-registry compatibility error is blocking a deploy.
- A task needs a decision on message delivery guarantees, windowing, or
  dead-letter handling for a stream.

## Workflow

1. **Decide the delivery guarantee before writing the consumer.** This is
   the single decision that shapes everything downstream:
   - **At-least-once** (default, simplest) — the consumer may see a
     message more than once after a rebalance or retry. Only safe if
     downstream processing is idempotent (same key → same effect,
     regardless of duplicate delivery).
   - **Exactly-once** — requires transactional producers/consumers (Kafka
     transactions, or Kinesis with idempotent writes downstream) and adds
     real throughput and complexity cost. Reach for it only when the
     downstream sink genuinely cannot tolerate duplicates and cannot be
     made idempotent cheaply (e.g., a non-idempotent external payment
     call) — not as a default.
   - **At-most-once** — rarely correct for data pipelines; only appropriate
     when losing a message is cheaper than the cost of possibly
     duplicating it (some metrics/logging use cases).

   In practice: prefer at-least-once delivery **plus an idempotent
   consumer** (upsert-by-key, dedupe-by-message-id) over building
   exactly-once machinery — it is simpler, cheaper, and covers the same
   correctness need for most pipelines.

2. **Wire the schema registry before the first message flows.** Producers
   and consumers must agree on message shape:
   - Register the schema (Avro/Protobuf/JSON Schema) before deploying the
     producer.
   - Set a compatibility mode on the subject —
     `BACKWARD` (new schema can read old data, the common default for
     evolving consumers safely) vs. `FORWARD` vs. `FULL` — deliberately,
     not left at whatever the registry's global default is.
   - Never let a producer publish an unregistered ad hoc schema change
     directly to production; a compatibility break there fails silently at
     every consumer, not loudly at the producer.

3. **Design the dead-letter queue (DLQ) pattern up front, not after the
   first poison-pill message:**
   - A message that fails deserialization or fails processing after N
     retries goes to a DLQ topic/stream, tagged with the failure reason
     and original offset — never silently dropped, never left to block
     the partition indefinitely.
   - Alert on DLQ volume, not just on consumer lag — a DLQ quietly filling
     up is a data-loss risk that lag metrics alone won't surface.
   - Decide the replay path for DLQ messages (manual review + reprocess,
     or an automated retry-with-backoff) before the DLQ has its first
     real entry.

4. **Choose the windowing strategy only if the pipeline aggregates over
   time** (stream processing, not plain pass-through):
   - **Tumbling windows** — fixed, non-overlapping intervals; simplest,
     good for periodic rollups.
   - **Sliding windows** — overlapping intervals; use when a moving
     aggregate (e.g., "events in the last 5 minutes, updated every
     minute") is the actual requirement.
   - **Session windows** — gap-based, groups events by inactivity gaps;
     use for user-session-shaped data.
   - Always set an explicit **watermark / allowed lateness** — late-arriving
     events are the normal case in streaming, not the exception, and an
     unset watermark either drops legitimate late data or lets the window
     never close.

5. **For CDC specifically:**
   - Confirm the source database has the CDC mechanism the plan assumes
     (logical replication slot, binlog access, or a change-tracking table)
     and confirm read-only/no-DDL constraints on the source, if any, are
     respected — CDC setup often requires a one-time DDL grant that a
     read-only engagement should flag rather than silently perform.
   - Handle the initial snapshot (full table load) and the ongoing change
     stream as two explicit phases; a pipeline that only wires the change
     stream will miss every row that existed before it started.
   - Decide how deletes are represented downstream (tombstone message vs.
     soft-delete flag) before the first delete happens in production.

6. **Consumer implementation checklist:**
   - Commit offsets only after successful processing (or use exactly-once
     transactional commits) — never commit-then-process, which loses
     messages on a crash between the two.
   - Set `max.poll.interval.ms`/equivalent generously enough that
     legitimate processing time doesn't trigger a false rebalance.
   - Log or emit a metric per consumer-group per partition for lag, so lag
     growth is visible before it becomes an incident.

## Checklist / quality gate
- [ ] The delivery guarantee (at-least-once + idempotent consumer, by
      default) is chosen explicitly and matches what the downstream sink
      can tolerate.
- [ ] Schema is registered with an explicit compatibility mode before the
      producer ships.
- [ ] A dead-letter path exists, is alerted on by volume, and has a defined
      replay process.
- [ ] If the pipeline aggregates over time, the windowing type and
      watermark/lateness policy are both explicit, not left at a library
      default.
- [ ] For CDC: the initial-snapshot phase and the ongoing-change-stream
      phase are both handled, and delete representation is decided.
- [ ] Consumer offset commits happen after successful processing, not
      before.
- [ ] Consumer lag is observable (metric or log) per partition.

## References
- Apache Kafka documentation — delivery semantics and transactions:
  https://kafka.apache.org/documentation/#semantics
- Confluent Schema Registry — compatibility modes:
  https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html
- Amazon Kinesis Data Streams developer guide:
  https://docs.aws.amazon.com/streams/latest/dev/introduction.html
- Debezium — change-data-capture concepts:
  https://debezium.io/documentation/reference/stable/architecture.html

## Composition
- Hands off to **data-quality-check-suite** for freshness and completeness
  checks on the stream's downstream sink (a warehouse table or lakehouse
  path fed by the pipeline).
- Pairs with **idempotent-backfill-authoring** for the CDC initial-snapshot
  phase, which is itself a large historical backfill.
- Complements **airflow-dag-authoring** in hybrid pipelines where a
  streaming ingest layer feeds a batch-orchestrated transformation layer
  downstream.
