import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import "./tabs.css";

interface TabDef { id: string; label: string; content: ReactNode }

interface TabsProps {
  tabs: TabDef[];
  /** Controlled active tab id. Omit for uncontrolled (internal state). */
  value?: string;
  /** Called when the user switches tabs (controlled mode only). */
  onChange?: (id: string) => void;
}

export function Tabs({ tabs, value, onChange }: TabsProps) {
  const [internal, setInternal] = useState(tabs[0]?.id);
  const uid = useId();
  const activeId = value ?? internal;
  const current = tabs.find((t) => t.id === activeId) ?? tabs[0];
  const btnRefs = useRef<(HTMLButtonElement | null)[]>([]);

  function handleTab(id: string) {
    if (onChange) onChange(id);
    else setInternal(id);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const idx = tabs.findIndex((t) => t.id === activeId);
    let next = idx;
    if (e.key === "ArrowRight") next = (idx + 1) % tabs.length;
    else if (e.key === "ArrowLeft") next = (idx - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = tabs.length - 1;
    else return;
    e.preventDefault();
    const nextTab = tabs[next];
    if (nextTab) {
      handleTab(nextTab.id);
      btnRefs.current[next]?.focus();
    }
  }

  return (
    <div className="tabs">
      <div className="tabs-head" role="tablist" onKeyDown={handleKeyDown}>
        {tabs.map((t, i) => (
          <button
            key={t.id}
            ref={(el) => { btnRefs.current[i] = el; }}
            type="button"
            id={`${uid}-tab-${t.id}`}
            role="tab"
            aria-selected={t.id === current?.id}
            aria-controls={`${uid}-panel-${t.id}`}
            tabIndex={t.id === current?.id ? 0 : -1}
            className={"tab" + (t.id === current?.id ? " active" : "")}
            onClick={() => handleTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div
        id={`${uid}-panel-${current?.id}`}
        role="tabpanel"
        aria-labelledby={`${uid}-tab-${current?.id}`}
        className="tabs-body"
      >
        {current?.content}
      </div>
    </div>
  );
}
