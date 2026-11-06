# ============================================================
# GAPTO MOBILE 2027
# Fichero: f06_01_b1_helpers.py
# Ruta: tests/api/f06_01_b1_helpers.py
# Descripcion: Helpers de las pruebas de B1 · Propiedad (F06-01, lote 12):
#   entorno con reloj fijo, cuerpos de alta/edicion/titularidad/valoracion
#   y huella SHA-256 del estado (filas completas de TODAS las tablas del
#   schema gapto, leidas como superusuario SOLO para comparar; patron D5 y
#   G9). Un rechazo debe dejar la huella identica.
# Version: 0.1.0 (F06-01 B1, lote 12)
# ============================================================

from __future__ import annotations

import hashlib
import uuid

import psycopg

import f05_05_helpers as x5
import vs01_api_helpers as h

HOY = "2026-10-10"
RELOJ = "2026-10-10T12:00:00"
#: Tablas que B1 nunca escribe (B2/B3 fuera): hechos, efectos, movimientos y atribuciones.
TABLAS_FINANCIERAS = ("hechos_financieros", "hecho_efectos", "hecho_entidades", "hecho_movimientos_tesoreria",
                      "movimientos_tesoreria", "efecto_atribuciones", "hecho_aportaciones_pago",
                      "hecho_participantes")


def entorno():
    """(owner, actor_self, cliente con reloj fijo en HOY)."""
    owner, actor, cli, _, _ = x5.entorno(RELOJ)
    return owner, actor, cli


def tercero(cli, nombre: str, naturaleza: str | None = "PERSONA") -> uuid.UUID:
    return x5.tercero(cli, nombre, naturaleza=naturaleza)


def huellas(tablas: tuple[str, ...] | None = None) -> dict[str, str]:
    with psycopg.connect(h.dsn()) as c:
        todas = [t for (t,) in c.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'gapto' ORDER BY 1")]
        elegidas = [t for t in todas if tablas is None or t in tablas]
        sql = " UNION ALL ".join(
            f"SELECT '{t}', coalesce(md5(string_agg(x::text, '|' ORDER BY x::text)), '') FROM gapto.{t} x"
            for t in elegidas)
        return dict(c.execute(sql).fetchall())


def huella(tablas: tuple[str, ...] | None = None) -> str:
    """SHA-256 del estado completo (o de las tablas indicadas)."""
    return hashlib.sha256(repr(sorted(huellas(tablas).items())).encode()).hexdigest()


def solo_mia(desde: str = "2026-01-01") -> dict:
    return {"modo": "SOLO_MIA", "desde": desde}


def compartida(partes: list[dict], desde: str = "2026-01-01") -> dict:
    return {"modo": "COMPARTIDA", "desde": desde, "partes": partes}


def yo(pct: str) -> dict:
    return {"yo": True, "porcentaje": pct}


def de(tercero_id, pct: str) -> dict:
    return {"tercero_id": str(tercero_id), "porcentaje": pct}


def alta(titularidad: dict | None = None, *, intencion_id=None, nombre: str = "Piso Gran Vía", **extra) -> dict:
    cuerpo = {"intencion_id": str(intencion_id or uuid.uuid4()), "nombre": nombre, "tipo_propiedad": "VIVIENDA",
              "titularidad": titularidad or solo_mia()}
    cuerpo.update(extra)
    return cuerpo


def crear(cli, cuerpo: dict) -> dict:
    r = cli.post("/v1/propiedades", json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()["propiedad"]


def leer(cli, pid) -> dict:
    r = cli.get(f"/v1/propiedades/{pid}", headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()["propiedad"]


def vista_de(prop: dict) -> list[dict]:
    """`titularidad_vista` que mandaria el cliente desde la vista que leyo."""
    return [{"actor_id": p["actor_id"], "porcentaje": p["porcentaje"]} for p in prop["titularidad"]["partes"]]


def cambio(prop: dict, titularidad: dict, *, intencion_id=None, version: int | None = None, **extra) -> dict:
    cuerpo = {"intencion_id": str(intencion_id or uuid.uuid4()),
              "row_version_esperada": prop["row_version"] if version is None else version,
              "titularidad_vista": vista_de(prop), **titularidad}
    cuerpo.update(extra)
    return cuerpo


def valoracion(prop: dict, valor: str = "250000.00", fecha: str = "2026-09-01", metodo: str = "MERCADO", *,
               intencion_id=None, version: int | None = None, **extra) -> dict:
    cuerpo = {"intencion_id": str(intencion_id or uuid.uuid4()),
              "row_version_esperada": prop["row_version"] if version is None else version,
              "valor_total": valor, "fecha_valoracion": fecha, "metodo": metodo}
    cuerpo.update(extra)
    return cuerpo


def post(cli, ruta: str, cuerpo: dict):
    return cli.post(ruta, json=cuerpo, headers=h.AUTH)
