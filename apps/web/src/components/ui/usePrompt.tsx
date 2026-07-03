import { useCallback, useRef, useState } from "react";
import { Dialog } from "./primitives";

type PromptOptions = {
  title: string;
  defaultValue?: string;
  placeholder?: string;
  confirmLabel?: string;
};

type PromptState = PromptOptions & { open: boolean };

/**
 * Accessible async replacement for window.prompt.
 *
 * window.prompt is not screen-reader friendly, blocks the JS thread, and returns
 * null in a Tauri v2 webview (so the feature silently breaks in the packaged
 * app). This renders a focus-trapped role="dialog" instead and resolves a
 * Promise with the entered text, or null on cancel/Escape/empty.
 */
export function usePrompt() {
  const [state, setState] = useState<PromptState | null>(null);
  const [value, setValue] = useState("");
  const resolver = useRef<((result: string | null) => void) | null>(null);

  const prompt = useCallback((options: PromptOptions) => {
    setValue(options.defaultValue ?? "");
    setState({ ...options, open: true });
    return new Promise<string | null>((resolve) => {
      resolver.current = resolve;
    });
  }, []);

  const settle = useCallback((result: string | null) => {
    resolver.current?.(result);
    resolver.current = null;
    setState(null);
  }, []);

  const dialog =
    state && state.open ? (
      <Dialog open title={state.title} onClose={() => settle(null)}>
        <form
          className="prompt-dialog-form"
          onSubmit={(event) => {
            event.preventDefault();
            const trimmed = value.trim();
            settle(trimmed ? trimmed : null);
          }}
        >
          <input
            autoFocus
            value={value}
            placeholder={state.placeholder}
            aria-label={state.title}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") settle(null);
            }}
          />
          <div className="prompt-dialog-actions">
            <button type="button" onClick={() => settle(null)}>
              Cancel
            </button>
            <button type="submit">{state.confirmLabel ?? "OK"}</button>
          </div>
        </form>
      </Dialog>
    ) : null;

  return { prompt, dialog };
}
