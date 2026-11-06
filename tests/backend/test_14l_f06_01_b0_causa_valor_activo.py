# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_14l_f06_01_b0_causa_valor_activo.py
# Ruta: tests/backend/test_14l_f06_01_b0_causa_valor_activo.py
# Descripcion: F06-01 B0 (F06-D002; reapertura acotada de F04 para OP-04,
#   OP-21 y OP-22; PB0-03, PB0-04, AJ-B0-03). Writer de la causa de
#   VALOR_ACTIVO persistida por 0351:
#     W1 OP-04 persiste el acontecimiento declarado en causa_valor_activo y
#        conserva auditoria.motivo (F04-D005); un GASTO queda con causa NULL.
#     W2 OP-22 (compuesto, via OP-04) persiste la causa; sin acontecimiento
#        sigue rechazando con VALOR_ACTIVO_SIN_ACONTECIMIENTO (la validacion de
#        entrada de OP-04 precede a la guarda de escritura).
#     W3 guarda de escritura `exigir_causa_valor_activo`: REQUERIDA y
#        NO_ADMITIDA, unitaria y por el camino real que la alcanza (altas de
#        reemplazo de OP-21, que no validan acontecimiento a la entrada).
#     W4 OP-21 rechaza convertir hacia y desde VALOR_ACTIVO con
#        CORRECCION_TIPO_EFECTO_VALOR_ACTIVO_NO_ADMITIDA, antes de cualquier
#        UPDATE: row_version, tipo y causa intactos. Corregir el importe de un
#        VALOR_ACTIVO sigue admitido y conserva la causa.
#     W5 traduccion HTTP: los cuatro codigos son 422 con mensaje propio.
#     W7 (v0.3, PB0I-06, AJ-B0I-01) OP-21 rechaza la conversion LOGICA por
#        retirada y alta en la misma correccion con
#        CORRECCION_CONVERSION_VALOR_ACTIVO_NO_ADMITIDA: (a) VALOR_ACTIVO ->
#        otro tipo, (b) otro tipo -> VALOR_ACTIVO, (c) VALOR_ACTIVO con causa
#        distinta; antes de cualquier escritura (row_version, efectos,
#        atribuciones y auditoria intactos). Controles: el mismo tipo no
#        VALOR_ACTIVO y el VALOR_ACTIVO con la misma causa siguen admitidos.
#     W8 (N1, RB0-06) PRECEDENCIA en OP-21: una correccion que reune a la
#        vez una conversion logica y una causa ausente o no admitida recibe
#        CORRECCION_CONVERSION_VALOR_ACTIVO_NO_ADMITIDA (la guarda de OP-21
#        precede a la guarda comun del INSERT), sin escribir nada. Es
#        contrato, no orden accidental de llamadas.
#   Se ejecuta como gapto_runtime con RLS (conftest).
# Version: 0.4.0  -- F06-01 B0 N1 (LOTE9 C2; dictamen de reconsulta RB0-06):
#   W8, precedencia de la guarda de conversion logica sobre la del INSERT.
# Version: 0.3.0  -- CANDIDATO B0 v0.3 (pendiente de dictamen y decision).
#   0.3.0 (PB0I-06, AJ-B0I-01): W7 y el cuarto codigo en W5.
# Version: 0.2.0  -- PAQUETE B0 v0.2 (no candidato hasta dictamen).
# ============================================================
from __future__ import annotations

import datetime as dt
import decimal
import uuid

import pytest

from app.api.errores_http import traducir_error_motor
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import DatosCreacionHecho
from app.core.modelos_compuesto import DatosHechoCompuesto
from app.core.modelos_efectos import DatosEfecto, exigir_causa_valor_activo
from app.core.unidad_trabajo import UnidadDeTrabajo
from app.services.compuesto_service import HechosCompuestosService
from app.services.correcciones_service import DatosCorreccion
from conftest import leer_fila

D = decimal.Decimal
REQUERIDA = CodigoError.CAUSA_VALOR_ACTIVO_REQUERIDA
NO_ADMITIDA = CodigoError.CAUSA_VALOR_ACTIVO_NO_ADMITIDA
CONVERSION = CodigoError.CORRECCION_TIPO_EFECTO_VALOR_ACTIVO_NO_ADMITIDA
CONVERSION_LOGICA = CodigoError.CORRECCION_CONVERSION_VALOR_ACTIVO_NO_ADMITIDA


