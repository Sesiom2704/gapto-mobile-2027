# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_137_f04_r1r2_v03_fronteras.py
# Ruta: tests/backend/test_137_f04_r1r2_v03_fronteras.py
# Descripcion: Mandato F04 R1+R2 v0.3 + enmienda E01. Pruebas discriminantes
#   de las guardas de FRONTERA DE ESCRITURA que v0.3 generaliza mas alla de
#   OP-13/OP-18/OP-21 (cubiertas en test_136):
#
#     - A08-bis generalizada: `presupuestable` esta INACTIVO mientras el hecho
#       no tiene GASTO/INGRESO; la transicion sin -> con exige decision
#       explicita en OP-04, OP-21 y la condonacion con GASTO. El booleano
#       fisico almacenado durante la etapa inactiva (true o false) NUNCA
#       sustituye a la decision.
#     - Localizacion: si una escritura de OP-04/OP-13/OP-18/OP-21/condonacion
#       deja GASTO/INGRESO, `NO_APLICA` es invalido; sin dato -> DESCONOCIDA.
#       `NO_APLICA` sigue siendo valido en un hecho puramente posicional.
#     - OP-19 sigue funcionando: propaga la decision ya explicita a OP-04.
#     - Condonacion: la parametrizacion interna de `_crear_hecho` y
#       `_aplicar_delta` no cambia nada observable en el resto de operaciones.
#
#   Cada prueba nombra en su docstring el numero de la bateria v0.3 (1..24) o
#   de E01 §7 (25..31) y el contrato exacto que discrimina. Las guardas son de
#   frontera hacia adelante: ninguna prueba recorre historico.
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
from app.core.modelos_posicion import DatosCondonacion, DatosReembolso
from app.core.modelos_suplemento import DatosSuplemento
from app.core.unidad_trabajo import UnidadDeTrabajo
from app.services.compartidos_service import (
    DatosGastoCompartido,
    GastosCompartidosService,
)
from app.services.correcciones_service import DatosCorreccion
from conftest import leer_fila
from test_109_op12_posiciones import alta, delta

D = decimal.Decimal
F = dt.date.fromisoformat
ACTIVACION = "F04-D046 A08-bis:%"


# ==================================================================
# Utilidades
# ==================================================================

def _crear(servicio, contexto, *, presupuestable=True, localizacion="DESCONOCIDA",
           tipo="GASTO", localidad_id=None) -> uuid.UUID:
    hecho_id = uuid.uuid4()
    servicio.crear_hecho(
        contexto,
        DatosCreacionHecho(
            hecho_id=hecho_id,
            fecha_hecho=F("2027-06-01"),
            moneda="EUR",
            presupuestable=presupuestable,
            estado_localizacion=localizacion,
            localidad_id=localidad_id,
            tipo_hecho_codigo=tipo,
            importe_total=D("100.0000"),
        ),
    )
    return hecho_id


def _efecto(tipo="GASTO", importe="100.0000", efecto_id=None) -> DatosEfecto:
    return DatosEfecto(
        efecto_id=efecto_id or uuid.uuid4(),
        tipo_efecto=tipo,
        importe_delta=D(importe),
        estado_atribucion="NO_DISPONIBLE",
    )


def _hecho(admin, contexto, hecho_id):
    return leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT presupuestable, estado_localizacion, localidad_id, row_version "
        "FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )


def _efectos(admin, contexto, hecho_id) -> int:
    return leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s",
        (hecho_id,),
    )[0]


def _auditorias(admin, contexto, hecho_id) -> int:
    return leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.auditoria WHERE registro_id = %s",
        (hecho_id,),
    )[0]


def _existe_hecho(admin, contexto, hecho_id) -> bool:
    return leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )[0] == 1


def _rechazo(fn, codigo=CodigoError.ENTRADA_INVALIDA):
    with pytest.raises(ErrorMotor) as excinfo:
        fn()
    assert excinfo.value.codigo is codigo
    return excinfo.value


# ==================================================================
# 10 · Hecho sin GASTO/INGRESO: booleano fisico presente, INACTIVO
# ==================================================================

