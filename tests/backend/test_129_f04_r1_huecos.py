# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_129_f04_r1_huecos.py
# Ruta: tests/backend/test_129_f04_r1_huecos.py
# Descripcion: F04-R1 (mandato F04-R1 IMPL v1.0 §F5.3). CARACTERIZACION de los
#   huecos de lock que el diagnostico PRE (aristas.md §B.6) dejo fuera de R1 y
#   que esta fase discrimina en SOLO LECTURA. Cada test fija la conducta ACTUAL
#   por una ruta ejecutable del motor (`backend/app`): pasa mientras el hueco
#   exista y FALLA el dia que se cierre, para que el cambio se haga a la vista
#   (y se retire o invierta este test). No es la conducta deseada: cada hueco
#   esta escalado en `C:\DEV\gapto-canal\handoffs\ESCALADO_F04-R1_<hueco>.md`.
#   R1 no los corrige (fuera de alcance; ningun fix aqui).
#     - OP21-PERTENENCIA: OP-21 sobre el hecho H1 actualiza un efecto, retira
#       una relacion y retira una conciliacion de OTRO hecho H2 del mismo
#       owner, bajo la raiz de H1 y sin bloquear ni versionar H2.
#     - RVRX-REGLA: crear_version de la regla A cierra una version de la regla
#       B, y corregir_excepcion de A reescribe una excepcion de B, bajo el lock
#       de A y sin tocar la version de B.
# Version: 0.1.0 (F04-R1 IMPL F5)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid

from app.core.modelos_prevision import DatosExcepcion, DatosRegla
from app.core.modelos_tesoreria import DatosConciliacion, DatosMovimiento
from app.services.correcciones_service import DatosCorreccion
from conftest import leer_fila
from test_113_rodante_y_materializacion import version_rodante
from test_117_op13_devolucion import crear_origen, datos_devolucion
from test_119_op21_correccion import crear_hecho_con_efectos
from test_138_f04_r1_discriminantes import version_hecho

D = decimal.Decimal
F = dt.date.fromisoformat


def _corregir_h1(servicio_correcciones, contexto, admin, h1, **filas):
    return servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=h1, row_version_esperada=version_hecho(admin, contexto.owner_user_id, h1),
        motivo="caracterizacion F04-R1 F5", **filas))


# ==================================================================
# OP21-PERTENENCIA
# ==================================================================
def test_caracterizacion_op21_actualiza_un_efecto_de_otro_hecho(servicio, servicio_efectos, servicio_correcciones,
                                                                contexto, admin):
    h1, _ = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    h2, efectos_h2 = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    version_h2 = version_hecho(admin, contexto.owner_user_id, h2)
    _corregir_h1(servicio_correcciones, contexto, admin, h1,
                 efectos_a_actualizar={efectos_h2[0]: {"descripcion": "escrito desde H1"}})
    assert leer_fila(admin, contexto.owner_user_id, "SELECT hecho_id, descripcion FROM gapto.hecho_efectos "
                     "WHERE id = %s", (efectos_h2[0],)) == (h2, "escrito desde H1")
    assert version_hecho(admin, contexto.owner_user_id, h2) == version_h2  # H2 ni se bloqueo ni se versiono


def test_caracterizacion_op21_retira_una_relacion_de_otro_hecho(servicio, servicio_efectos, servicio_devoluciones,
                                                                servicio_correcciones, contexto, admin):
    original = crear_origen(servicio, servicio_efectos, contexto)
    devolucion = datos_devolucion(original)
    servicio_devoluciones.devolver(contexto, devolucion)
    ajeno, _ = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    _corregir_h1(servicio_correcciones, contexto, admin, ajeno, relaciones_a_eliminar=(devolucion.relacion_id,))
    assert leer_fila(admin, contexto.owner_user_id, "SELECT count(*) FROM gapto.hecho_relaciones WHERE id = %s",
                     (devolucion.relacion_id,)) == (0,)


