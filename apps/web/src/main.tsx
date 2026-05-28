import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BookOpenCheck,
  CheckCircle2,
  FileText,
  Library,
  ListTodo,
  MessageSquareText,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Terminal,
  Activity,
  X,
  SplitSquareHorizontal
} from "lucide-react";

import "./styles.css";

type ActivityType = "chat" | "sources" | "notes" | "tasks" | "settings" | "evidence";

interface Message {
  id: string;
  role: string;
  content: string;
}

function App() {
  const [activeActivity, setActiveActivity] = useState<ActivityType>("chat");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [bottomPanelOpen, setBottomPanelOpen] = useState(true);
  const [activeEditorTab, setActiveEditorTab] = useState("research-1");
  const [draftText, setDraftText] = useState("");
  const [reviewData, setReviewData] = useState<any>(null);
  const [isReviewing, setIsReviewing] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [evidenceList, setEvidenceList] = useState<any[]>([]);

  React.useEffect(() => {
    if (activeActivity === "evidence") {
      fetch("http://localhost:8000/api/evidence")
        .then(r => r.json())
        .then(data => setEvidenceList(data.evidence || []))
        .catch(console.error);
    }
  }, [activeActivity]);


  const analyzeText = async () => {
    if (!draftText.trim()) return;
    setIsReviewing(true);
    try {
      const res = await fetch("http://localhost:8000/api/reviews/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: draftText })
      });
      const data = await res.json();
      setReviewData(data);
    } catch (err) {
      console.error(err);
    } finally {
      setIsReviewing(false);
    }
  };

  const sendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;
    const userMessage = { id: Date.now().toString(), role: "user", content: inputValue };
    setMessages(prev => [...prev, userMessage]);
    setInputValue("");
    setIsLoading(true);
    setStatusMessage("Starting request...");
    
    try {
      const res = await fetch("http://localhost:8000/api/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: inputValue, conversation_id: conversationId })
      });
      
      if (!res.body) return;
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      
      let assistantMessage = { id: (Date.now() + 1).toString(), role: "assistant", content: "" };
      setMessages(prev => [...prev, assistantMessage]);
      
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        const lines = chunk.split("\n\n");
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const dataStr = line.substring(6);
          if (!dataStr) continue;
          try {
            const data = JSON.parse(dataStr);
            if (data.type === "status") {
              setStatusMessage(data.content);
            } else if (data.type === "message") {
              assistantMessage.content += data.content;
              setMessages(prev => {
                const newMsgs = [...prev];
                newMsgs[newMsgs.length - 1] = { ...assistantMessage };
                return newMsgs;
              });
            } else if (data.type === "done") {
              setConversationId(data.conversation_id);
            }
          } catch (e) {
             console.error("Error parsing chunk", e, dataStr);
          }
        }
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
      setStatusMessage("");
    }
  };

  const toggleSidebar = (activity: ActivityType) => {
    if (activeActivity === activity) {
      setSidebarOpen(!sidebarOpen);
    } else {
      setActiveActivity(activity);
      setSidebarOpen(true);
    }
  };

  return (
    <div className={`workbench ${!sidebarOpen ? "sidebar-closed" : "sidebar-open"}`}>
      
      {/* Activity Bar */}
      <nav className="activity-bar" aria-label="Activity Bar">
        <div 
          className={`activity-icon ${activeActivity === "chat" ? "active" : ""}`} 
          onClick={() => toggleSidebar("chat")}
          title="Research Chat"
        >
          <MessageSquareText size={24} strokeWidth={1.5} />
        </div>
        <div 
          className={`activity-icon ${activeActivity === "sources" ? "active" : ""}`} 
          onClick={() => toggleSidebar("sources")}
          title="Sources"
        >
          <Library size={24} strokeWidth={1.5} />
        </div>
        <div 
          className={`activity-icon ${activeActivity === "notes" ? "active" : ""}`} 
          onClick={() => toggleSidebar("notes")}
          title="Notes"
        >
          <FileText size={24} strokeWidth={1.5} />
        </div>
        <div 
          className={`activity-icon ${activeActivity === "tasks" ? "active" : ""}`} 
          onClick={() => toggleSidebar("tasks")}
          title="Tasks"
        >
          <ListTodo size={24} strokeWidth={1.5} />
        </div>
        <div 
          className={`activity-icon ${activeActivity === "evidence" ? "active" : ""}`} 
          onClick={() => toggleSidebar("evidence")}
          title="Evidence"
        >
          <ShieldCheck size={24} strokeWidth={1.5} />
        </div>
        <div style={{ flex: 1 }} />
        <div 
          className={`activity-icon ${activeActivity === "settings" ? "active" : ""}`} 
          onClick={() => toggleSidebar("settings")}
          title="Settings"
        >
          <Settings size={24} strokeWidth={1.5} />
        </div>
      </nav>

      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <span>{activeActivity.toUpperCase()}</span>
        </div>
        <div className="sidebar-content">
          {activeActivity === "chat" && (
            <div className="empty-state" style={{ height: "auto", marginTop: "40px" }}>
              <p>No recent research chats.</p>
            </div>
          )}
          {activeActivity === "sources" && (
            <div className="empty-state" style={{ height: "auto", marginTop: "40px" }}>
              <p>No sources uploaded.</p>
            </div>
          )}
          {activeActivity === "notes" && (
            <div className="empty-state" style={{ height: "auto", marginTop: "40px" }}>
              <p>No notes available.</p>
            </div>
          )}
          {activeActivity === "tasks" && (
            <div className="empty-state" style={{ height: "auto", marginTop: "40px" }}>
              <p>No active tasks.</p>
            </div>
          )}
          {activeActivity === "evidence" && (
            <div style={{ padding: "12px", display: "flex", flexDirection: "column", gap: "12px" }}>
              {evidenceList.length === 0 ? (
                <div className="empty-state" style={{ height: "auto", marginTop: "40px" }}>
                  <p>No evidence links found.</p>
                </div>
              ) : (
                evidenceList.map(ev => (
                  <div key={ev.id} style={{ 
                    padding: "12px", 
                    backgroundColor: "var(--bg-dark)", 
                    borderRadius: "6px",
                    borderLeft: ev.support === "unsupported" ? "4px solid #ef4444" : ev.support === "weak" ? "4px solid #f59e0b" : "4px solid #10b981"
                  }}>
                    <div style={{ fontSize: "13px", fontWeight: "bold", marginBottom: "4px", color: "var(--fg)" }}>{ev.claim_text}</div>
                    <div style={{ fontSize: "12px", color: "var(--fg-dim)", marginBottom: "8px", fontStyle: "italic" }}>"{ev.passage}"</div>
                    <div style={{ fontSize: "11px", display: "flex", justifyContent: "space-between", color: "var(--fg-dim)" }}>
                      <span>Source: {ev.source_title}</span>
                      <span style={{ 
                        color: ev.support === "unsupported" ? "#ef4444" : ev.support === "weak" ? "#f59e0b" : "#10b981"
                      }}>
                        {ev.support.toUpperCase()}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </aside>

      {/* Main Area */}
      <main className="main-area">
        <div className="editor-group">
          <div className="editor-tabs">
            <div 
              className={`editor-tab ${activeEditorTab === "research-1" ? "active" : ""}`}
              onClick={() => setActiveEditorTab("research-1")}
            >
              <Sparkles size={14} />
              Research Agent
              <X size={14} style={{ marginLeft: 8, opacity: 0.5 }} />
            </div>
            <div 
              className={`editor-tab ${activeEditorTab === "notes-1" ? "active" : ""}`}
              onClick={() => setActiveEditorTab("notes-1")}
            >
              <FileText size={14} />
              Draft Notes.md
              <X size={14} style={{ marginLeft: 8, opacity: 0.5 }} />
            </div>
            <div 
              className={`editor-tab ${activeEditorTab === "writing-1" ? "active" : ""}`}
              onClick={() => setActiveEditorTab("writing-1")}
            >
              <BookOpenCheck size={14} />
              Writing Review
              <X size={14} style={{ marginLeft: 8, opacity: 0.5 }} />
            </div>
            <div style={{ flex: 1 }} />
            <div className="editor-tab" style={{ border: "none", cursor: "default" }}>
              <SplitSquareHorizontal size={14} style={{ cursor: "pointer", opacity: 0.7 }} />
            </div>
          </div>

          <div className="editor-pane-container">
            <div className="editor-pane">
              {activeEditorTab === "research-1" && (
                <div className="chat-interface" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
                  <div className="chat-messages" style={{ flex: 1, overflowY: "auto", padding: "20px" }}>
                    {messages.length === 0 ? (
                      <div className="empty-state">
                        <Sparkles />
                        <h2>Hydra Research</h2>
                        <p>Ask a question, upload a paper, or synthesize your notes. I will generate citations and trace claims back to their source.</p>
                      </div>
                    ) : (
                      messages.map(msg => (
                        <div key={msg.id} style={{ marginBottom: "20px", textAlign: msg.role === "user" ? "right" : "left" }}>
                          <div style={{
                            display: "inline-block",
                            padding: "10px 14px",
                            borderRadius: "8px",
                            backgroundColor: msg.role === "user" ? "var(--accent)" : "var(--bg-lighter)",
                            color: msg.role === "user" ? "white" : "inherit",
                            maxWidth: "80%"
                          }}>
                            {msg.content}
                          </div>
                        </div>
                      ))
                    )}
                    {isLoading && statusMessage && (
                      <div style={{ marginBottom: "20px", textAlign: "left", fontSize: "0.9em", color: "var(--fg-dim)", display: "flex", alignItems: "center", gap: "8px" }}>
                        <div className="spinner" style={{ width: "12px", height: "12px", border: "2px solid var(--fg-dim)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }}></div>
                        {statusMessage}
                      </div>
                    )}
                  </div>
                  <div className="chat-input-area" style={{ padding: "20px", borderTop: "1px solid var(--border)" }}>
                    <div style={{ display: "flex", gap: "10px" }}>
                      <input 
                        type="text" 
                        value={inputValue}
                        onChange={(e) => setInputValue(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && sendMessage()}
                        placeholder="Message Hydra..." 
                        style={{ flex: 1, padding: "10px", borderRadius: "4px", border: "1px solid var(--border)", backgroundColor: "var(--bg-dark)", color: "var(--fg)" }}
                      />
                      <button onClick={sendMessage} disabled={isLoading} style={{ padding: "10px 20px", borderRadius: "4px", backgroundColor: "var(--accent)", color: "white", border: "none", cursor: isLoading ? "not-allowed" : "pointer" }}>
                        Send
                      </button>
                    </div>
                  </div>
                  <style>{`
                    @keyframes spin { 100% { transform: rotate(360deg); } }
                  `}</style>
                </div>
              )}
              {activeEditorTab === "notes-1" && (
                <div className="empty-state">
                  <FileText />
                  <h2>Notes</h2>
                  <p>Write your synthesis here. Your sources and evidence review will guide your drafting.</p>
                </div>
              )}
              {activeEditorTab === "writing-1" && (
                <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
                  <div style={{ padding: "12px", borderBottom: "1px solid var(--border)", display: "flex", gap: "8px" }}>
                    <button onClick={analyzeText} disabled={isReviewing} style={{ padding: "6px 12px", background: "var(--accent)", color: "white", borderRadius: "4px", border: "none", cursor: "pointer" }}>
                      {isReviewing ? "Analyzing..." : "Review Draft"}
                    </button>
                    {reviewData && (
                      <span style={{ fontSize: "13px", alignSelf: "center", color: "var(--fg-dim)" }}>
                        Issues: {reviewData.categories?.join(", ")}
                      </span>
                    )}
                  </div>
                  <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
                    <div style={{ flex: 1, borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column" }}>
                      <div style={{ padding: "8px", background: "var(--bg)", borderBottom: "1px solid var(--border)", fontSize: "12px", color: "var(--fg-dim)", fontWeight: "bold" }}>LATEX EDITOR</div>
                      <textarea 
                        value={draftText} 
                        onChange={(e) => setDraftText(e.target.value)} 
                        style={{ flex: 1, padding: "16px", background: "var(--bg-dark)", color: "var(--fg)", border: "none", resize: "none", fontFamily: "monospace" }} 
                        placeholder="Write your draft here..."
                      />
                    </div>
                    {reviewData ? (
                      <div style={{ flex: 1, display: "flex", flexDirection: "column", background: "var(--bg)" }}>
                        <div style={{ padding: "8px", background: "var(--bg)", borderBottom: "1px solid var(--border)", fontSize: "12px", color: "var(--fg-dim)", fontWeight: "bold" }}>REVIEW SUGGESTIONS</div>
                        <div style={{ flex: 1, overflowY: "auto", padding: "16px" }}>
                          {reviewData.critique?.map((c: string, i: number) => (
                            <div key={i} style={{ padding: "12px", marginBottom: "12px", background: "var(--bg-lighter)", borderRadius: "6px", borderLeft: "4px solid var(--accent)" }}>
                              <p style={{ margin: "0 0 8px 0", fontSize: "13px" }}>{c}</p>
                            </div>
                          ))}
                          {reviewData.unsupported_claims?.length > 0 && (
                            <div style={{ marginTop: "16px", padding: "12px", background: "rgba(239, 68, 68, 0.1)", borderRadius: "6px", borderLeft: "4px solid #ef4444" }}>
                              <h4 style={{ margin: "0 0 8px 0", fontSize: "13px", color: "#ef4444" }}>Unsupported Claims (Needs Evidence)</h4>
                              <ul style={{ margin: 0, paddingLeft: "20px", fontSize: "13px" }}>
                                {reviewData.unsupported_claims.map((claim: string, i: number) => (
                                  <li key={i}>{claim} <span style={{ color: "var(--accent)", cursor: "pointer", textDecoration: "underline" }} onClick={() => setActiveActivity("evidence")}>Link Evidence</span></li>
                                ))}
                              </ul>
                            </div>
                          )}
                          <div style={{ marginTop: "16px", padding: "12px", background: "var(--bg-lighter)", borderRadius: "6px" }}>
                            <h4 style={{ margin: "0 0 8px 0", fontSize: "13px" }}>Suggested Revision</h4>
                            <p style={{ fontSize: "13px", color: "var(--fg-dim)", whiteSpace: "pre-wrap" }}>{reviewData.rewrite}</p>
                            <div style={{ display: "flex", gap: "8px", marginTop: "12px" }}>
                              <button onClick={() => { setDraftText(reviewData.rewrite); setReviewData(null); }} style={{ padding: "6px 12px", background: "var(--accent)", color: "white", borderRadius: "4px", border: "none", cursor: "pointer" }}>Accept Revision</button>
                              <button onClick={() => setReviewData(null)} style={{ padding: "6px 12px", background: "transparent", color: "var(--fg)", border: "1px solid var(--border)", borderRadius: "4px", cursor: "pointer" }}>Reject</button>
                            </div>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div style={{ flex: 1, display: "flex", flexDirection: "column", background: "var(--bg)" }}>
                        <div style={{ padding: "8px", background: "var(--bg)", borderBottom: "1px solid var(--border)", fontSize: "12px", color: "var(--fg-dim)", fontWeight: "bold" }}>PDF PREVIEW</div>
                        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--fg-dim)" }}>
                          [PDF Preview Placeholder]
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Bottom Panel */}
        {bottomPanelOpen && (
          <div className="bottom-panel">
            <div className="panel-tabs">
              <div className="panel-tab active">Terminal</div>
              <div className="panel-tab">Output</div>
              <div className="panel-tab">Problems</div>
              <div style={{ flex: 1 }} />
              <div className="panel-tab" style={{ border: "none" }} onClick={() => setBottomPanelOpen(false)}>
                <X size={14} style={{ marginTop: 2 }} />
              </div>
            </div>
            <div className="panel-content">
              <div>hydra-web@0.1.0 dev</div>
              <div style={{ color: "var(--accent)", marginTop: 4 }}>➜  Local:   http://127.0.0.1:5173/</div>
              <div style={{ marginTop: 4 }}>➜  Network: use --host to expose</div>
              <div style={{ marginTop: 4 }}>ready in 245ms.</div>
            </div>
          </div>
        )}
      </main>

      {/* Status Bar */}
      <footer className="status-bar">
        <div className="status-group">
          <div className="status-item" onClick={() => setBottomPanelOpen(!bottomPanelOpen)}>
            <Terminal size={12} />
          </div>
          <div className="status-item">
            <CheckCircle2 size={12} />
            0 Errors
          </div>
        </div>
        <div className="status-group">
          <div className="status-item">
            <Activity size={12} />
            Phase 1
          </div>
        </div>
      </footer>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
