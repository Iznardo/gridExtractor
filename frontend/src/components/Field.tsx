import type { ReactNode } from "react";
import "./filters.css";

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
    </label>
  );
}

export function FilterBar({ children, onSubmit }: { children: ReactNode; onSubmit: () => void }) {
  return (
    <form
      className="filter-bar"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      {children}
    </form>
  );
}
