# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_105_op05_atribuir_efectos.py
# Ruta: tests/backend/test_105_op05_atribuir_efectos.py
# Descripcion: F04-02 OP-05. Atribucion por actor: transiciones de
#   enriquecimiento, sumas y signos, prohibicion de retroceso y de reescritura,
#   independencia frente a participacion de cuenta y pago (INV-03/INV-04),
#   idempotencia de lote (F04-D006), carrera real sobre la version de la raiz
#   (INV-20), auditoria y atomicidad.
# Version: 0.3.0
#   0.3.0 (F04-04): el recuento de posiciones se acota al tenant. Contarlas
#   globalmente era una expresion incorrecta de INV-04 y rompia en cuanto otra
#   subfase creo posiciones legitimas en la misma base.
# Version: 0.2.0
#   0.2.0 (F04-02): cobertura de F04-D007, signo por fila en OP-05.
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
from app.core.modelos_efectos import DatosAtribucion, DatosEfecto
from app.repositories import auditoria_repository as auditoria
from app.repositories import efectos_repository as repo_efectos
from app.repositories import hechos_repository as repo_hechos
from app.services.efectos_service import EfectosService
from conftest import leer_fila
from test_104_op04_registrar_efectos import atribucion, datos_hecho, efecto

D = decimal.Decimal


@pytest.fixture()
def efecto_abierto(servicio, servicio_efectos: EfectosService, contexto):
    """Hecho ACTIVO con un efecto GASTO de 44,50 y atribucion NO_DISPONIBLE."""
    datos = datos_hecho(importe_total=D("44.5000"))
    creado = servicio.crear_hecho(contexto, datos)
    uno = efecto(importe_delta=D("44.5000"), estado_atribucion="NO_DISPONIBLE")
    resultado = servicio_efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=[uno],
    )
    return datos.hecho_id, uno.efecto_id, resultado.row_version


@pytest.fixture()
def efecto_negativo(servicio, servicio_efectos: EfectosService, contexto):
    datos = datos_hecho()
    creado = servicio.crear_hecho(contexto, datos)
    uno = efecto(importe_delta=D("-80.0000"), estado_atribucion="NO_DISPONIBLE")
    resultado = servicio_efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=[uno],
    )
    return datos.hecho_id, uno.efecto_id, resultado.row_version


# ------------------------------------------------------------------
# Transiciones de enriquecimiento
# ------------------------------------------------------------------

def test_no_disponible_a_parcial(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    efecto_abierto,
    actor_a: uuid.UUID,
) -> None:
    hecho_id, efecto_id, version = efecto_abierto
    resultado = servicio_efectos.atribuir_efecto(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        efecto_id=efecto_id,
        atribuciones=[atribucion(actor_a, "15.0000")],
        estado_resultante="PARCIAL",
    )
    assert resultado.row_version == version + 1
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado_atribucion FROM gapto.hecho_efectos WHERE id = %s",
        (efecto_id,),
    )
    assert fila == ("PARCIAL",)


def test_no_disponible_a_completa_en_una_sola_operacion(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    efecto_abierto,
    actor_a: uuid.UUID,
    actor_b: uuid.UUID,
) -> None:
    hecho_id, efecto_id, version = efecto_abierto
    resultado = servicio_efectos.atribuir_efecto(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        efecto_id=efecto_id,
        atribuciones=[
            atribucion(actor_a, "15.0000"),
            atribucion(actor_b, "29.5000"),
        ],
        estado_resultante="COMPLETA",
    )
    assert resultado.atribuciones_creadas == 2


def test_parcial_a_completa_conservando_las_filas_previas(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    efecto_abierto,
    actor_a: uuid.UUID,
    actor_b: uuid.UUID,
) -> None:
    """El ejemplo canonico del expediente: 44,50 -> A 15,00 -> B 29,50."""
    hecho_id, efecto_id, version = efecto_abierto
    parcial = servicio_efectos.atribuir_efecto(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        efecto_id=efecto_id,
        atribuciones=[atribucion(actor_a, "15.0000")],
        estado_resultante="PARCIAL",
    )
    completa = servicio_efectos.atribuir_efecto(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=parcial.row_version,
        efecto_id=efecto_id,
        atribuciones=[atribucion(actor_b, "29.5000")],
        estado_resultante="COMPLETA",
    )
    assert completa.row_version == version + 2

    # No se borro la atribucion de A para "recalcular" el reparto.
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), sum(importe_atribuido) "
        "FROM gapto.efecto_atribuciones WHERE efecto_id = %s",
        (efecto_id,),
    )
    assert fila == (2, D("44.5000"))


