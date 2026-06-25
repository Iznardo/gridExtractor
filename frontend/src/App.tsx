import { NavLink, Navigate, Route, Routes } from "react-router-dom";

import { API_BASE } from "./api/client";
import { ScoutingContextProvider } from "./lib/ScoutingContextProvider";
import { useScoutingContext, withScoutCtx } from "./lib/scoutingContext";
import { Drafts } from "./pages/Drafts";
import { Games } from "./pages/Games";
import { Matchups } from "./pages/Matchups";
import { Scouting } from "./pages/Scouting";
import { Scrims } from "./pages/Scrims";
import "./App.css";

function AppShell() {
  // Contexto de scouting (equipo + parche). Solo lo arrastran las tres ventanas
  // de scouting de equipo; Scrims y Picks usan rutas planas a propósito.
  const { ctx } = useScoutingContext();

  return (
    <div className="app">
      <header className="app-header">
        <h1>
          gridExtractor <span className="muted">· scouting</span>
        </h1>
        <nav className="app-nav">
          <NavLink to={withScoutCtx("/drafts", ctx)}>Drafts</NavLink>
          <NavLink to={withScoutCtx("/games", ctx)}>Games</NavLink>
          <NavLink to={withScoutCtx("/scouting", ctx)}>Scouting</NavLink>
          <NavLink to="/scrims">Scrims</NavLink>
          <NavLink to="/picks">Picks</NavLink>
        </nav>
        <span className="api-base muted" title="Base de la API (VITE_API_BASE)">
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
