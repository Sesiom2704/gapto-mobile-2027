# ============================================================
# GAPTO MOBILE 2027
# Fichero: f05_01_helpers.py
# Ruta: tests/api/f05_01_helpers.py
# Descripcion: Helpers de los tests de F05-01 (categorias). Modulo con NOMBRE
#   UNICO importado explicitamente (D-193): no hay conftest en tests/api.
#   Reutiliza vs01_api_helpers para tenant, cuenta y cliente HTTP. Los datos
#   de fixture son sinteticos y se crean como gapto_owner con la GUC del
#   tenant (WM 12C.7). Exigen GAPTO_TEST_DATABASE_URL apuntando a una base
#   DESECHABLE con la cadena 0001..0340 (estos tests confirman filas).
#
#   v0.1.1: `pid_servidor` obtiene el PID con `pg_backend_pid()`. El
#   `info.backend_pid` del cliente es el que anuncia el protocolo
#   (BackendKeyData); detras del proxy de Neon NO coincide con el PID real del
#   servidor y el test no podia localizar su propia sesion en
#   pg_stat_activity (fallo de test observado en gapto2027_cleanroom).
# Version: 0.1.1
# ============================================================

from __future__ import annotations

import time
import uuid

import psycopg

import vs01_api_helpers as h


def unidad():
    """UnidadDeTrabajo de tests: conexion por intento y SET LOCAL ROLE
    gapto_runtime, igual que el adaptador HTTP."""
    from contextlib import contextmanager

    from app.core.unidad_trabajo import UnidadDeTrabajo

    @contextmanager
    def _abrir():
        with psycopg.connect(h.dsn()) as conexion:
            yield conexion

    return UnidadDeTrabajo(_abrir, rol_runtime="gapto_runtime")


def en_transaccion(owner: uuid.UUID, operacion):
    from app.core.contexto import ContextoOperacion

    ctx = ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4())
    return unidad().ejecutar(ctx, operacion, nombre="test F05-01")


def crear_categoria(
    owner: uuid.UUID,
    nombre: str,
    ambito: str = "GASTO",
    *,
    parent_id: uuid.UUID | None = None,
    enabled: bool = True,
    orden: int = 0,
    icon_key: str | None = None,
) -> uuid.UUID:
    cid = uuid.uuid4()
    h.como_owner(
        owner,
        "INSERT INTO gapto.categorias_financieras (id, owner_user_id, parent_id, nombre, ambito, "
        "presupuestable_default, orden, enabled, icon_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (cid, owner, parent_id, nombre, ambito, ambito == "GASTO", orden, enabled, icon_key),
    )
    return cid


def crear_magnitud_categoria(owner: uuid.UUID, categoria_id: uuid.UUID, *, obligatoria: bool) -> None:
    mid = uuid.uuid4()
    h.como_owner(
        owner,
        "INSERT INTO gapto.magnitudes (id, owner_user_id, nombre, unidad_default, precision_decimales) "
        "VALUES (%s, %s, %s, 'l', 2)",
        (mid, owner, f"Litros {mid.hex[:6]}"),
    )
    h.como_owner(
        owner,
        "INSERT INTO gapto.categoria_magnitudes (categoria_id, magnitud_id, obligatoria) VALUES (%s, %s, %s)",
        (categoria_id, mid, obligatoria),
    )


def categoria_del_efecto(owner: uuid.UUID, hecho_id: uuid.UUID) -> list[tuple]:
    return h.leer(owner, "SELECT categoria_id FROM gapto.hecho_efectos WHERE hecho_id = %s", (hecho_id,))


def huella_agregado(owner: uuid.UUID, hecho_id: uuid.UUID) -> dict[str, int]:
    """Recuento de TODO lo que la intencion podria haber escrito. Un rechazo
    correcto deja todo a cero (sin mutacion parcial)."""
    consultas = {
        "hechos": "SELECT count(*) FROM gapto.hechos_financieros WHERE id=%s",
        "efectos": "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id=%s",
        "conciliaciones": "SELECT count(*) FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id=%s",
        "aportaciones": "SELECT count(*) FROM gapto.hecho_aportaciones_pago WHERE hecho_id=%s",
        "auditoria": "SELECT count(*) FROM gapto.auditoria WHERE registro_id=%s",
    }
    return {k: h.leer(owner, q, (hecho_id,))[0][0] for k, q in consultas.items()}


def sesion_owner(owner: uuid.UUID) -> psycopg.Connection:
    """Conexion con transaccion abierta como gapto_owner y GUC del tenant. El
    llamador decide COMMIT/ROLLBACK y cierra."""
    c = psycopg.connect(h.dsn())
    cur = c.cursor()
    cur.execute("BEGIN")
    cur.execute("SET LOCAL ROLE gapto_owner")
    cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
    return c


def pid_servidor(conexion: psycopg.Connection) -> int:
    """PID REAL del backend, valido para cruzar con pg_stat_activity."""
    return conexion.execute("SELECT pg_backend_pid()").fetchone()[0]


def esperar_bloqueo(pids_excluidos: tuple[int, ...], limite_s: float = 8.0, minimo: int = 1) -> bool:
    """True si al menos `minimo` sesiones de esta base (excluidas las dadas)
    quedan esperando un lock (WM 12C.1: el bloqueo debe OBSERVARSE)."""
    fin = time.monotonic() + limite_s
    with psycopg.connect(h.dsn(), autocommit=True) as mon:
        while time.monotonic() < fin:
            fila = mon.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                "AND pid <> ALL(%s) AND pid <> pg_backend_pid() AND wait_event_type = 'Lock'",
                (list(pids_excluidos),),
            ).fetchone()
            if fila[0] >= minimo:
                return True
            time.sleep(0.05)
    return False


def pids_esperando(pids: tuple[int, ...]) -> set[int]:
    with psycopg.connect(h.dsn(), autocommit=True) as mon:
        filas = mon.execute(
            "SELECT pid FROM pg_stat_activity WHERE pid = ANY(%s) AND wait_event_type = 'Lock'",
            (list(pids),),
        ).fetchall()
    return {f[0] for f in filas}
