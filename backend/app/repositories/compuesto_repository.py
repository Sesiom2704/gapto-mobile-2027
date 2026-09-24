# ============================================================
# GAPTO MOBILE 2027
# Fichero: compuesto_repository.py
# Ruta: backend/app/repositories/compuesto_repository.py
# Descripcion: F04-D048 R3 (A17). Lecturas de IDENTIDAD del agregado de OP-22.
#
#   Solo lee. Sirve para decidir, ANTES de cualquier validacion dependiente de
#   estado mutable, si una invocacion de OP-22 es un reintento exacto de algo
#   ya confirmado (§13/§14 del mandato R3): se localiza cada fila solicitada
#   por su UUID reservado y se devuelve tal cual esta persistida.
#
#   El nombre de tabla se valida contra un conjunto CERRADO; no existe
#   ninguna escritura en este modulo.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import decimal
import json
import uuid
from typing import Any

from app.core.unidad_trabajo import SesionMotor

#: tabla -> columna identidad
TABLAS_IDENTIDAD: dict[str, str] = {
    "hechos_financieros": "id",
    "hecho_efectos": "id",
    "efecto_atribuciones": "id",
    "hecho_participantes": "id",
    "movimientos_tesoreria": "id",
    "hecho_movimientos_tesoreria": "id",
    "hecho_aportaciones_pago": "id",
    "derechos_obligaciones_financieras": "entidad_id",
    "entidades": "id",
    "hecho_entidades": "id",
    "hecho_relaciones": "id",
    "prevision_hechos": "id",
    "previsiones": "id",
}


def leer(sesion: SesionMotor, tabla: str, registro_id: uuid.UUID) -> dict[str, Any] | None:
    columna = TABLAS_IDENTIDAD.get(tabla)
    if columna is None:
        raise ValueError(f"tabla no soportada en identidad de OP-22: {tabla}")
    fila = sesion.uno(
        f"SELECT row_to_json(t)::text FROM gapto.{tabla} t WHERE t.{columna} = %s::uuid",
        (registro_id,),
    )
    if fila is None:
        return None
    return json.loads(fila[0], parse_float=decimal.Decimal)


def codigo_tipo_hecho(sesion: SesionMotor, tipo_hecho_id: Any) -> str | None:
    fila = sesion.uno(
        "SELECT codigo FROM gapto.tipos_hecho WHERE id = %s::uuid", (tipo_hecho_id,)
    )
    return None if fila is None else fila[0]
