import { useEffect, useState } from "react";

export function useUrlState<T extends string>(
  key: string,
  allowed: readonly T[],
  fallback: T,
): [T, (value: T) => void] {
  const read = () => {
    const value = new URLSearchParams(window.location.search).get(key);
    return value && allowed.includes(value as T) ? (value as T) : fallback;
  };
  const [state, setState] = useState<T>(read);
  useEffect(() => {
    const onPopState = () => setState(read());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [key, fallback, allowed.join("|")]);
  const update = (value: T) => {
    if (!allowed.includes(value)) return;
    setState(value);
    const url = new URL(window.location.href);
    if (value === fallback) url.searchParams.delete(key);
    else url.searchParams.set(key, value);
    window.history.replaceState({}, "", url.pathname + url.search);
  };
  return [state, update];
}
export function useUrlParam(
  key: string,
  fallback = "",
): [string, (value: string) => void] {
  const read = () => {
    const value = new URLSearchParams(window.location.search).get(key) || "";
    return value.length <= 200 ? value : fallback;
  };
  const [state, setState] = useState<string>(read);
  useEffect(() => {
    const onPopState = () => setState(read());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [key, fallback]);
  const update = (value: string) => {
    if (value.length > 200) return;
    setState(value);
    const url = new URL(window.location.href);
    if (value) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
    window.history.replaceState({}, "", url.pathname + url.search);
  };
  return [state, update];
}
