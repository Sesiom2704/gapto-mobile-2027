# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_119_op21_correccion.py
# Ruta: tests/backend/test_119_op21_correccion.py
# Descripcion: F04-06 / B5. OP-21 correccion agregada.
#
#   OP-21 ARREGLA LO QUE NUNCA FUE CIERTO. Tres vias y solo tres:
#     UPDATE   el dato existe y es corregible;
#     DELETE   la fila hija o puente nunca debio existir;
#     OP-03    la RAIZ completa nunca debio existir.
#
#   Lo que esta suite vigila con mas insistencia:
#
#   - 0320 concedio DELETE sobre doce tablas hijas y sobre NINGUNA raiz. Pedir
#     el borrado de un hecho o de un movimiento devuelve
#     CORRECCION_REQUIERE_ANULACION_DE_RAIZ, no un hard-delete.
#   - Cada DELETE deja su SNAPSHOT completo en auditoria. Es la unica prueba
#     que queda de una fila que ya no existe.
#   - D-187 se evalua sobre el estado FINAL: cero efectos a mitad de
#     transaccion es legitimo si antes del COMMIT se instala el reemplazo.
# Version: 0.3.0
#   0.3.0 (mandato F04 R1+R2 v0.3 + E01): OP-04 aporta `presupuestable` en la
#   transicion al primer GASTO/INGRESO (A08-bis generalizada); fixtures de
#   GASTO con localizacion DESCONOCIDA en vez de NO_APLICA cuando aplica. Sin
#   cambio de las propiedades probadas.
# Version: 0.2.0
#   0.2.0 (F04-D046 R2): la devolucion de apoyo declara `presupuestable`, exigido ahora por OP-13.
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
from app.core.modelos_efectos import DatosEfecto
from app.services.correcciones_service import CorreccionesService, DatosCorreccion
from app.services.efectos_service import EfectosService
from app.services.hechos_service import HechosService
from conftest import leer_fila

D = decimal.Decimal
F = dt.date.fromisoformat


def crear_hecho_con_efectos(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    *,
    cuantos: int = 2,
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    hecho_id = uuid.uuid4()
    servicio.crear_hecho(
        contexto,
        DatosCreacionHecho(
            hecho_id=hecho_id,
            fecha_hecho=F("2027-07-01"),
            moneda="EUR",
            presupuestable=True,
            estado_localizacion="DESCONOCIDA",  # F04-D046 R2: GASTO aplicable, localidad no conocida
            tipo_hecho_codigo="GASTO",
            importe_total=D("100.0000"),
            concepto="Compra con datos mal capturados",
        ),
    )
    efectos = [
        DatosEfecto(
            efecto_id=uuid.uuid4(),
            tipo_efecto="GASTO",
            importe_delta=D("100.0000"),
            estado_atribucion="NO_DISPONIBLE",
        )
    ]
    if cuantos > 1:
        efectos.append(
            DatosEfecto(
                efecto_id=uuid.uuid4(),
                tipo_efecto="GASTO",
                importe_delta=D("20.0000"),
                estado_atribucion="NO_DISPONIBLE",
            )
        )
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=1, efectos=efectos, presupuestable=True
    )
    return hecho_id, [e.efecto_id for e in efectos]


def efecto_nuevo(importe: str = "55.0000") -> DatosEfecto:
    return DatosEfecto(
        efecto_id=uuid.uuid4(),
        tipo_efecto="GASTO",
        importe_delta=D(importe),
        estado_atribucion="NO_DISPONIBLE",
    )


# ==================================================================
# UPDATE de dato falso
# ==================================================================

def test_update_agregado_valido(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_correcciones: CorreccionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    hecho_id, efectos = crear_hecho_con_efectos(
        servicio, servicio_efectos, contexto
    )
    resultado = servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id,
            row_version_esperada=2,
            motivo="el importe estaba mal tecleado",
            efectos_a_actualizar={efectos[0]: {"importe_delta": D("90.0000")}},
        ),
    )
    assert resultado.efectos_actualizados == 1
    assert resultado.hecho_row_version == 3
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe_delta FROM gapto.hecho_efectos WHERE id = %s",
        (efectos[0],),
    ) == (D("90.0000"),)


