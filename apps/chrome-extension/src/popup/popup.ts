import "../chrome";
import type { CaptureSubset, RuntimeDescriptor } from "../types";

const statusEl = document.querySelector<HTMLSpanElement>("#status")!;
const resultEl = document.querySelector<HTMLPreElement>("#result")!;
const saveButton = document.querySelector<HTMLButtonElement>("#save")!;
const configureButton = document.querySelector<HTMLButtonElement>("#configure")!;
const subsetSelect = document.querySelector<HTMLSelectElement>("#subset")!;

async function refreshStatus() {
  const response = (await chrome.runtime.sendMessage({ type: "hydralab.status" })) as { status?: string };
  statusEl.textContent = response.status ?? "not-running";
}

saveButton.addEventListener("click", async () => {
  resultEl.textContent = "capturing active tab...";
  const response = await chrome.runtime.sendMessage({
    type: "hydralab.capture",
    subset: subsetSelect.value as CaptureSubset,
  });
  resultEl.textContent = JSON.stringify(response, null, 2);
  await refreshStatus();
});

configureButton.addEventListener("click", async () => {
  const descriptorText = prompt("Paste <app-data>/runtime/backend.json contents, or leave blank for 127.0.0.1:8765 dev defaults.");
  let descriptor: RuntimeDescriptor | undefined;
  if (descriptorText?.trim()) {
    descriptor = JSON.parse(descriptorText) as RuntimeDescriptor;
  }
  const response = await chrome.runtime.sendMessage({
    type: "hydralab.configureRuntime",
    descriptor: descriptor ?? {
      host: "127.0.0.1",
      port: 8765,
      scheme: "http",
      base_url: "http://127.0.0.1:8765",
      handshake_nonce: "dev-handshake",
    },
  });
  resultEl.textContent = JSON.stringify(response, null, 2);
  await refreshStatus();
});

refreshStatus();

