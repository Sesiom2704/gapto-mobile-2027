# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_104_op04_registrar_efectos.py
# Ruta: tests/backend/test_104_op04_registrar_efectos.py
# Descripcion: F04-02 OP-04. Alta de efectos economicos: naturalezas, delta
#   firmado, reparto inicial atomico, estados de atribucion, INV-09
#   (F04-D005), idempotencia de lote todo-o-nada (F04-D006), version de la raiz
#   (INV-20), tenant, auditoria y atomicidad. Incluye F04-D004.
# Version: 0.3.0
#   0.3.0 (mandato F04 R1+R2 v0.3 + E01): OP-04 aporta `presupuestable` al
#   introducir el primer GASTO/INGRESO; D004 mide que OP-02 rechazado no anade
#   auditoria respecto de la activacion previa.
# Version: 0.2.0
#   0.2.0 (F04-02): cobertura de F04-D007, signo por fila en OP-04.
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
from app.core.modelos_efectos import DatosAtribucion, DatosEfecto
from app.repositories import auditoria_repository as auditoria
from app.repositories import efectos_repository as repo_efectos
from app.repositories import hechos_repository as repo_hechos
from app.services.efectos_service import EfectosService
from app.services.hechos_service import HechosService
from conftest import leer_fila

D = decimal.Decimal


def datos_hecho(**extra) -> DatosCreacionHecho:
    base = {
        "hecho_id": uuid.uuid4(),
        "fecha_hecho": dt.date(2026, 4, 10),
        "moneda": "EUR",
        "presupuestable": True,
        "estado_localizacion": "DESCONOCIDA",
        "tipo_hecho_codigo": "GASTO",
    }
    base.update(extra)
    return DatosCreacionHecho(**base)


def efecto(**extra) -> DatosEfecto:
    base = {
        "efecto_id": uuid.uuid4(),
        "tipo_efecto": "GASTO",
        "importe_delta": D("44.5000"),
        "estado_atribucion": "NO_DISPONIBLE",
    }
    base.update(extra)
    return DatosEfecto(**base)


def atribucion(actor: uuid.UUID, importe: str, **extra) -> DatosAtribucion:
    base = {
        "atribucion_id": uuid.uuid4(),
        "actor_id": actor,
        "importe_atribuido": D(importe),
        "criterio_atribucion": "MANUAL",
    }
    base.update(extra)
    return DatosAtribucion(**base)


@pytest.fixture()
def hecho(servicio: HechosService, contexto: ContextoOperacion):
    datos = datos_hecho(importe_total=D("44.5000"))
    resultado = servicio.crear_hecho(contexto, datos)
    return datos.hecho_id, resultado.row_version


# ------------------------------------------------------------------
# Camino correcto
# ------------------------------------------------------------------

def test_alta_minima_de_efecto(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    hecho_id, version = hecho
    uno = efecto()
    resultado = servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=version, efectos=[uno], presupuestable=True
    )

    assert resultado.row_version == version + 1
    assert len(resultado.efectos) == 1
    assert resultado.idempotente is False

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT hecho_id, tipo_efecto, importe_delta, estado_atribucion, "
        "categoria_id, descripcion FROM gapto.hecho_efectos WHERE id = %s",
        (uno.efecto_id,),
    )
    assert fila == (hecho_id, "GASTO", D("44.5000"), "NO_DISPONIBLE", None, None)


def test_batch_de_varios_efectos_en_una_transaccion(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    hecho_id, version = hecho
    tres = [
        efecto(tipo_efecto="GASTO", importe_delta=D("100.0000")),
        efecto(tipo_efecto="DEUDA", importe_delta=D("-60.0000")),
        efecto(tipo_efecto="DERECHO_COBRO", importe_delta=D("25.0000")),
    ]
    resultado = servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=version, efectos=tres, presupuestable=True
    )

    # INV-20: una sola operacion logica, un solo incremento.
    assert resultado.row_version == version + 1
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s",
        (hecho_id,),
    )
    assert fila == (3,)


