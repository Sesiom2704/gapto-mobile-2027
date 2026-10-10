# ============================================================
# GAPTO MOBILE 2027
# Fichero: f05_02_helpers.py
# Ruta: tests/api/f05_02_helpers.py
# Descripcion: Helpers de los tests de F05-02 B1 (preferencias de registro,
#   F05-D026). Modulo con NOMBRE UNICO importado explicitamente (D-193): no
#   hay conftest en tests/api. Reutiliza vs01_api_helpers y f05_01_helpers
#   para tenant, cuentas, categorias, cliente HTTP y unidad de trabajo. Datos
#   sinteticos creados como gapto_owner con la GUC del tenant (WM 12C.7).
#   Exigen GAPTO_TEST_DATABASE_URL apuntando a una base DESECHABLE con la
#   cadena aplicada (estos tests confirman filas).
#
#   v0.2.0 (F05-03/F05-04 J2 §1.5; F05 §46.5 E3, §46.4 R6; F05-D032 C4;
#   decision de Moises OPCION A2 del STOP 2): se retira la preferencia global
#   sin tipo. `alta`, `editar` e `insertar_sql` toman por DEFECTO el tipo
#   GASTO cuando el test no indica `tipo_hecho_id` (sustitucion canonica de
#   E3: la global sin tipo pasa a «Todos los gastos»). Un test que necesita
#   una fila o un alta SIN tipo lo pide expresamente con tipo_hecho_id=None.
#   `resolver` admite el tercero del contexto (E2). `entidad` crea una entidad
#   PROPIEDAD sintetica (dimension diferida vigente).
#
#   v0.3.0 (F05-03/F05-04 J2 §1.0/§1.1; F05-D032 C1): `cuenta` crea la cuenta
#   con su tipo (PASIVO -> CREDITO) y sus capacidades explicitas (por defecto,
#   las del tipo; `capacidades` las fija, p. ej. una PASIVO sin PAGAR_GASTO).
# Version: 0.3.0
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid

import f05_01_helpers as fh
import vs01_api_helpers as h

BASE = "/v1/preferencias"
FECHA = dt.date(2026, 9, 24)


def tenant():
    """(owner, actor self, cliente HTTP)."""
    owner, actor = h.crear_tenant()
    return owner, actor, h.cliente(owner)


def cuenta(owner: uuid.UUID, actor: uuid.UUID, *, moneda: str = "EUR", enabled: bool = True,
           fecha_cierre: dt.date | None = None, naturaleza: str = "ACTIVO", nombre: str | None = None,
           capacidades: tuple[str, ...] | None = None) -> uuid.UUID:
    tipo = "CORRIENTE" if naturaleza == "ACTIVO" else "CREDITO"
    cid = h.crear_cuenta(owner, [(actor, 100)], moneda=moneda, tipo=tipo, naturaleza=naturaleza,
                         capacidades=capacidades)
    if nombre is not None:
        h.como_owner(owner, "UPDATE gapto.cuentas SET nombre=%s WHERE id=%s", (nombre, cid))
    if not enabled or fecha_cierre is not None:
        h.como_owner(owner, "UPDATE gapto.cuentas SET enabled=false, fecha_cierre=%s WHERE id=%s", (fecha_cierre, cid))
    return cid


def deshabilitar_cuenta(owner: uuid.UUID, cid: uuid.UUID) -> None:
    h.como_owner(owner, "UPDATE gapto.cuentas SET enabled=false WHERE id=%s", (cid,))


def categoria(owner: uuid.UUID, nombre: str, **kw) -> uuid.UUID:
    return fh.crear_categoria(owner, nombre, **kw)


_GASTO: list[uuid.UUID] = []


def tipo_gasto_global() -> uuid.UUID:
    """Id del tipo GASTO (catalogo global, igual para todos los owners)."""
    if not _GASTO:
        import psycopg

        with psycopg.connect(h.dsn()) as c:
            _GASTO.append(c.execute("SELECT id FROM gapto.tipos_hecho WHERE codigo='GASTO'").fetchone()[0])
    return _GASTO[0]


#: Centinela: «el test no indica tipo» -> GASTO por defecto (E3). None explicito = sin tipo.
POR_DEFECTO = object()


def tipo_gasto(owner: uuid.UUID) -> uuid.UUID:
    return h.leer(owner, "SELECT id FROM gapto.tipos_hecho WHERE codigo='GASTO'")[0][0]


def otro_tipo(owner: uuid.UUID) -> uuid.UUID:
    return h.leer(owner, "SELECT id FROM gapto.tipos_hecho WHERE codigo<>'GASTO' ORDER BY codigo LIMIT 1")[0][0]


def insertar_sql(owner: uuid.UUID, *, tipo_hecho_id=POR_DEFECTO, categoria_id=None, tercero_id=None,
                 entidad_id=None, cuenta=None, presupuestable=None, prioridad: int = 100,
                 enabled: bool = True) -> uuid.UUID:
    """Preferencia escrita por SQL DIRECTO (sin el writer): para fijar
    escenarios del resolver y filas que el writer nunca crearia. Sin
    `tipo_hecho_id`, GASTO (E3); tipo_hecho_id=None escribe una fila sin tipo."""
    if tipo_hecho_id is POR_DEFECTO:
        tipo_hecho_id = tipo_gasto_global()
    pid = uuid.uuid4()
    h.como_owner(
        owner,
        "INSERT INTO gapto.preferencias_registro (id, owner_user_id, tipo_hecho_id, categoria_id, tercero_id, "
        "entidad_id, cuenta_default_id, presupuestable_default, prioridad, enabled) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (pid, owner, tipo_hecho_id, categoria_id, tercero_id, entidad_id, cuenta, presupuestable, prioridad, enabled),
    )
    return pid