def test_el_update_queda_auditado_con_antes_y_despues(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_correcciones: CorreccionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    hecho_id, efectos = crear_hecho_con_efectos(
        servicio, servicio_efectos, contexto
    )
    servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id,
            row_version_esperada=2,
            motivo="importe mal tecleado",
            efectos_a_actualizar={efectos[0]: {"importe_delta": D("90.0000")}},
        ),
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT datos_antes->>'importe_delta', datos_despues->>'importe_delta', "
        "       motivo FROM gapto.auditoria "
        " WHERE registro_id = %s AND accion = 'ACTUALIZAR'",
        (efectos[0],),
    ) == ("100.0000", "90.0000", "importe mal tecleado")


# ==================================================================
# DELETE de hijo o puente falso
# ==================================================================

def test_delete_de_efecto_falso(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_correcciones: CorreccionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    hecho_id, efectos = crear_hecho_con_efectos(
        servicio, servicio_efectos, contexto
    )
    resultado = servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id,
            row_version_esperada=2,
            motivo="ese efecto nunca existio",
            efectos_a_eliminar=(efectos[1],),
        ),
    )
    assert resultado.efectos_eliminados == 1
    assert resultado.efectos_finales == 1
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos WHERE id = %s",
        (efectos[1],),
    ) == (0,)


def test_el_delete_deja_snapshot_completo(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_correcciones: CorreccionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """La fila ya no existe en ningun sitio: el snapshot es la unica prueba
    de que existio y de que decia."""
    hecho_id, efectos = crear_hecho_con_efectos(
        servicio, servicio_efectos, contexto
    )
    servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id,
            row_version_esperada=2,
            motivo="duplicado de captura",
            efectos_a_eliminar=(efectos[1],),
        ),
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT datos_antes->>'id', datos_antes->>'tipo_efecto', "
        "       datos_antes->>'importe_delta', datos_antes->>'hecho_id', motivo "
        "  FROM gapto.auditoria "
        " WHERE registro_id = %s AND accion = 'ANULAR'",
        (efectos[1],),
    ) == (
        str(efectos[1]),
        "GASTO",
        "20.0000",
        str(hecho_id),
        "duplicado de captura",
    )


def test_delete_de_puente_falso(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_correcciones: CorreccionesService,
    servicio_devoluciones,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """Una relacion que nunca debio existir se retira con su snapshot."""
    hecho_id, _ = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    from app.core.modelos_devolucion import DatosDevolucion

    devolucion = DatosDevolucion(
        hecho_id=uuid.uuid4(),
        efecto_id=uuid.uuid4(),
        relacion_id=uuid.uuid4(),
        hecho_original_id=hecho_id,
        tipo_efecto="GASTO",
        importe=D("30.0000"),
        presupuestable=True,
        fecha_hecho=F("2027-07-10"),
        moneda="EUR",
        concepto="Devolucion mal atribuida",
    )
    servicio_devoluciones.devolver(contexto, devolucion)

    resultado = servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=devolucion.hecho_id,
            row_version_esperada=1,
            motivo="la devolucion no era de ese hecho",
            relaciones_a_eliminar=(devolucion.relacion_id,),
        ),
    )
    assert resultado.relaciones_eliminadas == 1
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT datos_antes->>'tipo_relacion' FROM gapto.auditoria "
        "WHERE registro_id = %s AND accion = 'ANULAR'",
        (devolucion.relacion_id,),
    ) == ("DEVOLUCION_DE",)


# ==================================================================
# D-187 — estado final
# ==================================================================