@pytest.mark.parametrize(
    "tipo, delta",
    [
        ("GASTO", "100.0000"),
        ("GASTO", "-100.0000"),
        ("INGRESO", "100.0000"),
        ("INGRESO", "-100.0000"),
        ("DEUDA", "-500.0000"),
        ("DERECHO_COBRO", "80.0000"),
        ("INVERSION", "1000.0000"),
    ],
)
def test_el_signo_no_se_deduce_de_la_naturaleza(
    servicio_efectos: EfectosService, contexto: ContextoOperacion, hecho, tipo, delta
) -> None:
    """Naturaleza y signo son datos independientes: ninguno infiere al otro."""
    hecho_id, version = hecho
    uno = efecto(tipo_efecto=tipo, importe_delta=D(delta))
    resultado = servicio_efectos.registrar_efectos(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        efectos=[uno],
        # F04-D046 A08-bis: la decision solo existe si nace GASTO/INGRESO.
        presupuestable=True if tipo in ("GASTO", "INGRESO") else None,
    )
    assert resultado.efectos[0].tipo_efecto == tipo


def test_categoria_null_es_valida_y_no_se_inventa_default(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    hecho_id, version = hecho
    uno = efecto()
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=version, efectos=[uno], presupuestable=True
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT categoria_id FROM gapto.hecho_efectos WHERE id = %s",
        (uno.efecto_id,),
    )
    assert fila == (None,)


def test_inversion_sin_asignaciones_es_representable(
    servicio_efectos: EfectosService, contexto: ContextoOperacion, hecho
) -> None:
    """F04-02 consume D-080, no lo reimplementa ni fabrica una inversion."""
    hecho_id, version = hecho
    uno = efecto(tipo_efecto="INVERSION", importe_delta=D("1500.0000"))
    resultado = servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=version, efectos=[uno]
    )
    assert resultado.efectos[0].tipo_efecto == "INVERSION"


# ------------------------------------------------------------------
# Reparto inicial en la misma transaccion
# ------------------------------------------------------------------

def test_no_disponible_exige_cero_filas(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    hecho_id, version = hecho
    uno = efecto(estado_atribucion="NO_DISPONIBLE")
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=version, efectos=[uno], presupuestable=True
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.efecto_atribuciones WHERE efecto_id = %s",
        (uno.efecto_id,),
    )
    assert fila == (0,)


def test_no_disponible_con_filas_rechazado(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    hecho,
    actor_a: uuid.UUID,
) -> None:
    """INV-01/INV-02. Sin esta guarda de servicio nada fisico lo impediria."""
    hecho_id, version = hecho
    uno = efecto(
        estado_atribucion="NO_DISPONIBLE",
        atribuciones=(atribucion(actor_a, "15.0000"),),
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.registrar_efectos(
            contexto, hecho_id=hecho_id, row_version_esperada=version, efectos=[uno]
        )
    assert excinfo.value.codigo is CodigoError.NO_DISPONIBLE_CON_FILAS


def test_atribucion_de_cero_sigue_siendo_dato_conocido(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    hecho,
    actor_a: uuid.UUID,
) -> None:
    """0,00 no equivale a ausencia: con una fila de 0,00 ya no cabe NO_DISPONIBLE."""
    hecho_id, version = hecho
    uno = efecto(
        estado_atribucion="NO_DISPONIBLE",
        atribuciones=(atribucion(actor_a, "0.0000"),),
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.registrar_efectos(
            contexto, hecho_id=hecho_id, row_version_esperada=version, efectos=[uno]
        )
    assert excinfo.value.codigo is CodigoError.NO_DISPONIBLE_CON_FILAS


def test_parcial_con_reparto_inicial(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    actor_a: uuid.UUID,
) -> None:
    hecho_id, version = hecho
    uno = efecto(
        estado_atribucion="PARCIAL",
        atribuciones=(atribucion(actor_a, "15.0000"),),
    )
    resultado = servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=version, efectos=[uno], presupuestable=True
    )
    assert resultado.atribuciones_creadas == 1
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT sum(importe_atribuido) FROM gapto.efecto_atribuciones "
        "WHERE efecto_id = %s",
        (uno.efecto_id,),
    )
    assert fila == (D("15.0000"),)


def test_completa_con_reparto_inicial_exacto(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    hecho,
    actor_a: uuid.UUID,
    actor_b: uuid.UUID,
) -> None:
    hecho_id, version = hecho
    uno = efecto(
        estado_atribucion="COMPLETA",
        atribuciones=(
            atribucion(actor_a, "15.0000"),
            atribucion(actor_b, "29.5000"),
        ),
    )
    resultado = servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=version, efectos=[uno], presupuestable=True
    )
    assert resultado.atribuciones_creadas == 2
    assert resultado.efectos[0].estado_atribucion == "COMPLETA"