def test_atribucion_explicita_de_cero_es_valida(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    efecto_abierto,
    actor_a: uuid.UUID,
) -> None:
    hecho_id, efecto_id, version = efecto_abierto
    servicio_efectos.atribuir_efecto(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        efecto_id=efecto_id,
        atribuciones=[atribucion(actor_a, "0.0000")],
        estado_resultante="PARCIAL",
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe_atribuido FROM gapto.efecto_atribuciones WHERE efecto_id = %s",
        (efecto_id,),
    )
    assert fila == (D("0.0000"),)


def test_efecto_negativo_admite_reparto_negativo(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    efecto_negativo,
    actor_a: uuid.UUID,
) -> None:
    hecho_id, efecto_id, version = efecto_negativo
    resultado = servicio_efectos.atribuir_efecto(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        efecto_id=efecto_id,
        atribuciones=[atribucion(actor_a, "-80.0000")],
        estado_resultante="COMPLETA",
    )
    assert resultado.atribuciones_creadas == 1


# ------------------------------------------------------------------
# Sumas y signos (INV-01)
# ------------------------------------------------------------------

def test_suma_insuficiente_marcada_completa(
    servicio_efectos: EfectosService, contexto, efecto_abierto, actor_a
) -> None:
    hecho_id, efecto_id, version = efecto_abierto
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.atribuir_efecto(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efecto_id=efecto_id,
            atribuciones=[atribucion(actor_a, "15.0000")],
            estado_resultante="COMPLETA",
        )
    assert excinfo.value.codigo is CodigoError.SUMA_NO_CUADRA


def test_suma_completa_marcada_parcial(
    servicio_efectos: EfectosService, contexto, efecto_abierto, actor_a
) -> None:
    """Si el reparto conocido cubre el delta, el estado correcto es COMPLETA."""
    hecho_id, efecto_id, version = efecto_abierto
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.atribuir_efecto(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efecto_id=efecto_id,
            atribuciones=[atribucion(actor_a, "44.5000")],
            estado_resultante="PARCIAL",
        )
    assert excinfo.value.codigo is CodigoError.SUMA_NO_CUADRA


def test_exceso_de_suma_rechazado(
    servicio_efectos: EfectosService, contexto, efecto_abierto, actor_a
) -> None:
    hecho_id, efecto_id, version = efecto_abierto
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.atribuir_efecto(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efecto_id=efecto_id,
            atribuciones=[atribucion(actor_a, "60.0000")],
            estado_resultante="PARCIAL",
        )
    assert excinfo.value.codigo is CodigoError.SUMA_NO_CUADRA


def test_signo_incompatible_rechazado(
    servicio_efectos: EfectosService, contexto, efecto_abierto, actor_a
) -> None:
    hecho_id, efecto_id, version = efecto_abierto
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.atribuir_efecto(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efecto_id=efecto_id,
            atribuciones=[atribucion(actor_a, "-10.0000")],
            estado_resultante="PARCIAL",
        )
    assert excinfo.value.codigo is CodigoError.SIGNO_INCOMPATIBLE


def test_no_disponible_con_filas_rechazado_en_op05(
    servicio_efectos: EfectosService, contexto, efecto_abierto, actor_a
) -> None:
    hecho_id, efecto_id, version = efecto_abierto
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.atribuir_efecto(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efecto_id=efecto_id,
            atribuciones=[atribucion(actor_a, "15.0000")],
            estado_resultante="NO_DISPONIBLE",
        )
    assert excinfo.value.codigo is CodigoError.NO_DISPONIBLE_CON_FILAS


# ------------------------------------------------------------------
# Prohibiciones de retroceso y reescritura
# ------------------------------------------------------------------

