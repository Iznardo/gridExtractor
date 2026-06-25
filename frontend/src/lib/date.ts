/** ISO date (YYYY-MM-DD) for `n` days ago. Handy for `date_from` filters. */
export function daysAgoISO(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}
