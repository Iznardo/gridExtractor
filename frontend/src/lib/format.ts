// Formateadores pequeños y puros para la UI.

export function kdaRatio(k = 0, d = 0, a = 0): string {
  if (d === 0) return "Perfect";
  return ((k + a) / d).toFixed(2);
}

export function kpPct(kills: number, assists: number, teamKills: number): string {
  if (!teamKills) return "—";
  return `${Math.round(((kills + assists) / teamKills) * 100)}%`;
}

export function mmss(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function perMin(total: number | undefined, durationS: number | undefined): string {
  if (total == null || !durationS) return "—";
  return (total / (durationS / 60)).toFixed(1);
}

export function teamLabel(team: { name: string; tag: string | null } | null): string {
  if (!team) return "(desconocido)";
  return team.tag ? `${team.name} (${team.tag})` : team.name;
}
