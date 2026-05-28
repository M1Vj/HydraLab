import React from "react";
import { useAppContext } from "../../core/context";
import { registry } from "../../core/registry";

export function SettingsSidebar() {
  const {
    openaiModel,
    setOpenaiModel,
    openaiApiKey,
    setOpenaiApiKey,
    anthropicModel,
    setAnthropicModel,
    anthropicApiKey,
    setAnthropicApiKey,
    geminiModel,
    setGeminiModel,
    geminiApiKey,
    setGeminiApiKey,
    themePreference,
    setThemePreference,
    defaultProvider,
    setDefaultProvider,
    systemInstruction,
    setSystemInstruction,
    isSavingSettings,
    settingsStatus,
    isExportLoading,
    handleSaveSettings,
    handleExportPreview
  } = useAppContext();

  return (
    <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "16px", height: "100%", overflowY: "auto", boxSizing: "border-box" }}>
      <div>
        <h3 style={{ fontSize: "14px", fontWeight: "bold", margin: "0 0 12px 0", color: "var(--fg)" }}>Model Providers</h3>
        
        {/* OpenAI */}
        <div style={{ marginBottom: "12px", padding: "10px", borderRadius: "6px", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border)" }}>
          <div style={{ fontSize: "12px", fontWeight: "bold", color: "#10b981", marginBottom: "8px" }}>OpenAI</div>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <input 
              type="text" 
              placeholder="Model (e.g. gpt-4o)" 
              value={openaiModel} 
              onChange={(e) => setOpenaiModel(e.target.value)}
              style={{ padding: "6px 8px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)", backgroundColor: "var(--bg-base)", color: "var(--fg)" }}
            />
            <input 
              type="password" 
              placeholder="API Key or env reference" 
              value={openaiApiKey} 
              onChange={(e) => setOpenaiApiKey(e.target.value)}
              style={{ padding: "6px 8px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)", backgroundColor: "var(--bg-base)", color: "var(--fg)" }}
            />
          </div>
        </div>

        {/* Anthropic */}
        <div style={{ marginBottom: "12px", padding: "10px", borderRadius: "6px", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border)" }}>
          <div style={{ fontSize: "12px", fontWeight: "bold", color: "#d97706", marginBottom: "8px" }}>Anthropic</div>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <input 
              type="text" 
              placeholder="Model (e.g. claude-3-5-sonnet)" 
              value={anthropicModel} 
              onChange={(e) => setAnthropicModel(e.target.value)}
              style={{ padding: "6px 8px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)", backgroundColor: "var(--bg-base)", color: "var(--fg)" }}
            />
            <input 
              type="password" 
              placeholder="API Key or env reference" 
              value={anthropicApiKey} 
              onChange={(e) => setAnthropicApiKey(e.target.value)}
              style={{ padding: "6px 8px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)", backgroundColor: "var(--bg-base)", color: "var(--fg)" }}
            />
          </div>
        </div>

        {/* Gemini */}
        <div style={{ marginBottom: "12px", padding: "10px", borderRadius: "6px", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border)" }}>
          <div style={{ fontSize: "12px", fontWeight: "bold", color: "#8b5cf6", marginBottom: "8px" }}>Gemini</div>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <input 
              type="text" 
              placeholder="Model (e.g. gemini-1.5-pro)" 
              value={geminiModel} 
              onChange={(e) => setGeminiModel(e.target.value)}
              style={{ padding: "6px 8px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)", backgroundColor: "var(--bg-base)", color: "var(--fg)" }}
            />
            <input 
              type="password" 
              placeholder="API Key or env reference" 
              value={geminiApiKey} 
              onChange={(e) => setGeminiApiKey(e.target.value)}
              style={{ padding: "6px 8px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)", backgroundColor: "var(--bg-base)", color: "var(--fg)" }}
            />
          </div>
        </div>
      </div>

      <div>
        <h3 style={{ fontSize: "14px", fontWeight: "bold", margin: "0 0 12px 0", color: "var(--fg)" }}>Workspace Preferences</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: "10px", padding: "10px", borderRadius: "6px", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border)" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            <label style={{ fontSize: "11px", color: "var(--fg-dim)", fontWeight: "500" }}>Default Provider</label>
            <select 
              value={defaultProvider} 
              onChange={(e) => setDefaultProvider(e.target.value)}
              style={{ padding: "6px 8px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)", backgroundColor: "var(--bg-base)", color: "var(--fg)", outline: "none" }}
            >
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="gemini">Gemini</option>
            </select>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            <label style={{ fontSize: "11px", color: "var(--fg-dim)", fontWeight: "500" }}>Theme</label>
            <select 
              value={themePreference} 
              onChange={(e) => setThemePreference(e.target.value)}
              style={{ padding: "6px 8px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)", backgroundColor: "var(--bg-base)", color: "var(--fg)", outline: "none" }}
            >
              <option value="light">Light</option>
              <option value="dark">Dark</option>
              <option value="glassmorphism">Glassmorphism</option>
            </select>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            <label style={{ fontSize: "11px", color: "var(--fg-dim)", fontWeight: "500" }}>System Instructions</label>
            <textarea 
              rows={3}
              value={systemInstruction} 
              onChange={(e) => setSystemInstruction(e.target.value)}
              placeholder="Enter system prompt instructions..."
              style={{ padding: "6px 8px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)", backgroundColor: "var(--bg-base)", color: "var(--fg)", resize: "vertical" }}
            />
          </div>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        <button 
          onClick={handleSaveSettings}
          disabled={isSavingSettings}
          style={{
            width: "100%",
            padding: "8px 12px",
            backgroundColor: "var(--accent)",
            color: "white",
            border: "none",
            borderRadius: "4px",
            cursor: "pointer",
            fontWeight: "600",
            fontSize: "13px",
            display: "flex",
            justifyContent: "center",
            alignItems: "center"
          }}
        >
          {isSavingSettings ? "Saving Settings..." : "Save Configuration"}
        </button>
        {settingsStatus && (
          <div style={{ fontSize: "12px", textAlign: "center", color: settingsStatus.includes("successfully") ? "#10b981" : "#ef4444" }}>
            {settingsStatus}
          </div>
        )}
      </div>

      <div style={{ borderTop: "1px solid var(--border)", paddingTop: "16px", marginTop: "8px" }}>
        <h3 style={{ fontSize: "14px", fontWeight: "bold", margin: "0 0 8px 0", color: "var(--fg)" }}>Data Export</h3>
        <p style={{ fontSize: "11px", color: "var(--fg-dim)", margin: "0 0 12px 0", lineHeight: "1.4" }}>
          Export your notes, citations, Kanban tasks, and sources into a local workspace ZIP bundle.
        </p>
        <button 
          onClick={handleExportPreview}
          disabled={isExportLoading}
          style={{
            width: "100%",
            padding: "8px 12px",
            backgroundColor: "var(--bg-dark)",
            color: "var(--fg)",
            border: "1px solid var(--border)",
            borderRadius: "4px",
            cursor: "pointer",
            fontWeight: "600",
            fontSize: "13px",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            gap: "8px"
          }}
        >
          {isExportLoading ? "Preparing Preview..." : "Export Workspace (ZIP)"}
        </button>
      </div>
    </div>
  );
}