def test_correccion_que_dejaria_el_hecho_sin_efectos(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_correcciones: CorreccionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    hecho_id, efectos = crear_hecho_con_efectos(
        servicio, servicio_efectos, contexto, cuantos=1
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=hecho_id,
                row_version_esperada=2,
                motivo="quitar el unico efecto",
                efectos_a_eliminar=(efectos[0],),
            ),
        )
    assert excinfo.value.codigo is CodigoError.CORRECCION_DEJA_HECHO_SIN_EFECTOS
    # Rechazo atomico: el efecto sigue ahi y la version no avanzo.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT count(*) FROM gapto.hecho_efectos WHERE id = %s), "
        "       (SELECT row_version FROM gapto.hechos_financieros WHERE id = %s)",
        (efectos[0], hecho_id),
    ) == (1, 2)


def test_reemplazo_del_ultimo_efecto_en_la_misma_transaccion(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_correcciones: CorreccionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """D-187 se evalua sobre el estado FINAL.

    Quedarse en cero efectos a mitad de la transaccion es legitimo si antes
    del COMMIT se instala el reemplazo. Sin este caso, el test anterior solo
    demostraria que el servicio rechaza, no que DISCRIMINA.
    """
    hecho_id, efectos = crear_hecho_con_efectos(
        servicio, servicio_efectos, contexto, cuantos=1
    )
    reemplazo = efecto_nuevo()
    resultado = servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id,
            row_version_esperada=2,
            motivo="el efecto correcto era otro",
            efectos_a_eliminar=(efectos[0],),
            efectos_a_crear=(reemplazo,),
        ),
    )
    assert (resultado.efectos_eliminados, resultado.efectos_creados) == (1, 1)
    assert resultado.efectos_finales == 1
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe_delta FROM gapto.hecho_efectos WHERE hecho_id = %s",
        (hecho_id,),
    ) == (D("55.0000"),)


def test_nunca_se_reclasifica_a_transferencia(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_correcciones: CorreccionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """Salvar la invariante cambiando el tipo del hecho seria falsificar que
    ocurrio."""
    hecho_id, efectos = crear_hecho_con_efectos(
        servicio, servicio_efectos, contexto, cuantos=1
    )
    with pytest.raises(ErrorMotor):
        servicio_correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=hecho_id,
                row_version_esperada=2,
                motivo="x",
                efectos_a_eliminar=(efectos[0],),
            ),
        )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT t.codigo FROM gapto.hechos_financieros h "
        "  JOIN gapto.tipos_hecho t ON t.id = h.tipo_hecho_id WHERE h.id = %s",
        (hecho_id,),
    ) == ("GASTO",)


# ==================================================================
# Las raices no se borran
# ==================================================================

def test_hard_delete_de_hecho_rechazado(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_correcciones: CorreccionesService,
    contexto: ContextoOperacion,
) -> None:
    """0320 no concedio DELETE sobre `hechos_financieros`, y este servicio
    tampoco lo ofrece: la via es OP-03."""
    hecho_id, _ = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=hecho_id,
                row_version_esperada=2,
                motivo="la raiz nunca debio existir",
                eliminar_hecho=True,
            ),
        )
    assert (
        excinfo.value.codigo is CodigoError.CORRECCION_REQUIERE_ANULACION_DE_RAIZ
    )


def test_hard_delete_de_movimiento_rechazado(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_correcciones: CorreccionesService,
    contexto: ContextoOperacion,
) -> None:
    hecho_id, _ = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=hecho_id,
                row_version_esperada=2,
                motivo="x",
                eliminar_movimiento=uuid.uuid4(),
            ),
        )
    assert (
        excinfo.value.codigo is CodigoError.CORRECCION_REQUIERE_ANULACION_DE_RAIZ
    )


def test_el_grant_de_0320_no_alcanza_a_las_raices(
    admin: psycopg.Connection,
) -> None:
    """Verificacion directa del contrato fisico, sin pasar por el servicio.

    La garantia no depende de mi prevalidacion: gapto_runtime no tiene DELETE
    sobre las dos raices financieras.
    """
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute(
            "SELECT has_table_privilege('gapto_runtime', %s, 'DELETE'), "
            "       has_table_privilege('gapto_runtime', %s, 'DELETE'), "
            "       has_table_privilege('gapto_runtime', %s, 'DELETE')",
            (
                "gapto.hechos_financieros",
                "gapto.movimientos_tesoreria",
                "gapto.hecho_efectos",
            ),
        )
        assert cursor.fetchone() == (False, False, True)


