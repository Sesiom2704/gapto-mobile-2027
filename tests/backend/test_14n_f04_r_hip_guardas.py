# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_14n_f04_r_hip_guardas.py
# Ruta: tests/backend/test_14n_f04_r_hip_guardas.py
# Descripcion: T3-F06 · F04-R-HIP, subhito F04 (literal F04 v1.1 A1-A5 y A9;
#   mandato v1.2 §9 y adenda v1.3 con D-04 y D-07). Por SERVICIO, como
#   gapto_runtime con RLS; fixtures sinteticos con la forma del contrato v0.4
#   (f04_r_hip_formas.py), creados bajo gapto_owner donde el motor no escribe.
#     O-H13-{cuota,Hd}-{a,b,c,d}: OP-21 sobre el efecto vinculado a una
#       FINANCIACION a nivel de efecto -> OWNERSHIP_F07 con su modalidad y
#       estado identico (efectos, atribuciones, vinculos, conciliaciones,
#       row_version y auditoria).
#     O-H13-NH: el vinculo FINANCIACION de nivel hecho se sigue retirando.
#     O-PREC-21 (D-07): con row_version desfasada responde la guarda, no
#       VERSION_DESFASADA; control con un hecho que no es de financiacion.
#     H-B-01-1/2/3: guarda INVERSION existente (baja conjunta, baja aislada y
#       vinculo principal de hecho).
#     O-A9-03-{C,Hd} (sin conciliacion), O-A9-03P-{C,Hd} (con conciliacion;
#       Hd discrimina por codigo, D-04), O-PREC-03P (D-07) y su control,
#       O-A9-NH (no ampliacion) y no regresion del orden de errores de OP-03P
#       para hechos que no son de financiacion (D-04).
#     V3-FIX: HIPOTECA sin cuadro y apertura indeterminada con un hecho
#       importado: las guardas lo tratan como financiacion.
#   Oraculos con ORDER BY y fechas fijas.
# Version: 0.1.0 (F06 T3-F06 · F04-R-HIP, paso 3)
# ============================================================

from __future__ import annotations

import decimal
import uuid

import pytest

import f04_r_hip_formas as fz
from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos_efectos import DatosEfecto
from app.services.anulacion_tesoreria_service import AnulacionTesoreriaService, DatosAnulacionRegistro
from app.services.correcciones_service import DatosCorreccion
from app.services.previsiones_service import adquirir_impacto_ancla, aplicar_impacto_ancla
from test_140_f04_r3_op22 import SUBTIPOS

D = decimal.Decimal
#: getattr: el fichero se ejecuta tambien sobre el HEAD de inicio (e90a33e), sin el
#: codigo, para guardar la prueba de discriminacion (los negativos deben fallar alli).
A9 = getattr(CodigoError, "ANULACION_FINANCIACION_SIN_REVERSION", None)


@pytest.fixture()
def gdsn(dsn):
    return dsn


def _ctx(owner):
    return ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4())


def _forma(tipo, gdsn, unidad, contexto, owner, cuenta=None):
    entidad, _ = fz.financiacion(gdsn, owner)
    hacer = fz.cuota_pagada if tipo == "cuota" else fz.desembolso_hd
    return hacer(gdsn, unidad, contexto, owner, entidad, cuenta_id=cuenta)


def _modalidad(m, f):
    if m == "a":
        extra = {}
        if f.efecto_gasto is None:  # Hd: sin reemplazo se quedaria sin efectos (otra guarda, tardia)
            extra["efectos_a_crear"] = (DatosEfecto(efecto_id=uuid.uuid4(), tipo_efecto="DEUDA",
                                                    importe_delta=fz.P, estado_atribucion="NO_DISPONIBLE"),)
        return dict(efectos_a_eliminar=(f.efecto_deuda,), entidades_a_eliminar=(f.vinculo_id,), **extra), \
            "BAJA_CONJUNTA"
    if m == "b":
        return dict(entidades_a_eliminar=(f.vinculo_id,)), "BAJA_VINCULO"
    if m == "c":
        return dict(efectos_a_actualizar={f.efecto_deuda: {"importe_delta": D("-1.0000") if f.efecto_gasto
                                                           else D("1.0000")}}), "IMPORTE_DELTA"
    return dict(efectos_a_actualizar={f.efecto_deuda: {"tipo_efecto": "GASTO"}}), "TIPO_EFECTO"


