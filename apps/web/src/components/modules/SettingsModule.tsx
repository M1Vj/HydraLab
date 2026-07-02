import { RefreshCcw, ShieldCheck, SlidersHorizontal, Trash2, WifiOff } from "lucide-react";
import { useMemo, useState } from "react";

import {
  DEFAULT_BROWSER_CAPTURE_SETTINGS,
  DEFAULT_SOURCE_DISCOVERY_SETTINGS,
  browserHistoryPermissionRequest,
  browserProviderEligibility,
  hostPermissionPromptChoices,
  nextBrowserBridgeConnection,
  sourceDiscoveryNetworkPosture,
  type BrowserCaptureSettings,
  type SourceDiscoverySettings,
} from "../../lib/hydra";
import { Switch } from "../ui/primitives";

export function SettingsModule() {
  const [settings, setSettings] = useState<BrowserCaptureSettings>(DEFAULT_BROWSER_CAPTURE_SETTINGS);
  const [discoverySettings, setDiscoverySettings] = useState<SourceDiscoverySettings>(DEFAULT_SOURCE_DISCOVERY_SETTINGS);
  const [connection, setConnection] = useState(settings.connectionStatus);
  const historyRequest = useMemo(() => browserHistoryPermissionRequest("Find prior browsing for this assistant request"), []);
  const provider = browserProviderEligibility(settings);
  const discoveryPosture = sourceDiscoveryNetworkPosture(discoverySettings);
  const hostChoices = hostPermissionPromptChoices("openreview.net");

  function setFlag<K extends keyof BrowserCaptureSettings>(key: K, value: BrowserCaptureSettings[K]) {
    setSettings((current) => ({ ...current, [key]: value }));
  }

  function simulateReconnect() {
    const next = nextBrowserBridgeConnection({ status: connection, attempt: connection === "connected" ? 0 : 1 }, "request-failed");
    setConnection(next.status);
    setSettings((current) => ({ ...current, connectionStatus: next.status }));
  }

  return (
    <div className="settings-module" aria-label="Browser capture settings">
      <section className="settings-group">
        <header>
          <ShieldCheck size={15} />
          <strong>Browser integration</strong>
        </header>
        <Switch
          checked={settings.integrationEnabled}
          onChange={(checked) => setFlag("integrationEnabled", checked)}
          label="Enable Chrome extension bridge"
        />
        <Switch
          checked={settings.g2LocalCapture}
          onChange={(checked) => setFlag("g2LocalCapture", checked)}
          label="G2 local browser capture"
        />
        <Switch
          checked={settings.browserPageTextToProvider}
          onChange={(checked) => setFlag("browserPageTextToProvider", checked)}
          label="Browser page text to provider"
        />
        <p className="helper-text">
          Local capture and provider send are separate. Browser page text remains provider-ineligible until this separate opt-in is enabled.
        </p>
        <div className="settings-status-grid">
          <span>Local capture</span>
          <strong>{provider.localCaptureEnabled ? "enabled" : "off"}</strong>
          <span>Provider eligibility</span>
          <strong>{provider.pageTextProviderEligible ? "enabled" : "off"}</strong>
        </div>
      </section>

      <section className="settings-group">
        <header>
          <SlidersHorizontal size={15} />
          <strong>Source discovery</strong>
        </header>
        <Switch
          checked={discoverySettings.offlineOnly}
          onChange={(checked) => setDiscoverySettings((current) => ({ ...current, offlineOnly: checked }))}
          label="Offline-only mode"
        />
        <Switch
          checked={discoverySettings.scholarlyApisEnabled}
          onChange={(checked) => setDiscoverySettings((current) => ({ ...current, scholarlyApisEnabled: checked }))}
          label="Allow scholarly metadata APIs"
        />
        <Switch
          checked={discoverySettings.automaticPdfDownload}
          onChange={(checked) => setDiscoverySettings((current) => ({ ...current, automaticPdfDownload: checked }))}
          label="Automatic open-PDF download"
        />
        <div className="settings-status-grid">
          <span>Discovery posture</span>
          <strong>{discoveryPosture.state}</strong>
          <span>Provider calls</span>
          <strong>{discoveryPosture.providerCallsAllowed ? "allowed" : "cache-only"}</strong>
        </div>
        <p className="helper-text">
          Auto PDF mode uses allowlisted domains, the 25 MB large-file threshold, storage checks and pause/cancel controls. Paywall, CAPTCHA and credential bypass are not supported.
        </p>
      </section>

      <section className="settings-group">
        <header>
          <SlidersHorizontal size={15} />
          <strong>Capture controls</strong>
        </header>
        <div className="control-grid">
          <button onClick={() => setFlag("capturePaused", !settings.capturePaused)}>
            {settings.capturePaused ? "Resume" : "Pause"}
          </button>
          <button onClick={() => setFlag("integrationEnabled", false)}>Disable</button>
          <button onClick={() => setFlag("reducedCapture", !settings.reducedCapture)}>Reduced capture</button>
          <button>
            <Trash2 size={13} /> Clear captured context
          </button>
        </div>
        <div className="host-lists">
          <section>
            <h3>Allowlist</h3>
            <span>arxiv.org</span>
            <span>openreview.net</span>
          </section>
          <section>
            <h3>Blocklist</h3>
            <span>banking.example</span>
            <span>chrome://*</span>
          </section>
        </div>
      </section>

      <section className="settings-group">
        <header>
          <WifiOff size={15} />
          <strong>Local connection</strong>
        </header>
        <div className={`connection-pill ${connection}`}>{connection}</div>
        <button onClick={simulateReconnect}>
          <RefreshCcw size={13} /> Re-read port file
        </button>
        <p className="helper-text">Reconnect uses capped backoff and re-reads the app-data runtime port file after backend restart.</p>
      </section>

      <section className="settings-group">
        <header>
          <ShieldCheck size={15} />
          <strong>First-use host prompt</strong>
        </header>
        <div className="permission-choice-list">
          {hostChoices.map((choice) => (
            <button key={choice.value}>{choice.label}</button>
          ))}
        </div>
        <p className="helper-text">No page text is captured until a host choice is made.</p>
      </section>

      <section className="settings-group">
        <header>
          <ShieldCheck size={15} />
          <strong>Browser history request</strong>
        </header>
        <p className="helper-text">{historyRequest.reason}</p>
        <div className="permission-choice-list">
          {historyRequest.choices.map((choice) => (
            <button key={choice}>{choice}</button>
          ))}
        </div>
      </section>
    </div>
  );
}
