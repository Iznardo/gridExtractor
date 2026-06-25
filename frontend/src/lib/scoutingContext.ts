import { createContext, useContext, useEffect } from "react";

/**
 * Contexto de scouting compartido entre las ventanas de scouting de equipo
 * (Drafts, Games, Scouting): el equipo + parche elegidos se heredan al navegar
 * entre ellas, en vez de re-seleccionarse en cada una.
 *
 * Fuera, a propósito: **Scrims** (su "equipo" es el propio, no el scouteado;
 * tiene su propio localStorage) y **Picks** (búsqueda de matchups concretos,
 * no es team-scoped). Sus NavLinks no llevan ni consumen este contexto.
 *
 * Persistencia: la URL es la fuente de verdad de cada ventana; este contexto se
 * siembra en localStorage para sobrevivir entre sesiones y para que los NavLinks
 * arrastren el equipo/parche al destino.
 *
 * El `ScoutingContextProvider` vive en su propio fichero (Fast Refresh exige que
 * un módulo con componentes no exporte además hooks/utilidades).
 */

export type ScoutCtx = { team?: string; patch?: string };

const KEY = "scoutingContext";

export function readScoutCtx(): ScoutCtx {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return {};
    const o = JSON.parse(raw) as ScoutCtx;
    return { team: o.team || undefined, patch: o.patch || undefined };
  } catch {
    return {};
  }
}

export function writeScoutCtx(ctx: ScoutCtx): void {
  try {
    if (!ctx.team && !ctx.patch) localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, JSON.stringify(ctx));
  } catch {
    /* localStorage no disponible: el contexto vive solo en memoria. */
  }
}

export type ScoutCtxValue = { ctx: ScoutCtx; setCtx: (next: ScoutCtx) => void };

export const ScoutingCtx = createContext<ScoutCtxValue>({ ctx: {}, setCtx: () => {} });

export function useScoutingContext() {
  return useContext(ScoutingCtx);
}

/**
 * Sincroniza el contexto compartido con lo que la ventana tiene aplicado (lo que
 * vive en la URL). Llamar con los valores **aplicados** (de `params.get`), no con
 * el estado del formulario. Cubre de forma unificada aplicar, limpiar y la
 * entrada por enlace compartido.
 *
 * `patch === undefined` → la ventana no controla el parche (p. ej. Scouting): se
 * **conserva** el parche del contexto. `patch === ""` → la ventana lo controla y
 * está vacío: se **limpia**.
 */
export function useScoutingContextSync(team: string, patch: string | undefined) {
  const { ctx, setCtx } = useScoutingContext();
  useEffect(() => {
    const t = team || undefined;
    const p = patch === undefined ? ctx.patch : patch || undefined;
    if (t !== ctx.team || p !== ctx.patch) setCtx({ team: t, patch: p });
    // ctx/setCtx omitidos a propósito: el guard evita el bucle y solo nos
    // interesa reaccionar a cambios de lo aplicado.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [team, patch]);
}

/**
 * Añade el contexto de scouting (team + patch) a la query de una ruta. Lo usan
 * los NavLinks de Drafts/Games/Scouting para que la selección siga al analista.
 */
export function withScoutCtx(path: string, ctx: ScoutCtx): string {
  const qs = new URLSearchParams();
  if (ctx.team) qs.set("team", ctx.team);
  if (ctx.patch) qs.set("patch", ctx.patch);
  const s = qs.toString();
  return s ? `${path}?${s}` : path;
}
