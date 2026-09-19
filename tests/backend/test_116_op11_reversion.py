# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_116_op11_reversion.py
# Ruta: tests/backend/test_116_op11_reversion.py
# Descripcion: F04-06 / B2. OP-11 reversion de tesoreria.
#
#   LA PROPIEDAD CENTRAL: una reversion de tesoreria NO es una devolucion y NO
#   es una correccion. No crea hecho, ni efecto, ni `hecho_relaciones`, ni
#   transferencia inversa. El acontecimiento economico original sigue siendo
#   cierto; lo que se deshizo es el apunte bancario.
#
#   Y la consecuencia menos evidente: revertir una o las dos patas de una
#   transferencia NO reescribe la fila `transferencias`. Esa fila describe la
#   pareja de movimientos que realmente existio, y una reversion posterior no
#   la invalida historicamente. Cobertura revertida y posicion neta son
#   conclusiones DERIVADAS.
#
#   Garantias fisicas consumidas y verificadas aqui por conducta:
#   D-099/0220 same-account · D-133/0280 profundidad 1 en ambos sentidos ·
#   signo contrario · suma de reversiones ACTIVAS <= original · D-119/T6.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid

import psycopg
import pytest

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos_tesoreria import DatosMovimiento, DatosReversion
from app.core.modelos_transferencia import DatosTransferencia
from app.services.tesoreria_service import TesoreriaService
from app.services.transferencias_service import TransferenciasService
from conftest import leer_fila

D = decimal.Decimal
F = dt.date.fromisoformat

CARGO = D("-100.0000")


def crear_movimiento(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    cuenta_id: uuid.UUID,
    importe: decimal.Decimal = CARGO,
    clase: str = "OPERACION",
) -> uuid.UUID:
    movimiento_id = uuid.uuid4()
    servicio_tesoreria.registrar_movimiento(
        contexto,
        DatosMovimiento(
            movimiento_id=movimiento_id,
            cuenta_id=cuenta_id,
            fecha_movimiento=F("2027-04-01"),
            importe=importe,
            clase_movimiento=clase,
        ),
    )
    return movimiento_id


def reversion(
    original_id: uuid.UUID, cuenta_id: uuid.UUID, importe: str, **extra
) -> DatosReversion:
    base = {
        "reversion_id": uuid.uuid4(),
        "movimiento_original_id": original_id,
        "cuenta_id": cuenta_id,
        "fecha_movimiento": F("2027-04-05"),
        "importe": D(importe),
    }
    base.update(extra)
    return DatosReversion(**base)


# ==================================================================
# Camino correcto
# ==================================================================

def test_reversion_total(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
) -> None:
    original = crear_movimiento(servicio_tesoreria, contexto, cuenta)
    resultado = servicio_tesoreria.revertir_movimiento(
        contexto, reversion(original, cuenta, "100.0000")
    )
    assert resultado.importe == D("100.0000")
    assert resultado.pendiente == D("0.0000")
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe, reversion_de_movimiento_id, estado "
        "FROM gapto.movimientos_tesoreria WHERE id = %s",
        (resultado.reversion_id,),
    ) == (D("100.0000"), original, "ACTIVO")


def test_el_signo_lo_pone_el_motor_desde_el_original(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
) -> None:
    """Revertir un ingreso produce un cargo, y al reves."""
    ingreso = crear_movimiento(servicio_tesoreria, contexto, cuenta, D("250.0000"))
    resultado = servicio_tesoreria.revertir_movimiento(
        contexto, reversion(ingreso, cuenta, "250.0000")
    )
    assert resultado.importe == D("-250.0000")


