---
name: design-rtos-task-and-ipc
description: Use when adding a new concurrent task, thread, or feature to an RTOS application (FreeRTOS, Zephyr, QNX, ThreadX) and deciding its priority, stack size, and how it talks to the rest of the system. Triggers include an unmeasured task stack, a watchdog reset with no clear owner, a shared resource touched from two tasks without a lock, priority-inversion symptoms, or a system that occasionally deadlocks or misses a deadline under load.
---

# design-rtos-task-and-ipc

## Overview
Sizes and wires a new RTOS task — priority, stack, and the inter-process
communication primitive it uses to talk to the rest of the system — so the
addition does not introduce priority inversion, stack overflow, or a missed
watchdog check-in. The one job it owns: turn "we need a task for this" into
a justified, documented set of concurrency choices.

## When to use
- A new feature needs its own concurrent task (or its own state machine
  sharing an existing task) in a FreeRTOS, Zephyr, QNX, or ThreadX
  application.
- Two tasks need to exchange data or signal each other and it is unclear
  whether to reach for a queue, semaphore, mutex, or event group.
- Symptoms: an unmeasured task stack, a watchdog reset with no clear owner, a
  shared resource accessed from two tasks without a lock, or a system that
  usually works but occasionally deadlocks or misses a deadline under load.

## Workflow
1. **Classify the task by timing requirement** — hard real-time (a missed
   deadline breaks the system), soft real-time (a miss degrades but does not
   break it), or best-effort/background.
2. **Assign priority by that classification**, not by verbal "importance."
   Prefer a few coarse priority bands over many closely spaced ones —
   closely spaced priorities are a common source of unintended priority
   inversion. Reserve the highest bands for interrupt-adjacent, time-critical
   work, and keep that work short-running.
3. **Choose the IPC primitive by interaction shape**, not habit:

   | Interaction shape | Primitive |
   |---|---|
   | Producer/consumer data handoff | Queue |
   | One-shot signal (ISR-to-task or task-to-task) | Binary semaphore, or a direct task notification where the RTOS supports one (cheaper) |
   | Counting resource availability | Counting semaphore |
   | Multiple independent conditions a task waits on | Event group / flags |
   | Protecting a shared resource | Mutex with priority inheritance enabled |

4. **Size the stack from measurement, not a guess.** Fill the stack with a
   known pattern at startup, measure the high-water mark under worst-case
   call depth — including any logging/printf paths, a common stack-size
   surprise — then add headroom (a common rule of thumb is 20-30%).
5. **Define failure containment.** Decide what happens if the task starves,
   crashes, or its queue fills, and wire that into the watchdog strategy:
   does the task need to check in, and what is the recovery action (task
   restart, system reset, degrade-and-continue) if it does not?
6. **Document the choices at the point of use** — priority, stack size, and
   IPC rationale belong as a comment next to the task-creation call, not in a
   separate document that will drift out of sync.

**Gotcha — unbounded queues and dynamic allocation inside tasks** are a
common latent bug in RTOS code. Prefer fixed-size, statically allocated
queues and pools sized for the worst case, so an out-of-memory condition is
caught at build/link time instead of in the field.

**Gotcha — priority inversion.** A low-priority task holding a mutex a
high-priority task needs, while a medium-priority task preempts the
low-priority holder, is priority inversion. The standard fix is priority
inheritance on the mutex, and it must be enabled explicitly on some RTOS
ports — it is not always the default.

## Checklist / quality gate
- Task priority is justified by real-time classification, not by verbal
  "importance."
- Stack size is derived from a measured high-water mark plus headroom, not
  guessed.
- Every shared resource has an explicit lock (mutex with priority
  inheritance) or is single-owner by design.
- IPC choice matches the interaction shape and is documented at the point of
  use.
- Queues and memory pools are statically sized; no unbounded dynamic
  allocation inside a task.
- The task's watchdog/failure-containment behavior is explicit, not implicit.

## References
- Senior Embedded Firmware Engineer (RTOS) job description template — https://www.expertia.ai/blogs/jd/sr-embedded-firmware-engineer-rtos-job-description-65341j
- Embedded Systems Roadmap — https://www.scaler.com/blog/the-embedded-systems-roadmap/

## Composition
Frequently owns a driver produced by `write-peripheral-driver-with-hil-test`.
Feeds `run-misra-static-analysis-triage`, whose rule sets flag the same
unbounded-recursion/dynamic-allocation risks this skill guards against in
step 4. An update task inside `design-ota-bootloader-update-flow` has its own
priority/IPC constraints and should be sized with this skill. Logging calls
from inside a task are a common stack-size surprise — cross-check against
`add-structured-logging-and-tracing`.