@pytest.mark.parametrize("destino", ["NO_DISPONIBLE", "PARCIAL"])
def test_retroceso_desde_completa_rechazado(
    servicio_efectos: EfectosService, contexto, efecto_abierto, actor_a, actor_b, destino
) -> None:
    hecho_id, efecto_id, version = efecto_abierto
    completa = servicio_efectos.atribuir_efecto(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        efecto_id=efecto_id,
        atribuciones=[atribucion(actor_a, "44.5000")],
        estado_resultante="COMPLETA",
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.atribuir_efecto(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=completa.row_version,
            efecto_id=efecto_id,
            atribuciones=[atribucion(actor_b, "1.0000")],
            estado_resultante=destino,
        )
    assert excinfo.value.codigo is CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO


def test_retroceso_de_parcial_a_no_disponible_rechazado(
    servicio_efectos: EfectosService, contexto, efecto_abierto, actor_a
) -> None:
    hecho_id, efecto_id, version = efecto_abierto
    parcial = servicio_efectos.atribuir_efecto(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        efecto_id=efecto_id,
        atribuciones=[atribucion(actor_a, "15.0000")],
        estado_resultante="PARCIAL",
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.atribuir_efecto(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=parcial.row_version,
            efecto_id=efecto_id,
            atribuciones=[],
            estado_resultante="NO_DISPONIBLE",
        )
    assert excinfo.value.codigo is CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO


def test_reescribir_una_atribucion_ya_materializada_rechazado(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    efecto_abierto,
    actor_a: uuid.UUID,
) -> None:
    """Cambiar lo ya conocido es correccion de realidad registrada, no alta."""
    hecho_id, efecto_id, version = efecto_abierto
    parcial = servicio_efectos.atribuir_efecto(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        efecto_id=efecto_id,
        atribuciones=[atribucion(actor_a, "15.0000")],
        estado_resultante="PARCIAL",
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.atribuir_efecto(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=parcial.row_version,
            efecto_id=efecto_id,
            atribuciones=[atribucion(actor_a, "20.0000")],
            estado_resultante="PARCIAL",
        )
    assert excinfo.value.codigo is CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), sum(importe_atribuido) "
        "FROM gapto.efecto_atribuciones WHERE efecto_id = %s",
        (efecto_id,),
    )
    assert fila == (1, D("15.0000"))


# ------------------------------------------------------------------
# Independencia financiera (INV-03 / INV-04)
# ------------------------------------------------------------------

def test_cuenta_compartida_no_genera_atribucion_automatica(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    efecto_abierto,
    actor_a: uuid.UUID,
    actor_b: uuid.UUID,
) -> None:
    """Cuenta 50/50 y gasto atribuido 100 % al usuario: nada se reparte solo."""
    hecho_id, efecto_id, version = efecto_abierto
    cuenta_id = uuid.uuid4()
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        try:
            cursor.execute(
                "SELECT set_config('gapto.owner_user_id', %s, false)",
                (str(contexto.owner_user_id),),
            )
            cursor.execute(
                "INSERT INTO gapto.cuentas (id, owner_user_id, nombre, tipo, "
                "naturaleza, moneda, computa_liquidez, computa_patrimonio, "
                "permite_negativo) VALUES (%s, %s, 'Cuenta 50/50', 'CORRIENTE', "
                "'ACTIVO', 'EUR', true, true, false)",
                (cuenta_id, contexto.owner_user_id),
            )
            # La participacion debe sumar 100 en todo instante cubierto, asi
            # que las dos mitades tienen que entrar dentro de la misma
            # transaccion con la validacion diferida.
            cursor.execute("BEGIN")
            cursor.execute("SET CONSTRAINTS ALL DEFERRED")
            for actor in (actor_a, actor_b):
                cursor.execute(
                    "INSERT INTO gapto.cuenta_participaciones "
                    "(id, cuenta_id, actor_id, porcentaje, vigente_desde) "
                    "VALUES (%s, %s, %s, 50, CURRENT_DATE)",
                    (uuid.uuid4(), cuenta_id, actor),
                )
            cursor.execute("COMMIT")
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET ALL")

    servicio_efectos.atribuir_efecto(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        efecto_id=efecto_id,
        atribuciones=[atribucion(actor_a, "44.5000")],
        estado_resultante="COMPLETA",
    )

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), max(actor_id::text), sum(importe_atribuido) "
        "FROM gapto.efecto_atribuciones WHERE efecto_id = %s",
        (efecto_id,),
    )
    assert fila == (1, str(actor_a), D("44.5000"))


