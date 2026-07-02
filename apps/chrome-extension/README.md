# HydraLab Chrome Extension

Phase 1 uses a Chrome MV3 extension for signed-in or institutional browsing that cannot be represented honestly in the in-app iframe/PDF/snapshot preview.

## Dev Load

1. Start the HydraLab backend so `<app-data>/runtime/backend.json` exists.
2. Build the extension:

   ```bash
   bun run --filter @hydra/chrome-extension build
   ```

3. Open `chrome://extensions`, enable Developer mode, choose **Load unpacked**, and select `apps/chrome-extension`.
4. Open the extension popup and click **Connect to local HydraLab**.
5. Paste the contents of `<app-data>/runtime/backend.json` when using a non-default port. The dev default is `http://127.0.0.1:8765` with nonce `dev-handshake`.

## Permissions

- `activeTab`: lets HydraLab capture only the active tab after the user clicks Save.
- `optional_host_permissions`: requested per host only after the user chooses to allow that host.
- `storage`: stores local host choices and the loopback runtime descriptor.
- `scripting`: injects the capture script after a user action.

The extension does not request all-sites access on install and does not use Chrome Native Messaging.

## Bridge Contract

The service worker exchanges the runtime descriptor `handshake_nonce` for a bearer token at `/api/browser/handshake`, then calls only the narrow browser bridge endpoints:

- `/api/browser/capture`
- `/api/browser/selection`
- `/api/browser/propose-source`

Every payload is sent with `trust_level: "untrusted-external"`. Browser page text is local G2 capture only; it is not provider-eligible unless the separate browser-page-text provider opt-in is enabled in HydraLab Settings.

