# ============================================================
# GAPTO MOBILE 2027
# Fichero: integridad_posicion.py
# Ruta: backend/app/services/integridad_posicion.py
# Descripcion: F04-D053. Integridad de la posicion generica (DERECHO_COBRO /
#   OBLIGACION_PAGO de `derechos_obligaciones_financieras`).
#
#   B8 · RAIZ DE BLOQUEO. Toda via que crea, corrige, cambia de fecha o anula
#   un delta de posicion serializa lectura, validacion y escritura sobre la
#   fila `entidades` de cada posicion afectada, y adquiere los recursos en un
#   ORDEN GLOBAL UNICO:
#
#     1. advisory (INVERSIONES, owner)  si la operacion escribira algo que
#        D-080 / 0270 validan en el COMMIT (vinculo hecho_entidades,
#        importe_delta o tipo_efecto). D-158: el patron fila -> advisory
#        diferido frente a advisory -> fila es interbloqueo determinista.
#     2. hechos existentes FOR NO KEY UPDATE ORDER BY id (D-171, sin cambios).
#     3. posiciones FOR NO KEY UPDATE ORDER BY id (raiz F04-D053).
#     4. movimientos existentes (lo hace el llamante, despues).
#
#   Las posiciones de un hecho se leen DESPUES de bloquear el hecho: con el
#   hecho bloqueado su conjunto de vinculos no puede cambiar.
#
#   B1 · VALIDADOR CENTRAL. Un unico punto, invocado por la creacion
#   (`_aplicar_delta` y el alta), OP-02, OP-03 y OP-21, siempre bajo la raiz:
#     `fotografiar` ANTES de escribir -> el writer escribe -> `validar` sobre
#     el estado final de la misma transaccion.
#   Reglas activas:
#     B2+B3 (lectura (a), v0.2 Q2) con saldo determinado: con S(d) = cierre
#       de la fecha economica d segun A1, se rechaza si existe d >= inicio con
#       S_post(d) < 0 y S_post(d) < S_pre(d). No crea ni agrava; mantener o
#       mejorar una incoherencia preexistente no se bloquea.
#     B4 con saldo determinado: delta nuevo o cambio de fecha hacia antes de
#       fecha_inicio_seguimiento -> rechazo (tambien el alta, v0.2 Q5).
#     B7 con saldo indeterminado: no se aplican B2, B3 ni B4.
#     B5 lectura (b) (dictamen v0.3): con la posicion cerrada no cambia nada
#       de lo que le pertenece (firma de deltas, vinculos y conciliaciones).
#     B6 L2 por hecho (dictamen v0.3): REEMBOLSO conciliado -> asignado =
#       |efectos de posicion| con el signo de la operacion; agravar un
#       historico se rechaza; CONDONACION sin asignaciones.
#   Vias x reglas (dictamen v0.3): creacion A1 B2 B3 B4 B5 B6; OP-02 A1 B2 B3
#   B4 B5; OP-03 A1 B2 B3 B5 B6; OP-21 A1 B2 B3 B5 B6; OP-09 SOLO B5 B6.
#   B9: INTEGRIDAD_POSICION_VIOLADA con su motivo.
#   Limitacion documentada (B2): no hay orden dentro de un mismo dia; se
#   valida el cierre de cada fecha con todos sus deltas incorporados.
# Version: 0.3.0
#   0.3.0 (F04-D053 B1 · v0.3): B5 lectura (b) y B6 L2 activados; modo solo
#   B5/B6 para OP-09.
# Version: 0.2.0
#   0.2.0 (F04-D053 B1 · v0.2): validador central B1 con B2/B3 (a), B4, B7 y
#   B9; huecos de B5/B6 sin activar.
# Version: 0.1.0
#   0.1.0 (F04-D053 B1 · P0-1): raiz de bloqueo y orden global.
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from app.core.errores import CodigoError, ErrorMotor, MotivoIntegridadPosicion
from app.core.modelos_posicion import (
    EFECTO_DE_POSICION,
    ESTADO_CERRADA,
    TIPO_HECHO_CONDONACION,
    TIPO_HECHO_REEMBOLSO,
    TIPO_OBLIGACION,
)
from app.core.unidad_trabajo import SesionMotor
from app.repositories import correcciones_repository as repo_corr
from app.repositories import posiciones_repository as repo_pos
from app.repositories import relaciones_repository as repo_rel

