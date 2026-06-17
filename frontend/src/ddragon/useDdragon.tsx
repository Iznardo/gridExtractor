import { createContext, useContext, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  FALLBACK_VERSION,
  runesUrl,
  summonerUrl,
  versionsUrl,
  type RuneDef,
  type RuneStyle,
  type RunesReforged,
  type SummonerData,
} from "./ddragon";

export type DdragonData = {
  version: string;
  perks: Map<number, RuneDef>; // todas las runas (no shards) por id
  styles: Map<number, RuneStyle>; // árboles (Domination, etc.) por id
  spells: Map<number, { name: string; image: string }>; // summoner spells por id
};

const EMPTY: DdragonData = {
  version: FALLBACK_VERSION,
  perks: new Map(),
  styles: new Map(),
  spells: new Map(),
};

async function loadDdragon(): Promise<DdragonData> {
  let version = FALLBACK_VERSION;
  try {
    const versions: string[] = await (await fetch(versionsUrl())).json();
    if (versions?.[0]) version = versions[0];
  } catch {
    /* usa fallback */
  }

  const perks = new Map<number, RuneDef>();
  const styles = new Map<number, RuneStyle>();
  const spells = new Map<number, { name: string; image: string }>();

  try {
    const reforged: RunesReforged = await (await fetch(runesUrl(version))).json();
    for (const style of reforged) {
      styles.set(style.id, style);
      for (const slot of style.slots) {
        for (const rune of slot.runes) perks.set(rune.id, rune);
      }
    }
  } catch {
    /* runas no disponibles */
  }

  try {
    const summoner: SummonerData = await (await fetch(summonerUrl(version))).json();
    for (const s of Object.values(summoner.data)) {
      spells.set(Number(s.key), { name: s.name, image: s.image.full });
    }
  } catch {
    /* spells no disponibles */
  }

  return { version, perks, styles, spells };
}

const DdragonContext = createContext<DdragonData>(EMPTY);

export function DdragonProvider({ children }: { children: ReactNode }) {
  const { data } = useQuery({
    queryKey: ["ddragon"],
    queryFn: loadDdragon,
    staleTime: 24 * 60 * 60 * 1000,
  });
  return (
    <DdragonContext.Provider value={data ?? EMPTY}>{children}</DdragonContext.Provider>
  );
}

export function useDdragon(): DdragonData {
  return useContext(DdragonContext);
}
