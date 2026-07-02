declare module "y-codemirror.next" {
  import type { Extension } from "@codemirror/state";
  import type * as Y from "yjs";

  export function yCollab(
    ytext: Y.Text,
    awareness: {
      doc: Y.Doc;
      getLocalState(): Record<string, unknown> | null;
      setLocalStateField(field: string, value: unknown): void;
      getStates(): Map<number, Record<string, unknown>>;
      on(event: "change", listener: (change: { added: number[]; updated: number[]; removed: number[] }) => void): void;
      off(event: "change", listener: (change: { added: number[]; updated: number[]; removed: number[] }) => void): void;
    },
    options?: { undoManager?: Y.UndoManager },
  ): Extension;
}
