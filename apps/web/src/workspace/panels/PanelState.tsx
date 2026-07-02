import { AlertTriangle, LockKeyhole, RefreshCcw } from "lucide-react";
import type React from "react";
import type { HydraApiError } from "../../lib/api";

export function PanelScaffold({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="workspace-panel" aria-label={title}>
      {children}
    </section>
  );
}

export function EmptyState({ title, message, action, onAction }: { title: string; message: string; action?: string; onAction?: () => void }) {
  return (
    <div className="panel-state empty" role="status">
      <strong>{title}</strong>
      <span>{message}</span>
      {action && onAction && <button onClick={onAction}>{action}</button>}
    </div>
  );
}

export function LoadingState({ title = "Loading" }: { title?: string }) {
  return (
    <div className="panel-state loading" aria-busy="true" aria-label={title}>
      <div className="skeleton-line" />
      <div className="skeleton-line short" />
      <div className="skeleton-line" />
    </div>
  );
}

export function FailureState({ error, onRetry }: { error: Error | HydraApiError; onRetry?: () => void }) {
  const apiError = error as HydraApiError;
  const permissionDenied = apiError.kind === "permission-denied" || apiError.kind === "consent-required";
  return (
    <div className={`panel-state ${permissionDenied ? "permission-denied" : "failure"}`} role="alert">
      {permissionDenied ? <LockKeyhole size={18} /> : <AlertTriangle size={18} />}
      <strong>{permissionDenied ? "Permission denied" : "Request failed"}</strong>
      <span>{error.message}</span>
      {onRetry && (
        <button onClick={onRetry}>
          <RefreshCcw size={14} /> Retry
        </button>
      )}
    </div>
  );
}

export function NotWiredState({ title, route }: { title: string; route?: string }) {
  return (
    <div className="panel-state not-wired" role="status">
      <strong>{title}</strong>
      <span>{route ? `${route} is not available in this backend branch.` : "This panel is intentionally registered for layout continuity."}</span>
    </div>
  );
}
