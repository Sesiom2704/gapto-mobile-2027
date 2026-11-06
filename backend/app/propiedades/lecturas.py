# ============================================================
# GAPTO MOBILE 2027
# Fichero: lecturas.py
# Ruta: backend/app/propiedades/lecturas.py
# Descripcion: L-PROP (F06-01 B1; contratos R1 v0.8 Parte I y v0.7 L-PROP).
#   Solo lectura, como gapto_runtime con RLS.
#   - Titularidad vigente HOY (fecha civil del owner) y, aparte, el cambio
#     programado (vigente_desde > hoy). Modo derivado de las filas: ninguna
#     -> DESCONOCIDA; YO al 100 % -> SOLO_MIA; YO y otros -> COMPARTIDA; sin
#     YO -> DE_OTROS.
#   - Valor estimado: ultima MERCADO/TASACION/MANUAL con fecha <= hoy (empate
#     de fecha -> mayor id); una valoracion futura no cuenta. La
#     FISCAL_REFERENCIA va aparte y nunca desplaza al estimado; COMPRA solo
#     informativa; sin fecha = evidencia, no punto temporal.
#   - Cuota segun titularidad: VISTA ESTRUCTURAL etiquetada (PA-08), no una
#     atribucion ni un pagador: valor estimado x porcentaje vigente de YO /
#     100, redondeo determinista ROUND_HALF_UP a centimos (PR1-04).
#   - Importes, porcentajes y superficies como TEXTO exacto (v0.8 §1.2).
# Version: 0.1.0 (F06-01 B1, lote 12)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.core.unidad_trabajo import SesionMotor
from app.propiedades import repositorio as repo

ESTIMADO = ("MERCADO", "TASACION", "MANUAL")
FISCAL = ("FISCAL_REFERENCIA",)
COMPRA = ("COMPRA",)
CENTIMO = Decimal("0.01")
DIEZMILESIMA = Decimal("0.0001")
ETIQUETA_CUOTA = "VISTA_ESTRUCTURAL"


def _importe(valor: Decimal | None) -> str | None:
    return None if valor is None else str(valor.quantize(CENTIMO))


def _valoracion(v: dict[str, Any]) -> dict[str, Any]:
    return {"id": v["id"], "valor_total": _importe(v["valor_total"]), "fecha_valoracion": v["fecha_valoracion"],
            "metodo": v["metodo"], "fuente": v["fuente"], "notas": v["notas"],
            "sin_fecha": v["fecha_valoracion"] is None}


def _ultima(vals: list[dict], metodos: tuple[str, ...], hoy: dt.date) -> dict | None:
    candidatas = [v for v in vals if v["metodo"] in metodos and v["fecha_valoracion"] is not None
                  and v["fecha_valoracion"] <= hoy]
    return max(candidatas, key=lambda v: (v["fecha_valoracion"], str(v["id"])), default=None)


def _titularidad(filas: list[dict[str, Any]]) -> dict[str, Any]:
    if not filas:
        return {"modo": "DESCONOCIDA", "desde": None, "partes": []}
    partes = sorted(({"actor_id": f["actor_id"], "yo": f["tercero_id"] is None, "tercero_id": f["tercero_id"],
                      "nombre": f["nombre"], "porcentaje": str(f["porcentaje"].quantize(DIEZMILESIMA))}
                     for f in filas), key=lambda p: (not p["yo"], p["nombre"] or "", str(p["actor_id"])))
    hay_yo = any(p["yo"] for p in partes)
    modo = ("SOLO_MIA" if len(partes) == 1 else "COMPARTIDA") if hay_yo else "DE_OTROS"
    return {"modo": modo, "desde": max(f["vigente_desde"] for f in filas), "partes": partes}


def _vigentes(filas: list[dict[str, Any]], hoy: dt.date) -> list[dict[str, Any]]:
    return [f for f in filas if f["vigente_desde"] <= hoy and (f["vigente_hasta"] is None or f["vigente_hasta"] >= hoy)]


def _programadas(filas: list[dict[str, Any]], hoy: dt.date) -> list[dict[str, Any]]:
    futuras = [f for f in filas if f["vigente_desde"] > hoy]
    if not futuras:
        return []
    primera = min(f["vigente_desde"] for f in futuras)
    return [f for f in futuras if f["vigente_desde"] == primera]


def cuota(valor: Decimal, porcentaje: Decimal) -> Decimal:
    """Vista estructural: valor x porcentaje / 100, ROUND_HALF_UP a centimos."""
    return (valor * porcentaje / Decimal(100)).quantize(CENTIMO, rounding=ROUND_HALF_UP)


def detalle(sesion: SesionMotor, entidad_id: uuid.UUID, hoy: dt.date) -> dict[str, Any] | None:
    base = repo.leer(sesion, entidad_id)
    if base is None:
        return None
    filas = repo.participaciones(sesion, entidad_id)
    vals = repo.valoraciones(sesion, entidad_id)
    vigentes = _vigentes(filas, hoy)
    programadas = _programadas(filas, hoy)
    estimado = _ultima(vals, ESTIMADO, hoy)
    fiscal = _ultima(vals, FISCAL, hoy)
    compra = max((v for v in vals if v["metodo"] in COMPRA), key=lambda v: (v["fecha_valoracion"] or dt.date.min,
                                                                           str(v["id"])), default=None)
    mia = next((f["porcentaje"] for f in vigentes if f["tercero_id"] is None), None)
    vista = {
        "id": base["id"], "nombre": base["nombre"], "enabled": base["enabled"], "row_version": base["row_version"],
        "tipo_propiedad": base["tipo_propiedad"], "fecha_adquisicion": base["fecha_adquisicion"],
        "superficie_m2": _importe(base["superficie_m2"]),
        "superficie_construida_m2": _importe(base["superficie_construida_m2"]),
        "habitaciones": base["habitaciones"], "banos": base["banos"], "tiene_garaje": base["tiene_garaje"],
        "tiene_trastero": base["tiene_trastero"], "referencia_catastral": base["referencia_catastral"],
        "incluir_en_rentabilidad": base["incluir_en_rentabilidad"], "notas": base["notas"],
        "fecha_consulta": hoy,
        "titularidad": _titularidad(vigentes),
        "cambio_programado": _titularidad(programadas) if programadas else None,
        "valor_estimado": None if estimado is None else _valoracion(estimado),
        "referencia_fiscal": None if fiscal is None else _valoracion(fiscal),
        "valor_compra": None if compra is None else _valoracion(compra),
        "cuota_segun_titularidad": None if estimado is None or mia is None else {
            "importe": _importe(cuota(estimado["valor_total"], mia)),
            "porcentaje": str(mia.quantize(DIEZMILESIMA)), "etiqueta": ETIQUETA_CUOTA},
        "valoraciones": [_valoracion(v) for v in vals],
    }
    return vista


def listar(sesion: SesionMotor, hoy: dt.date) -> list[dict[str, Any]]:
    salida = []
    for base in repo.listar(sesion):
        filas = _vigentes(repo.participaciones(sesion, base["id"]), hoy)
        estimado = _ultima(repo.valoraciones(sesion, base["id"]), ESTIMADO, hoy)
        salida.append({"id": base["id"], "nombre": base["nombre"], "enabled": base["enabled"],
                       "row_version": base["row_version"], "tipo_propiedad": base["tipo_propiedad"],
                       "modo_titularidad": _titularidad(filas)["modo"],
                       "valor_estimado": None if estimado is None else _valoracion(estimado)})
    return salida
