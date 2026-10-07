# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_148_f04_d055_ciclo_vida.py
# Ruta: tests/backend/test_148_f04_d055_ciclo_vida.py
# Descripcion: F04-D055 B1. Ciclo de vida de la posicion generica: cierre con
#   saldo 0 (A1), motivos de runtime (A2), cierre por declaracion con saldo
#   indeterminado (A3), contrato de lectura (A4 / R-Q3), motivo del cierre
#   explicito (R-Q1), reapertura auditable (B1/B2) y marca legacy (B4 / R-Q2).
#
#   Cada rechazo afirma el CODIGO de F04-D055 (o el de la guarda que se
#   reutiliza) y que el estado no cambio; nunca una restriccion incidental.
#   R-Q1 se prueba con saldo conocido y con saldo indeterminado (ajuste 4).
#   Los estados legacy se fabrican con escrituras de FIXTURE que no pasan por
#   el servicio: SQL directo (RV3) o el cierre anterior a D055 auditado
#   ACTUALIZAR. La concurrencia esta en test_149.
# Version: 0.1.0
#   0.1.0 (F04-D055 B1): bateria CC-D055-1, R-Q1, R-Q2, R-Q3 y regresion de
#   F04-D053 tras reabrir (CC-D055-2).
# ============================================================
from __future__ import annotations

import datetime as dt
import decimal

import pytest

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor, MotivoIntegridadPosicion
from app.core.modelos_posicion import (
    TIPO_DERECHO,
    TIPO_OBLIGACION,
    DatosCierre,
    DatosReembolso,
)
from app.repositories import auditoria_repository as auditoria
from app.repositories import posiciones_repository as repo_pos
from app.services.correcciones_service import DatosCorreccion
from app.services.neto_service import NetoService
from conftest import leer_fila
from test_109_op12_posiciones import COBRO, delta, tesoreria_nueva
from test_140_f04_r3_op22 import como_owner
from test_147_f04_d053_integridad import (
    ALTA,
    INICIO,
    _condonar,
    _historico,
    _op21_importe,
    _pagar,
    _posicion,
    _rechazo,
    _version_entidad,
)

D = decimal.Decimal
M = MotivoIntegridadPosicion
CIERRE = dt.date(2026, 7, 1)
APERTURAS = pytest.mark.parametrize("apertura", ["0", None], ids=["conocido", "indeterminado"])
MOTIVOS = pytest.mark.parametrize("motivo", ["LIQUIDADA", "CONDONADA"])


# ==================================================================
# Utilidades
# ==================================================================

def _error(funcion, codigo: CodigoError) -> ErrorMotor:
    with pytest.raises(ErrorMotor) as info:
        funcion()
    assert info.value.codigo is codigo, (info.value.codigo, info.value.mensaje)
    return info.value


def _cerrar(servicio, contexto, admin, entidad_id, motivo="LIQUIDADA", *, version=None):
    return servicio.cerrar_posicion(
        contexto, entidad_id=entidad_id,
        entidad_row_version_esperada=(
            _version_entidad(admin, contexto.owner_user_id, entidad_id)
            if version is None else version),
        cierre=DatosCierre(motivo_cierre=motivo, fecha_cierre=CIERRE))


def _reabrir(servicio, contexto, admin, entidad_id, motivo="error de captura", *, version=None):
    return servicio.reabrir_posicion(
        contexto, entidad_id=entidad_id,
        entidad_row_version_esperada=(
            _version_entidad(admin, contexto.owner_user_id, entidad_id)
            if version is None else version),
        motivo=motivo)


def _cobrar(servicio, contexto, admin, entidad_id, importe, cuenta, **extra):
    d = delta(importe, causa=COBRO, **extra)
    return servicio.reembolsar(
        contexto, entidad_id=entidad_id,
        entidad_row_version_esperada=_version_entidad(admin, contexto.owner_user_id, entidad_id),
        datos=DatosReembolso(delta=d, tesoreria=tesoreria_nueva(cuenta)))


def _fila(admin, contexto, entidad_id) -> dict:
    """Estado integro de la posicion (todas las columnas de §46)."""
    return leer_fila(admin, contexto.owner_user_id,
                     "SELECT to_jsonb(p) FROM gapto.derechos_obligaciones_financieras p "
                     "WHERE p.entidad_id = %s", (entidad_id,))[0]


def _auditoria(admin, contexto, entidad_id, accion) -> list[dict]:
    return leer_fila(admin, contexto.owner_user_id,
                     "SELECT COALESCE(jsonb_agg(jsonb_build_object("
                     "  'motivo', a.motivo, 'antes', a.datos_antes, 'despues', a.datos_despues)"
                     "  ORDER BY a.created_at), '[]'::jsonb) "
                     "FROM gapto.auditoria a WHERE a.tabla = 'derechos_obligaciones_financieras' "
                     "AND a.registro_id = %s AND a.accion = %s", (entidad_id, accion))[0]


def _recuento(admin, contexto, entidad_id) -> tuple[int, int]:
    fila = leer_fila(admin, contexto.owner_user_id,
                     "SELECT count(*) FILTER (WHERE accion = 'CERRAR'), "
                     "count(*) FILTER (WHERE accion = 'REABRIR') FROM gapto.auditoria "
                     "WHERE tabla = 'derechos_obligaciones_financieras' AND registro_id = %s",
                     (entidad_id,))
    return int(fila[0]), int(fila[1])