# ------------------------------------------------------------------
# Validaciones canonicas
# ------------------------------------------------------------------

def test_delta_cero_rechazado(
    servicio_efectos: EfectosService, contexto: ContextoOperacion, hecho
) -> None:
    hecho_id, version = hecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.registrar_efectos(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efectos=[efecto(importe_delta=D("0.0000"))],
        )
    assert excinfo.value.codigo is CodigoError.DELTA_CERO


def test_naturaleza_invalida_rechazada(
    servicio_efectos: EfectosService, contexto: ContextoOperacion, hecho
) -> None:
    hecho_id, version = hecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.registrar_efectos(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efectos=[efecto(tipo_efecto="PLUSVALIA")],
        )
    assert excinfo.value.codigo is CodigoError.NATURALEZA_INVALIDA


def test_lote_vacio_rechazado(
    servicio_efectos: EfectosService, contexto: ContextoOperacion, hecho
) -> None:
    hecho_id, version = hecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.registrar_efectos(
            contexto, hecho_id=hecho_id, row_version_esperada=version, efectos=[]
        )
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


def test_hecho_inexistente(
    servicio_efectos: EfectosService, contexto: ContextoOperacion
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.registrar_efectos(
            contexto,
            hecho_id=uuid.uuid4(),
            row_version_esperada=1,
            efectos=[efecto()],
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


def test_tenant_ajeno_indistinguible_de_inexistente(
    servicio_efectos: EfectosService, otro_owner: uuid.UUID, hecho
) -> None:
    hecho_id, version = hecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.registrar_efectos(
            ContextoOperacion.de_usuario(otro_owner),
            hecho_id=hecho_id,
            row_version_esperada=version,
            efectos=[efecto()],
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


def test_hecho_anulado_rechazado(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    hecho,
) -> None:
    hecho_id, version = hecho
    anulado = servicio.anular_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        motivo_anulacion="nunca debio existir",
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.registrar_efectos(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=anulado.row_version,
            efectos=[efecto()],
        )
    assert excinfo.value.codigo is CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO


def test_version_desfasada(
    servicio_efectos: EfectosService, contexto: ContextoOperacion, hecho
) -> None:
    hecho_id, version = hecho
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=version, efectos=[efecto()], presupuestable=True
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.registrar_efectos(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efectos=[efecto()],
        )
    assert excinfo.value.codigo is CodigoError.VERSION_DESFASADA


def test_actor_de_otro_tenant_no_filtra_informacion(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    hecho,
    actor_ajeno: uuid.UUID,
) -> None:
    hecho_id, version = hecho
    uno = efecto(
        estado_atribucion="COMPLETA",
        atribuciones=(atribucion(actor_ajeno, "44.5000"),),
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.registrar_efectos(
            contexto, hecho_id=hecho_id, row_version_esperada=version, efectos=[uno]
        )
    # Mismo error que un actor inexistente: no se revela que pertenece a otro.
    assert excinfo.value.codigo is CodigoError.ACTOR_DESCONOCIDO


# ------------------------------------------------------------------
# INV-09 / F04-D005
# ------------------------------------------------------------------

def test_valor_activo_sin_acontecimiento_rechazado(
    servicio_efectos: EfectosService, contexto: ContextoOperacion, hecho
) -> None:
    hecho_id, version = hecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.registrar_efectos(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efectos=[efecto(tipo_efecto="VALOR_ACTIVO", importe_delta=D("9000.0000"))],
        )
    assert excinfo.value.codigo is CodigoError.VALOR_ACTIVO_SIN_ACONTECIMIENTO


@pytest.mark.parametrize("codigo", ["TASACION", "VALOR_MERCADO", "REVALORIZACION", ""])
def test_valor_activo_como_mera_valoracion_rechazado(
    servicio_efectos: EfectosService, contexto: ContextoOperacion, hecho, codigo
) -> None:
    hecho_id, version = hecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.registrar_efectos(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efectos=[
                efecto(
                    tipo_efecto="VALOR_ACTIVO",
                    importe_delta=D("9000.0000"),
                    acontecimiento=codigo,
                )
            ],
        )
    assert excinfo.value.codigo is CodigoError.VALOR_ACTIVO_SIN_ACONTECIMIENTO


def test_valor_activo_por_acontecimiento_real_permitido_y_declarado(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    """F04-D005: la declaracion queda en auditoria.motivo, no en el dominio."""
    hecho_id, version = hecho
    uno = efecto(
        tipo_efecto="VALOR_ACTIVO",
        importe_delta=D("9000.0000"),
        acontecimiento="ADQUISICION",
    )
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=version, efectos=[uno]
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT motivo FROM gapto.auditoria WHERE registro_id = %s AND accion = 'CREAR'",
        (uno.efecto_id,),
    )
    assert fila == ("VALOR_ACTIVO:ADQUISICION",)


def test_acontecimiento_en_naturaleza_distinta_rechazado(
    servicio_efectos: EfectosService, contexto: ContextoOperacion, hecho
) -> None:
    hecho_id, version = hecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.registrar_efectos(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efectos=[efecto(tipo_efecto="GASTO", acontecimiento="ADQUISICION")],
        )
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


# ------------------------------------------------------------------
# F04-D006 · idempotencia de lote todo-o-nada
# ------------------------------------------------------------------

def test_d006_ninguno_existe_se_ejecuta(
    servicio_efectos: EfectosService, contexto: ContextoOperacion, hecho
) -> None:
    hecho_id, version = hecho
    resultado = servicio_efectos.registrar_efectos(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        efectos=[efecto(), efecto(importe_delta=D("10.0000"))],
        presupuestable=True,  # F04-D046 A08-bis: primer GASTO/INGRESO
    )
    assert resultado.idempotente is False
    assert resultado.row_version == version + 1


def test_d006_todos_existen_con_la_misma_intencion_es_idempotente(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    actor_a: uuid.UUID,
) -> None:
    hecho_id, version = hecho
    lote = [
        efecto(
            estado_atribucion="COMPLETA",
            atribuciones=(atribucion(actor_a, "44.5000"),),
        ),
        efecto(importe_delta=D("10.0000")),
    ]
    primero = servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=version, efectos=lote, presupuestable=True
    )
    segundo = servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=version, efectos=lote
    )

    assert primero.idempotente is False
    assert segundo.idempotente is True
    # El reintento NO vuelve a incrementar la version que el llamante conoce.
    assert segundo.row_version == primero.row_version

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s",
        (hecho_id,),
    )
    assert fila == (2,)


def test_d006_todos_existen_pero_alguno_difiere_es_conflicto(
    servicio_efectos: EfectosService, contexto: ContextoOperacion, hecho
) -> None:
    hecho_id, version = hecho
    a = efecto()
    b = efecto(importe_delta=D("10.0000"))
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=version, efectos=[a, b], presupuestable=True
    )
    distinto = DatosEfecto(
        efecto_id=b.efecto_id,
        tipo_efecto="GASTO",
        importe_delta=D("99.0000"),
        estado_atribucion="NO_DISPONIBLE",
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.registrar_efectos(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version + 1,
            efectos=[a, distinto],
        )
    assert excinfo.value.codigo is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION


def test_d006_subconjunto_existente_es_conflicto_y_no_completa_las_ausentes(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    """Un lote atomico no puede haberse aplicado a medias: coincidencia parcial
    significa reuso de UUID, no retry valido."""
    hecho_id, version = hecho
    a = efecto()
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=version, efectos=[a], presupuestable=True
    )
    version_tras_a = version + 1
    ausente = efecto(importe_delta=D("10.0000"))

    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.registrar_efectos(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version_tras_a,
            efectos=[a, ausente],
        )
    assert excinfo.value.codigo is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION

    # Ni se completa la fila ausente, ni sube la version, ni hay auditoria nueva.
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos WHERE id = %s",
        (ausente.efecto_id,),
    )
    assert fila == (0,)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == (version_tras_a,)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.auditoria WHERE registro_id = %s",
        (ausente.efecto_id,),
    )
    assert fila == (0,)


