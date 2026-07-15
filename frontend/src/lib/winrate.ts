// Shared win-rate credibility gate. A win rate from a tiny sample (a 1-game
// 100%) must not render with the same visual confidence as one from a large
// sample (a 40-game 65%) — that contradicts the product's core promise
// ("confianza en el dato", PRODUCT.md). Every view that colors or arrows a WR
// must gate through here instead of re-deciding its own threshold.
export const WR_MIN_GAMES = 3;

export type WrStatus = "pos" | "neg" | "neutral";

/** "pos"/"neg" only once the sample reaches WR_MIN_GAMES; otherwise "neutral"
 *  — the % still renders (see each page's WR display), just without color or
 *  directional glyph, so a small sample never reads as a trustworthy trend. */
export function wrStatus(wr: number | null, games: number): WrStatus {
  if (wr == null || games < WR_MIN_GAMES) return "neutral";
  if (wr >= 55) return "pos";
  if (wr <= 45) return "neg";
  return "neutral";
}

// Directional glyph: WR is not conveyed by color alone (color blindness).
// Empty string below the games gate, same as when the WR itself is neutral.
export function wrArrow(wr: number | null, games: number): string {
  const status = wrStatus(wr, games);
  if (status === "pos") return "▲";
  if (status === "neg") return "▼";
  return "";
}