def _cierre_sql_directo(admin, contexto, entidad_id, motivo="LIQUIDADA", fecha=None) -> None:
    """Forma RV3 (o un writer ajeno): CERRADA sin auditoria de cierre."""
    como_owner(admin, contexto.owner_user_id,
               "UPDATE gapto.derechos_obligaciones_financieras "
               "SET estado = 'CERRADA', motivo_cierre = %s, fecha_cierre = %s WHERE entidad_id = %s",
               (motivo, fecha, entidad_id))


def _cierre_antiguo_actualizar(unidad, contexto, entidad_id, motivo="OTRO") -> None:
    """El cierre tal y como lo escribia el runtime ANTERIOR a D055: UPDATE de
    estado y auditoria ACTUALIZAR (fixture; no pasa por el servicio)."""

    def operacion(sesion):
        previa = repo_pos.leer_posicion(sesion, entidad_id)
        snapshot = repo_pos.cerrar_posicion(sesion, entidad_id, motivo, CIERRE)
        auditoria.registrar(sesion, tabla=repo_pos.TABLA_POSICIONES, registro_id=entidad_id,
                            accion=auditoria.ACCION_ACTUALIZAR, datos_antes_json=previa["snapshot"],
                            datos_despues_json=snapshot, motivo=f"cierre explicito: {motivo}")

    unidad.ejecutar(contexto, operacion, nombre="fixture-cierre-anterior-d055")


def _neto(unidad, contexto, contraparte):
    """(neto, entidades del segmento) de la contraparte en EUR."""
    segmento = NetoService(unidad).posicion_neta(
        contexto, contraparte_actor_id=contraparte).segmento(contraparte, "EUR")
    if segmento is None:
        return None, []
    return segmento.neto, [d.entidad_id for d in segmento.posiciones]


def _a_cero(servicio, contexto, contraparte, apertura="0", tipo=TIPO_OBLIGACION):
    """Posicion sin deltas: saldo 0 (o indeterminado) y S vacio."""
    datos, _ = _posicion(servicio, contexto, contraparte, tipo=tipo, apertura=apertura, importe=None)
    return datos.entidad_id


# ==================================================================
# CC-D055-1 · A1 por las dos vias
# ==================================================================

@pytest.mark.parametrize("extincion", ["pago", "condonacion"])
def test_cc1_cierre_explicito_con_saldo_cero(servicio_posiciones, contexto, admin, contraparte, cuenta,
                                             extincion) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    if extincion == "pago":
        _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "100.0000", dt.date(2026, 6, 15), cuenta)
        motivo = "LIQUIDADA"
    else:
        _condonar(servicio_posiciones, contexto, admin, datos.entidad_id, "100.0000", dt.date(2026, 6, 15))
        motivo = "CONDONADA"
    resultado = _cerrar(servicio_posiciones, contexto, admin, datos.entidad_id, motivo)
    assert resultado.estado == "CERRADA"
    assert resultado.saldo.conocido and resultado.saldo.importe == D("0")
    assert resultado.apertura_indeterminada is False
    fila = _fila(admin, contexto, datos.entidad_id)
    assert (fila["estado"], fila["motivo_cierre"], fila["fecha_cierre"]) == ("CERRADA", motivo, "2026-07-01")


def test_cc1_cierre_explicito_con_residual_rechazado(servicio_posiciones, contexto, admin, contraparte,
                                                    cuenta) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "60.0000", dt.date(2026, 6, 15), cuenta)
    version = _version_entidad(admin, contexto.owner_user_id, datos.entidad_id)
    error = _error(lambda: _cerrar(servicio_posiciones, contexto, admin, datos.entidad_id, "LIQUIDADA"),
                   CodigoError.CIERRE_CON_SALDO_NO_NULO)
    assert error.contexto_extra["saldo"] == "40.0000"
    assert _fila(admin, contexto, datos.entidad_id)["estado"] == "ACTIVA"
    assert _version_entidad(admin, contexto.owner_user_id, datos.entidad_id) == version
    assert _recuento(admin, contexto, datos.entidad_id) == (0, 0)


@pytest.mark.parametrize("via", ["pago", "condonacion", "cobro"])
def test_cc1_pago_parcial_con_cierre_rechazado(servicio_posiciones, contexto, admin, contraparte, cuenta,
                                               via) -> None:
    """A1 en `_aplicar_delta`: reduccion parcial con cierre declarado."""
    tipo = TIPO_DERECHO if via == "cobro" else TIPO_OBLIGACION
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, tipo=tipo)
    if via == "pago":
        cierre = DatosCierre(motivo_cierre="LIQUIDADA", fecha_cierre=CIERRE)
        operacion = lambda: _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "40.0000",  # noqa: E731
                                   dt.date(2026, 6, 15), cuenta, cierre=cierre)
    elif via == "cobro":
        operacion = lambda: _cobrar(servicio_posiciones, contexto, admin, datos.entidad_id, "40.0000", cuenta,  # noqa: E731
                                    cierre=DatosCierre(motivo_cierre="LIQUIDADA", fecha_cierre=CIERRE))
    else:
        operacion = lambda: _condonar(  # noqa: E731
            servicio_posiciones, contexto, admin, datos.entidad_id, "40.0000", dt.date(2026, 6, 15),
            delta_extra={"cierre": DatosCierre(motivo_cierre="CONDONADA", fecha_cierre=CIERRE)})
    _error(operacion, CodigoError.CIERRE_CON_SALDO_NO_NULO)
    assert _fila(admin, contexto, datos.entidad_id)["estado"] == "ACTIVA"
    assert servicio_posiciones.saldo(contexto, datos.entidad_id).saldo.importe == D("100.0000")
    assert leer_fila(admin, contexto.owner_user_id,
                     "SELECT count(*) FROM gapto.hecho_entidades WHERE entidad_id = %s",
                     (datos.entidad_id,))[0] == 1  # solo el alta: nada de la reduccion
    assert _recuento(admin, contexto, datos.entidad_id) == (0, 0)


