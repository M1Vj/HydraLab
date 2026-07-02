export type RuntimeDescriptor = {
  host: "127.0.0.1";
  port: number;
  scheme: "http";
  base_url: string;
  handshake_nonce: string;
};

export type BridgeStatus = "not-running" | "handshaking" | "connected" | "reconnecting" | "token-rejected";

export type CaptureSubset =
  | "smart-save"
  | "source-only"
  | "citation"
  | "snapshot"
  | "pdf"
  | "note"
  | "summarize-then-save"
  | "task"
  | "full-research-packet";

export type PageCapture = {
  project_id: string;
  url: string;
  title: string;
  page_text: string;
  selection: string;
  event_type: "capture" | "selection" | "navigation" | "snapshot" | "save";
  source_policy: "auto-source" | "context-only" | "always-ask" | "blocked";
  browser_integration_enabled: boolean;
  g2_local_capture: boolean;
  browser_page_text_to_provider: boolean;
  host_permission: "allow-for-project" | "always-allow-host" | "blocked" | "unknown";
  incognito: boolean;
  has_credential_fields: boolean;
  has_payment_fields: boolean;
  is_project_relevant: boolean;
  metadata: Record<string, unknown>;
  trust_level: "untrusted-external";
};

export type BridgeMessage =
  | { type: "hydralab.status" }
  | { type: "hydralab.configureRuntime"; descriptor: RuntimeDescriptor }
  | { type: "hydralab.capture"; subset: CaptureSubset }
  | { type: "hydralab.contentCapture" };

