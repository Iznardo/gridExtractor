// Typed HTTP client against the read-only API. Base URL configurable via
// VITE_API_BASE. Default `/api`: the Vite dev server proxies /api -> the real
// API (see vite.config.ts). This way the frontend uses its own origin and works
// the same locally as from another LAN device, with no CORS or hardcoded IP.

export const API_BASE: string =
  import.meta.env.VITE_API_BASE ?? "/api";

export type QueryParams = Record<
  string,
  string | number | boolean | null | undefined
>;

export function buildQuery(params: QueryParams): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === "") continue;
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(API_BASE + path);
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail ?? "");
    } catch {
      /* no JSON body */
    }
    throw new Error(`HTTP ${res.status} on ${path}${detail ? ` — ${detail}` : ""}`);
  }
  return res.json() as Promise<T>;
}
