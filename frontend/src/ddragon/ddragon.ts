// Data Dragon helpers (Riot's public CDN). URL building and types only; version
// and catalog loading (runes, spells) live in useDdragon.tsx.

const DDRAGON = "https://ddragon.leagueoflegends.com";
export const FALLBACK_VERSION = "14.23.1";

export const versionsUrl = () => `${DDRAGON}/api/versions.json`;
export const runesUrl = (v: string) => `${DDRAGON}/cdn/${v}/data/en_US/runesReforged.json`;
export const summonerUrl = (v: string) => `${DDRAGON}/cdn/${v}/data/en_US/summoner.json`;
export const itemUrl = (v: string) => `${DDRAGON}/cdn/${v}/data/en_US/item.json`;

export const champIconUrl = (v: string, alias: string) =>
  `${DDRAGON}/cdn/${v}/img/champion/${alias}.png`;
export const itemIconUrl = (v: string, id: number) =>
  `${DDRAGON}/cdn/${v}/img/item/${id}.png`;
export const spellIconUrl = (v: string, imageFull: string) =>
  `${DDRAGON}/cdn/${v}/img/spell/${imageFull}`;
// Runes (perks) and styles use cdn/img/ WITHOUT a version.
export const perkIconUrl = (iconPath: string) => `${DDRAGON}/cdn/img/${iconPath}`;

// ---- shapes of the Data Dragon JSON we consume ----
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

export type ItemData = {
  data: Record<string, { name: string }>;
};

// Stat shards (not in runesReforged.json): best-effort static map.
export const STAT_PERKS: Record<number, { name: string; icon: string }> = {
  5008: { name: "Adaptive Force", icon: "perk-images/StatMods/StatModsAdaptiveForceIcon.png" },
  5005: { name: "Attack Speed", icon: "perk-images/StatMods/StatModsAttackSpeedIcon.png" },
  5007: { name: "Ability Haste", icon: "perk-images/StatMods/StatModsCDRScalingIcon.png" },
  5010: { name: "Movement Speed", icon: "perk-images/StatMods/StatModsMovementSpeedIcon.png" },
  5001: { name: "Health (scaling)", icon: "perk-images/StatMods/StatModsHealthScalingIcon.png" },
  5011: { name: "Health", icon: "perk-images/StatMods/StatModsHealthFlatIcon.png" },
  5013: { name: "Tenacity", icon: "perk-images/StatMods/StatModsTenacityIcon.png" },
  5002: { name: "Armor", icon: "perk-images/StatMods/StatModsArmorIcon.png" },
  5003: { name: "Magic Resist", icon: "perk-images/StatMods/StatModsMagicResIcon.png" },
};
