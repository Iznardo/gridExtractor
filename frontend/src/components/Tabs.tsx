import { useState, type ReactNode } from "react";
import "./tabs.css";

export function Tabs({ tabs }: { tabs: { id: string; label: string; content: ReactNode }[] }) {
  const [active, setActive] = useState(tabs[0]?.id);
  const current = tabs.find((t) => t.id === active) ?? tabs[0];
  return (
    <div className="tabs">
      <div className="tabs-head">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            className={"tab" + (t.id === current?.id ? " active" : "")}
            onClick={() => setActive(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="tabs-body">{current?.content}</div>
    </div>
  );
}
