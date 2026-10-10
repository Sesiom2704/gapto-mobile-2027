# ============================================================
# GAPTO MOBILE 2027
# Fichero: captura_magnitudes.py
# Ruta: backend/app/api/captura_magnitudes.py
# Descripcion: C07 — captura de magnitudes con el SERVIDOR como autoridad
#   (F05-D014 §28.2; F05-D008 C07; F05-D012 AJ-01/AJ-02 reconciliados).
#   API DE INTEGRACION F05, PENDIENTE DE CONSOLIDACION F10 (F10-03/04).
#
#   Contrato de uso (lo verifica el inventario C-b, test_154 I4/I9):
#     - se invoca SOLO para una intencion NUEVA con estado CATEGORIA, dentro
#       de la rama `not ya_materializada` y DESPUES de la guarda C-a (que ya
#       tomo la categoria `FOR SHARE`); ANTES de componer OP-22. Un reintento
#       de una intencion ya materializada no revalida nada (AJ-C07-04): ni
#       asociacion, ni `enabled`, ni unidad, ni precision actuales;
#     - orden de locks (AJ-C07-07), continuacion del de la guarda:
#         cuenta (FOR NO KEY UPDATE) -> categoria (FOR SHARE) ->
#         filas de categoria_magnitudes de la categoria (FOR SHARE, por id) ->
#         sus magnitudes (FOR SHARE, por id) -> raiz (OP-22).
#       Una magnitud ENVIADA que no esta asociada se rechaza sin bloquearla;
#     - no escribe: un rechazo se devuelve antes de cualquier escritura, y la
#       unidad NO sale de aqui (la toma el writer F04 como snapshot de
#       `magnitudes.unidad_default`, AJ-C07-05);
#     - NO toma el advisory (CATEGORIAS, owner): el registro no serializa el
#       catalogo (C04).
#
#   Codigos F05 (409, definitivos, sin escritura previa), en ESTE orden de
#   evaluacion (§28.2):
#     1. asociacion obligatoria hacia magnitud deshabilitada (o no visible)
#        -> CATEGORIA_MAGNITUD_NO_DISPONIBLE;
#     2. magnitud inexistente, ajena, no asociada u opcional deshabilitada
#        -> MAGNITUD_NO_ADMITIDA (sin distinguir inexistente de ajena);
#     3. obligatoria ausente -> MAGNITUD_OBLIGATORIA_AUSENTE;
#     4. valor sintacticamente valido (DTO) pero fuera de `precision_decimales`
#        o de la capacidad numeric(18,6) -> MAGNITUD_VALOR_NO_VALIDO.
#   Sin redondeo: con precision 2, "1.23" y "1.230" son validos y "1.234" no.
#   Sin restriccion de signo: negativos y cero explicito se admiten.
#
#   `categoria_magnitudes` no tiene estado propio (AJ-02): una asociacion
#   vigente es una fila existente. La ajena no puede asociarse (WITH CHECK de
#   tenant_isolation); si una obligatoria apuntara a una magnitud no visible,
#   se trata como no disponible (fail-closed). La propiedad de owner de la
#   magnitud la garantiza la RLS bajo gapto_runtime.
#
#   Alcance semantico (AJ-C07-09): C07 se refiere a la categoria del UNICO
#   efecto GASTO de VS-01; no define magnitudes para hechos multicategoria
#   (F05-01-R15).
#
#   Los codigos son de la capa F05 y NO forman parte de la taxonomia F04
#   (core/errores.py no se modifica).
#
#   v0.2.0 (F05-03/F05-04 J2 §1.7; F05 §46.3 A9, R14): «No lo sé». La
#   intencion puede declarar DESCONOCIDAS magnitudes de la categoria: deben
#   estar asociadas y disponibles (si no, MAGNITUD_NO_ADMITIDA) y una
#   obligatoria declarada desconocida ya no es MAGNITUD_OBLIGATORIA_AUSENTE.
#   No generan fila en hecho_magnitudes (sin valor por defecto ni cero). Sin
#   declararla, la obligatoria ausente sigue rechazandose igual que antes.
# Version: 0.2.0
# ============================================================

from __future__ import annotations

import decimal
import uuid
from dataclasses import dataclass
from typing import Iterable, Protocol

from app.core.unidad_trabajo import SesionMotor

