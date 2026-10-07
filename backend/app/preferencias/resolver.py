# ============================================================
# GAPTO MOBILE 2027
# Fichero: resolver.py
# Ruta: backend/app/preferencias/resolver.py
# Descripcion: Resolver de la propuesta de registro por campo (F05-02,
#   F05-D026 §41.3/§41.4; REG-01 campos 3 y 5 enmendados por E1/E2). Servicio
#   PURO de lectura: no escribe, no toma el advisory (PREFERENCIAS, owner) ni
#   bloquea filas. Es una instantanea para MOSTRAR: el registro la sella en la
#   intencion y nunca relee la preferencia al confirmar (§41.4, AJ-D026-11).
#
#   Capas efectivas v1 (AJ-D026-01): preferencia contextual > default general.
#   Plantilla y regla/origen funcional existen en el modelo D-042 pero no
#   tienen consumidor y nunca producen propuesta (huecos sin implementar). El
#   dato explicito no entra aqui: lo aplica el cliente.
#
#   Candidatas por campo: habilitadas, del owner (RLS + GUC), que COINCIDEN
#   con el contexto y que proponen ese campo. Coincidencia por dimension
#   operativa (tipo_hecho_id, categoria_id): NULL = comodin; si no, igualdad
#   EXACTA (categoria sin herencia de ancestros, AJ-D026-05). Una categoria
#   NULL en el contexto («Sin categoria») solo casa con preferencias de
#   categoria NULL. Filas con tercero_id o entidad_id no nulos se ignoran
#   SIEMPRE (dimensiones diferidas a F05-04, AJ-D026-12; defensa frente a
#   filas escritas fuera del writer).
#
#   Orden: especificidad desc (claves no nulas entre tipo_hecho_id y
#   categoria_id, AJ-D026-02), prioridad desc (mayor valor = mayor prioridad,
#   AJ-D026-04). Cabeza con valores distintos (configuracion invalida que el
#   writer impide) -> sin propuesta para ese campo, nunca eleccion arbitraria
#   (tampoco el fallback de cuenta unica: el campo queda sin propuesta).
#   Cabeza con el mismo valor en varias filas (empate no contradictorio,
#   AJ-D026-08) -> ese valor; el origen cita la de menor id (determinista).
#   Cada campo se resuelve por separado (E3, AJ-D026-07).
#
#   Cuenta (E2, AJ-D025-13/14): (a) la de la preferencia ganadora si es
#   elegible en `fecha`; si no lo es se IGNORA sin descender a la siguiente
#   preferencia; (b) sin (a), la unica cuenta elegible cuando haya
#   exactamente una (capa DEFAULT_GENERAL); en otro caso, sin propuesta. Nunca
#   error. Elegible = regla de cuentas_pago (lecturas_vs01.cuentas_elegibles)
#   + misma moneda del registro (EUR; REG-01 campo 5, §41.7).
#   Presupuestable (E1): valor de la ganadora; sin default general.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from app.api.lecturas_vs01 import cuentas_elegibles
from app.core.unidad_trabajo import SesionMotor
from app.preferencias import repositorio as repo

#: Moneda del registro VS-01 (dto_vs01: moneda Literal["EUR"]).
MONEDA_REGISTRO = "EUR"
#: Codigo del tipo de hecho del write-path de gasto pagado (traductor VS-01).
TIPO_HECHO_REGISTRO = "GASTO"

CAPA_PREFERENCIA = "PREFERENCIA"
CAPA_DEFAULT_GENERAL = "DEFAULT_GENERAL"
DIMENSIONES = ("tipo_hecho_id", "categoria_id")
CAMPOS = {"cuenta": "cuenta_default_id", "presupuestable": "presupuestable_default"}


# ------------------------------------------------------------------ reglas puras
def dimension_diferida(p: dict[str, Any]) -> bool:
    return p.get("tercero_id") is not None or p.get("entidad_id") is not None


def especificidad(p: dict[str, Any]) -> int:
    return sum(1 for d in DIMENSIONES if p[d] is not None)


def coincide(p: dict[str, Any], contexto: dict[str, Any]) -> bool:
    return all(p[d] is None or p[d] == contexto[d] for d in DIMENSIONES)


def pueden_coincidir(p: dict[str, Any], q: dict[str, Any]) -> bool:
    """Existe un contexto en el que ambas coinciden: en cada dimension
    operativa, claves iguales o al menos una NULL (AJ-D026-03)."""
    return all(p[d] is None or q[d] is None or p[d] == q[d] for d in DIMENSIONES)


#: Resultado de `ganadora` cuando la cabeza tiene valores distintos.
CONTRADICTORIA = "CONTRADICTORIA"


def ganadora(candidatas: list[dict[str, Any]], columna: str) -> dict[str, Any] | str | None:
    """Preferencia que decide `columna`; None si ninguna la propone;
    CONTRADICTORIA si la cabeza (max especificidad, max prioridad) propone
    valores distintos."""
    propias = [p for p in candidatas if p[columna] is not None]
    if not propias:
        return None
    clave = max((especificidad(p), p["prioridad"]) for p in propias)
    cabeza = [p for p in propias if (especificidad(p), p["prioridad"]) == clave]
    if len({p[columna] for p in cabeza}) != 1:
        return CONTRADICTORIA
    return min(cabeza, key=lambda p: p["id"])


# ------------------------------------------------------------------ lecturas
def tipo_hecho_registro(sesion: SesionMotor) -> uuid.UUID:
    fila = sesion.uno("SELECT id FROM gapto.tipos_hecho WHERE codigo = %s", (TIPO_HECHO_REGISTRO,))
    assert fila is not None, "catalogo tipos_hecho sin GASTO"
    return fila[0]


def cuentas_elegibles_registro(sesion: SesionMotor, fecha: dt.date) -> list[uuid.UUID]:
    return [f[0] for f in cuentas_elegibles(sesion, fecha) if f[2] == MONEDA_REGISTRO]


def _propuesta(valor: Any, capa: str, preferencia_id: uuid.UUID | None = None) -> dict[str, Any]:
    return {"valor": valor, "origen": {"capa": capa, "preferencia_id": preferencia_id}}


def resolver(
    sesion: SesionMotor,
    *,
    tipo_hecho_id: uuid.UUID,
    categoria_id: uuid.UUID | None,
    fecha: dt.date,
) -> dict[str, dict[str, Any] | None]:
    contexto = {"tipo_hecho_id": tipo_hecho_id, "categoria_id": categoria_id}
    candidatas = [
        p for p in repo.habilitadas(sesion) if not dimension_diferida(p) and coincide(p, contexto)
    ]
    elegibles = cuentas_elegibles_registro(sesion, fecha)

    cuenta = None
    g = ganadora(candidatas, CAMPOS["cuenta"])
    if isinstance(g, dict) and g["cuenta_default_id"] in elegibles:
        cuenta = _propuesta(g["cuenta_default_id"], CAPA_PREFERENCIA, g["id"])
    elif g != CONTRADICTORIA and len(elegibles) == 1:
        cuenta = _propuesta(elegibles[0], CAPA_DEFAULT_GENERAL)

    presupuestable = None
    g = ganadora(candidatas, CAMPOS["presupuestable"])
    if isinstance(g, dict):
        presupuestable = _propuesta(g["presupuestable_default"], CAPA_PREFERENCIA, g["id"])

    return {"cuenta": cuenta, "presupuestable": presupuestable}