CERO = decimal.Decimal(0)


# ==================================================================
# B8 · raiz de bloqueo
# ==================================================================
def adquirir_raiz(
    sesion: SesionMotor,
    owner: uuid.UUID,
    *,
    hechos: Iterable[uuid.UUID] = (),
    posiciones: Iterable[uuid.UUID] = (),
    advisory: bool = False,
) -> list[uuid.UUID]:
    """Adquiere advisory -> hechos -> posiciones, en ese orden y una sola vez.

    Devuelve las posiciones bloqueadas: las indicadas mas las alimentadas por
    los hechos. Un hecho no visible falla cerrado (AGREGADO_NO_ENCONTRADO),
    igual que en OP-21.
    """
    if advisory:
        repo_corr.tomar_advisory_inversiones(sesion, owner)
    hechos = sorted(set(hechos), key=str)
    if hechos and not repo_rel.bloquear_hechos(sesion, hechos):
        raise ErrorMotor(
            CodigoError.AGREGADO_NO_ENCONTRADO,
            "El hecho indicado no existe o no es accesible.",
        )
    objetivo = set(posiciones)
    for hecho_id in hechos:
        objetivo.update(repo_pos.posiciones_de_hecho(sesion, hecho_id))
    return repo_pos.bloquear_posiciones(sesion, list(objetivo))


# ==================================================================
# B1 · validador central
# ==================================================================
@dataclass(frozen=True, slots=True)
class FotoPosicion:
    """Estado de una posicion ANTES de la operacion (bajo la raiz)."""

    entidad_id: uuid.UUID
    estado: str
    determinado: bool
    inicio: dt.date | None
    apertura: decimal.Decimal | None
    cierres: tuple[tuple[dt.date, decimal.Decimal], ...]
    firma: str


@dataclass(frozen=True, slots=True)
class FotoConciliacion:
    """B6. Estado de conciliacion de un hecho: suma asignada y la esperada."""

    hecho_id: uuid.UUID
    codigo: str | None
    asignado: decimal.Decimal
    esperado: decimal.Decimal


@dataclass(frozen=True, slots=True)
class Foto:
    posiciones: dict[uuid.UUID, FotoPosicion]
    hechos: dict[uuid.UUID, FotoConciliacion]


def violacion(motivo: MotivoIntegridadPosicion, mensaje: str, **extra) -> ErrorMotor:
    """B9: un unico codigo; el motivo viaja en el mensaje y en contexto_extra."""
    return ErrorMotor(
        CodigoError.INTEGRIDAD_POSICION_VIOLADA,
        f"{motivo.value}: {mensaje}",
        contexto_extra={"motivo": motivo.value, **extra},
    )


def _cierres(
    sesion: SesionMotor, entidad_id: uuid.UUID, posicion: dict
) -> tuple[tuple[dt.date, decimal.Decimal], ...]:
    """S(d) al cierre de cada fecha con deltas, desde la apertura (A1)."""
    acumulado = decimal.Decimal(posicion["saldo_apertura"])
    salida = []
    for fecha, suma in repo_pos.deltas_por_fecha(
        sesion, entidad_id, EFECTO_DE_POSICION[posicion["tipo"]]
    ):
        acumulado += decimal.Decimal(suma)
        salida.append((fecha, acumulado))
    return tuple(salida)


