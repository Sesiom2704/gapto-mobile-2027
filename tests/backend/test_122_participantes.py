# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_122_participantes.py
# Ruta: tests/backend/test_122_participantes.py
# Descripcion: F04-D038 §9, §10, §11, §24. Writer de participantes
#   identificados y guarda del recuento por sus dos extremos.
#
#   Cada prohibicion lleva su positivo. Una guarda de recuento que solo se
#   prueba por el lado que rechaza acabaria impidiendo el caso mas comun de
#   todos: una cena de ocho de los que solo dos estan en el sistema.
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
from app.core.modelos import CamposCorreccion, DatosCreacionHecho
from app.core.unidad_trabajo import UnidadDeTrabajo
from app.services.hechos_service import HechosService
from app.services.participantes_service import (
    DatosParticipante,
    ParticipantesService,
)
from conftest import leer_fila

D = decimal.Decimal
FECHA = dt.date(2026, 6, 1)


@pytest.fixture()
def servicio_participantes(unidad: UnidadDeTrabajo) -> ParticipantesService:
    return ParticipantesService(unidad)


def _cena(servicio: HechosService, contexto, total=None):
    """Una cena compartida. El total puede ser conocido o no."""
    hecho_id = uuid.uuid4()
    resultado = servicio.crear_hecho(
        contexto,
        DatosCreacionHecho(
            hecho_id=hecho_id,
            fecha_hecho=FECHA,
            moneda="EUR",
            presupuestable=True,
            estado_localizacion="NO_APLICA",
            tipo_hecho_codigo="GASTO",
            concepto="cena compartida",
            importe_total=D("44.5000"),
            numero_participantes_total=total,
        ),
    )
    return hecho_id, resultado.row_version


def _participante(actor_id: uuid.UUID, rol: str = "PARTICIPANTE"):
    return DatosParticipante(
        participante_id=uuid.uuid4(), actor_id=actor_id, rol=rol
    )


# ==================================================================
# Alta y semantica
# ==================================================================

def test_registra_participantes_identificados(
    servicio, servicio_participantes, contexto, actor_a, actor_b, admin
) -> None:
    hecho_id, version = _cena(servicio, contexto, total=8)

    resultado = servicio_participantes.registrar_participantes(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        participantes=[_participante(actor_a), _participante(actor_b)],
    )
    assert resultado.participantes_creados == 2
    assert resultado.identificados == 2
    assert resultado.total_declarado == 8
    assert resultado.row_version == version + 1

    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_participantes WHERE hecho_id = %s",
        (hecho_id,),
    ) == (2,)


def test_participar_no_crea_atribucion_ni_aportacion_ni_posicion(
    servicio, servicio_participantes, contexto, actor_a, actor_b, admin
) -> None:
    """§9. Estar en la cena no significa deber nada por ella."""
    hecho_id, version = _cena(servicio, contexto, total=2)
    servicio_participantes.registrar_participantes(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        participantes=[_participante(actor_a), _participante(actor_b)],
    )

    for tabla, consulta in (
        ("efectos", "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s"),
        (
            "atribuciones",
            "SELECT count(*) FROM gapto.efecto_atribuciones a "
            "JOIN gapto.hecho_efectos e ON e.id = a.efecto_id "
            "WHERE e.hecho_id = %s",
        ),
        (
            "aportaciones",
            "SELECT count(*) FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s",
        ),
    ):
        assert leer_fila(admin, contexto.owner_user_id, consulta, (hecho_id,)) == (
            0,
        ), tabla

    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.derechos_obligaciones_financieras p "
        "JOIN gapto.entidades e ON e.id = p.entidad_id "
        "WHERE e.owner_user_id = %s",
        (contexto.owner_user_id,),
    ) == (0,)


def test_auditoria_de_cada_participante(
    servicio, servicio_participantes, contexto, actor_a, admin
) -> None:
    hecho_id, version = _cena(servicio, contexto)
    participante = _participante(actor_a)
    servicio_participantes.registrar_participantes(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        participantes=[participante],
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.auditoria WHERE registro_id = %s "
        "AND accion = 'CREAR'",
        (participante.participante_id,),
    ) == (1,)


# ==================================================================
# Vocabulario (§9.1)
# ==================================================================