@pytest.mark.parametrize("extincion", ["pago", "condonacion"])
def test_cc1_reduccion_total_con_cierre_en_la_misma_operacion(servicio_posiciones, contexto, admin,
                                                              contraparte, cuenta, extincion) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    if extincion == "pago":
        _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "100.0000", dt.date(2026, 6, 15), cuenta,
               cierre=DatosCierre(motivo_cierre="LIQUIDADA", fecha_cierre=CIERRE))
    else:
        _condonar(servicio_posiciones, contexto, admin, datos.entidad_id, "100.0000", dt.date(2026, 6, 15),
                  delta_extra={"cierre": DatosCierre(motivo_cierre="CONDONADA", fecha_cierre=CIERRE)})
    assert _fila(admin, contexto, datos.entidad_id)["estado"] == "CERRADA"
    assert _recuento(admin, contexto, datos.entidad_id) == (1, 0)


@pytest.mark.parametrize("via", ["cerrar_posicion", "delta"])
def test_cc1_cierre_indeterminado_por_declaracion(servicio_posiciones, contexto, admin, contraparte, cuenta,
                                                  via) -> None:
    """A3: con saldo indeterminado se cierra por declaracion, sin residual."""
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, apertura=None)
    if via == "cerrar_posicion":
        _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "30.0000", dt.date(2026, 6, 15), cuenta)
        resultado = _cerrar(servicio_posiciones, contexto, admin, datos.entidad_id, "LIQUIDADA")
    else:
        _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "30.0000", dt.date(2026, 6, 15), cuenta,
               cierre=DatosCierre(motivo_cierre="LIQUIDADA", fecha_cierre=CIERRE))
        resultado = servicio_posiciones.saldo(contexto, datos.entidad_id)
    assert resultado.estado == "CERRADA"
    assert resultado.saldo.conocido and resultado.saldo.importe == D("0")
    assert resultado.apertura_indeterminada is True
    # Sin residual fabricado: alta + la reduccion observada, nada mas.
    assert leer_fila(admin, contexto.owner_user_id,
                     "SELECT count(*) FROM gapto.hecho_entidades WHERE entidad_id = %s",
                     (datos.entidad_id,))[0] == 2


# ==================================================================
# CC-D055-1 · A2: CANCELADA y OTRO no se escriben en runtime
# ==================================================================

@pytest.mark.parametrize("motivo", ["CANCELADA", "OTRO"])
@pytest.mark.parametrize("via", ["cerrar_posicion", "delta"])
def test_cc1_cancelada_y_otro_rechazados(servicio_posiciones, contexto, admin, contraparte, cuenta,
                                         motivo, via) -> None:
    if via == "cerrar_posicion":
        entidad_id = _a_cero(servicio_posiciones, contexto, contraparte)
        _error(lambda: _cerrar(servicio_posiciones, contexto, admin, entidad_id, motivo),
               CodigoError.CIERRE_SIN_MOTIVO)
    else:
        datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
        entidad_id = datos.entidad_id
        # La guarda motivo <-> causa de F04-D052 (sin cambios) es A2 en esta via.
        _error(lambda: _pagar(servicio_posiciones, contexto, admin, entidad_id, "100.0000",
                              dt.date(2026, 6, 15), cuenta,
                              cierre=DatosCierre(motivo_cierre=motivo, fecha_cierre=CIERRE)),
               CodigoError.CAUSA_REDUCCION_INVALIDA)
    assert _fila(admin, contexto, entidad_id)["estado"] == "ACTIVA"


# ==================================================================
# CC-D055-1 · B1: reapertura
# ==================================================================

def test_cc1_reabrir_activa_rechazada(servicio_posiciones, contexto, admin, contraparte) -> None:
    entidad_id = _a_cero(servicio_posiciones, contexto, contraparte)
    version = _version_entidad(admin, contexto.owner_user_id, entidad_id)
    _error(lambda: _reabrir(servicio_posiciones, contexto, admin, entidad_id),
           CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO)
    assert _version_entidad(admin, contexto.owner_user_id, entidad_id) == version
    assert _recuento(admin, contexto, entidad_id) == (0, 0)


@pytest.mark.parametrize("motivo", [None, "", "   "], ids=["none", "vacio", "espacios"])
def test_cc1_reabrir_sin_motivo_rechazada(servicio_posiciones, contexto, admin, contraparte, motivo) -> None:
    entidad_id = _a_cero(servicio_posiciones, contexto, contraparte)
    _cerrar(servicio_posiciones, contexto, admin, entidad_id)
    _error(lambda: _reabrir(servicio_posiciones, contexto, admin, entidad_id, motivo),
           CodigoError.MOTIVO_AUSENTE)
    assert _fila(admin, contexto, entidad_id)["estado"] == "CERRADA"
    assert _recuento(admin, contexto, entidad_id) == (1, 0)


def test_cc1_reabrir_version_obsoleta_rechazada(servicio_posiciones, contexto, admin, contraparte) -> None:
    entidad_id = _a_cero(servicio_posiciones, contexto, contraparte)
    cerrada = _cerrar(servicio_posiciones, contexto, admin, entidad_id)
    _error(lambda: _reabrir(servicio_posiciones, contexto, admin, entidad_id,
                            version=cerrada.entidad_row_version - 1),
           CodigoError.VERSION_DESFASADA)
    assert _fila(admin, contexto, entidad_id)["estado"] == "CERRADA"
    assert _recuento(admin, contexto, entidad_id) == (1, 0)


