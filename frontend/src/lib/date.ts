/** ISO date (YYYY-MM-DD) for `n` days ago. Handy for `date_from` filters. */
export function daysAgoISO(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

/** The later (more restrictive) of an applied `dateFrom` and `days` ago —
 *  a "from" filter narrower than a section's own default window should win,
 *  but one further in the past should not widen it past that window. */
export function effectiveSince(dateFrom: string | undefined, days: number): string {
  const floor = daysAgoISO(days);
  return dateFrom && dateFrom > floor ? dateFrom : floor;
}