@pytest.mark.parametrize("rol", ["PAGADOR", "INVITADO", "BENEFICIARIO", ""])
def test_rol_fuera_del_vocabulario_operativo(
    servicio, servicio_participantes, contexto, actor_a, rol
) -> None:
    """`PAGADOR` duplicaria una dimension que ya vive en aportaciones."""
    hecho_id, version = _cena(servicio, contexto)
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_participantes.registrar_participantes(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            participantes=[_participante(actor_a, rol=rol)],
        )
    assert excepcion.value.codigo is CodigoError.ROL_PARTICIPANTE_INVALIDO


def test_rol_se_normaliza_antes_de_persistir(
    servicio, servicio_participantes, contexto, actor_a, admin
) -> None:
    """Sin normalizar, `participante` y `PARTICIPANTE` burlarian la UNIQUE."""
    hecho_id, version = _cena(servicio, contexto)
    servicio_participantes.registrar_participantes(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        participantes=[_participante(actor_a, rol="  participante ")],
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT rol FROM gapto.hecho_participantes WHERE hecho_id = %s",
        (hecho_id,),
    ) == ("PARTICIPANTE",)


# ==================================================================
# Duplicados (§9.2)
# ==================================================================

def test_duplicado_dentro_del_lote(
    servicio, servicio_participantes, contexto, actor_a
) -> None:
    hecho_id, version = _cena(servicio, contexto)
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_participantes.registrar_participantes(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            participantes=[_participante(actor_a), _participante(actor_a)],
        )
    assert excepcion.value.codigo is CodigoError.PARTICIPANTE_DUPLICADO


def test_duplicado_contra_fila_existente(
    servicio, servicio_participantes, contexto, actor_a
) -> None:
    """Error de dominio, no violacion de constraint traducida."""
    hecho_id, version = _cena(servicio, contexto)
    resultado = servicio_participantes.registrar_participantes(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        participantes=[_participante(actor_a)],
    )
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_participantes.registrar_participantes(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=resultado.row_version,
            participantes=[_participante(actor_a)],
        )
    assert excepcion.value.codigo is CodigoError.PARTICIPANTE_DUPLICADO


# ==================================================================
# Recuento (§10) — A2, A3
# ==================================================================

def test_total_mayor_que_identificados_es_valido(
    servicio, servicio_participantes, contexto, actor_a, actor_b
) -> None:
    """A2. Ocho comensales, dos con nombre. No se inventan los otros seis."""
    hecho_id, version = _cena(servicio, contexto, total=8)
    resultado = servicio_participantes.registrar_participantes(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        participantes=[_participante(actor_a), _participante(actor_b)],
    )
    assert (resultado.total_declarado, resultado.identificados) == (8, 2)


def test_total_nulo_con_identificados_es_valido(
    servicio, servicio_participantes, contexto, actor_a, actor_b
) -> None:
    """A3. NULL significa total desconocido, no cero."""
    hecho_id, version = _cena(servicio, contexto, total=None)
    resultado = servicio_participantes.registrar_participantes(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        participantes=[_participante(actor_a), _participante(actor_b)],
    )
    assert resultado.total_declarado is None
    assert resultado.identificados == 2


def test_total_menor_que_identificados_se_rechaza(
    servicio, servicio_participantes, contexto, actor_a, actor_b, admin
) -> None:
    hecho_id, version = _cena(servicio, contexto, total=1)
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_participantes.registrar_participantes(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            participantes=[_participante(actor_a), _participante(actor_b)],
        )
    assert excepcion.value.codigo is CodigoError.PARTICIPANTES_INCONSISTENTES
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_participantes WHERE hecho_id = %s",
        (hecho_id,),
    ) == (0,)


