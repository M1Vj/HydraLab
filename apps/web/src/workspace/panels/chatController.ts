import { api, type ApiClient, type Chat, type ChatMessage, type ContextRef, type SendScopeResult } from "../../lib/api";

export type StreamStatus = "idle" | "streaming" | "done" | "blocked" | "error";

export type StreamState = {
  status: StreamStatus;
  assistantContent: string;
  statusLine: string;
  blockedReason: string | null;
  blockedKind: string | null;
  chatId: string | null;
  messageId: string | null;
};

export type StreamEvent = {
  type?: string;
  content?: string;
  reason?: string;
  status?: string;
  kind?: string;
  chat_id?: string;
  message_id?: string;
};

export function initialStreamState(chatId: string | null = null): StreamState {
  return {
    status: "idle",
    assistantContent: "",
    statusLine: "",
    blockedReason: null,
    blockedKind: null,
    chatId,
    messageId: null,
  };
}

/** Pure reducer for the assistant SSE stream — drives streaming render + states. */
export function reduceStreamEvent(state: StreamState, event: StreamEvent): StreamState {
  switch (event.type) {
    case "status":
      return { ...state, status: "streaming", statusLine: event.content ?? state.statusLine };
    case "message":
      return { ...state, status: "streaming", assistantContent: state.assistantContent + (event.content ?? "") };
    case "blocked":
      return {
        ...state,
        status: "blocked",
        blockedReason: event.reason ?? "Send blocked",
        blockedKind: event.status ?? "blocked",
      };
    case "budget":
      return { ...state, status: "blocked", blockedReason: event.reason ?? "Budget exceeded", blockedKind: "budget-exceeded" };
    case "error":
      return { ...state, status: "error", blockedReason: event.reason ?? "Assistant error" };
    case "done":
      return { ...state, status: "done", chatId: event.chat_id ?? state.chatId, messageId: event.message_id ?? state.messageId };
    default:
      return state;
  }
}

export function isConsentBlocked(state: StreamState): boolean {
  return state.status === "blocked" && (state.blockedKind === "offline-blocked" || state.blockedKind === "hard-blocked");
}

/** Build a context_refs payload from picker selections. */
export function buildContextRefs(selections: ContextRef[]): ContextRef[] {
  return selections
    .filter((ref) => ref.type && (ref.id_or_path || ref.label))
    .map((ref) => ({
      type: ref.type,
      id_or_path: ref.id_or_path,
      label: ref.label ?? ref.id_or_path,
      locator: ref.locator ?? {},
      text: ref.text ?? "",
    }));
}

export async function fetchChats(projectId: string, client: ApiClient = api): Promise<Chat[]> {
  const payload = await client.get<{ chats: Chat[] }>(`/api/chats?project_id=${encodeURIComponent(projectId)}`);
  return payload.chats;
}

export async function fetchMessages(chatId: string, client: ApiClient = api): Promise<ChatMessage[]> {
  const payload = await client.get<{ messages: ChatMessage[] }>(`/api/chats/${encodeURIComponent(chatId)}/messages`);
  return payload.messages;
}

export async function createChat(projectId: string, name: string, client: ApiClient = api): Promise<Chat> {
  const payload = await client.post<{ chat: Chat }>("/api/chats", { project_id: projectId, name });
  return payload.chat;
}

export async function renameChat(chatId: string, name: string, client: ApiClient = api): Promise<Chat> {
  const payload = await client.patch<{ chat: Chat }>(`/api/chats/${encodeURIComponent(chatId)}`, { name });
  return payload.chat;
}

export async function archiveChat(chatId: string, archived: boolean, client: ApiClient = api): Promise<Chat> {
  const payload = await client.patch<{ chat: Chat }>(`/api/chats/${encodeURIComponent(chatId)}`, { archived });
  return payload.chat;
}

export async function searchChats(projectId: string, query: string, client: ApiClient = api): Promise<Chat[]> {
  const payload = await client.get<{ chats: Chat[] }>(
    `/api/chats/search?project_id=${encodeURIComponent(projectId)}&q=${encodeURIComponent(query)}`,
  );
  return payload.chats;
}

/** Ask the backend which items would actually leave the machine (pre-send surface). */
export async function previewSendScope(contextRefs: ContextRef[], client: ApiClient = api): Promise<SendScopeResult> {
  return client.post<SendScopeResult>("/api/assistant/send-scope", { context_refs: contextRefs });
}