def test_reversion_parcial_y_multiples_dentro_del_limite(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    cuenta: uuid.UUID,
) -> None:
    original = crear_movimiento(servicio_tesoreria, contexto, cuenta)
    primera = servicio_tesoreria.revertir_movimiento(
        contexto, reversion(original, cuenta, "40.0000")
    )
    segunda = servicio_tesoreria.revertir_movimiento(
        contexto, reversion(original, cuenta, "35.0000")
    )
    assert primera.revertido_acumulado == D("40.0000")
    assert primera.pendiente == D("60.0000")
    assert segunda.revertido_acumulado == D("75.0000")
    assert segunda.pendiente == D("25.0000")


def test_la_reversion_conserva_la_clase_del_original(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
) -> None:
    """Revertir un AJUSTE_SALDO no lo convierte en una operacion ordinaria.

    Las dos clases describen cosas distintas: una corrige un saldo y la otra
    registra dinero que se movio. Heredar siempre OPERACION reescribiria la
    naturaleza del apunte al deshacerlo.
    """
    original = crear_movimiento(
        servicio_tesoreria, contexto, cuenta, CARGO, clase="AJUSTE_SALDO"
    )
    resultado = servicio_tesoreria.revertir_movimiento(
        contexto, reversion(original, cuenta, "100.0000")
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT clase_movimiento FROM gapto.movimientos_tesoreria WHERE id = %s",
        (resultado.reversion_id,),
    ) == ("AJUSTE_SALDO",)


def test_no_crea_realidad_economica(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
) -> None:
    """Ni hecho, ni efecto, ni relacion. Solo un apunte bancario mas."""
    original = crear_movimiento(servicio_tesoreria, contexto, cuenta)
    servicio_tesoreria.revertir_movimiento(
        contexto, reversion(original, cuenta, "100.0000")
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT count(*) FROM gapto.hechos_financieros "
        "          WHERE owner_user_id = %s), "
        "       (SELECT count(*) FROM gapto.hecho_relaciones r "
        "          JOIN gapto.hechos_financieros h ON h.id = r.hecho_origen_id "
        "         WHERE h.owner_user_id = %s)",
        (contexto.owner_user_id, contexto.owner_user_id),
    ) == (0, 0)


def test_la_reversion_no_se_concilia_con_el_hecho_del_original(
    servicio_tesoreria: TesoreriaService,
    servicio_transferencias: TransferenciasService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
) -> None:
    """Conciliarla reduciria la porcion asignada y reescribiria hacia atras
    una realidad economica que nadie ha negado."""
    datos = DatosTransferencia(
        transferencia_id=uuid.uuid4(),
        hecho_id=uuid.uuid4(),
        movimiento_salida_id=uuid.uuid4(),
        movimiento_entrada_id=uuid.uuid4(),
        conciliacion_salida_id=uuid.uuid4(),
        conciliacion_entrada_id=uuid.uuid4(),
        cuenta_origen_id=cuenta,
        cuenta_destino_id=cuenta_destino,
        fecha_hecho=F("2027-04-01"),
        fecha_movimiento=F("2027-04-01"),
        moneda="EUR",
        importe_salida=D("100.0000"),
        importe_entrada=D("100.0000"),
    )
    servicio_transferencias.transferir(contexto, datos)
    resultado = servicio_tesoreria.revertir_movimiento(
        contexto, reversion(datos.movimiento_salida_id, cuenta, "100.0000")
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT count(*) FROM gapto.hecho_movimientos_tesoreria "
        "          WHERE movimiento_tesoreria_id = %s), "
        "       (SELECT count(*) FROM gapto.hecho_movimientos_tesoreria "
        "          WHERE hecho_id = %s)",
        (resultado.reversion_id, datos.hecho_id),
    ) == (0, 2)


# ==================================================================
# Rechazos
# ==================================================================

