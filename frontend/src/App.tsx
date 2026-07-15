import { NavLink, Navigate, Route, Routes } from "react-router-dom";

import { API_BASE } from "./api/client";
import { ScoutingContextProvider } from "./lib/ScoutingContextProvider";
import { useGlobalShortcuts } from "./lib/useGlobalShortcuts";
import { useScoutingContext, withScoutCtx } from "./lib/scoutingContext";
import { Drafts } from "./pages/Drafts";
import { Games } from "./pages/Games";
import { Matchups } from "./pages/Matchups";
import { Scouting } from "./pages/Scouting";
import { Scrims } from "./pages/Scrims";
import "./App.css";

// Nav key hints are aria-hidden: the shortcut is a bonus for the sighted
// mouse-averse user, not part of the link's accessible name.
function NavKey({ children }: { children: string }) {
  return (
    <span className="app-nav-key" aria-hidden="true">
      {children}
    </span>
  );
}

function AppShell() {
  // Scouting context (team + patch). Only the three team-scouting windows carry
  // it; Scrims and Picks use flat routes on purpose.
  const { ctx } = useScoutingContext();
  useGlobalShortcuts(ctx);

  return (
    <div className="app">
      <header className="app-header">
        <h1>
          gridExtractor <span className="muted">· scouting</span>
        </h1>
        <nav className="app-nav">
          <NavLink to={withScoutCtx("/drafts", ctx)}>Drafts<NavKey>1</NavKey></NavLink>
          <NavLink to={withScoutCtx("/games", ctx)}>Games<NavKey>2</NavKey></NavLink>
          <NavLink to={withScoutCtx("/scouting", ctx)}>Scouting<NavKey>3</NavKey></NavLink>
          <NavLink to="/scrims">Scrims<NavKey>4</NavKey></NavLink>
          <NavLink to="/picks">Picks<NavKey>5</NavKey></NavLink>
        </nav>
        <span
          className="app-shortcut-hint muted"
          title="Keyboard shortcuts: / focuses the filter bar, 1-5 jump between windows"
        >
          / · 1-5
        </span>
        <span className="api-base muted" title="API base (VITE_API_BASE)">
          {API_BASE}
        </span>
      </header>

      <main className="app-main">
        <Routes>
          <Route path="/" element={<Navigate to={withScoutCtx("/drafts", ctx)} replace />} />
          <Route path="/drafts" element={<Drafts />} />
          <Route path="/games" element={<Games />} />
          <Route path="/scouting" element={<Scouting />} />
          <Route path="/scrims" element={<Scrims />} />
          <Route path="/picks" element={<Matchups />} />
          <Route path="*" element={<Navigate to={withScoutCtx("/drafts", ctx)} replace />} />
        </Routes>
      </main>
    </div>
  );
}

function App() {
  return (
    <ScoutingContextProvider>
      <AppShell />
    </ScoutingContextProvider>
  );
}

export default App;
