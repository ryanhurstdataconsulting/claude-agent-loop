---
name: ansible-playbook-authoring
description: Use when a configuration-management task is expressed as "provision/configure these hosts" — installing packages, laying down config files, or managing services across a fleet of VMs or bare-metal hosts outside a container/Kubernetes workflow. Produces role-decomposed, idempotent Ansible playbooks with Vault-encrypted secrets and a Molecule test scaffold per role, rather than a flat, unstructured playbook or ad hoc shell scripts run by hand. Also triggers on "this playbook isn't idempotent," a plaintext password in an Ansible repo, or "write a role for X."
---

# ansible-playbook-authoring

## Overview
Produces host-level configuration-management automation — roles, playbooks,
inventory, and their tests — for infrastructure that isn't containerized.
The one job it owns: a playbook that can be run against the same hosts
twice and, on the second run, reports zero changes.

## When to use
- A fleet of VMs or bare-metal hosts needs packages installed, config files
  templated, or services managed, and there's no existing automation.
- An existing playbook is a flat list of `shell`/`command` tasks with no
  role structure and no idempotency guarantee.
- A playbook re-run reports "changed" on tasks that should be no-ops the
  second time.
- A secret (API key, database password) is sitting in plaintext in an
  Ansible repo.
- A role has no test coverage and nobody knows if it still works against a
  fresh host.

## Workflow
1. **Decompose into roles, not one flat playbook.** Each role owns one
   responsibility (`nginx`, `postgres-client`, `node-exporter`) with the
   standard layout:
   ```
   roles/nginx/
     tasks/main.yml
     handlers/main.yml
     templates/
     defaults/main.yml
     vars/main.yml
     meta/main.yml
   ```
   The top-level playbook then just maps roles to host groups.
2. **Prefer declarative modules over `command`/`shell`.** `apt`, `yum`,
   `dnf`, `template`, `copy`, `service`, `systemd`, `user`, `file`, etc.
   are idempotent by construction — Ansible checks state before acting.
   `command`/`shell` are not: they run every time unless explicitly guarded.
3. **When `command`/`shell` is unavoidable, guard it explicitly.**
   ```yaml
   - name: Run migration script once
     command: /opt/app/migrate.sh
     args:
       creates: /opt/app/.migrated   # skip if this file already exists
   ```
   Or use `changed_when`/`when` conditionals so the task reports accurately
   instead of always claiming "changed."
4. **Put overridable values in `defaults/main.yml`; fixed values in
   `vars/main.yml`.** `defaults/` has the lowest variable precedence and is
   meant to be overridden by inventory or `-e`; `vars/` is not. Mixing the
   two makes a role's tunable surface unclear.
5. **Use handlers for restart/reload, notified — not run unconditionally.**
   ```yaml
   tasks:
     - name: Deploy nginx config
       template:
         src: nginx.conf.j2
         dest: /etc/nginx/nginx.conf
       notify: Restart nginx

   handlers:
     - name: Restart nginx
       service:
         name: nginx
         state: restarted
   ```
   A handler only fires when the task that notified it actually reported
   "changed," which keeps re-runs from restarting services that didn't
   need it.
6. **Encrypt every secret with Ansible Vault.** Never commit a plaintext
   password, API key, or private key. `ansible-vault encrypt
   group_vars/prod/secrets.yml`, reference the value normally in tasks, and
   supply the vault password via `--vault-password-file` or a vault-id at
   run time — not hardcoded in the repo.
7. **Structure inventory by role and environment.** Group hosts logically
   (`[web_prod]`, `[db_staging]`) in static YAML/INI inventory, or use a
   dynamic inventory plugin for cloud-provisioned hosts so the inventory
   stays in sync with what actually exists.
8. **Scaffold a Molecule test per role.** A `molecule/default/` scenario
   with a Docker (or Podman) driver runs the full loop in seconds: converge
   (apply the role), idempotence (apply again, assert zero changes),
   verify (assertions against the resulting state).
   ```bash
   molecule test    # converge -> idempotence check -> verify -> destroy
   ```
9. **Lint before every commit.** `ansible-lint` and `yamllint` catch
   deprecated module usage, missing `name:` fields, and YAML formatting
   issues that don't show up until a real run fails.
10. **Dry-run against production with `--check --diff` before the real
    apply.** Check mode surfaces exactly what would change without
    changing it — the cheapest verification step before touching hosts
    that matter.

## Checklist / quality gate
- [ ] Playbook is decomposed into single-responsibility roles, not one flat
      task list.
- [ ] Declarative modules are used wherever available; any `command`/
      `shell` use is guarded (`creates`/`removes`/`changed_when`) so it's
      idempotent.
- [ ] All secrets are Ansible Vault-encrypted; none appear in plaintext
      anywhere in the repo or its history.
- [ ] Handlers are used for restart/reload actions and notified rather
      than run unconditionally.
- [ ] Role variables are split correctly between `defaults/` (overridable)
      and `vars/` (fixed).
- [ ] A Molecule scenario exists per role and `molecule test` passes,
      including the idempotence check.
- [ ] `ansible-lint` and `yamllint` run clean.
- [ ] A second real run against the same hosts reports zero changes —
      idempotence is demonstrated, not assumed.

## References
- [Ansible documentation](https://docs.ansible.com/)
- [Ansible Vault](https://docs.ansible.com/ansible/latest/vault_guide/index.html)
- [Molecule testing framework](https://ansible.readthedocs.io/projects/molecule/)
- [ansible-lint](https://ansible.readthedocs.io/projects/lint/)

## Composition
Sits downstream of `terraform-module-authoring` at the inventory boundary —
Terraform provisions the hosts, this skill configures them. Role skeletons
produced here are a reusable component for
`golden-path-template-authoring`. Run `secrets-scanning-remediation` before
committing to confirm Vault encryption caught every secret. Wire
`ansible-lint` and `molecule test` into CI via `ci-pipeline-authoring`.
