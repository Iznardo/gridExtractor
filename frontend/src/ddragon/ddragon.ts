// Helpers de Data Dragon (CDN público de Riot). Solo construcción de URLs y
// tipos; la carga de versión y de los catálogos (runas, spells) vive en
// useDdragon.tsx.

const DDRAGON = "https://ddragon.leagueoflegends.com";
export const FALLBACK_VERSION = "14.23.1";

export const versionsUrl = () => `${DDRAGON}/api/versions.json`;
export const runesUrl = (v: string) => `${DDRAGON}/cdn/${v}/data/en_US/runesReforged.json`;
export const summonerUrl = (v: string) => `${DDRAGON}/cdn/${v}/data/en_US/summoner.json`;

export const champIconUrl = (v: string, alias: string) =>
  `${DDRAGON}/cdn/${v}/img/champion/${alias}.png`;
export const itemIconUrl = (v: string, id: number) =>
  `${DDRAGON}/cdn/${v}/img/item/${id}.png`;
export const spellIconUrl = (v: string, imageFull: string) =>
  `${DDRAGON}/cdn/${v}/img/spell/${imageFull}`;
// Las runas (perks) y estilos usan cdn/img/ SIN versión.
export const perkIconUrl = (iconPath: string) => `${DDRAGON}/cdn/img/${iconPath}`;

// ---- formas de los JSON de Data Dragon que consumimos ----
export type RuneDef = { id: number; key: string; icon: string; name: string };
export type RuneStyle = {
  id: number;
  key: string;
  icon: string;
  name: string;
  slots: { runes: RuneDef[] }[];
};
export type RunesReforged = RuneStyle[];

export type SummonerData = {
  data: Record<string, { key: string; name: string; image: { full: string } }>;
};

// Stat shards (no están en runesReforged.json): mapa estático best-effort.
export const STAT_PERKS: Record<number, { name: string; icon: string }> = {
  5008: { name: "Fuerza Adaptativa", icon: "perk-images/StatMods/StatModsAdaptiveForceIcon.png" },
  5005: { name: "Velocidad de Ataque", icon: "perk-images/StatMods/StatModsAttackSpeedIcon.png" },
  5007: { name: "Celeridad de Habilidad", icon: "perk-images/StatMods/StatModsCDRScalingIcon.png" },
  5010: { name: "Velocidad de Movimiento", icon: "perk-images/StatMods/StatModsMovementSpeedIcon.png" },
  5001: { name: "Vida (escala)", icon: "perk-images/StatMods/StatModsHealthScalingIcon.png" },
  5011: { name: "Vida", icon: "perk-images/StatMods/StatModsHealthFlatIcon.png" },
  5013: { name: "Tenacidad", icon: "perk-images/StatMods/StatModsTenacityIcon.png" },
  5002: { name: "Armadura", icon: "perk-images/StatMods/StatModsArmorIcon.png" },
  5003: { name: "Resist. Mágica", icon: "perk-images/StatMods/StatModsMagicResIcon.png" },
};
