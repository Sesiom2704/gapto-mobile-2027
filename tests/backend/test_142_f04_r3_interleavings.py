# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_142_f04_r3_interleavings.py
# Ruta: tests/backend/test_142_f04_r3_interleavings.py
# Descripcion: F04-D048 R3 §27. Interleavings forzados de OP-22, el
#   enriquecimiento, OP-21, OP-12 y OP-17.
#
#   El solapamiento se FUERZA: una conexion bloqueadora retiene el advisory
#   INVERSIONES del owner (o la fila raiz) mientras arrancan los dos
#   comandos; al liberarla compiten de verdad. No se acepta "no hubo
#   deadlock" como prueba: cada caso verifica el RESULTADO SEMANTICO final
#   (una sola realidad, versiones coherentes, perdedor con error de dominio
#   estable) y que ninguno queda colgado (join con timeout).
#
#   R-F04-033: OP-12 enganchado a un hecho existente frente a OP-21 con
#   `toca_inversion` puede producir 40P01; el retry de transaccion completa
#   debe recuperarlo sin perdida semantica ni livelock.
# Version: 0.2.0 (F04-D060 · F04-R2 R2-A, C3; contrato v0.6 §6.5; mandato
#   F04-R2A §2 D-A4): IL5 deja de aceptar el 40P01 y EXIGE su ausencia. OP-12A
#   enganchado toma el advisory antes del hecho (orden global de F04-D058), asi
#   que el par serializa. Se ejecuta en serie y determinista en los dos ordenes
#   con el arnes de test_139 (el primero espera tras la barrera del hecho y el
#   segundo tras el primero antes de liberar): gana el primero y el otro recibe
#   VERSION_DESFASADA. Con OP-12A primero el oraculo es el del mandato (gana P,
#   Q desfasada, posicion creada, importe_delta 10). Sin 40P01 en el log de
#   reintento ni deadlocks en pg_stat_database. Se anade OP-12A frente a OP-21
#   sin `toca_inversion` ni importe (OP-21 sin advisory). La contraprueba
#   (advisory despues del hecho) reproduce el 40P01 con OP-12A primero.
# Version: 0.1.0
# ============================================================
from __future__ import annotations

import dataclasses
import decimal
import logging
import threading
import time
import uuid

import psycopg
import pytest

from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos_compuesto import (
    DatosContextoHecho,
    DatosEntidadHecho,
    DatosHechoCompuesto,
    DatosPrevisionCompuesta,
)
from app.core.modelos_prevision import DatosVinculo
from app.services.contexto_service import ContextoService
from app.services.correcciones_service import DatosCorreccion
from conftest import leer_fila
from f08_motor import efecto
from test_140_f04_r3_op22 import _prevision, alta, cuenta_filas, hecho, nueva_entidad, pago

D = decimal.Decimal
REPETICIONES = 4
TIMEOUT = 30


def _en_hilos(*funciones):
    resultados: list[dict] = [dict() for _ in funciones]

    def envolver(i, f):
        try:
            resultados[i]["r"] = f()
        except Exception as exc:  # noqa: BLE001 - se clasifica en el oraculo
            resultados[i]["e"] = exc

    hilos = [threading.Thread(target=envolver, args=(i, f)) for i, f in enumerate(funciones)]
    for h in hilos:
        h.start()
    return hilos, resultados


def _advisory_retenido(dsn, owner):
    c = psycopg.connect(dsn)
    c.execute("BEGIN")
    c.execute("SELECT pg_advisory_xact_lock(hashtext('gapto:INVERSIONES'), hashtext(%s))", (str(owner),))
    return c


def _liberar_y_esperar(bloqueador, hilos):
    time.sleep(0.8)
    bloqueador.execute("ROLLBACK")
    bloqueador.close()
    for h in hilos:
        h.join(TIMEOUT)
        assert not h.is_alive(), "comando colgado: posible livelock"


def _codigo(res):
    e = res.get("e")
    return None if e is None else getattr(e, "codigo", e)


@pytest.fixture()
def op22(unidad):
    from app.services.compuesto_service import HechosCompuestosService
    from app.services.previsiones_service import impacto_correccion_ancla

    return HechosCompuestosService(unidad, impacto_ancla=impacto_correccion_ancla)