def _rechazo(llamada, codigo):
    with pytest.raises(ErrorMotor) as exc:
        llamada()
    assert exc.value.codigo is codigo, (exc.value.codigo, exc.value.contexto_extra)
    return exc.value


# ------------------------------------------------------------------ O-H13 (A1, A2)

@pytest.mark.parametrize("modalidad", ["a", "b", "c", "d"])
@pytest.mark.parametrize("tipo", ["cuota", "hd"])
def test_o_h13_op21_rechaza_la_modalidad_con_estado_identico(
    servicio_correcciones, unidad, contexto, owner, gdsn, tipo, modalidad
) -> None:
    f = _forma(tipo, gdsn, unidad, contexto, owner)
    cambios, esperada = _modalidad(modalidad, f)
    antes = fz.foto(gdsn, owner, f.hecho_id)
    e = _rechazo(lambda: servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=f.hecho_id, row_version_esperada=f.version, motivo="F04-R-HIP O-H13", **cambios)),
        CodigoError.OWNERSHIP_F07)
    assert e.contexto_extra == {"motivo": "FINANCIACION", "modalidades": [esperada]}
    assert fz.foto(gdsn, owner, f.hecho_id) == antes


@pytest.mark.parametrize("modalidad", ["b", "c", "d"])
@pytest.mark.parametrize("tipo", ["cuota", "hd"])
def test_o_prec_21_la_guarda_precede_a_version_desfasada(
    servicio_correcciones, unidad, contexto, owner, gdsn, tipo, modalidad
) -> None:
    """D-07 (MF04-10): con row_version desfasada responde la guarda, no tocar_raiz."""
    f = _forma(tipo, gdsn, unidad, contexto, owner)
    cambios, esperada = _modalidad(modalidad, f)
    antes = fz.foto(gdsn, owner, f.hecho_id)
    e = _rechazo(lambda: servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=f.hecho_id, row_version_esperada=f.version - 1, motivo="F04-R-HIP O-PREC-21", **cambios)),
        CodigoError.OWNERSHIP_F07)
    assert e.contexto_extra["modalidades"] == [esperada]
    assert fz.foto(gdsn, owner, f.hecho_id) == antes


def test_o_prec_21_control_hecho_ordinario_da_version_desfasada(
    servicio_correcciones, unidad, contexto, owner, gdsn
) -> None:
    g = fz.gasto_ordinario(gdsn, unidad, contexto, owner)
    _rechazo(lambda: servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=g.hecho_id, row_version_esperada=g.version - 1, motivo="control D-07",
        efectos_a_actualizar={g.efecto_gasto: {"importe_delta": D("1.0000")}})), CodigoError.VERSION_DESFASADA)


def test_o_h13_nh_vinculo_de_nivel_hecho_se_sigue_retirando(
    servicio_correcciones, unidad, contexto, owner, gdsn
) -> None:
    """A3: no ampliacion (MF04-06)."""
    entidad, _ = fz.financiacion(gdsn, owner)
    g = fz.gasto_ordinario(gdsn, unidad, contexto, owner, entidad_nivel_hecho=entidad)
    r = servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=g.hecho_id, row_version_esperada=g.version, motivo="F04-R-HIP O-H13-NH",
        entidades_a_eliminar=(g.vinculo_id,)))
    assert r.hecho_row_version == g.version + 1
    assert fz.foto(gdsn, owner, g.hecho_id)["vinculos"] == []


def test_o_h13_nh_en_un_hecho_de_cuota_el_cambio_de_otro_efecto_sigue(
    servicio_correcciones, unidad, contexto, owner, gdsn
) -> None:
    """El efecto GASTO (intereses) de la cuota no esta vinculado: su
    descripcion se corrige como hoy (la guarda mira solo el efecto vinculado)."""
    f = _forma("cuota", gdsn, unidad, contexto, owner)
    r = servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=f.hecho_id, row_version_esperada=f.version, motivo="F04-R-HIP no ampliacion",
        efectos_a_actualizar={f.efecto_gasto: {"descripcion": "intereses"}}))
    assert r.hecho_row_version == f.version + 1


# ------------------------------------------------------------------ H-B-01 (A4)

