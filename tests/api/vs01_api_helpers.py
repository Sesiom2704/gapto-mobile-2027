# ============================================================
# GAPTO MOBILE 2027
# Fichero: vs01_api_helpers.py
# Ruta: tests/api/vs01_api_helpers.py
# Descripcion: Helpers de los tests del adaptador HTTP F05-00-B (VS-01).
#   Modulo con NOMBRE UNICO e importado explicitamente por los tests: no se
#   usa conftest.py en tests/api para no reproducir la ambiguedad de
#   colecciones combinadas (D-193 / R-F04-032).
#   Los datos se crean como gapto_owner con la GUC del tenant (WM 12C.7) y son
#   sinteticos. Exigen GAPTO_TEST_DATABASE_URL apuntando a una base
#   DESECHABLE local con la cadena 0001..0330 (estos tests confirman filas).
#   v0.2.0 (F05-D003): la intencion incluye la financiacion sellada; por
#   defecto PROPUESTA_ACEPTADA self 100 % por el importe del gasto.
# Version: 0.2.0
# ============================================================

from __future__ import annotations

import os
import pathlib
import sys
import uuid

import psycopg

RAIZ_BACKEND = pathlib.Path(__file__).resolve().parents[2] / "backend"
if str(RAIZ_BACKEND) not in sys.path:
    sys.path.insert(0, str(RAIZ_BACKEND))

TOKEN = "token-desarrollo-tests-vs01-000000"


def dsn() -> str:
    valor = os.getenv("GAPTO_TEST_DATABASE_URL")
    if not valor:
        raise RuntimeError("Falta GAPTO_TEST_DATABASE_URL (base local desechable).")
    return valor


def nombre_base() -> str:
    with psycopg.connect(dsn()) as c:
        return c.execute("SELECT current_database()").fetchone()[0]


def como_owner(owner: uuid.UUID, sql: str, params: tuple = ()) -> None:
    with psycopg.connect(dsn()) as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute("SET LOCAL ROLE gapto_owner")
            cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
            cur.execute(sql, params)


def leer(owner: uuid.UUID, sql: str, params: tuple = ()) -> list[tuple]:
    with psycopg.connect(dsn()) as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute("SET LOCAL ROLE gapto_runtime")
            cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
            cur.execute(sql, params)
            return cur.fetchall()


def crear_tenant() -> tuple[uuid.UUID, uuid.UUID]:
    owner, actor = uuid.uuid4(), uuid.uuid4()
    como_owner(owner, "INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, 'VS-01 test')",
               (owner, f"{owner}@example.invalid"))
    como_owner(owner, "INSERT INTO gapto.actores_financieros (id, owner_user_id) VALUES (%s, %s)",
               (actor, owner))
    return owner, actor


def crear_actor_tercero(owner: uuid.UUID) -> uuid.UUID:
    tercero, actor = uuid.uuid4(), uuid.uuid4()
    como_owner(owner, "INSERT INTO gapto.terceros (id, owner_user_id, nombre) VALUES (%s, %s, 'Cotitular sintetico')",
               (tercero, owner))
    como_owner(owner, "INSERT INTO gapto.actores_financieros (id, owner_user_id, tercero_id) VALUES (%s, %s, %s)",
               (actor, owner, tercero))
    return actor


def crear_cuenta(owner: uuid.UUID, participaciones: list[tuple[uuid.UUID, int]], moneda: str = "EUR") -> uuid.UUID:
    """Cuenta + participaciones en UNA transaccion: la suma 100 % se valida al COMMIT."""
    cuenta = uuid.uuid4()
    with psycopg.connect(dsn()) as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute("SET LOCAL ROLE gapto_owner")
            cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
            cur.execute(
                "INSERT INTO gapto.cuentas (id, owner_user_id, nombre, tipo, naturaleza, moneda, "
                "computa_liquidez, computa_patrimonio, permite_negativo) VALUES "
                "(%s, %s, %s, 'CORRIENTE', 'ACTIVO', %s, true, true, false)",
                (cuenta, owner, f"Cuenta {moneda} sintetica", moneda))
            for actor, pct in participaciones:
                cur.execute(
                    "INSERT INTO gapto.cuenta_participaciones (cuenta_id, actor_id, porcentaje, vigente_desde) "
                    "VALUES (%s, %s, %s, DATE '2026-01-01')", (cuenta, actor, pct))
    return cuenta


def configuracion(owner: uuid.UUID, **extra):
    from app.api.configuracion import cargar_desde_entorno

    env = {
        "GAPTO_ENV": "development",
        "GAPTO_DATABASE_URL": dsn(),
        "GAPTO_DEV_OWNER_USER_ID": str(owner),
        "GAPTO_DEV_TOKEN": TOKEN,
        "GAPTO_DEV_DB_ALLOWLIST": nombre_base(),
    }
    env.update(extra)
    return cargar_desde_entorno(env)


def cliente(owner: uuid.UUID, **kw):
    from fastapi.testclient import TestClient

    from app.api.app import create_app

    return TestClient(create_app(configuracion(owner), **kw), raise_server_exceptions=False)


AUTH = {"Authorization": f"Bearer {TOKEN}"}


def propuesta_self_100(importe: str) -> dict:
    return {
        "estado": "PROPUESTA_ACEPTADA",
        "actor": "SELF",
        "criterio": "PARTICIPACION_CUENTA",
        "porcentaje": "100",
        "importe": importe,
    }


NO_DETERMINADA = {"estado": "NO_DETERMINADA"}


def intencion(cuenta: uuid.UUID, **cambios) -> dict:
    """Intencion VS-01. Si no se indica `financiacion`, se sella la propuesta
    self 100 % por el importe final (caso frecuente de cuenta propia)."""
    base = {
        "intencion_id": str(uuid.uuid4()),
        "concepto": "Café",
        "importe": "3.50",
        "moneda": "EUR",
        "fecha_hecho": "2026-09-24",
        "cuenta_id": str(cuenta),
        "presupuestable": True,
        "atribucion": "SOLO_MIO",
    }
    base.update(cambios)
    base.setdefault("financiacion", propuesta_self_100(base["importe"]))
    return base
