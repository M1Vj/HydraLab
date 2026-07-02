import React from "react";
import { FilePlus2, Link2, MessageSquareQuote } from "lucide-react";

import { type PdfAnnotationRecord } from "../../../lib/annotations/store";

export function AnnotationInspector({
  annotation,
  autoCreateClaim,
  onAutoCreateClaim,
  onClaimAction,
}: {
  annotation: PdfAnnotationRecord | null;
  autoCreateClaim: boolean;
  onAutoCreateClaim: (enabled: boolean) => void;
  onClaimAction: () => void;
}) {
  return (
    <aside className="annotation-inspector" aria-label="Annotation inspector">
      <header>
        <MessageSquareQuote size={15} />
        <strong>Annotation</strong>
      </header>
      {annotation ? (
        <>
          <p>{annotation.text}</p>
          <dl>
            <div>
              <dt>Page</dt>
              <dd>{annotation.page}</dd>
            </div>
            <div>
              <dt>Revision</dt>
              <dd>{annotation.rev}</dd>
            </div>
            <div>
              <dt>Links</dt>
              <dd>{annotation.linked_claim_ids.length + annotation.linked_note_ids.length}</dd>
            </div>
          </dl>
          <label className="inspector-toggle">
            <input type="checkbox" checked={autoCreateClaim} onChange={(event) => onAutoCreateClaim(event.target.checked)} />
            Auto-create draft claims
          </label>
          <button onClick={onClaimAction}>
            {autoCreateClaim ? <FilePlus2 size={13} /> : <Link2 size={13} />}
            {autoCreateClaim ? "Draft claim" : "Suggest claim"}
          </button>
        </>
      ) : (
        <div className="empty-panel compact">
          <p>No annotation selected</p>
        </div>
      )}
    </aside>
  );
}