def _inversion(gdsn, owner):
    i = uuid.uuid4()
    fz.como_owner(gdsn, owner, [
        ("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) VALUES (%s, %s, 'INVERSION', "
         "'Fondo sintetico')", (i, owner)),
        (SUBTIPOS["INVERSION"], (i,)),
    ])
    return i


def _vinculo_inversion(gdsn, owner, hecho_id, efecto_id, entidad_id, principal):
    v = uuid.uuid4()
    fz.como_owner(gdsn, owner, [(
        "INSERT INTO gapto.hecho_entidades (id, hecho_id, efecto_id, entidad_id, tipo_relacion, principal, "
        "owner_user_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (v, hecho_id, efecto_id, entidad_id, "AFECTA_A" if principal else "RELACIONADO_CON", principal, owner))])
    return v


@pytest.mark.parametrize("caso", ["baja_conjunta", "baja_aislada", "principal_de_hecho"])
def test_h_b_01_guarda_inversion(servicio_correcciones, unidad, contexto, owner, gdsn, caso) -> None:
    g = fz.gasto_ordinario(gdsn, unidad, contexto, owner)
    inv = _inversion(gdsn, owner)
    if caso == "principal_de_hecho":
        v = _vinculo_inversion(gdsn, owner, g.hecho_id, None, inv, True)
        cambios = dict(entidades_a_eliminar=(v,))
    else:
        v = _vinculo_inversion(gdsn, owner, g.hecho_id, g.efecto_gasto, inv, False)
        cambios = dict(entidades_a_eliminar=(v,))
        if caso == "baja_conjunta":
            cambios.update(efectos_a_eliminar=(g.efecto_gasto,), efectos_a_crear=(DatosEfecto(
                efecto_id=uuid.uuid4(), tipo_efecto="GASTO", importe_delta=fz.CUOTA,
                estado_atribucion="NO_DISPONIBLE"),))
    version = fz.version(gdsn, owner, g.hecho_id)
    antes = fz.foto(gdsn, owner, g.hecho_id)
    _rechazo(lambda: servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=g.hecho_id, row_version_esperada=version, motivo="H-B-01", toca_inversion=True, **cambios)),
        CodigoError.OWNERSHIP_F07)
    assert fz.foto(gdsn, owner, g.hecho_id) == antes


# ------------------------------------------------------------------ A9: OP-03 y OP-03P

def _prevision_de_cuota(gdsn, unidad, owner):
    from app.core.modelos_prevision import DatosPrevisionManual
    from app.services.previsiones_service import PrevisionesService

    pid = uuid.uuid4()
    PrevisionesService(unidad).crear_manual(_ctx(owner), DatosPrevisionManual(
        prevision_id=pid, concepto="Cuota 1 hipoteca", tipo_hecho_codigo="GASTO", fecha_esperada_desde=fz.FECHA,
        fecha_esperada_hasta=fz.FECHA, flujo_tesoreria_esperado="SALIDA", moneda="EUR", presupuestable=True,
        categoria_id=None, tercero_id=None, cuenta_salida_esperada_id=None, cuenta_entrada_esperada_id=None,
        importe_esperado=fz.CUOTA))
    return pid


def _anular_op03(servicio, owner, f, version=None):
    return servicio.anular_hecho(_ctx(owner), hecho_id=f.hecho_id,
                                 row_version_esperada=f.version if version is None else version,
                                 motivo_anulacion="F04-R-HIP A9")


def _op03p(unidad):
    return AnulacionTesoreriaService(unidad, adquirir_impacto=adquirir_impacto_ancla,
                                     aplicar_impacto=aplicar_impacto_ancla)


def _anular_op03p(unidad, gdsn, owner, f, version=None):
    mov = fz.foto(gdsn, owner, f.hecho_id)["movimientos"]
    return _op03p(unidad).anular_registro(_ctx(owner), DatosAnulacionRegistro(
        hecho_id=f.hecho_id, row_version_esperada=f.version if version is None else version,
        movimientos_row_version_esperadas={m[0]: m[2] for m in mov}, motivo="F04-R-HIP A9",
        movimiento_en_banco=False))


@pytest.mark.parametrize("tipo", ["cuota", "hd"])
def test_o_a9_03_op03_rechaza_sin_conciliacion(servicio, unidad, contexto, owner, gdsn, tipo) -> None:
    pid = _prevision_de_cuota(gdsn, unidad, owner)
    entidad, cuota = fz.financiacion(gdsn, owner, prevision_id=pid)
    hacer = fz.cuota_pagada if tipo == "cuota" else fz.desembolso_hd
    f = hacer(gdsn, unidad, contexto, owner, entidad)
    antes = fz.foto(gdsn, owner, f.hecho_id, pid, cuota)
    e = _rechazo(lambda: _anular_op03(servicio, owner, f), A9)
    assert e.contexto_extra == {"motivo": "HECHO_DE_FINANCIACION",
                                "detalle": "CUOTA" if tipo == "cuota" else "DESEMBOLSO_HD"}
    assert fz.foto(gdsn, owner, f.hecho_id, pid, cuota) == antes


@pytest.mark.parametrize("tipo", ["cuota", "hd"])
def test_o_a9_03p_op03p_rechaza_con_conciliacion(unidad, contexto, owner, gdsn, cuenta, tipo) -> None:
    """Cuota: discrimina por prosperidad (W1-W5 retirarian la tesoreria y
    anularian). Hd: por codigo frente a TIPO_NO_SOPORTADO (D-04)."""
    pid = _prevision_de_cuota(gdsn, unidad, owner)
    entidad, cuota = fz.financiacion(gdsn, owner, prevision_id=pid)
    hacer = fz.cuota_pagada if tipo == "cuota" else fz.desembolso_hd
    f = hacer(gdsn, unidad, contexto, owner, entidad, cuenta_id=cuenta)
    antes = fz.foto(gdsn, owner, f.hecho_id, pid, cuota)
    assert antes["conciliaciones"] and antes["movimientos"]
    e = _rechazo(lambda: _anular_op03p(unidad, gdsn, owner, f), A9)
    assert e.contexto_extra["detalle"] == ("CUOTA" if tipo == "cuota" else "DESEMBOLSO_HD")
    assert fz.foto(gdsn, owner, f.hecho_id, pid, cuota) == antes


def test_o_prec_03p_la_guarda_precede_a_version_desfasada(unidad, contexto, owner, gdsn, cuenta) -> None:
    """D-07 (MF04-14): con row_version desfasada responde A9, no VERSION_DESFASADA
    (que OP-03P comprueba al final de _elegibilidad, antes de W1)."""
    f = _forma("cuota", gdsn, unidad, contexto, owner, cuenta)
    antes = fz.foto(gdsn, owner, f.hecho_id)
    _rechazo(lambda: _anular_op03p(unidad, gdsn, owner, f, version=f.version - 1), A9)
    assert fz.foto(gdsn, owner, f.hecho_id) == antes


def test_o_prec_03p_control_hecho_ordinario_da_version_desfasada(unidad, contexto, owner, gdsn, cuenta) -> None:
    g = fz.gasto_ordinario(gdsn, unidad, contexto, owner, cuenta_id=cuenta)
    _rechazo(lambda: _anular_op03p(unidad, gdsn, owner, g, version=g.version - 1), CodigoError.VERSION_DESFASADA)


@pytest.mark.parametrize("nivel_hecho", [False, True], ids=["ordinario", "financiacion_nivel_hecho"])
def test_o_a9_nh_op03_y_op03p_anulan_como_hoy(servicio, unidad, contexto, owner, gdsn, cuenta, nivel_hecho) -> None:
    """No ampliacion (MF04-15): hecho ordinario y con vinculo FINANCIACION solo de nivel hecho."""
    entidad = fz.financiacion(gdsn, owner)[0] if nivel_hecho else None
    g = fz.gasto_ordinario(gdsn, unidad, contexto, owner, entidad_nivel_hecho=entidad)
    assert _anular_op03(servicio, owner, g).estado == "ANULADO"
    g2 = fz.gasto_ordinario(gdsn, unidad, contexto, owner, cuenta_id=cuenta, entidad_nivel_hecho=entidad)
    _anular_op03p(unidad, gdsn, owner, g2)
    assert fz.foto(gdsn, owner, g2.hecho_id)["hecho"][0][0] == "ANULADO"


def test_d04_no_regresion_orden_de_errores_op03p(unidad, contexto, owner, gdsn, cuenta) -> None:
    """D-04: para hechos que no son de financiacion el orden de errores no
    cambia: un hecho de tipo no anulable por OP-03P sigue dando el rechazo de
    tipo (FUERA_DE_ALCANCE_V1 / TIPO_NO_SOPORTADO), y con version desfasada
    tambien (el tipo va antes)."""
    from app.core.modelos import DatosCreacionHecho
    from app.services.efectos_service import EfectosService
    from app.services.hechos_service import HechosService
    from app.services.previsiones_service import impacto_correccion_ancla

    hecho_id = uuid.uuid4()
    r = HechosService(unidad, impacto_ancla=impacto_correccion_ancla).crear_hecho(contexto, DatosCreacionHecho(
        hecho_id=hecho_id, fecha_hecho=fz.FECHA, moneda="EUR", presupuestable=False,
        estado_localizacion="DESCONOCIDA", tipo_hecho_codigo="GENERACION_DERECHO_OBLIGACION",
        concepto="posicion sin financiacion", importe_total=fz.P))
    r = EfectosService(unidad).registrar_efectos(contexto, hecho_id=hecho_id, row_version_esperada=r.row_version,
                                                 efectos=[DatosEfecto(efecto_id=uuid.uuid4(), tipo_efecto="DEUDA",
                                                                      importe_delta=fz.P,
                                                                      estado_atribucion="NO_DISPONIBLE")])
    fz._tesoreria(unidad, contexto, hecho_id, cuenta, fz.P, r.row_version)
    f = fz.Forma(hecho_id, None, None, None, None, None, fz.version(gdsn, owner, hecho_id))
    for version in (f.version, f.version - 1):
        e = _rechazo(lambda: _anular_op03p(unidad, gdsn, owner, f, version=version),
                     CodigoError.CORRECCION_AGREGADA_REQUERIDA)
        assert e.contexto_extra == {"motivo": "FUERA_DE_ALCANCE_V1", "detalle": "TIPO_NO_SOPORTADO"}


# ------------------------------------------------------------------ V3-FIX (A5)

def _hecho_v3(gdsn, unidad, contexto, owner):
    """Financiacion HIPOTECA sin cuadro y apertura indeterminada + hecho DEUDA
    importado (mapeos_importacion) vinculado a nivel efecto (D8-I)."""
    from app.core.modelos import DatosCreacionHecho
    from app.services.efectos_service import EfectosService
    from app.services.hechos_service import HechosService
    from app.services.previsiones_service import impacto_correccion_ancla

    entidad, _ = fz.financiacion(gdsn, owner, v3=True)
    hecho_id, deuda = uuid.uuid4(), uuid.uuid4()
    r = HechosService(unidad, impacto_ancla=impacto_correccion_ancla).crear_hecho(contexto, DatosCreacionHecho(
        hecho_id=hecho_id, fecha_hecho=fz.FECHA, moneda="EUR", presupuestable=False,
        estado_localizacion="DESCONOCIDA", tipo_hecho_codigo="GENERACION_DERECHO_OBLIGACION",
        concepto="V3 hipoteca", importe_total=fz.P))
    EfectosService(unidad).registrar_efectos(contexto, hecho_id=hecho_id, row_version_esperada=r.row_version,
                                             efectos=[DatosEfecto(efecto_id=deuda, tipo_efecto="DEUDA",
                                                                  importe_delta=fz.P,
                                                                  estado_atribucion="NO_DISPONIBLE")])
    vinculo = fz.vincular_nivel_efecto(gdsn, owner, hecho_id, deuda, entidad)
    fz.marcar_v3(gdsn, owner, hecho_id)
    return fz.Forma(hecho_id, deuda, None, vinculo, entidad, None, fz.version(gdsn, owner, hecho_id))


def test_v3_fix_las_guardas_tratan_el_caso_v3_como_financiacion(
    servicio, servicio_correcciones, unidad, contexto, owner, gdsn
) -> None:
    f = _hecho_v3(gdsn, unidad, contexto, owner)
    antes = fz.foto(gdsn, owner, f.hecho_id)
    _rechazo(lambda: servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=f.hecho_id, row_version_esperada=f.version, motivo="V3-FIX",
        entidades_a_eliminar=(f.vinculo_id,))), CodigoError.OWNERSHIP_F07)
    _rechazo(lambda: _anular_op03(servicio, owner, f), A9)
    assert fz.foto(gdsn, owner, f.hecho_id) == antes
