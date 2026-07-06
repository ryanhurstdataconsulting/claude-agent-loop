# Security & scrub statement

This bundle was scanned with the `secret-pii-scrub-gate` tool it ships (the tool
is part of the payload) before packaging. **It contains no real secrets, API
tokens, JWTs, SSH keys, passwords, or personal data.**

## How it was built

`claude-agent-loop-starter` was generalized from a working, client-specific
Claude Code environment. Everything that identified the original client was
removed — organization and product names, infrastructure hostnames, project
codenames, customer and personal data, and every domain-specific resource. What
remains is the generic agent-loop framework plus a curated, reusable resource
set. No credential, host, or MCP registration ships in the bundle; the database
pieces are placeholder templates you fill in yourself (see below).

## Remaining scanner findings — all benign, explained

Re-running the scrub over this bundle (scanning every file) reports 8 matches;
each is an example, a placeholder, or the scanner describing itself:

| Location | Hits | What it is | Why it is safe |
|---|---|---|---|
| `payload/tools/secret_pii_scrub_gate.py` | 2 | the scanner's own docstring + regex source | it describes the patterns it detects — not real data |
| `payload/skills/tauri-desktop-dev/SKILL.md` | 4 | generic `/Users/<you>`-style example paths | placeholders illustrating a Tauri `homeDir()` bug — no real username |
| `payload/skills/aws-local-emulation/references/ministack.md` | 1 | the LocalStack dummy credential (the literal word test) | the standard LocalStack sandbox value |
| `payload/mcp-specs/postgres-readonly.md` | 1 | a placeholder Postgres connection string (all `<PLACEHOLDERS>`) | the MCP template's example — no real host or credential |

This file, `SECURITY.md`, is written to avoid the scanner's trigger patterns, so
it adds no findings of its own.

## What YOU supply (never shipped)

To connect a database, you provide your own values — the `environment-bootstrap`
skill walks you through it:

- your database host, port, name, and a **read-only** role — see
  `payload/mcp-specs/postgres-readonly.md`;
- the password → a project `secrets.env` (gitignored), referenced as an env var,
  never embedded in a registration;
- if the database is behind a bastion: your own SSH key and account, and an open
  tunnel (`ssh-tunnel-keepalive`).

## Verify it yourself

```bash
python3 payload/tools/secret_pii_scrub_gate.py .
```

The findings you see should match the table above (8 total) and nothing else.
