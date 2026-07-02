import type { PanelComponentProps } from "../../../workspace/panelRegistry";
import { PdfReaderPanel, ReviewInboxPanel } from "../../../workspace/panels/ResearchObjectPanels";
import { MarkdownEditorPanel } from "../../../workspace/panels/MarkdownEditorPanel";
import { TasksPanel } from "../../../workspace/panels/TasksPanel";
import { ResearchChatPanel } from "../../../workspace/panels/ResearchChatPanel";

/**
 * Thin mobile adapters: each renders the EXISTING desktop panel component with the
 * mobile-supplied PanelComponentProps. No panel internals are copied or forked — the
 * PDF.js reader + sidecar (DEC-15), the CodeMirror note editor + autosave/journal
 * (DEC-9), the Review Inbox (DEC-11), tasks and the consent-aware chat are reused
 * verbatim, so their empty/loading/failure/permission-denied states come for free.
 * The wrapper only adds mobile spacing/touch-target chrome via CSS.
 */
export function ReadAnnotateView(props: PanelComponentProps) {
  return (
    <div className="mobile-view mobile-view-read">
      <PdfReaderPanel {...props} />
    </div>
  );
}

export function ReviewView(props: PanelComponentProps) {
  return (
    <div className="mobile-view mobile-view-review">
      <ReviewInboxPanel {...props} />
    </div>
  );
}

export function NotesView(props: PanelComponentProps) {
  return (
    <div className="mobile-view mobile-view-notes">
      <MarkdownEditorPanel {...props} />
    </div>
  );
}

export function TasksView(props: PanelComponentProps) {
  return (
    <div className="mobile-view mobile-view-tasks">
      <TasksPanel {...props} />
    </div>
  );
}

export function ChatView(props: PanelComponentProps) {
  return (
    <div className="mobile-view mobile-view-chat">
      <ResearchChatPanel {...props} />
    </div>
  );
}
