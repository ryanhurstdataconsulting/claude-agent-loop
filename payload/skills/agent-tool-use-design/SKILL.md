---
name: agent-tool-use-design
description: Use when a task asks to design an agent that calls tools, functions, or external APIs autonomously — "give the assistant a tool to look up orders," "build an agent that can query our database and send emails," or "the agent keeps calling the wrong tool" / "the agent got stuck in a loop." Covers tool-schema design, guardrails against unsafe or runaway tool calls, observability/tracing setup, and enumerating failure modes like infinite loops and wrong-tool selection.
---

# agent-tool-use-design

## Overview
Designs the tool layer an LLM agent operates through — schema definitions,
selection guardrails, execution safety, and observability — so the agent
reliably picks the right tool, uses it safely, and fails visibly instead
of silently or catastrophically. Owns the tool-use contract, distinct from
the agent's underlying prompt/reasoning strategy or the retrieval layer
(rag-pipeline-scaffolding) it might call as one of several tools.

## When to use
- A task asks to add a new callable tool/function to an existing agent, or
  to design a tool set for a new agent from scratch.
- An agent is choosing the wrong tool for a given request, or repeatedly
  fails to call a tool it should.
- An agent enters a loop — calling the same tool repeatedly without making
  progress, or alternating between two tools without resolving.
- A tool call needs a safety review before it's allowed to take a
  consequential or irreversible action (a write, a payment, an email send,
  a deletion).
- A task asks to add tracing/observability so tool calls can be debugged
  after the fact.

## Workflow

1. **Design each tool schema for unambiguous selection, not just
   functional coverage.** An agent picks between tools primarily by
   matching the request against each tool's name and description — a
   vague or overlapping description is the single most common cause of
   wrong-tool selection.
   - Name the tool for what it does, not how it's implemented
     (`search_orders_by_customer`, not `run_query`).
   - Write the description as the deciding factor between this tool and
     any tool it could be confused with — state explicitly what it does
     *not* do if a near-duplicate tool exists.
   - Keep the parameter schema minimal and typed; every optional
     parameter is a place the model can guess wrong. Use enums over free
     text wherever the valid values are a known, finite set.
   - Return structured, parseable results — a tool that returns a wall of
     unstructured text forces the agent to re-parse it on every
     subsequent turn, wasting context and inviting misreads.

2. **Classify every tool by consequence before deciding how much
   autonomy to grant it:**

   | Tool consequence | Example | Autonomy level |
   |---|---|---|
   | Read-only, reversible | Look up a record, search, query a report | Full autonomy — no confirmation needed |
   | Write, reversible | Update a draft, add a note, change a non-final status | Autonomous with logging; reviewable/undoable after the fact |
   | Write, hard to reverse | Send an email, charge a payment, delete a record, execute DDL | Require explicit confirmation (human-in-the-loop) before execution, or gate behind a separate approval step |
   | External side effect outside the system | Post to a third-party service, trigger a webhook to an external party | Treat as irreversible by default unless proven otherwise; require confirmation |

   Never grant an irreversible-action tool the same autonomy as a
   read-only one just because both are exposed through the same agent —
   the schema should make the consequence class visible to whoever is
   reviewing the tool set, and the agent's execution layer should enforce
   it, not just document it.

3. **Guard against the standard failure modes explicitly, don't assume
   the model will avoid them on its own:**
   - **Infinite/repeated-call loops.** Cap the number of tool calls per
     turn or per task, and detect a call repeated with identical
     arguments as a stop condition, not a retry signal.
   - **Wrong-tool selection.** Covered primarily by schema design (step
     1); as a backstop, log every tool selection with the request that
     triggered it so misselection patterns are visible in review, not
     just in a one-off bug report.
   - **Silent partial failure.** A tool that fails should return a
     structured error the agent can act on (retry, choose a different
     tool, or surface the failure to the user) — never fail silently in a
     way that lets the agent proceed as if the call succeeded.
   - **Argument hallucination.** Validate tool-call arguments against the
     schema before execution (type, enum membership, required fields);
     reject and return a clear error rather than executing with an
     invalid or fabricated argument.
   - **Excessive or unbounded tool chaining.** Set a maximum reasoning/
     tool-call budget per task and design the agent to fail gracefully
     ("I couldn't complete this within the available steps") rather than
     running until an external timeout kills it.

4. **Instrument tracing before shipping, not after the first hard-to-
   reproduce bug.** Log, per tool call: the triggering request/context,
   the tool selected, the arguments passed, the raw result, and the
   latency. This is what turns "the agent got stuck" from an
   unreproducible complaint into a traceable sequence of tool calls that
   can be replayed and fixed.

5. **Test tool selection and safety behavior with adversarial and
   ambiguous cases, not just the happy path.** Include cases in the
   agent's eval suite (hand off to eval-harness) that specifically probe:
   a request that could plausibly match two different tools, a request
   that should trigger an irreversible-action tool and therefore should
   require confirmation, and a request designed to push the agent toward
   an excessive number of tool calls.

## Checklist / quality gate
- [ ] Every tool's name and description are unambiguous against any
      tool it could be confused with, and parameters use enums/typed
      fields over free text wherever possible.
- [ ] Every tool is classified by consequence (read-only, reversible
      write, irreversible write, external side effect), and autonomy
      level matches that classification.
- [ ] A per-task or per-turn cap on tool-call count exists, with repeated
      identical calls treated as a stop condition, not a retry.
- [ ] Tool-call arguments are validated against the schema before
      execution, with a structured error path for invalid arguments.
- [ ] Tracing captures the triggering context, tool selected, arguments,
      result, and latency for every call.
- [ ] The eval suite includes ambiguous and adversarial cases probing
      tool selection and irreversible-action confirmation, not only
      happy-path requests.

## References
- Agent/tool-use design and observability are documented as core
  competencies in current GenAI application-engineering role profiles,
  alongside RAG, fine-tuning, and evaluation/safety.
- Structured tool/function-calling schemas and their role in agent
  reliability are documented in major LLM provider tool-use guides.

## Composition
- Hands off to **eval-harness** to build the adversarial and ambiguous
  test cases from step 5 into a repeatable, CI-gated suite.
- Calls **rag-pipeline-scaffolding** when retrieval is exposed to the
  agent as one of its callable tools rather than a fixed pipeline step —
  the retrieval tool still needs a schema, consequence classification,
  and tracing like any other tool.
- Pairs with **observability-instrumentation** for the tracing
  infrastructure underlying step 4, if general request tracing doesn't
  already exist in the system.
- Feeds **llm-cost-latency-optimization** when tool-call chaining or an
  unbounded tool budget is itself the cost/latency driver.