def test_caracterizacion_op21_retira_una_conciliacion_de_otro_hecho(servicio, servicio_efectos, servicio_tesoreria,
                                                                    servicio_correcciones, contexto, admin, cuenta):
    h1, _ = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    h2, _ = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    mov = servicio_tesoreria.registrar_movimiento(contexto, DatosMovimiento(
        movimiento_id=uuid.uuid4(), cuenta_id=cuenta, fecha_movimiento=F("2026-06-02"),
        importe=D("-7.0000"), clase_movimiento="OPERACION"))
    conciliacion = DatosConciliacion(uuid.uuid4(), h2, mov.movimiento_id, D("-7.0000"))
    servicio_tesoreria.conciliar(contexto, conciliacion,
                                 hecho_row_version_esperada=version_hecho(admin, contexto.owner_user_id, h2),
                                 movimiento_row_version_esperada=mov.row_version)
    version_h2 = version_hecho(admin, contexto.owner_user_id, h2)
    _corregir_h1(servicio_correcciones, contexto, admin, h1, conciliaciones_a_eliminar=(conciliacion.conciliacion_id,))
    assert leer_fila(admin, contexto.owner_user_id, "SELECT count(*) FROM gapto.hecho_movimientos_tesoreria "
                     "WHERE id = %s", (conciliacion.conciliacion_id,)) == (0,)
    assert version_hecho(admin, contexto.owner_user_id, h2) == version_h2


# ==================================================================
# RVRX-REGLA
# ==================================================================
def _regla(servicio_reglas, contexto, *, con_version: bool = True):
    regla_id = uuid.uuid4()
    version = version_rodante(vigente_desde=F("2027-01-10")) if con_version else None
    r = servicio_reglas.crear_regla(contexto, DatosRegla(regla_id=regla_id, nombre="F04-R1 F5"), version)
    return regla_id, version and version.version_id, r.regla_row_version


def _version_regla(admin, owner, regla_id) -> int:
    return leer_fila(admin, owner, "SELECT row_version FROM gapto.reglas_financieras WHERE id = %s", (regla_id,))[0]


def test_caracterizacion_crear_version_de_a_cierra_una_version_de_b(servicio_reglas, contexto, admin):
    a, _, version_a = _regla(servicio_reglas, contexto, con_version=False)  # su nueva version no solapa con nada
    b, rv_b, _ = _regla(servicio_reglas, contexto)
    version_b = _version_regla(admin, contexto.owner_user_id, b)
    servicio_reglas.crear_version(contexto, regla_id=a, regla_row_version_esperada=version_a,
                                  version=version_rodante(vigente_desde=F("2027-03-01")),
                                  cerrar_version_id=rv_b, cerrar_vigente_hasta=F("2027-02-01"))
    assert leer_fila(admin, contexto.owner_user_id, "SELECT regla_id, vigente_hasta FROM gapto.regla_versiones "
                     "WHERE id = %s", (rv_b,)) == (b, F("2027-02-01"))
    assert _version_regla(admin, contexto.owner_user_id, b) == version_b  # B ni se bloqueo ni se versiono


def test_caracterizacion_corregir_excepcion_de_a_reescribe_una_excepcion_de_b(servicio_reglas, contexto, admin):
    a, _, _ = _regla(servicio_reglas, contexto)
    b, _, version_b = _regla(servicio_reglas, contexto)
    excepcion = DatosExcepcion(excepcion_id=uuid.uuid4(), fecha_objetivo=F("2027-03-10"),
                               importe_override=D("10.0000"), motivo="de B")
    servicio_reglas.registrar_excepcion(contexto, regla_id=b, regla_row_version_esperada=version_b,
                                        excepcion=excepcion)
    version_b = _version_regla(admin, contexto.owner_user_id, b)
    servicio_reglas.corregir_excepcion(contexto, regla_id=a,
                                       regla_row_version_esperada=_version_regla(admin, contexto.owner_user_id, a),
                                       excepcion_id=excepcion.excepcion_id,
                                       cambios={"importe_override": D("99.0000")}, motivo="desde A")
    assert leer_fila(admin, contexto.owner_user_id, "SELECT regla_id, importe_override FROM gapto.regla_excepciones "
                     "WHERE id = %s", (excepcion.excepcion_id,)) == (b, D("99.0000"))
    assert _version_regla(admin, contexto.owner_user_id, b) == version_b