def test_cc1_reabrir_otro_tenant_no_encontrada(servicio_posiciones, contexto, admin, contraparte,
                                               otro_owner) -> None:
    entidad_id = _a_cero(servicio_posiciones, contexto, contraparte)
    cerrada = _cerrar(servicio_posiciones, contexto, admin, entidad_id)
    _error(lambda: servicio_posiciones.reabrir_posicion(
        ContextoOperacion.de_usuario(otro_owner), entidad_id=entidad_id,
        entidad_row_version_esperada=cerrada.entidad_row_version, motivo="ajeno"),
        CodigoError.AGREGADO_NO_ENCONTRADO)
    assert _fila(admin, contexto, entidad_id)["estado"] == "CERRADA"


def test_cc1_reabrir_y_volver_a_cerrar(servicio_posiciones, contexto, admin, contraparte, cuenta) -> None:
    """Ciclo completo: cerrar -> reabrir -> cerrar, con todo el estado comprobado."""
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "100.0000", dt.date(2026, 6, 15), cuenta)
    cerrada = _cerrar(servicio_posiciones, contexto, admin, datos.entidad_id)
    reabierta = _reabrir(servicio_posiciones, contexto, admin, datos.entidad_id)
    assert reabierta.estado == "ACTIVA"
    assert reabierta.entidad_row_version == cerrada.entidad_row_version + 1
    assert reabierta.saldo.conocido and reabierta.saldo.importe == D("0")
    fila = _fila(admin, contexto, datos.entidad_id)
    assert (fila["estado"], fila["motivo_cierre"], fila["fecha_cierre"]) == ("ACTIVA", None, None)
    otra = _cerrar(servicio_posiciones, contexto, admin, datos.entidad_id, "LIQUIDADA")
    assert otra.estado == "CERRADA"
    fila = _fila(admin, contexto, datos.entidad_id)
    assert (fila["estado"], fila["motivo_cierre"], fila["fecha_cierre"]) == ("CERRADA", "LIQUIDADA", "2026-07-01")
    assert _recuento(admin, contexto, datos.entidad_id) == (2, 1)


# ==================================================================
# CC-D055-2 · regresion de F04-D053: reabrir no es bypass
# ==================================================================

def test_cc2_cerrada_sin_reabrir_no_se_corrige_b5(servicio_posiciones, servicio_correcciones, contexto, admin,
                                                 contraparte, cuenta) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    pago, _ = _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "100.0000",
                     dt.date(2026, 6, 15), cuenta)
    _cerrar(servicio_posiciones, contexto, admin, datos.entidad_id)
    _rechazo(lambda: _op21_importe(servicio_correcciones, admin, contexto, pago.hecho_id, pago.efecto_id,
                                   "-90.0000"), M.POSICION_CERRADA)


def test_cc2_reabrir_no_es_bypass_de_d053(servicio_posiciones, servicio_correcciones, contexto, admin,
                                         contraparte, cuenta) -> None:
    """Tras reabrir rigen B2-B6 de F04-D053 y el nuevo cierre cumple A1/A2/R-Q1."""
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    cond = _condonar(servicio_posiciones, contexto, admin, datos.entidad_id, "100.0000", dt.date(2026, 6, 15))
    _cerrar(servicio_posiciones, contexto, admin, datos.entidad_id, "CONDONADA")
    _reabrir(servicio_posiciones, contexto, admin, datos.entidad_id)
    # B2/B3: la correccion no puede dejar el saldo negativo.
    _rechazo(lambda: _op21_importe(servicio_correcciones, admin, contexto, cond.hecho_id, cond.efecto_id,
                                   "-110.0000"), M.SALDO_NEGATIVO)
    # B4: nada anterior al inicio.
    _rechazo(lambda: _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "1.0000",
                            INICIO - dt.timedelta(days=1), cuenta), M.FECHA_ANTERIOR_INICIO)
    # Correccion valida tras reabrir: lo condonado era 90 (saldo 10).
    _op21_importe(servicio_correcciones, admin, contexto, cond.hecho_id, cond.efecto_id, "-90.0000")
    assert servicio_posiciones.saldo(contexto, datos.entidad_id).saldo.importe == D("10.0000")
    # A1: el nuevo cierre exige extinguir antes el residual.
    _error(lambda: _cerrar(servicio_posiciones, contexto, admin, datos.entidad_id, "CONDONADA"),
           CodigoError.CIERRE_CON_SALDO_NO_NULO)
    _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "10.0000", dt.date(2026, 6, 20), cuenta)
    # R-Q1: S = {CONDONACION, PAGO} es mixto, LIQUIDADA admitida.
    assert _cerrar(servicio_posiciones, contexto, admin, datos.entidad_id, "LIQUIDADA").estado == "CERRADA"
    assert _recuento(admin, contexto, datos.entidad_id) == (2, 1)


def test_a1_cierre_con_trayectoria_invalida_lo_rechaza_d053(servicio_posiciones, contexto, admin,
                                                            contraparte) -> None:
    """A1 coexiste con F04-D053: saldo final 0 pero trayectoria invalida.

    Alta +100 el 1 de junio; condonacion de 100 con cierre fechada el 1 de
    mayo: el saldo final es 0 (A1 no rechaza) pero S(1 de mayo) = -100 (B2)."""
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    _rechazo(lambda: _condonar(servicio_posiciones, contexto, admin, datos.entidad_id, "100.0000",
                               dt.date(2026, 5, 1),
                               delta_extra={"cierre": DatosCierre(motivo_cierre="CONDONADA",
                                                                  fecha_cierre=CIERRE)}),
             M.SALDO_NEGATIVO)
    assert _fila(admin, contexto, datos.entidad_id)["estado"] == "ACTIVA"
    assert _recuento(admin, contexto, datos.entidad_id) == (0, 0)