@pytest.mark.parametrize("vuelta", range(REPETICIONES))
def test_il1_op22_contra_op22_misma_raiz(dsn, op22, contexto, admin, cuenta, vuelta) -> None:
    """IL1. Dos OP-22 con la MISMA intencion solapadas: una sola realidad; el
    otro termina idempotente o con conflicto de identidad, nunca duplicado."""
    owner = contexto.owner_user_id
    h = hecho()
    datos = DatosHechoCompuesto(
        hecho=h, efectos=[efecto("GASTO", D("100.0000"))], pagos=[pago(h.hecho_id, cuenta, "-100.0000")],
        contexto=DatosContextoHecho(entidades=[DatosEntidadHecho(uuid.uuid4(), nueva_entidad(admin, owner), "AFECTA_A", principal=False)]),
    )
    bloqueador = _advisory_retenido(dsn, owner)
    hilos, res = _en_hilos(lambda: op22.registrar_hecho_compuesto(contexto, datos),
                           lambda: op22.registrar_hecho_compuesto(contexto, datos))
    _liberar_y_esperar(bloqueador, hilos)
    exitos = [r["r"] for r in res if "r" in r]
    assert len(exitos) >= 1
    assert all(_codigo(r) in (None, CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION) for r in res), res
    assert sum(1 for r in exitos if not r.idempotente) == 1
    for tabla in ("hecho_efectos", "hecho_movimientos_tesoreria", "hecho_entidades"):
        assert cuenta_filas(admin, owner, tabla, "hecho_id", h.hecho_id) == 1


@pytest.mark.parametrize("vuelta", range(REPETICIONES))
def test_il1b_op22_contra_op22_sin_advisory(dsn, op22, contexto, admin, cuenta, vuelta) -> None:
    """IL1b. Misma intencion SIN hecho_entidades (no hay advisory que
    serialice): el solapamiento se fuerza reteniendo la conexion del primero
    antes del COMMIT. Oraculo: una sola realidad y ningun error distinto del
    conflicto de identidad; el perdedor no duplica nada."""
    owner = contexto.owner_user_id
    h = hecho()
    datos = DatosHechoCompuesto(hecho=h, efectos=[efecto("GASTO", D("100.0000"))],
                                pagos=[pago(h.hecho_id, cuenta, "-100.0000")])
    hilos, res = _en_hilos(lambda: op22.registrar_hecho_compuesto(contexto, datos),
                           lambda: op22.registrar_hecho_compuesto(contexto, datos))
    for hilo in hilos:
        hilo.join(TIMEOUT)
        assert not hilo.is_alive()
    assert any("r" in r for r in res), res
    assert all(_codigo(r) in (None, CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION) for r in res), res
    for tabla in ("hecho_efectos", "hecho_movimientos_tesoreria"):
        assert cuenta_filas(admin, owner, tabla, "hecho_id", h.hecho_id) == 1
    assert cuenta_filas(admin, owner, "movimientos_tesoreria", "id", datos.pagos[0].movimiento.movimiento_id) == 1


@pytest.mark.parametrize("vuelta", range(REPETICIONES))
def test_il2_enriquecimiento_contra_op21(
    dsn, unidad, servicio_correcciones, servicio, servicio_efectos, contexto, admin, vuelta
) -> None:
    """IL2. Enriquecimiento (entidad) y OP-21 (entidad) sobre el MISMO hecho y
    la misma version: serializados por advisory+raiz; gana uno y el otro
    recibe VERSION_DESFASADA. Estado final coherente con el ganador."""
    owner = contexto.owner_user_id
    h = hecho()
    servicio.crear_hecho(contexto, h)
    v = servicio_efectos.registrar_efectos(contexto, hecho_id=h.hecho_id, row_version_esperada=1,
                                           efectos=[efecto("GASTO", D("10.0000"))], presupuestable=True).row_version
    previa = DatosEntidadHecho(uuid.uuid4(), nueva_entidad(admin, owner), "AFECTA_A", principal=False)
    v = ContextoService(unidad).enriquecer(contexto, hecho_id=h.hecho_id, row_version_esperada=v,
                                           datos=DatosContextoHecho(entidades=[previa])).hecho_row_version
    nueva = DatosEntidadHecho(uuid.uuid4(), nueva_entidad(admin, owner), "RELACIONADO_CON", principal=False)
    reemplazo = DatosEntidadHecho(uuid.uuid4(), nueva_entidad(admin, owner), "AFECTA_A", principal=False)
    bloqueador = _advisory_retenido(dsn, owner)
    hilos, res = _en_hilos(
        lambda: ContextoService(unidad).enriquecer(contexto, hecho_id=h.hecho_id, row_version_esperada=v,
                                                   datos=DatosContextoHecho(entidades=[nueva])),
        lambda: servicio_correcciones.corregir(contexto, DatosCorreccion(
            hecho_id=h.hecho_id, row_version_esperada=v, motivo="entidad equivocada",
            entidades_a_eliminar=(previa.registro_id,), entidades_a_crear=(reemplazo,))),
    )
    _liberar_y_esperar(bloqueador, hilos)
    codigos = sorted(str(_codigo(r)) for r in res)
    assert codigos == sorted([str(None), str(CodigoError.VERSION_DESFASADA)]), res
    filas = cuenta_filas(admin, owner, "hecho_entidades", "hecho_id", h.hecho_id)
    assert filas == (2 if "r" in res[0] else 1)


