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

// Imagen con fallback: si falla la carga, se oculta (deja ver el texto al
// lado). Guardamos el src que falló (no un booleano) para que, al cambiar el
// src — misma posición de icono renderizando otro campeón al re-filtrar — la
// imagen vuelva a intentarse en lugar de quedarse en blanco.
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
  const { version } = useDdragon();
  if (!id) return <span className="item-empty" style={{ width: size, height: size }} />;
  return <Img className="icon-sq" size={size} src={itemIconUrl(version, id)} alt={`item ${id}`} />;
}

export function SpellIcon({ id, size = 22 }: { id: number; size?: number }) {
  const { version, spells } = useDdragon();
  const spell = spells.get(id);
  if (!spell) return <span className="item-empty" style={{ width: size, height: size }} />;
  return <Img className="icon-sq" size={size} src={spellIconUrl(version, spell.image)} alt={spell.name} />;
}

// Runa (perk) por id: keystone o runa menor. Si no está en runesReforged,
// prueba el mapa de stat shards.
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

// Icono del árbol de runas (estilo: Domination, Precision...).
export function RuneStyleIcon({ id, size = 20 }: { id: number; size?: number }) {
  const { styles } = useDdragon();
  const style = styles.get(id);
  if (!style) return null;
  return <Img className="icon-round" size={size} src={perkIconUrl(style.icon)} alt={style.name} />;
}
