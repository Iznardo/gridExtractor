"""Conexion a PostgreSQL. Carga credenciales del entorno (.env si existe)
y entrega una conexion psycopg como context manager.

Quien la use decide cuando commitear: la conexion se entrega con
autocommit=False para que el caller controle las transacciones (el
discovery, por ejemplo, hace un solo commit al final).
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import psycopg



def db_kwargs() -> dict:
    """Parametros de conexion a Postgres desde el entorno.

    Compartido por get_conn (extractores, autocommit=False) y por el pool
    read-only de la API (que ademas fija autocommit=True y row_factory).
    """
    return {
        "host": os.environ.get("PGHOST", "localhost"),
        "port": int(os.environ.get("PGPORT", "5432")),
        "user": os.environ["PGUSER"],
        "password": os.environ["PGPASSWORD"],
        "dbname": os.environ["PGDATABASE"],
    }


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(**db_kwargs(), autocommit=False)
    try:
        yield conn
    finally:
        conn.close()