# ==================================================================
# Utilidades
# ==================================================================

def _hecho(tipo: str = "ADQUISICION_PATRIMONIAL", total: str = "90000.0000") -> DatosCreacionHecho:
    return DatosCreacionHecho(
        hecho_id=uuid.uuid4(), fecha_hecho=dt.date(2026, 11, 4), moneda="EUR",
        presupuestable=False, estado_localizacion="DESCONOCIDA",
        tipo_hecho_codigo=tipo, concepto="B0 causa", importe_total=D(total),
    )


def _ef(tipo: str, importe: str, acontecimiento: str | None = None,
        efecto_id: uuid.UUID | None = None) -> DatosEfecto:
    return DatosEfecto(
        efecto_id=efecto_id or uuid.uuid4(), tipo_efecto=tipo,
        importe_delta=D(importe), estado_atribucion="NO_DISPONIBLE",
        acontecimiento=acontecimiento,
    )


def _version(admin, contexto, hecho_id) -> int:
    return leer_fila(admin, contexto.owner_user_id,
                     "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
                     (hecho_id,))[0]


def _fila_efecto(admin, contexto, efecto_id):
    return leer_fila(admin, contexto.owner_user_id,
                     "SELECT tipo_efecto, importe_delta, causa_valor_activo "
                     "FROM gapto.hecho_efectos WHERE id = %s", (efecto_id,))


def _efectos_del_hecho(admin, contexto, hecho_id) -> int:
    return leer_fila(admin, contexto.owner_user_id,
                     "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s",
                     (hecho_id,))[0]


def _rechazo(fn, codigo) -> ErrorMotor:
    with pytest.raises(ErrorMotor) as excinfo:
        fn()
    assert excinfo.value.codigo is codigo, excinfo.value
    return excinfo.value


@pytest.fixture()
def op22(unidad: UnidadDeTrabajo) -> HechosCompuestosService:
    from app.services.previsiones_service import impacto_correccion_ancla

    return HechosCompuestosService(unidad, impacto_ancla=impacto_correccion_ancla)


@pytest.fixture()
def con_valor_activo(servicio, servicio_efectos, contexto, admin):
    """Hecho ADQUISICION_PATRIMONIAL con un VALOR_ACTIVO (ADQUISICION) y un GASTO."""
    h = _hecho()
    creado = servicio.crear_hecho(contexto, h)
    va, gasto = _ef("VALOR_ACTIVO", "90000.0000", "ADQUISICION"), _ef("GASTO", "1200.0000")
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=h.hecho_id, row_version_esperada=creado.row_version,
        efectos=[va, gasto], presupuestable=False,
    )
    return h.hecho_id, va.efecto_id, gasto.efecto_id


def _op21(servicio_correcciones, contexto, admin, hecho_id, **cambios):
    return servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=hecho_id, row_version_esperada=_version(admin, contexto, hecho_id),
        motivo="F06-D002 B0", **cambios,
    ))


# ==================================================================
# W1 · OP-04
# ==================================================================

@pytest.mark.parametrize("acontecimiento", sorted(
    {"ADQUISICION", "TRANSFORMACION_CAPITALIZABLE", "BAJA_TOTAL", "BAJA_PARCIAL", "REDUCCION_ESTRUCTURAL"}))
def test_w1_op04_persiste_la_causa(servicio, servicio_efectos, contexto, admin, acontecimiento) -> None:
    h = _hecho()
    creado = servicio.crear_hecho(contexto, h)
    va = _ef("VALOR_ACTIVO", "90000.0000", acontecimiento)
    servicio_efectos.registrar_efectos(
        contexto, hecho_id=h.hecho_id, row_version_esperada=creado.row_version, efectos=[va],
    )
    assert _fila_efecto(admin, contexto, va.efecto_id) == ("VALOR_ACTIVO", D("90000.0000"), acontecimiento)
    motivo = leer_fila(admin, contexto.owner_user_id,
                       "SELECT motivo FROM gapto.auditoria WHERE registro_id = %s AND accion = 'CREAR'",
                       (va.efecto_id,))
    assert motivo == (f"VALOR_ACTIVO:{acontecimiento}",)  # F04-D005 intacto


def test_w1_op04_gasto_sin_causa(con_valor_activo, contexto, admin) -> None:
    _, _, gasto = con_valor_activo
    assert _fila_efecto(admin, contexto, gasto) == ("GASTO", D("1200.0000"), None)


