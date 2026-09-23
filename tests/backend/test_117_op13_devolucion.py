# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_117_op13_devolucion.py
# Ruta: tests/backend/test_117_op13_devolucion.py
# Descripcion: F04-06 / B3. OP-13 devolucion economica.
#
#   TRES PROPIEDADES GOBIERNAN LA SUITE:
#
#   INV-05  una devolucion conserva la naturaleza del original. Devolver un
#           gasto produce un GASTO negativo, jamas un INGRESO. Que el dinero
#           entre en la cuenta no cambia que aquello fue un gasto.
#   F04-D030 la capacidad reversible se agrega POR NATURALEZA, porque la
#           relacion es fact-level y el modelo no conserva trazabilidad hacia
#           un `hecho_efectos.id`. Signos mezclados => fail-closed.
#   F04-D033 devolucion y materializacion de previsión COEXISTEN. Que el
#           original satisficiera una expectativa sigue siendo cierto.
#
#   Y una advertencia que la suite verifica de forma explicita: el limite
#   acumulado NO tiene red fisica. No hay constraint sobre lo devuelto. Lo
#   protege unicamente el lock del hecho original, igual que R-F04-017 protege
#   la identidad de ocurrencia en F04-05.
# Version: 0.2.0
#   0.2.0 (F04-D046 R2): el helper declara `presupuestable` explicito (GASTO/INGRESO), exigido ahora por OP-13.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import threading
import uuid

import psycopg
import pytest

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import DatosCreacionHecho
from app.core.modelos_devolucion import DatosDevolucion
from app.core.modelos_efectos import DatosEfecto
from app.services.devoluciones_service import DevolucionesService
from app.services.efectos_service import EfectosService
from app.services.hechos_service import HechosService
from conftest import leer_fila

D = decimal.Decimal
F = dt.date.fromisoformat

BRUTO = D("120.0000")


def crear_origen(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    *,
    tipo_efecto: str = "GASTO",
    importe: decimal.Decimal = BRUTO,
    segundo: decimal.Decimal | None = None,
    moneda: str = "EUR",
    tipo_hecho: str = "GASTO",
) -> uuid.UUID:
    """Hecho original con uno o dos efectos de la misma naturaleza."""
    hecho_id = uuid.uuid4()
    servicio.crear_hecho(
        contexto,
        DatosCreacionHecho(
            hecho_id=hecho_id,
            fecha_hecho=F("2027-05-01"),
            moneda=moneda,
            presupuestable=True,
            estado_localizacion="NO_APLICA",
            tipo_hecho_codigo=tipo_hecho,
            importe_total=importe,
        ),
    )
    efectos = [
        DatosEfecto(
            efecto_id=uuid.uuid4(),
            tipo_efecto=tipo_efecto,
            importe_delta=importe,
            estado_atribucion="NO_DISPONIBLE",
        )
    ]
    if segundo is not None:
        efectos.append(
            DatosEfecto(
                efecto_id=uuid.uuid4(),
                tipo_efecto=tipo_efecto,
                importe_delta=segundo,
                estado_atribucion="NO_DISPONIBLE",
            )
        )
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=1, efectos=efectos
    )
    return hecho_id


def datos_devolucion(original: uuid.UUID, **extra) -> DatosDevolucion:
    base = {
        "hecho_id": uuid.uuid4(),
        "efecto_id": uuid.uuid4(),
        "relacion_id": uuid.uuid4(),
        "hecho_original_id": original,
        "tipo_efecto": "GASTO",
        "importe": D("45.0000"),
        "fecha_hecho": F("2027-05-20"),
        "moneda": "EUR",
        "concepto": "Devolucion",
    }
    base.update(extra)
    # F04-D046 R2. La devolucion declara su propia decision historica. Con
    # GASTO/INGRESO es obligatoria; con DEUDA/DERECHO_COBRO se deriva y no se
    # declara. El helper la fija explicitamente para no depender de defaults.
    if "presupuestable" not in extra and base["tipo_efecto"] in ("GASTO", "INGRESO"):
        base["presupuestable"] = True
    return DatosDevolucion(**base)


# ==================================================================
# Camino correcto
# ==================================================================