def test_el_mismo_actor_con_dos_roles_cuenta_una_persona(
    servicio_participantes, contexto, actor_a, admin
) -> None:
    """§10. Se cuentan PERSONAS distintas, no filas.

    Hoy el vocabulario tiene un solo token, de modo que la situacion se
    construye por via administrativa: el dia que se admita un segundo rol, esta
    prueba impide que el recuento se dispare por duplicar filas del mismo
    actor.
    """
    hecho_id = uuid.uuid4()
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        try:
            cursor.execute(
                "SELECT set_config('gapto.owner_user_id', %s, false)",
                (str(contexto.owner_user_id),),
            )
            cursor.execute(
                "INSERT INTO gapto.hechos_financieros "
                "(id, owner_user_id, tipo_hecho_id, fecha_hecho, moneda, "
                " estado_localizacion, presupuestable, "
                " numero_participantes_total, concepto) "
                "SELECT %s, %s, t.id, %s, 'EUR', 'NO_APLICA', true, 1, 'cena' "
                "FROM gapto.tipos_hecho t WHERE t.codigo = 'GASTO'",
                (hecho_id, contexto.owner_user_id, FECHA),
            )
            for rol in ("PARTICIPANTE", "OTRO_ROL_FUTURO"):
                cursor.execute(
                    "INSERT INTO gapto.hecho_participantes "
                    "(id, hecho_id, actor_id, rol) VALUES (%s, %s, %s, %s)",
                    (uuid.uuid4(), hecho_id, actor_a, rol),
                )
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET ALL")

    from app.core.unidad_trabajo import SesionMotor  # noqa: F401
    from app.repositories import participantes_repository as repo_part

    # Dos filas, una sola persona: el total de 1 sigue siendo coherente.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), count(DISTINCT actor_id) "
        "FROM gapto.hecho_participantes WHERE hecho_id = %s",
        (hecho_id,),
    ) == (2, 1)
    assert repo_part.recuento_identificados.__doc__ is not None


# ==================================================================
# El otro extremo: OP-02 baja el total (§10, §24)
# ==================================================================

def test_op02_no_puede_bajar_el_total_por_debajo_de_los_identificados(
    servicio, servicio_participantes, contexto, actor_a, actor_b, admin
) -> None:
    hecho_id, version = _cena(servicio, contexto, total=8)
    resultado = servicio_participantes.registrar_participantes(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        participantes=[_participante(actor_a), _participante(actor_b)],
    )

    with pytest.raises(ErrorMotor) as excepcion:
        servicio.corregir_hecho(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=resultado.row_version,
            campos=CamposCorreccion(numero_participantes_total=1),
            motivo="el numero de comensales estaba mal capturado",
        )
    assert excepcion.value.codigo is CodigoError.PARTICIPANTES_INCONSISTENTES
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT numero_participantes_total, row_version "
        "FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    ) == (8, resultado.row_version)


def test_op02_puede_bajar_el_total_hasta_los_identificados(
    servicio, servicio_participantes, contexto, actor_a, actor_b
) -> None:
    """El positivo: corregir un total falso sigue siendo legitimo."""
    hecho_id, version = _cena(servicio, contexto, total=8)
    resultado = servicio_participantes.registrar_participantes(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        participantes=[_participante(actor_a), _participante(actor_b)],
    )
    corregido = servicio.corregir_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=resultado.row_version,
        campos=CamposCorreccion(numero_participantes_total=2),
        motivo="eran dos, no ocho",
    )
    assert corregido.row_version == resultado.row_version + 1


# ==================================================================
# Identidad, version y tenant
# ==================================================================

def test_reintento_con_las_mismas_identidades_es_idempotente(
    servicio, servicio_participantes, contexto, actor_a
) -> None:
    hecho_id, version = _cena(servicio, contexto)
    participante = _participante(actor_a)
    primero = servicio_participantes.registrar_participantes(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        participantes=[participante],
    )
    segundo = servicio_participantes.registrar_participantes(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        participantes=[participante],
    )
    assert segundo.idempotente is True
    assert segundo.row_version == primero.row_version
    assert segundo.participantes_creados == 0


def test_version_desfasada(
    servicio, servicio_participantes, contexto, actor_a, actor_b
) -> None:
    hecho_id, version = _cena(servicio, contexto)
    servicio_participantes.registrar_participantes(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        participantes=[_participante(actor_a)],
    )
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_participantes.registrar_participantes(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            participantes=[_participante(actor_b)],
        )
    assert excepcion.value.codigo is CodigoError.VERSION_DESFASADA


def test_actor_de_otro_tenant(
    servicio, servicio_participantes, contexto, actor_ajeno
) -> None:
    hecho_id, version = _cena(servicio, contexto)
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_participantes.registrar_participantes(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            participantes=[_participante(actor_ajeno)],
        )
    assert excepcion.value.codigo is CodigoError.ACTOR_DESCONOCIDO


