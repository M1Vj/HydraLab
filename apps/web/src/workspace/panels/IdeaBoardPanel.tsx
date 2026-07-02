import { useMemo, useState } from "react";
import { CheckCircle2, CircleDashed, Lightbulb, Play, RefreshCcw, SkipForward, Upload } from "lucide-react";
import type { IdeaCandidate, IdeaRunResponse } from "../../lib/api";
import { HydraApiError } from "../../lib/api";
import type { PanelComponentProps } from "../panelRegistry";
import { EmptyState, FailureState, LoadingState, PanelScaffold } from "./PanelState";
import {
  IDEA_STAGE_IDS,
  IDEA_STATE_MESSAGES,
  type IdeaStageId,
  type IdeaStageToggles,
  type PromotableTarget,
  defaultIdeaToggles,
  deriveIdeaBoardState,
  hasRubricScores,
  ideaStageStatus,
  promoteCandidate,
  rankedCandidates,
  startIdeaRun,
  toggleIdeaStage,
} from "./ideaBoardController";

const PROJECT_ID = "default";

function statusIcon(status: string) {
  if (status === "completed") return <CheckCircle2 size={14} aria-hidden />;
  if (status === "skipped") return <SkipForward size={14} aria-hidden />;
  return <CircleDashed size={14} aria-hidden />;
}