@pytest.mark.parametrize("vuelta", range(REPETICIONES))
def test_il3_op22_con_posicion_contra_op21_toca_inversion(
    dsn, op22, servicio, servicio_efectos, servicio_correcciones, contexto, admin, contraparte, vuelta
) -> None:
    """IL3 / D-080. OP-22 con posicion (escribe hecho_entidades) y OP-21 con
    toca_inversion sobre OTRO hecho del mismo owner: ambos toman primero el
    advisory, se serializan y ambos terminan con exito."""
    owner = contexto.owner_user_id
    otro = hecho()
    servicio.crear_hecho(contexto, otro)
    e = efecto("GASTO", D("10.0000"))
    v = servicio_efectos.registrar_efectos(contexto, hecho_id=otro.hecho_id, row_version_esperada=1,
                                           efectos=[e], presupuestable=True).row_version
    h = hecho()
    datos = DatosHechoCompuesto(hecho=h, efectos=[efecto("GASTO", D("100.0000"))],
                                posiciones=[alta(h.hecho_id, contraparte, importe="40.0000")])
    bloqueador = _advisory_retenido(dsn, owner)
    hilos, res = _en_hilos(
        lambda: op22.registrar_hecho_compuesto(contexto, datos),
        lambda: servicio_correcciones.corregir(contexto, DatosCorreccion(
            hecho_id=otro.hecho_id, row_version_esperada=v, motivo="importe falso", toca_inversion=True,
            efectos_a_actualizar={e.efecto_id: {"importe_delta": D("11.0000")}})),
    )
    _liberar_y_esperar(bloqueador, hilos)
    assert all("r" in r for r in res), res
    assert cuenta_filas(admin, owner, "hecho_entidades", "hecho_id", h.hecho_id) == 1


@pytest.mark.parametrize("vuelta", range(REPETICIONES))
def test_il4_op22_contra_op17_misma_prevision(
    dsn, op22, servicio_previsiones, servicio, servicio_efectos, contexto, admin, vuelta
) -> None:
    """IL4. OP-22 (con prevision) y OP-17 suelto sobre la MISMA prevision y
    version: uno gana y el otro VERSION_DESFASADA; si pierde OP-22, NADA de
    su hecho queda confirmado."""
    owner = contexto.owner_user_id
    prevision_id, pv = _prevision(admin, contexto, servicio_previsiones)
    suelto = hecho()
    servicio.crear_hecho(contexto, suelto)
    servicio_efectos.registrar_efectos(contexto, hecho_id=suelto.hecho_id, row_version_esperada=1,
                                       efectos=[efecto("GASTO", D("100.0000"))], presupuestable=True)
    h = hecho()
    datos = DatosHechoCompuesto(hecho=h, efectos=[efecto("GASTO", D("100.0000"))],
                                prevision=DatosPrevisionCompuesta(prevision_id, pv, uuid.uuid4(), D("100.0000"), marcar_realizada=True))
    bloqueo = psycopg.connect(dsn)
    bloqueo.execute("BEGIN")
    bloqueo.execute("SET LOCAL ROLE gapto_owner")
    bloqueo.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
    bloqueo.execute("SELECT 1 FROM gapto.previsiones WHERE id=%s FOR UPDATE", (prevision_id,))
    hilos, res = _en_hilos(
        lambda: op22.registrar_hecho_compuesto(contexto, datos),
        lambda: servicio_previsiones.vincular_realidad(
            contexto, prevision_id=prevision_id, row_version_esperada=pv,
            datos=DatosVinculo(vinculo_id=uuid.uuid4(), hecho_id=suelto.hecho_id,
                               importe_asignado=D("100.0000"), marcar_realizada=False)),
    )
    _liberar_y_esperar(bloqueo, hilos)
    codigos = sorted(str(_codigo(r)) for r in res)
    assert codigos == sorted([str(None), str(CodigoError.VERSION_DESFASADA)]), res
    assert cuenta_filas(admin, owner, "prevision_hechos", "prevision_id", prevision_id) == 1
    assert cuenta_filas(admin, owner, "hechos_financieros", "id", h.hecho_id) == (1 if "r" in res[0] else 0)