def _foto_conciliacion(sesion: SesionMotor, hecho_id: uuid.UUID) -> FotoConciliacion:
    """Asignado = suma de importe_asignado del hecho (todas sus conciliaciones).
    Esperado = |suma de efectos de posicion| con el signo de la operacion:
    pago de obligacion -> salida (negativo); cobro de derecho -> entrada."""
    codigo, asignado, efectos = repo_pos.conciliacion_de_hecho(sesion, hecho_id)
    esperado = CERO
    for tipo, suma in efectos:
        signo = -1 if tipo == TIPO_OBLIGACION else 1
        esperado += signo * abs(decimal.Decimal(suma))
    return FotoConciliacion(hecho_id, codigo, decimal.Decimal(asignado), esperado)


def fotografiar(
    sesion: SesionMotor,
    posiciones: Iterable[uuid.UUID],
    *,
    hechos: Iterable[uuid.UUID] = (),
) -> Foto:
    """Foto previa de las posiciones visibles y de la conciliacion de los
    hechos operados. Se llama bajo la raiz B8, antes de escribir."""
    fotos: dict[uuid.UUID, FotoPosicion] = {}
    for entidad_id in posiciones:
        posicion = repo_pos.leer_posicion(sesion, entidad_id)
        if posicion is None:
            continue
        determinado = posicion["saldo_apertura"] is not None
        fotos[entidad_id] = FotoPosicion(
            entidad_id=entidad_id,
            estado=posicion["estado"],
            determinado=determinado,
            inicio=posicion["fecha_inicio_seguimiento"],
            apertura=(
                decimal.Decimal(posicion["saldo_apertura"]) if determinado else None
            ),
            cierres=_cierres(sesion, entidad_id, posicion) if determinado else (),
            firma=repo_pos.firma_posicion(sesion, entidad_id),
        )
    return Foto(
        posiciones=fotos,
        hechos={h: _foto_conciliacion(sesion, h) for h in hechos},
    )


def exigir_fecha_no_anterior_al_inicio(foto: FotoPosicion, fecha: dt.date) -> None:
    """B4 (B7: solo con saldo determinado)."""
    if foto.determinado and foto.inicio is not None and fecha < foto.inicio:
        raise violacion(
            MotivoIntegridadPosicion.FECHA_ANTERIOR_INICIO,
            "La fecha economica es anterior al inicio de seguimiento de la "
            "posicion: ese tramo ya esta dentro de la apertura.",
            entidad_id=str(foto.entidad_id),
        )


def exigir_alta_no_anterior_al_inicio(
    sesion: SesionMotor, entidad_id: uuid.UUID, hecho_id: uuid.UUID
) -> None:
    """B4 en el alta (OP-12A y via OP-22): el efecto inicial no precede al inicio."""
    if repo_pos.delta_de_hecho_anterior_al_inicio(sesion, entidad_id, hecho_id):
        raise violacion(
            MotivoIntegridadPosicion.FECHA_ANTERIOR_INICIO,
            "El efecto de alta tiene fecha economica anterior al inicio de "
            "seguimiento de la posicion.",
            entidad_id=str(entidad_id),
        )


def _saldo_en(
    cierres: tuple[tuple[dt.date, decimal.Decimal], ...],
    fecha: dt.date,
    apertura: decimal.Decimal,
) -> decimal.Decimal:
    """S(fecha) de una funcion escalonada: ultimo cierre <= fecha."""
    saldo = apertura
    for dia, valor in cierres:
        if dia > fecha:
            break
        saldo = valor
    return saldo


def _regla_b2_b3(antes: FotoPosicion, despues: FotoPosicion) -> None:
    """B2 + B3 (a): fecha a fecha, sobre la union de fechas de ambos estados.
    Rechazo si existe d >= inicio con S_post(d) < 0 y S_post(d) < S_pre(d)."""
    apertura = despues.apertura
    fechas = sorted({d for d, _ in antes.cierres} | {d for d, _ in despues.cierres})
    for fecha in fechas:
        s_pre = _saldo_en(antes.cierres, fecha, apertura)
        s_post = _saldo_en(despues.cierres, fecha, apertura)
        if s_post < CERO and s_post < s_pre:
            raise violacion(
                MotivoIntegridadPosicion.SALDO_NEGATIVO,
                f"El saldo de la posicion al cierre del {fecha.isoformat()} "
                "quedaria negativo o mas negativo que antes.",
                entidad_id=str(despues.entidad_id),
                fecha=fecha.isoformat(),
            )


