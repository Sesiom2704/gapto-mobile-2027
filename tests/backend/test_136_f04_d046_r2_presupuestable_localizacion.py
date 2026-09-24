# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_136_f04_d046_r2_presupuestable_localizacion.py
# Ruta: tests/backend/test_136_f04_d046_r2_presupuestable_localizacion.py
# Descripcion: F04-D046 R2 (A20 + A08-bis). Bateria discriminante de la
#   decision historica `presupuestable` y de la localizacion en OP-13, OP-18 y
#   OP-21.
#
#   UNA PRUEBA POR CONTRATO. El mandato exige no agrupar: si falla una, su
#   nombre dice que contrato se rompio.
#
#   EL CONSUMO SE CALCULA CON EL CONTRATO VIGENTE, NO CON UN READ-MODEL F08
#   (que no existe todavia): solo alimentan presupuesto los efectos GASTO /
#   INGRESO de hechos ACTIVOS con `presupuestable=true` (DB Schema, INV-11).
#   La consulta `consumo` es esa definicion, literal.
# Version: 0.2.0
#   0.2.0 (mandato F04 R1+R2 v0.3 + E01, auditoria de test_136): (a) OP-04
#   exige ahora la decision `presupuestable` al nacer el primer GASTO/INGRESO,
#   asi que los helpers `_gasto` y `_aportacion_con_comision` la aportan; (b)
#   R2-10 se reformula de «false derivado» a «INACTIVO» (v0.3 §3) y su
#   auditoria se filtra por el motivo de la correccion, porque la activacion
#   en OP-04 deja otra; (c) R2-11b: la decision explicita se persiste y audita
#   SIEMPRE en la transicion, tambien cuando coincide con el booleano
#   inactivo previo (v0.3 §7: el valor almacenado no sustituye la decision).
#   Las pruebas nuevas de v0.3/E01 viven en test_137.
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
from app.core.modelos import DatosCreacionHecho
from app.core.modelos_devolucion import DatosDevolucion
from app.core.modelos_efectos import DatosEfecto
from app.core.modelos_posicion import DatosAltaPosicion, TIPO_OBLIGACION
from app.core.modelos_suplemento import DatosSuplemento
from app.core.modelos_transferencia import DatosTransferencia
from app.services.correcciones_service import DatosCorreccion
from conftest import leer_fila

D = decimal.Decimal
F = dt.date.fromisoformat


# ==================================================================
# Utilidades
# ==================================================================

def _gasto(servicio, servicio_efectos, contexto, importe="100.0000") -> uuid.UUID:
    """Gasto original presupuestable: GASTO +100."""
    hecho_id = uuid.uuid4()
    servicio.crear_hecho(
        contexto,
        DatosCreacionHecho(
            hecho_id=hecho_id,
            fecha_hecho=F("2027-05-01"),
            moneda="EUR",
            presupuestable=True,
            estado_localizacion="DESCONOCIDA",
            tipo_hecho_codigo="GASTO",
            importe_total=D(importe),
        ),
    )
    servicio_efectos.registrar_efectos(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=1,
        efectos=[
            DatosEfecto(
                efecto_id=uuid.uuid4(),
                tipo_efecto="GASTO",
                importe_delta=D(importe),
                estado_atribucion="NO_DISPONIBLE",
            )
        ],
        presupuestable=True,
    )
    return hecho_id


def _devolucion(original: uuid.UUID, **extra) -> DatosDevolucion:
    base = dict(
        hecho_id=uuid.uuid4(),
        efecto_id=uuid.uuid4(),
        relacion_id=uuid.uuid4(),
        hecho_original_id=original,
        tipo_efecto="GASTO",
        importe=D("40.0000"),
        fecha_hecho=F("2027-05-10"),
        moneda="EUR",
        concepto="devolucion",
    )
    base.update(extra)
    return DatosDevolucion(**base)


