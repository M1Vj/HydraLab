import "./chrome";
import type { BridgeMessage, BridgeStatus, CaptureSubset, PageCapture, RuntimeDescriptor } from "./types";

const DEFAULT_PROJECT_ID = "active-project";
const DEFAULT_DESCRIPTOR: RuntimeDescriptor = {
  host: "127.0.0.1",
  port: 8765,
  scheme: "http",
  base_url: "http://127.0.0.1:8765",
  handshake_nonce: "dev-handshake",
};

const subsetPolicy: Record<CaptureSubset, PageCapture["source_policy"]> = {
  "smart-save": "auto-source",
  "source-only": "auto-source",
  citation: "always-ask",
  snapshot: "context-only",
  pdf: "auto-source",
  note: "always-ask",
  "summarize-then-save": "always-ask",
  task: "always-ask",
  "full-research-packet": "auto-source",
};

let token: string | null = null;
let status: BridgeStatus = "not-running";
let reconnectAttempt = 0;

async function setStatus(next: BridgeStatus) {
  status = next;
  await chrome.storage.local.set({ bridgeStatus: status });
  await chrome.action.setBadgeText({ text: next === "connected" ? "" : "!" });
  await chrome.action.setBadgeBackgroundColor({ color: next === "connected" ? "#3fb950" : "#d29922" });
}

async function runtimeDescriptor(): Promise<RuntimeDescriptor> {
  const stored = await chrome.storage.local.get({ runtimeDescriptor: DEFAULT_DESCRIPTOR });
  return (stored.runtimeDescriptor as RuntimeDescriptor) || DEFAULT_DESCRIPTOR;
}

async function handshake(): Promise<string> {
  await setStatus("handshaking");
  const descriptor = await runtimeDescriptor();
  const response = await fetch(`${descriptor.base_url}/api/browser/handshake`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ handshake_nonce: descriptor.handshake_nonce }),
  });
  if (!response.ok) {
    await setStatus("not-running");
    throw new Error(`HydraLab handshake failed: ${response.status}`);
  }
  const payload = (await response.json()) as { token: string };
  token = payload.token;
  reconnectAttempt = 0;
  await setStatus("connected");
  return token;
}

async function bridgeFetch(path: string, payload: unknown): Promise<unknown> {
  const descriptor = await runtimeDescriptor();
  const bearer = token ?? (await handshake());
  const response = await fetch(`${descriptor.base_url}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${bearer}`,
    },
    body: JSON.stringify(payload),
  });
  if (response.status === 401) {
    token = null;
    await reconnect();
    throw new Error("HydraLab token rejected; reconnecting");
  }
  if (!response.ok) {
    throw new Error(`HydraLab bridge request failed: ${response.status}`);
  }
  return response.json();
}

async function reconnect() {
  reconnectAttempt += 1;
  await setStatus("reconnecting");
  const delay = Math.min(10000, 250 * 2 ** Math.max(0, reconnectAttempt - 1));
  await new Promise((resolve) => setTimeout(resolve, delay));
  await handshake();
}

async function activeTabCapture(subset: CaptureSubset): Promise<unknown> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url) throw new Error("No active tab");
  const origin = new URL(tab.url).origin;
  const hostPermission = await ensureHostPermission(origin);
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["dist/content-script.js"] });
  const content = (await chrome.tabs.sendMessage(tab.id, { type: "hydralab.contentCapture" })) as Omit<PageCapture, "project_id" | "source_policy" | "browser_integration_enabled" | "g2_local_capture" | "browser_page_text_to_provider" | "host_permission" | "incognito" | "is_project_relevant">;
  const payload: PageCapture = {
    ...content,
    project_id: DEFAULT_PROJECT_ID,
    source_policy: subsetPolicy[subset],
    browser_integration_enabled: true,
    g2_local_capture: hostPermission !== "blocked",
    browser_page_text_to_provider: false,
    host_permission: hostPermission,
    incognito: Boolean(tab.incognito),
    is_project_relevant: true,
  };
  return bridgeFetch(subset === "task" || subset === "note" || subset === "summarize-then-save" ? "/api/browser/propose-source" : "/api/browser/capture", payload);
}

async function ensureHostPermission(origin: string): Promise<PageCapture["host_permission"]> {
  const stored = await chrome.storage.local.get({ hostPermissions: {} });
  const hostPermissions = stored.hostPermissions as Record<string, PageCapture["host_permission"]>;
  if (hostPermissions[origin]) return hostPermissions[origin];
  const granted = await chrome.permissions.request({ origins: [`${origin}/*`] });
  const choice: PageCapture["host_permission"] = granted ? "allow-for-project" : "blocked";
  await chrome.storage.local.set({ hostPermissions: { ...hostPermissions, [origin]: choice } });
  return choice;
}

chrome.runtime.onMessage.addListener((message, _sender, respond) => {
  const msg = message as BridgeMessage;
  if (msg.type === "hydralab.status") {
    respond({ status });
    return false;
  }
  if (msg.type === "hydralab.configureRuntime") {
    chrome.storage.local.set({ runtimeDescriptor: msg.descriptor }).then(() => handshake().then(respond).catch((error) => respond({ error: String(error) })));
    return true;
  }
  if (msg.type === "hydralab.capture") {
    activeTabCapture(msg.subset).then(respond).catch((error) => respond({ error: String(error) }));
    return true;
  }
  return false;
});

