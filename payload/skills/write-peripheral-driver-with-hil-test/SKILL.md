---
name: write-peripheral-driver-with-hil-test
description: Use when a new sensor, radio, or peripheral IC needs a driver over SPI/I2C/UART/CAN/1-Wire, when an existing driver is being ported to a new MCU or bus instance, or when a driver bug is intermittent (NACKs, timeouts, garbled frames, "only works when single-stepped in a debugger"). Produces a register-map-backed driver behind a hardware abstraction layer plus a two-tier test harness: host-side unit tests against a mocked bus and a hardware-in-the-loop (HIL) test against the real part.
---

# write-peripheral-driver-with-hil-test

## Overview
Turns a peripheral datasheet into a driver with a clean bus abstraction and a
test harness proven against both a mocked bus and real hardware. The one job
it owns: no driver merges on "it worked on my bench once" — it merges with a
repeatable pass/fail gate.

## When to use
- A new sensor, radio, memory, or peripheral IC is being brought up over
  SPI/I2C/UART/CAN/1-Wire and needs its first driver.
- An existing driver is being ported to a new microcontroller or a new bus
  instance on the same part.
- A driver change needs a repeatable pass/fail gate instead of manual
  scope-probing before every merge.
- Symptoms: intermittent NACKs, bus timeouts, garbled UART frames, or a
  peripheral that only behaves correctly when single-stepped in a debugger
  (a classic timing-sensitive bug masked by breakpoints).

## Workflow
1. **Extract the register map** from the datasheet into named constants or a
   struct (addresses, bitfields, reset values). Never hand-roll raw addresses
   inline in driver logic.
2. **Define the HAL boundary.** The driver depends on an abstract bus
   interface, not the concrete MCU HAL, so it can be swapped for a mock in
   host-side tests:
   ```c
   typedef struct {
       int (*write_reg)(void *ctx, uint8_t reg, const uint8_t *data, size_t len);
       int (*read_reg)(void *ctx, uint8_t reg, uint8_t *data, size_t len);
       void (*delay_us)(uint32_t us);
   } bus_ops_t;
   ```
3. **Implement the state machine**: init/config → read/write → error handling
   → deinit. Handle every documented error path — NACK, CRC failure, timeout,
   a stuck busy-flag — not just the happy path.
4. **Encode timing from the datasheet**: reset delays, minimum clock periods,
   setup/hold times, as named constants with the datasheet section cited in a
   comment next to each one.
5. **Build a two-tier test harness**:
   - Host-side unit tests against the mocked `bus_ops_t` — fast, run on every
     commit, and the easiest place to cover error-path branches.
   - Hardware-in-the-loop tests that flash the target and drive/read the real
     part (pair with `set-up-embedded-ci-with-hil-runner` to automate this).
6. **Sanity-check values off the bus** before handing them to application
   code — a temperature sensor returning an impossible reading is a bus
   fault, not a measurement, and should be treated as one.

**Decision point — mock vs. HIL:** if the peripheral's behavior is fully
deterministic from the bus protocol (an EEPROM, a GPIO expander), a bus-level
mock alone can reach full coverage. If it has physical-world nondeterminism
(analog noise, RF timing, mechanical settling), only a HIL test catches real
bugs — budget test time accordingly rather than trying to mock it all away.

**Gotcha:** bus timing that "works" under a debugger with breakpoints can
fail in production, because breakpoints change wait states, mask race
conditions, or let a watchdog reset before an interrupt service routine
completes. Never sign off a driver validated only by single-stepping.

## Checklist / quality gate
- Register map lives as named constants/structs, not magic numbers in logic.
- Every documented error path (NACK, timeout, CRC, busy-flag) has a handling
  branch and a test that exercises it.
- Host-side unit tests pass against the mocked bus interface.
- The HIL test has passed against real hardware at least once before merge,
  or CI is wired to run it automatically.
- Timing constants cite the datasheet section they came from.
- Values read off the bus are range/sanity-checked before use.

## References
- Embedded Systems Roadmap — https://www.scaler.com/blog/the-embedded-systems-roadmap/
- Embedded Integration Testing — Parasoft — https://www.parasoft.com/blog/embedded-integration-testing/

## Composition
Hands its HIL test case to `set-up-embedded-ci-with-hil-runner` to run on
every commit. The task that owns this driver is usually sized with
`design-rtos-task-and-ipc`. Once the driver compiles, gate it through
`run-misra-static-analysis-triage` before merge, and cover the host-side mock
tests under a broader `write-unit-tests-with-coverage-target` pass.
