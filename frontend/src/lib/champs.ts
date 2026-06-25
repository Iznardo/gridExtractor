import { useMemo } from "react";

import { useChampions } from "../api/hooks";
import type { Champion } from "../api/types";

export type ChampMaps = {
  byId: Map<number, Champion>;
  byName: Map<string, number>; // lowercase name -> id
  list: Champion[]; // catalog sorted by name (for the filter combobox)
  ready: boolean;
};

// Maps derived from the /champions catalog: id->Champion (for icons/alias),
// name->id (so filters accept "Aatrox" and send champ_id; the API is id-based,
// resolution is the frontend's job) and the sorted list (for the champion
// combobox, which receives the catalog by prop instead of re-subscribing the
// query — avoids the React 19 render warning).
export function useChampMaps(): ChampMaps {
  const { data } = useChampions();
  return useMemo(() => {
    const byId = new Map<number, Champion>();
    const byName = new Map<string, number>();
    for (const c of data ?? []) {
      byId.set(c.id, c);
      byName.set(c.name.toLowerCase(), c.id);
    }
    const list = [...(data ?? [])].sort((a, b) => a.name.localeCompare(b.name));
    return { byId, byName, list, ready: !!data };
  }, [data]);
}
