# ============================================================
# GAPTO MOBILE 2027
# Fichero: lecturas_pag.py
# Ruta: backend/app/patrimonio/lecturas_pag.py
# Descripcion: T2-F06 PAG · lecturas nuevas de F06 (N1 sin DDL; solo lectura, sin locks, gapto_runtime con RLS):
#   - invertido_mes(fecha) — «Invertido en viviendas este mes» (Q-VP-02; decision literal del paquete n.º 3: «es mi
#     parte de las reformas y mejoras del mes, sin compras»). Universo: hechos ACTIVOS del owner de tipo
#     MEJORA_PATRIMONIAL, moneda EUR y fecha_hecho en el mes natural de la fecha recibida. Suma la atribucion del
#     actor propio de sus efectos VALOR_ACTIVO con causa TRANSFORMACION_CAPITALIZABLE (C-MEJ-01 y C-MEJ-02 por la
#     fecha del hecho). No cuenta compras (C-COMPRA-01/03: ADQUISICION), gastos de la compra ni amortizacion de
#     hipoteca. Los hechos sin reparto (NO_LO_SE) no suman y se cuentan aparte (`sin_reparto`). Nunca entra en el
#     Resultado del mes (que solo suma GASTO e INGRESO): es una fila aparte de Inicio.
#   - movimientos_cuenta(cuenta_id, pagina, limite) — L-MOV-CUENTA (L-09; Q-VP-01): movimientos ACTIVOS de una
#     cuenta del owner en orden cronologico (fecha, alta), con los hechos a los que esta conciliado cada uno. Sin
#     estado de punteo ni acciones de conciliacion (el punteo es de un bloque propio de tesoreria, fuera de T2).
#     Una cuenta que no es del owner (RLS) es None -> 404, sin eco de su id.
# Version: 0.1.0 (F06 T2-F06 PAG N1)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import json
import uuid
from typing import Any

from app.comun.fecha_funcional import limites_mes
from app.core.unidad_trabajo import SesionMotor

_CENT = decimal.Decimal("0.01")
LIMITE_MAXIMO = 200

_MEJORAS_DEL_MES = (
    "SELECT e.id, e.estado_atribucion, "
    "(SELECT COALESCE(sum(a.importe_atribuido), 0) FROM gapto.efecto_atribuciones a "
    " WHERE a.efecto_id = e.id AND a.actor_id = %(actor)s) "
    "FROM gapto.hecho_efectos e JOIN gapto.hechos_financieros h ON h.id = e.hecho_id "
    "JOIN gapto.tipos_hecho th ON th.id = h.tipo_hecho_id "
    "WHERE h.estado = 'ACTIVO' AND h.moneda = 'EUR' AND th.codigo = 'MEJORA_PATRIMONIAL' "
    "AND h.fecha_hecho >= %(inicio)s AND h.fecha_hecho < %(fin)s "
    "AND e.tipo_efecto = 'VALOR_ACTIVO' AND e.causa_valor_activo = 'TRANSFORMACION_CAPITALIZABLE'"
)


def _texto(valor: decimal.Decimal) -> str:
    return str(decimal.Decimal(valor).quantize(_CENT))


def invertido_mes(sesion: SesionMotor, fecha: dt.date) -> dict[str, Any]:
    inicio, fin = limites_mes(fecha)
    actor = sesion.uno("SELECT id FROM gapto.actores_financieros WHERE tercero_id IS NULL")
    actor_self = actor[0] if actor else None
    total, sin_reparto = decimal.Decimal(0), 0
    with sesion.conexion.cursor() as cur:
        cur.execute(_MEJORAS_DEL_MES, {"actor": actor_self, "inicio": inicio, "fin": fin})
        for _efecto, estado, propio in cur.fetchall():
            if estado == "NO_DISPONIBLE":
                sin_reparto += 1
                continue
            total += decimal.Decimal(propio)
    return {"mes": f"{inicio.year:04d}-{inicio.month:02d}", "moneda": "EUR", "invertido": _texto(total),
            "sin_reparto": sin_reparto}


_MOVIMIENTOS = (
    "SELECT m.id, m.fecha_movimiento, m.importe::text, m.descripcion, m.clase_movimiento, "
    "(SELECT coalesce(json_agg(json_build_object('hecho_id', h.id, 'concepto', h.concepto, 'tipo_hecho', th.codigo, "
    "  'importe_asignado', x.importe_asignado::text) ORDER BY h.id), '[]') "
    "  FROM gapto.hecho_movimientos_tesoreria x JOIN gapto.hechos_financieros h ON h.id = x.hecho_id "
    "  JOIN gapto.tipos_hecho th ON th.id = h.tipo_hecho_id WHERE x.movimiento_tesoreria_id = m.id) "
    "FROM gapto.movimientos_tesoreria m WHERE m.cuenta_id = %(c)s AND m.estado = 'ACTIVO' "
    "ORDER BY m.fecha_movimiento, m.confirmado_at, m.id LIMIT %(limite)s OFFSET %(desde)s"
)


def movimientos_cuenta(sesion: SesionMotor, cuenta_id: uuid.UUID, *, pagina: int = 0,
                       limite: int = 50) -> dict[str, Any] | None:
    cuenta = sesion.uno("SELECT nombre, moneda FROM gapto.cuentas WHERE id = %s", (cuenta_id,))
    if cuenta is None:
        return None
    limite = max(1, min(int(limite), LIMITE_MAXIMO))
    pagina = max(0, int(pagina))
    with sesion.conexion.cursor() as cur:
        cur.execute(_MOVIMIENTOS, {"c": cuenta_id, "limite": limite + 1, "desde": pagina * limite})
        filas = cur.fetchall()
    hay_mas = len(filas) > limite
    movimientos = []
    for mid, fecha, importe, descripcion, clase, hechos in filas[:limite]:
        hechos = hechos if isinstance(hechos, list) else json.loads(hechos)
        movimientos.append({
            "movimiento_id": mid, "fecha": fecha, "importe": _texto(decimal.Decimal(importe)),
            "descripcion": descripcion, "clase": clase,
            "hechos": [{**x, "importe_asignado": _texto(decimal.Decimal(x["importe_asignado"]))} for x in hechos]})
    return {"cuenta_id": cuenta_id, "nombre": cuenta[0], "moneda": cuenta[1], "pagina": pagina, "limite": limite,
            "hay_mas": hay_mas, "movimientos": movimientos}
