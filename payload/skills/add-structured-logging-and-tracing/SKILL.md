---
name: add-structured-logging-and-tracing
description: Use when a service has an observability gap — no structured logs, no distributed tracing across service calls, or a postmortem action item calling for better visibility into a failure. Walks through OpenTelemetry instrumentation, consistent log-field conventions, and correlation/trace-ID propagation across service boundaries, rather than ad-hoc print statements or unstructured text logs. Also triggers on "we couldn't tell what happened during the incident," "add tracing to this request path," a log line with no request or user context, or "why can't we correlate logs across these two services."
---

# add-structured-logging-and-tracing

## Overview
Instruments a service with structured logs, metrics, and distributed traces
using consistent field conventions and propagated correlation IDs, so a
failure can be reconstructed after the fact instead of guessed at from
scattered, unstructured print statements. The one job it owns: any request
that touches multiple log lines or multiple services can be reassembled from
one identifier.

## When to use
- A service logs unstructured text (`print`/`console.log`-style strings)
  instead of structured, machine-parseable fields.
- A postmortem action item calls for better visibility into what happened
  during an incident.
- Requests span multiple services and there's no way to correlate their logs
  or traces to a single originating request.
- A new critical code path (payment, auth, a background job) is being added
  with no logging or tracing plan yet.
- Debugging currently requires SSHing into a box to `grep` a log file rather
  than querying a central log/trace store.

## Workflow
1. **Separate the three signal types and use each for what it's good at**
   rather than reaching for logs for everything:
   - **Logs** — discrete events with context ("order 4821 failed payment
     capture: card declined"). Best for understanding *what* happened at a
     specific point.
   - **Metrics** — aggregated numeric time series (request rate, error rate,
     p99 latency). Best for *is something wrong right now*, and for
     dashboards/alerts — not for reconstructing a single request's story.
   - **Traces** — the causal chain of spans across a single request as it
     crosses functions and services. Best for *where* time went and *which*
     downstream call failed.
   All three should share the same correlation ID so an alert (metric) leads
   to a trace, and a trace leads to the specific log lines for that request.
2. **Adopt OpenTelemetry (or an equivalent vendor-neutral standard) rather
   than a proprietary SDK directly**, so the instrumentation isn't locked to
   one backend. Instrument at the framework boundary first (HTTP
   server/client, database driver, message-queue client) — most frameworks
   have an auto-instrumentation package that covers this in one step —
   then add manual spans only around business logic that auto-instrumentation
   can't see.
3. **Log in structured fields, not formatted strings.** Every log line
   should be an object/map (JSON in most stacks), not
   `f"user {id} did {action}"`. At minimum, standardize on:
   - `timestamp` (ISO 8601, UTC)
   - `level` (`debug`/`info`/`warn`/`error`, used consistently — `error`
     means something needs human attention, not just "an exception was
     caught and handled")
   - `service` / `component`
   - `trace_id` / `span_id` (from the active trace context)
   - `message` (human-readable, but the *fields* — not this string — are
     what gets queried)
   - Request-scoped context: `request_id`, `user_id` (or tenant ID),
     `route`/`operation`
4. **Propagate a correlation/trace ID across every service boundary.** Accept
   an incoming trace context header (W3C `traceparent` is the interoperable
   default) if present, generate one if absent, and forward it on every
   outbound call — HTTP headers, message-queue message attributes, and job
   payloads for anything processed asynchronously. A request that loses its
   trace ID crossing into a background job is the most common gap in an
   otherwise well-instrumented system.
5. **Never log a secret, credential, token, or unredacted PII field.** Build
   this into the logging setup itself (a field-denylist or automatic
   redaction on known-sensitive field names) rather than relying on every
   call site to remember.
6. **Sample traces, not logs, when volume is a cost concern.** Head-based or
   tail-based trace sampling keeps trace volume manageable while still
   capturing the traces that matter (errors, slow requests) — but keep error
   and warning-level logs unsampled; the moment something needs
   investigation is exactly when a missing log line hurts most.
7. **Wire alerts to metrics, not to log volume.** An alert threshold on "more
   than N error-level logs per minute" is a reasonable start; a mature setup
   defines an SLO and alerts on error-budget burn rate instead.

## Checklist / quality gate
- [ ] Logs are structured (key-value/JSON), not formatted free-text strings.
- [ ] Every log line and span carries a `trace_id` (or equivalent
      correlation ID) that survives a request crossing a service boundary,
      including async/queue boundaries.
- [ ] `error`-level logs are reserved for conditions that actually need
      human attention, not routine handled exceptions.
- [ ] No secret, credential, token, or unredacted PII field appears in any
      log or span attribute.
- [ ] Auto-instrumentation covers the framework's HTTP/database/queue
      boundaries; manual spans exist around business-critical logic those
      can't see.
- [ ] A trace for a representative request can be pulled up and shows every
      service it touched, in order, with timing.
- [ ] Log/trace volume and cost are sane at current traffic (sampling
      configured if not).

## References
- [OpenTelemetry documentation](https://opentelemetry.io/docs/)
- [W3C Trace Context specification](https://www.w3.org/TR/trace-context/)
- [The Twelve-Factor App — XI. Logs](https://12factor.net/logs)

## Composition
A natural follow-on to an incident postmortem skill's action items, and a
prerequisite most other backend skills in this family assume is already in
place — `add-caching-layer` needs a hit/miss metric to land somewhere, and
`containerize-service-for-deployment`'s health-check endpoint is more useful
once its failures are traceable. Pairs with a runbook-authoring skill: a
runbook is only as good as the traces and logs it tells the responder to
pull up.