def test_w1_op04_entrada_sigue_precediendo(servicio, servicio_efectos, contexto) -> None:
    """La validacion de entrada de F04 no cambia de codigo (PB0-03: los 422
    nuevos no sustituyen ni a la entrada ni al CHECK)."""
    h = _hecho()
    creado = servicio.crear_hecho(contexto, h)
    for efecto, codigo in ((_ef("VALOR_ACTIVO", "1.0000"), CodigoError.VALOR_ACTIVO_SIN_ACONTECIMIENTO),
                           (_ef("VALOR_ACTIVO", "1.0000", "TASACION"), CodigoError.VALOR_ACTIVO_SIN_ACONTECIMIENTO),
                           (_ef("GASTO", "1.0000", "ADQUISICION"), CodigoError.ENTRADA_INVALIDA)):
        _rechazo(lambda: servicio_efectos.registrar_efectos(
            contexto, hecho_id=h.hecho_id, row_version_esperada=creado.row_version, efectos=[efecto],
        ), codigo)


# ==================================================================
# W2 · OP-22 (compuesto)
# ==================================================================

def test_w2_op22_persiste_la_causa(op22, contexto, admin) -> None:
    h = _hecho(tipo="MEJORA_PATRIMONIAL", total="15000.0000")
    va = _ef("VALOR_ACTIVO", "15000.0000", "TRANSFORMACION_CAPITALIZABLE")
    op22.registrar_hecho_compuesto(contexto, DatosHechoCompuesto(hecho=h, efectos=[va]))
    assert _fila_efecto(admin, contexto, va.efecto_id) == (
        "VALOR_ACTIVO", D("15000.0000"), "TRANSFORMACION_CAPITALIZABLE")