def test_la_atribucion_no_crea_aportacion_tesoreria_ni_posicion(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    efecto_abierto,
    actor_a: uuid.UUID,
) -> None:
    """INV-04: que atribucion y pago difieran NO crea derecho ni obligacion."""
    hecho_id, efecto_id, version = efecto_abierto
    servicio_efectos.atribuir_efecto(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        efecto_id=efecto_id,
        atribuciones=[atribucion(actor_a, "44.5000")],
        estado_resultante="COMPLETA",
    )
    for tabla, columna in (
        ("hecho_aportaciones_pago", "hecho_id"),
        ("hecho_movimientos_tesoreria", "hecho_id"),
    ):
        fila = leer_fila(
            admin,
            contexto.owner_user_id,
            f"SELECT count(*) FROM gapto.{tabla} WHERE {columna} = %s",
            (hecho_id,),
        )
        assert fila == (0,), tabla
    # Ninguna posicion nace de la diferencia entre atribucion y pago.
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        # Acotado al tenant: la conexion de verificacion tiene BYPASSRLS, y
        # ademas F04-04 crea posiciones legitimas en la misma base. Lo que
        # INV-04 prohibe es que ESTA operacion cree una posicion a ESTE
        # usuario, no que existan posiciones en el mundo.
        "SELECT count(*) FROM gapto.derechos_obligaciones_financieras p "
        "JOIN gapto.entidades e ON e.id = p.entidad_id "
        "WHERE e.owner_user_id = %s",
        (contexto.owner_user_id,),
    )
    assert fila == (0,)


# ------------------------------------------------------------------
# Actores
# ------------------------------------------------------------------

def test_actor_desconocido(
    servicio_efectos: EfectosService, contexto, efecto_abierto
) -> None:
    hecho_id, efecto_id, version = efecto_abierto
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.atribuir_efecto(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efecto_id=efecto_id,
            atribuciones=[atribucion(uuid.uuid4(), "10.0000")],
            estado_resultante="PARCIAL",
        )
    assert excinfo.value.codigo is CodigoError.ACTOR_DESCONOCIDO


def test_actor_de_otro_tenant_no_filtra(
    servicio_efectos: EfectosService, contexto, efecto_abierto, actor_ajeno
) -> None:
    hecho_id, efecto_id, version = efecto_abierto
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.atribuir_efecto(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efecto_id=efecto_id,
            atribuciones=[atribucion(actor_ajeno, "10.0000")],
            estado_resultante="PARCIAL",
        )
    assert excinfo.value.codigo is CodigoError.ACTOR_DESCONOCIDO