export function IdeaBoardPanel({ announce }: PanelComponentProps) {
  const [topic, setTopic] = useState("");
  const [sourceScope, setSourceScope] = useState("");
  const [constraints, setConstraints] = useState("");
  const [noveltyTarget, setNoveltyTarget] = useState("medium");
  const [toggles, setToggles] = useState<IdeaStageToggles>(() => defaultIdeaToggles());
  const [run, setRun] = useState<IdeaRunResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<Error | HydraApiError | null>(null);

  const board = useMemo(
    () => deriveIdeaBoardState({ loading: running, error, run }),
    [running, error, run],
  );

  async function onRun() {
    if (!topic.trim()) {
      announce("Enter a topic before running /generate-hypotheses");
      return;
    }
    setRunning(true);
    setError(null);
    try {
      const started = await startIdeaRun(
        PROJECT_ID,
        { topic, source_scope: sourceScope, constraints, novelty_target: noveltyTarget },
        toggles,
      );
      setRun(started);
      announce(`Idea run ${started.run.state ?? started.run.status}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setRunning(false);
    }
  }

  async function onPromote(candidate: IdeaCandidate, target: PromotableTarget) {
    try {
      const result = await promoteCandidate(PROJECT_ID, candidate.id, target);
      announce(`Promotion queued to Review Inbox (${result.status})`);
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    }
  }

  function onToggle(stage: IdeaStageId, enabled: boolean) {
    setToggles((current) => toggleIdeaStage(current, stage, enabled));
  }

  const steps = run?.trace.steps ?? [];
  const candidates = rankedCandidates(board.candidates);
  const showScores = hasRubricScores(candidates);

  return (
    <PanelScaffold title="Idea Board">
      <div className="idea-board-panel">
        <header className="idea-board-header">
          <div>
            <h2><Lightbulb size={16} aria-hidden /> Idea Board</h2>
            <p>/generate-hypotheses — one bounded Generate → Review → Compare → Evolve pass</p>
          </div>
          <button type="button" className="primary-action compact" onClick={() => void onRun()} disabled={running}>
            {running ? <RefreshCcw size={14} aria-hidden /> : <Play size={14} aria-hidden />}
            {running ? "Running" : "Run"}
          </button>
        </header>

        <section className="idea-board-form" aria-label="Recipe input">
          <label>
            <span>Topic</span>
            <input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="sub-quadratic attention for long documents" />
          </label>
          <label>
            <span>Source scope</span>
            <input value={sourceScope} onChange={(event) => setSourceScope(event.target.value)} placeholder="working set of saved sources" />
          </label>
          <label>
            <span>Constraints</span>
            <input value={constraints} onChange={(event) => setConstraints(event.target.value)} placeholder="solo researcher, no GPU cluster" />
          </label>
          <label>
            <span>Novelty target</span>
            <select value={noveltyTarget} onChange={(event) => setNoveltyTarget(event.target.value)}>
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
            </select>
          </label>
        </section>

        <section className="idea-stage-toggle-list" aria-label="Stage toggles">
          {IDEA_STAGE_IDS.map((id) => (
            <label key={id} className="idea-stage-toggle">
              <input type="checkbox" checked={toggles[id]} onChange={(event) => onToggle(id, event.target.checked)} />
              <span>{id}</span>
              <small>{ideaStageStatus(steps, id)}</small>
            </label>
          ))}
        </section>

        {board.completedStages.length > 0 && (
          <p className="idea-board-prefix" role="status">
            Completed stages: {board.completedStages.join(" → ")}
          </p>
        )}

        <IdeaBoardBody
          board={board}
          candidates={candidates}
          showScores={showScores}
          steps={steps}
          onRetry={() => void onRun()}
          onPromote={onPromote}
        />
      </div>
    </PanelScaffold>
  );
}

function IdeaBoardBody({
  board,
  candidates,
  showScores,
  steps,
  onRetry,
  onPromote,
}: {
  board: ReturnType<typeof deriveIdeaBoardState>;
  candidates: IdeaCandidate[];
  showScores: boolean;
  steps: IdeaRunResponse["trace"]["steps"];
  onRetry: () => void;
  onPromote: (candidate: IdeaCandidate, target: PromotableTarget) => void;
}) {
  if (board.kind === "loading") return <LoadingState title={IDEA_STATE_MESSAGES.loading} />;
  if (board.kind === "permission-denied") {
    return <FailureState error={new HydraApiError({ kind: "permission-denied", message: board.message })} />;
  }
  if (board.kind === "failure") {
    return (
      <>
        <FailureState error={new Error(board.message)} onRetry={onRetry} />
        {candidates.length > 0 && <CandidateList candidates={candidates} showScores={showScores} onPromote={onPromote} />}
      </>
    );
  }
  if (board.kind === "empty") {
    return <EmptyState title="No ideas yet" message={IDEA_STATE_MESSAGES.empty} />;
  }
  return (
    <>
      <TraceStream steps={steps} />
      <CandidateList candidates={candidates} showScores={showScores} onPromote={onPromote} />
    </>
  );
}

function TraceStream({ steps }: { steps: IdeaRunResponse["trace"]["steps"] }) {
  return (
    <section className="idea-run-stream" aria-label="Live event stream">
      <h3>Reasoning trace</h3>
      {steps.length === 0 ? (
        <p className="idea-board-muted">No run events yet.</p>
      ) : (
        <ol>
          {steps.map((step) => (
            <li key={`${step.index}-${step.kind}`} className={`idea-trace-row ${step.status}`}>
              {statusIcon(step.status)}
              <span>{step.kind.replace("stage.", "").replace("_", " ")}</span>
              <small>{step.status}</small>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function CandidateList({
  candidates,
  showScores,
  onPromote,
}: {
  candidates: IdeaCandidate[];
  showScores: boolean;
  onPromote: (candidate: IdeaCandidate, target: PromotableTarget) => void;
}) {
  return (
    <section className="idea-candidate-list" aria-label="Candidate ideas">
      {candidates.map((candidate) => (
        <article key={candidate.id} className="idea-candidate-card">
          <header>
            {showScores && candidate.rank != null && <span className="idea-rank">#{candidate.rank}</span>}
            <h4>{candidate.title}</h4>
            <span className={`idea-status ${candidate.status}`}>{candidate.status}</span>
          </header>
          <p>{candidate.short_hypothesis}</p>
          {candidate.evidence_links.length > 0 && (
            <ul className="idea-evidence" aria-label="Evidence links">
              {candidate.evidence_links.map((link) => (
                <li key={`${link.source_id}-${link.evidence_id ?? ""}`}>
                  <code>{link.source_id}</code>
                  {link.evidence_id && <small> · {link.evidence_id}</small>}
                </li>
              ))}
            </ul>
          )}
          {showScores && candidate.rubric_results.length > 0 && (
            <table className="idea-rubric-table">
              <thead>
                <tr>
                  <th scope="col">Criterion</th>
                  <th scope="col">Score</th>
                  <th scope="col">Rationale</th>
                </tr>
              </thead>
              <tbody>
                {candidate.rubric_results.map((result) => (
                  <tr key={result.criterion}>
                    <th scope="row">{result.criterion.replace(/_/g, " ")}</th>
                    <td>{result.value.toFixed(2)}</td>
                    <td>{result.rationale}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <footer className="idea-candidate-actions">
            <button type="button" onClick={() => onPromote(candidate, "task")}>
              <Upload size={13} aria-hidden /> Promote to task
            </button>
            <button type="button" onClick={() => onPromote(candidate, "note")}>
              <Upload size={13} aria-hidden /> Promote to note
            </button>
          </footer>
        </article>
      ))}
    </section>
  );
}