# ==================================================================
# R-Q1 · motivo del cierre explicito determinado por S (ventana A1)
# ==================================================================

def _intentar_ambos(servicio, contexto, admin, entidad_id, admitidos: set[str]) -> None:
    """Prueba primero los motivos NO admitidos (rechazo y estado intacto) y
    despues cierra con uno admitido."""
    for motivo in sorted({"LIQUIDADA", "CONDONADA"} - admitidos):
        _error(lambda m=motivo: _cerrar(servicio, contexto, admin, entidad_id, m),
               CodigoError.CAUSA_REDUCCION_INVALIDA)
        assert _fila(admin, contexto, entidad_id)["estado"] == "ACTIVA"
    motivo = sorted(admitidos)[0]
    assert _cerrar(servicio, contexto, admin, entidad_id, motivo).estado == "CERRADA"


@APERTURAS
def test_rq1_pago_solo_liquidada(servicio_posiciones, contexto, admin, contraparte, cuenta, apertura) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, apertura=apertura)
    _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "100.0000", dt.date(2026, 6, 15), cuenta)
    _intentar_ambos(servicio_posiciones, contexto, admin, datos.entidad_id, {"LIQUIDADA"})


@APERTURAS
def test_rq1_cobro_solo_liquidada(servicio_posiciones, contexto, admin, contraparte, cuenta, apertura) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, tipo=TIPO_DERECHO, apertura=apertura)
    _cobrar(servicio_posiciones, contexto, admin, datos.entidad_id, "100.0000", cuenta)
    _intentar_ambos(servicio_posiciones, contexto, admin, datos.entidad_id, {"LIQUIDADA"})


@APERTURAS
def test_rq1_condonacion_solo_condonada(servicio_posiciones, contexto, admin, contraparte, apertura) -> None:
    """R-F04-D055-Q1: una posicion cuya unica causa es CONDONACION no se
    cierra LIQUIDADA."""
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, apertura=apertura)
    _condonar(servicio_posiciones, contexto, admin, datos.entidad_id, "100.0000", dt.date(2026, 6, 15))
    _intentar_ambos(servicio_posiciones, contexto, admin, datos.entidad_id, {"CONDONADA"})


@APERTURAS
@MOTIVOS
def test_rq1_mixto_ambos(servicio_posiciones, contexto, admin, contraparte, cuenta, apertura, motivo) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, apertura=apertura)
    _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "60.0000", dt.date(2026, 6, 10), cuenta)
    _condonar(servicio_posiciones, contexto, admin, datos.entidad_id, "40.0000", dt.date(2026, 6, 20))
    assert _cerrar(servicio_posiciones, contexto, admin, datos.entidad_id, motivo).estado == "CERRADA"


@APERTURAS
@MOTIVOS
def test_rq1_vacio_ambos(servicio_posiciones, contexto, admin, contraparte, apertura, motivo) -> None:
    entidad_id = _a_cero(servicio_posiciones, contexto, contraparte, apertura=apertura)
    assert _cerrar(servicio_posiciones, contexto, admin, entidad_id, motivo).estado == "CERRADA"


@APERTURAS
@MOTIVOS
def test_rq1_solo_no_determinable_ambos(unidad, servicio_posiciones, contexto, admin, contraparte,
                                        apertura, motivo) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, apertura=apertura)
    _historico(unidad, contexto, datos.entidad_id, dt.date(2026, 6, 10), "-100.0000")
    assert _cerrar(servicio_posiciones, contexto, admin, datos.entidad_id, motivo).estado == "CERRADA"


@APERTURAS
def test_rq1_pago_y_no_determinable_solo_liquidada(unidad, servicio_posiciones, contexto, admin, contraparte,
                                                   cuenta, apertura) -> None:
    """NO_DETERMINABLE no entra en S: {PAGO} + NO_DETERMINABLE -> {PAGO}."""
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, apertura=apertura)
    _historico(unidad, contexto, datos.entidad_id, dt.date(2026, 6, 10), "-40.0000")
    _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "60.0000", dt.date(2026, 6, 15), cuenta)
    _intentar_ambos(servicio_posiciones, contexto, admin, datos.entidad_id, {"LIQUIDADA"})


def test_rq1_reduccion_anterior_al_inicio_fuera_de_s(unidad, servicio_posiciones, contexto, admin,
                                                     contraparte, cuenta) -> None:
    """Ventana canonica de F04-D053: una CONDONACION anterior al inicio ya
    esta dentro de la apertura y no entra en S; dentro de la ventana solo hay
    PAGO -> solo LIQUIDADA. `causas_de_reduccion` (sin ventana) no cambia."""
    inicio = dt.date(2026, 3, 1)
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, apertura="40.0000", inicio=inicio,
                         importe=None)
    _historico(unidad, contexto, datos.entidad_id, dt.date(2026, 2, 1), "-10.0000", codigo="CONDONACION")
    _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "40.0000", dt.date(2026, 6, 15), cuenta)
    assert {c.causa for c in servicio_posiciones.causas_de_reduccion(contexto, datos.entidad_id)} == {
        "PAGO", "CONDONACION"}
    _intentar_ambos(servicio_posiciones, contexto, admin, datos.entidad_id, {"LIQUIDADA"})


