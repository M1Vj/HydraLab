import { useCallback, useEffect, useState } from "react";
import type React from "react";

export type ResourceState<T> =
  | { status: "loading"; data: T | null; error: null }
  | { status: "ready"; data: T; error: null }
  | { status: "empty"; data: T | null; error: null }
  | { status: "failure"; data: T | null; error: Error };

export function useApiResource<T>(loader: () => Promise<T>, deps: React.DependencyList, isEmpty: (data: T) => boolean = () => false) {
  const [version, setVersion] = useState(0);
  const [state, setState] = useState<ResourceState<T>>({ status: "loading", data: null, error: null });
  const reload = useCallback(() => setVersion((current) => current + 1), []);

  useEffect(() => {
    let disposed = false;
    setState((current) => ({ status: "loading", data: current.data, error: null }));
    void loader()
      .then((data) => {
        if (disposed) return;
        setState(isEmpty(data) ? { status: "empty", data, error: null } : { status: "ready", data, error: null });
      })
      .catch((error) => {
        if (disposed) return;
        setState((current) => ({ status: "failure", data: current.data, error: error instanceof Error ? error : new Error(String(error)) }));
      });
    return () => {
      disposed = true;
    };
  }, [...deps, version]);

  return { ...state, reload };
}
