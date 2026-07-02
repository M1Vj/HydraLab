# HydraLab macOS Release Runbook

HydraLab remains source/dev-run first. This branch adds testable updater and release scaffolding only; this machine has no Apple Developer credentials, so no real `tauri build`, `codesign`, or `xcrun notarytool` command was executed.

## Startup Path Audit

| Surface | Startup path | Verdict | Notes |
| --- | --- | --- | --- |
| `apps/web` dev server | Vite default `http://localhost:5173` | Packaging-safe | Tauri uses it only as `devUrl`; packaged builds load `apps/web/dist`. |
| `apps/web/dist` | Static frontend output | Packaging-safe | `frontendDist` points to the built output, not an install-relative project path. |
| `backend/hydra/serve.py` | Runtime-managed local backend with injected port | Packaging-safe | Port comes from runtime/env; no packaged app install path is assumed. |
| `backend/hydra/storage/app_data.py` | `HYDRALAB_APP_DATA_ROOT` override or user app-data root | Packaging-safe | App state remains outside the app bundle. |
| `backend/hydra/settings/toml_config.py` | Global `settings.toml` | Packaging-safe | Updater preferences live in `[updater]`, migrated in place. |
| `backend/hydra/storage/runtime.py` | Single-instance runtime lock | Packaging-safe | DEC-10 process lock, not a per-operation write lock. |
| `backend/hydra/services/git/service.py` | Synchronous Git subprocess calls against project root | To-fix later | This branch defines the updater tracker surface; future branches should wrap Git operations with it. |

## Packaging Shell Decision

HydraLab selects Tauri first and does not add Electron. Tauri keeps the native shell light and leaves the backend/frontend boundary explicit. The scaffold lives under `apps/desktop/` and points at `apps/web`.

Electron fallback criteria:

- HydraLab requires bundled Chromium or bundled Node APIs that cannot be cleanly replaced through Tauri/WebView boundaries.
- Tauri WebView or backend sidecar friction blocks required offline-first startup, update, or accessibility behavior after a real packaging spike.
- A signed/notarized Tauri build cannot preserve project folders outside the install location without brittle native workarounds.

## Exact Commands

Local web build:

```bash
cd apps/web && bun run typecheck && bun run build
```

Local Tauri build, documented only:

```bash
cd apps/desktop && HYDRALAB_PACKAGED_BUILD=1 bun run build
```

Sign the built app, documented only:

```bash
codesign --force --deep --options runtime --timestamp --sign "$APPLE_DEVELOPER_ID" "target/release/bundle/macos/HydraLab.app"
```

Notarize and staple, documented only:

```bash
xcrun notarytool submit "target/release/bundle/dmg/HydraLab_0.1.0_aarch64.dmg" --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" --password "$APPLE_NOTARIZATION_PASSWORD" --wait
xcrun stapler staple "target/release/bundle/macos/HydraLab.app"
```

Validate simulated release artifact before channel upload:

```bash
python scripts/package-macos.py /path/to/release-manifest.json
```

Publish channel metadata:

```bash
python scripts/release.py --channel stable --version 0.1.0 --artifact HydraLab-0.1.0-stable.dmg --previous-installer HydraLab-0.0.9-stable.dmg --out releases/stable/latest.json
python scripts/release.py --channel preview --version 0.1.0 --artifact HydraLab-0.1.0-preview.dmg --previous-installer HydraLab-0.0.9-preview.dmg --out releases/preview/latest.json
python scripts/release.py --channel dev --version 0.1.0 --artifact HydraLab-0.1.0-dev.dmg --previous-installer HydraLab-0.0.9-dev.dmg --out releases/dev/latest.json
```

Rollback:

```bash
python scripts/release.py --channel stable --version 0.0.9 --artifact HydraLab-0.0.9-stable.dmg --previous-installer HydraLab-0.1.0-stable.dmg --out releases/stable/latest.json
```

## CI Gate

The macOS release workflow runs this before any packaging/signing step:

```bash
python scripts/license_gate.py --evidence release-evidence/license-gate.json
```

The gate reads `ATTRIBUTION.md`, filters `bundled-dependency` rows, fails on AGPL/GPL/CPAL or unknown SPDX identifiers, and passes the current cleared register.

## Updater Behavior

- Channels are exactly `stable`, `preview`, and `dev`.
- Auto-checks are disabled by `[updater].auto_check_enabled = false`.
- Update checks are inert unless `HYDRALAB_PACKAGED_BUILD=1`.
- Install is refused while `agent_run`, `conversion`, `git_operation`, or `write_operation` is active.
- Binary app updates do not mutate `[providers]`, `[skills]`, `[assistant]`, provider settings, or agent mode policy records without a user-visible policy.

## Open Clarifications

- [NEEDS CLARIFICATION: update-server hosting/endpoint for stable, preview, and dev channels]
- [NEEDS CLARIFICATION: signing-key provenance and final Tauri updater public key for channel trust]
- [NEEDS CLARIFICATION: rollback UX should auto-revert immediately or prompt the user to reinstall the preserved previous installer]