def test_rq1_sin_frontera_con_apertura_indeterminada(unidad, servicio_posiciones, contexto, admin,
                                                     contraparte, cuenta) -> None:
    """Con saldo_apertura NULL no hay frontera: cuentan todas las reducciones."""
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, apertura=None, importe=None)
    _historico(unidad, contexto, datos.entidad_id, dt.date(2025, 1, 1), "-10.0000", codigo="CONDONACION")
    _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "40.0000", dt.date(2026, 6, 15), cuenta)
    assert _cerrar(servicio_posiciones, contexto, admin, datos.entidad_id, "CONDONADA").estado == "CERRADA"


@APERTURAS
@pytest.mark.parametrize("ultima", ["pago", "condonacion"])
def test_rq1_no_depende_de_la_ultima_reduccion(servicio_posiciones, contexto, admin, contraparte, cuenta,
                                               apertura, ultima) -> None:
    """S mixto admite el motivo que NO corresponde a la ultima reduccion."""
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, apertura=apertura)
    fechas = {"pago": dt.date(2026, 6, 10), "condonacion": dt.date(2026, 6, 10)}
    fechas[ultima] = dt.date(2026, 6, 20)
    _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "60.0000", fechas["pago"], cuenta)
    _condonar(servicio_posiciones, contexto, admin, datos.entidad_id, "40.0000", fechas["condonacion"])
    contrario = "CONDONADA" if ultima == "pago" else "LIQUIDADA"
    assert _cerrar(servicio_posiciones, contexto, admin, datos.entidad_id, contrario).estado == "CERRADA"


@APERTURAS
@MOTIVOS
@pytest.mark.parametrize("primero", ["pago", "condonacion"])
def test_rq1_mixto_mismo_dia_sin_orden(servicio_posiciones, contexto, admin, contraparte, cuenta,
                                       apertura, motivo, primero) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, apertura=apertura)
    dia = dt.date(2026, 6, 15)
    pasos = [
        lambda: _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "60.0000", dia, cuenta),
        lambda: _condonar(servicio_posiciones, contexto, admin, datos.entidad_id, "40.0000", dia),
    ]
    for paso in (pasos if primero == "pago" else pasos[::-1]):
        paso()
    assert _cerrar(servicio_posiciones, contexto, admin, datos.entidad_id, motivo).estado == "CERRADA"


# ==================================================================
# R-Q2 · reapertura legacy (ajuste 7): nada fabricado, prefijo correcto
# ==================================================================

def _comprobar_reapertura(admin, contexto, entidad_id, antes: dict, prefijo: str, motivo: str) -> None:
    """La ULTIMA fila REABRIR: prefijo, datos_antes = estado encontrado
    integro, datos_despues = estado posterior integro, sin claves anadidas."""
    fila = _auditoria(admin, contexto, entidad_id, "REABRIR")[-1]
    assert fila["motivo"] == f"{prefijo}: {motivo}"
    assert fila["antes"] == antes
    assert fila["despues"] == _fila(admin, contexto, entidad_id)
    assert set(fila["antes"]) == set(repo_pos.TIPOS_SQL_POSICION)
    assert (fila["despues"]["estado"], fila["despues"]["motivo_cierre"], fila["despues"]["fecha_cierre"]) == (
        "ACTIVA", None, None)


def test_rq2_rv3_sin_auditoria(servicio_posiciones, contexto, admin, contraparte) -> None:
    """CERRADA de RV3 (fecha_cierre NULL, sin auditoria de cierre)."""
    entidad_id = _a_cero(servicio_posiciones, contexto, contraparte)
    _cierre_sql_directo(admin, contexto, entidad_id, "LIQUIDADA", None)
    antes = _fila(admin, contexto, entidad_id)
    assert antes["fecha_cierre"] is None
    _reabrir(servicio_posiciones, contexto, admin, entidad_id, "dato RV3")
    _comprobar_reapertura(admin, contexto, entidad_id, antes, "REABRIR LEGACY", "dato RV3")
    assert _auditoria(admin, contexto, entidad_id, "REABRIR")[-1]["antes"]["fecha_cierre"] is None
    assert _recuento(admin, contexto, entidad_id) == (0, 1)  # ningun CERRAR fabricado


def test_rq2_cierre_antiguo_actualizar(unidad, servicio_posiciones, contexto, admin, contraparte) -> None:
    """R-F04-D055-Q6: un cierre anterior a D055 auditado ACTUALIZAR no se
    reinterpreta como CERRAR."""
    entidad_id = _a_cero(servicio_posiciones, contexto, contraparte)
    _cierre_antiguo_actualizar(unidad, contexto, entidad_id, "OTRO")
    antes = _fila(admin, contexto, entidad_id)
    _reabrir(servicio_posiciones, contexto, admin, entidad_id, "cierre antiguo")
    _comprobar_reapertura(admin, contexto, entidad_id, antes, "REABRIR LEGACY", "cierre antiguo")
    assert antes["motivo_cierre"] == "OTRO"
    assert _recuento(admin, contexto, entidad_id) == (0, 1)


def test_rq2_cerrar_reabrir(servicio_posiciones, contexto, admin, contraparte) -> None:
    entidad_id = _a_cero(servicio_posiciones, contexto, contraparte)
    previa = _fila(admin, contexto, entidad_id)
    _cerrar(servicio_posiciones, contexto, admin, entidad_id, "LIQUIDADA")
    cierre = _auditoria(admin, contexto, entidad_id, "CERRAR")
    assert len(cierre) == 1 and cierre[0]["antes"] == previa
    antes = _fila(admin, contexto, entidad_id)
    assert cierre[0]["despues"] == antes
    _reabrir(servicio_posiciones, contexto, admin, entidad_id, "error de captura")
    _comprobar_reapertura(admin, contexto, entidad_id, antes, "REABRIR", "error de captura")
    assert (antes["estado"], antes["motivo_cierre"], antes["fecha_cierre"]) == ("CERRADA", "LIQUIDADA", "2026-07-01")