@pytest.mark.parametrize("almacenado", [True, False])
def test_10_sin_gasto_ni_ingreso_el_booleano_existe_pero_esta_inactivo(
    servicio, servicio_efectos, contexto, admin, almacenado
) -> None:
    """#10 · v0.3 §3. Un hecho solo-INVERSION conserva fisicamente el
    booleano (NOT NULL de 0330) y OP-04 no pide ni acepta decision: sin
    GASTO/INGRESO la decision no tiene significado."""
    hecho_id = _crear(servicio, contexto, presupuestable=almacenado,
                      tipo="APORTACION_INVERSION")
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=1,
        efectos=[_efecto("INVERSION")],
    )
    assert _hecho(admin, contexto, hecho_id)[0] is almacenado
    _rechazo(lambda: servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=2,
        efectos=[_efecto("INVERSION")], presupuestable=True,
    ))


# ==================================================================
# 13..16 · OP-04 en la transicion
# ==================================================================

def test_13_op04_primer_gasto_exige_decision_y_la_persiste(
    servicio, servicio_efectos, contexto, admin
) -> None:
    """#13 · v0.3 §5. OP-04 introduce el primer GASTO: con decision explicita
    se persiste la decision aportada (false sobre un true inactivo), la
    version sube UNA vez y la activacion queda auditada."""
    hecho_id = _crear(servicio, contexto, presupuestable=True)
    resultado = servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=1,
        efectos=[_efecto()], presupuestable=False,
    )
    assert resultado.row_version == 2
    assert _hecho(admin, contexto, hecho_id)[0] is False
    assert leer_fila(
        admin, contexto.owner_user_id,
        "SELECT datos_antes->>'presupuestable', datos_despues->>'presupuestable' "
        "FROM gapto.auditoria WHERE registro_id = %s AND accion = 'ACTUALIZAR' "
        "AND motivo LIKE %s",
        (hecho_id, ACTIVACION),
    ) == ("true", "false")


def test_14_op04_sin_decision_rollback_total(
    servicio, servicio_efectos, contexto, admin
) -> None:
    """#14 · v0.3 §5. Sin decision en la transicion: ENTRADA_INVALIDA y
    NADA confirmado (ni efectos, ni version, ni auditoria nueva)."""
    hecho_id = _crear(servicio, contexto)
    auditorias = _auditorias(admin, contexto, hecho_id)
    _rechazo(lambda: servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=1,
        efectos=[_efecto(), _efecto("INGRESO", "5.0000")],
    ))
    assert _efectos(admin, contexto, hecho_id) == 0
    assert _hecho(admin, contexto, hecho_id)[3] == 1
    assert _auditorias(admin, contexto, hecho_id) == auditorias


@pytest.mark.parametrize("almacenado", [True, False])
def test_15_16_valor_inactivo_almacenado_no_sustituye_decision_en_op04(
    servicio, servicio_efectos, contexto, admin, almacenado
) -> None:
    """#15 (true) / #16 (false) · v0.3 §3/§5. Hecho con INVERSION previa y
    `presupuestable` almacenado: el primer GASTO posterior por OP-04 sigue
    exigiendo decision. El booleano de la etapa inactiva no cuenta."""
    hecho_id = _crear(servicio, contexto, presupuestable=almacenado,
                      tipo="APORTACION_INVERSION")
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=1,
        efectos=[_efecto("INVERSION")],
    )
    _rechazo(lambda: servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=2,
        efectos=[_efecto("GASTO", "2.0000")],
    ))
    assert _efectos(admin, contexto, hecho_id) == 1
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=2,
        efectos=[_efecto("GASTO", "2.0000")], presupuestable=almacenado,
    )
    # La decision se persiste Y se audita aunque coincida con el valor previo.
    assert leer_fila(
        admin, contexto.owner_user_id,
        "SELECT count(*) FROM gapto.auditoria WHERE registro_id = %s "
        "AND accion = 'ACTUALIZAR' AND motivo LIKE %s",
        (hecho_id, ACTIVACION),
    )[0] == 1


def test_op04_sin_transicion_rechaza_decision_explicita(
    servicio, servicio_efectos, contexto, admin
) -> None:
    """v0.3 §5 / E01 §5. Con GASTO ya presente, un `presupuestable` en OP-04
    carece de significado (el escalar se corrige con OP-02) y se rechaza."""
    hecho_id = _crear(servicio, contexto)
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=1,
        efectos=[_efecto()], presupuestable=True,
    )
    _rechazo(lambda: servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=2,
        efectos=[_efecto("GASTO", "1.0000")], presupuestable=True,
    ))
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=2,
        efectos=[_efecto("GASTO", "1.0000")],
    )
    assert _efectos(admin, contexto, hecho_id) == 2


