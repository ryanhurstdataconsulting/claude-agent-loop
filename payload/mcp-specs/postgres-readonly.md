# MCP — postgres-readonly (read-only SQL to your database)

**Provides:** a live, read-only SQL connection Claude can query. **Requires:**
your database host + credentials (you supply) and an open tunnel if the database
is behind a bastion. **Access:** read-only — never point this registration at a
role that can write.

## What it is

A Model Context Protocol server that lets Claude run SELECT queries against your
Postgres (or MySQL) database. No credential lives in the registration itself: you
connect through a local port — direct, or the local end of an SSH tunnel you open
with `ssh-tunnel-keepalive` — and the password comes from `secrets.env`.

## Registration (Postgres)

Add to your project's `.claude/settings.local.json` under `mcpServers` (or global
`~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "postgres-readonly": {
      "command": "npx",
      "args": [
        "-y", "@modelcontextprotocol/server-postgres",
        "postgresql://<DB_USER>@localhost:<LOCAL_PORT>/<DB_NAME>?sslmode=disable"
      ]
    }
  }
}
```

- `<LOCAL_PORT>` — the local port your tunnel forwards to the database (for
  example, 15432), or the database's real port for a direct/local connection.
- `<DB_USER>` — a **read-only** database role. Do not use a role that can write.
- The password is read from the environment (`PGPASSWORD` in `secrets.env`), not
  embedded here.

For MySQL, use `@modelcontextprotocol/server-mysql` (or your preferred MySQL MCP)
with the equivalent connection string.

## Read-only enforcement (do this — do not trust the client)

Grant the connecting role SELECT-only at the database, and open every session
with a read-only transaction and a statement timeout:

```sql
SET default_transaction_read_only = on;
SET statement_timeout = '30s';
```

Always dispatch `sql-safety-reviewer` before running a query it has not seen.

## What YOU supply (never shipped)

- The database host, port, name, and a read-only role — filled during
  `environment-bootstrap`.
- The password → `secrets.env` (gitignored), referenced as an env var.
- If the database is behind a bastion: your own SSH key + account, and an open
  tunnel (`ssh-tunnel-keepalive`).
