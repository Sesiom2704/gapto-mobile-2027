# ============================================================
# GAPTO MOBILE 2027
# Fichero: atribucion.py
# Ruta: backend/app/patrimonio/atribucion.py
# Descripcion: Atribucion M-2 de B2 y lectura de la titularidad en una fecha (R1 v0.9.5 §1.2, §II.1 AJ-TR1-10 y
#   HF-12; v0.9 §II.2; P-H2-03 adelantada a B2 por el mandato, §1.2.6).
#   - Titularidad en una fecha: filas de `entidad_participaciones` vigentes ese dia (vigente_desde <= f y
#     vigente_hasta nula o >= f). Es una lectura NUEVA: no toca L-PROP ni el GET de B1.
#   - SEGUN_TITULARIDAD_ACEPTADA: el servidor relee bajo el lock de la propiedad la titularidad en la fecha de
#     referencia y compara el conjunto COMPLETO {(actor, porcentaje exacto)} con la propuesta vista:
#     sin titularidad -> TITULARIDAD_NO_DISPONIBLE_EN_FECHA (nunca YO 100 por defecto); distinta ->
#     ATRIBUCION_PROPUESTA_DESFASADA. Criterio persistido PARTICIPACION_ENTIDAD (HF-12).
#   - MANUAL: partes declaradas (suma 100 exacta, > 0, <= 4 decimales, sin duplicados, actores del owner);
#     criterio MANUAL.
#   - NO_LO_SE: estado NO_DISPONIBLE y cero filas.
#   Importes: round_half_even(importe x pct / 100, 2) y residuo centimo a centimo por porcentaje descendente y
#   actor_id ascendente (texto); la suma es exactamente el importe (§1.2). Ids uuid5(efecto, prefijo + actor).
#   La titularidad nunca determina el pagador ni la cuenta la atribucion.
# Version: 0.1.0 (F06 T1-F06 B2 N1)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from app.core.modelos_efectos import DatosAtribucion
from app.core.unidad_trabajo import SesionMotor

CIEN = Decimal("100")
CENT = Decimal("0.01")
ESCALA_PCT = Decimal("0.0001")

SEGUN_TITULARIDAD = "SEGUN_TITULARIDAD_ACEPTADA"
MANUAL = "MANUAL"
NO_LO_SE = "NO_LO_SE"
MODOS = (SEGUN_TITULARIDAD, MANUAL, NO_LO_SE)
CRITERIO_ESCRITURA = "TITULARIDAD_EN_FECHA_ESCRITURA"      # C-COMPRA-01 (AJ-TR1-10)
CRITERIO_EFECTO = "TITULARIDAD_EN_FECHA_ECONOMICA"          # C-COMPRA-03 (fecha economica de su efecto)

PROPUESTA_DESFASADA = "ATRIBUCION_PROPUESTA_DESFASADA"
TITULARIDAD_NO_DISPONIBLE = "TITULARIDAD_NO_DISPONIBLE_EN_FECHA"
SUMA_NO_CUADRA = "SUMA_NO_CUADRA"
PARTICIPANTE_DUPLICADO = "PARTICIPANTE_DUPLICADO"
ENTRADA_INVALIDA = "ENTRADA_INVALIDA"


def _decimales(valor: Decimal) -> int:
    exponente = valor.as_tuple().exponent
    return -exponente if isinstance(exponente, int) and exponente < 0 else 0


def repartir(importe: Decimal, partes: list[tuple[uuid.UUID, Decimal]]) -> dict[uuid.UUID, Decimal]:
    """M-2: HALF_EVEN por parte y residuo determinista. La suma es exactamente el importe."""
    importe = importe.quantize(CENT)
    base = {a: (importe * p / CIEN).quantize(CENT, rounding=ROUND_HALF_EVEN) for a, p in partes}
    residuo = importe - sum(base.values(), Decimal(0))
    orden = sorted(partes, key=lambda x: (-x[1], str(x[0])))
    paso = CENT if residuo > 0 else -CENT
    i = 0
    while residuo != 0:
        base[orden[i % len(orden)][0]] += paso
        residuo -= paso
        i += 1
    return base