def _suplemento(ajustado: uuid.UUID | None, **extra) -> DatosSuplemento:
    base = dict(
        hecho_id=uuid.uuid4(),
        efecto_id=uuid.uuid4(),
        tipo_efecto="GASTO",
        importe_delta=D("3.5000"),
        fecha_hecho=F("2027-05-12"),
        moneda="EUR",
        fecha_demostrada=True,
        concepto="recargo",
    )
    if ajustado is not None:
        base.update(relacion_id=uuid.uuid4(), hecho_ajustado_id=ajustado)
    base.update(extra)
    return DatosSuplemento(**base)


def _hecho(admin, contexto, hecho_id) -> tuple:
    return leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT presupuestable, estado_localizacion, localidad_id, row_version "
        "FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )


def _consumo(admin, contexto, hechos) -> decimal.Decimal:
    """Contrato vigente: GASTO de hechos ACTIVOS con presupuestable=true."""
    return leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT coalesce(sum(e.importe_delta), 0) FROM gapto.hecho_efectos e "
        "JOIN gapto.hechos_financieros h ON h.id = e.hecho_id "
        "WHERE h.id = ANY(%s) AND h.estado = 'ACTIVO' AND h.presupuestable "
        "AND e.tipo_efecto = 'GASTO'",
        (list(hechos),),
    )[0]


# ==================================================================
# 1..4 · OP-13 y consumo presupuestario
# ==================================================================

def test_r2_01_gasto_mas_100_presupuestable(
    servicio, servicio_efectos, contexto, admin
) -> None:
    original = _gasto(servicio, servicio_efectos, contexto)
    assert _hecho(admin, contexto, original)[0] is True
    assert _consumo(admin, contexto, [original]) == D("100.0000")


def test_r2_02_devolucion_menos_40_presupuestable(
    servicio, servicio_efectos, servicio_devoluciones, contexto, admin
) -> None:
    original = _gasto(servicio, servicio_efectos, contexto)
    datos = _devolucion(original, presupuestable=True)
    resultado = servicio_devoluciones.devolver(contexto, datos)
    assert resultado.importe_delta == D("-40.0000")
    assert _hecho(admin, contexto, datos.hecho_id)[0] is True


def test_r2_03_consumo_neto_60(
    servicio, servicio_efectos, servicio_devoluciones, contexto, admin
) -> None:
    original = _gasto(servicio, servicio_efectos, contexto)
    datos = _devolucion(original, presupuestable=True)
    servicio_devoluciones.devolver(contexto, datos)
    assert _consumo(admin, contexto, [original, datos.hecho_id]) == D("60.0000")


def test_r2_04_devolucion_deliberadamente_no_presupuestable(
    servicio, servicio_efectos, servicio_devoluciones, contexto, admin
) -> None:
    original = _gasto(servicio, servicio_efectos, contexto)
    datos = _devolucion(original, presupuestable=False)
    servicio_devoluciones.devolver(contexto, datos)
    assert _hecho(admin, contexto, datos.hecho_id)[0] is False
    assert _consumo(admin, contexto, [original, datos.hecho_id]) == D("100.0000")


def test_r2_04b_devolucion_sin_decision_se_rechaza(
    servicio, servicio_efectos, servicio_devoluciones, contexto, admin
) -> None:
    """Sin default oculto: el motor no decide por el llamante."""
    original = _gasto(servicio, servicio_efectos, contexto)
    datos = _devolucion(original)
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_devoluciones.devolver(contexto, datos)
    assert excepcion.value.codigo is CodigoError.ENTRADA_INVALIDA
    assert _hecho(admin, contexto, datos.hecho_id) is None


# ==================================================================
# 5..6 · OP-18
# ==================================================================

def test_r2_05_suplemento_mas_3_50_presupuestable(
    servicio, servicio_efectos, servicio_suplementos, contexto, admin
) -> None:
    original = _gasto(servicio, servicio_efectos, contexto)
    datos = _suplemento(original, presupuestable=True)
    servicio_suplementos.registrar(contexto, datos)
    assert _hecho(admin, contexto, datos.hecho_id)[0] is True
    assert _consumo(admin, contexto, [original, datos.hecho_id]) == D("103.5000")


