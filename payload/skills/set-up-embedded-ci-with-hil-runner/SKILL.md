---
name: set-up-embedded-ci-with-hil-runner
description: Use when a firmware repository builds and unit-tests on a host machine but has no automated pass/fail signal from real hardware, when hardware regressions are only caught manually or in the field, or when a new peripheral driver or RTOS task needs its test wired into CI instead of run by hand. Covers flashing a target board from CI, capturing device output, and distinguishing what a simulator can cover from what genuinely needs hardware-in-the-loop (HIL) — BLE pairing, analog readings, interrupt timing under real bus contention.
---

# set-up-embedded-ci-with-hil-runner

## Overview
Sets up a CI pipeline that builds firmware, flashes it to a real target
board (or a simulator where one exists), and runs an automated pass/fail
test against the running device, so hardware regressions surface on every
commit instead of at bring-up or in the field. The one job it owns: give
firmware the same "green means safe to merge" guarantee application code
already has.

## When to use
- A firmware repository builds and unit-tests on a host machine but has no
  automated pass/fail signal from real hardware.
- Hardware regressions are only caught manually, late, or in the field.
- A new peripheral driver or RTOS task needs its test wired into CI rather
  than run by hand on a bench.
- BLE pairing, analog sensor readings, or interrupt-timing behavior cannot be
  faithfully covered by a host-side mock alone.

## Workflow
1. **Split the test suite into three tiers and route each to the cheapest
   runner that can actually catch its class of bug:**

   | Tier | Covers | Runs on |
   |---|---|---|
   | Host-side unit tests | Business logic, protocol parsing, mocked bus interfaces | Every commit, standard CI runner, no hardware |
   | Simulator/emulator tests | Behavior the target has a faithful emulator for | Every commit if fast enough |
   | Hardware-in-the-loop (HIL) | Analog readings, RF/BLE pairing, real bus-contention timing, power behavior | Dedicated hardware runner |

2. **Provision the HIL runner as a persistent, addressable CI agent**
   physically wired to the target board(s): power control (so CI can
   hard-reset a hung board), a flashing interface (an SWD/JTAG debug probe or
   a bootloader-based flasher), and a way to observe output (serial/UART
   capture, or a test-point wired to a logic analyzer or DAQ the runner can
   read).
3. **Make every HIL job idempotent and self-recovering.** A representative
   job shape:
   ```yaml
   hil-test:
     steps:
       - power-cycle: target
       - flash: firmware.bin
       - verify-flash: checksum
       - run-test: hil_suite --timeout 120s
       - on-timeout: power-cycle && mark-failed
       - collect-artifacts: [serial.log, checksum.txt, results.xml]
   ```
   Power-cycle before flashing, verify the flash succeeded (read-back or
   checksum) before running the test, and set a hard timeout with automatic
   power-cycle on hang so one wedged board does not stall the queue.
4. **Model the runner pool per-target** when more than one board or board
   revision needs coverage — jobs should queue per-target, not round-robin
   across boards that are not interchangeable. A test written for one board
   revision silently passing on a queue that happened to pick a different
   revision is a common false-confidence bug.
5. **Keep HIL jobs fast enough to run on every pull request** if at all
   possible. If the full suite is too slow, run a fast smoke subset per pull
   request and the full suite on a schedule or pre-release gate — but make
   that schedule/gate blocking, not advisory, or it quietly stops being run.
6. **Archive artifacts from every HIL run** (serial log, flash checksum,
   pass/fail per test case) so a flaky failure can be diagnosed from CI
   history instead of requiring someone to reproduce it live on the bench.

**Gotcha:** shared lab hardware drifts from what ships. Track the firmware
and hardware revision of every runner board explicitly, and re-provision or
retire boards that fall out of sync with the current production revision.

**Gotcha:** HIL runners are a common source of "works in CI, fails on the
bench" and the reverse, because of subtle wiring or power differences. Treat
the runner's own hardware setup — wiring diagram, board revision, probe
firmware version — as configuration worth version-controlling next to the
pipeline definition, not tribal knowledge.

## Checklist / quality gate
- Tests are explicitly tiered (host unit → simulator → HIL), and each test
  lives in the cheapest tier that can actually catch its class of bug.
- The HIL runner can power-cycle the target, flash it, verify the flash, and
  capture output programmatically — no manual step in the loop.
- Jobs queue per-target when more than one board variant exists.
- A hung board times out and power-cycles automatically rather than stalling
  the pipeline.
- HIL runs produce archived, per-run artifacts (log, checksum, pass/fail) for
  later diagnosis.
- The runner's own hardware configuration (wiring, board revision, probe
  firmware) is version-controlled, not tribal knowledge.
- The full HIL suite runs on a blocking gate (per pull request or
  pre-release), not merely on request.

## References
- Embedded DevOps: CI/CD, automated tests and firmware deployment — AESTECHNO — https://www.aestechno.com/en/embedded-devops-cicd-automated-tests/
- Embedded Integration Testing — Parasoft — https://www.parasoft.com/blog/embedded-integration-testing/

## Composition
Runs the HIL test cases produced by `write-peripheral-driver-with-hil-test`
and exercises the task-level behavior designed by `design-rtos-task-and-ipc`.
Gates the pipeline with `run-misra-static-analysis-triage` ahead of the
flash-and-test stage. Generalizes the cross-cutting
`ci-pipeline-authoring` pattern to hardware targets, and can run
`design-ota-bootloader-update-flow`'s flash-and-verify step as its own HIL
test case.
