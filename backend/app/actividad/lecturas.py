# ============================================================
# GAPTO MOBILE 2027
# Fichero: lecturas.py
# Ruta: backend/app/actividad/lecturas.py
# Descripcion: Lectura de la Actividad v0 (F05 §49.4 A7, §49.5 R8/R10-R12;
#   AJ-F0505-05; casos 12-18, 22-24, 33 de §49.9). Solo lectura, sin locks,
#   gapto_runtime con RLS del tenant. Nunca usa `v_hechos_resumen` como fuente
#   (no trae tercero, categoria, contexto ni «tu parte»). Frontera con F08: no
#   calcula metricas, tendencias, presupuestos ni previsiones; sin posiciones.
#
#   listar(filtros, cursor, limite):
#   - Universo: hechos ACTIVOS del owner. Periodo opcional [desde, hasta)
#     (sin periodo = todo el historial: busqueda y «Ver sus registros»).
#   - Filtros: tipo (GASTO / INGRESO / TRANSFERENCIA, varios), categoria (con
#     subcategorias por defecto), cuenta (algun movimiento del hecho), tercero,
#     contexto (entidad del hecho).
#   - Busqueda `q` (ILIKE, sin indice: R10): nombre o nombre_legal del
#     tercero, nombre de la categoria, nombre del contexto o entidad, nota o
#     concepto historico (columna `concepto`); `importe`: igualdad numerica
#     con importe_total. Cada fila dice por que coincide (`coincide_en`). La
#     nota nunca es la unica via (F05-R-CONCEPTO-02).
#   - Orden y paginacion keyset (fecha_hecho DESC, id ASC) con cursor opaco;
#     `total` = recuento con los mismos filtros (sin cursor).
#   - UN HECHO = UNA FILA: primero se pagina por id; despues cada fila se
#     compone con lecturas por hecho (efectos, terceros, entidades, cuentas)
#     agregadas en Python, de modo que ningun join multiplica filas.
#   Fila: id, fecha_hecho (sin hora: fecha_hecho es date), tipo, nota
#   (columna `concepto`, M5-08), tercero, categoria (con ruta; `varias` si los
#   efectos GASTO/INGRESO tienen mas de una categoria distinta, PA-4),
#   contexto, cuentas (rol PAGO / COBRO / ORIGEN / DESTINO), importe_total,
#   estado_reparto = el peor de los efectos GASTO/INGRESO (NO_DISPONIBLE >
#   PARCIAL > COMPLETA; null en una transferencia), tu_parte (COMPLETA: suma
#   atribuida al actor propio; PARCIAL: la parte propia atribuida y
#   `pendiente`; NO_DISPONIBLE: null, nunca inventada, R12) y
#   maestros_desactivados (CATEGORIA, TERCERO, CONTEXTO).
#   detalle(hecho_id): los mismos campos + presupuestable + magnitudes.
#   El titulo lo calcula el cliente (`tituloRegistro`, una sola implementacion).
# Version: 0.1.0 (F05-05 K2 §1.5)
# ============================================================

from __future__ import annotations

import base64
import binascii
import datetime as dt
import decimal
import uuid
from dataclasses import dataclass
from typing import Any

from app.comun.rutas_categoria import catalogo, ruta_texto
from app.core.unidad_trabajo import SesionMotor

LIMITE_POR_DEFECTO = 50
LIMITE_MAXIMO = 100
TIPOS = ("GASTO", "INGRESO", "TRANSFERENCIA")
_CENT = decimal.Decimal("0.01")
_PEOR = {"COMPLETA": 0, "PARCIAL": 1, "NO_DISPONIBLE": 2}


class CursorInvalido(ValueError):
    pass


@dataclass(frozen=True)
class Filtros:
    desde: dt.date | None = None
    hasta: dt.date | None = None
    tipos: tuple[str, ...] = ()
    categoria: uuid.UUID | None = None
    incluir_subcategorias: bool = True
    cuenta: uuid.UUID | None = None
    tercero: uuid.UUID | None = None
    contexto: uuid.UUID | None = None
    q: str | None = None
    importe: decimal.Decimal | None = None


