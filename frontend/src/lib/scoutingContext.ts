import { createContext, useContext, useEffect } from "react";

/**
 * Scouting context shared across the team-scouting windows (Drafts, Games,
 * Scouting): the chosen team + patch carry over when navigating between them,
 * instead of being re-selected in each.
 *
 * Excluded on purpose: **Scrims** (its "team" is your own, not the scouted one;
 * it has its own localStorage) and **Picks** (specific matchup search, not
 * team-scoped). Their NavLinks neither carry nor consume this context.
 *
 * Persistence: the URL is each window's source of truth; this context is seeded
 * into localStorage to survive between sessions and so the NavLinks carry the
 * team/patch to the destination.
 *
 * `ScoutingContextProvider` lives in its own file (Fast Refresh requires that a
 * module with components not also export hooks/utilities).
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
    /* localStorage unavailable: the context lives in memory only. */
  }
}

export type ScoutCtxValue = { ctx: ScoutCtx; setCtx: (next: ScoutCtx) => void };

export const ScoutingCtx = createContext<ScoutCtxValue>({ ctx: {}, setCtx: () => {} });

export function useScoutingContext() {
  return useContext(ScoutingCtx);
}

/**
 * Sync the shared context with what the window has applied (what lives in the
 * URL). Call with the **applied** values (from `params.get`), not the form
 * state. Covers applying, clearing and shared-link entry in one path.
 *
 * `patch === undefined` -> the window does not control the patch (e.g. Scouting):
 * the context patch is **kept**. `patch === ""` -> the window controls it and it
 * is empty: it is **cleared**.
 */
export function useScoutingContextSync(team: string, patch: string | undefined) {
  const { ctx, setCtx } = useScoutingContext();
  useEffect(() => {
    const t = team || undefined;
    const p = patch === undefined ? ctx.patch : patch || undefined;
    if (t !== ctx.team || p !== ctx.patch) setCtx({ team: t, patch: p });
    // ctx/setCtx omitted on purpose: the guard prevents the loop and we only
    // care about reacting to changes in what is applied.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [team, patch]);
}

/**
 * Append the scouting context (team + patch) to a route's query. Used by the
 * Drafts/Games/Scouting NavLinks so the selection follows the analyst.
 */
export function withScoutCtx(path: string, ctx: ScoutCtx): string {
  const qs = new URLSearchParams();
  if (ctx.team) qs.set("team", ctx.team);
  if (ctx.patch) qs.set("patch", ctx.patch);
  const s = qs.toString();
  return s ? `${path}?${s}` : path;
}
