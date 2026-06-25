import { useState } from "react";
import type { FocusEvent, MouseEvent, ReactNode } from "react";
import { createPortal } from "react-dom";

import "./tooltip.css";

type TipState = { x: number; y: number; below: boolean };

// Custom tooltip replacing the native `title` attribute. Why: on Chrome/Windows
// the browser title shows as an unstyled OS box with a delay — inconsistent with
// the dark theme (Firefox integrates better). This renders in a portal to <body>
// with position:fixed, so it escapes the container's overflow (e.g. .cp-wrap
// with overflow-x:auto) without clipping, and looks the same in every browser.
// Supports multiline: a string with "\n" is honored via white-space:pre-line in
// tooltip.css.
//
// Usage: const { anchorProps, tip } = useTooltip(content);
//        <td {...anchorProps}>…{tip}</td>
export function useTooltip(content: ReactNode) {
  const [state, setState] = useState<TipState | null>(null);

  function show(e: MouseEvent | FocusEvent) {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const below = r.top < 80; // near the top edge (sticky thead) -> show below
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
