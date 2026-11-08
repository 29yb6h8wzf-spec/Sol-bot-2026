# SignalPilot EC2 runtime recovery gap — observed 2026-11-08

This document records **read-only observations**, not a reconstructed or approved deployment. Do not use this inventory to deploy, merge, restart services, or execute exchange commands.

## Verified active dependencies (systemd ExecStart and git ls-files)

| Unit | Entrypoint | Git-tracked on active EC2 checkout? |
| --- | --- | --- |
| signalpilot-signal-inbox.service | signal_bridge_http.py | NO |
| signalpilot-sqs-consumer.service | signal_sqs_consumer.py | NO |
| signalpilot-sandbox-consumer.service | futures_engine.sandbox_research_consumer | NO |
| signalpilot-sandbox-publisher.service | futures_engine.sandbox_research_publisher | NO |
| signalpilot-paper-sol.service | futures_engine | YES (futures_engine/__main__.py) |
| signalpilot-paper-xrp.service | futures_engine | YES (futures_engine/__main__.py) |

The live checkout was at `990d11a` (2026-11-05); its `git status --porcelain` reported 49 lines, including runtime databases and local Python scripts. **Do not run git clean/reset** against this machine. Four entrypoints above were explicitly verified as local-only; this does not prove other dependencies are recoverable.

All six units had `Result=success` at observation. SOL/XRP oneshots exited with code 0. Inbox and SQS consumer were active; the sandbox units are timer-triggered oneshots. These observations do not prove end-to-end trading functionality.

## Secret and privilege boundaries

- `signal_bridge_http.py` contains a `SECRET_PATH` string constant read with `open()`. The referenced file existed, was owned by root and mode `0600`; its content and path were not captured. This is **not** a complete source secret scan.
- Inbox and SQS consumer had an empty `User=` (systemd defaults to root), `NoNewPrivileges=yes`, `ProtectSystem=no`, `PrivateTmp=no`. Hardening requires separate compatibility testing.
- Do not commit runtime SQLite/JSON, backups, environment files, service credentials, SSM output with secrets, or raw server files before manual review.

## Recovery acceptance criteria (currently NOT MET)

1. Obtain an approved, **redacted and reviewed** source copy of each local-only entrypoint; verify its SHA-256 against the running machine without publishing sensitive content.
2. Verify its local imports and service unit definitions, then add reviewed code and systemd unit templates to an isolated branch; never embed absolute secret values.
3. Run offline syntax/unit tests and a secret scanner; require CI success and demonstrate a clean-room bootstrap in an isolated environment.
4. Ensure rootless service permissions and restrictive systemd settings are tested before proposing them.
5. Compare installed service entrypoints with versioned files using `tools/audit_unit_inventory.py` from PR #144. Its default empty-unit result is not proof of coverage; pass explicit `--unit` names and use `--strict`.
6. No merge, deploy, service restart, or Binance commands as part of this audit.

## Evidence provenance

Observed through user-supplied output of AWS Systems Manager read-only commands on 2026-11-08. The repository contents of PR #144 were independently read through GitHub. **The four local source files were not retrieved or reviewed through GitHub and are not included here.**
