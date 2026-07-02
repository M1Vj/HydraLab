import { useEffect, useState } from "react";
import { Send } from "lucide-react";
import { api, type ChatConversation, type ChatMessage } from "../../lib/api";
import type { PanelComponentProps } from "../panelRegistry";
import { EmptyState, FailureState, LoadingState, PanelScaffold } from "./PanelState";

export function ResearchChatPanel({ announce }: PanelComponentProps) {
  const [conversations, setConversations] = useState<ChatConversation[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    void loadConversations();
  }, []);

  async function loadConversations() {
    setLoading(true);
    setError(null);
    try {
      const payload = await api.get<{ conversations: ChatConversation[] }>("/api/chat/conversations");
      setConversations(payload.conversations);
      if (payload.conversations[0]) {
        setConversationId(payload.conversations[0].id);
        const messagePayload = await api.get<{ messages: ChatMessage[] }>(`/api/chat/conversations/${payload.conversations[0].id}/messages`);
        setMessages(messagePayload.messages);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setLoading(false);
    }
  }

  async function sendMessage() {
    const message = input.trim();
    if (!message || streaming) return;
    setInput("");
    setStreaming(true);
    setError(null);
    setMessages((current) => [...current, { id: `local-${Date.now()}`, role: "user", content: message }, { id: "streaming", role: "assistant", content: "" }]);
    try {
      await api.stream("/api/chat/completions", { conversation_id: conversationId, message }, (event) => {
        const item = event as { type?: string; content?: string; conversation_id?: string };
        if (item.type === "message") {
          setMessages((current) => current.map((row) => (row.id === "streaming" ? { ...row, content: row.content + (item.content ?? "") } : row)));
        }
        if (item.type === "status") announce(item.content ?? "Chat status update");
        if (item.type === "done" && item.conversation_id) setConversationId(item.conversation_id);
      });
      void loadConversations();
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
      setMessages((current) => current.map((row) => (row.id === "streaming" ? { ...row, content: `${row.content}\n\n[interrupted]` } : row)));
    } finally {
      setStreaming(false);
    }
  }

  if (loading) return <LoadingState title="Loading conversations" />;
  if (error) return <FailureState error={error} onRetry={loadConversations} />;

  return (
    <PanelScaffold title="Research Chat">
      <div className="chat-layout">
        <aside className="conversation-list" aria-label="Conversations">
          {conversations.length === 0 ? <span>No conversations</span> : conversations.map((conversation) => <button key={conversation.id}>{conversation.title}</button>)}
        </aside>
        <section className="chat-thread" aria-live="polite">
          {messages.length === 0 ? (
            <EmptyState title="Default project chat empty" message="Ask research questions grounded in the active workspace." action="Ask the assistant" onAction={() => undefined} />
          ) : (
            messages.map((message) => (
              <article key={message.id} className={`chat-message ${message.role}`}>
                <strong>{message.role}</strong>
                <p>{message.content}</p>
              </article>
            ))
          )}
        </section>
        <form
          className="chat-composer"
          onSubmit={(event) => {
            event.preventDefault();
            void sendMessage();
          }}
        >
          <textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder="Ask about notes, sources, claims, or citations" />
          <button type="submit" disabled={streaming}>
            <Send size={14} /> {streaming ? "Streaming" : "Send"}
          </button>
        </form>
      </div>
    </PanelScaffold>
  );
}