def test_op04_reintento_con_otra_decision_es_otra_intencion(
    servicio, servicio_efectos, contexto
) -> None:
    """F04-D006 + A08-bis. El reintento exacto es idempotente; con los mismos
    UUID y otra decision es otra intencion."""
    hecho_id = _crear(servicio, contexto)
    uno = _efecto()
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=1,
        efectos=[uno], presupuestable=True,
    )
    repetido = servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=1,
        efectos=[uno], presupuestable=True,
    )
    assert repetido.idempotente
    _rechazo(
        lambda: servicio_efectos.registrar_efectos(
            contexto, hecho_id=hecho_id, row_version_esperada=1,
            efectos=[uno], presupuestable=False,
        ),
        CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
    )


# ==================================================================
# 15/16 en OP-21 (valor inactivo previo true)
# ==================================================================

def test_15_op21_true_inactivo_no_sustituye_decision(
    servicio, servicio_efectos, servicio_correcciones, contexto, admin
) -> None:
    """#15 en OP-21 · v0.3 §7. test_136 cubre el false inactivo; aqui el
    true inactivo tampoco vale como decision."""
    hecho_id = _crear(servicio, contexto, presupuestable=True,
                      tipo="APORTACION_INVERSION")
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=1,
        efectos=[_efecto("INVERSION")],
    )
    _rechazo(lambda: servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id, row_version_esperada=2,
            motivo="la comision se omitio", efectos_a_crear=(_efecto("GASTO", "2.0000"),),
        ),
    ))
    assert _efectos(admin, contexto, hecho_id) == 1
    assert _hecho(admin, contexto, hecho_id)[3] == 2


# ==================================================================
# 17..21 · Localizacion
# ==================================================================

def _gasto_original(servicio, servicio_efectos, contexto) -> uuid.UUID:
    hecho_id = _crear(servicio, contexto)
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=1,
        efectos=[_efecto()], presupuestable=True,
    )
    return hecho_id


def test_17_op13_gasto_con_no_aplica_se_rechaza(
    servicio, servicio_efectos, servicio_devoluciones, contexto, admin
) -> None:
    """#17 · v0.3 §9. Devolucion de GASTO declarando NO_APLICA."""
    original = _gasto_original(servicio, servicio_efectos, contexto)
    datos = DatosDevolucion(
        hecho_id=uuid.uuid4(), efecto_id=uuid.uuid4(), relacion_id=uuid.uuid4(),
        hecho_original_id=original, tipo_efecto="GASTO", importe=D("40.0000"),
        fecha_hecho=F("2027-06-10"), moneda="EUR", concepto="devolucion",
        presupuestable=True, estado_localizacion="NO_APLICA",
    )
    _rechazo(lambda: servicio_devoluciones.devolver(contexto, datos))
    assert not _existe_hecho(admin, contexto, datos.hecho_id)


def test_18_op18_gasto_con_no_aplica_se_rechaza(
    servicio_suplementos, contexto, admin
) -> None:
    """#18 · v0.3 §9. Suplemento GASTO declarando NO_APLICA."""
    datos = DatosSuplemento(
        hecho_id=uuid.uuid4(), efecto_id=uuid.uuid4(), tipo_efecto="GASTO",
        importe_delta=D("3.5000"), fecha_hecho=F("2027-06-12"), moneda="EUR",
        fecha_demostrada=True, concepto="recargo",
        presupuestable=True, estado_localizacion="NO_APLICA",
    )
    _rechazo(lambda: servicio_suplementos.registrar(contexto, datos))
    assert not _existe_hecho(admin, contexto, datos.hecho_id)


def test_19_9_devolucion_puramente_posicional_admite_no_aplica(
    servicio, servicio_efectos, servicio_devoluciones, contexto, admin
) -> None:
    """#19 y #9 · v0.3 §10. Devolucion de DEUDA (sin GASTO/INGRESO): el
    llamante puede declarar NO_APLICA; el `false` persistido es INACTIVO."""
    original = _crear(servicio, contexto, presupuestable=False)
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=original, row_version_esperada=1,
        efectos=[_efecto("DEUDA", "100.0000")],
    )
    datos = DatosDevolucion(
        hecho_id=uuid.uuid4(), efecto_id=uuid.uuid4(), relacion_id=uuid.uuid4(),
        hecho_original_id=original, tipo_efecto="DEUDA", importe=D("40.0000"),
        fecha_hecho=F("2027-06-10"), moneda="EUR", concepto="devolucion deuda",
        estado_localizacion="NO_APLICA",
    )
    servicio_devoluciones.devolver(contexto, datos)
    assert _hecho(admin, contexto, datos.hecho_id)[:2] == (False, "NO_APLICA")


