import { useMemo } from "react";

import { useChampions } from "../api/hooks";
import type { Champion } from "../api/types";

export type ChampMaps = {
  byId: Map<number, Champion>;
  byName: Map<string, number>; // nombre en minúsculas -> id
  list: Champion[]; // catálogo ordenado por nombre (para el combobox de filtros)
  ready: boolean;
};

// Mapas derivados del catálogo /champions: id->Champion (para iconos/alias),
// nombre->id (para que los filtros acepten "Aatrox" y manden champ_id; la API
// es id-based, la resolución es del front) y la lista ordenada (para el
// combobox de campeón, que recibe el catálogo por prop en vez de re-suscribir
// el query — evita el warning de React 19 al renderizar).
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