def codificar_cursor(fecha: dt.date, hecho_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{fecha.isoformat()}|{hecho_id}".encode()).decode().rstrip("=")


def decodificar_cursor(cursor: str) -> tuple[dt.date, uuid.UUID]:
    try:
        texto = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        fecha, hid = texto.split("|")
        return dt.date.fromisoformat(fecha), uuid.UUID(hid)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise CursorInvalido(str(exc)) from exc


def _patron(texto: str) -> str:
    return "%" + texto.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_") + "%"


def _descendientes(nodos: dict[uuid.UUID, dict[str, Any]], raiz: uuid.UUID) -> list[uuid.UUID]:
    hijos: dict[uuid.UUID, list[uuid.UUID]] = {}
    for n in nodos.values():
        if n["parent_id"]:
            hijos.setdefault(n["parent_id"], []).append(n["id"])
    salida, pila, vistos = [], [raiz], set()
    while pila:
        actual = pila.pop()
        if actual in vistos:
            continue
        vistos.add(actual)
        salida.append(actual)
        pila.extend(hijos.get(actual, []))
    return salida


_COINCIDE_TERCERO = (
    "EXISTS (SELECT 1 FROM gapto.hecho_terceros ht JOIN gapto.terceros t ON t.id = ht.tercero_id "
    "WHERE ht.hecho_id = h.id AND (t.nombre ILIKE %(p)s OR t.nombre_legal ILIKE %(p)s))"
)
_COINCIDE_CATEGORIA = (
    "EXISTS (SELECT 1 FROM gapto.hecho_efectos e JOIN gapto.categorias_financieras c ON c.id = e.categoria_id "
    "WHERE e.hecho_id = h.id AND c.nombre ILIKE %(p)s)"
)
_COINCIDE_CONTEXTO = (
    "EXISTS (SELECT 1 FROM gapto.hecho_entidades he JOIN gapto.entidades en ON en.id = he.entidad_id "
    "WHERE he.hecho_id = h.id AND en.nombre ILIKE %(p)s)"
)
_COINCIDE_NOTA = "(h.concepto ILIKE %(p)s)"
_COINCIDE_IMPORTE = "(h.importe_total = %(importe)s)"


def _condiciones(sesion: SesionMotor, f: Filtros) -> tuple[list[str], dict[str, Any]]:
    cond = ["h.estado = 'ACTIVO'"]
    params: dict[str, Any] = {}
    if f.desde is not None:
        cond.append("h.fecha_hecho >= %(desde)s")
        params["desde"] = f.desde
    if f.hasta is not None:
        cond.append("h.fecha_hecho < %(hasta)s")
        params["hasta"] = f.hasta
    if f.tipos:
        cond.append("th.codigo = ANY(%(tipos)s)")
        params["tipos"] = list(f.tipos)
    if f.categoria is not None:
        ids = _descendientes(catalogo(sesion), f.categoria) if f.incluir_subcategorias else [f.categoria]
        cond.append("EXISTS (SELECT 1 FROM gapto.hecho_efectos e WHERE e.hecho_id = h.id "
                    "AND e.categoria_id = ANY(%(categorias)s))")
        params["categorias"] = ids
    if f.cuenta is not None:
        cond.append("EXISTS (SELECT 1 FROM gapto.hecho_movimientos_tesoreria hm "
                    "JOIN gapto.movimientos_tesoreria m ON m.id = hm.movimiento_tesoreria_id "
                    "WHERE hm.hecho_id = h.id AND m.cuenta_id = %(cuenta)s)")
        params["cuenta"] = f.cuenta
    if f.tercero is not None:
        cond.append("EXISTS (SELECT 1 FROM gapto.hecho_terceros ht WHERE ht.hecho_id = h.id "
                    "AND ht.tercero_id = %(tercero)s)")
        params["tercero"] = f.tercero
    if f.contexto is not None:
        cond.append("EXISTS (SELECT 1 FROM gapto.hecho_entidades he WHERE he.hecho_id = h.id "
                    "AND he.entidad_id = %(contexto)s)")
        params["contexto"] = f.contexto
    busqueda = []
    if f.q:
        params["p"] = _patron(f.q)
        busqueda += [_COINCIDE_TERCERO, _COINCIDE_CATEGORIA, _COINCIDE_CONTEXTO, _COINCIDE_NOTA]
    if f.importe is not None:
        params["importe"] = f.importe
        busqueda.append(_COINCIDE_IMPORTE)
    if busqueda:
        cond.append("(" + " OR ".join(busqueda) + ")")
    return cond, params


_FROM = "FROM gapto.hechos_financieros h JOIN gapto.tipos_hecho th ON th.id = h.tipo_hecho_id "


def listar(sesion: SesionMotor, f: Filtros, cursor: str | None, limite: int) -> dict[str, Any]:
    limite = max(1, min(limite, LIMITE_MAXIMO))
    cond, params = _condiciones(sesion, f)
    total = sesion.uno("SELECT count(*) " + _FROM + "WHERE " + " AND ".join(cond), params)[0]
    pagina = list(cond)
    if cursor:
        fecha_c, id_c = decodificar_cursor(cursor)
        pagina.append("(h.fecha_hecho < %(c_fecha)s OR (h.fecha_hecho = %(c_fecha)s AND h.id > %(c_id)s))")
        params.update(c_fecha=fecha_c, c_id=id_c)
    coincide = []
    if f.q:
        coincide += [f"{_COINCIDE_TERCERO} AS m_ter", f"{_COINCIDE_CATEGORIA} AS m_cat",
                     f"{_COINCIDE_CONTEXTO} AS m_ctx", f"{_COINCIDE_NOTA} AS m_nota"]
    if f.importe is not None:
        coincide.append(f"{_COINCIDE_IMPORTE} AS m_imp")
    columnas = ", ".join(["h.id", "h.fecha_hecho"] + coincide)
    params["limite"] = limite + 1
    with sesion.conexion.cursor() as cur:
        cur.execute(f"SELECT {columnas} {_FROM}WHERE {' AND '.join(pagina)} "
                    "ORDER BY h.fecha_hecho DESC, h.id ASC LIMIT %(limite)s", params)
        filas = cur.fetchall()
    hay_mas = len(filas) > limite
    filas = filas[:limite]
    motivos: dict[uuid.UUID, list[str]] = {}
    nombres = (["TERCERO", "CATEGORIA", "CONTEXTO", "NOTA"] if f.q else []) + (["IMPORTE"] if f.importe is not None else [])
    for fila in filas:
        motivos[fila[0]] = [m for m, v in zip(nombres, fila[2:]) if v]
    ids = [fila[0] for fila in filas]
    compuestas = _componer(sesion, ids)
    items = []
    for hid in ids:
        item = compuestas[hid]
        if nombres:
            item["coincide_en"] = motivos[hid]
        items.append(item)
    siguiente = codificar_cursor(filas[-1][1], filas[-1][0]) if hay_mas and filas else None
    return {"filas": items, "siguiente": siguiente, "total": int(total)}


def detalle(sesion: SesionMotor, hecho_id: uuid.UUID) -> dict[str, Any] | None:
    existe = sesion.uno("SELECT presupuestable FROM gapto.hechos_financieros WHERE id = %s AND estado = 'ACTIVO'",
                        (hecho_id,))
    if existe is None:
        return None
    item = _componer(sesion, [hecho_id])[hecho_id]
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT m.id, m.nombre, hm.valor, hm.unidad FROM gapto.hecho_magnitudes hm "
            "JOIN gapto.magnitudes m ON m.id = hm.magnitud_id WHERE hm.hecho_id = %s ORDER BY m.nombre, m.id",
            (hecho_id,))
        item["magnitudes"] = [{"magnitud_id": r[0], "nombre": r[1], "valor": str(r[2]), "unidad": r[3]}
                              for r in cur.fetchall()]
    item["presupuestable"] = existe[0]
    return item


