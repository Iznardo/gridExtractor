"""Paginacion comun a todos los endpoints de listado."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query


@dataclass
class Pagination:
    limit: int
    offset: int


def pagination(
    limit: int = Query(50, ge=1, le=500, description="Maximo de filas a devolver"),
    offset: int = Query(0, ge=0, description="Filas a saltar"),
) -> Pagination:
    return Pagination(limit=limit, offset=offset)
