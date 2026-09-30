"use client";

import { useCallback, useEffect, useState } from "react";

/** Minimal request state for real backend reads. Failures surface as error
 * states — pages must never fall back to demo data. */

interface Settled<T> {
  nonce: number;
  data: T | null;
  error: string | null;
}

interface ResourceState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

export function useResource<T>(loader: () => Promise<T>): ResourceState<T> {
  const [nonce, setNonce] = useState(0);
  const [settled, setSettled] = useState<Settled<T>>({
    nonce: -1,
    data: null,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;
    loader().then(
      (data) => {
        if (!cancelled) setSettled({ nonce, data, error: null });
      },
      (error: unknown) => {
        if (!cancelled)
          setSettled({
            nonce,
            data: null,
            error:
              error instanceof Error ? error.message : "Request failed.",
          });
      },
    );
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonce]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);
  const current = settled.nonce === nonce;

  return {
    data: current ? settled.data : null,
    error: current ? settled.error : null,
    loading: !current,
    reload,
  };
}