IL5_CASOS = [(variante, primero) for variante in ("toca_inversion", "sin_advisory") for primero in ("OP-12A", "OP-21")]


@pytest.mark.parametrize("variante, primero", IL5_CASOS, ids=[f"{v}-{p}-primero" for v, p in IL5_CASOS])
def test_il5_r_f04_033_op12_enganchado_contra_op21_toca_inversion(
    dsn, servicio_posiciones, servicio, servicio_efectos, servicio_correcciones, contexto, admin, contraparte,
    variante, primero, caplog
) -> None:
    """IL5 / R-F04-033 tras C3. OP-12A enganchado a H (advisory -> hecho) frente a OP-21 sobre H, en serie
    determinista y en los dos ordenes. Oraculo: gana el primero, el segundo recibe VERSION_DESFASADA, el estado
    final es exactamente el del ganador, nadie queda colgado y NO hay 40P01 (ni reintento ni deadlock)."""
    from test_139_f04_r1_concurrencia_serial import LOGGER, serie

    caplog.set_level(logging.WARNING, logger=LOGGER)
    owner = contexto.owner_user_id
    h = hecho()
    servicio.crear_hecho(contexto, h)
    e = efecto("GASTO", D("10.0000"))
    v = servicio_efectos.registrar_efectos(contexto, hecho_id=h.hecho_id, row_version_esperada=1,
                                           efectos=[e], presupuestable=True).row_version
    a = dataclasses.replace(alta(h.hecho_id, contraparte, importe="5.0000"), hecho_row_version_esperada=v)
    if variante == "toca_inversion":
        cambios, toca = {"importe_delta": D("12.0000")}, True
    else:  # OP-21 sin advisory: ni toca_inversion ni importe_delta/tipo_efecto
        cambios, toca = {"descripcion": "concepto corregido"}, False
    pasos = {
        "OP-12A": lambda: servicio_posiciones.crear_posicion(contexto, a),
        "OP-21": lambda: servicio_correcciones.corregir(contexto, DatosCorreccion(
            hecho_id=h.hecho_id, row_version_esperada=v, motivo="importe falso", toca_inversion=toca,
            efectos_a_actualizar={e.efecto_id: cambios})),
    }
    segundo = "OP-21" if primero == "OP-12A" else "OP-12A"
    traza = serie(dsn, caplog, [("hechos_financieros", h.hecho_id)], (primero, pasos[primero]),
                  (segundo, pasos[segundo]))
    traza.pop("resultados")
    assert traza["primero_espera"] and traza["segundo_espera"], traza
    assert not traza["vivos"], traza
    assert traza["reintentos_40P01"] == 0 and traza["deadlocks_delta"] == 0, traza
    assert traza[primero] == "OK" and traza[segundo] == CodigoError.VERSION_DESFASADA.value, traza
    posicion_gano = primero == "OP-12A"
    assert cuenta_filas(admin, owner, "entidades", "id", a.entidad_id) == (1 if posicion_gano else 0)
    importe, descripcion = leer_fila(admin, owner, "SELECT importe_delta, descripcion FROM gapto.hecho_efectos "
                                     "WHERE id=%s", (e.efecto_id,))
    assert importe == (D("12.0000") if not posicion_gano and variante == "toca_inversion" else D("10.0000"))
    assert (descripcion == "concepto corregido") == (not posicion_gano and variante == "sin_advisory")