def _dinero(valor) -> str | None:
    return None if valor is None else str(decimal.Decimal(valor).quantize(_CENT))


def _componer(sesion: SesionMotor, ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
    if not ids:
        return {}
    nodos = catalogo(sesion)
    with sesion.conexion.cursor() as cur:
        cur.execute("SELECT h.id, h.fecha_hecho, th.codigo, h.concepto, h.importe_total, h.moneda "
                    + _FROM + "WHERE h.id = ANY(%s)", (ids,))
        base = {r[0]: r for r in cur.fetchall()}
        actor = sesion.uno("SELECT id FROM gapto.actores_financieros WHERE tercero_id IS NULL")
        actor_self = actor[0] if actor else None
        cur.execute(
            "SELECT e.hecho_id, e.id, e.tipo_efecto, e.importe_delta, e.estado_atribucion, e.categoria_id, "
            "(SELECT COALESCE(sum(a.importe_atribuido), 0) FROM gapto.efecto_atribuciones a WHERE a.efecto_id = e.id), "
            "(SELECT COALESCE(sum(a.importe_atribuido), 0) FROM gapto.efecto_atribuciones a "
            " WHERE a.efecto_id = e.id AND a.actor_id = %s) "
            "FROM gapto.hecho_efectos e WHERE e.hecho_id = ANY(%s) AND e.tipo_efecto IN ('GASTO', 'INGRESO') "
            "ORDER BY e.hecho_id, e.id", (actor_self, ids))
        efectos: dict[uuid.UUID, list[tuple]] = {}
        for r in cur.fetchall():
            efectos.setdefault(r[0], []).append(r)
        cur.execute(
            "SELECT ht.hecho_id, t.id, t.nombre, t.enabled FROM gapto.hecho_terceros ht "
            "JOIN gapto.terceros t ON t.id = ht.tercero_id WHERE ht.hecho_id = ANY(%s) "
            "ORDER BY ht.hecho_id, ht.principal DESC, t.id", (ids,))
        terceros: dict[uuid.UUID, dict] = {}
        for r in cur.fetchall():
            terceros.setdefault(r[0], {"id": r[1], "nombre": r[2], "enabled": r[3]})
        cur.execute(
            "SELECT he.hecho_id, en.id, en.nombre, en.enabled FROM gapto.hecho_entidades he "
            "JOIN gapto.entidades en ON en.id = he.entidad_id "
            "WHERE he.hecho_id = ANY(%s) AND en.tipo_entidad = 'CONTEXTO' "
            "ORDER BY he.hecho_id, he.principal DESC, en.id", (ids,))
        contextos: dict[uuid.UUID, dict] = {}
        for r in cur.fetchall():
            contextos.setdefault(r[0], {"id": r[1], "nombre": r[2], "enabled": r[3]})
        cur.execute(
            "SELECT hm.hecho_id, c.id, c.nombre, c.enabled, m.importe FROM gapto.hecho_movimientos_tesoreria hm "
            "JOIN gapto.movimientos_tesoreria m ON m.id = hm.movimiento_tesoreria_id "
            "JOIN gapto.cuentas c ON c.id = m.cuenta_id WHERE hm.hecho_id = ANY(%s) "
            "ORDER BY hm.hecho_id, m.importe, c.id", (ids,))
        cuentas: dict[uuid.UUID, list[dict]] = {}
        for r in cur.fetchall():
            cuentas.setdefault(r[0], []).append({"cuenta_id": r[1], "nombre": r[2], "enabled": r[3],
                                                 "importe": decimal.Decimal(r[4])})
    salida = {}
    for hid in ids:
        _, fecha, tipo, concepto, importe_total, moneda = base[hid]
        efs = efectos.get(hid, [])
        categorias = sorted({e[5] for e in efs if e[5] is not None}, key=str)
        categoria = None
        if len(categorias) == 1:
            n = nodos[categorias[0]]
            categoria = {"id": n["id"], "nombre": n["nombre"], "ruta": ruta_texto(n), "enabled": bool(n["enabled"])}
        estado, tu_parte, pendiente = None, None, None
        if efs:
            estado = max((e[4] for e in efs), key=lambda s: _PEOR[s])
            if estado == "COMPLETA":
                tu_parte = sum((decimal.Decimal(e[7]) for e in efs), decimal.Decimal(0))
            elif estado == "PARCIAL":
                tu_parte = sum((decimal.Decimal(e[7]) for e in efs), decimal.Decimal(0))
                pendiente = sum((decimal.Decimal(e[3]) - decimal.Decimal(e[6]) for e in efs if e[4] == "PARCIAL"),
                                decimal.Decimal(0))
        roles = []
        for c in cuentas.get(hid, []):
            if tipo == "TRANSFERENCIA":
                rol = "ORIGEN" if c["importe"] < 0 else "DESTINO"
            else:
                rol = "PAGO" if c["importe"] < 0 else "COBRO"
            roles.append({"cuenta_id": c["cuenta_id"], "nombre": c["nombre"], "rol": rol, "enabled": c["enabled"]})
        ter, ctx = terceros.get(hid), contextos.get(hid)
        desactivados = [nombre for nombre, obj in (("CATEGORIA", categoria), ("TERCERO", ter), ("CONTEXTO", ctx))
                        if obj is not None and not obj["enabled"]]
        salida[hid] = {
            "id": hid, "fecha_hecho": fecha, "tipo": tipo, "nota": concepto, "moneda": moneda,
            "importe_total": _dinero(importe_total), "tercero": ter, "categoria": categoria,
            "varias": len(categorias) > 1, "contexto": ctx, "cuentas": roles, "estado_reparto": estado,
            "tu_parte": _dinero(tu_parte), "pendiente": _dinero(pendiente), "maestros_desactivados": desactivados,
        }
    return salida