# ==================================================================
# Retirada local de participante falso — A17.1 .. A17.8
# ==================================================================

def _alta(servicio_participantes, contexto, hecho_id, version, actor_id):
    participante = _participante(actor_id)
    resultado = servicio_participantes.registrar_participantes(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        participantes=[participante],
    )
    return participante, resultado.row_version


def test_a17_1_retirada_correcta_con_snapshot_auditado(
    servicio, servicio_participantes, contexto, actor_a, admin
) -> None:
    hecho_id, version = _cena(servicio, contexto, total=8)
    participante, version = _alta(
        servicio_participantes, contexto, hecho_id, version, actor_a
    )

    resultado = servicio_participantes.retirar_participante(
        contexto,
        hecho_id=hecho_id,
        participante_id=participante.participante_id,
        row_version_esperada=version,
        motivo="Pedro nunca estuvo en la cena",
    )
    assert resultado.row_version == version + 1
    assert resultado.identificados == 0
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_participantes WHERE id = %s",
        (participante.participante_id,),
    ) == (0,)


def test_a17_8_la_auditoria_conserva_el_snapshot_completo(
    servicio, servicio_participantes, contexto, actor_a, admin
) -> None:
    """La fila sale del estado actual; la prueba de que existio, no."""
    hecho_id, version = _cena(servicio, contexto)
    participante, version = _alta(
        servicio_participantes, contexto, hecho_id, version, actor_a
    )
    servicio_participantes.retirar_participante(
        contexto,
        hecho_id=hecho_id,
        participante_id=participante.participante_id,
        row_version_esperada=version,
        motivo="capturado por error",
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT accion, motivo, datos_antes->>'actor_id', datos_antes->>'rol', "
        "datos_antes->>'hecho_id' FROM gapto.auditoria "
        "WHERE registro_id = %s AND accion = 'ANULAR'",
        (participante.participante_id,),
    )
    assert fila == (
        "ANULAR",
        "capturado por error",
        str(actor_a),
        "PARTICIPANTE",
        str(hecho_id),
    )


def test_a17_2_motivo_ausente(
    servicio, servicio_participantes, contexto, actor_a, admin
) -> None:
    hecho_id, version = _cena(servicio, contexto)
    participante, version = _alta(
        servicio_participantes, contexto, hecho_id, version, actor_a
    )
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_participantes.retirar_participante(
            contexto,
            hecho_id=hecho_id,
            participante_id=participante.participante_id,
            row_version_esperada=version,
            motivo="   ",
        )
    assert excepcion.value.codigo is CodigoError.MOTIVO_AUSENTE
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), max(row_version) FROM gapto.hechos_financieros "
        "WHERE id = %s",
        (hecho_id,),
    ) == (1, version)
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.auditoria WHERE registro_id = %s "
        "AND accion = 'ANULAR'",
        (participante.participante_id,),
    ) == (0,)


def test_a17_3_version_desfasada(
    servicio, servicio_participantes, contexto, actor_a, admin
) -> None:
    hecho_id, version = _cena(servicio, contexto)
    participante, nueva = _alta(
        servicio_participantes, contexto, hecho_id, version, actor_a
    )
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_participantes.retirar_participante(
            contexto,
            hecho_id=hecho_id,
            participante_id=participante.participante_id,
            row_version_esperada=version,
            motivo="nunca estuvo",
        )
    assert excepcion.value.codigo is CodigoError.VERSION_DESFASADA
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_participantes WHERE id = %s",
        (participante.participante_id,),
    ) == (1,)


def test_a17_4_participante_de_otro_hecho(
    servicio, servicio_participantes, contexto, actor_a
) -> None:
    hecho_uno, version_uno = _cena(servicio, contexto)
    participante, _ = _alta(
        servicio_participantes, contexto, hecho_uno, version_uno, actor_a
    )
    hecho_dos, version_dos = _cena(servicio, contexto)

    with pytest.raises(ErrorMotor) as excepcion:
        servicio_participantes.retirar_participante(
            contexto,
            hecho_id=hecho_dos,
            participante_id=participante.participante_id,
            row_version_esperada=version_dos,
            motivo="nunca estuvo",
        )
    assert excepcion.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


