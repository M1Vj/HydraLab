import { useEffect, useState } from "react";
import { CheckCircle2, Eye, FileCheck2, PackageCheck, ShieldCheck } from "lucide-react";
import {
  buildReproducibilityBundle,
  exportReproducibilityReport,
  getReproducibilityPreview,
  listReproducibilityRuns,
  verifyReproducibilityBundle,
  type ReproducibilityBundleResponse,
  type ReproducibilityPreviewResponse,
  type ReproducibilityRunSummary,
  type ReproducibilityVerificationResponse,
} from "../../lib/api";
import type { PanelComponentProps } from "../panelRegistry";
import { EmptyState, FailureState, LoadingState, PanelScaffold } from "./PanelState";
import {
  buildBundleRequest,
  buildResultMessage,
  canBuildBundle,
  includedCategoryLabels,
  reviewRedactionCount,
} from "./reproducibilityController";

const PROJECT_ID = "default";

export function ReproducibilityPanel({ announce }: PanelComponentProps) {
  const [runs, setRuns] = useState<ReproducibilityRunSummary[]>([]);
  const [selectedRunIds, setSelectedRunIds] = useState<string[]>([]);
  const [preview, setPreview] = useState<ReproducibilityPreviewResponse | null>(null);
  const [bundle, setBundle] = useState<ReproducibilityBundleResponse | null>(null);
  const [verification, setVerification] = useState<ReproducibilityVerificationResponse | null>(null);
  const [reportPath, setReportPath] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    void loadRuns();
  }, []);

  async function loadRuns() {
    setLoading(true);
    setError(null);
    try {
      const payload = await listReproducibilityRuns(PROJECT_ID);
      setRuns(payload.runs);
      setSelectedRunIds((current) => (current.length > 0 ? current : payload.runs.map((run) => run.id)));
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setLoading(false);
    }
  }

  async function loadPreview() {
    setBusy(true);
    setError(null);
    try {
      setPreview(await getReproducibilityPreview(PROJECT_ID, selectedRunIds));
      setBundle(null);
      setVerification(null);
      setReportPath("");
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setBusy(false);
    }
  }

  async function buildBundle() {
    setBusy(true);
    setError(null);
    try {
      const result = await buildReproducibilityBundle(buildBundleRequest(PROJECT_ID, selectedRunIds));
      setBundle(result);
      announce(buildResultMessage(result));
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setBusy(false);
    }
  }

  async function verifyBundle() {
    if (!bundle) return;
    setBusy(true);
    setError(null);
    try {
      const result = await verifyReproducibilityBundle(bundle.bundle_id, PROJECT_ID);
      setVerification(result);
      announce(result.ok ? "Reproducibility bundle verified" : "Reproducibility bundle verification failed");
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setBusy(false);
    }
  }

  async function exportReport() {
    if (!bundle) return;
    setBusy(true);
    setError(null);
    try {
      const result = await exportReproducibilityReport(bundle.bundle_id, { project_id: PROJECT_ID });
      setReportPath(result.report_path);
      announce("Exported reproducibility final report");
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setBusy(false);
    }
  }

  function toggleRun(id: string) {
    setSelectedRunIds((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
    setPreview(null);
    setBundle(null);
    setVerification(null);
    setReportPath("");
  }

  if (error) return <FailureState error={error} onRetry={loadRuns} />;
  if (loading) return <LoadingState title="Loading reproducibility runs" />;
  if (runs.length === 0) {
    return (
      <EmptyState
        title="No bundleable runs"
        message="Completed autonomy or experiment runs will appear here when they are ready for a reproducibility package."
        action="Refresh"
        onAction={() => void loadRuns()}
      />
    );
  }

  const buildReady = canBuildBundle(runs, selectedRunIds);

  return (
    <PanelScaffold title="Reproducibility">
      <section className="settings-section" aria-label="Bundle runs">
        <header>
          <ShieldCheck size={15} />
          <strong>Runs</strong>
        </header>
        <div className="object-list">
          {runs.map((run) => (
            <label className="object-card" key={run.id}>
              <span>
                <input type="checkbox" checked={selectedRunIds.includes(run.id)} onChange={() => toggleRun(run.id)} />
                <strong>{run.label}</strong>
              </span>
              <small>
                {run.kind} · {run.status}
              </small>
            </label>
          ))}
        </div>
        <div className="export-format-row">
          <button disabled={!buildReady || busy} onClick={() => void loadPreview()}>
            <Eye size={14} /> Review
          </button>
          <button disabled={!preview || busy} onClick={() => void buildBundle()}>
            <PackageCheck size={14} /> Confirm build
          </button>
        </div>
      </section>

      {busy && <LoadingState title="Building and hashing" />}

      {preview && (
        <section className="settings-section" aria-label="Pre-export review">
          <header>
            <FileCheck2 size={15} />
            <strong>Pre-export review</strong>
          </header>
          <ul className="git-file-list">
            {includedCategoryLabels(preview).map((label) => (
              <li key={label}>{label}</li>
            ))}
          </ul>
          <p className="settings-hint">{reviewRedactionCount(preview)} redacted item(s)</p>
        </section>
      )}

      {bundle && (
        <section className="settings-section" aria-label="Bundle result">
          <header>
            <CheckCircle2 size={15} />
            <strong>{bundle.bundle_id}</strong>
          </header>
          <p className="settings-hint">{bundle.manifest_content_hash}</p>
          <div className="export-format-row">
            <button disabled={busy} onClick={() => void verifyBundle()}>
              <ShieldCheck size={14} /> Verify
            </button>
            <button disabled={busy} onClick={() => void exportReport()}>
              <FileCheck2 size={14} /> Report
            </button>
          </div>
          {verification && (
            <p className={verification.ok ? "settings-hint" : "panel-state failure"} role="status">
              {verification.ok ? "Verified with zero dangling references." : `Failed: ${verification.hash_mismatches.concat(verification.dangling_ids).join(", ")}`}
            </p>
          )}
          {reportPath && <p className="settings-hint">{reportPath}</p>}
        </section>
      )}
    </PanelScaffold>
  );
}
