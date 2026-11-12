# ============================================================
# GAPTO MOBILE 2027
# Fichero: coste.py
# Ruta: backend/app/patrimonio/coste.py
# Descripcion: L-COSTE · coste e inversion de una propiedad (R1 v0.9.5 §II.6; v0.9 §II.6 por remision).
#   Total, «tu parte», conjunto vigente y declaracion salen de UNA sentencia (repositorio.leer_coste).
#   Regla de lectura con `a_fecha` (por defecto, hoy del owner):
#     1 ADQUISICION sin componentes <= a_fecha        -> NO_DISPONIBLE  SIN_COMPONENTES
#     2 sin declaracion                               -> PARCIAL (MEJORAS sin componentes: NO_DISPONIBLE)
#                                                        SIN_DECLARACION
#     3 a_fecha < corte                               -> PARCIAL  LECTURA_ANTERIOR_AL_CORTE
#     4 conjunto(corte) vigente != declarado          -> PARCIAL  DECLARACION_DESACTUALIZADA
#     5 componente con corte < fecha <= a_fecha       -> PARCIAL  COMPONENTE_POSTERIOR_AL_CORTE
#     6 resto                                         -> COMPLETO (MEJORAS con [] : COMPLETO con 0,00)
#   «Tu parte» (HF-13): estado propio; NO_DISPONIBLE si algun componente lo es, PARCIAL si alguno lo es; nunca
#   se completa con la titularidad. «Permanece»: nunca COMPLETO en R1 (bajas no representadas); NO_DISPONIBLE
#   si la adquisicion lo es. Sin desglose por concepto (M-11).
#   Consumidor PROVISIONAL de 0352 (habilitacion.py): con los consumidores no habilitados, la lectura no ve la
#   declaracion (fila 2 siempre), no devuelve corte ni huella y nunca da COMPLETO.
# Version: 0.1.0 (F06 T1-F06 B2 N1)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from app.core.unidad_trabajo import SesionMotor
from app.patrimonio import habilitacion
from app.propiedades import repositorio as repo

CENT = Decimal("0.01")


def _regla(ambito: str, n: int, declarado, corte, igual, posteriores, a_fecha: dt.date) -> tuple[str, str | None]:
    if ambito == "ADQUISICION" and n == 0:
        return "NO_DISPONIBLE", "SIN_COMPONENTES"
    if declarado is not True:
        return ("NO_DISPONIBLE" if n == 0 else "PARCIAL"), "SIN_DECLARACION"
    if a_fecha < corte:
        return "PARCIAL", "LECTURA_ANTERIOR_AL_CORTE"
    if igual is not True:
        return "PARCIAL", "DECLARACION_DESACTUALIZADA"
    if posteriores:
        return "PARCIAL", "COMPONENTE_POSTERIOR_AL_CORTE"
    return "COMPLETO", None


def _tu_parte(n: int, mio: Decimal, estados: list[str]) -> dict[str, Any]:
    if n == 0 or "NO_DISPONIBLE" in estados:
        return {"importe": None, "estado": "NO_DISPONIBLE"}
    return {"importe": str(Decimal(mio).quantize(CENT)), "estado": "PARCIAL" if "PARCIAL" in estados else "COMPLETO"}


def leer(sesion: SesionMotor, propiedad_id: uuid.UUID, a_fecha: dt.date) -> dict[str, Any] | None:
    habilitada = habilitacion.consumidores_0352_habilitados()
    filas = repo.leer_coste(sesion, propiedad_id, a_fecha, habilitada)
    if filas is None:
        return None
    salida: dict[str, Any] = {"a_fecha": a_fecha.isoformat(), "declaracion_habilitada": habilitada}
    for ambito, total, n, mio, estados, declarado, corte, igual, posteriores, huella in filas:
        estado, motivo = _regla(ambito, n, declarado, corte, igual, posteriores, a_fecha)
        salida[ambito] = {"total": str(Decimal(total).quantize(CENT)), "estado": estado, "motivo_estado": motivo,
                          "fecha_corte": corte.isoformat() if (habilitada and corte) else None,
                          "huella_conjunto": huella if habilitada else None,
                          "componentes": n, "tu_parte": _tu_parte(n, mio, list(estados or []))}
    adq, mej = salida["ADQUISICION"], salida["MEJORAS"]
    salida["PERMANECE"] = {
        "total": str((Decimal(adq["total"]) + Decimal(mej["total"])).quantize(CENT)),
        "estado": "NO_DISPONIBLE" if adq["estado"] == "NO_DISPONIBLE" else "PARCIAL",
        "bajas": "NO_REPRESENTADAS",
    }
    return salida