def test_r2_06_suplemento_mas_3_50_no_presupuestable(
    servicio, servicio_efectos, servicio_suplementos, contexto, admin
) -> None:
    original = _gasto(servicio, servicio_efectos, contexto)
    datos = _suplemento(original, presupuestable=False)
    servicio_suplementos.registrar(contexto, datos)
    assert _hecho(admin, contexto, datos.hecho_id)[0] is False
    assert _consumo(admin, contexto, [original, datos.hecho_id]) == D("100.0000")


def test_r2_06b_suplemento_sin_decision_se_rechaza(
    servicio_suplementos, contexto, admin
) -> None:
    datos = _suplemento(None)
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_suplementos.registrar(contexto, datos)
    assert excepcion.value.codigo is CodigoError.ENTRADA_INVALIDA
    assert _hecho(admin, contexto, datos.hecho_id) is None


def test_r2_06c_suplemento_no_hereda_del_ajustado(
    servicio, servicio_efectos, servicio_suplementos, contexto, admin
) -> None:
    """El ajustado es presupuestable; el suplemento decide lo contrario."""
    original = _gasto(servicio, servicio_efectos, contexto)
    datos = _suplemento(original, presupuestable=False)
    servicio_suplementos.registrar(contexto, datos)
    assert _hecho(admin, contexto, original)[0] is True
    assert _hecho(admin, contexto, datos.hecho_id)[0] is False


# ==================================================================
# 7..9 · Localizacion
# ==================================================================

def test_r2_07_devolucion_con_localizacion_desconocida(
    servicio, servicio_efectos, servicio_devoluciones, contexto, admin
) -> None:
    original = _gasto(servicio, servicio_efectos, contexto)
    datos = _devolucion(original, presupuestable=True)
    servicio_devoluciones.devolver(contexto, datos)
    assert _hecho(admin, contexto, datos.hecho_id)[1:3] == ("DESCONOCIDA", None)


def test_r2_08_suplemento_con_localizacion_desconocida(
    servicio_suplementos, contexto, admin
) -> None:
    datos = _suplemento(None, presupuestable=True)
    servicio_suplementos.registrar(contexto, datos)
    assert _hecho(admin, contexto, datos.hecho_id)[1:3] == ("DESCONOCIDA", None)


def test_r2_09a_devolucion_con_localidad_conocida(
    servicio, servicio_efectos, servicio_devoluciones, contexto, admin, localidad
) -> None:
    """El dato aportado se conserva; no se hereda ni se inventa."""
    original = _gasto(servicio, servicio_efectos, contexto)
    datos = _devolucion(original, presupuestable=True, localidad_id=localidad)
    servicio_devoluciones.devolver(contexto, datos)
    assert _hecho(admin, contexto, datos.hecho_id)[1:3] == ("CONOCIDA", localidad)


def test_r2_09b_no_aplica_nunca_es_default_en_op13_ni_op18(
    servicio, servicio_efectos, servicio_devoluciones, servicio_suplementos,
    contexto, admin,
) -> None:
    original = _gasto(servicio, servicio_efectos, contexto)
    devolucion = _devolucion(original, presupuestable=True)
    suplemento = _suplemento(original, presupuestable=True)
    servicio_devoluciones.devolver(contexto, devolucion)
    servicio_suplementos.registrar(contexto, suplemento)
    for hecho_id in (devolucion.hecho_id, suplemento.hecho_id):
        assert _hecho(admin, contexto, hecho_id)[1] != "NO_APLICA"


