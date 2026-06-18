import { useState } from "react";
import { Download, Loader2 } from "lucide-react";

import { API_BASE } from "../api/client";

function filenameFromDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const m = /filename="?([^"]+)"?/.exec(header);
  return m ? m[1] : fallback;
}

// Botón de descarga de replay: icono solo, inline.
// Llama stopPropagation para no activar el expander del padre.
// Error: icono se vuelve rojo + tooltip con el mensaje.
export function ReplayButton({ gameId }: { gameId: number }) {
  const [state, setState] = useState<"idle" | "loading">("idle");
  const [error, setError] = useState("");

  async function download(e: React.MouseEvent) {
    e.stopPropagation();
    setError("");
    setState("loading");
    try {
      const res = await fetch(`${API_BASE}/games/${gameId}/replay`);
      if (!res.ok) {
        let detail = `Error ${res.status}`;
        try {
          const body = await res.json();
          if (typeof body?.detail === "string") detail = body.detail;
        } catch { /* sin cuerpo JSON */ }
        setError(detail);
        return;
      }
      const blob = await res.blob();
      const name = filenameFromDisposition(
        res.headers.get("Content-Disposition"),
        `replay_game_${gameId}.rofl`,
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError((err as Error).message || "Fallo de red");
    } finally {
      setState("idle");
    }
  }

  return (
    <button
      type="button"
      className={"btn-ghost btn-ghost-sm replay-btn" + (error ? " replay-btn-error" : "")}
      onClick={download}
      disabled={state === "loading"}
      title={error || "Descargar replay (.rofl)"}
      aria-label={error || "Descargar replay (.rofl)"}
    >
      {state === "loading" ? (
        <Loader2 size={13} className="spin" />
      ) : (
        <Download size={13} />
      )}
    </button>
  );
}