def titularidad_en_fecha(sesion: SesionMotor, propiedad_id: uuid.UUID, fecha: dt.date) -> list[dict[str, Any]]:
    """P-H2-03: partes vigentes en `fecha`, ordenadas por actor (texto). Sin filas = sin titularidad."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT x.actor_id, x.porcentaje, a.tercero_id, t.nombre FROM gapto.entidad_participaciones x "
            "JOIN gapto.actores_financieros a ON a.id = x.actor_id LEFT JOIN gapto.terceros t ON t.id = a.tercero_id "
            "WHERE x.entidad_id = %s AND x.vigente_desde <= %s AND (x.vigente_hasta IS NULL OR x.vigente_hasta >= %s) "
            "ORDER BY x.actor_id::text", (propiedad_id, fecha, fecha))
        return [{"actor_id": a, "porcentaje": Decimal(p).quantize(ESCALA_PCT), "yo": tid is None,
                 "tercero_id": tid, "nombre": nombre} for a, p, tid, nombre in cur.fetchall()]


def _partes(lista: list[dict[str, Any]] | None) -> list[tuple[uuid.UUID, Decimal]]:
    return sorted(((uuid.UUID(str(p["actor_id"])), Decimal(str(p["porcentaje"]))) for p in lista or []),
                  key=lambda x: str(x[0]))


def validar_forma(atribucion: dict[str, Any], *, criterio: str, fecha_referencia: dt.date) -> str | None:
    """Validacion pura (sin base): modo, propuesta con su criterio y fecha, partes manuales."""
    modo = atribucion.get("modo")
    if modo not in MODOS:
        return ENTRADA_INVALIDA
    propuesta = atribucion.get("propuesta_vista")
    partes = atribucion.get("partes")
    if modo == SEGUN_TITULARIDAD:
        if propuesta is None or partes is not None:
            return ENTRADA_INVALIDA
        if propuesta.get("criterio") != criterio or propuesta.get("fecha_referencia") != fecha_referencia:
            return ENTRADA_INVALIDA
        if not propuesta.get("partes"):
            return ENTRADA_INVALIDA
        return None
    if propuesta is not None:
        return ENTRADA_INVALIDA
    if modo == NO_LO_SE:
        return None if partes is None else ENTRADA_INVALIDA
    lista = _partes(partes)
    if not lista:
        return ENTRADA_INVALIDA
    if any(p <= 0 or p > CIEN or _decimales(p) > 4 for _, p in lista):
        return ENTRADA_INVALIDA
    if len({a for a, _ in lista}) != len(lista):
        return PARTICIPANTE_DUPLICADO
    if sum((p for _, p in lista), Decimal(0)) != CIEN:
        return SUMA_NO_CUADRA
    return None


def resolver(sesion: SesionMotor, propiedad_id: uuid.UUID, atribucion: dict[str, Any]
             ) -> list[tuple[uuid.UUID, Decimal]] | None | str:
    """Bajo el lock de la propiedad: partes a aplicar (lista), None (NO_LO_SE) o codigo de rechazo."""
    modo = atribucion["modo"]
    if modo == NO_LO_SE:
        return None
    if modo == MANUAL:
        partes = _partes(atribucion["partes"])
        actores = {a for a, _ in partes}
        with sesion.conexion.cursor() as cur:
            cur.execute("SELECT id FROM gapto.actores_financieros WHERE id = ANY(%s) "
                        "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid", (list(actores),))
            if {f[0] for f in cur.fetchall()} != actores:
                return ENTRADA_INVALIDA
        return partes
    propuesta = atribucion["propuesta_vista"]
    vigente = [(p["actor_id"], p["porcentaje"]) for p in
               titularidad_en_fecha(sesion, propiedad_id, propuesta["fecha_referencia"])]
    if not vigente:
        return TITULARIDAD_NO_DISPONIBLE
    if sorted(vigente, key=lambda x: str(x[0])) != _partes(propuesta["partes"]):
        return PROPUESTA_DESFASADA
    return sorted(vigente, key=lambda x: str(x[0]))


def filas(efecto_id: uuid.UUID, importe: Decimal, partes: list[tuple[uuid.UUID, Decimal]] | None, modo: str,
          prefijo: str) -> tuple[str, tuple[DatosAtribucion, ...]]:
    """(estado_atribucion, filas) del efecto con ids uuid5(efecto, prefijo + actor)."""
    if partes is None:
        return "NO_DISPONIBLE", ()
    criterio = "MANUAL" if modo == MANUAL else "PARTICIPACION_ENTIDAD"
    importes = repartir(importe, partes)
    return "COMPLETA", tuple(
        DatosAtribucion(atribucion_id=uuid.uuid5(efecto_id, f"{prefijo}{a}"), actor_id=a,
                        importe_atribuido=importes[a], criterio_atribucion=criterio,
                        porcentaje_aplicado=p.quantize(ESCALA_PCT))
        for a, p in partes)
