---
name: yagni-ladder
description: Use before writing new code — a function, a dependency, a config knob, a new file, an abstraction — or when reviewing a diff/PR for unnecessary complexity. Climb a seven-rung ladder from the top and stop at the first rung that resolves the need. Triggers - "do we need this," "is there a simpler way," "yagni," adding a dependency, scaffolding a new file or module, a design proposing a new abstraction.
---

# YAGNI Ladder

## Overview

Before new code gets written, climb this ladder from the top and stop at
the first rung that resolves the need. The same ladder works in reverse as a
review lens: when reading a diff or PR, walk it top-down and flag any code
that could have stopped at a higher rung than the one it landed on.

## The ladder

1. **Does this need to exist at all?** Is it solving a problem anyone
   actually has, or can the goal be reached by removing or simplifying
   something else instead?
2. **Is it already in the codebase?** An existing function, module, or
   pattern that does this, or is trivially extended to.
3. **Does the standard library already do this?**
4. **Is there a native platform or language feature** — built-in syntax, an
   OS or runtime capability — that does this without pulling in a library?
5. **Can an already-installed dependency do this?**
6. **Can this be one line instead of a new abstraction, file, or class?**
7. **What is the smallest thing that actually works** — no speculative
   generality, no unused parameters, no "just in case" flags?

Stop at the first rung that resolves the need. Reaching rung 7 is not a
failure — it means the first six rungs were checked and none applied.

## Never-skip carve-out

Validation, security, and accessibility logic must never be shortcut to a
lower rung just because it produces less code. Correctness and safety in
those areas outweigh minimalism; do not use this ladder to justify skipping
input validation, an authorization check, or an accessibility affordance.

## Relationship to existing guidance

This skill gives the "don't add features, refactor, or introduce
abstractions beyond what the task requires" instruction a concrete,
checkable procedure. It does not replace that instruction — it
operationalizes it into seven ordered questions an agent (or reviewer) can
actually run.

## When to use this

- Before adding a new dependency
- Before scaffolding a new file, module, or class
- Before introducing a new abstraction layer
- Reviewing a diff or PR for unnecessary complexity
- Any time the question "do we need this?" or "is there a simpler way?"
  comes up
