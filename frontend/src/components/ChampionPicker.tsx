import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, RefObject } from "react";

import type { Champion } from "../api/types";
import { ChampIcon } from "./icons";
import "./filters.css";

// Accessible combobox to pick a champion. name->id resolution stays in the
// parent page (the API is id-based); this control only guarantees the resulting
// text is a valid name (picking from the list rules out typos). The catalog
// arrives by prop, not via useChampions(): re-subscribing the query in the child
// triggers "Cannot update a component while rendering a different component" in
// React 19. It is a custom list (<ul>/<li>), not a native <datalist> — a
// datalist with dynamic <option>s caused a reconciliation loop.
const MAX_VISIBLE = 50; // cap on options rendered at once

export function ChampionPicker({
  value,
  onChange,
  champions,
  placeholder = "e.g. Aatrox",
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

  // If the text is already an exact name, no need to open on focus.
  const exact = useMemo(() => champions.some((c) => c.name.toLowerCase() === q), [champions, q]);

  // Keep the active option visible when navigating with arrows.
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
      // With the list open, Enter selects (does not submit the form). Closed,
      // let the form submit normally.
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
        // Close only when focus leaves the container (not when moving from the
        // input to an option).
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
              No matches
            </li>
          ) : (
            matches.map((c, i) => (
              <li
                key={c.id}
                id={`${listId}-opt-${i}`}
                role="option"
                aria-selected={i === active}
                className={"champ-opt" + (i === active ? " active" : "")}
                // onMouseDown (not onClick): preventDefault keeps the input
                // focus so the click registers before the blur.
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
