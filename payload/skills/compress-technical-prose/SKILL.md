---
name: compress-technical-prose
description: Use when a SKILL.md frontmatter description, a CATALOG.md bullet, or a tool docstring is too long, or when asked to trim, condense, or reduce the token cost of a specific technical document. Two techniques - compress tool/skill descriptions without losing meaning, and condense one named long file on request. It never compresses conversational replies or other human-facing prose into fragments. Triggers - "this tool description is too long," "trim this doc," "condense this file," reviewing CATALOG.md or SKILL.md descriptions for bloat.
---

# Compress Technical Prose

## Overview

Reduce token bloat in two specific, non-conversational surfaces without ever
touching the grammatical completeness of prose written for a human reader.

## Technique A — tool/skill description compression

When authoring or reviewing a `SKILL.md` frontmatter `description:` field, a
`CATALOG.md` bullet, or a tool docstring — text that loads into context on
every session regardless of whether the skill fires — apply this checklist:

- Cut redundant qualifiers.
- Merge overlapping trigger phrases into one clause.
- Replace multi-clause run-on sentences with a single precise sentence.
- Drop examples that don't add disambiguating information.

The description must remain grammatically complete and unambiguous. This is
an authoring aid applied deliberately when writing or reviewing a
description — never a middleware that rewrites text automatically at
runtime.

Run `payload/tools/lint_description_bloat.py` to find descriptions and
CATALOG.md bullets over budget before applying this technique by hand.

## Technique B — on-request file compression

This technique is an explicit, user-invoked pass over one long technical
file (a verbose README, a design doc) that condenses it: preserve every
fact and every full sentence, cut only redundancy and restatement. It is
always invoked on request for a named file — never applied automatically to
conversational output.

## Hard boundary

This skill never compresses conversational replies, commit messages, PR
bodies, or any prose generated for a human reader into fragments or
shorthand. That behavior is caveman's core mode and is deliberately
excluded because it conflicts with the machine-global grammar mandate.

## When to use this

- "This tool description is too long"
- "Trim this doc"
- "Reduce the token cost of this skill description"
- "Condense this file"
- Reviewing `CATALOG.md` or `SKILL.md` descriptions for bloat
