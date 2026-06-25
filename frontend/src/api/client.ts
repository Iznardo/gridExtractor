// Cliente HTTP tipado contra la API read-only. Base URL configurable por
// VITE_API_BASE. Default `/api`: el dev server de Vite proxifica /api → la API
// real (ver vite.config.ts). Así el front usa su mismo origen y funciona igual
// en local que desde otro dispositivo de la LAN, sin CORS ni IP hardcodeada.

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
      /* sin cuerpo JSON */
    }
    throw new Error(`HTTP ${res.status} en ${path}${detail ? ` — ${detail}` : ""}`);
  }
  return res.json() as Promise<T>;
}
