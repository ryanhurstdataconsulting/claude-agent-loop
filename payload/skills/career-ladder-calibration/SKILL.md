---
name: career-ladder-calibration
description: Use when defining or updating an engineering career ladder or competency framework, or when a promotion packet needs to be checked against an existing ladder before a calibration meeting. Triggers include "define our levels," "update the IC/management ladder," "does this packet support a promotion to senior," a cross-manager calibration session, a "scope creep" complaint where someone's actual work has outgrown their level, or a request to draft observable, evidence-based level descriptors instead of vague ones. Produces level definitions across scope, technical-depth, and leadership axes, plus an evidence-to-descriptor mapping for a specific packet.
---

# career-ladder-calibration

## Overview
Drafts or refines an engineering career ladder — level definitions across scope,
technical, and leadership axes — and, given a specific promotion packet, maps its
submitted evidence against that ladder's descriptors to flag what's solidly
supported and what's thin. This skill owns the ladder-definition and
evidence-mapping artifact; it does not own the promotion decision or any
compensation number, both of which stay with the human calibration committee.

## When to use
- Defining a new engineering career ladder from scratch, for an individual
  contributor track, a management track, or both.
- Updating an existing ladder to add a level, split a track that has outgrown a
  single shared definition, or tighten language that has become too vague to
  calibrate against.
- A promotion packet needs to be checked against the current rubric before a
  calibration meeting.
- Multiple managers need a calibration pass to catch inconsistent leveling of
  comparable work across teams.
- Someone believes their actual scope has outgrown their current level and wants
  the gap made explicit against the rubric.

## Workflow

**1. Confirm the axes before drafting anything.** Most ladders separate at least:
**Scope & Impact** (what a person owns, and the blast radius of their decisions),
**Technical Depth** (execution quality, architectural judgment, complexity
handled), and **Leadership & Influence** (mentoring, cross-team influence,
culture-setting). Some organizations add a fourth axis — Communication or
Ambiguity Navigation is common. Use the organization's existing axis set if one
exists; do not invent new axes without confirming first.

**2. Draft observable, evidence-based descriptors — not vibes.** Every descriptor
should map to something a reviewer could point to in a packet as present or
absent.
- Weak: "Is a strong communicator."
- Calibratable: "Regularly presents technical trade-offs to non-technical
  stakeholders and adjusts the framing to the audience without being prompted."

**3. Keep levels distinguishable and monotonic.** Apply the swap test: could you
exchange two adjacent levels' descriptors and no one would notice? If yes, the
boundary is too soft — tighten it. Watch for level-inflation language, where a
level is labeled "senior" but its descriptors would fit a mid-level scope just as
well.

**4. Separate IC and management tracks once they diverge.** A shared ladder that
force-fits management scope onto individual-contributor descriptors (or the
reverse) is a common failure mode; split the tracks explicitly at the point where
the work genuinely differs, typically around senior or staff-plus.

**5. For a calibration pass, map every piece of submitted evidence to a specific
descriptor.** Evidence sources: project outcomes, peer and cross-functional
feedback, 1:1 notes, and the accomplishment log. Flag any descriptor with zero
mapped evidence — that is a gap the packet needs to close before the meeting, not
an assumption the calibration pass should wave through.

**6. Cross-check against comparable packets from the same cycle when available.**
The point of calibration is consistency across managers, not just internal
consistency within a single packet — a candidate leveled against a stricter or
looser bar than a peer doing comparable work is exactly what a calibration pass
exists to catch.

**7. Output a calibration checklist, not a verdict.** Report which descriptors are
solidly evidenced, which are thin, and which are entirely unaddressed. The
go/no-go decision, and any compensation change, belongs to the human calibration
committee — the skill's job ends at making the evidence gap visible.

**Common gotchas:**
- Descriptors written as personality traits ("is passionate," "has great
  instincts") rather than observable behavior — these cannot be calibrated
  consistently across reviewers.
- Defining levels by tenure ("two-plus years of experience") instead of
  demonstrated scope — tenure is a proxy, not evidence, and produces resentment
  when tenure and actual scope diverge.
- No distinction in the ladder between "meets" and "exceeds" the level below the
  one being sought, which makes nearly every packet look promotion-ready on
  paper.
- Silently inventing new competency axes that are not part of the organization's
  existing framework — always confirm the axis set first (step 1).

## Checklist / quality gate
- [ ] Levels are defined on confirmed axes (scope, technical, leadership, or the
      organization's own set) — not invented ones.
- [ ] Every descriptor is observable and evidence-based, not a personality trait.
- [ ] Adjacent levels pass the swap test — clearly distinguishable, not
      interchangeable.
- [ ] IC and management tracks are separated once their scope genuinely diverges.
- [ ] For a calibration pass, every submitted evidence item is mapped to a
      specific descriptor.
- [ ] Descriptors with no supporting evidence are flagged as gaps, not silently
      accepted.
- [ ] The output stops at a calibration checklist and evidence map — no
      promotion verdict or compensation figure is generated.

## References
- [Teamflect — Competency Mapping for Performance Reviews](https://teamflect.com/blog/performance-management/competency-mapping-for-performance-reviews)
- [LeadDev — The Engineering Manager 101](https://leaddev.com/career-development/engineering-manager-101)

## Composition
- Pairs with `perf-review-drafting` — the ladder this skill produces is the
  rubric a performance-review draft maps accomplishment evidence against.
- Feeds a human calibration committee meeting; the checklist this skill produces
  is meeting prep, not a substitute for the meeting itself.
- Overlaps with `status-report`-style leadership reporting only at the summary
  level — individual evidence mapping stays out of any broader status narrative.
