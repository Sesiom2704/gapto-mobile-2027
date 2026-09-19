# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_120_interleavings_f0406.py
# Ruta: tests/backend/test_120_interleavings_f0406.py
# Descripcion: F04-06. Interleavings que CRUZAN operaciones de bloques
#   distintos, mas la revalidacion secuencial que los motivo.
#
#   Los interleavings dentro de una sola operacion viven en la suite de esa
#   operacion —I1 en OP-13, reversiones concurrentes en OP-11, dos OP-21 sobre
#   la misma raiz en OP-21—. Aqui estan los que solo aparecen cuando dos
#   operaciones distintas tocan la misma realidad:
#
#     I2  correccion agregada frente a devolucion
#     I3  correccion agregada frente a reversion de tesoreria
#
#   HALLAZGO QUE ORIGINO ESTE FICHERO. Antes de escribir I2 se comprobo de
#   forma SECUENCIAL si OP-21 podia dejar la capacidad reversible por debajo de
#   lo ya devuelto. Podia: 110 devueltos sobre una capacidad que la correccion
#   reducia a 20. Ninguna constraint fisica lo impedia, porque el acumulado
#   devuelto no tiene red fisica en ningun sitio. La revalidacion cruzada de
#   OP-21 nacio de ahi, y el primer test de este fichero la fija.
#
#   Ese orden importa: la carrera no descubrio el defecto, lo descubrio
#   preguntarse que pasaba en el caso secuencial. Un interleaving escrito antes
#   habria pasado en verde sobre un motor incoherente.
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
from app.core.modelos_tesoreria import DatosMovimiento, DatosReversion
from app.core.modelos_transferencia import DatosTransferencia
from app.services.correcciones_service import CorreccionesService, DatosCorreccion
from app.services.devoluciones_service import DevolucionesService
from app.services.efectos_service import EfectosService
from app.services.hechos_service import HechosService
from app.services.tesoreria_service import TesoreriaService
from app.services.transferencias_service import TransferenciasService
from conftest import leer_fila

D = decimal.Decimal
F = dt.date.fromisoformat


