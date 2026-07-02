import { afterEach, describe, expect, test } from "bun:test";
import { createApiClient, HydraApiError } from "./api";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("api client error normalization", () => {
  test("maps 401/403 to permission denied", async () => {
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: "Forbidden" }), { status: 403, headers: { "content-type": "application/json" } });
    const client = createApiClient("/api", 100);

    await expect(client.get("/api/settings")).rejects.toMatchObject({ kind: "permission-denied", status: 403 });
  });

  test("maps user-initiated consent errors to consent-required", async () => {
    globalThis.fetch = async () =>
      new Response(JSON.stringify({ detail: { reason: "user-initiated-save-required" } }), { status: 403, headers: { "content-type": "application/json" } });
    const client = createApiClient("/api", 100);

    await expect(client.post("/api/sources/save", {})).rejects.toMatchObject({ kind: "consent-required", status: 403 });
  });

  test("maps thrown fetch errors to network", async () => {
    globalThis.fetch = async () => {
      throw new Error("offline");
    };
    const client = createApiClient("/api", 100);

    await expect(client.get("/api/events")).rejects.toBeInstanceOf(HydraApiError);
    await expect(client.get("/api/events")).rejects.toMatchObject({ kind: "network" });
  });
});
