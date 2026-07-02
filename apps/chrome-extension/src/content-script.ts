import "./chrome";
import type { PageCapture } from "./types";

function collectPageCapture(): Omit<PageCapture, "project_id" | "source_policy" | "browser_integration_enabled" | "g2_local_capture" | "browser_page_text_to_provider" | "host_permission" | "incognito" | "is_project_relevant"> {
  const selection = String(globalThis.getSelection?.() ?? "").slice(0, 12000);
  const bodyText = document.body?.innerText ?? "";
  const fields = Array.from(document.querySelectorAll("input, textarea, select"));
  const hasCredentialFields = fields.some((field) => {
    const input = field as HTMLInputElement;
    const name = `${input.type} ${input.name} ${input.id} ${input.autocomplete}`.toLowerCase();
    return name.includes("password") || name.includes("token") || name.includes("credential") || name.includes("cookie");
  });
  const hasPaymentFields = fields.some((field) => {
    const input = field as HTMLInputElement;
    const name = `${input.type} ${input.name} ${input.id} ${input.autocomplete}`.toLowerCase();
    return name.includes("cc-") || name.includes("credit") || name.includes("card") || name.includes("payment");
  });

  return {
    url: location.href,
    title: document.title,
    page_text: hasCredentialFields || hasPaymentFields ? "" : bodyText.slice(0, 64000),
    selection: hasCredentialFields || hasPaymentFields ? "" : selection,
    event_type: selection ? "selection" : "capture",
    has_credential_fields: hasCredentialFields,
    has_payment_fields: hasPaymentFields,
    metadata: {
      canonical_url: document.querySelector<HTMLLinkElement>('link[rel="canonical"]')?.href,
      doi: document.querySelector<HTMLMetaElement>('meta[name="citation_doi"]')?.content,
      pdf_url: document.querySelector<HTMLMetaElement>('meta[name="citation_pdf_url"]')?.content,
    },
    trust_level: "untrusted-external",
  };
}

chrome.runtime.onMessage.addListener((message, _sender, respond) => {
  if (!message || typeof message !== "object" || (message as { type?: string }).type !== "hydralab.contentCapture") {
    return false;
  }
  respond(collectPageCapture());
  return false;
});

