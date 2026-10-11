# ============================================================
# GAPTO MOBILE 2027
# Fichero: lecturas.py
# Ruta: backend/app/senales/lecturas.py
# Descripcion: Senales de F05-05 (F05 §49.4 A1/A2/A4/A6, §49.5 R1-R8;
#   PA-2 resuelto con el backtest K1-PRE). Lecturas PURAS: sin escritura,
#   sin locks, sin persistir puntuaciones ni descartes (R5); gapto_runtime
#   con RLS del tenant (R8). Ninguna senal entra en un resolver de propuesta
#   (R1, contrato I13 v2): la lista es una SUGERENCIA que el usuario toca.
#
#   categorias_candidatas(tipo, tercero_id | None, fecha) -> hasta 3:
#     1. con tercero: afinidades explicitas de `tercero_afinidades`
#        (motivo AFINIDAD), ordenadas por su uso con el tercero;
#     2. con tercero: frecuencia de la categoria en los hechos del tercero
#        (motivo FRECUENTE_TERCERO);
#     3. para completar (o sin tercero): frecuencia en los hechos del tipo
#        (motivo FRECUENTE_TIPO; el PRIMERO de este bloque lleva RECIENTE si
#        su ultimo uso cae en los ultimos 7 dias, R4).
#     Frecuencia = numero de HECHOS ACTIVOS del owner con un efecto del tipo
#     (GASTO / INGRESO) y esa categoria, en la ventana (f - 365, f] de la
#     fecha funcional recibida (R7: nunca current_date). Desempate: recencia
#     (ultimo uso, descendente) y despues (nombre normalizado C06, id) (R6).
#     Solo categorias HABILITADAS y elegibles por C02 para el tipo (R3); una
#     afinidad hacia una categoria deshabilitada o incompatible no se sugiere.
#   terceros_recientes(tipo, fecha) -> hasta 5 terceros habilitados con
#     hechos del tipo en la ventana: primero los usados en los ultimos 7 dias
#     (motivo RECIENTE, por recencia), despues por frecuencia (motivo
#     FRECUENTE_TIPO); desempate (nombre normalizado, id).
#   historial_tercero(tipo, tercero_id, fecha) -> uso por categoria con el
#     tercero y total de hechos (C1 «N de tus M gastos»).
#   El texto del motivo lo pone el cliente (vocabulario cerrado de R4).
# Version: 0.1.0 (F05-05 K2 §1.2)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from app.api.elegibilidad_categoria import ambito_compatible
from app.categorias.normalizacion import normalizar
from app.comun.fecha_funcional import ventana
from app.comun.rutas_categoria import catalogo, clave_orden, ruta_texto
from app.core.unidad_trabajo import SesionMotor

TIPOS = ("GASTO", "INGRESO")
VENTANA_DIAS = 365
DIAS_RECIENTE = 7
LIMITE_CATEGORIAS = 3
LIMITE_TERCEROS = 5

MOTIVO_AFINIDAD = "AFINIDAD"
MOTIVO_FRECUENTE_TERCERO = "FRECUENTE_TERCERO"
MOTIVO_FRECUENTE_TIPO = "FRECUENTE_TIPO"
MOTIVO_RECIENTE = "RECIENTE"