// Register components
registry.register("hydra.settings", SettingsSidebar);

export function ExportPreviewModal() {
  const {
    isPreviewModalOpen,
    setIsPreviewModalOpen,
    previewData,
    handleTriggerExport
  } = useAppContext();

  if (!isPreviewModalOpen || !previewData) return null;

  return (
    <div className="kanban-modal-overlay">
      <div className="kanban-modal" style={{ maxWidth: "500px", width: "95%" }}>
        <h3 className="kanban-modal-title">Export Workspace Preview</h3>
        <p style={{ fontSize: "12px", color: "var(--fg-dim)", margin: "0 0 16px 0", lineHeight: "1.4" }}>
          Please review the files and counts that will be bundled into your zip archive.
        </p>

        <div style={{ backgroundColor: "var(--bg-dark)", border: "1px solid var(--border)", borderRadius: "6px", padding: "12px", display: "flex", flexWrap: "wrap", gap: "12px", marginBottom: "16px" }}>
          <div style={{ flex: "1 1 40%", display: "flex", flexDirection: "column" }}>
            <span style={{ fontSize: "11px", color: "var(--fg-dim)", textTransform: "uppercase", letterSpacing: "0.5px" }}>Notes</span>
            <span style={{ fontSize: "20px", fontWeight: "bold", color: "var(--fg)" }}>{previewData.counts?.notes || 0}</span>
          </div>
          <div style={{ flex: "1 1 40%", display: "flex", flexDirection: "column" }}>
            <span style={{ fontSize: "11px", color: "var(--fg-dim)", textTransform: "uppercase", letterSpacing: "0.5px" }}>Citations</span>
            <span style={{ fontSize: "20px", fontWeight: "bold", color: "var(--fg)" }}>{previewData.counts?.citations || 0}</span>
          </div>
          <div style={{ flex: "1 1 40%", display: "flex", flexDirection: "column" }}>
            <span style={{ fontSize: "11px", color: "var(--fg-dim)", textTransform: "uppercase", letterSpacing: "0.5px" }}>Kanban Tasks</span>
            <span style={{ fontSize: "20px", fontWeight: "bold", color: "var(--fg)" }}>{previewData.counts?.tasks || 0}</span>
          </div>
          <div style={{ flex: "1 1 40%", display: "flex", flexDirection: "column" }}>
            <span style={{ fontSize: "11px", color: "var(--fg-dim)", textTransform: "uppercase", letterSpacing: "0.5px" }}>Sources</span>
            <span style={{ fontSize: "20px", fontWeight: "bold", color: "var(--fg)" }}>{previewData.counts?.sources || 0}</span>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "6px", marginBottom: "20px" }}>
          <span style={{ fontSize: "12px", fontWeight: "600", color: "var(--fg)" }}>Archive File Structure:</span>
          <div style={{
            maxHeight: "150px",
            overflowY: "auto",
            backgroundColor: "var(--bg-dark)",
            border: "1px solid var(--border)",
            borderRadius: "6px",
            padding: "8px",
            fontFamily: "monospace",
            fontSize: "11px",
            color: "var(--fg-dim)"
          }}>
            {previewData.files && previewData.files.map((file: string) => (
              <div key={file} style={{ display: "flex", alignItems: "center", gap: "6px", padding: "3px 0" }}>
                <span style={{ color: "var(--accent)" }}>📁</span>
                <span>{file}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="kanban-modal-actions">
          <button
            type="button"
            className="kanban-btn kanban-btn-secondary"
            onClick={() => setIsPreviewModalOpen(false)}
          >
            Cancel
          </button>
          <button 
            type="button" 
            className="kanban-btn kanban-btn-primary"
            onClick={handleTriggerExport}
          >
            Download ZIP
          </button>
        </div>
      </div>
    </div>
  );
}

