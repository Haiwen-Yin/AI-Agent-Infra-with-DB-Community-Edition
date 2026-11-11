import { useCallback, useEffect, useRef, useState } from "react";

/** A visible region owns its request; obsolete responses cannot replace it. */
export function usePageResource<T>(key: string | null, request: (path: string) => Promise<T>, initial: T) {
  const loader = useRef(request);
  loader.current = request;
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<{key: string; data: T; loading: boolean; error: string} | null>(null);
  const reload = useCallback(() => setRevision(value => value + 1), []);
  useEffect(() => {
    if (!key) return;
    let active = true;
    setState({key, data: initial, loading: true, error: ""});
    const load = loader.current;
    Promise.resolve().then(() => active ? load(key) : undefined).then(data => {
      if (active && data !== undefined) setState({key, data, loading: false, error: ""});
    }).catch(error => {
      if (active) setState({key, data: initial, loading: false, error: error instanceof Error ? error.message : String(error)});
    });
    return () => { active = false; };
  }, [key, revision]);
  if (!key) return {data: initial, loading: false, error: "", reload};
  return state?.key === key ? {...state, reload} : {data: initial, loading: true, error: "", reload};
}