def test_w2_op22_sin_acontecimiento_no_escribe_nada(op22, contexto, admin) -> None:
    h = _hecho(tipo="MEJORA_PATRIMONIAL", total="15000.0000")
    _rechazo(lambda: op22.registrar_hecho_compuesto(
        contexto, DatosHechoCompuesto(hecho=h, efectos=[_ef("VALOR_ACTIVO", "15000.0000")])),
        CodigoError.VALOR_ACTIVO_SIN_ACONTECIMIENTO)
    assert leer_fila(admin, contexto.owner_user_id,
                     "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (h.hecho_id,))[0] == 0


# ==================================================================
# W3 · guarda de escritura
# ==================================================================

@pytest.mark.parametrize("tipo,causa,codigo", [
    ("VALOR_ACTIVO", None, REQUERIDA),
    ("VALOR_ACTIVO", "", REQUERIDA),
    ("VALOR_ACTIVO", "TASACION", REQUERIDA),
    ("GASTO", "ADQUISICION", NO_ADMITIDA),
    ("INVERSION", "BAJA_TOTAL", NO_ADMITIDA),
    ("DEUDA", "", NO_ADMITIDA),
])
def test_w3_guarda_rechaza(tipo, causa, codigo) -> None:
    _rechazo(lambda: exigir_causa_valor_activo(tipo, causa), codigo)


@pytest.mark.parametrize("tipo,causa", [("VALOR_ACTIVO", "BAJA_PARCIAL"), ("GASTO", None), ("INGRESO", None)])
def test_w3_guarda_admite(tipo, causa) -> None:
    exigir_causa_valor_activo(tipo, causa)


def test_w3_op21_alta_valor_activo_sin_acontecimiento(con_valor_activo, servicio_correcciones, contexto, admin) -> None:
    """Alta de reemplazo de OP-21: no valida acontecimiento a la entrada, asi que
    es la guarda del INSERT la que rechaza, antes de escribir el efecto."""
    hecho_id, _, _ = con_valor_activo
    version, n = _version(admin, contexto, hecho_id), _efectos_del_hecho(admin, contexto, hecho_id)
    _rechazo(lambda: _op21(servicio_correcciones, contexto, admin, hecho_id,
                           efectos_a_crear=(_ef("VALOR_ACTIVO", "500.0000"),)), REQUERIDA)
    assert (_version(admin, contexto, hecho_id), _efectos_del_hecho(admin, contexto, hecho_id)) == (version, n)


def test_w3_op21_alta_gasto_con_acontecimiento(con_valor_activo, servicio_correcciones, contexto, admin) -> None:
    hecho_id, _, _ = con_valor_activo
    version, n = _version(admin, contexto, hecho_id), _efectos_del_hecho(admin, contexto, hecho_id)
    _rechazo(lambda: _op21(servicio_correcciones, contexto, admin, hecho_id,
                           efectos_a_crear=(_ef("GASTO", "500.0000", "ADQUISICION"),)), NO_ADMITIDA)
    assert (_version(admin, contexto, hecho_id), _efectos_del_hecho(admin, contexto, hecho_id)) == (version, n)


def test_w3_op21_alta_valor_activo_con_acontecimiento(con_valor_activo, servicio_correcciones, contexto, admin) -> None:
    """Control: con causa valida el reemplazo se escribe con ella."""
    hecho_id, _, _ = con_valor_activo
    nuevo = _ef("VALOR_ACTIVO", "500.0000", "TRANSFORMACION_CAPITALIZABLE")
    _op21(servicio_correcciones, contexto, admin, hecho_id, efectos_a_crear=(nuevo,))
    assert _fila_efecto(admin, contexto, nuevo.efecto_id) == (
        "VALOR_ACTIVO", D("500.0000"), "TRANSFORMACION_CAPITALIZABLE")


# ==================================================================
# W4 · OP-21 no convierte hacia ni desde VALOR_ACTIVO
# ==================================================================

def test_w4_op21_hacia_valor_activo(con_valor_activo, servicio_correcciones, contexto, admin) -> None:
    hecho_id, _, gasto = con_valor_activo
    version = _version(admin, contexto, hecho_id)
    _rechazo(lambda: _op21(servicio_correcciones, contexto, admin, hecho_id,
                           efectos_a_actualizar={gasto: {"tipo_efecto": "VALOR_ACTIVO"}}), CONVERSION)
    assert _version(admin, contexto, hecho_id) == version
    assert _fila_efecto(admin, contexto, gasto) == ("GASTO", D("1200.0000"), None)


@pytest.mark.parametrize("destino", ["GASTO", "INVERSION"])
def test_w4_op21_desde_valor_activo(con_valor_activo, servicio_correcciones, contexto, admin, destino) -> None:
    hecho_id, va, _ = con_valor_activo
    version = _version(admin, contexto, hecho_id)
    _rechazo(lambda: _op21(servicio_correcciones, contexto, admin, hecho_id,
                           efectos_a_actualizar={va: {"tipo_efecto": destino}}), CONVERSION)
    assert _version(admin, contexto, hecho_id) == version
    assert _fila_efecto(admin, contexto, va) == ("VALOR_ACTIVO", D("90000.0000"), "ADQUISICION")


def test_w4_op21_desde_valor_activo_junto_a_otro_cambio(con_valor_activo, servicio_correcciones, contexto, admin) -> None:
    """El rechazo es del conjunto: el otro cambio tampoco se aplica (rollback integro)."""
    hecho_id, va, gasto = con_valor_activo
    version = _version(admin, contexto, hecho_id)
    _rechazo(lambda: _op21(servicio_correcciones, contexto, admin, hecho_id, efectos_a_actualizar={
        gasto: {"importe_delta": D("1300.0000")}, va: {"tipo_efecto": "GASTO"}}), CONVERSION)
    assert _version(admin, contexto, hecho_id) == version
    assert _fila_efecto(admin, contexto, gasto) == ("GASTO", D("1200.0000"), None)


def test_w4_op21_importe_de_valor_activo_admitido(con_valor_activo, servicio_correcciones, contexto, admin) -> None:
    hecho_id, va, _ = con_valor_activo
    _op21(servicio_correcciones, contexto, admin, hecho_id,
          efectos_a_actualizar={va: {"importe_delta": D("91000.0000")}})
    assert _fila_efecto(admin, contexto, va) == ("VALOR_ACTIVO", D("91000.0000"), "ADQUISICION")


# ==================================================================
# W5 · traduccion HTTP
# ==================================================================

@pytest.mark.parametrize("codigo", [REQUERIDA, NO_ADMITIDA, CONVERSION, CONVERSION_LOGICA])
def test_w5_http_422_con_mensaje_propio(codigo) -> None:
    status, cuerpo = traducir_error_motor(codigo)
    assert status == 422 and cuerpo["codigo"] == codigo.value and cuerpo["reintentable"] is False
    assert cuerpo["mensaje"] != traducir_error_motor(CodigoError.DELTA_CERO)[1]["mensaje"]


# ==================================================================
# W7 · OP-21 no convierte por retirada y alta (PB0I-06, AJ-B0I-01)
# ==================================================================

def _huella_hecho(admin, contexto, hecho_id):
    """row_version, efectos (id, tipo, importe, causa), atribuciones de sus
    efectos y total de filas de auditoria: lo que un rechazo no puede tocar."""
    return leer_fila(admin, contexto.owner_user_id, """
        SELECT h.row_version,
               (SELECT string_agg(e.id::text || ':' || e.tipo_efecto || ':' ||
                                  e.importe_delta::text || ':' ||
                                  coalesce(e.causa_valor_activo, '-'), ',' ORDER BY e.id)
                  FROM gapto.hecho_efectos e WHERE e.hecho_id = h.id),
               (SELECT count(*) FROM gapto.efecto_atribuciones a
                  JOIN gapto.hecho_efectos e ON e.id = a.efecto_id
                 WHERE e.hecho_id = h.id),
               (SELECT count(*) FROM gapto.auditoria)
          FROM gapto.hechos_financieros h WHERE h.id = %s""", (hecho_id,))


def _rechazo_logico(servicio_correcciones, contexto, admin, hecho_id, **cambios) -> None:
    antes = _huella_hecho(admin, contexto, hecho_id)
    _rechazo(lambda: _op21(servicio_correcciones, contexto, admin, hecho_id, **cambios),
             CONVERSION_LOGICA)
    assert _huella_hecho(admin, contexto, hecho_id) == antes


def test_w7a_retira_valor_activo_y_crea_otro_tipo(con_valor_activo, servicio_correcciones, contexto, admin) -> None:
    hecho_id, va, _ = con_valor_activo
    _rechazo_logico(servicio_correcciones, contexto, admin, hecho_id,
                    efectos_a_eliminar=(va,), efectos_a_crear=(_ef("GASTO", "90000.0000"),))


def test_w7b_retira_otro_tipo_y_crea_valor_activo(con_valor_activo, servicio_correcciones, contexto, admin) -> None:
    hecho_id, _, gasto = con_valor_activo
    _rechazo_logico(servicio_correcciones, contexto, admin, hecho_id,
                    efectos_a_eliminar=(gasto,),
                    efectos_a_crear=(_ef("VALOR_ACTIVO", "1200.0000", "ADQUISICION"),))


def test_w7c_retira_y_crea_valor_activo_con_otra_causa(con_valor_activo, servicio_correcciones, contexto, admin) -> None:
    hecho_id, va, _ = con_valor_activo
    _rechazo_logico(servicio_correcciones, contexto, admin, hecho_id,
                    efectos_a_eliminar=(va,),
                    efectos_a_crear=(_ef("VALOR_ACTIVO", "90000.0000", "TRANSFORMACION_CAPITALIZABLE"),))


def test_w7_mezcla_con_valor_activo_de_igual_causa_tambien_rechaza(
        con_valor_activo, servicio_correcciones, contexto, admin) -> None:
    """La regla es por conjuntos: anadir un reemplazo VALOR_ACTIVO con la misma
    causa no tapa el GASTO que sustituye al VALOR_ACTIVO retirado."""
    hecho_id, va, _ = con_valor_activo
    _rechazo_logico(servicio_correcciones, contexto, admin, hecho_id,
                    efectos_a_eliminar=(va,),
                    efectos_a_crear=(_ef("VALOR_ACTIVO", "45000.0000", "ADQUISICION"),
                                     _ef("GASTO", "45000.0000")))


def test_w7_control_mismo_tipo_no_valor_activo_admitido(con_valor_activo, servicio_correcciones, contexto, admin) -> None:
    """Positivo de control: retirar y dar de alta el MISMO tipo no VALOR_ACTIVO
    sigue funcionando, y el VALOR_ACTIVO del hecho no se toca."""
    hecho_id, va, gasto = con_valor_activo
    nuevo = _ef("GASTO", "1250.0000")
    _op21(servicio_correcciones, contexto, admin, hecho_id,
          efectos_a_eliminar=(gasto,), efectos_a_crear=(nuevo,))
    assert _fila_efecto(admin, contexto, nuevo.efecto_id) == ("GASTO", D("1250.0000"), None)
    assert _fila_efecto(admin, contexto, gasto) is None
    assert _fila_efecto(admin, contexto, va) == ("VALOR_ACTIVO", D("90000.0000"), "ADQUISICION")


def test_w7_control_valor_activo_misma_causa_admitido(con_valor_activo, servicio_correcciones, contexto, admin) -> None:
    """Control de (c): reemplazar un VALOR_ACTIVO por otro con la MISMA causa
    no es una conversion y se admite."""
    hecho_id, va, _ = con_valor_activo
    nuevo = _ef("VALOR_ACTIVO", "91000.0000", "ADQUISICION")
    _op21(servicio_correcciones, contexto, admin, hecho_id,
          efectos_a_eliminar=(va,), efectos_a_crear=(nuevo,))
    assert _fila_efecto(admin, contexto, nuevo.efecto_id) == ("VALOR_ACTIVO", D("91000.0000"), "ADQUISICION")
    assert _fila_efecto(admin, contexto, va) is None


# ==================================================================
# W8 · precedencia: conversion logica antes que causa (RB0-06)
# ==================================================================

def test_w8_conversion_logica_precede_a_causa_requerida(
        con_valor_activo, servicio_correcciones, contexto, admin) -> None:
    """(b) + causa ausente: retira el GASTO y da de alta un VALOR_ACTIVO sin
    acontecimiento. Sin la guarda de OP-21 contestaria la del INSERT
    (CAUSA_VALOR_ACTIVO_REQUERIDA): el contrato fija la de conversion."""
    hecho_id, _, gasto = con_valor_activo
    _rechazo_logico(servicio_correcciones, contexto, admin, hecho_id,
                    efectos_a_eliminar=(gasto,), efectos_a_crear=(_ef("VALOR_ACTIVO", "1200.0000"),))


def test_w8_conversion_logica_precede_a_causa_no_admitida(
        con_valor_activo, servicio_correcciones, contexto, admin) -> None:
    """(a) + causa no admitida: retira el VALOR_ACTIVO y da de alta un GASTO
    con acontecimiento."""
    hecho_id, va, _ = con_valor_activo
    _rechazo_logico(servicio_correcciones, contexto, admin, hecho_id,
                    efectos_a_eliminar=(va,), efectos_a_crear=(_ef("GASTO", "90000.0000", "ADQUISICION"),))


def test_w8_reemplazo_valor_activo_sin_causa_es_conversion(
        con_valor_activo, servicio_correcciones, contexto, admin) -> None:
    """(c) + causa ausente: retirar un VALOR_ACTIVO y dar de alta otro sin
    acontecimiento cambia el conjunto de causas: responde la guarda de OP-21."""
    hecho_id, va, _ = con_valor_activo
    _rechazo_logico(servicio_correcciones, contexto, admin, hecho_id,
                    efectos_a_eliminar=(va,), efectos_a_crear=(_ef("VALOR_ACTIVO", "90000.0000"),))


# ==================================================================
# W6 · cobertura total del writer (AJ-B0-03), por inspeccion del codigo
# ==================================================================

def test_w6_todo_insert_de_efectos_declara_su_causa() -> None:
    """Cada llamada a `insertar_efecto_si_no_existe` en backend/app pasa
    `causa_valor_activo` por nombre, y el SQL de INSERT de hecho_efectos solo
    existe en el repositorio. El parametro no tiene default: olvidarlo seria
    un TypeError, no un efecto sin causa."""
    import ast
    import inspect
    from pathlib import Path

    from app.repositories import efectos_repository

    firma = inspect.signature(efectos_repository.insertar_efecto_si_no_existe)
    assert firma.parameters["causa_valor_activo"].default is inspect.Parameter.empty

    raiz = Path(efectos_repository.__file__).resolve().parents[1]
    llamadas, inserts = [], []
    for fichero in sorted(raiz.rglob("*.py")):
        texto = fichero.read_text(encoding="utf-8")
        if "INSERT INTO gapto.hecho_efectos" in texto:
            inserts.append(fichero.name)
        for nodo in ast.walk(ast.parse(texto)):
            if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                    and nodo.func.attr == "insertar_efecto_si_no_existe"):
                llamadas.append((fichero.name, nodo.lineno,
                                 any(k.arg == "causa_valor_activo" for k in nodo.keywords)))
    assert inserts == ["efectos_repository.py"]
    assert len(llamadas) == 7, llamadas
    assert all(declara for _, _, declara in llamadas), llamadas