_USO_DEL_TIPO = (
    "SELECT e.categoria_id, count(DISTINCT h.id), max(h.fecha_hecho) "
    "FROM gapto.hecho_efectos e JOIN gapto.hechos_financieros h ON h.id = e.hecho_id "
    "WHERE h.estado = 'ACTIVO' AND e.tipo_efecto = %s AND e.categoria_id IS NOT NULL "
    "AND h.fecha_hecho > %s AND h.fecha_hecho <= %s "
    "GROUP BY e.categoria_id"
)
_USO_CON_TERCERO = (
    "SELECT e.categoria_id, count(DISTINCT h.id), max(h.fecha_hecho) "
    "FROM gapto.hecho_efectos e JOIN gapto.hechos_financieros h ON h.id = e.hecho_id "
    "WHERE h.estado = 'ACTIVO' AND e.tipo_efecto = %s AND e.categoria_id IS NOT NULL "
    "AND h.fecha_hecho > %s AND h.fecha_hecho <= %s "
    "AND EXISTS (SELECT 1 FROM gapto.hecho_terceros ht WHERE ht.hecho_id = h.id AND ht.tercero_id = %s) "
    "GROUP BY e.categoria_id"
)
_TOTAL_CON_TERCERO = (
    "SELECT count(DISTINCT h.id) FROM gapto.hechos_financieros h "
    "JOIN gapto.hecho_efectos e ON e.hecho_id = h.id "
    "WHERE h.estado = 'ACTIVO' AND e.tipo_efecto = %s AND h.fecha_hecho > %s AND h.fecha_hecho <= %s "
    "AND EXISTS (SELECT 1 FROM gapto.hecho_terceros ht WHERE ht.hecho_id = h.id AND ht.tercero_id = %s)"
)
_AFINIDADES = "SELECT categoria_id FROM gapto.tercero_afinidades WHERE tercero_id = %s"
_TERCEROS_DEL_TIPO = (
    "SELECT t.id, t.nombre, t.naturaleza, count(DISTINCT h.id), max(h.fecha_hecho) "
    "FROM gapto.hecho_terceros ht JOIN gapto.hechos_financieros h ON h.id = ht.hecho_id "
    "JOIN gapto.tipos_hecho th ON th.id = h.tipo_hecho_id JOIN gapto.terceros t ON t.id = ht.tercero_id "
    "WHERE h.estado = 'ACTIVO' AND th.codigo = %s AND t.enabled "
    "AND h.fecha_hecho > %s AND h.fecha_hecho <= %s "
    "GROUP BY t.id, t.nombre, t.naturaleza"
)


def tercero_visible(sesion: SesionMotor, tercero_id: uuid.UUID) -> bool:
    return sesion.uno("SELECT 1 FROM gapto.terceros WHERE id = %s", (tercero_id,)) is not None


def _uso(sesion: SesionMotor, tipo: str, fecha: dt.date,
         tercero_id: uuid.UUID | None) -> dict[uuid.UUID, tuple[int, dt.date]]:
    desde, hasta = ventana(fecha, VENTANA_DIAS)
    with sesion.conexion.cursor() as cur:
        if tercero_id is None:
            cur.execute(_USO_DEL_TIPO, (tipo, desde, hasta))
        else:
            cur.execute(_USO_CON_TERCERO, (tipo, desde, hasta, tercero_id))
        return {f[0]: (int(f[1]), f[2]) for f in cur.fetchall()}


def _orden_uso(uso: dict[uuid.UUID, tuple[int, dt.date]], nodos: dict[uuid.UUID, dict[str, Any]]):
    """(frecuencia desc, recencia desc, nombre normalizado, id)."""
    def clave(cid: uuid.UUID):
        n, ultima = uso.get(cid, (0, dt.date.min))
        return (-n, -ultima.toordinal(), *clave_orden(nodos[cid]))
    return clave


def _candidata(nodo: dict[str, Any], motivo: str, uso: tuple[int, dt.date] | None) -> dict[str, Any]:
    n, ultima = uso if uso else (0, None)
    return {"categoria_id": nodo["id"], "nombre": nodo["nombre"], "ruta": ruta_texto(nodo),
            "motivo": motivo, "fuente": "AFINIDAD" if motivo == MOTIVO_AFINIDAD else "HISTORIAL",
            "usos": n, "ultimo_uso": ultima}


