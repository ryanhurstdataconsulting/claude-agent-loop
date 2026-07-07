---
name: design-ota-bootloader-update-flow
description: Use when a product is moving from factory-only programming to field-updatable firmware, when an existing over-the-air (OTA) update flow has shipped a bad build and needs a rollback redesign, when a security review flags unsigned or unverified firmware images, or when a device fleet needs a staged/canary rollout plan. Covers dual-bank/A-B partitioning, the signature and trust chain, boot-confirmation and rollback triggers, and bricking-mitigation for power loss or corrupted downloads mid-update.
---

# design-ota-bootloader-update-flow

## Overview
Designs the bootloader-level plan for delivering, verifying, and safely
rolling back a firmware update in the field, so a failed or corrupted update
degrades to a recoverable state instead of bricking the device. The one job
it owns: make "the update failed" a survivable event, not a factory-return
event.

## When to use
- A product is moving from factory-only (debug-probe) programming to
  field-updatable firmware.
- An existing OTA flow has shipped a bad update and needs a
  rollback/recovery redesign.
- A security review flags unsigned or unverified firmware images as a
  finding.
- A device fleet needs a staged-rollout plan (canary percentage, halt
  criteria) instead of an all-at-once push.

## Workflow
1. **Choose the partition strategy first** — it drives almost everything
   downstream.
   - **Dual-bank / A-B:** two full application partitions; the bootloader
     boots whichever is marked valid. The simplest rollback story — just
     re-point the boot flag — at the cost of roughly double the flash
     footprint.
   - **Single-bank with a staging area:** the update writes to a smaller
     staging region, then copies over the active bank on verified
     completion. Saves flash at the cost of a more fragile "mid-copy"
     failure window that needs its own recovery path.
   - Pick dual-bank whenever flash budget allows it — it removes an entire
     class of "the device died mid-flash" failure modes.
2. **Define the trust chain before writing any transport code**: what signs
   the image (an offline signing key, never present on-device), what
   verifies it (a public key baked into the bootloader, not into the
   updatable application), and what the signature covers (the whole image
   plus its version/metadata header, to block replay of an old,
   signed-but-vulnerable image).
3. **Design the update sequence explicitly**:
   ```
   download/stage → verify signature → verify integrity (hash/CRC)
     → mark pending → reboot into new image
     → new image self-tests and confirms boot → commit (mark permanently valid)
   ```
   Nothing is permanent until the new image proves it can boot and run.
4. **Define the rollback trigger and its owner.** A watchdog-driven
   boot-loop counter is the standard mechanism: N failed boot attempts
   within the new image causes the bootloader to revert the boot-valid flag
   to the previous bank. Decide N and the definition of "failed boot"
   (crash, watchdog reset, or an explicit app-level health check that must
   report in) up front.
5. **Plan for the worst case explicitly**: power loss mid-write, a corrupted
   download, and a signature that fails verification. Each needs a defined
   bootloader behavior, not an assumption that "it won't happen." A device
   recoverable only by factory return is a shipped bricking bug waiting to
   happen.
6. **For fleets, add a staged/canary rollout**: push to a small percentage
   first, define a halt/abort criterion (crash-rate or failed-boot-rate
   threshold) before it reaches every device, and keep a server-side kill
   switch independent of the device's own logic.

**Gotcha:** the bootloader itself is almost never updated over the air —
updating the thing that verifies updates is its own separate, much
higher-risk problem. Keep it minimal, keep it stable, and give it its own
heavily scrutinized release process.

**Gotcha:** verifying a signature and then reading version/size fields from
an unverified header before that check completes is a common ordering bug —
verify the whole image, header included, before trusting any field inside
it.

## Checklist / quality gate
- Partition strategy (dual-bank vs. staged single-bank) is chosen and
  documented with the trade-off reasoning.
- Update images are signed offline; the verification key lives in the
  bootloader, not the updatable application.
- The full image, including its version/metadata header, is covered by the
  signature — not just the payload.
- A new image must self-confirm boot before being marked permanently valid.
- A boot-loop counter (or equivalent) triggers automatic rollback to the
  last-known-good bank.
- Power-loss-mid-write and corrupted-download cases both have a defined,
  tested recovery behavior — no failure mode requires a factory return.
- The bootloader itself is excluded from the routine OTA update path.

## References
- Mastering Embedded Software Testing — Fidus Systems — https://fidus.com/blog/mastering-embedded-software-testing-a-complete-guide-to-tools-and-techniques/
- Embedded DevOps: CI/CD and firmware deployment — AESTECHNO — https://www.aestechno.com/en/embedded-devops-cicd-automated-tests/

## Composition
A flash-and-verify HIL test from `set-up-embedded-ci-with-hil-runner` proves
this flow before it ships. Bootloader code is a prime candidate for the
strictest tier of `run-misra-static-analysis-triage` given its blast radius.
The trust-chain design in step 2 is itself a `threat-model-on-diff`
pass. The partition-strategy choice in step 1 is exactly the kind of
hard-to-reverse call `adr-authoring` should capture.
