import React from "react";
import { Sparkles } from "lucide-react";
import { useAppContext } from "../../core/context";
import { registry } from "../../core/registry";

export function ChatSidebar() {
  return (
    <div className="empty-state" style={{ height: "auto", marginTop: "40px" }}>
      <p>No recent research chats.</p>
    </div>
  );
}

export function ChatMain() {
  const {
    messages,
    isLoading,
    statusMessage,
    inputValue,
    setInputValue,
    sendMessage
  } = useAppContext();

  return (
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
  );
}

// Register components
registry.register("hydra.chat", ChatSidebar);
registry.register("hydra.chat.main", ChatMain);
