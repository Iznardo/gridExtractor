import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { withScoutCtx, type ScoutCtx } from "./scoutingContext";

// Window jump targets, in nav order. ctxAware routes carry the shared
// team+patch scouting context (see scoutingContext.ts); Scrims/Picks don't.
const ROUTES = [
  { key: "1", path: "/drafts", ctxAware: true },
  { key: "2", path: "/games", ctxAware: true },
  { key: "3", path: "/scouting", ctxAware: true },
  { key: "4", path: "/scrims", ctxAware: false },
  { key: "5", path: "/picks", ctxAware: false },
] as const;

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

// Prefers a real text input (the first field in every filter bar except
// Picks' mode toggle) so "/" lands where typing is actually useful; falls
// back to the first focusable control otherwise.
function focusFirstFilterControl(): boolean {
  const bar = document.querySelector<HTMLElement>(".filter-bar");
  if (!bar) return false;
  const control =
    bar.querySelector<HTMLElement>("input:not([type=hidden])") ??
    bar.querySelector<HTMLElement>("button, select, textarea, [tabindex]");
  if (!control) return false;
  control.focus();
  return true;
}

/**
 * App-wide keyboard accelerators for the expert-analyst persona (long
 * sessions, mouse-averse): "/" focuses the active window's first filter
 * control, "1".."5" jump between the five windows. Both are ignored while
 * typing in a field — so "/" and digits still type literally inside inputs —
 * and while any modifier key is held, so browser/OS shortcuts stay untouched.
 */
export function useGlobalShortcuts(ctx: ScoutCtx): void {
  const navigate = useNavigate();

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (isEditableTarget(e.target)) return;

      if (e.key === "/") {
        if (focusFirstFilterControl()) e.preventDefault();
        return;
      }

      const route = ROUTES.find((r) => r.key === e.key);
      if (route) {
        e.preventDefault();
        navigate(route.ctxAware ? withScoutCtx(route.path, ctx) : route.path);
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navigate, ctx]);
}
