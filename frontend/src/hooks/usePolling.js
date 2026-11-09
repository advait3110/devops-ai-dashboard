import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

/*
 * usePolling(fetcher, intervalMs)
 *
 * Calls `fetcher` now and then every `intervalMs`, and returns
 * { data, error, loading, refresh, updatedAt }.
 *
 * Kept light on purpose (8 GB laptop):
 * - pauses while the browser tab is hidden (no wasted requests),
 * - never starts a new request while the previous one is still running,
 * - keeps the last good data visible if one refresh fails.
 */
export default function usePolling(fetcher, intervalMs = 5000, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState(null);
  const busy = useRef(false);
  const fetcherRef = useRef(fetcher);
  useLayoutEffect(() => {
    fetcherRef.current = fetcher;
  });

  const refresh = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    try {
      const result = await fetcherRef.current();
      setData(result);
      setError(null);
      setUpdatedAt(new Date());
    } catch (err) {
      setError(err);
    } finally {
      busy.current = false;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    if (!intervalMs) return undefined;
    const id = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, intervalMs);
    const onVisible = () => document.visibilityState === "visible" && refresh();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, refresh, ...deps]);

  return { data, error, loading, refresh, updatedAt };
}
