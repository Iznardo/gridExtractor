import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, RefObject } from "react";

import type { Champion } from "../api/types";
import { ChampIcon } from "./icons";
import "./filters.css";

// Combobox accesible para elegir campeón. La resolución nombre->id la sigue
// haciendo la página padre (la API es id-based); este control solo garantiza
// que el texto resultante sea un nombre válido (al elegir de la lista no hay
// typo posible). El catálogo llega por prop, no por useChampions(): re-suscribir
// el query en el hijo dispara "Cannot update a component while rendering a
// different component" en React 19. Es una lista propia (<ul>/<li>), no un
// <datalist> nativo — el datalist con <option> dinámicos causaba un loop de
// reconciliación.
const MAX_VISIBLE = 50; // tope de opciones renderizadas a la vez

export function ChampionPicker({
  value,
  onChange,
  champions,
  placeholder = "ej. Aatrox",
  hasError,
  inputRef: externalRef,
}: {
  value: string;
  onChange: (v: string) => void;
  champions: Champion[];
  placeholder?: string;
  hasError?: boolean;
  inputRef?: RefObject<HTMLInputElement | null>;
}) {
  const listId = useId();
  const listRef = useRef<HTMLUListElement>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  const q = value.trim().toLowerCase();

  const matches = useMemo(() => {
    const pool = q
      ? champions.filter(
          (c) => c.name.toLowerCase().includes(q) || c.alias.toLowerCase().includes(q),
        )
      : champions;
    return pool.slice(0, MAX_VISIBLE);
  }, [champions, q]);

  // Si el texto ya es un nombre exacto, no hace falta abrir al enfocar.
  const exact = useMemo(() => champions.some((c) => c.name.toLowerCase() === q), [champions, q]);

  // Mantener visible la opción activa al navegar con flechas.
  useEffect(() => {
    if (!open) return;
    const el = listRef.current?.children[active] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  function choose(c: Champion) {
    onChange(c.name);
    setOpen(false);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!open) {
        setOpen(true);
        setActive(0);
        return;
      }
      setActive((i) => Math.min(i + 1, matches.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (open) setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      // Con la lista abierta, Enter elige (no envía el formulario). Cerrada,
      // deja que el form se envíe normalmente.
      if (open && matches[active]) {
        e.preventDefault();
        choose(matches[active]);
      }
    } else if (e.key === "Escape") {
      if (open) {
        e.preventDefault();
        e.stopPropagation();
        setOpen(false);
      }
    }
  }

  const activeId = open && matches[active] ? `${listId}-opt-${active}` : undefined;

  return (
    <div
      className="champ-combo"
      onBlur={(e) => {
        // Cerrar solo cuando el foco sale del contenedor (no al pasar del input
        // a una opción).
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(false);
      }}
    >
      <input
        ref={externalRef}
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={activeId}
        aria-invalid={hasError || undefined}
        value={value}
        placeholder={placeholder}
        autoComplete="off"
        size={14}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          setActive(0);
        }}
        onFocus={() => {
          if (!exact) setOpen(true);
        }}
        onKeyDown={onKeyDown}
      />
      {open && (
        <ul className="champ-list" role="listbox" id={listId} ref={listRef}>
          {matches.length === 0 ? (
            <li className="champ-none" aria-disabled="true">
              Sin coincidencias
            </li>
          ) : (
            matches.map((c, i) => (
              <li
                key={c.id}
                id={`${listId}-opt-${i}`}
                role="option"
                aria-selected={i === active}
                className={"champ-opt" + (i === active ? " active" : "")}
                // onMouseDown (no onClick): preventDefault conserva el foco del
                // input para que el click se registre antes del blur.
                onMouseDown={(e) => {
                  e.preventDefault();
                  choose(c);
                }}
                onMouseEnter={() => setActive(i)}
              >
                <ChampIcon id={c.id} name={c.name} size={22} />
                <span className="cn">{c.name}</span>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