def test_devolucion_parcial_conserva_la_naturaleza(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """INV-05. Devolver un gasto produce un GASTO negativo."""
    original = crear_origen(servicio, servicio_efectos, contexto)
    resultado = servicio_devoluciones.devolver(
        contexto, datos_devolucion(original)
    )
    assert resultado.importe_delta == D("-45.0000")
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT tipo_efecto, importe_delta FROM gapto.hecho_efectos WHERE id = %s",
        (resultado.efecto_id,),
    ) == ("GASTO", D("-45.0000"))


def test_la_relacion_va_de_la_devolucion_al_original(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """F04-D030. Origen = hecho NUEVO; destino = hecho ORIGINAL reducido."""
    original = crear_origen(servicio, servicio_efectos, contexto)
    datos = datos_devolucion(original)
    servicio_devoluciones.devolver(contexto, datos)
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT hecho_origen_id, hecho_destino_id, tipo_relacion, "
        "       importe_relacionado FROM gapto.hecho_relaciones WHERE id = %s",
        (datos.relacion_id,),
    ) == (datos.hecho_id, original, "DEVOLUCION_DE", D("45.0000"))


def test_el_original_no_se_toca(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """Una devolucion no edita, no anula y no resta nada al original.

    El hecho anterior sigue siendo cierto: lo que cambia es que despues ocurrio
    otra cosa.
    """
    original = crear_origen(servicio, servicio_efectos, contexto)
    antes = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado, row_version, "
        "       (SELECT sum(importe_delta) FROM gapto.hecho_efectos "
        "          WHERE hecho_id = %s) "
        "FROM gapto.hechos_financieros WHERE id = %s",
        (original, original),
    )
    servicio_devoluciones.devolver(contexto, datos_devolucion(original))
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado, row_version, "
        "       (SELECT sum(importe_delta) FROM gapto.hecho_efectos "
        "          WHERE hecho_id = %s) "
        "FROM gapto.hechos_financieros WHERE id = %s",
        (original, original),
    ) == antes


def test_varias_devoluciones_parciales_hasta_agotar(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    contexto: ContextoOperacion,
) -> None:
    original = crear_origen(servicio, servicio_efectos, contexto)
    primera = servicio_devoluciones.devolver(
        contexto, datos_devolucion(original, importe=D("45.0000"))
    )
    segunda = servicio_devoluciones.devolver(
        contexto, datos_devolucion(original, importe=D("50.0000"))
    )
    tercera = servicio_devoluciones.devolver(
        contexto, datos_devolucion(original, importe=D("25.0000"))
    )
    assert primera.pendiente == D("75.0000")
    assert segunda.pendiente == D("25.0000")
    assert tercera.pendiente == D("0.0000")
    assert tercera.devuelto_acumulado == BRUTO


def test_devolucion_total(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    contexto: ContextoOperacion,
) -> None:
    original = crear_origen(servicio, servicio_efectos, contexto)
    resultado = servicio_devoluciones.devolver(
        contexto, datos_devolucion(original, importe=BRUTO)
    )
    assert resultado.pendiente == D("0.0000")
    assert resultado.importe_delta == -BRUTO


def test_varios_efectos_de_igual_naturaleza_y_mismo_signo_se_agregan(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    contexto: ContextoOperacion,
) -> None:
    """F04-D030. Dos efectos GASTO de 120 y 30 dan capacidad 150.

    No se escoge uno de los dos ni se reparte: la capacidad es su suma
    firmada, porque la relacion no puede apuntar a un efecto concreto.
    """
    original = crear_origen(
        servicio, servicio_efectos, contexto, segundo=D("30.0000")
    )
    resultado = servicio_devoluciones.devolver(
        contexto, datos_devolucion(original, importe=D("150.0000"))
    )
    assert resultado.capacidad == D("150.0000")
    assert resultado.pendiente == D("0.0000")


def test_devolucion_sin_movimiento_inmediato(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """El efecto economico puede preceder al dinero. No se fabrica caja."""
    original = crear_origen(servicio, servicio_efectos, contexto)
    resultado = servicio_devoluciones.devolver(
        contexto, datos_devolucion(original)
    )
    assert resultado.movimiento_id is None
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s",
        (resultado.hecho_id,),
    ) == (0,)


