import React from "react";
import { useAppContext } from "../../core/context";
import { registry } from "../../core/registry";

export function WritingMain() {
  const {
    draftText,
    setDraftText,
    reviewData,
    setReviewData,
    isReviewing,
    analyzeText,
    setActiveActivity
  } = useAppContext();

  return (
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
                      <li key={i}>
                        {claim}{" "}
                        <span 
                          style={{ color: "var(--accent)", cursor: "pointer", textDecoration: "underline" }} 
                          onClick={() => setActiveActivity("evidence")}
                        >
                          Link Evidence
                        </span>
                      </li>
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
  );
}

// Register components
registry.register("hydra.writing.main", WritingMain);
