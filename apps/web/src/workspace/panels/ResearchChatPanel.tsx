import { useEffect, useMemo, useState } from "react";
import { Info, LockKeyhole, Pause, Paperclip, Play, Plus, Search, Send, ShieldQuestion, X } from "lucide-react";
import { api, type AgentApproval, type AssistantModes, type Chat, type ChatMessage, type ContextRef, type SendScopeResult } from "../../lib/api";
import type { PanelComponentProps } from "../panelRegistry";
import { usePrompt } from "../../components/ui/usePrompt";
import { fetchApprovals, fetchModes, modeLabel, resolveApproval } from "./agentController";
import { EmptyState, FailureState, LoadingState, PanelScaffold } from "./PanelState";
import {
  archiveChat,
  buildContextRefs,
  createChat,
  fetchChats,
  fetchMessages,
  initialStreamState,
  isConsentBlocked,
  previewSendScope,
  reduceStreamEvent,
  renameChat,
  searchChats,
  type StreamEvent,
  type StreamState,
} from "./chatController";

const PROJECT_ID = "default";

const PICKER_TYPES: Array<{ type: string; label: string }> = [
  { type: "active_file", label: "Active file" },
  { type: "selection", label: "Selection" },
  { type: "attachment", label: "Attached item" },
  { type: "pdf", label: "PDF" },
  { type: "source", label: "Source" },
  { type: "note", label: "Note" },
  { type: "task", label: "Task" },
  { type: "browser_event", label: "Browser event" },
];