def test_20_op04_gasto_en_hecho_no_aplica_se_rechaza(
    servicio, servicio_efectos, contexto, admin
) -> None:
    """#20 · v0.3 §9. OP-04 escribe GASTO en un hecho NO_APLICA: rechazo,
    aunque la decision presupuestaria venga explicita."""
    hecho_id = _crear(servicio, contexto, localizacion="NO_APLICA")
    _rechazo(lambda: servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=1,
        efectos=[_efecto()], presupuestable=True,
    ))
    assert _efectos(admin, contexto, hecho_id) == 0
    # Una naturaleza no presupuestaria sigue admitida en ese mismo hecho.
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=1,
        efectos=[_efecto("DEUDA", "10.0000")],
    )


def test_21_op21_crear_gasto_en_hecho_no_aplica_se_rechaza(
    servicio, servicio_efectos, servicio_correcciones, contexto, admin
) -> None:
    """#21 · v0.3 §9. OP-21 produce GASTO en un hecho NO_APLICA: rechazo y
    rollback total, aunque la decision presupuestaria venga explicita."""
    hecho_id = _crear(servicio, contexto, presupuestable=False,
                      localizacion="NO_APLICA", tipo="APORTACION_INVERSION")
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=1,
        efectos=[_efecto("INVERSION")],
    )
    _rechazo(lambda: servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id, row_version_esperada=2, motivo="comision omitida",
            efectos_a_crear=(_efecto("GASTO", "2.0000"),), presupuestable=True,
        ),
    ))
    assert _efectos(admin, contexto, hecho_id) == 1
    assert _hecho(admin, contexto, hecho_id)[0::3] == (False, 2)


def test_21b_op21_reclasificar_a_gasto_en_hecho_no_aplica_se_rechaza(
    servicio, servicio_efectos, servicio_correcciones, contexto, admin
) -> None:
    """#21 (variante UPDATE) · v0.3 §9. Reclasificar un efecto a GASTO."""
    hecho_id = _crear(servicio, contexto, presupuestable=False,
                      localizacion="NO_APLICA", tipo="APORTACION_INVERSION")
    efecto_id = uuid.uuid4()
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=1,
        efectos=[_efecto("INVERSION", efecto_id=efecto_id)],
    )
    _rechazo(lambda: servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id, row_version_esperada=2, motivo="naturaleza mal",
            efectos_a_actualizar={efecto_id: {"tipo_efecto": "GASTO"}},
            presupuestable=True,
        ),
    ))
    assert leer_fila(
        admin, contexto.owner_user_id,
        "SELECT tipo_efecto FROM gapto.hecho_efectos WHERE id = %s", (efecto_id,),
    ) == ("INVERSION",)


def test_op21_corregir_importe_en_historico_no_aplica_no_activa_la_guarda(
    servicio, servicio_efectos, servicio_correcciones, contexto, admin
) -> None:
    """v0.3 §11 (frontera hacia adelante). Un GASTO ya existente en un hecho
    NO_APLICA (representacion historica, montada aqui por SQL) puede
    corregirse de importe: OP-21 no escribe la dimension y no reinterpreta."""
    hecho_id = _crear(servicio, contexto)
    efecto_id = uuid.uuid4()
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=1,
        efectos=[_efecto(efecto_id=efecto_id)], presupuestable=True,
    )
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute(
            "SELECT set_config('gapto.owner_user_id', %s, false)",
            (str(contexto.owner_user_id),),
        )
        try:
            cursor.execute(
                "UPDATE gapto.hechos_financieros "
                "SET estado_localizacion = 'NO_APLICA' WHERE id = %s",
                (hecho_id,),
            )
        finally:
            cursor.execute("RESET ALL")
    admin.commit()
    version = _hecho(admin, contexto, hecho_id)[3]
    servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id, row_version_esperada=version, motivo="importe falso",
            efectos_a_actualizar={efecto_id: {"importe_delta": D("90.0000")}},
        ),
    )
    assert _hecho(admin, contexto, hecho_id)[1] == "NO_APLICA"


# ==================================================================
# 22..23 y 25..31 · Condonacion
# ==================================================================

@pytest.fixture()
def derecho(servicio_posiciones, contexto, contraparte):
    datos = alta(contraparte)
    resultado = servicio_posiciones.crear_posicion(contexto, datos)
    return datos.entidad_id, resultado