def test_excede_el_importe_original(
    servicio_tesoreria: TesoreriaService, contexto, cuenta
) -> None:
    original = crear_movimiento(servicio_tesoreria, contexto, cuenta)
    servicio_tesoreria.revertir_movimiento(
        contexto, reversion(original, cuenta, "80.0000")
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.revertir_movimiento(
            contexto, reversion(original, cuenta, "21.0000")
        )
    assert excinfo.value.codigo is CodigoError.EXCEDE_IMPORTE_ORIGINAL


def test_cuenta_distinta(
    servicio_tesoreria: TesoreriaService, contexto, cuenta, cuenta_destino
) -> None:
    """Devolver el dinero a otra cuenta es una transferencia, no una
    reversion. Autoridad fisica: FK compuesta de 0220 (D-099)."""
    original = crear_movimiento(servicio_tesoreria, contexto, cuenta)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.revertir_movimiento(
            contexto, reversion(original, cuenta_destino, "50.0000")
        )
    assert excinfo.value.codigo is CodigoError.CUENTA_DISTINTA


def test_autorreversion(
    servicio_tesoreria: TesoreriaService, contexto, cuenta
) -> None:
    original = crear_movimiento(servicio_tesoreria, contexto, cuenta)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.revertir_movimiento(
            contexto, reversion(original, cuenta, "50.0000", reversion_id=original)
        )
    assert excinfo.value.codigo is CodigoError.AUTORREVERSION


def test_reversion_de_reversion(
    servicio_tesoreria: TesoreriaService, contexto, cuenta
) -> None:
    """Profundidad maxima 1 (D-133 / 0280)."""
    original = crear_movimiento(servicio_tesoreria, contexto, cuenta)
    primera = servicio_tesoreria.revertir_movimiento(
        contexto, reversion(original, cuenta, "50.0000")
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.revertir_movimiento(
            contexto, reversion(primera.reversion_id, cuenta, "20.0000")
        )
    assert excinfo.value.codigo is CodigoError.REVERSION_DE_REVERSION


def test_original_anulado(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
) -> None:
    """Si nunca existio, no hay nada que deshacer."""
    original = crear_movimiento(servicio_tesoreria, contexto, cuenta)
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        cursor.execute(
            "SELECT set_config('gapto.owner_user_id', %s, false)",
            (str(contexto.owner_user_id),),
        )
        cursor.execute(
            "UPDATE gapto.movimientos_tesoreria SET estado = 'ANULADO', "
            "anulado_at = CURRENT_TIMESTAMP WHERE id = %s",
            (original,),
        )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.revertir_movimiento(
            contexto, reversion(original, cuenta, "50.0000")
        )
    assert excinfo.value.codigo is CodigoError.ORIGINAL_ANULADO


def test_magnitud_negativa(
    servicio_tesoreria: TesoreriaService, contexto, cuenta
) -> None:
    original = crear_movimiento(servicio_tesoreria, contexto, cuenta)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.revertir_movimiento(
            contexto, reversion(original, cuenta, "-50.0000")
        )
    assert excinfo.value.codigo is CodigoError.SIGNOS_INCORRECTOS


def test_original_inexistente(
    servicio_tesoreria: TesoreriaService, contexto, cuenta
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.revertir_movimiento(
            contexto, reversion(uuid.uuid4(), cuenta, "50.0000")
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


def test_cross_tenant(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    otro_owner: uuid.UUID,
    cuenta: uuid.UUID,
) -> None:
    original = crear_movimiento(servicio_tesoreria, contexto, cuenta)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.revertir_movimiento(
            ContextoOperacion.de_usuario(otro_owner),
            reversion(original, cuenta, "50.0000"),
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


# ==================================================================
# Deshacer una reversion
# ==================================================================

def test_deshacer_una_reversion_es_un_movimiento_ordinario(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
) -> None:
    """No se encadena `reversion_de_movimiento_id`.

    Una cadena R1 -> R2 -> R3 produce un neto que nadie puede leer. El
    movimiento que deshace una reversion es ordinario y no enlaza con ella.
    """
    original = crear_movimiento(servicio_tesoreria, contexto, cuenta)
    primera = servicio_tesoreria.revertir_movimiento(
        contexto, reversion(original, cuenta, "100.0000")
    )
    ordinario = crear_movimiento(servicio_tesoreria, contexto, cuenta, CARGO)
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT reversion_de_movimiento_id FROM gapto.movimientos_tesoreria "
        "WHERE id = %s",
        (ordinario,),
    ) == (None,)
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT reversion_de_movimiento_id FROM gapto.movimientos_tesoreria "
        "WHERE id = %s",
        (primera.reversion_id,),
    ) == (original,)


# ==================================================================
# Reversion de patas de transferencia
# ==================================================================

def transferencia_de(
    servicio_transferencias: TransferenciasService,
    contexto: ContextoOperacion,
    origen: uuid.UUID,
    destino: uuid.UUID,
) -> DatosTransferencia:
    datos = DatosTransferencia(
        transferencia_id=uuid.uuid4(),
        hecho_id=uuid.uuid4(),
        movimiento_salida_id=uuid.uuid4(),
        movimiento_entrada_id=uuid.uuid4(),
        conciliacion_salida_id=uuid.uuid4(),
        conciliacion_entrada_id=uuid.uuid4(),
        cuenta_origen_id=origen,
        cuenta_destino_id=destino,
        fecha_hecho=F("2027-04-01"),
        fecha_movimiento=F("2027-04-01"),
        moneda="EUR",
        importe_salida=D("100.0000"),
        importe_entrada=D("100.0000"),
    )
    servicio_transferencias.transferir(contexto, datos)
    return datos


def test_revertir_una_pata_no_reescribe_la_transferencia(
    servicio_tesoreria: TesoreriaService,
    servicio_transferencias: TransferenciasService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
) -> None:
    """La fila `transferencias` describe la pareja que realmente existio.

    Revertir una pata no la invalida historicamente, no crea REVERSA_A y no
    genera transferencia inversa. Lo que queda es una cobertura parcial, que
    es conclusion derivada.
    """
    datos = transferencia_de(
        servicio_transferencias, contexto, cuenta, cuenta_destino
    )
    servicio_tesoreria.revertir_movimiento(
        contexto, reversion(datos.movimiento_salida_id, cuenta, "100.0000")
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT movimiento_salida_id, movimiento_entrada_id "
        "FROM gapto.transferencias WHERE id = %s",
        (datos.transferencia_id,),
    ) == (datos.movimiento_salida_id, datos.movimiento_entrada_id)
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_relaciones r "
        "JOIN gapto.hechos_financieros h ON h.id = r.hecho_origen_id "
        "WHERE h.owner_user_id = %s",
        (contexto.owner_user_id,),
    ) == (0,)


def test_revertir_ambas_patas_no_crea_transferencia_inversa(
    servicio_tesoreria: TesoreriaService,
    servicio_transferencias: TransferenciasService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
) -> None:
    """El acontecimiento se deshizo, no ocurrio uno nuevo.

    Sigue habiendo UNA transferencia, el hecho original sigue ACTIVO y la
    liquidez neta vuelve a cero por suma de movimientos, no por haber
    reescrito nada.
    """
    datos = transferencia_de(
        servicio_transferencias, contexto, cuenta, cuenta_destino
    )
    servicio_tesoreria.revertir_movimiento(
        contexto, reversion(datos.movimiento_salida_id, cuenta, "100.0000")
    )
    servicio_tesoreria.revertir_movimiento(
        contexto,
        reversion(datos.movimiento_entrada_id, cuenta_destino, "100.0000"),
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT count(*) FROM gapto.transferencias t "
        "          JOIN gapto.movimientos_tesoreria m "
        "            ON m.id = t.movimiento_salida_id "
        "          JOIN gapto.cuentas c ON c.id = m.cuenta_id "
        "         WHERE c.owner_user_id = %s), "
        "       (SELECT estado FROM gapto.hechos_financieros WHERE id = %s)",
        (contexto.owner_user_id, datos.hecho_id),
    ) == (1, "ACTIVO")

    for cuenta_id in (cuenta, cuenta_destino):
        assert leer_fila(
            admin,
            contexto.owner_user_id,
            "SELECT COALESCE(sum(importe), 0) FROM gapto.movimientos_tesoreria "
            "WHERE cuenta_id = %s AND estado = 'ACTIVO'",
            (cuenta_id,),
        ) == (D("0.0000"),)


# ==================================================================
# Idempotencia
# ==================================================================

def test_retry_idempotente(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
) -> None:
    original = crear_movimiento(servicio_tesoreria, contexto, cuenta)
    datos = reversion(original, cuenta, "60.0000")
    primero = servicio_tesoreria.revertir_movimiento(contexto, datos)
    segundo = servicio_tesoreria.revertir_movimiento(contexto, datos)
    assert primero.idempotente is False
    assert segundo.idempotente is True
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.movimientos_tesoreria "
        "WHERE reversion_de_movimiento_id = %s",
        (original,),
    ) == (1,)


def test_misma_identidad_con_otro_importe_es_conflicto(
    servicio_tesoreria: TesoreriaService, contexto, cuenta
) -> None:
    """La identidad de una reversion es a que original apunta y por cuanto."""
    original = crear_movimiento(servicio_tesoreria, contexto, cuenta)
    primera = reversion(original, cuenta, "60.0000")
    servicio_tesoreria.revertir_movimiento(contexto, primera)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_tesoreria.revertir_movimiento(
            contexto,
            reversion(
                original, cuenta, "30.0000", reversion_id=primera.reversion_id
            ),
        )
    assert (
        excinfo.value.codigo
        is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION
    )


# ==================================================================
# Concurrencia
# ==================================================================

def test_dos_reversiones_concurrentes_no_superan_el_original(
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
) -> None:
    """Interleaving: dos reversiones compiten por lo que queda por revertir.

    Cada una pide 60 sobre un original de 100. Si el acumulado se leyera SIN
    haber bloqueado antes el original, ambas verian cero revertido, ambas
    calcularian 100 disponibles y la suma acabaria en 120.

    El desenlace legitimo es que confirme UNA y la otra falle con el error de
    dominio EXCEDE_IMPORTE_ORIGINAL. Esa segunda parte es la que discrimina:
    sin el lock ambas leen cero revertido, ambas insertan, y quien rechaza es
    el trigger diferido al COMMIT. El resultado final seguiria siendo correcto
    —la suma no supera el original— pero el llamante recibiria un fallo
    tecnico traducido a una invariante fisica en vez del error de su contrato.
    El mandato prohibe exponer garantias de PostgreSQL como contrato externo,
    de modo que el lock del servicio no es una optimizacion: es lo que hace
    que el conflicto tenga nombre.
    """
    import threading

    original = crear_movimiento(servicio_tesoreria, contexto, cuenta)
    barrera = threading.Barrier(2)
    resultados: list[object] = []
    cerrojo = threading.Lock()

    def intentar(_indice: int) -> None:
        barrera.wait()
        try:
            servicio_tesoreria.revertir_movimiento(
                ContextoOperacion.de_usuario(contexto.owner_user_id),
                reversion(original, cuenta, "60.0000"),
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

    # Estado persistido: la suma nunca supera el original.
    revertido = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT COALESCE(sum(abs(importe)), 0) FROM gapto.movimientos_tesoreria "
        "WHERE reversion_de_movimiento_id = %s AND estado = 'ACTIVO'",
        (original,),
    )[0]
    assert decimal.Decimal(revertido) <= D("100.0000"), (resultados, revertido)

    # Contrato externo: exactamente una confirma y la otra falla con SU error.
    assert resultados.count("OK") == 1, resultados
    assert CodigoError.EXCEDE_IMPORTE_ORIGINAL in resultados, resultados