def _regla_b5(antes: FotoPosicion, despues: FotoPosicion) -> None:
    """B5, lectura (b) (dictamen v0.3): con la posicion CERRADA nada de lo que
    le pertenece cambia, aunque el saldo final no cambie: importe, tipo,
    fecha, moneda, anulacion del hecho, vinculo y conciliaciones de sus
    hechos. Se evalua sobre el estado posterior. Sin reapertura (R-F04-041)."""
    if antes.estado == ESTADO_CERRADA and despues.firma != antes.firma:
        raise violacion(
            MotivoIntegridadPosicion.POSICION_CERRADA,
            "La posicion esta cerrada: sus deltas, vinculos y conciliaciones "
            "no se modifican.",
            entidad_id=str(antes.entidad_id),
        )


def _signo_coherente(f: FotoConciliacion) -> bool:
    return f.asignado == 0 or f.esperado == 0 or (f.asignado > 0) == (f.esperado > 0)


def _regla_b6(antes: FotoConciliacion, despues: FotoConciliacion) -> None:
    """B6, L2 operativa (dictamen v0.3), por HECHO.

    REEMBOLSO conciliado (con asignaciones antes o despues): asignado =
    |efectos de posicion| con el signo de la operacion. Historico que ya
    incumple (B3): solo se rechaza agravar -aumentar |asignado - esperado|,
    pasar de conforme a no conforme o invertir el signo-; mantener o reducir
    la diferencia no se bloquea. CONDONACION: cero asignaciones."""
    codigo = despues.codigo
    if codigo == TIPO_HECHO_CONDONACION:
        if despues.asignado != 0 and abs(despues.asignado) > abs(antes.asignado):
            raise violacion(
                MotivoIntegridadPosicion.CONCILIACION_INCOMPATIBLE,
                "Un hecho CONDONACION no tiene conciliacion con tesoreria.",
                hecho_id=str(despues.hecho_id),
            )
        return
    if codigo != TIPO_HECHO_REEMBOLSO:
        return
    if antes.asignado == 0 and despues.asignado == 0:
        return  # no conciliado en ningun estado: B6 no aplica
    diferencia_pre = abs(antes.asignado - antes.esperado)
    diferencia_post = abs(despues.asignado - despues.esperado)
    if diferencia_post > diferencia_pre or (
        _signo_coherente(antes) and not _signo_coherente(despues)
    ):
        raise violacion(
            MotivoIntegridadPosicion.CONCILIACION_INCOMPATIBLE,
            "La conciliacion del REEMBOLSO no cuadraria con su efecto de "
            "posicion (importe asignado o signo).",
            hecho_id=str(despues.hecho_id),
        )


def validar(sesion: SesionMotor, antes: Foto, *, reglas_saldo: bool = True) -> None:
    """Estado FINAL de la misma transaccion frente a la foto previa.

    `reglas_saldo=False` es el modo de OP-09: solo B5 y B6, nunca reglas de
    saldo (dictamen v0.3, punto 2)."""
    despues = fotografiar(sesion, antes.posiciones.keys(), hechos=antes.hechos.keys())
    for entidad_id, previa in antes.posiciones.items():
        final = despues.posiciones.get(entidad_id)
        if final is None:  # pragma: no cover - una posicion no desaparece
            continue
        _regla_b5(previa, final)
        if reglas_saldo and final.determinado:  # B7
            _regla_b2_b3(previa, final)
    for hecho_id, previa in antes.hechos.items():
        _regla_b6(previa, despues.hechos[hecho_id])
