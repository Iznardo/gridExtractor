import { useState } from "react";

import { useDdragon } from "../ddragon/useDdragon";
import {
  STAT_PERKS,
  champIconUrl,
  itemIconUrl,
  perkIconUrl,
  spellIconUrl,
} from "../ddragon/ddragon";
import { useChampMaps } from "../lib/champs";
import "./icons.css";

type ImgProps = { src: string; alt: string; title?: string; className?: string; size?: number };

// Image with fallback: if loading fails it hides (showing the text beside it).
// We store the src that failed (not a boolean) so that when the src changes —
// same icon position rendering another champion on re-filter — the image is
// retried instead of staying blank.
function Img({ src, alt, title, className, size }: ImgProps) {
  const [brokenSrc, setBrokenSrc] = useState<string | null>(null);
  if (brokenSrc === src) return null;
  return (
    <img
      src={src}
      alt={alt}
      title={title ?? alt}
      className={className}
      width={size}
      height={size}
      style={size != null ? { width: size, height: size, flexShrink: 0 } : undefined}
      loading="lazy"
      onError={() => setBrokenSrc(src)}
    />
  );
}

export function ChampIcon({ id, name, size = 28 }: { id: number; name?: string | null; size?: number }) {
  const { version } = useDdragon();
  const { byId } = useChampMaps();
  const champ = byId.get(id);
  const label = name ?? champ?.name ?? `#${id}`;
  if (!champ) return <span className="icon-fallback" title={label}>{label}</span>;
  return <Img className="icon-sq" size={size} src={champIconUrl(version, champ.alias)} alt={label} />;
}

export function ItemIcon({ id, size = 24 }: { id: number; size?: number }) {
  const { version, items } = useDdragon();
  if (!id) return <span className="item-empty" style={{ width: size, height: size }} />;
  const name = items.get(id) ?? `item ${id}`;
  return <Img className="icon-sq" size={size} src={itemIconUrl(version, id)} alt={name} />;
}

export function SpellIcon({ id, size = 22 }: { id: number; size?: number }) {
  const { version, spells } = useDdragon();
  const spell = spells.get(id);
  if (!spell) return <span className="item-empty" style={{ width: size, height: size }} />;
  return <Img className="icon-sq" size={size} src={spellIconUrl(version, spell.image)} alt={spell.name} />;
}

// Rune (perk) by id: keystone or minor rune. If not in runesReforged, try the
// stat shards map.
export function RuneIcon({ id, size = 22 }: { id: number; size?: number }) {
  const { perks } = useDdragon();
  const perk = perks.get(id);
  if (perk) {
    return <Img className="icon-round" size={size} src={perkIconUrl(perk.icon)} alt={perk.name} />;
  }
  const stat = STAT_PERKS[id];
  if (stat) {
    return <Img className="icon-round" size={size} src={perkIconUrl(stat.icon)} alt={stat.name} />;
  }
  return <span className="item-empty" style={{ width: size, height: size }} />;
}

// Rune tree icon (style: Domination, Precision...).
export function RuneStyleIcon({ id, size = 20 }: { id: number; size?: number }) {
  const { styles } = useDdragon();
  const style = styles.get(id);
  if (!style) return null;
  return <Img className="icon-round" size={size} src={perkIconUrl(style.icon)} alt={style.name} />;
}
