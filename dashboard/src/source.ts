import { useSearchParams } from "react-router-dom";
import type { Source } from "./api";

const KEY = "monitor.source";

function stored(): Source | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "live" || v === "replay" ? v : null;
  } catch {
    return null;
  }
}

export function useSource(): [Source, (next: Source) => void] {
  const [params, setParams] = useSearchParams();
  const fromUrl = params.get("source");
  const source: Source = fromUrl === "live" || fromUrl === "replay" ? fromUrl : (stored() ?? "live");
  function set(next: Source) {
    try {
      localStorage.setItem(KEY, next);
    } catch {
      // storage unavailable (private window): the URL still carries the choice
    }
    const p = new URLSearchParams(params);
    p.set("source", next);
    setParams(p);
  }
  return [source, set];
}

export function withSource(path: string, source: Source): string {
  const [base, query = ""] = path.split("?");
  const p = new URLSearchParams(query);
  p.set("source", source);
  return `${base}?${p.toString()}`;
}
