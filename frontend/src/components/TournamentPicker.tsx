import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import "./filters.css";

// Combobox para seleccionar torneo. El catálogo es string[] (nombres directos),
// así que value y la opción elegida son el mismo string — sin resolución id↔nombre.

export function TournamentPicker({
  value,
  onChange,
  tournaments,
  placeholder = "Buscar torneo…",
}: {
  value: string;
  onChange: (v: string) => void;
  tournaments: string[];
  placeholder?: string;
}) {
  const listId = useId();
  const listRef = useRef<HTMLUListElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  useEffect(() => {
    if (!value) setQuery("");
  }, [value]);

  const displayValue = open ? query : value;

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q
      ? tournaments.filter((t) => t.toLowerCase().includes(q))
      : tournaments;
  }, [tournaments, query]);

  useEffect(() => {
    if (!open) return;
    const el = listRef.current?.children[active] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  function choose(t: string) {
    onChange(t);
    setQuery("");
    setOpen(false);
  }

  function clear() {
    onChange("");
    setQuery("");
    setOpen(false);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!open) { setOpen(true); setActive(0); return; }
      setActive((i) => Math.min(i + 1, matches.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (open) setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      if (open && matches[active]) { e.preventDefault(); choose(matches[active]); }
    } else if (e.key === "Escape") {
      if (open) { e.preventDefault(); e.stopPropagation(); setOpen(false); setQuery(""); }
    } else if (e.key === "Backspace" && !query && value) {
      e.preventDefault();
      clear();
    }
  }

  const activeId = open && matches[active] ? `${listId}-opt-${active}` : undefined;

  return (
    <div
      className="champ-combo"
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
          setOpen(false);
          setQuery("");
        }
      }}
    >
      <input
        ref={inputRef}
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={activeId}
        value={displayValue}
        placeholder={placeholder}
        autoComplete="off"
        size={18}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          setActive(0);
          if (!e.target.value && value) onChange("");
        }}
        onFocus={() => setOpen(true)}
        onClick={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />
      {open && (
        <ul className="champ-list" role="listbox" id={listId} ref={listRef}>
          {value && (
            <li
              className="champ-opt"
              role="option"
              aria-selected={false}
              onMouseDown={(e) => { e.preventDefault(); clear(); }}
            >
              <span className="cn" style={{ color: "var(--muted)", fontStyle: "italic" }}>
                (todos)
              </span>
            </li>
          )}
          {matches.length === 0 ? (
            <li className="champ-none" aria-disabled="true">Sin coincidencias</li>
          ) : (
            matches.map((t, i) => (
              <li
                key={t}
                id={`${listId}-opt-${i}`}
                role="option"
                aria-selected={i === active}
                className={"champ-opt" + (i === active ? " active" : "")}
                onMouseDown={(e) => { e.preventDefault(); choose(t); }}
                onMouseEnter={() => setActive(i)}
              >
                <span className="cn">{t}</span>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