def _condonar(servicio_posiciones, contexto, derecho, **extra):
    entidad_id, creada = derecho
    datos = DatosCondonacion(
        delta=delta("30.0000"),
        declara_gasto_soportado=True,
        declara_coste_no_reconocido=True,
        efecto_gasto_id=uuid.uuid4(),
        **extra,
    )
    servicio_posiciones.condonar_derecho(
        contexto, entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version, datos=datos,
    )
    return datos


@pytest.mark.parametrize("decision", [True, False])
def test_25_26_29_condonacion_con_gasto_persiste_la_decision(
    servicio_posiciones, contexto, admin, derecho, decision
) -> None:
    """#25 (true) / #26 (false) / #29 · v0.3 §8 + E01 §3. La decision
    aportada se persiste; sin dato de localidad -> DESCONOCIDA."""
    datos = _condonar(servicio_posiciones, contexto, derecho,
                      presupuestable=decision)
    assert _hecho(admin, contexto, datos.delta.hecho_id)[:3] == (
        decision, "DESCONOCIDA", None,
    )


def test_22_27_condonacion_con_gasto_sin_decision_se_rechaza(
    servicio_posiciones, contexto, admin, derecho
) -> None:
    """#22 / #27 · E01 §3. Sin decision: rechazo, sin hecho ni efectos."""
    entidad_id, creada = derecho
    datos = DatosCondonacion(
        delta=delta("30.0000"), declara_gasto_soportado=True,
        declara_coste_no_reconocido=True, efecto_gasto_id=uuid.uuid4(),
    )
    _rechazo(lambda: servicio_posiciones.condonar_derecho(
        contexto, entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version, datos=datos,
    ))
    assert not _existe_hecho(admin, contexto, datos.delta.hecho_id)


def test_23_28_condonacion_con_gasto_y_no_aplica_se_rechaza(
    servicio_posiciones, contexto, admin, derecho
) -> None:
    """#23 / #28 · v0.3 §9 + E01 §3."""
    entidad_id, creada = derecho
    datos = DatosCondonacion(
        delta=delta("30.0000"), declara_gasto_soportado=True,
        declara_coste_no_reconocido=True, efecto_gasto_id=uuid.uuid4(),
        presupuestable=True, estado_localizacion="NO_APLICA",
    )
    _rechazo(lambda: servicio_posiciones.condonar_derecho(
        contexto, entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version, datos=datos,
    ))
    assert not _existe_hecho(admin, contexto, datos.delta.hecho_id)


def test_30_condonacion_localidad_coherente_con_estado(
    servicio_posiciones, contexto, admin, derecho, localidad
) -> None:
    """#30 · E01 §3. Con localidad y sin estado -> CONOCIDA (es el dato
    aportado, no una inferencia)."""
    datos = _condonar(servicio_posiciones, contexto, derecho,
                      presupuestable=True, localidad_id=localidad)
    fila = _hecho(admin, contexto, datos.delta.hecho_id)
    assert fila[1] == "CONOCIDA" and str(fila[2]) == str(localidad)


def test_30b_condonacion_localidad_incoherente_no_confirma_nada(
    servicio_posiciones, contexto, admin, derecho, localidad
) -> None:
    """#30 · E01 §3. DESCONOCIDA con localidad es incoherente: lo rechaza el
    CHECK fisico de 0040 y no queda nada confirmado."""
    entidad_id, creada = derecho
    datos = DatosCondonacion(
        delta=delta("30.0000"), declara_gasto_soportado=True,
        declara_coste_no_reconocido=True, efecto_gasto_id=uuid.uuid4(),
        presupuestable=True, estado_localizacion="DESCONOCIDA",
        localidad_id=localidad,
    )
    with pytest.raises((ErrorMotor, psycopg.Error)):
        servicio_posiciones.condonar_derecho(
            contexto, entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version, datos=datos,
        )
    assert not _existe_hecho(admin, contexto, datos.delta.hecho_id)


def test_condonacion_sin_gasto_no_admite_decision_ni_localizacion(
    servicio_posiciones, contexto, derecho
) -> None:
    """E01 §2/§3. Sin GASTO declarado el hecho es puramente posicional."""
    entidad_id, creada = derecho
    for extra in ({"presupuestable": False}, {"estado_localizacion": "DESCONOCIDA"}):
        datos = DatosCondonacion(delta=delta("30.0000"), **extra)
        _rechazo(lambda: servicio_posiciones.condonar_derecho(
            contexto, entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version, datos=datos,
        ))


