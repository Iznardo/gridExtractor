import { useState, type ReactNode } from "react";

import {
  ScoutingCtx,
  readScoutCtx,
  writeScoutCtx,
  type ScoutCtx,
} from "./scoutingContext";

/** Scouting context provider (team + patch). See `scoutingContext.ts`. */
export function ScoutingContextProvider({ children }: { children: ReactNode }) {
  const [ctx, setCtxState] = useState<ScoutCtx>(readScoutCtx);

  function setCtx(next: ScoutCtx) {
    const clean: ScoutCtx = { team: next.team || undefined, patch: next.patch || undefined };
    setCtxState(clean);
    writeScoutCtx(clean);
  }

  return <ScoutingCtx.Provider value={{ ctx, setCtx }}>{children}</ScoutingCtx.Provider>;
}
