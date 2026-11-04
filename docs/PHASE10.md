# Phase 10 — owner login, Mac deployment and fresh evaluation

The user authorized quality evaluation, authentication and deployment, then specified **keep it on Mac**. This phase delivers one private owner account and loopback-only deployment. It preserves existing PDF originals, ingestion/retrieval storage and saved answers. It does not add public hosting, multi-user document isolation, cloud services or model downloads.

## Open and manage the app

Double-click [Open OmniRAG.command](../Open%20OmniRAG.command), or run from the repository root:

```bash
.venv/bin/python scripts/mac_app.py start
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). A built React frontend is served by the same API process. Vite is no longer needed for normal use. The launcher verifies recorded process commands and working directories, avoids duplicate API/worker launches, and refuses an occupied API port belonging to an unverified process. It reuses local Ollama or starts the installed executable; it never downloads a model. Service PIDs and logs remain under `data/local/`.

```bash
.venv/bin/python scripts/mac_app.py status
.venv/bin/python scripts/mac_app.py restart
.venv/bin/python scripts/mac_app.py stop
```

`restart` replaces only the verified API; `stop` stops the verified API and worker. Shared Ollama remains running. Services run detached after startup, but no login agent or automatic crash-restart service was installed. After reboot, double-click the launcher again. A sleeping Mac cannot serve requests. No public network binding, router rule or firewall change is required.

After editing frontend source, run `npm --prefix frontend run build` before restarting. The existing locked Python environment, Node packages, OCR executable and retrieval/model files must already be installed. Follow the README development setup only on a fresh installation. Startup reports missing prerequisites rather than installing them silently.

## Owner password and recovery

The existing Mac installation has a generated owner password in **`data/local/auth/owner-password.txt`**. That file is excluded from Git, with permissions `0600` inside a `0700` directory. Open it locally, sign in, and use **Change password** to choose a private password of 15–128 characters. Save the new password in your password manager. The handoff file is not updated when you change the password; remove the obsolete file after storing your new password safely. Do not paste passwords into chat or command arguments.

For a new installation, configure the account interactively before starting:

```bash
.venv/bin/python scripts/owner.py
```

If you forget the password, use the explicit local recovery command:

```bash
.venv/bin/python scripts/owner.py --reset
```

This prompts without echoing the password, replaces the owner credential and revokes all sessions. It does not delete documents/history. A normal setup refuses to replace an existing account. `--generate` is an alternative that writes an exclusive private handoff file rather than printing a password; it refuses to overwrite that file.

## Access and session behavior

When authentication is enabled, documents, original PDFs, history, search, queries, retrieval management, readiness and API documentation require an owner session. The login screen, static assets, minimal health response and session-status endpoint remain public. An unconfigured owner leaves private routes locked.

Passwords use a fresh random salt and scrypt (`N=2^17`, `r=8`, `p=1`). Random 256-bit session tokens are stored only as hashes in a separate authentication SQLite database. Browser cookies are HttpOnly and SameSite Strict. Sessions expire after eight hours or thirty minutes without authenticated requests; background polling counts as activity. A new login replaces prior sessions. Logout, password change and local reset revoke access.

Login requires a custom request header and accepts only the configured local origins when Origin is present. Authenticated writes also require a session-bound CSRF token; SameSite alone is not the CSRF control. Five login attempts per minute are allowed across the single owner, persisted across API restarts. The global limit can temporarily block legitimate login after repeated failures. Password hashing is serialized within the API process. The UI clears workspace state on expired-session responses.

Private responses are marked `no-store`; response headers constrain framing to the same origin, avoid referrer transmission and disable MIME sniffing. Cookies deliberately do not use Secure because this deployment uses loopback HTTP. **This configuration is not suitable for public HTTP hosting.** Local malware, another application running as the same macOS user, or an administrator can access local data/credentials. There is no filesystem encryption added by this change; use macOS account controls and FileVault as appropriate. This is functional security validation, not an independent penetration test.

The private launcher explicitly enables authentication and built-frontend serving. Raw development commands retain their prior unauthenticated defaults for isolated tests; do not substitute them for the private launcher. Backend tests and historical evaluation commands use temporary storage without authentication unless explicitly testing it.

Implementation references: [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) and [CSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

## Evaluation boundary

[acceptance_v1.json](../evaluation/acceptance_v1.json) contains new fictional entities, values and questions frozen before its first model run. The run used unchanged Phase 9 generation behavior and isolated temporary ingestion/retrieval storage. It did not tune prompts or weaken expected facts after observing failures. It is fresh authored acceptance evidence from the same assistant, **not an external benchmark or independent human assessment**.

```bash
.venv/bin/python scripts/evaluate_quality.py \
  --fixture evaluation/acceptance_v1.json \
  --modes bm25 hybrid_rerank --with-model --strict \
  --output data/local/acceptance-new-run.json
```

Use a new report path; existing evidence is not overwritten. The original run returned strict exit 2 because quality requirements failed. See [observed validation](PHASE10_VALIDATION.md). Subsequent tuning would turn these cases into development regressions and require another frozen acceptance set. No general answer-accuracy claim is justified by the implemented source-binding checks.