def test_identidades_duplicadas_dentro_del_lote_rechazadas(
    servicio_efectos: EfectosService, contexto: ContextoOperacion, hecho
) -> None:
    hecho_id, version = hecho
    uno = efecto()
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.registrar_efectos(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efectos=[uno, uno],
        )
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


# ------------------------------------------------------------------
# Atomicidad y auditoria
# ------------------------------------------------------------------

def test_rollback_total_si_falla_uno_de_varios_efectos(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    hecho_id, version = hecho
    a = efecto()
    b = efecto(importe_delta=D("10.0000"))
    malo = efecto(tipo_efecto="PLUSVALIA")

    with pytest.raises(ErrorMotor):
        servicio_efectos.registrar_efectos(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efectos=[a, b, malo],
        )

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s",
        (hecho_id,),
    )
    assert fila == (0,)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == (version,)


def test_auditoria_de_cada_efecto_y_atribucion(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    actor_a: uuid.UUID,
) -> None:
    hecho_id, version = hecho
    fila_atrib = atribucion(actor_a, "44.5000")
    uno = efecto(estado_atribucion="COMPLETA", atribuciones=(fila_atrib,))
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=version, efectos=[uno], presupuestable=True
    )

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT tabla, accion, datos_antes, datos_despues->>'tipo_efecto', request_id "
        "FROM gapto.auditoria WHERE registro_id = %s",
        (uno.efecto_id,),
    )
    assert fila == ("hecho_efectos", "CREAR", None, "GASTO", contexto.request_id)

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT tabla, accion, datos_despues->>'importe_atribuido' "
        "FROM gapto.auditoria WHERE registro_id = %s",
        (fila_atrib.atribucion_id,),
    )
    assert fila == ("efecto_atribuciones", "CREAR", "44.5000")