# ==================================================================
# Motivo, version y concurrencia
# ==================================================================

def test_motivo_ausente(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_correcciones: CorreccionesService,
    contexto: ContextoOperacion,
) -> None:
    hecho_id, efectos = crear_hecho_con_efectos(
        servicio, servicio_efectos, contexto
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=hecho_id,
                row_version_esperada=2,
                motivo="   ",
                efectos_a_eliminar=(efectos[1],),
            ),
        )
    assert excinfo.value.codigo is CodigoError.MOTIVO_AUSENTE


def test_version_desfasada(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_correcciones: CorreccionesService,
    contexto: ContextoOperacion,
) -> None:
    hecho_id, efectos = crear_hecho_con_efectos(
        servicio, servicio_efectos, contexto
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=hecho_id,
                row_version_esperada=99,
                motivo="x",
                efectos_a_eliminar=(efectos[1],),
            ),
        )
    assert excinfo.value.codigo is CodigoError.VERSION_DESFASADA


def test_correccion_vacia(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_correcciones: CorreccionesService,
    contexto: ContextoOperacion,
) -> None:
    hecho_id, _ = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=hecho_id, row_version_esperada=2, motivo="x"
            ),
        )
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


def test_cross_tenant(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_correcciones: CorreccionesService,
    contexto: ContextoOperacion,
    otro_owner: uuid.UUID,
) -> None:
    hecho_id, efectos = crear_hecho_con_efectos(
        servicio, servicio_efectos, contexto
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_correcciones.corregir(
            ContextoOperacion.de_usuario(otro_owner),
            DatosCorreccion(
                hecho_id=hecho_id,
                row_version_esperada=2,
                motivo="x",
                efectos_a_eliminar=(efectos[1],),
            ),
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


def test_dos_correcciones_concurrentes_sobre_la_misma_raiz(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_correcciones: CorreccionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """Interleaving: dos OP-21 sobre el mismo hecho.

    Ambas parten de la misma version esperada. El control optimista debe dejar
    pasar exactamente una; la otra recibe VERSION_DESFASADA y no aplica NADA,
    ni siquiera su parte.
    """
    hecho_id, efectos = crear_hecho_con_efectos(
        servicio, servicio_efectos, contexto
    )
    barrera = threading.Barrier(2)
    resultados: list[object] = []
    cerrojo = threading.Lock()

    def intentar(indice: int) -> None:
        propio = ContextoOperacion.de_usuario(contexto.owner_user_id)
        barrera.wait()
        try:
            servicio_correcciones.corregir(
                propio,
                DatosCorreccion(
                    hecho_id=hecho_id,
                    row_version_esperada=2,
                    motivo=f"correccion {indice}",
                    efectos_a_actualizar={
                        efectos[0]: {"descripcion": f"version {indice}"}
                    },
                ),
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
    assert CodigoError.VERSION_DESFASADA in resultados, resultados
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    ) == (3,)


def test_campo_no_corregible_rechazado(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_correcciones: CorreccionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """Mover un efecto a otro hecho no es corregir un dato falso.

    Es falsificar a que realidad pertenece. La lista de campos corregibles es
    CERRADA, y pedir uno fuera de ella produce un error legible en vez de un
    AGREGADO_NO_ENCONTRADO enganoso sobre un efecto que si existe.
    """
    hecho_id, efectos = crear_hecho_con_efectos(
        servicio, servicio_efectos, contexto
    )
    otro, _ = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=hecho_id,
                row_version_esperada=2,
                motivo="reasignar el efecto",
                efectos_a_actualizar={efectos[0]: {"hecho_id": otro}},
            ),
        )
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT hecho_id FROM gapto.hecho_efectos WHERE id = %s",
        (efectos[0],),
    ) == (hecho_id,)