def test_r2_09c_no_aplica_en_transferencia_sin_incidencia_territorial(
    servicio_transferencias, contexto, admin, cuenta, cuenta_destino
) -> None:
    """Transferencia propia: sin efectos ni consumo, la localidad no aplica."""
    datos = DatosTransferencia(
        transferencia_id=uuid.uuid4(),
        hecho_id=uuid.uuid4(),
        movimiento_salida_id=uuid.uuid4(),
        movimiento_entrada_id=uuid.uuid4(),
        conciliacion_salida_id=uuid.uuid4(),
        conciliacion_entrada_id=uuid.uuid4(),
        cuenta_origen_id=cuenta,
        cuenta_destino_id=cuenta_destino,
        fecha_hecho=F("2027-05-15"),
        fecha_movimiento=F("2027-05-15"),
        moneda="EUR",
        importe_salida=D("50.0000"),
        importe_entrada=D("50.0000"),
        concepto="traspaso",
    )
    servicio_transferencias.transferir(contexto, datos)
    assert _hecho(admin, contexto, datos.hecho_id)[:2] == (False, "NO_APLICA")


def test_r2_09d_no_aplica_en_posicion_pura(
    servicio_posiciones, contexto, admin, contraparte
) -> None:
    """Posicion con hecho propio: solo DEUDA, sin consumo territorial."""
    datos = DatosAltaPosicion(
        entidad_id=uuid.uuid4(),
        nombre="prestamo recibido",
        tipo=TIPO_OBLIGACION,
        contraparte_actor_id=contraparte,
        moneda="EUR",
        justificacion="DECISION_EXPLICITA",
        fecha_inicio_seguimiento=F("2027-05-01"),
        saldo_apertura=D("0"),
        hecho_id=uuid.uuid4(),
        fecha_hecho=F("2027-05-01"),
        concepto="prestamo recibido",
        efecto_id=uuid.uuid4(),
        vinculo_id=uuid.uuid4(),
        importe_inicial=D("200.0000"),
    )
    servicio_posiciones.crear_posicion(contexto, datos)
    assert _hecho(admin, contexto, datos.hecho_id)[:2] == (False, "NO_APLICA")


# ==================================================================
# 10 · Sin GASTO ni INGRESO -> presupuestable=false derivado
# ==================================================================

def _aportacion_con_comision(servicio, servicio_efectos, contexto):
    """Aportacion 100 a inversion + comision 2 (GASTO), presupuestable."""
    hecho_id = uuid.uuid4()
    servicio.crear_hecho(
        contexto,
        DatosCreacionHecho(
            hecho_id=hecho_id,
            fecha_hecho=F("2027-05-01"),
            moneda="EUR",
            presupuestable=True,
            estado_localizacion="DESCONOCIDA",
            tipo_hecho_codigo="APORTACION_INVERSION",
            importe_total=D("102.0000"),
        ),
    )
    inversion = uuid.uuid4()
    comision = uuid.uuid4()
    resultado = servicio_efectos.registrar_efectos(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=1,
        efectos=[
            DatosEfecto(
                efecto_id=inversion,
                tipo_efecto="INVERSION",
                importe_delta=D("100.0000"),
                estado_atribucion="NO_DISPONIBLE",
            ),
            DatosEfecto(
                efecto_id=comision,
                tipo_efecto="GASTO",
                importe_delta=D("2.0000"),
                estado_atribucion="NO_DISPONIBLE",
            ),
        ],
        presupuestable=True,
    )
    return hecho_id, comision, resultado.row_version


def test_r2_10_solo_inversion_deriva_presupuestable_false(
    servicio, servicio_efectos, servicio_correcciones, contexto, admin
) -> None:
    """La comision nunca existio: OP-21 la retira y el hecho queda solo con
    INVERSION. `presupuestable` queda INACTIVO (v0.3 §3); fisicamente se
    persiste `false` y la transicion queda auditada (E01 §5)."""
    hecho_id, comision, version = _aportacion_con_comision(
        servicio, servicio_efectos, contexto
    )
    servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id,
            row_version_esperada=version,
            motivo="la comision no existia",
            efectos_a_eliminar=(comision,),
        ),
    )
    assert _hecho(admin, contexto, hecho_id)[0] is False
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT motivo, datos_antes->>'presupuestable', "
        "datos_despues->>'presupuestable' FROM gapto.auditoria "
        "WHERE tabla = 'hechos_financieros' AND registro_id = %s "
        "AND accion = 'ACTUALIZAR' AND motivo = 'la comision no existia'",
        (hecho_id,),
    ) == ("la comision no existia", "true", "false")


