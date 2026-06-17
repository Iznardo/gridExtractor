import { NavLink, Navigate, Route, Routes } from "react-router-dom";

import { API_BASE } from "./api/client";
import { Drafts } from "./pages/Drafts";
import { Games } from "./pages/Games";
import { Scouting } from "./pages/Scouting";
import "./App.css";

function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>
          gridExtractor <span className="muted">· scouting</span>
        </h1>
        <nav className="app-nav">
          <NavLink to="/drafts">Drafts</NavLink>
          <NavLink to="/games">Games</NavLink>
          <NavLink to="/scouting">Scouting</NavLink>
        </nav>
        <span className="api-base muted" title="Base de la API (VITE_API_BASE)">
          {API_BASE}
        </span>
      </header>

      <main className="app-main">
        <Routes>
          <Route path="/" element={<Navigate to="/drafts" replace />} />
          <Route path="/drafts" element={<Drafts />} />
          <Route path="/games" element={<Games />} />
          <Route path="/scouting" element={<Scouting />} />
          <Route path="*" element={<Navigate to="/drafts" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
