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
#   categoria NULL. Filas con tercero_id o entidad_id no nulos se ignoraban
#   SIEMPRE (dimensiones diferidas a F05-04, AJ-D026-12); desde v0.2.0 solo
#   entidad_id sigue diferida y las filas sin tipo se ignoran (ver v0.2.0).
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
#
#   v0.1.1 (F05-02 B1-C, AJ-B1-02): solo documentacion. La cabeza
#   contradictoria es una DEFENSA fail-closed ante configuracion invalida
#   (que el writer impide), no una regla de precedencia (E01). Sin cambio
#   de comportamiento.
#
#   v0.2.0 (F05-03/F05-04 J2 §1.5; F05 §46.4 R6, §46.5 E2/E3; F05-D032 C4):
#   - `tercero_id` pasa a ser dimension OPERATIVA (E2): DIMENSIONES =
#     (tipo_hecho_id, categoria_id, tercero_id) y la especificidad tecnica es
#     el numero de claves no nulas entre las tres (0..3). Un tercero NULL en
#     el contexto («sin tercero») solo casa con preferencias de tercero NULL,
#     igual que la categoria. `entidad_id` sigue DIFERIDA: una fila con
#     entidad_id no nulo se ignora siempre.
#   - Se retira la preferencia global sin tipo (E3): el resolver IGNORA las
#     filas con tipo_hecho_id NULL (datos previos a la conversion C4 o
#     escritos fuera del writer). La precedencia D-042 y el desempate de
#     §41.4 no cambian.
#   - `resolver` recibe el tercero del contexto (None = sin tercero) y
#     `cuentas_elegibles_registro` sigue siendo la regla de elegibilidad
#     de cuenta del registro.
# Version: 0.2.0
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
DIMENSIONES = ("tipo_hecho_id", "categoria_id", "tercero_id")
CAMPOS = {"cuenta": "cuenta_default_id", "presupuestable": "presupuestable_default"}


# ------------------------------------------------------------------ reglas puras
def dimension_diferida(p: dict[str, Any]) -> bool:
    """Solo `entidad_id` sigue diferida (E2: tercero_id es operativo)."""
    return p.get("entidad_id") is not None


def sin_tipo(p: dict[str, Any]) -> bool:
    """Preferencia global sin tipo, retirada por E3: el resolver no la consume."""
    return p.get("tipo_hecho_id") is None


def consumible(p: dict[str, Any]) -> bool:
    """El resolver y la regla de empate solo consideran estas filas."""
    return not dimension_diferida(p) and not sin_tipo(p)


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
    valores distintos.

    CONTRADICTORIA no es una regla de precedencia: es una DEFENSA fail-closed
    ante una configuracion invalida que el writer impide (empate de
    AJ-D026-03) y que solo puede existir por escritura fuera del writer. Ante
    ella el campo queda sin propuesta y nunca se elige un valor (E01)."""
    propias = [p for p in candidatas if p[columna] is not None]
    if not propias:
        return None
    clave = max((especificidad(p), p["prioridad"]) for p in propias)
    cabeza = [p for p in propias if (especificidad(p), p["prioridad"]) == clave]
    if len({p[columna] for p in cabeza}) != 1:
        return CONTRADICTORIA
    return min(cabeza, key=lambda p: p["id"])


# ------------------------------------------------------------------ lecturas
def tipo_hecho_registro(sesion: SesionMotor, codigo: str = TIPO_HECHO_REGISTRO) -> uuid.UUID:
    """Id del tipo de hecho de un registro (GASTO por defecto; INGRESO en F05-04)."""
    fila = sesion.uno("SELECT id FROM gapto.tipos_hecho WHERE codigo = %s", (codigo,))
    assert fila is not None, f"catalogo tipos_hecho sin {codigo}"
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
    tercero_id: uuid.UUID | None = None,
) -> dict[str, dict[str, Any] | None]:
    """Propuesta por campo para el contexto del registro: {campo: {valor,
    origen: {capa, preferencia_id}} | None}. Instantanea de lectura, sin locks.
    Si la cabeza de un campo es contradictoria (defensa fail-closed, ver
    `ganadora`), ese campo queda sin propuesta, tambien sin el fallback de
    cuenta unica (E01)."""
    contexto = {"tipo_hecho_id": tipo_hecho_id, "categoria_id": categoria_id, "tercero_id": tercero_id}
    candidatas = [p for p in repo.habilitadas(sesion) if consumible(p) and coincide(p, contexto)]
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