def test_r2_10b_declarar_true_sin_gasto_ni_ingreso_se_rechaza(
    servicio_devoluciones, contexto
) -> None:
    """Devolucion de DEUDA: sin GASTO/INGRESO no cabe `presupuestable=true`."""
    datos = _devolucion(uuid.uuid4(), tipo_efecto="DEUDA", presupuestable=True)
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_devoluciones.devolver(contexto, datos)
    assert excepcion.value.codigo is CodigoError.ENTRADA_INVALIDA


def test_r2_10c_op21_rechaza_true_al_retirar_el_ultimo_gasto(
    servicio, servicio_efectos, servicio_correcciones, contexto, admin
) -> None:
    hecho_id, comision, version = _aportacion_con_comision(
        servicio, servicio_efectos, contexto
    )
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=hecho_id,
                row_version_esperada=version,
                motivo="la comision no existia",
                efectos_a_eliminar=(comision,),
                presupuestable=True,
            ),
        )
    assert excepcion.value.codigo is CodigoError.ENTRADA_INVALIDA
    assert _hecho(admin, contexto, hecho_id)[0] is True


# ==================================================================
# 11..12 · OP-21 introduce el primer GASTO/INGRESO
# ==================================================================

def _solo_inversion(servicio, servicio_efectos, contexto):
    hecho_id = uuid.uuid4()
    servicio.crear_hecho(
        contexto,
        DatosCreacionHecho(
            hecho_id=hecho_id,
            fecha_hecho=F("2027-05-01"),
            moneda="EUR",
            presupuestable=False,
            estado_localizacion="DESCONOCIDA",
            tipo_hecho_codigo="APORTACION_INVERSION",
            importe_total=D("100.0000"),
        ),
    )
    resultado = servicio_efectos.registrar_efectos(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=1,
        efectos=[
            DatosEfecto(
                efecto_id=uuid.uuid4(),
                tipo_efecto="INVERSION",
                importe_delta=D("100.0000"),
                estado_atribucion="NO_DISPONIBLE",
            )
        ],
    )
    return hecho_id, resultado.row_version


def _comision_omitida() -> DatosEfecto:
    return DatosEfecto(
        efecto_id=uuid.uuid4(),
        tipo_efecto="GASTO",
        importe_delta=D("2.0000"),
        estado_atribucion="NO_DISPONIBLE",
    )


def test_r2_11_primer_gasto_por_op21_exige_decision(
    servicio, servicio_efectos, servicio_correcciones, contexto
) -> None:
    hecho_id, version = _solo_inversion(servicio, servicio_efectos, contexto)
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=hecho_id,
                row_version_esperada=version,
                motivo="la comision se omitio al registrar",
                efectos_a_crear=(_comision_omitida(),),
            ),
        )
    assert excepcion.value.codigo is CodigoError.ENTRADA_INVALIDA


def test_r2_12_sin_decision_rollback_total(
    servicio, servicio_efectos, servicio_correcciones, contexto, admin
) -> None:
    hecho_id, version = _solo_inversion(servicio, servicio_efectos, contexto)
    antes = _hecho(admin, contexto, hecho_id)
    comision = _comision_omitida()
    auditoria_antes = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.auditoria WHERE registro_id = ANY(%s)",
        ([hecho_id, comision.efecto_id],),
    )
    with pytest.raises(ErrorMotor):
        servicio_correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=hecho_id,
                row_version_esperada=version,
                motivo="la comision se omitio al registrar",
                efectos_a_crear=(comision,),
            ),
        )
    # Ninguna modificacion parcial: ni efecto, ni version, ni escalar, ni
    # auditoria.
    assert _hecho(admin, contexto, hecho_id) == antes
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), string_agg(tipo_efecto, ',') FROM gapto.hecho_efectos "
        "WHERE hecho_id = %s",
        (hecho_id,),
    ) == (1, "INVERSION")
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.auditoria WHERE registro_id = ANY(%s)",
        ([hecho_id, comision.efecto_id],),
    ) == auditoria_antes


