"""Helpers de paginacion GraphQL reutilizables (patron Relay).

Compartido por discovery y extraction.
"""

from __future__ import annotations

from typing import Any, Generator

from grid_minion import GridGraphQLClient


def paginate(
    client: GridGraphQLClient,
    query: str,
    root_key: str,
    variables: dict[str, Any],
) -> Generator[dict, None, None]:
    """Genera nodos de una conexion Relay paginando hasta agotar.

    Parametros:
        root_key: clave del campo raiz en `data` (ej. "allSeries", "players").
        variables: se fusionan con {"after": cursor} en cada pagina.
    """
    cursor: str | None = None
    while True:
        data = client.query_central(query, variables={**variables, "after": cursor})
        conn = data.get(root_key) or {}
        for edge in conn.get("edges") or []:
            node = edge.get("node")
            if node:
                yield node
        page = conn.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        cursor = page.get("endCursor")
        if not cursor:
            break
