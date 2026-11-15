# ============================================================
# GAPTO MOBILE 2027
# Fichero: coste.py
# Ruta: backend/app/patrimonio/coste.py
# Descripcion: L-COSTE · coste e inversion de una propiedad (R1 v0.9.5 §II.6; v0.9 §II.6 por remision).
#   Total, «tu parte», conjunto vigente y declaracion salen de UNA sentencia (repositorio.leer_coste, S1).
#   A3-0352 · L2 (contrato A3-0352 v1.1 §4.3): S0 = repo.leer (row_version v0, fecha_adquisicion f0), S1 =
#   leer_coste, S2 = repo.leer (v2). Muestra ESTABLE si v0 = v2 (todo escritor de la fecha o de la terna sube
#   row_version en su misma transaccion: O-A3-R15-INV); si no, se descarta ENTERA y se repite, hasta INTENTOS_L2.
#   Se calcula siempre con la ULTIMA muestra. Agotamiento: ADQUISICION nunca COMPLETO (PARCIAL LECTURA_NO_ESTABLE)
#   y se registra en el log. Sin locks ni caches. READ COMMITTED: cada sentencia con su instantanea.
#   Regla de lectura con `a_fecha` (por defecto, hoy del owner):
#     1 ADQUISICION sin componentes <= a_fecha        -> NO_DISPONIBLE  SIN_COMPONENTES
#     2 sin declaracion                               -> PARCIAL (MEJORAS sin componentes: NO_DISPONIBLE)
#                                                        SIN_DECLARACION
#     2 bis ADQUISICION declarada y fecha_adquisicion NULL en la muestra estable (solo habilitada; R15-a)
#                                                     -> PARCIAL  SIN_FECHA_DE_ADQUISICION (corte y huella se
#                                                        devuelven; reponer la fecha reevalua las filas 3-6)
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
# Version: 0.2.0 (F06 T2-F06 A3-0352 (L-05)): fila 2 bis (SIN_FECHA_DE_ADQUISICION) y lectura L2 con reintento
#   acotado y agotamiento conservador (LECTURA_NO_ESTABLE).
# ============================================================

from __future__ import annotations

import datetime as dt
import logging
import uuid
from decimal import Decimal
from typing import Any

from app.core.unidad_trabajo import SesionMotor
from app.patrimonio import habilitacion
from app.propiedades import repositorio as repo

CENT = Decimal("0.01")
INTENTOS_L2 = 3
_LOG = logging.getLogger("gapto.patrimonio.coste")


def _regla(ambito: str, n: int, declarado, corte, igual, posteriores, a_fecha: dt.date,
           sin_fecha: bool = False) -> tuple[str, str | None]:
    if ambito == "ADQUISICION" and n == 0:
        return "NO_DISPONIBLE", "SIN_COMPONENTES"
    if declarado is not True:
        return ("NO_DISPONIBLE" if n == 0 else "PARCIAL"), "SIN_DECLARACION"
    if sin_fecha:                                                               # fila 2 bis (R15-a)
        return "PARCIAL", "SIN_FECHA_DE_ADQUISICION"
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


def _muestra(sesion: SesionMotor, propiedad_id: uuid.UUID, a_fecha: dt.date, habilitada: bool):
    """L2: (f0, filas de S1, estable) o None si la propiedad no existe."""
    antes = repo.leer(sesion, propiedad_id)                                         # S0
    filas = repo.leer_coste(sesion, propiedad_id, a_fecha, habilitada)              # S1
    despues = repo.leer(sesion, propiedad_id)                                       # S2
    if antes is None or filas is None or despues is None:
        return None
    return antes["fecha_adquisicion"], filas, antes["row_version"] == despues["row_version"]


def leer(sesion: SesionMotor, propiedad_id: uuid.UUID, a_fecha: dt.date) -> dict[str, Any] | None:
    habilitada = habilitacion.consumidores_0352_habilitados()
    fecha, filas, estable = None, None, False
    for intento in range(INTENTOS_L2):
        muestra = _muestra(sesion, propiedad_id, a_fecha, habilitada)
        if muestra is None:
            return None
        fecha, filas, estable = muestra
        if estable:
            break
    if not estable:
        _LOG.warning("L-COSTE: lectura L2 agotada sin muestra estable",
                     extra={"propiedad_id": str(propiedad_id), "intentos": INTENTOS_L2})
    salida: dict[str, Any] = {"a_fecha": a_fecha.isoformat(), "declaracion_habilitada": habilitada}
    for ambito, total, n, mio, estados, declarado, corte, igual, posteriores, huella in filas:
        sin_fecha = habilitada and ambito == "ADQUISICION" and fecha is None
        estado, motivo = _regla(ambito, n, declarado, corte, igual, posteriores, a_fecha, sin_fecha)
        if ambito == "ADQUISICION" and not estable and estado == "COMPLETO":        # agotamiento conservador
            estado, motivo = "PARCIAL", "LECTURA_NO_ESTABLE"
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