@pytest.mark.parametrize("decision", [True, False])
def test_r2_11b_primer_gasto_con_decision_explicita(
    servicio, servicio_efectos, servicio_correcciones, contexto, admin, decision
) -> None:
    """Caso positivo: la decision aportada se persiste tal cual y se audita."""
    hecho_id, version = _solo_inversion(servicio, servicio_efectos, contexto)
    resultado = servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id,
            row_version_esperada=version,
            motivo="la comision se omitio al registrar",
            efectos_a_crear=(_comision_omitida(),),
            presupuestable=decision,
        ),
    )
    fila = _hecho(admin, contexto, hecho_id)
    assert fila[0] is decision
    assert fila[3] == resultado.hecho_row_version
    cambios = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.auditoria WHERE tabla = 'hechos_financieros' "
        "AND registro_id = %s AND accion = 'ACTUALIZAR'",
        (hecho_id,),
    )[0]
    # v0.3 §7: la decision se persiste y audita SIEMPRE en la transicion,
    # tambien `false` sobre un `false` inactivo previo (R2-16).
    assert cambios == 1


def test_r2_11c_sin_transicion_presupuestable_va_por_op02(
    servicio, servicio_efectos, servicio_correcciones, contexto
) -> None:
    hecho_id, version = _solo_inversion(servicio, servicio_efectos, contexto)
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=hecho_id,
                row_version_esperada=version,
                motivo="ajuste",
                efectos_a_actualizar={},
                relaciones_a_eliminar=(),
                efectos_a_crear=(
                    DatosEfecto(
                        efecto_id=uuid.uuid4(),
                        tipo_efecto="INVERSION",
                        importe_delta=D("5.0000"),
                        estado_atribucion="NO_DISPONIBLE",
                    ),
                ),
                presupuestable=False,
            ),
        )
    assert excepcion.value.codigo is CodigoError.ENTRADA_INVALIDA


# ==================================================================
# Idempotencia: la decision forma parte de la intencion
# ==================================================================

def test_r2_idem_retry_mismo_payload_es_idempotente(
    servicio, servicio_efectos, servicio_devoluciones, contexto
) -> None:
    original = _gasto(servicio, servicio_efectos, contexto)
    datos = _devolucion(original, presupuestable=True)
    servicio_devoluciones.devolver(contexto, datos)
    assert servicio_devoluciones.devolver(contexto, datos).idempotente is True


def test_r2_idem_misma_identidad_otra_decision_es_conflicto(
    servicio, servicio_efectos, servicio_devoluciones, servicio_suplementos,
    contexto,
) -> None:
    original = _gasto(servicio, servicio_efectos, contexto)
    devolucion = _devolucion(original, presupuestable=True)
    servicio_devoluciones.devolver(contexto, devolucion)
    otra = DatosDevolucion(
        **{**{f: getattr(devolucion, f) for f in devolucion.__slots__},
           "presupuestable": False}
    )
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_devoluciones.devolver(contexto, otra)
    assert excepcion.value.codigo is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION

    suplemento = _suplemento(original, presupuestable=True)
    servicio_suplementos.registrar(contexto, suplemento)
    otro = DatosSuplemento(
        **{**{f: getattr(suplemento, f) for f in suplemento.__slots__},
           "presupuestable": False}
    )
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_suplementos.registrar(contexto, otro)
    assert excepcion.value.codigo is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION
