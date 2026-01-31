# Setup & Enrollment Flow Audit

Traces the actual user experience for three scenarios, identifies gaps, and proposes improvements.

---

## Scenario 1: New User (First Run)

### What They Run

```
tescmd setup
```

### Actual Flow (Phase by Phase)

| Phase | What Happens | User Action | Outcome |
|-------|-------------|-------------|---------|
| **0: Tier** | Prompt: "Choose [1] readonly or [2] full" | Types `2` | `TESLA_SETUP_TIER=full` written to `.env` |
| **1: Domain** | Detects `gh` CLI, suggests `<user>.github.io` | Presses Enter | Creates GitHub Pages repo, writes `TESLA_DOMAIN` + `TESLA_GITHUB_REPO` to `.env` |
| **2: Dev Portal** | Walks through `developer.tesla.com` registration | Copies client ID + secret from portal | Writes `TESLA_CLIENT_ID` + `TESLA_CLIENT_SECRET` to `.env` |
| **3: Key Gen+Deploy** | Generates EC P-256 key pair, deploys PEM to GitHub Pages, waits for Pages build | Watches spinner | Key live at `https://<user>.github.io/.well-known/appspecific/com.tesla.3p.public-key.pem` |
| **3.5: Enrollment** | Checks key accessibility, opens `https://tesla.com/_ak/<domain>` | Opens Tesla app, approves key | Key enrolled on vehicle(s) |
| **4: Registration** | `POST /api/1/partner_accounts` to Tesla Fleet API | Watches output | App registered for region |
| **5: OAuth** | Opens browser for OAuth2 PKCE login | Clicks "Allow" in Tesla auth page | Access + refresh tokens stored in keyring |
| **6: Summary** | Prints next-step commands | Done | |

### Problems

1. **Phase 3.5 enrollment is a dead end.** The setup wizard opens the enrollment URL and prints instructions, but never confirms whether enrollment actually succeeded. The user is told "After approving, try: `tescmd charge status --wake`" but if they haven't approved yet (or didn't understand the instructions), setup continues to Phase 4 anyway with no indication that anything is incomplete.

2. **Phase 6 contradicts Phase 3.5.** The final summary (`_print_next_steps`) previously printed stale instructions referencing a non-existent "Security > Third-Party Access" menu. **Fixed:** Phase 6 now directs users to `tescmd key enroll`. The correct Tesla app path to verify enrollment is Profile > Security & Privacy > Third-Party Apps.

3. **No VIN awareness.** The enrollment URL (`tesla.com/_ak/<domain>`) enrolls the key for ALL vehicles on the account, but this isn't explained. The user may think they need to enroll per-vehicle (the old `key enroll <VIN>` messaging is still referenced in `signed_command.py:125`).

4. **`key enroll` command also doesn't know about VINs.** The `key enroll` CLI command has no VIN parameter — it just opens the portal URL. But `signed_command.py:125` says "Run `tescmd key enroll {vin}` first" when a key-not-enrolled error is detected. This command doesn't accept a VIN argument.

5. **Phase 4 can fail silently if key isn't live yet.** `_precheck_public_key` checks the key URL before registration, but GitHub Pages can take 30-60s. If Phase 3 said "not yet accessible" and Phase 4 proceeds anyway, registration fails with HTTP 424. The `_remediate_424` handler gives good guidance, but the user has to re-run setup.

6. **No `--json` support for setup.** The entire wizard is TTY-only with `input()` calls. Running `tescmd --format json setup` still gets interactive prompts.

---

## Scenario 2: Returning User (readonly -> full upgrade)

### What They Run

```
tescmd setup
```

### Actual Flow

| Phase | What Happens | User Action | Outcome |
|-------|-------------|-------------|---------|
| **0: Tier** | "Setup tier: readonly (previously configured)" then "Upgrade to full control? [y/N]" | Types `y` | `TESLA_SETUP_TIER=full` written to `.env` |
| **1: Domain** | "Domain: user.github.io (already configured)" | — skipped | |
| **2: Dev Portal** | "Client ID: abc123... (already configured)" | — skipped | |
| **3: Key Gen+Deploy** | Generates keys (new), deploys to existing GitHub Pages repo | Watches spinner | |
| **3.5: Enrollment** | Opens enrollment URL | Approves in Tesla app | |
| **4: Registration** | May need to re-register (key changed) | — | |
| **5: OAuth** | "Already logged in. Skipping OAuth flow." | — skipped | |
| **6: Summary** | Prints next steps | Done | |

### Problems

1. **Existing tokens may lack command scopes.** When the user initially set up as readonly, their OAuth scopes may be limited (e.g., `vehicle_device_data` only, no `vehicle_cmds`). Phase 5 skips OAuth because `store.has_token` is True. But the existing token doesn't have the command scopes needed for full-tier operations. The user will hit a permissions error on their first command with no clear guidance about why.

2. **No scope check before skipping OAuth.** There's no validation that the stored token's scopes include what full-tier needs. The fix should compare stored scopes vs. `DEFAULT_SCOPES` and re-auth if there's a gap.

3. **Re-registration timing.** Phase 4 re-registers, but the public key might not be accessible yet if Phase 3 just deployed it. Same GitHub Pages propagation issue as Scenario 1.

4. **`_prompt_tier` returns early for `TIER_FULL`.** If someone already has `setup_tier=full` and runs `tescmd setup` again (e.g., to fix broken enrollment), Phase 0 immediately returns `"full"` without asking anything. This is correct behavior, but it means re-running setup doesn't offer a way to "reset" or "re-enroll."

5. **No "what changed" summary.** When upgrading, the user gets the same Phase 6 summary as a new user. There's no "Here's what changed: you now have key-based command signing" message.

---

## Scenario 3: Broken Command Key

### Possible Causes

- Key pair deleted from `~/.config/tescmd/keys/`
- Public key removed from GitHub Pages (repo deleted, file deleted)
- Key enrolled on vehicle but local private key lost
- Key never actually enrolled (user skipped Phase 3.5)
- GitHub Pages domain changed but `.env` still has old domain

### What the User Sees

Depends on what's broken:

| Broken State | Command Run | Error | Guidance Given |
|-------------|-------------|-------|---------------|
| **No local keys** | `tescmd charge start` | Falls back to unsigned REST path silently (protocol=auto) | None — may work or may get a vague API error |
| **No local keys** + `protocol=signed` | `tescmd charge start` | `ConfigError: command_protocol is 'signed' but no key pair found` | "Run 'tescmd setup' to configure full tier" |
| **Keys exist but not enrolled** | `tescmd security lock` | `KeyNotEnrolledError` from signed_command.py | "Run 'tescmd key enroll {vin}' first" — **wrong, key enroll doesn't take a VIN** |
| **Keys exist, public key not at URL** | `tescmd key enroll` | Exit code 1: "Public key not accessible" | "Deploy with 'tescmd key deploy' first" — correct |
| **Keys exist, enrolled, but private key corrupted** | `tescmd charge start` | `SessionError` (ECDH fails) or crypto error | No specific handler — falls through to generic error |
| **Domain changed** | `tescmd key enroll` | Opens wrong enrollment URL | No detection of mismatch between .env domain and actual key URL |

### Problems

1. **Silent fallback is dangerous.** When `command_protocol=auto` and keys are missing, the code falls back to unsigned REST in `get_command_api()` at `_client.py:186`. The user has no idea their commands are being sent unsigned. For commands that require signing (VCSEC domain: lock/unlock), the unsigned REST path may fail with a confusing API error rather than a clear "you need keys" message.

2. **`KeyNotEnrolledError` gives wrong command.** `signed_command.py:125` says `tescmd key enroll {vin}` but the `key enroll` command doesn't accept a VIN. It should say `tescmd key enroll`.

3. **No `key enroll` error handler in `main.py`.** `KeyNotEnrolledError` is not handled in `_handle_known_error()`. It falls through to the generic exception handler, which just prints the raw error message. It should get the same treatment as `TierError` and `AuthError` — a friendly message with specific next steps.

4. **No diagnostic command.** There's no `tescmd key status` or `tescmd doctor` that checks the entire chain: keys exist locally → public key accessible at URL → domain matches → token has command scopes → key enrolled on vehicle. Users have to manually run `key show` + `key validate` + guess about enrollment.

5. **No way to detect whether a key is enrolled.** The code has no endpoint or check for "is my key enrolled on vehicle X?" The only way to find out is to try a signed command and see if it fails. The `vehicle_data` response may contain a key list, but there's no code to check it.

