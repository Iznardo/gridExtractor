import { useState } from "react";
import type { FocusEvent, MouseEvent, ReactNode } from "react";
import { createPortal } from "react-dom";

import "./tooltip.css";

type TipState = { x: number; y: number; below: boolean };

// Tooltip propio que sustituye al atributo `title` nativo. Motivo: en
// Chrome/Windows el title del navegador sale como cajita blanca del SO, sin
// estilar y con retardo — incoherente con el tema oscuro (en Firefox se integra
// mejor). Este se renderiza en un portal a <body> con position:fixed, así que
// escapa del overflow del contenedor (p. ej. .cp-wrap con overflow-x:auto) sin
// recortarse, y se ve igual en todos los navegadores. Soporta multilínea: el
// string con "\n" se respeta vía white-space:pre-line en tooltip.css.
//
// Uso: const { anchorProps, tip } = useTooltip(content);
//      <td {...anchorProps}>…{tip}</td>
export function useTooltip(content: ReactNode) {
  const [state, setState] = useState<TipState | null>(null);

  function show(e: MouseEvent | FocusEvent) {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const below = r.top < 80; // pegado al borde superior (thead sticky) → abajo
    setState({ x: r.left + r.width / 2, y: below ? r.bottom : r.top, below });
  }
  function hide() {
    setState(null);
  }

  const anchorProps = { onMouseEnter: show, onMouseLeave: hide, onFocus: show, onBlur: hide };

  const tip =
    state && content != null && content !== ""
      ? createPortal(
          <div
            className={"tip" + (state.below ? " tip-below" : "")}
            role="tooltip"
            style={{ left: state.x, top: state.y }}
          >
            {content}
          </div>,
          document.body,
        )
      : null;

  return { anchorProps, tip };
}