def test_rq2_cerrar_reabrir_cerrar_reabrir(servicio_posiciones, contexto, admin, contraparte) -> None:
    entidad_id = _a_cero(servicio_posiciones, contexto, contraparte)
    for numero in (1, 2):
        _cerrar(servicio_posiciones, contexto, admin, entidad_id, "LIQUIDADA")
        antes = _fila(admin, contexto, entidad_id)
        _reabrir(servicio_posiciones, contexto, admin, entidad_id, f"vuelta {numero}")
        _comprobar_reapertura(admin, contexto, entidad_id, antes, "REABRIR", f"vuelta {numero}")
    assert _recuento(admin, contexto, entidad_id) == (2, 2)


def test_rq2_legacy_reabrir_cerrar_reabrir(servicio_posiciones, contexto, admin, contraparte) -> None:
    entidad_id = _a_cero(servicio_posiciones, contexto, contraparte)
    _cierre_sql_directo(admin, contexto, entidad_id)
    antes = _fila(admin, contexto, entidad_id)
    _reabrir(servicio_posiciones, contexto, admin, entidad_id, "legacy")
    _comprobar_reapertura(admin, contexto, entidad_id, antes, "REABRIR LEGACY", "legacy")
    _cerrar(servicio_posiciones, contexto, admin, entidad_id, "CONDONADA")
    antes = _fila(admin, contexto, entidad_id)
    _reabrir(servicio_posiciones, contexto, admin, entidad_id, "tras el ciclo")
    _comprobar_reapertura(admin, contexto, entidad_id, antes, "REABRIR", "tras el ciclo")
    assert _recuento(admin, contexto, entidad_id) == (1, 2)


def test_rq2_tres_o_mas_reaperturas(servicio_posiciones, contexto, admin, contraparte) -> None:
    entidad_id = _a_cero(servicio_posiciones, contexto, contraparte)
    for numero in range(1, 5):
        _cerrar(servicio_posiciones, contexto, admin, entidad_id, "LIQUIDADA")
        antes = _fila(admin, contexto, entidad_id)
        _reabrir(servicio_posiciones, contexto, admin, entidad_id, f"vuelta {numero}")
        _comprobar_reapertura(admin, contexto, entidad_id, antes, "REABRIR", f"vuelta {numero}")
        assert _recuento(admin, contexto, entidad_id) == (numero, numero)


def test_rq2_varias_reaperturas_y_cierre_sql_directo(servicio_posiciones, contexto, admin, contraparte) -> None:
    """legacy -> REABRIR -> CERRAR -> REABRIR -> cierre SQL -> REABRIR: con
    C=1 y R=2 el cierre actual no esta acreditado (no basta con que exista
    ALGUN CERRAR)."""
    entidad_id = _a_cero(servicio_posiciones, contexto, contraparte)
    _cierre_sql_directo(admin, contexto, entidad_id)
    _reabrir(servicio_posiciones, contexto, admin, entidad_id, "uno")
    _cerrar(servicio_posiciones, contexto, admin, entidad_id)
    _reabrir(servicio_posiciones, contexto, admin, entidad_id, "dos")
    _cierre_sql_directo(admin, contexto, entidad_id, "LIQUIDADA", dt.date(2026, 8, 1))
    antes = _fila(admin, contexto, entidad_id)
    _reabrir(servicio_posiciones, contexto, admin, entidad_id, "tres")
    _comprobar_reapertura(admin, contexto, entidad_id, antes, "REABRIR LEGACY", "tres")
    assert _recuento(admin, contexto, entidad_id) == (1, 3)


def test_rq2_legacy_reabrir_y_cierre_sql_directo(servicio_posiciones, contexto, admin, contraparte) -> None:
    """legacy -> REABRIR -> cierre SQL (C=0, R=1) -> legacy."""
    entidad_id = _a_cero(servicio_posiciones, contexto, contraparte)
    _cierre_sql_directo(admin, contexto, entidad_id)
    _reabrir(servicio_posiciones, contexto, admin, entidad_id, "uno")
    _cierre_sql_directo(admin, contexto, entidad_id)
    antes = _fila(admin, contexto, entidad_id)
    _reabrir(servicio_posiciones, contexto, admin, entidad_id, "dos")
    _comprobar_reapertura(admin, contexto, entidad_id, antes, "REABRIR LEGACY", "dos")


def test_rq2_limite_declarado_r_f04_044(servicio_posiciones, contexto, admin, contraparte) -> None:
    """Limite ACEPTADO: CERRAR -> REABRIR -> cierre SQL (C=1, R=1) no es
    detectable sin orden fiable ni DDL y se clasifica no legacy."""
    entidad_id = _a_cero(servicio_posiciones, contexto, contraparte)
    _cerrar(servicio_posiciones, contexto, admin, entidad_id)
    _reabrir(servicio_posiciones, contexto, admin, entidad_id, "uno")
    _cierre_sql_directo(admin, contexto, entidad_id)
    antes = _fila(admin, contexto, entidad_id)
    _reabrir(servicio_posiciones, contexto, admin, entidad_id, "dos")
    _comprobar_reapertura(admin, contexto, entidad_id, antes, "REABRIR", "dos")


