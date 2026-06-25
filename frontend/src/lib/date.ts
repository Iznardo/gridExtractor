/** Fecha ISO (YYYY-MM-DD) de hace `n` días. Útil para filtros `date_from`. */
export function daysAgoISO(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}