6. **Regenerating keys doesn't warn about re-enrollment.** `tescmd key generate --force` creates new keys, but doesn't warn that the old key is now orphaned on every vehicle where it was enrolled. The user must re-deploy AND re-enroll, but there's no guidance.

---

## Improvement Recommendations

### High Priority (broken behavior)

| # | Issue | Fix | Files |
|---|-------|-----|-------|
| **H1** | `KeyNotEnrolledError` references non-existent `key enroll {vin}` syntax | Change message to `tescmd key enroll` (no VIN) | `api/signed_command.py:125` |
| **H2** | `KeyNotEnrolledError` not handled in error handler | Add `KeyNotEnrolledError` case to `_handle_known_error()` with friendly Rich output and enrollment URL | `cli/main.py` |
| **H3** | Silent unsigned fallback when keys missing | When `protocol=auto` and a VCSEC command is attempted without keys, warn (or error) instead of silently falling back | `cli/_client.py` |
| **H4** | Readonly→full upgrade doesn't re-check OAuth scopes | Compare stored scopes vs. `DEFAULT_SCOPES` before skipping Phase 5 | `cli/setup.py` |

### Medium Priority (confusing UX)

| # | Issue | Fix | Files |
|---|-------|-----|-------|
| **M1** | Phase 6 summary repeats enrollment instructions even when Phase 3.5 already ran | Conditionally skip enrollment guidance in `_print_next_steps` if enrollment was offered | `cli/setup.py` |
| **M2** | `key generate --force` doesn't warn about re-enrollment | Add warning: "Existing key was enrolled on N vehicles. You must re-deploy and re-enroll." | `cli/key.py` |
| **M3** | No diagnostic/health-check command | Add `tescmd status` or `tescmd doctor` that validates the full chain (keys → URL → domain → scopes → enrollment) | New file or extend `cli/status.py` |
| **M4** | Setup enrollment step has no confirmation | Add "Press Enter after approving in Tesla app" prompt, then try a signed command to verify | `cli/setup.py` |

### Low Priority (polish)

| # | Issue | Fix | Files |
|---|-------|-----|-------|
| **L1** | No JSON mode for `tescmd setup` | Not critical — setup is inherently interactive. Document this limitation. | docs |
| **L2** | Phase numbering visible to user (3.5) | Rename to "Phase 4" and bump subsequent phases | `cli/setup.py` |
| **L3** | `_print_next_steps` doesn't mention `tescmd status` | Add status command to suggested commands | `cli/setup.py` |

---

## Error Message Audit

Current error messages and whether they correctly guide the user:

| Error | Current Message | Correct? | Suggested Fix |
|-------|----------------|----------|---------------|
| `TierError` | "This command requires 'full' tier setup. Run 'tescmd setup' to upgrade." | Yes | — |
| `AuthError` | "Authentication failed. Run 'tescmd auth login'." | Yes | — |
| `KeyNotEnrolledError` | "Key not enrolled on vehicle {vin}. Run 'tescmd key enroll {vin}' first." | **No** | Remove `{vin}`, add enrollment URL: `tescmd key enroll` |
| `ConfigError` (no keys + signed) | "command_protocol is 'signed' but no key pair found or tier is not 'full'." | Partial | Also mention `tescmd key generate` |
| `SessionError` | (no handler) | **No** | Add handler: "Session handshake failed. Your key may be corrupted or the vehicle's session expired. Try again, or regenerate with `tescmd key generate --force`." |
| Unsigned fallback | (silent) | **No** | At minimum, log a debug-level message. For VCSEC commands, error instead of falling back. |

---

## Recommended Implementation Order

1. **H1 + H2**: Fix `KeyNotEnrolledError` message and add handler (~15 min)
2. **H3**: Add VCSEC guard against silent unsigned fallback (~20 min)
3. **H4**: Add scope check in setup upgrade path (~20 min)
4. **M1**: Clean up Phase 6 duplicate enrollment messaging (~10 min)
5. **M3**: Add `tescmd doctor` diagnostic command (~45 min)
6. **M4**: Add enrollment confirmation to setup wizard (~20 min)
7. **M2**: Add re-enrollment warning to `key generate --force` (~15 min)
