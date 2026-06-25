import { useEffect, useId, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent } from "react";

import "./filters.css";

// Listbox propio que sustituye a los <select> nativos en las barras de filtro.
// Motivo: en Chrome/Linux la lista desplegada de un <select> la dibuja el SO
// (GTK) y no respeta el tema oscuro — se ve incoherente frente a Firefox. Este
// control es 100% DOM propio (botón + <ul role="listbox">), así que se renderiza
// igual en todos los navegadores. Mismo lenguaje visual y de teclado que
// TeamPicker / ChampionPicker (reutiliza .champ-list / .champ-opt de filters.css).
//
// API deliberadamente igual a la del <select> que reemplaza: value string +
// onChange(value) — el padre no cambia. No hay búsqueda: es para listas fijas o
// cortas (rol, parche, tipo…); para catálogos grandes seguir usando los pickers.

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

  // Al abrir, el cursor de teclado arranca sobre la opción ya seleccionada.
  function openMenu() {
    setActive(selectedIndex >= 0 ? selectedIndex : 0);
    setOpen(true);
  }

  // Mantener la opción activa a la vista al navegar con flechas.
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