def test_condonacion_reintento_con_otra_decision_es_otra_intencion(
    servicio_posiciones, contexto, derecho
) -> None:
    """Mandato 32 + E01. Reintento exacto idempotente; otra decision con los
    mismos UUID es otra intencion."""
    entidad_id, creada = derecho
    datos = DatosCondonacion(
        delta=delta("30.0000"), declara_gasto_soportado=True,
        declara_coste_no_reconocido=True, efecto_gasto_id=uuid.uuid4(),
        presupuestable=True,
    )
    kwargs = dict(entidad_id=entidad_id,
                  entidad_row_version_esperada=creada.entidad_row_version)
    servicio_posiciones.condonar_derecho(contexto, datos=datos, **kwargs)
    assert servicio_posiciones.condonar_derecho(contexto, datos=datos, **kwargs).idempotente
    otra = DatosCondonacion(
        delta=datos.delta, declara_gasto_soportado=True,
        declara_coste_no_reconocido=True, efecto_gasto_id=datos.efecto_gasto_id,
        presupuestable=False,
    )
    _rechazo(
        lambda: servicio_posiciones.condonar_derecho(contexto, datos=otra, **kwargs),
        CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
    )


def test_31_resto_de_operaciones_de_posiciones_sin_cambio_observable(
    servicio_posiciones, contexto, admin, derecho
) -> None:
    """#31 · E01 §2. Alta, reembolso y condonacion SIN GASTO atraviesan los
    mismos helpers parametrizados y conservan exactamente false/NO_APLICA."""
    entidad_id, creada = derecho
    reembolso = DatosReembolso(delta=delta("10.0000"))
    tras_reembolso = servicio_posiciones.reembolsar(
        contexto, entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version, datos=reembolso,
    )
    condonacion = DatosCondonacion(delta=delta("10.0000"))
    servicio_posiciones.condonar_derecho(
        contexto, entidad_id=entidad_id,
        entidad_row_version_esperada=tras_reembolso.entidad_row_version,
        datos=condonacion,
    )
    for hecho_id in (creada.hecho_id, reembolso.delta.hecho_id,
                     condonacion.delta.hecho_id):
        assert _hecho(admin, contexto, hecho_id)[:3] == (False, "NO_APLICA", None)


# ==================================================================
# 24 · OP-19 propaga la decision a OP-04
# ==================================================================

@pytest.fixture()
def servicio_compartidos(unidad: UnidadDeTrabajo) -> GastosCompartidosService:
    from app.services.previsiones_service import impacto_correccion_ancla

    return GastosCompartidosService(unidad, impacto_ancla=impacto_correccion_ancla)


def _op19(presupuestable, localizacion="DESCONOCIDA") -> DatosGastoCompartido:
    return DatosGastoCompartido(
        hecho=DatosCreacionHecho(
            hecho_id=uuid.uuid4(), fecha_hecho=F("2027-06-01"), moneda="EUR",
            presupuestable=presupuestable, estado_localizacion=localizacion,
            tipo_hecho_codigo="GASTO", concepto="cena compartida",
            importe_total=D("44.5000"),
        ),
        efectos=[_efecto("GASTO", "44.5000")],
    )


@pytest.mark.parametrize("decision", [True, False])
def test_24_op19_propaga_la_decision_explicita(
    servicio_compartidos, contexto, admin, decision
) -> None:
    """#24 · v0.3 §6. OP-19 no queda bloqueada por la guarda de OP-04: la
    decision de `datos.hecho` es la que se persiste, sin cambio de
    atomicidad ni de efectos."""
    datos = _op19(decision)
    resultado = servicio_compartidos.registrar_gasto_compartido(contexto, datos)
    assert resultado.posiciones_creadas == 0
    assert _hecho(admin, contexto, datos.hecho.hecho_id)[:2] == (decision, "DESCONOCIDA")
    assert _efectos(admin, contexto, datos.hecho.hecho_id) == 1


def test_24b_op19_con_no_aplica_es_atomica(
    servicio_compartidos, contexto, admin
) -> None:
    """#24 (atomicidad) · v0.3 §6/§9. Si OP-04 rechaza por NO_APLICA, OP-19
    no deja ni el hecho creado por su OP-01 interna."""
    datos = _op19(True, localizacion="NO_APLICA")
    _rechazo(lambda: servicio_compartidos.registrar_gasto_compartido(contexto, datos))
    assert not _existe_hecho(admin, contexto, datos.hecho.hecho_id)