def test_devolucion_con_caja(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
) -> None:
    """El movimiento lleva signo CONTRARIO al efecto: efecto negativo y
    entrada de dinero."""
    original = crear_origen(servicio, servicio_efectos, contexto)
    datos = datos_devolucion(
        original,
        movimiento_id=uuid.uuid4(),
        conciliacion_id=uuid.uuid4(),
        cuenta_id=cuenta,
        fecha_movimiento=F("2027-05-22"),
    )
    servicio_devoluciones.devolver(contexto, datos)
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT importe FROM gapto.movimientos_tesoreria WHERE id = %s), "
        "       (SELECT importe_asignado FROM gapto.hecho_movimientos_tesoreria "
        "          WHERE id = %s)",
        (datos.movimiento_id, datos.conciliacion_id),
    ) == (D("45.0000"), D("45.0000"))


def test_devolver_un_ingreso_produce_ingreso_negativo(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    contexto: ContextoOperacion,
) -> None:
    """La simetria tambien se cumple al reves: devolver un ingreso no produce
    un gasto."""
    original = crear_origen(
        servicio,
        servicio_efectos,
        contexto,
        tipo_efecto="INGRESO",
        tipo_hecho="INGRESO",
    )
    resultado = servicio_devoluciones.devolver(
        contexto, datos_devolucion(original, tipo_efecto="INGRESO")
    )
    assert resultado.tipo_efecto == "INGRESO"
    assert resultado.importe_delta == D("-45.0000")


# ==================================================================
# Rechazos
# ==================================================================