def categorias_candidatas(sesion: SesionMotor, tipo: str, tercero_id: uuid.UUID | None,
                          fecha: dt.date) -> list[dict[str, Any]]:
    if tipo not in TIPOS:
        raise ValueError(f"tipo no admitido: {tipo}")
    nodos = catalogo(sesion)
    elegibles = {cid for cid, n in nodos.items() if n["enabled"] and ambito_compatible(tipo, n["ambito"])}
    salida: list[dict[str, Any]] = []
    elegidas: set[uuid.UUID] = set()

    if tercero_id is not None:
        uso_ter = _uso(sesion, tipo, fecha, tercero_id)
        with sesion.conexion.cursor() as cur:
            cur.execute(_AFINIDADES, (tercero_id,))
            afinidades = [f[0] for f in cur.fetchall() if f[0] in elegibles]
        for cid in sorted(afinidades, key=_orden_uso(uso_ter, nodos)):
            salida.append(_candidata(nodos[cid], MOTIVO_AFINIDAD, uso_ter.get(cid)))
            elegidas.add(cid)
        for cid in sorted((c for c in uso_ter if c in elegibles and c not in elegidas), key=_orden_uso(uso_ter, nodos)):
            salida.append(_candidata(nodos[cid], MOTIVO_FRECUENTE_TERCERO, uso_ter[cid]))
            elegidas.add(cid)

    if len(salida) < LIMITE_CATEGORIAS:
        uso_tipo = _uso(sesion, tipo, fecha, None)
        primero = True
        for cid in sorted((c for c in uso_tipo if c in elegibles and c not in elegidas), key=_orden_uso(uso_tipo, nodos)):
            n, ultima = uso_tipo[cid]
            reciente = primero and (fecha - ultima).days < DIAS_RECIENTE
            salida.append(_candidata(nodos[cid], MOTIVO_RECIENTE if reciente else MOTIVO_FRECUENTE_TIPO, uso_tipo[cid]))
            elegidas.add(cid)
            primero = False
            if len(salida) >= LIMITE_CATEGORIAS:
                break
    return salida[:LIMITE_CATEGORIAS]


def terceros_recientes(sesion: SesionMotor, tipo: str, fecha: dt.date) -> list[dict[str, Any]]:
    if tipo not in TIPOS:
        raise ValueError(f"tipo no admitido: {tipo}")
    desde, hasta = ventana(fecha, VENTANA_DIAS)
    with sesion.conexion.cursor() as cur:
        cur.execute(_TERCEROS_DEL_TIPO, (tipo, desde, hasta))
        filas = [{"tercero_id": f[0], "nombre": f[1], "naturaleza": f[2], "usos": int(f[3]), "ultimo_uso": f[4]}
                 for f in cur.fetchall()]
    recientes = [x for x in filas if (fecha - x["ultimo_uso"]).days < DIAS_RECIENTE]
    resto = [x for x in filas if (fecha - x["ultimo_uso"]).days >= DIAS_RECIENTE]
    recientes.sort(key=lambda x: (-x["ultimo_uso"].toordinal(), normalizar(x["nombre"]), str(x["tercero_id"])))
    resto.sort(key=lambda x: (-x["usos"], -x["ultimo_uso"].toordinal(), normalizar(x["nombre"]), str(x["tercero_id"])))
    salida = [dict(x, motivo=MOTIVO_RECIENTE) for x in recientes] + [dict(x, motivo=MOTIVO_FRECUENTE_TIPO) for x in resto]
    return salida[:LIMITE_TERCEROS]


def historial_tercero(sesion: SesionMotor, tipo: str, tercero_id: uuid.UUID,
                      fecha: dt.date) -> tuple[list[dict[str, Any]], int]:
    """Uso por categoria (habilitada y elegible) con el tercero en la ventana y
    total de hechos del tipo con ese tercero (C1 «N de tus M gastos»)."""
    nodos = catalogo(sesion)
    uso = _uso(sesion, tipo, fecha, tercero_id)
    elegibles = [c for c in uso if nodos[c]["enabled"] and ambito_compatible(tipo, nodos[c]["ambito"])]
    desde, hasta = ventana(fecha, VENTANA_DIAS)
    total = sesion.uno(_TOTAL_CON_TERCERO, (tipo, desde, hasta, tercero_id))[0]
    filas = [_candidata(nodos[c], MOTIVO_FRECUENTE_TERCERO, uso[c]) for c in sorted(elegibles, key=_orden_uso(uso, nodos))]
    return filas, int(total)