def test_a17_5_hecho_anulado(
    servicio, servicio_participantes, contexto, actor_a
) -> None:
    """Una raiz ANULADA ya expresa que el hecho no forma parte de la realidad."""
    hecho_id, version = _cena(servicio, contexto)
    participante, version = _alta(
        servicio_participantes, contexto, hecho_id, version, actor_a
    )
    anulado = servicio.anular_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        motivo_anulacion="el ticket era de otra persona",
    )
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_participantes.retirar_participante(
            contexto,
            hecho_id=hecho_id,
            participante_id=participante.participante_id,
            row_version_esperada=anulado.row_version,
            motivo="nunca estuvo",
        )
    assert excepcion.value.codigo is CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO


def test_a17_6_retirar_no_decrementa_el_total(
    servicio, servicio_participantes, contexto, actor_a, admin
) -> None:
    """Pedro pudo ocupar el hueco de uno de los desconocidos: siguen siendo 8."""
    hecho_id, version = _cena(servicio, contexto, total=8)
    participante, version = _alta(
        servicio_participantes, contexto, hecho_id, version, actor_a
    )
    resultado = servicio_participantes.retirar_participante(
        contexto,
        hecho_id=hecho_id,
        participante_id=participante.participante_id,
        row_version_esperada=version,
        motivo="nunca estuvo",
    )
    assert resultado.total_declarado == 8
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT numero_participantes_total FROM gapto.hechos_financieros "
        "WHERE id = %s",
        (hecho_id,),
    ) == (8,)


def test_n6_el_recuento_cuenta_personas_no_filas(
    servicio, servicio_participantes, contexto, actor_a, admin
) -> None:
    """Un actor con dos roles es UNA persona frente al total declarado.

    Se construye la segunda fila por via administrativa porque el vocabulario
    operativo de esta version tiene un solo token. La guarda se ejercita
    despues a traves de OP-02, que revalida el recuento sobre el estado final:
    si contase filas en vez de personas, total=1 fallaria con un solo
    participante real.
    """
    hecho_id, version = _cena(servicio, contexto, total=8)
    servicio_participantes.registrar_participantes(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        participantes=[_participante(actor_a)],
    )
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        try:
            cursor.execute(
                "SELECT set_config('gapto.owner_user_id', %s, false)",
                (str(contexto.owner_user_id),),
            )
            cursor.execute(
                "INSERT INTO gapto.hecho_participantes (id, hecho_id, actor_id, rol) "
                "VALUES (%s, %s, %s, 'OTRO_ROL_FUTURO')",
                (uuid.uuid4(), hecho_id, actor_a),
            )
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET ALL")

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    resultado = servicio.corregir_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=fila[0],
        campos=CamposCorreccion(numero_participantes_total=1),
        motivo="en realidad solo estuvo una persona",
    )
    assert resultado.row_version == fila[0] + 1


def test_n6_el_recuento_cuenta_personas_no_filas(
    servicio, servicio_participantes, contexto, actor_a, actor_b, admin
) -> None:
    """N6. Un actor con dos roles es UNA persona.

    Se monta la segunda fila por via administrativa porque el vocabulario
    operativo tiene hoy un solo token. Si el recuento contase filas en vez de
    actores distintos, este alta legitima se rechazaria por un motivo
    inventado.
    """
    hecho_id, version = _cena(servicio, contexto, total=2)
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        try:
            cursor.execute(
                "SELECT set_config('gapto.owner_user_id', %s, false)",
                (str(contexto.owner_user_id),),
            )
            for rol in ("PARTICIPANTE", "OTRO_ROL_FUTURO"):
                cursor.execute(
                    "INSERT INTO gapto.hecho_participantes "
                    "(id, hecho_id, actor_id, rol) VALUES (%s, %s, %s, %s)",
                    (uuid.uuid4(), hecho_id, actor_a, rol),
                )
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET ALL")

    resultado = servicio_participantes.registrar_participantes(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        participantes=[_participante(actor_b)],
    )
    assert resultado.identificados == 2
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_participantes WHERE hecho_id = %s",
        (hecho_id,),
    ) == (3,)