def test_efecto_de_otro_hecho_rechazado(
    servicio, servicio_efectos: EfectosService, contexto, efecto_abierto, actor_a
) -> None:
    _, efecto_id, _ = efecto_abierto
    otros = datos_hecho()
    otro = servicio.crear_hecho(contexto, otros)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.atribuir_efecto(
            contexto,
            hecho_id=otros.hecho_id,
            row_version_esperada=otro.row_version,
            efecto_id=efecto_id,
            atribuciones=[atribucion(actor_a, "10.0000")],
            estado_resultante="PARCIAL",
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


def test_aislamiento_tenant_en_op05(
    servicio_efectos: EfectosService, otro_owner, efecto_abierto
) -> None:
    hecho_id, efecto_id, version = efecto_abierto
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.atribuir_efecto(
            ContextoOperacion.de_usuario(otro_owner),
            hecho_id=hecho_id,
            row_version_esperada=version,
            efecto_id=efecto_id,
            atribuciones=[],
            estado_resultante="PARCIAL",
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


# ------------------------------------------------------------------
# Idempotencia y concurrencia
# ------------------------------------------------------------------

def test_retry_idempotente_de_op05(
    servicio_efectos: EfectosService,
    admin: psycopg.Connection,
    owner: uuid.UUID,
    efecto_abierto,
    actor_a: uuid.UUID,
) -> None:
    hecho_id, efecto_id, version = efecto_abierto
    ctx = ContextoOperacion.de_usuario(owner)
    filas = [atribucion(actor_a, "15.0000")]

    primero = servicio_efectos.atribuir_efecto(
        ctx,
        hecho_id=hecho_id,
        row_version_esperada=version,
        efecto_id=efecto_id,
        atribuciones=filas,
        estado_resultante="PARCIAL",
    )
    segundo = servicio_efectos.atribuir_efecto(
        ctx,
        hecho_id=hecho_id,
        row_version_esperada=version,
        efecto_id=efecto_id,
        atribuciones=filas,
        estado_resultante="PARCIAL",
    )
    assert primero.idempotente is False
    assert segundo.idempotente is True
    assert segundo.row_version == primero.row_version

    fila = leer_fila(
        admin,
        owner,
        "SELECT count(*) FROM gapto.efecto_atribuciones WHERE efecto_id = %s",
        (efecto_id,),
    )
    assert fila == (1,)


def test_d006_en_op05_subconjunto_existente_es_conflicto(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    efecto_abierto,
    actor_a: uuid.UUID,
    actor_b: uuid.UUID,
) -> None:
    hecho_id, efecto_id, version = efecto_abierto
    primera = atribucion(actor_a, "15.0000")
    parcial = servicio_efectos.atribuir_efecto(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        efecto_id=efecto_id,
        atribuciones=[primera],
        estado_resultante="PARCIAL",
    )
    ausente = atribucion(actor_b, "29.5000")
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.atribuir_efecto(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=parcial.row_version,
            efecto_id=efecto_id,
            atribuciones=[primera, ausente],
            estado_resultante="COMPLETA",
        )
    assert excinfo.value.codigo is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.efecto_atribuciones WHERE efecto_id = %s",
        (efecto_id,),
    )
    assert fila == (1,)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == (parcial.row_version,)


def test_version_consumida_por_otra_operacion(
    servicio_efectos: EfectosService, contexto, efecto_abierto, actor_a, actor_b
) -> None:
    hecho_id, efecto_id, version = efecto_abierto
    servicio_efectos.atribuir_efecto(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        efecto_id=efecto_id,
        atribuciones=[atribucion(actor_a, "15.0000")],
        estado_resultante="PARCIAL",
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.atribuir_efecto(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efecto_id=efecto_id,
            atribuciones=[atribucion(actor_b, "10.0000")],
            estado_resultante="PARCIAL",
        )
    assert excinfo.value.codigo is CodigoError.VERSION_DESFASADA


def test_carrera_real_sobre_la_version_de_la_raiz(
    unidad,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    efecto_abierto,
) -> None:
    """Interleaving real entre la lectura y el incremento de la raiz.

    Comprobar `row_version` en Python no protege nada: entre leer y escribir
    cabe otra transaccion. Quien impide la perdida de actualizacion es la
    clausula `AND h.row_version = %s` de `tocar_raiz`. Este test intercala una
    escritura ajena YA CONFIRMADA y exige que el incremento no case fila. Sin
    esa clausula el test falla: es su mutante.
    """
    hecho_id, _, version = efecto_abierto
    resultado: dict = {}

    def operacion(sesion):
        repo_hechos.exigir_contexto(sesion)
        estado = repo_hechos.leer_estado(sesion, hecho_id)
        assert estado is not None and estado[0] == version

        with admin.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute("SET ROLE gapto_owner")
            try:
                cursor.execute(
                    "SELECT set_config('gapto.owner_user_id', %s, false)",
                    (str(contexto.owner_user_id),),
                )
                cursor.execute(
                    "UPDATE gapto.hechos_financieros "
                    "SET notas = 'ajena', row_version = row_version + 1 "
                    "WHERE id = %s",
                    (hecho_id,),
                )
            finally:
                cursor.execute("RESET ROLE")
                cursor.execute("RESET ALL")

        resultado["tocar"] = repo_hechos.tocar_raiz(sesion, hecho_id, version)

    unidad.ejecutar(contexto, operacion, nombre="prueba-carrera-op05")

    assert resultado["tocar"] is None
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version, notas FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == (version + 1, "ajena")


# ------------------------------------------------------------------
# Auditoria y atomicidad
# ------------------------------------------------------------------

def test_auditoria_de_transicion_con_estado_anterior_y_posterior(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    efecto_abierto,
    actor_a: uuid.UUID,
) -> None:
    hecho_id, efecto_id, version = efecto_abierto
    servicio_efectos.atribuir_efecto(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        efecto_id=efecto_id,
        atribuciones=[atribucion(actor_a, "15.0000")],
        estado_resultante="PARCIAL",
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT accion, datos_antes->>'estado_atribucion', "
        "datos_despues->>'estado_atribucion', motivo "
        "FROM gapto.auditoria WHERE registro_id = %s AND accion = 'ACTUALIZAR'",
        (efecto_id,),
    )
    assert fila == (
        "ACTUALIZAR",
        "NO_DISPONIBLE",
        "PARCIAL",
        "transicion de atribucion NO_DISPONIBLE -> PARCIAL",
    )


def test_rollback_completo_si_falla_la_auditoria_de_op05(
    unidad,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    efecto_abierto,
    actor_a: uuid.UUID,
) -> None:
    hecho_id, efecto_id, version = efecto_abierto
    atribucion_id = uuid.uuid4()

    def operacion(sesion):
        repo_hechos.exigir_contexto(sesion)
        repo_hechos.tocar_raiz(sesion, hecho_id, version)
        repo_efectos.insertar_atribucion_si_no_existe(
            sesion,
            atribucion_id=atribucion_id,
            efecto_id=efecto_id,
            actor_id=actor_a,
            importe_atribuido=D("15.0000"),
            criterio_atribucion="MANUAL",
            porcentaje_aplicado=None,
        )
        auditoria.registrar(
            sesion,
            tabla=repo_efectos.TABLA_ATRIBUCIONES,
            registro_id=atribucion_id,
            accion=auditoria.ACCION_CREAR,
            datos_despues_json='{"secret": "x"}',
        )

    with pytest.raises(ErrorMotor):
        unidad.ejecutar(contexto, operacion, nombre="prueba-rollback-op05")

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.efecto_atribuciones WHERE efecto_id = %s",
        (efecto_id,),
    )
    assert fila == (0,)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == (version,)


# ------------------------------------------------------------------
# F04-D007 · signo por fila en OP-05
# ------------------------------------------------------------------

def test_d007_op05_fila_de_signo_contrario_rechazada(
    servicio_efectos: EfectosService, contexto, efecto_abierto, actor_a
) -> None:
    hecho_id, efecto_id, version = efecto_abierto
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.atribuir_efecto(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efecto_id=efecto_id,
            atribuciones=[atribucion(actor_a, "-10.0000")],
            estado_resultante="PARCIAL",
        )
    assert excinfo.value.codigo is CodigoError.SIGNO_INCOMPATIBLE


def test_d007_op05_efecto_negativo_con_atribucion_positiva(
    servicio_efectos: EfectosService, contexto, efecto_negativo, actor_a
) -> None:
    hecho_id, efecto_id, version = efecto_negativo
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.atribuir_efecto(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efecto_id=efecto_id,
            atribuciones=[atribucion(actor_a, "10.0000")],
            estado_resultante="PARCIAL",
        )
    assert excinfo.value.codigo is CodigoError.SIGNO_INCOMPATIBLE


def test_d007_op05_rechazo_por_signo_no_deja_rastro(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    efecto_abierto,
    actor_a: uuid.UUID,
    actor_b: uuid.UUID,
) -> None:
    """Ni sube row_version, ni escribe auditoria, ni deja atribuciones."""
    hecho_id, efecto_id, version = efecto_abierto
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.atribuir_efecto(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efecto_id=efecto_id,
            atribuciones=[
                atribucion(actor_a, "60.0000"),
                atribucion(actor_b, "-15.5000"),
            ],
            estado_resultante="PARCIAL",
        )
    # 60,00 - 15,50 suma exactamente 44,50: sin la guarda por fila esto
    # devolveria otro codigo y el rechazo pasaria por el motivo equivocado.
    assert excinfo.value.codigo is CodigoError.SIGNO_INCOMPATIBLE
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == (version,)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.efecto_atribuciones WHERE efecto_id = %s",
        (efecto_id,),
    )
    assert fila == (0,)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.auditoria "
        "WHERE registro_id = %s AND accion = 'ACTUALIZAR'",
        (efecto_id,),
    )
    assert fila == (0,)


def test_d007_op05_cero_sigue_siendo_valido_en_efecto_negativo(
    servicio_efectos: EfectosService, contexto, efecto_negativo, actor_a
) -> None:
    hecho_id, efecto_id, version = efecto_negativo
    resultado = servicio_efectos.atribuir_efecto(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        efecto_id=efecto_id,
        atribuciones=[atribucion(actor_a, "0.0000")],
        estado_resultante="PARCIAL",
    )
    assert resultado.atribuciones_creadas == 1