def test_rollback_completo_si_falla_la_auditoria(
    unidad, contexto: ContextoOperacion, admin: psycopg.Connection, hecho
) -> None:
    hecho_id, version = hecho
    efecto_id = uuid.uuid4()

    def operacion(sesion):
        repo_hechos.exigir_contexto(sesion)
        repo_hechos.tocar_raiz(sesion, hecho_id, version)
        repo_efectos.insertar_efecto_si_no_existe(
            sesion,
            hecho_id,
            efecto_id=efecto_id,
            tipo_efecto="GASTO",
            importe_delta=D("10.0000"),
            estado_atribucion="NO_DISPONIBLE",
            categoria_id=None,
            descripcion=None,
        )
        auditoria.registrar(
            sesion,
            tabla=repo_efectos.TABLA_EFECTOS,
            registro_id=efecto_id,
            accion=auditoria.ACCION_CREAR,
            datos_despues_json='{"token": "x"}',
        )

    with pytest.raises(ErrorMotor):
        unidad.ejecutar(contexto, operacion, nombre="prueba-rollback-op04")

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos WHERE id = %s",
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
# F04-D004
# ------------------------------------------------------------------

def test_d004_tipo_corregible_sin_efectos(
    servicio: HechosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    hecho_id, version = hecho
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT id FROM gapto.tipos_hecho WHERE codigo = 'INGRESO'",
        (),
    )
    resultado = servicio.corregir_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        campos=CamposCorreccion(tipo_hecho_id=fila[0]),
        motivo="arquetipo equivocado al capturar",
    )
    assert resultado.snapshot["tipo_hecho_id"] == str(fila[0])


@pytest.mark.parametrize("cuantos", [1, 3])
def test_d004_tipo_no_corregible_con_efectos(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    cuantos,
) -> None:
    hecho_id, version = hecho
    lote = [efecto(importe_delta=D(f"{10 + i}.0000")) for i in range(cuantos)]
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=version, efectos=lote, presupuestable=True
    )
    nueva_version = version + 1
    # F04-D046 A08-bis: la activacion de `presupuestable` en la transicion ya
    # deja una auditoria ACTUALIZAR del hecho. Lo que se comprueba es que el
    # intento rechazado de OP-02 no anade NINGUNA mas.
    actualizaciones_previas = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.auditoria "
        "WHERE registro_id = %s AND accion = 'ACTUALIZAR'",
        (hecho_id,),
    )

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT id FROM gapto.tipos_hecho WHERE codigo = 'INGRESO'",
        (),
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.corregir_hecho(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=nueva_version,
            campos=CamposCorreccion(tipo_hecho_id=fila[0]),
            motivo="arquetipo equivocado",
        )
    assert excinfo.value.codigo is CodigoError.CORRECCION_AGREGADA_REQUERIDA

    # Ni hecho, ni efectos, ni auditoria previa quedan alterados.
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == (nueva_version,)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s",
        (hecho_id,),
    )
    assert fila == (cuantos,)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.auditoria "
        "WHERE registro_id = %s AND accion = 'ACTUALIZAR'",
        (hecho_id,),
    )
    assert fila == actualizaciones_previas == (1,)


