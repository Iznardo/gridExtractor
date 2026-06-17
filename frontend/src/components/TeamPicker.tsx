import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import type { Team } from "../api/types";
import "./filters.css";

// Combobox para seleccionar equipo. Emite el ID como string (igual que el
// <select> que sustituye) para no cambiar la interfaz del padre. El catálogo
// llega por prop; la resolución ID↔nombre vive aquí, no en el padre.

function teamLabel(t: Team) {
  return t.tag ? `${t.tag} — ${t.name}` : t.name;
}

export function TeamPicker({
  value,
  onChange,
  teams,
  placeholder = "Buscar equipo…",
}: {
  value: string;       // ID string del equipo, "" si no hay selección
  onChange: (id: string) => void;
  teams: Team[];
  placeholder?: string;
}) {
  const listId = useId();
  const listRef = useRef<HTMLUListElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  // Cuando el valor externo se limpia (clearFilters), resetear el query.
  useEffect(() => {
    if (!value) setQuery("");
  }, [value]);

  const selectedTeam = useMemo(
    () => (value ? teams.find((t) => String(t.id) === value) ?? null : null),
    [value, teams],
  );

  // El input muestra el query mientras el usuario escribe; al cerrar sin
  // seleccionar, muestra el equipo seleccionado (o queda vacío).
  const displayValue = open ? query : (selectedTeam ? teamLabel(selectedTeam) : "");

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    const pool = q
      ? teams.filter(
          (t) =>
            t.name.toLowerCase().includes(q) ||
            (t.tag ?? "").toLowerCase().includes(q),
        )
      : teams;
    return pool.slice(0, 50);
  }, [teams, query]);

  useEffect(() => {
    if (!open) return;
    const el = listRef.current?.children[active] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  function choose(t: Team) {
    onChange(String(t.id));
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
    } else if (e.key === "Backspace" && !query && selectedTeam) {
      // Borrar la selección actual si el input ya está vacío.
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
        size={16}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          setActive(0);
          // Si el usuario borra el texto estando un equipo seleccionado, limpiar.
          if (!e.target.value && selectedTeam) onChange("");
        }}
        onFocus={() => {
          if (!selectedTeam) setOpen(true);
          else setOpen(true);  // siempre abre al enfocar para poder cambiar
        }}
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
                (cualquiera)
              </span>
            </li>
          )}
          {matches.length === 0 ? (
            <li className="champ-none" aria-disabled="true">Sin coincidencias</li>
          ) : (
            matches.map((t, i) => (
              <li
                key={t.id}
                id={`${listId}-opt-${i}`}
                role="option"
                aria-selected={i === active}
                className={"champ-opt" + (i === active ? " active" : "")}
                onMouseDown={(e) => { e.preventDefault(); choose(t); }}
                onMouseEnter={() => setActive(i)}
              >
                <span className="cn">{teamLabel(t)}</span>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