# ==================================================================
# R-Q3 · contrato de lectura A4 (ajuste 11)
# ==================================================================

def test_rq3_activa_conocida(unidad, servicio_posiciones, contexto, admin, contraparte, cuenta) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, tipo=TIPO_DERECHO)
    resultado = _cobrar(servicio_posiciones, contexto, admin, datos.entidad_id, "40.0000", cuenta)
    for lectura in (resultado, servicio_posiciones.saldo(contexto, datos.entidad_id)):
        assert lectura.estado == "ACTIVA" and lectura.saldo.importe == D("60.0000")
        assert lectura.apertura_indeterminada is False
    assert _neto(unidad, contexto, contraparte) == (D("60.0000"), [datos.entidad_id])


def test_rq3_activa_indeterminada(unidad, servicio_posiciones, contexto, admin, contraparte) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, tipo=TIPO_DERECHO, apertura=None)
    lectura = servicio_posiciones.saldo(contexto, datos.entidad_id)
    assert lectura.saldo.conocido is False  # INV-17 intacto
    assert lectura.apertura_indeterminada is False
    neto, entidades = _neto(unidad, contexto, contraparte)
    assert neto is None and entidades == [datos.entidad_id]


def test_rq3_cerrada_conocida(unidad, servicio_posiciones, contexto, admin, contraparte, cuenta) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, tipo=TIPO_DERECHO)
    _cobrar(servicio_posiciones, contexto, admin, datos.entidad_id, "100.0000", cuenta)
    cerrada = _cerrar(servicio_posiciones, contexto, admin, datos.entidad_id)
    for lectura in (cerrada, servicio_posiciones.saldo(contexto, datos.entidad_id)):
        assert lectura.saldo.conocido and lectura.saldo.importe == D("0")
        assert lectura.apertura_indeterminada is False
    assert _neto(unidad, contexto, contraparte) == (None, [])


def test_rq3_cerrada_indeterminada(unidad, servicio_posiciones, contexto, admin, contraparte, cuenta) -> None:
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, tipo=TIPO_DERECHO, apertura=None)
    _cobrar(servicio_posiciones, contexto, admin, datos.entidad_id, "30.0000", cuenta)
    cerrada = _cerrar(servicio_posiciones, contexto, admin, datos.entidad_id)
    for lectura in (cerrada, servicio_posiciones.saldo(contexto, datos.entidad_id)):
        assert lectura.saldo.conocido is True and lectura.saldo.importe == D("0")
        assert lectura.apertura_indeterminada is True
    assert _neto(unidad, contexto, contraparte) == (None, [])
    reabierta = _reabrir(servicio_posiciones, contexto, admin, datos.entidad_id)
    assert reabierta.saldo.conocido is False and reabierta.apertura_indeterminada is False


@pytest.mark.parametrize("apertura", ["0", None], ids=["conocida", "indeterminada"])
def test_rq3_cerrada_legacy_con_residual(unidad, servicio_posiciones, contexto, admin, contraparte,
                                         apertura) -> None:
    """Legacy con residual (SQL directo): se lee 0 sin tocar sus deltas, igual
    que el neto; reabierta vuelve al saldo canonico y el neto lo incluye."""
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte, tipo=TIPO_DERECHO, apertura=apertura)
    _cierre_sql_directo(admin, contexto, datos.entidad_id)
    lectura = servicio_posiciones.saldo(contexto, datos.entidad_id)
    assert lectura.estado == "CERRADA"
    assert lectura.saldo.conocido and lectura.saldo.importe == D("0")
    assert lectura.apertura_indeterminada is (apertura is None)
    assert _neto(unidad, contexto, contraparte) == (None, [])
    assert leer_fila(admin, contexto.owner_user_id,
                     "SELECT count(*) FROM gapto.hecho_entidades WHERE entidad_id = %s",
                     (datos.entidad_id,))[0] == 1  # el delta de alta sigue ahi
    reabierta = _reabrir(servicio_posiciones, contexto, admin, datos.entidad_id, "legacy con residual")
    assert reabierta.estado == "ACTIVA" and reabierta.apertura_indeterminada is False
    if apertura is None:
        assert reabierta.saldo.conocido is False
        neto, entidades = _neto(unidad, contexto, contraparte)
        assert neto is None and entidades == [datos.entidad_id]
    else:
        assert reabierta.saldo.importe == D("100.0000")
        assert servicio_posiciones.saldo(contexto, datos.entidad_id).saldo.importe == D("100.0000")
        assert _neto(unidad, contexto, contraparte) == (D("100.0000"), [datos.entidad_id])
    assert _auditoria(admin, contexto, datos.entidad_id, "REABRIR")[-1]["motivo"].startswith("REABRIR LEGACY: ")


def test_rq3_ningun_validador_lee_la_lectura(servicio_posiciones, contexto, admin, contraparte, cuenta) -> None:
    """Ajuste 10, prueba directa: el A1 de la via delta se evalua con la
    posicion YA CERRADA. Si leyese el saldo de lectura (0) aceptaria el
    residual; lee el canonico y rechaza."""
    datos, _ = _posicion(servicio_posiciones, contexto, contraparte)
    error = _error(lambda: _pagar(servicio_posiciones, contexto, admin, datos.entidad_id, "99.9999",
                                  dt.date(2026, 6, 15), cuenta,
                                  cierre=DatosCierre(motivo_cierre="LIQUIDADA", fecha_cierre=CIERRE)),
                   CodigoError.CIERRE_CON_SALDO_NO_NULO)
    assert error.contexto_extra["saldo"] == "0.0001"
