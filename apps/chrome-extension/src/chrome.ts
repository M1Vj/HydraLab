export {};

declare global {
  const chrome: {
    action: {
      setBadgeText(details: { text: string }): Promise<void>;
      setBadgeBackgroundColor(details: { color: string }): Promise<void>;
    };
    permissions: {
      request(details: { origins?: string[] }): Promise<boolean>;
    };
    runtime: {
      onMessage: {
        addListener(listener: (message: unknown, sender: unknown, respond: (response?: unknown) => void) => boolean | void): void;
      };
      sendMessage(message: unknown): Promise<unknown>;
    };
    scripting: {
      executeScript(details: { target: { tabId: number }; files?: string[] }): Promise<unknown>;
    };
    storage: {
      local: {
        get(keys?: string | string[] | Record<string, unknown> | null): Promise<Record<string, unknown>>;
        set(values: Record<string, unknown>): Promise<void>;
      };
    };
    tabs: {
      query(queryInfo: { active: boolean; currentWindow: boolean }): Promise<Array<{ id?: number; url?: string; title?: string; incognito?: boolean }>>;
      sendMessage(tabId: number, message: unknown): Promise<unknown>;
    };
  };
}