def test_excede_la_capacidad(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    contexto: ContextoOperacion,
) -> None:
    original = crear_origen(servicio, servicio_efectos, contexto)
    servicio_devoluciones.devolver(
        contexto, datos_devolucion(original, importe=D("100.0000"))
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_devoluciones.devolver(
            contexto, datos_devolucion(original, importe=D("21.0000"))
        )
    assert excinfo.value.codigo is CodigoError.EXCEDE_CAPACIDAD_REVERSIBLE


def test_signos_mezclados_falla_cerrado(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    contexto: ContextoOperacion,
) -> None:
    """F04-D030. GASTO +120 y GASTO -30 no determinan una capacidad univoca.

    Agregarlos a 90 seria una respuesta plausible y equivocada: el modelo no
    sabe si el -30 ya fue una reduccion previa o parte de la base. Fallar
    cerrado es la unica salida que no inventa.
    """
    original = crear_origen(
        servicio, servicio_efectos, contexto, segundo=D("-30.0000")
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_devoluciones.devolver(contexto, datos_devolucion(original))
    assert (
        excinfo.value.codigo is CodigoError.CAPACIDAD_REVERSIBLE_NO_DEMOSTRABLE
    )


def test_intento_de_registrar_la_devolucion_como_ingreso(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    contexto: ContextoOperacion,
) -> None:
    original = crear_origen(servicio, servicio_efectos, contexto)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_devoluciones.devolver(
            contexto,
            datos_devolucion(original, tipo_efecto_devolucion="INGRESO"),
        )
    assert excinfo.value.codigo is CodigoError.INGRESO_NO_PERMITIDO


def test_naturaleza_ausente_en_el_original(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    contexto: ContextoOperacion,
) -> None:
    original = crear_origen(servicio, servicio_efectos, contexto)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_devoluciones.devolver(
            contexto, datos_devolucion(original, tipo_efecto="DEUDA")
        )
    assert excinfo.value.codigo is CodigoError.NATURALEZA_DISTINTA_DEL_ORIGEN


def test_multidivisa_sin_equivalencia(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    contexto: ContextoOperacion,
) -> None:
    """Acumular 45 USD contra una capacidad de 120 EUR seria un FX de 1:1."""
    original = crear_origen(servicio, servicio_efectos, contexto)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_devoluciones.devolver(
            contexto, datos_devolucion(original, moneda="USD")
        )
    assert (
        excinfo.value.codigo is CodigoError.DEVOLUCION_MULTIDIVISA_NO_DEMOSTRADA
    )


def test_original_anulado(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    original = crear_origen(servicio, servicio_efectos, contexto)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (original,),
    )
    servicio.anular_hecho(
        contexto,
        hecho_id=original,
        row_version_esperada=fila[0],
        motivo_anulacion="capturado por error",
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_devoluciones.devolver(contexto, datos_devolucion(original))
    assert excinfo.value.codigo is CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO


def test_original_inexistente(
    servicio_devoluciones: DevolucionesService, contexto: ContextoOperacion
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_devoluciones.devolver(contexto, datos_devolucion(uuid.uuid4()))
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


def test_cross_tenant(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    contexto: ContextoOperacion,
    otro_owner: uuid.UUID,
) -> None:
    original = crear_origen(servicio, servicio_efectos, contexto)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_devoluciones.devolver(
            ContextoOperacion.de_usuario(otro_owner), datos_devolucion(original)
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


def test_movimiento_sin_conciliacion_rechazado(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    contexto: ContextoOperacion,
    cuenta: uuid.UUID,
) -> None:
    original = crear_origen(servicio, servicio_efectos, contexto)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_devoluciones.devolver(
            contexto,
            datos_devolucion(
                original, movimiento_id=uuid.uuid4(), cuenta_id=cuenta
            ),
        )
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


# ==================================================================
# Idempotencia y unicidad logica de la relacion
# ==================================================================

def test_retry_idempotente(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    original = crear_origen(servicio, servicio_efectos, contexto)
    datos = datos_devolucion(original)
    primero = servicio_devoluciones.devolver(contexto, datos)
    segundo = servicio_devoluciones.devolver(contexto, datos)
    assert primero.idempotente is False
    assert segundo.idempotente is True
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_relaciones "
        "WHERE hecho_destino_id = %s AND tipo_relacion = 'DEVOLUCION_DE'",
        (original,),
    ) == (1,)


def test_misma_identidad_con_otra_porcion_es_conflicto(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    contexto: ContextoOperacion,
) -> None:
    original = crear_origen(servicio, servicio_efectos, contexto)
    primera = datos_devolucion(original)
    servicio_devoluciones.devolver(contexto, primera)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_devoluciones.devolver(
            contexto,
            datos_devolucion(
                original,
                hecho_id=primera.hecho_id,
                efecto_id=primera.efecto_id,
                relacion_id=primera.relacion_id,
                importe=D("10.0000"),
            ),
        )
    assert (
        excinfo.value.codigo
        is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION
    )


def test_una_sola_relacion_por_terna(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """F04-D028. Varias devoluciones parciales son hechos DESTINO distintos,
    de modo que cada una tiene su propia terna y no chocan entre si."""
    original = crear_origen(servicio, servicio_efectos, contexto)
    for importe in ("40.0000", "40.0000", "40.0000"):
        servicio_devoluciones.devolver(
            contexto, datos_devolucion(original, importe=D(importe))
        )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), count(DISTINCT hecho_origen_id) "
        "FROM gapto.hecho_relaciones WHERE hecho_destino_id = %s",
        (original,),
    ) == (3, 3)


# ==================================================================
# I1 — doble devolucion concurrente
# ==================================================================

def test_i1_dos_devoluciones_concurrentes_no_superan_la_capacidad(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """I1. Dos devoluciones compiten por la capacidad del mismo original.

    Cada una pide 100 sobre una capacidad de 120. Aqui NO hay red fisica: no
    existe constraint alguna sobre el acumulado devuelto. Si el servicio leyera
    lo ya devuelto sin haber bloqueado antes el hecho original, ambas verian
    cero, ambas calcularian 120 disponibles y el acumulado acabaria en 200 sin
    que nada lo impidiese.

    Por eso el oraculo mira las dos cosas: que exactamente una confirme y que
    el estado persistido no supere la capacidad. La segunda asercion es la que
    demuestra que el lock es la unica defensa.
    """
    original = crear_origen(servicio, servicio_efectos, contexto)
    barrera = threading.Barrier(2)
    resultados: list[object] = []
    cerrojo = threading.Lock()

    def intentar(_indice: int) -> None:
        barrera.wait()
        try:
            servicio_devoluciones.devolver(
                ContextoOperacion.de_usuario(contexto.owner_user_id),
                datos_devolucion(original, importe=D("100.0000")),
            )
            salida: object = "OK"
        except ErrorMotor as error:
            salida = error.codigo
        except Exception as error:
            salida = type(error).__name__
        with cerrojo:
            resultados.append(salida)

    hilos = [threading.Thread(target=intentar, args=(i,)) for i in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=60)

    assert resultados.count("OK") == 1, resultados
    assert CodigoError.EXCEDE_CAPACIDAD_REVERSIBLE in resultados, resultados

    devuelto = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT COALESCE(sum(abs(e.importe_delta)), 0) "
        "  FROM gapto.hecho_relaciones r "
        "  JOIN gapto.hechos_financieros d ON d.id = r.hecho_origen_id "
        "  JOIN gapto.hecho_efectos e ON e.hecho_id = d.id "
        " WHERE r.hecho_destino_id = %s AND r.tipo_relacion = 'DEVOLUCION_DE' "
        "   AND d.estado = 'ACTIVO'",
        (original,),
    )[0]
    assert decimal.Decimal(devuelto) <= BRUTO, (resultados, devuelto)


# ==================================================================
# F04-D033 — coexistencia OP-13 / OP-17
# ==================================================================

def _prevision_para(
    servicio_previsiones,
    contexto: ContextoOperacion,
    *,
    importe: decimal.Decimal,
    concepto: str,
) -> uuid.UUID:
    from app.core.modelos_prevision import DatosPrevisionManual

    prevision_id = uuid.uuid4()
    servicio_previsiones.crear_manual(
        contexto,
        DatosPrevisionManual(
            prevision_id=prevision_id,
            concepto=concepto,
            tipo_hecho_codigo="GASTO",
            fecha_esperada_desde=F("2027-05-01"),
            fecha_esperada_hasta=F("2027-05-31"),
            flujo_tesoreria_esperado="SALIDA",
            moneda="EUR",
            presupuestable=True,
            importe_esperado=importe,
        ),
    )
    return prevision_id


def _materializar(
    servicio_previsiones,
    contexto: ContextoOperacion,
    prevision_id: uuid.UUID,
    hecho_id: uuid.UUID,
    importe: decimal.Decimal,
) -> uuid.UUID:
    from app.core.modelos_prevision import DatosVinculo

    vinculo_id = uuid.uuid4()
    estado = servicio_previsiones.estado_de(contexto, prevision_id)
    servicio_previsiones.vincular_realidad(
        contexto,
        prevision_id=prevision_id,
        row_version_esperada=estado.row_version,
        datos=DatosVinculo(
            vinculo_id=vinculo_id,
            hecho_id=hecho_id,
            importe_asignado=importe,
            marcar_realizada=True,
        ),
    )
    return vinculo_id


def test_d033_la_devolucion_no_desmaterializa_la_prevision_del_original(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    servicio_previsiones,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """F04-D033. El gasto ocurrio, satisfizo una expectativa, y DESPUES hubo
    una devolucion.

    Que el original materializara correctamente una previsión sigue siendo
    cierto. OP-13 no elimina `prevision_hechos`, no desmaterializa la previsión
    y no reasigna OP-17: la devolucion es otro hecho real, no una correccion
    del anterior.
    """
    original = crear_origen(servicio, servicio_efectos, contexto)
    prevision_id = _prevision_para(
        servicio_previsiones, contexto, importe=BRUTO, concepto="Compra prevista"
    )
    vinculo_id = _materializar(
        servicio_previsiones, contexto, prevision_id, original, BRUTO
    )

    resultado = servicio_devoluciones.devolver(
        contexto, datos_devolucion(original)
    )
    assert resultado.previsiones_del_original == 1

    # El vinculo sigue ahi, con su importe y apuntando al mismo hecho.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT hecho_id, importe_asignado FROM gapto.prevision_hechos "
        "WHERE id = %s",
        (vinculo_id,),
    ) == (original, BRUTO)
    # Y la previsión sigue REALIZADA.
    assert servicio_previsiones.estado_de(contexto, prevision_id).estado == "REALIZADA"


def test_d033_la_devolucion_puede_materializar_su_propia_prevision(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    servicio_previsiones,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """Una devolucion esperada es una expectativa propia.

    Se materializa con SU OP-17, no reasignando el del original. Al final
    coexisten dos previsiones REALIZADAS y dos hechos reales, sin que ninguno
    haya perdido nada.
    """
    original = crear_origen(servicio, servicio_efectos, contexto)
    prevision_original = _prevision_para(
        servicio_previsiones, contexto, importe=BRUTO, concepto="Compra"
    )
    _materializar(
        servicio_previsiones, contexto, prevision_original, original, BRUTO
    )

    devolucion = servicio_devoluciones.devolver(
        contexto, datos_devolucion(original)
    )
    prevision_devolucion = _prevision_para(
        servicio_previsiones,
        contexto,
        importe=D("45.0000"),
        concepto="Devolucion esperada",
    )
    _materializar(
        servicio_previsiones,
        contexto,
        prevision_devolucion,
        devolucion.hecho_id,
        D("45.0000"),
    )

    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), count(DISTINCT hecho_id), count(DISTINCT prevision_id) "
        "  FROM gapto.prevision_hechos pv "
        "  JOIN gapto.hechos_financieros h ON h.id = pv.hecho_id "
        " WHERE h.owner_user_id = %s",
        (contexto.owner_user_id,),
    ) == (2, 2, 2)
    for hecho_id in (original, devolucion.hecho_id):
        assert leer_fila(
            admin,
            contexto.owner_user_id,
            "SELECT estado FROM gapto.hechos_financieros WHERE id = %s",
            (hecho_id,),
        ) == ("ACTIVO",)


def test_i7_devolucion_y_materializacion_concurrentes_coexisten(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    servicio_previsiones,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """I7. Las dos operaciones son legitimas y deben poder coexistir.

    Un hilo materializa la previsión con el hecho original; el otro registra
    una devolucion de ese mismo hecho. El oraculo NO puede ser que una falle:
    ambas describen realidades ciertas y distintas.

    Lo que se exige es que las DOS confirmen, que no haya doble creacion —un
    vinculo y una relacion, ni mas ni menos—, que no haya doble conteo del
    acumulado devuelto, y que ninguna de las dos realidades se pierda.
    """
    original = crear_origen(servicio, servicio_efectos, contexto)
    prevision_id = _prevision_para(
        servicio_previsiones, contexto, importe=BRUTO, concepto="Compra"
    )
    datos = datos_devolucion(original)
    barrera = threading.Barrier(2)
    resultados: list[object] = []
    cerrojo = threading.Lock()

    def intentar(indice: int) -> None:
        propio = ContextoOperacion.de_usuario(contexto.owner_user_id)
        barrera.wait()
        try:
            if indice == 0:
                _materializar(
                    servicio_previsiones, propio, prevision_id, original, BRUTO
                )
            else:
                servicio_devoluciones.devolver(propio, datos)
            salida: object = "OK"
        except ErrorMotor as error:
            salida = error.codigo
        except Exception as error:
            salida = type(error).__name__
        with cerrojo:
            resultados.append(salida)

    hilos = [threading.Thread(target=intentar, args=(i,)) for i in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=60)

    # Ninguna falla por principio.
    assert resultados == ["OK", "OK"], resultados

    # Ni doble creacion ni doble conteo.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT count(*) FROM gapto.prevision_hechos WHERE hecho_id = %s), "
        "       (SELECT count(*) FROM gapto.hecho_relaciones "
        "          WHERE hecho_destino_id = %s "
        "            AND tipo_relacion = 'DEVOLUCION_DE'), "
        "       (SELECT estado FROM gapto.hechos_financieros WHERE id = %s)",
        (original, original, original),
    ) == (1, 1, "ACTIVO")

    # Las dos realidades siguen vivas.
    assert servicio_previsiones.estado_de(contexto, prevision_id).estado == "REALIZADA"
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado FROM gapto.hechos_financieros WHERE id = %s",
        (datos.hecho_id,),
    ) == ("ACTIVO",)