def entidad(owner: uuid.UUID) -> uuid.UUID:
    """Entidad PROPIEDAD sintetica (dimension diferida entidad_id)."""
    eid = uuid.uuid4()
    c = fh.sesion_owner(owner)
    try:
        c.execute("SET CONSTRAINTS ALL DEFERRED")
        c.execute("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
                  "VALUES (%s, %s, 'PROPIEDAD', 'Vivienda sintetica')", (eid, owner))
        c.execute("INSERT INTO gapto.propiedades (entidad_id, tipo_propiedad) VALUES (%s, 'VIVIENDA')", (eid,))
        c.execute("COMMIT")
    finally:
        c.close()
    return eid


def tercero(owner: uuid.UUID) -> uuid.UUID:
    tid = uuid.uuid4()
    h.como_owner(owner, "INSERT INTO gapto.terceros (id, owner_user_id, nombre) VALUES (%s,%s,'Tercero sintetico')",
                 (tid, owner))
    return tid


def resolver(owner: uuid.UUID, categoria_id: uuid.UUID | None, fecha: dt.date = FECHA, tipo_hecho_id=None,
             tercero_id=None):
    from app.preferencias import resolver as r

    def op(s):
        th = tipo_hecho_id or r.tipo_hecho_registro(s)
        return r.resolver(s, tipo_hecho_id=th, categoria_id=categoria_id, fecha=fecha, tercero_id=tercero_id)

    return fh.en_transaccion(owner, op)


def valor(propuesta: dict, campo: str):
    p = propuesta[campo]
    return None if p is None else p["valor"]


def origen(propuesta: dict, campo: str):
    p = propuesta[campo]
    return None if p is None else (p["origen"]["capa"], p["origen"]["preferencia_id"])


# ------------------------------------------------------------------ HTTP
def _con_tipo(campos: dict) -> dict:
    """Sin `tipo_hecho_id` en el test -> GASTO (E3); None explicito se envia como null."""
    return campos if "tipo_hecho_id" in campos else {"tipo_hecho_id": tipo_gasto_global(), **campos}


def alta(cli, pid: uuid.UUID | None = None, **campos):
    pid = pid or uuid.uuid4()
    campos = _con_tipo(campos)
    cuerpo = {"id": str(pid), **{k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in campos.items()}}
    return pid, cli.post(BASE, json=cuerpo, headers=h.AUTH)


def editar(cli, pid: uuid.UUID, row_version: int, **campos):
    campos = _con_tipo(campos)
    cuerpo = {"row_version": row_version, **{k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in campos.items()}}
    return cli.post(f"{BASE}/{pid}/editar", json=cuerpo, headers=h.AUTH)


def desactivar(cli, pid: uuid.UUID, row_version: int):
    return cli.post(f"{BASE}/{pid}/desactivar", json={"row_version": row_version}, headers=h.AUTH)


def reactivar(cli, pid: uuid.UUID, row_version: int):
    return cli.post(f"{BASE}/{pid}/reactivar", json={"row_version": row_version}, headers=h.AUTH)


def propuesta_http(cli, categoria_id: uuid.UUID | None = None, fecha: dt.date = FECHA):
    q = f"?fecha={fecha.isoformat()}" + ("" if categoria_id is None else f"&categoria_id={categoria_id}")
    return cli.get(f"{BASE}/propuesta{q}", headers=h.AUTH)


def fila(owner: uuid.UUID, pid: uuid.UUID) -> dict | None:
    filas = h.leer(owner, "SELECT tipo_hecho_id, categoria_id, cuenta_default_id, presupuestable_default, prioridad, "
                          "enabled, row_version FROM gapto.preferencias_registro WHERE id=%s", (pid,))
    if not filas:
        return None
    return dict(zip(("tipo_hecho_id", "categoria_id", "cuenta_default_id", "presupuestable_default", "prioridad",
                     "enabled", "row_version"), filas[0]))


def n_preferencias(owner: uuid.UUID) -> int:
    return h.leer(owner, "SELECT count(*) FROM gapto.preferencias_registro")[0][0]


def auditorias(owner: uuid.UUID, pid: uuid.UUID) -> list[tuple]:
    return h.leer(owner, "SELECT accion, motivo FROM gapto.auditoria WHERE tabla='preferencias_registro' "
                         "AND registro_id=%s ORDER BY created_at, id", (pid,))


def retener_advisory(owner: uuid.UUID):
    """Sesion que retiene el advisory (PREFERENCIAS, owner): barrera
    explicita para ordenar escritores (WM 12C.1)."""
    c = fh.sesion_owner(owner)
    c.execute("SELECT pg_advisory_xact_lock(hashtext('gapto:PREFERENCIAS'), hashtext(%s::uuid::text))", (str(owner),))
    return c