def test_d004_ya_no_existe_el_codigo_transitorio() -> None:
    assert not any(c.name == "DECISION_DIFERIDA_F04_02" for c in CodigoError)


def test_d006_el_conflicto_de_identidad_se_detecta_antes_que_la_version(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    """F04-D006 es una regla de identidad, no un efecto colateral del INSERT.

    Con un subconjunto ya existente Y una version caducada, el error debe ser
    el de identidad reutilizada, no VERSION_DESFASADA: la decision aprobada
    califica la coincidencia parcial como reuso de UUID con independencia de la
    version. Este test discrimina la clasificacion explicita de un motor que
    simplemente dejase reventar el `ON CONFLICT`: ese fallaria antes en la
    guarda de version y devolveria otro codigo.
    """
    hecho_id, version = hecho
    a = efecto()
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=version, efectos=[a], presupuestable=True
    )
    version_actual = version + 1
    ausente = efecto(importe_delta=D("10.0000"))

    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.registrar_efectos(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,  # caducada a proposito
            efectos=[a, ausente],
        )
    assert excinfo.value.codigo is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == (version_actual,)


# ------------------------------------------------------------------
# F04-D007 · signo por fila
# ------------------------------------------------------------------

def test_d007_efecto_positivo_con_atribucion_negativa(
    servicio_efectos: EfectosService, contexto: ContextoOperacion, hecho, actor_a
) -> None:
    hecho_id, version = hecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.registrar_efectos(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efectos=[
                efecto(
                    importe_delta=D("100.0000"),
                    estado_atribucion="PARCIAL",
                    atribuciones=(atribucion(actor_a, "-20.0000"),),
                )
            ],
        )
    assert excinfo.value.codigo is CodigoError.SIGNO_INCOMPATIBLE


def test_d007_efecto_negativo_con_atribucion_positiva(
    servicio_efectos: EfectosService, contexto: ContextoOperacion, hecho, actor_a
) -> None:
    hecho_id, version = hecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.registrar_efectos(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efectos=[
                efecto(
                    importe_delta=D("-100.0000"),
                    estado_atribucion="PARCIAL",
                    atribuciones=(atribucion(actor_a, "20.0000"),),
                )
            ],
        )
    assert excinfo.value.codigo is CodigoError.SIGNO_INCOMPATIBLE


def test_d007_suma_exacta_pero_una_fila_de_signo_contrario(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    hecho,
    actor_a: uuid.UUID,
    actor_b: uuid.UUID,
) -> None:
    """GASTO +100 repartido +120 / -20 suma bien y aun asi es neteo."""
    hecho_id, version = hecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.registrar_efectos(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efectos=[
                efecto(
                    importe_delta=D("100.0000"),
                    estado_atribucion="COMPLETA",
                    atribuciones=(
                        atribucion(actor_a, "120.0000"),
                        atribucion(actor_b, "-20.0000"),
                    ),
                )
            ],
        )
    assert excinfo.value.codigo is CodigoError.SIGNO_INCOMPATIBLE


@pytest.mark.parametrize("delta", ["100.0000", "-100.0000"])
def test_d007_cero_es_valido_en_ambos_sentidos(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    actor_a: uuid.UUID,
    delta,
) -> None:
    hecho_id, version = hecho
    uno = efecto(
        importe_delta=D(delta),
        estado_atribucion="PARCIAL",
        atribuciones=(atribucion(actor_a, "0.0000"),),
    )
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=version, efectos=[uno], presupuestable=True
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe_atribuido FROM gapto.efecto_atribuciones WHERE efecto_id = %s",
        (uno.efecto_id,),
    )
    assert fila == (D("0.0000"),)


def test_d007_batch_con_una_fila_de_signo_contrario_hace_rollback_total(
    servicio_efectos: EfectosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
    actor_a: uuid.UUID,
) -> None:
    hecho_id, version = hecho
    bueno = efecto(importe_delta=D("50.0000"))
    malo = efecto(
        importe_delta=D("100.0000"),
        estado_atribucion="PARCIAL",
        atribuciones=(atribucion(actor_a, "-10.0000"),),
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_efectos.registrar_efectos(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            efectos=[bueno, malo],
        )
    assert excinfo.value.codigo is CodigoError.SIGNO_INCOMPATIBLE

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s",
        (hecho_id,),
    )
    assert fila == (0,)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == (version,)