CODIGO_CATEGORIA_MAGNITUD_NO_DISPONIBLE = "CATEGORIA_MAGNITUD_NO_DISPONIBLE"
CODIGO_MAGNITUD_NO_ADMITIDA = "MAGNITUD_NO_ADMITIDA"
CODIGO_MAGNITUD_OBLIGATORIA_AUSENTE = "MAGNITUD_OBLIGATORIA_AUSENTE"
CODIGO_MAGNITUD_VALOR_NO_VALIDO = "MAGNITUD_VALOR_NO_VALIDO"

#: Capacidad fisica de hecho_magnitudes.valor: numeric(18,6) -> 12 digitos
#: enteros. Un valor mayor provocaria overflow en el INSERT (22003).
DIGITOS_ENTEROS_MAX = 12


class _Capturada(Protocol):
    magnitud_id: uuid.UUID
    valor: str


@dataclass(frozen=True, slots=True)
class _Asociacion:
    magnitud_id: uuid.UUID
    obligatoria: bool


@dataclass(frozen=True, slots=True)
class _Magnitud:
    enabled: bool
    precision_decimales: int


def valor_admisible(valor: str, precision_decimales: int) -> bool:
    """Regla UNICA de valor (AJ-C07-06), sobre texto ya canonico (DTO).
    Sin redondeo: los ceros decimales a la derecha no cuentan como precision
    usada; el resto de cifras decimales no puede superar la precision de la
    magnitud; la parte entera cabe en numeric(18,6)."""
    d = decimal.Decimal(valor)
    if not d.is_finite():
        return False
    signo, digitos, exponente = d.normalize().as_tuple()
    if d == 0:
        return True
    decimales = max(0, -exponente)
    enteros = max(0, len(digitos) + exponente)
    return decimales <= precision_decimales and enteros <= DIGITOS_ENTEROS_MAX


def _asociaciones(sesion: SesionMotor, categoria_id: uuid.UUID) -> list[_Asociacion]:
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT magnitud_id, obligatoria FROM gapto.categoria_magnitudes "
            "WHERE categoria_id = %s ORDER BY id FOR SHARE",
            (categoria_id,),
        )
        return [_Asociacion(f[0], f[1]) for f in cur.fetchall()]


def _magnitudes(sesion: SesionMotor, ids: list[uuid.UUID]) -> dict[uuid.UUID, _Magnitud]:
    if not ids:
        return {}
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, enabled, precision_decimales FROM gapto.magnitudes "
            "WHERE id = ANY(%s) ORDER BY id FOR SHARE",
            (ids,),
        )
        return {f[0]: _Magnitud(f[1], f[2]) for f in cur.fetchall()}


def validar_magnitudes(
    sesion: SesionMotor, categoria_id: uuid.UUID, capturadas: Iterable[_Capturada],
    desconocidas: Iterable[uuid.UUID] = (),
) -> str | None:
    """C07. Devuelve None si la captura es admisible o el codigo F05 de
    rechazo. No escribe. Debe llamarse en la transaccion que va a persistir,
    tras reconocer la identidad y tras la guarda C-a."""
    enviadas = {c.magnitud_id: c.valor for c in capturadas}
    no_lo_se = set(desconocidas)
    asociaciones = _asociaciones(sesion, categoria_id)
    fichas = _magnitudes(sesion, sorted({a.magnitud_id for a in asociaciones}))
    por_id = {a.magnitud_id: a for a in asociaciones}

    def disponible(magnitud_id: uuid.UUID) -> bool:
        ficha = fichas.get(magnitud_id)
        return ficha is not None and ficha.enabled

    # 1. Una obligatoria que no puede capturarse hace la categoria no
    #    capturable para registro nuevo, se envie lo que se envie.
    if any(a.obligatoria and not disponible(a.magnitud_id) for a in asociaciones):
        return CODIGO_CATEGORIA_MAGNITUD_NO_DISPONIBLE
    # 2. Cada enviada debe estar asociada y disponible.
    if any(m not in por_id or not disponible(m) for m in [*enviadas, *no_lo_se]):
        return CODIGO_MAGNITUD_NO_ADMITIDA
    # 3. Toda obligatoria debe venir informada o declarada «No lo sé» (A9).
    if any(a.obligatoria and a.magnitud_id not in enviadas and a.magnitud_id not in no_lo_se
           for a in asociaciones):
        return CODIGO_MAGNITUD_OBLIGATORIA_AUSENTE
    # 4. Precision y capacidad, sin redondeo.
    if any(not valor_admisible(v, fichas[m].precision_decimales) for m, v in enviadas.items()):
        return CODIGO_MAGNITUD_VALOR_NO_VALIDO
    return None
