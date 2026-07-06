# Guide — ssh-tunnel-keepalive

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
A long-lived SSH tunnel to a remote database or internal service dies on the
bastion's idle timeout mid-session, and the next query fails with "connection
refused". This tool holds the tunnel open with server keepalives and reconnects
automatically on drop, so multi-turn database work does not stall.

## When to deploy (triggers)
Any remote-DB or SSH-tunnel session spanning multiple background-command turns or
more than ~30 minutes; a "connection refused" after an idle gap; a bastion with a
short idle-timeout.

## Interface (how to invoke)
`bash ~/.claude/tools/ssh_tunnel_keepalive.sh -k <key> -H <host> -u <user> -L <localport:remotehost:remoteport>`.
Prefers `autossh` when installed (robust reconnect); otherwise loops plain `ssh`
with `ServerAliveInterval` keepalives. `-h` prints usage.

## Composition (pairs with / hands off to)
Pairs with `postgres-readonly` (the MCP that talks to the forwarded local port)
and `env-tooling-preflight` (confirms `ssh`/`autossh` are present). Fill in the
host and key during `environment-bootstrap`.

## Build & maintenance notes
Tool at `~/.claude/tools/ssh_tunnel_keepalive.sh`; macOS bash 3.2 safe. Keys must
be `chmod 600`. Never hardcode a host or key into a tracked file — pass them as
flags or source them from `secrets.env`.