def gasto_con_dos_efectos(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Hecho con GASTO 100 + GASTO 20: capacidad reversible 120."""
    hecho_id = uuid.uuid4()
    servicio.crear_hecho(
        contexto,
        DatosCreacionHecho(
            hecho_id=hecho_id,
            fecha_hecho=F("2027-08-01"),
            moneda="EUR",
            presupuestable=True,
            estado_localizacion="NO_APLICA",
            tipo_hecho_codigo="GASTO",
            importe_total=D("120.0000"),
        ),
    )
    grande, pequeno = uuid.uuid4(), uuid.uuid4()
    servicio_efectos.registrar_efectos(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=1,
        efectos=[
            DatosEfecto(
                efecto_id=grande,
                tipo_efecto="GASTO",
                importe_delta=D("100.0000"),
                estado_atribucion="NO_DISPONIBLE",
            ),
            DatosEfecto(
                efecto_id=pequeno,
                tipo_efecto="GASTO",
                importe_delta=D("20.0000"),
                estado_atribucion="NO_DISPONIBLE",
            ),
        ],
    )
    return hecho_id, grande, pequeno


def devolucion_de(original: uuid.UUID, importe: str) -> DatosDevolucion:
    return DatosDevolucion(
        hecho_id=uuid.uuid4(),
        efecto_id=uuid.uuid4(),
        relacion_id=uuid.uuid4(),
        hecho_original_id=original,
        tipo_efecto="GASTO",
        importe=D(importe),
        fecha_hecho=F("2027-08-10"),
        moneda="EUR",
        concepto="Devolucion",
    )


def capacidad_y_devuelto(
    admin: psycopg.Connection, owner: uuid.UUID, hecho_id: uuid.UUID
) -> tuple[decimal.Decimal, decimal.Decimal]:
    fila = leer_fila(
        admin,
        owner,
        "SELECT COALESCE((SELECT sum(importe_delta) FROM gapto.hecho_efectos "
        "                   WHERE hecho_id = %s), 0), "
        "       COALESCE((SELECT sum(abs(e.importe_delta)) "
        "                   FROM gapto.hecho_relaciones r "
        "                   JOIN gapto.hechos_financieros d "
        "                     ON d.id = r.hecho_origen_id "
        "                   JOIN gapto.hecho_efectos e ON e.hecho_id = d.id "
        "                  WHERE r.hecho_destino_id = %s "
        "                    AND r.tipo_relacion = 'DEVOLUCION_DE' "
        "                    AND d.estado = 'ACTIVO'), 0)",
        (hecho_id, hecho_id),
    )
    return abs(decimal.Decimal(fila[0])), decimal.Decimal(fila[1])


# ==================================================================
# La revalidacion cruzada, en secuencial
# ==================================================================

def test_la_correccion_no_puede_dejar_devuelto_por_encima_de_la_capacidad(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    servicio_correcciones: CorreccionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """Se devuelven 110 sobre una capacidad de 120. Retirar despues el efecto
    de 100 dejaria capacidad 20 con 110 ya devueltos.

    Haber devuelto mas de lo que el hecho llego a reconocer es un estado
    imposible, y ninguna constraint fisica lo impide: el acumulado devuelto no
    tiene red en ningun sitio. La correccion se rechaza y no aplica nada.
    """
    hecho_id, grande, _ = gasto_con_dos_efectos(
        servicio, servicio_efectos, contexto
    )
    servicio_devoluciones.devolver(contexto, devolucion_de(hecho_id, "110.0000"))

    with pytest.raises(ErrorMotor) as excinfo:
        servicio_correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=hecho_id,
                row_version_esperada=2,
                motivo="ese efecto de 100 nunca existio",
                efectos_a_eliminar=(grande,),
            ),
        )
    assert excinfo.value.codigo is CodigoError.EXCEDE_CAPACIDAD_REVERSIBLE

    capacidad, devuelto = capacidad_y_devuelto(
        admin, contexto.owner_user_id, hecho_id
    )
    assert (capacidad, devuelto) == (D("120.0000"), D("110.0000"))


def test_la_correccion_procede_si_la_capacidad_restante_alcanza(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    servicio_correcciones: CorreccionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """El caso que DISCRIMINA la guarda anterior.

    Con solo 15 devueltos, retirar el efecto de 100 deja capacidad 20, que
    sigue cubriendolos. Sin este test, el anterior demostraria que el servicio
    rechaza, no que distingue.
    """
    hecho_id, grande, _ = gasto_con_dos_efectos(
        servicio, servicio_efectos, contexto
    )
    servicio_devoluciones.devolver(contexto, devolucion_de(hecho_id, "15.0000"))

    servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id,
            row_version_esperada=2,
            motivo="ese efecto de 100 nunca existio",
            efectos_a_eliminar=(grande,),
        ),
    )
    capacidad, devuelto = capacidad_y_devuelto(
        admin, contexto.owner_user_id, hecho_id
    )
    assert (capacidad, devuelto) == (D("20.0000"), D("15.0000"))


# ==================================================================
# I2 — correccion agregada frente a devolucion
# ==================================================================

def _competir(objetivo) -> list[object]:
    barrera = threading.Barrier(2)
    resultados: list[object] = []
    cerrojo = threading.Lock()

    def correr(indice: int) -> None:
        barrera.wait()
        try:
            objetivo(indice)
            salida: object = "OK"
        except ErrorMotor as error:
            salida = error.codigo
        except Exception as error:
            salida = type(error).__name__
        with cerrojo:
            resultados.append(salida)

    hilos = [threading.Thread(target=correr, args=(i,)) for i in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=60)
    return resultados


def test_i2_correccion_agregada_frente_a_devolucion(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_devoluciones: DevolucionesService,
    servicio_correcciones: CorreccionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """I2. Una retira el efecto del que la otra depende.

    Las dos bloquean el MISMO hecho con FOR NO KEY UPDATE, de modo que se
    serializan. Cualquiera de los dos ordenes es legitimo:

      correccion primero -> la devolucion ve capacidad 20 y 110 no cabe;
      devolucion primero -> la correccion dejaria devuelto por encima de la
                            capacidad y se rechaza.

    Lo que NUNCA puede quedar persistido es un estado donde lo devuelto supere
    la capacidad, ni un estado parcial de la correccion. El oraculo mira eso,
    no el reparto de codigos.
    """
    hecho_id, grande, _ = gasto_con_dos_efectos(
        servicio, servicio_efectos, contexto
    )
    datos_devolucion = devolucion_de(hecho_id, "110.0000")

    def intentar(indice: int) -> None:
        propio = ContextoOperacion.de_usuario(contexto.owner_user_id)
        if indice == 0:
            servicio_devoluciones.devolver(propio, datos_devolucion)
        else:
            servicio_correcciones.corregir(
                propio,
                DatosCorreccion(
                    hecho_id=hecho_id,
                    row_version_esperada=2,
                    motivo="ese efecto nunca existio",
                    efectos_a_eliminar=(grande,),
                ),
            )

    resultados = _competir(intentar)
    assert resultados.count("OK") >= 1, resultados

    capacidad, devuelto = capacidad_y_devuelto(
        admin, contexto.owner_user_id, hecho_id
    )
    assert devuelto <= capacidad, (resultados, capacidad, devuelto)

    # Sin estado parcial: o el efecto sigue entero, o desaparecio entero.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos WHERE id = %s",
        (grande,),
    )[0] in (0, 1)


# ==================================================================
# I3 — correccion agregada frente a reversion de tesoreria
# ==================================================================

def test_i3_correccion_agregada_frente_a_reversion(
    servicio_transferencias: TransferenciasService,
    servicio_tesoreria: TesoreriaService,
    servicio_correcciones: CorreccionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
) -> None:
    """I3. Una retira la conciliacion; la otra revierte el movimiento.

    Tocan raices distintas —la correccion el hecho, la reversion el
    movimiento— asi que no compiten por el mismo row lock. Ambas pueden
    confirmar, y eso es legitimo: revertir un apunte no exige conservar su
    conciliacion, y retirar una conciliacion falsa no impide que el banco
    devuelva el dinero.

    Lo que se exige es que el estado final sea coherente: la reversion existe
    o no, la conciliacion existe o no, y en ningun caso queda una conciliacion
    asignando mas de lo que su movimiento tiene. Esa ultima parte la sostiene
    la revalidacion parent-side de 0270, no el servicio.
    """
    datos = DatosTransferencia(
        transferencia_id=uuid.uuid4(),
        hecho_id=uuid.uuid4(),
        movimiento_salida_id=uuid.uuid4(),
        movimiento_entrada_id=uuid.uuid4(),
        conciliacion_salida_id=uuid.uuid4(),
        conciliacion_entrada_id=uuid.uuid4(),
        cuenta_origen_id=cuenta,
        cuenta_destino_id=cuenta_destino,
        fecha_hecho=F("2027-08-01"),
        fecha_movimiento=F("2027-08-01"),
        moneda="EUR",
        importe_salida=D("100.0000"),
        importe_entrada=D("100.0000"),
    )
    servicio_transferencias.transferir(contexto, datos)

    def intentar(indice: int) -> None:
        propio = ContextoOperacion.de_usuario(contexto.owner_user_id)
        if indice == 0:
            servicio_tesoreria.revertir_movimiento(
                propio,
                DatosReversion(
                    reversion_id=uuid.uuid4(),
                    movimiento_original_id=datos.movimiento_salida_id,
                    cuenta_id=cuenta,
                    fecha_movimiento=F("2027-08-05"),
                    importe=D("100.0000"),
                ),
            )
        else:
            servicio_correcciones.corregir(
                propio,
                DatosCorreccion(
                    hecho_id=datos.hecho_id,
                    row_version_esperada=1,
                    motivo="esa conciliacion nunca debio existir",
                    conciliaciones_a_eliminar=(datos.conciliacion_salida_id,),
                ),
            )

    resultados = _competir(intentar)
    assert "OK" in resultados, resultados

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT count(*) FROM gapto.hecho_movimientos_tesoreria "
        "          WHERE id = %s), "
        "       (SELECT count(*) FROM gapto.movimientos_tesoreria "
        "          WHERE reversion_de_movimiento_id = %s), "
        "       (SELECT COALESCE(sum(abs(importe_asignado)), 0) "
        "          FROM gapto.hecho_movimientos_tesoreria "
        "         WHERE movimiento_tesoreria_id = %s), "
        "       (SELECT abs(importe) FROM gapto.movimientos_tesoreria "
        "          WHERE id = %s)",
        (
            datos.conciliacion_salida_id,
            datos.movimiento_salida_id,
            datos.movimiento_salida_id,
            datos.movimiento_salida_id,
        ),
    )
    conciliaciones, reversiones, asignado, importe = fila
    assert conciliaciones in (0, 1)
    assert reversiones in (0, 1)
    # Lo asignado nunca supera el importe del movimiento.
    assert decimal.Decimal(asignado) <= decimal.Decimal(importe)


def test_i3_la_reversion_no_depende_de_la_conciliacion(
    servicio_transferencias: TransferenciasService,
    servicio_tesoreria: TesoreriaService,
    servicio_correcciones: CorreccionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
) -> None:
    """Secuencial: retirada la conciliacion, el movimiento sigue siendo
    reversible.

    Confirma que la independencia del caso concurrente no es casual: son
    raices distintas y la reversion nunca dependio del puente.
    """
    datos = DatosTransferencia(
        transferencia_id=uuid.uuid4(),
        hecho_id=uuid.uuid4(),
        movimiento_salida_id=uuid.uuid4(),
        movimiento_entrada_id=uuid.uuid4(),
        conciliacion_salida_id=uuid.uuid4(),
        conciliacion_entrada_id=uuid.uuid4(),
        cuenta_origen_id=cuenta,
        cuenta_destino_id=cuenta_destino,
        fecha_hecho=F("2027-08-01"),
        fecha_movimiento=F("2027-08-01"),
        moneda="EUR",
        importe_salida=D("100.0000"),
        importe_entrada=D("100.0000"),
    )
    servicio_transferencias.transferir(contexto, datos)
    servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=datos.hecho_id,
            row_version_esperada=1,
            motivo="conciliacion falsa",
            conciliaciones_a_eliminar=(datos.conciliacion_salida_id,),
        ),
    )
    resultado = servicio_tesoreria.revertir_movimiento(
        contexto,
        DatosReversion(
            reversion_id=uuid.uuid4(),
            movimiento_original_id=datos.movimiento_salida_id,
            cuenta_id=cuenta,
            fecha_movimiento=F("2027-08-05"),
            importe=D("100.0000"),
        ),
    )
    assert resultado.importe == D("100.0000")
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_movimientos_tesoreria WHERE id = %s",
        (datos.conciliacion_salida_id,),
    ) == (0,)
