import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { panelTitle: string; children: ReactNode };
type State = { error: Error | null };

/**
 * Isolates a single panel's render failures. Without this, one panel throwing
 * (a malformed config, a backend shape change, a bad `new URL(...)`) unmounts the
 * whole React tree and white-screens the entire workbench. The boundary keeps the
 * rest of the shell alive and offers an in-place retry.
 */
export class PanelErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Surface for dev tools; a panel crash must never take down the workbench.
    console.error(`Panel "${this.props.panelTitle}" crashed:`, error, info.componentStack);
  }

  private reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      return (
        <div className="panel-state failure" role="alert">
          <strong>{this.props.panelTitle} failed to render</strong>
          <span>{this.state.error.message || "Unexpected panel error."}</span>
          <button onClick={this.reset}>Retry</button>
        </div>
      );
    }
    return this.props.children;
  }
}
