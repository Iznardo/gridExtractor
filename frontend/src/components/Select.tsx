import { useEffect, useId, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent } from "react";

import "./filters.css";

// Custom listbox replacing the native <select> in the filter bars.
// Why: on Chrome/Linux a <select>'s dropdown is drawn by the OS (GTK) and does
// not respect the dark theme — inconsistent against Firefox. This control is
// 100% custom DOM (button + <ul role="listbox">), so it renders the same in
// every browser. Same visual and keyboard language as TeamPicker /
// ChampionPicker (reuses .champ-list / .champ-opt from filters.css).
//
// API deliberately identical to the <select> it replaces: value string +
// onChange(value) — the parent does not change. No search: it is for fixed or
// short lists (role, patch, type...); for large catalogs use the pickers.

export type SelectOption = { value: string; label: string; title?: string };

export function Select({
  value,
  onChange,
  options,
  placeholder = "—",
  minWidth,
  ariaLabel,
}: {
  value: string;
  onChange: (v: string) => void;
  options: SelectOption[];
  placeholder?: string;
  minWidth?: number;
  ariaLabel?: string;
}) {
  const listId = useId();
  const listRef = useRef<HTMLUListElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  const selectedIndex = options.findIndex((o) => o.value === value);
  const selected = selectedIndex >= 0 ? options[selectedIndex] : null;

  // On open, the keyboard cursor starts on the already-selected option.
  function openMenu() {
    setActive(selectedIndex >= 0 ? selectedIndex : 0);
    setOpen(true);
  }

  // Keep the active option in view when navigating with arrows.
  useEffect(() => {
    if (!open) return;
    const el = listRef.current?.children[active] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  function choose(i: number) {
    onChange(options[i].value);
    setOpen(false);
    btnRef.current?.focus();
  }

  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!open) { openMenu(); return; }
      setActive((i) => Math.min(i + 1, options.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) { openMenu(); return; }
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Home") {
      if (open) { e.preventDefault(); setActive(0); }
    } else if (e.key === "End") {
      if (open) { e.preventDefault(); setActive(options.length - 1); }
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (!open) openMenu();
      else choose(active);
    } else if (e.key === "Escape") {
      if (open) { e.preventDefault(); e.stopPropagation(); setOpen(false); }
    }
  }

  const triggerStyle: CSSProperties | undefined = minWidth ? { minWidth } : undefined;

  return (
    <div
      className="select-combo"
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(false);
      }}
    >
      <button
        ref={btnRef}
        type="button"
        className={"select-trigger" + (selected ? "" : " is-placeholder")}
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={ariaLabel}
        aria-activedescendant={open ? `${listId}-opt-${active}` : undefined}
        style={triggerStyle}
        onClick={() => (open ? setOpen(false) : openMenu())}
        onKeyDown={onKeyDown}
      >
        <span className="select-value">{selected ? selected.label : placeholder}</span>
        <svg className="select-caret" width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
          <path
            d="M2 3.5 L5 6.5 L8 3.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      {open && (
        <ul className="champ-list select-list" role="listbox" id={listId} ref={listRef}>
          {options.map((o, i) => (
            <li
              key={o.value}
              id={`${listId}-opt-${i}`}
              role="option"
              aria-selected={o.value === value}
              title={o.title}
              className={
                "champ-opt" +
                (i === active ? " active" : "") +
                (o.value === value ? " selected" : "")
              }
              onMouseDown={(e) => { e.preventDefault(); choose(i); }}
              onMouseEnter={() => setActive(i)}
            >
              <span className="cn">{o.label}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