/** Active Agent Access Mode + live/pause control + pending approval prompts. */
function AgentRunBar({ streaming, announce }: { streaming: boolean; announce: (message: string) => void }) {
  const [modes, setModes] = useState<AssistantModes | null>(null);
  const [approvals, setApprovals] = useState<AgentApproval[]>([]);
  const [paused, setPaused] = useState(false);

  async function loadApprovals() {
    try {
      setApprovals(await fetchApprovals(PROJECT_ID));
    } catch {
      setApprovals([]);
    }
  }

  useEffect(() => {
    void fetchModes(PROJECT_ID).then(setModes).catch(() => setModes(null));
    void loadApprovals();
  }, []);

  async function decide(id: string, decision: "approved" | "rejected") {
    await resolveApproval(id, decision);
    announce(decision === "approved" ? "Approved proposed change" : "Rejected proposed change; workspace unchanged");
    await loadApprovals();
  }

  if (!modes) return null;
  const active = modes.default_mode;
  return (
    <div className="agent-run-bar" aria-label="Agent run status">
      {modes.provider_configured === false && !modes.offline_only && (
        <div className="assistant-placeholder-notice" role="status">
          <Info size={13} aria-hidden />
          <span>No AI provider configured — replies are local placeholders. Add a provider key in Settings to get real answers.</span>
        </div>
      )}
      <div className="agent-mode-indicator" role="status">
        <span className="agent-mode-dot" aria-hidden />
        <span>Mode: <strong>{modeLabel(active)}</strong></span>
        {active === "full_access" && (
          <button
            type="button"
            className="agent-pause-control"
            aria-pressed={paused}
            onClick={() => { setPaused((value) => !value); announce(paused ? "Resumed run" : "Paused run"); }}
          >
            {paused ? <Play size={13} /> : <Pause size={13} />} {paused ? "Resume" : "Pause"}
          </button>
        )}
        {streaming && <span className="agent-live-tag">live</span>}
      </div>
      {approvals.length > 0 && (
        <ul className="agent-approval-list" aria-label="Pending approvals">
          {approvals.map((approval) => (
            <li key={approval.id} className="agent-approval">
              <ShieldQuestion size={13} aria-hidden />
              <span className="approval-summary">{approval.summary || approval.action_kind}</span>
              {approval.target_ref && <span className="approval-target">{approval.target_ref}</span>}
              <div className="approval-actions">
                <button type="button" onClick={() => void decide(approval.id, "approved")}>Accept</button>
                <button type="button" onClick={() => void decide(approval.id, "rejected")}>Reject</button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ResearchChatPanel({ announce }: PanelComponentProps) {
  const [chats, setChats] = useState<Chat[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatId, setChatId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [stream, setStream] = useState<StreamState>(() => initialStreamState());
  const [searchTerm, setSearchTerm] = useState("");
  const [refs, setRefs] = useState<ContextRef[]>([]);
  const [scope, setScope] = useState<SendScopeResult | null>(null);
  const [pickerType, setPickerType] = useState(PICKER_TYPES[0].type);
  const [pickerValue, setPickerValue] = useState("");
  const { prompt, dialog } = usePrompt();

  const streaming = stream.status === "streaming";
  const consentBlocked = isConsentBlocked(stream);

  useEffect(() => {
    void loadChats();
  }, []);

  async function loadChats() {
    setLoading(true);
    setError(null);
    try {
      const list = await fetchChats(PROJECT_ID);
      setChats(list);
      const first = list[0]?.id ?? null;
      setChatId(first);
      if (first) setMessages(await fetchMessages(first));
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setLoading(false);
    }
  }

  async function selectChat(id: string) {
    setChatId(id);
    setStream(initialStreamState(id));
    setMessages(await fetchMessages(id));
  }

  async function onCreateChat() {
    const name = await prompt({ title: "New chat name", defaultValue: "New chat", confirmLabel: "Create" });
    if (!name) return;
    const chat = await createChat(PROJECT_ID, name);
    await loadChats();
    void selectChat(chat.id);
  }

  async function onRename(id: string) {
    const name = await prompt({ title: "Rename chat", confirmLabel: "Rename" });
    if (!name) return;
    await renameChat(id, name);
    await loadChats();
  }

  async function onArchive(id: string, archived: boolean) {
    await archiveChat(id, archived);
    await loadChats();
  }

  async function onSearch(term: string) {
    setSearchTerm(term);
    if (!term.trim()) {
      await loadChats();
      return;
    }
    setChats(await searchChats(PROJECT_ID, term));
  }

  function addRef() {
    if (!pickerValue.trim()) return;
    setRefs((current) => [...current, { type: pickerType, id_or_path: pickerValue.trim(), label: pickerValue.trim() }]);
    setPickerValue("");
    setScope(null);
  }

  function removeRef(index: number) {
    setRefs((current) => current.filter((_, i) => i !== index));
    setScope(null);
  }

  async function reviewSend() {
    try {
      setScope(await previewSendScope(buildContextRefs(refs)));
      announce("Reviewed what will be sent to the provider");
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    }
  }

  async function sendMessage() {
    const message = input.trim();
    if (!message || streaming || !chatId) return;
    setInput("");
    const contextRefs = buildContextRefs(refs);
    setMessages((current) => [
      ...current,
      { id: `local-${Date.now()}`, role: "user", content: message, context_refs: contextRefs },
      { id: "streaming", role: "assistant", content: "" },
    ]);
    let next = initialStreamState(chatId);
    setStream(next);
    try {
      await api.stream("/api/chat/completions", { chat_id: chatId, project_id: PROJECT_ID, message, context_refs: contextRefs }, (event) => {
        next = reduceStreamEvent(next, event as StreamEvent);
        setStream(next);
        const evt = event as { type?: string; content?: string };
        if (evt.type === "status" && evt.content) announce(evt.content);
        if (evt.type === "message") {
          setMessages((current) => current.map((row) => (row.id === "streaming" ? { ...row, content: next.assistantContent } : row)));
        }
      });
      if (next.status === "blocked") {
        setMessages((current) => current.filter((row) => row.id !== "streaming"));
        announce(next.blockedReason ?? "Send blocked");
      }
      setRefs([]);
      setScope(null);
      await loadMessagesOnly(chatId);
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    }
  }

  async function loadMessagesOnly(id: string) {
    try {
      setMessages(await fetchMessages(id));
    } catch {
      /* keep optimistic view */
    }
  }

  const visibleChats = useMemo(() => chats, [chats]);

  if (loading) return <LoadingState title="Loading chats" />;
  if (error) return <FailureState error={error} onRetry={loadChats} />;

  return (
    <PanelScaffold title="Assistant">
      <div className="chat-layout">
        <aside className="conversation-list" aria-label="Chats">
          <div className="chat-list-header">
            <button onClick={() => void onCreateChat()} aria-label="New chat"><Plus size={14} /> New</button>
          </div>
          <label className="chat-search">
            <Search size={12} aria-hidden />
            <input value={searchTerm} onChange={(event) => void onSearch(event.target.value)} placeholder="Search chats" aria-label="Search chats" />
          </label>
          {visibleChats.length === 0 ? (
            <span>No chats</span>
          ) : (
            visibleChats.map((chat) => (
              <div key={chat.id} className={`chat-list-row ${chat.id === chatId ? "active" : ""}`}>
                <button onClick={() => void selectChat(chat.id)}>
                  {chat.name}
                  {chat.archived && <span className="chat-archived-badge"> (archived)</span>}
                </button>
                <div className="chat-row-actions">
                  <button onClick={() => void onRename(chat.id)} title="Rename">✎</button>
                  <button onClick={() => void onArchive(chat.id, !chat.archived)} title={chat.archived ? "Unarchive" : "Archive"}>
                    {chat.archived ? "↩" : "🗄"}
                  </button>
                </div>
              </div>
            ))
          )}
        </aside>

        <section className="chat-thread" aria-live="polite">
          <AgentRunBar streaming={streaming} announce={announce} />
          {messages.length === 0 ? (
            <EmptyState title="Default project chat" message="Ask research questions grounded in the active workspace." />
          ) : (
            messages.map((message) => (
              <article key={message.id} className={`chat-message ${message.role}`}>
                <strong>{message.role}</strong>
                <p>{message.content}</p>
                {message.context_refs && message.context_refs.length > 0 && (
                  <ul className="chat-refs" aria-label="Context references">
                    {message.context_refs.map((ref, index) => (
                      <li key={index}>{ref.type}: {ref.label ?? ref.id_or_path}</li>
                    ))}
                  </ul>
                )}
              </article>
            ))
          )}
          {stream.statusLine && streaming && <p className="chat-status-line" role="status">{stream.statusLine}</p>}
          {consentBlocked && (
            <div className="panel-state permission-denied" role="alert">
              <LockKeyhole size={16} aria-hidden />
              <strong>Send blocked</strong>
              <span>{stream.blockedReason}</span>
            </div>
          )}
        </section>

        <div className="chat-composer-area">
          <div className="context-picker" aria-label="Context picker">
            <div className="context-picker-controls">
              <select value={pickerType} onChange={(event) => setPickerType(event.target.value)} aria-label="Context type">
                {PICKER_TYPES.map((option) => (
                  <option key={option.type} value={option.type}>{option.label}</option>
                ))}
              </select>
              <input value={pickerValue} onChange={(event) => setPickerValue(event.target.value)} placeholder="id or path" aria-label="Context reference" />
              <button onClick={addRef} aria-label="Attach context"><Paperclip size={13} /> Attach</button>
            </div>
            {refs.length > 0 && (
              <ul className="context-ref-list" aria-label="Attached context">
                {refs.map((ref, index) => (
                  <li key={index}>
                    {ref.type}: {ref.label ?? ref.id_or_path}
                    <button onClick={() => removeRef(index)} aria-label={`Remove ${ref.label ?? ref.id_or_path}`}><X size={11} /></button>
                  </li>
                ))}
              </ul>
            )}
            {refs.length > 0 && <button className="review-send" onClick={() => void reviewSend()}>Review what will be sent</button>}
            {scope && (
              <div className="send-scope-surface" aria-label="What will be sent">
                <strong>What will be sent</strong>
                <ul>
                  {scope.included.map((item, index) => (
                    <li key={`in-${index}`} className="scope-included">✓ {item.label ?? item.id_or_path}</li>
                  ))}
                  {scope.excluded.map((item, index) => (
                    <li key={`ex-${index}`} className="scope-excluded">✕ {item.label ?? item.id_or_path} — {item.reason}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          <form
            className="chat-composer"
            onSubmit={(event) => {
              event.preventDefault();
              void sendMessage();
            }}
          >
            <textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder="Ask about notes, sources, claims, or citations" aria-label="Message" />
            <button type="submit" disabled={streaming || !chatId}>
              <Send size={14} /> {streaming ? "Streaming" : "Send"}
            </button>
          </form>
        </div>
      </div>
      {dialog}
    </PanelScaffold>
  );
}
