# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_138_f04_r1_discriminantes.py
# Ruta: tests/backend/test_138_f04_r1_discriminantes.py
# Descripcion: F04-R1 (F04-D057 criterio de recierre 1; F04-D058 G-R1-A/B/C;
#   mandato F04-R1 IMPL v1.0 §F1.2). Pruebas DISCRIMINANTES que fallan sobre
#   la base (93ab00c y 5536bb3: logs en evidencia_f04r1\f1\) y pasan con la
#   correccion, y regresiones que pasan antes y despues.
#
#   Discriminantes (rojas sobre la base):
#     (a) anular un original con una devolucion ACTIVA (DEVOLUCION_DE);
#     (b) lo mismo con un REEMBOLSO_DE activo (OP-14);
#     (c) lo mismo con un CORRIGE_A activo (OP-18);
#     (c-res) tipo reservado REPERCUSION_DE (sin escritor; fixture) activo;
#     (f) OP-14 hacia un causal ANULADO;
#     (g) OP-18 hacia un ajustado ANULADO;
#     (h) doble asignacion de 76,10 sobre un hecho de 76,10;
#     (j1) corregir_vinculo al alza por encima del tope;
#     (k) importe_total NULL y segundo vinculo (NO_DETERMINABLE);
#     (l) multidivisa y segundo vinculo (NO_DETERMINABLE).
#   Regresion (verdes antes y despues):
#     (d) anular cuando la unica devolucion esta ANULADA;
#     (e) anular la propia devolucion;
#     (i) asignaciones que suman exactamente el total.
#   Los codigos nuevos se comparan por su VALOR (str): sobre la base el
#   miembro del catalogo aun no existe y el test debe fallar por la
#   conducta, no por un AttributeError.
# Version: 0.1.0 (F04-R1 IMPL F1)
# Version: 0.2.0 (F04-R1 IMPL F2, G-R1-A/B): OP-03 con dependencia y row_version
#   desfasada (gana la dependencia); el detalle solo lista dependientes del
#   mismo owner (una relacion de origen ajeno, solo posible con superusuario,
#   ni se lista ni bloquea: la RLS de hecho_relaciones la oculta). Las filas de
#   tipos reservados que crean los fixtures se BORRAN al terminar cada test:
#   test_123 (N12) exige que la suite no deje ninguna.
# Version: 0.3.0 (F04-R1 IMPL F3, G-R1-C): (j2) correccion a la baja con exceso
#   previo; exceso que se mantiene, que disminuye y que se agrava; OP-17 sobre
#   un exceso previo; traslado con el destino en exceso y el origen que mejora
#   (rechazo, sin compensar); corregir y retirar el unico vinculo
#   NO_DETERMINABLE sin fabricar capacidad; vinculo en la moneda del hecho
#   seguido de otro en una moneda distinta. El exceso previo se crea por la via
#   real que lo permite (OP-02 rebaja importe_total; R1-OBS-01).
# Version: 0.4.0 (F04-R1 IMPL F5, impacto en F05-06 M5): OP-22 con una
#   asignacion mayor que el total se rechaza y no deja nada (ni el hecho); «Ya
#   lo registre» (OP-17) sobre un hecho que OP-22 ya asigno entero se rechaza.
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
from app.core.modelos_posicion import DatosReembolso
from app.core.modelos_prevision import DatosPrevisionManual, DatosVinculo
from app.services.hechos_service import HechosService
from app.services.previsiones_service import PrevisionesService
from conftest import leer_fila
from test_109_op12_posiciones import COBRO, alta, delta, tesoreria_nueva
from test_117_op13_devolucion import crear_origen, datos_devolucion
from test_118_op18_suplemento import datos_suplemento

D = decimal.Decimal
F = dt.date.fromisoformat
PORCION = "PORCION_DE_REALIDAD_EXCEDIDA"


# ==================================================================
# Utilidades compartidas por la bateria F04-R1 (test_128/129/139 las importan)
# ==================================================================
def hecho_simple(
    servicio: HechosService,
    contexto: ContextoOperacion,
    *,
    importe: decimal.Decimal | None = D("76.1000"),
    moneda: str = "EUR",
    fecha: dt.date = F("2027-05-01"),
) -> uuid.UUID:
    """Hecho ACTIVO sin efectos, tesoreria ni posicion: nada mas lo bloquea."""
    hecho_id = uuid.uuid4()
    servicio.crear_hecho(
        contexto,
        DatosCreacionHecho(
            hecho_id=hecho_id,
            fecha_hecho=fecha,
            moneda=moneda,
            presupuestable=True,
            estado_localizacion="NO_APLICA",
            tipo_hecho_codigo="GASTO",
            importe_total=importe,
        ),
    )
    return hecho_id


def version_hecho(admin: psycopg.Connection, owner: uuid.UUID, hecho_id: uuid.UUID) -> int:
    return leer_fila(admin, owner, "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s", (hecho_id,))[0]


def estado_hecho(admin: psycopg.Connection, owner: uuid.UUID, hecho_id: uuid.UUID) -> str:
    return leer_fila(admin, owner, "SELECT estado FROM gapto.hechos_financieros WHERE id = %s", (hecho_id,))[0]


def anular(servicio: HechosService, contexto, admin, hecho_id: uuid.UUID):
    return servicio.anular_hecho(
        contexto, hecho_id=hecho_id, row_version_esperada=version_hecho(admin, contexto.owner_user_id, hecho_id),
        motivo_anulacion="capturado por error")


def prevision_manual(servicio_previsiones: PrevisionesService, contexto, *, moneda: str = "EUR") -> uuid.UUID:
    prevision_id = uuid.uuid4()
    servicio_previsiones.crear_manual(contexto, DatosPrevisionManual(
        prevision_id=prevision_id, concepto="Prevision F04-R1", tipo_hecho_codigo="GASTO",
        fecha_esperada_desde=F("2027-05-01"), fecha_esperada_hasta=F("2027-05-31"),
        flujo_tesoreria_esperado="SALIDA", moneda=moneda, presupuestable=True, importe_esperado=D("76.1000")))
    return prevision_id


def vincular(servicio_previsiones: PrevisionesService, contexto, prevision_id, hecho_id, importe: str,
             *, equivalencia: bool = False, vinculo_id: uuid.UUID | None = None):
    estado = servicio_previsiones.estado_de(contexto, prevision_id)
    return servicio_previsiones.vincular_realidad(
        contexto, prevision_id=prevision_id, row_version_esperada=estado.row_version,
        datos=DatosVinculo(vinculo_id=vinculo_id or uuid.uuid4(), hecho_id=hecho_id, importe_asignado=D(importe),
                           marcar_realizada=False, equivalencia_declarada=equivalencia))


def vinculos_de(admin, owner, hecho_id) -> list[tuple]:
    with admin.cursor() as cur:
        cur.execute("RESET ROLE")
        cur.execute("SELECT prevision_id, importe_asignado FROM gapto.prevision_hechos WHERE hecho_id = %s "
                    "ORDER BY prevision_id", (hecho_id,))
        return cur.fetchall()


_RESERVADAS: list[uuid.UUID] = []


@pytest.fixture(autouse=True)
def _limpiar_reservadas(admin):
    """N12 (test_123): ninguna fila de tipo reservado sobrevive al test que la creo."""
    yield
    if _RESERVADAS:
        with admin.cursor() as cur:
            cur.execute("RESET ROLE")
            cur.execute("DELETE FROM gapto.hecho_relaciones WHERE id = ANY(%s)", (list(_RESERVADAS),))
        _RESERVADAS.clear()


def relacion_reservada(admin: psycopg.Connection, owner: uuid.UUID, origen: uuid.UUID, destino: uuid.UUID,
                       tipo: str = "REPERCUSION_DE") -> uuid.UUID:
    """Relacion de un tipo SIN escritor (REPERCUSION_DE, REVERSA_A, PARTE_DE): fixture gapto_owner."""
    relacion_id = uuid.uuid4()
    _RESERVADAS.append(relacion_id)
    with admin.cursor() as cur:
        cur.execute("RESET ROLE")
        cur.execute("SET ROLE gapto_owner")
        try:
            cur.execute("SELECT set_config('gapto.owner_user_id', %s, false)", (str(owner),))
            cur.execute("INSERT INTO gapto.hecho_relaciones (id, hecho_origen_id, hecho_destino_id, tipo_relacion) "
                        "VALUES (%s, %s, %s, %s)", (relacion_id, origen, destino, tipo))
        finally:
            cur.execute("RESET ROLE")
    admin.commit()
    return relacion_id


def _rechazo_dependencias(excinfo) -> None:
    assert excinfo.value.codigo is CodigoError.HECHO_CON_REALIDAD_ASOCIADA
    assert excinfo.value.contexto_extra.get("motivo") == "DEPENDENCIAS_ACTIVAS"


def _rechazo_porcion(excinfo, motivo: str) -> None:
    assert excinfo.value.codigo.value == PORCION, excinfo.value.codigo
    assert excinfo.value.contexto_extra.get("motivo") == motivo


# ==================================================================
# G-R1-A · OP-03 con dependencias activas
# ==================================================================
def test_a_anular_original_con_devolucion_activa(servicio, servicio_efectos, servicio_devoluciones, contexto, admin):
    original = crear_origen(servicio, servicio_efectos, contexto)
    servicio_devoluciones.devolver(contexto, datos_devolucion(original))
    with pytest.raises(ErrorMotor) as excinfo:
        anular(servicio, contexto, admin, original)
    _rechazo_dependencias(excinfo)
    assert estado_hecho(admin, contexto.owner_user_id, original) == "ACTIVO"


def test_b_anular_causal_con_reembolso_activo(servicio, servicio_posiciones, contexto, admin, contraparte, cuenta):
    causal = hecho_simple(servicio, contexto)
    datos_alta = alta(contraparte)
    creada = servicio_posiciones.crear_posicion(contexto, datos_alta)
    servicio_posiciones.reembolsar(
        contexto, entidad_id=datos_alta.entidad_id, entidad_row_version_esperada=creada.entidad_row_version,
        datos=DatosReembolso(delta=delta("40.0000", causa=COBRO), tesoreria=tesoreria_nueva(cuenta),
                             hecho_causal_id=causal, relacion_id=uuid.uuid4()))
    with pytest.raises(ErrorMotor) as excinfo:
        anular(servicio, contexto, admin, causal)
    _rechazo_dependencias(excinfo)
    assert estado_hecho(admin, contexto.owner_user_id, causal) == "ACTIVO"


def test_c_anular_ajustado_con_corrige_a_activo(servicio, servicio_suplementos, contexto, admin):
    ajustado = hecho_simple(servicio, contexto)
    servicio_suplementos.registrar(contexto, datos_suplemento(relacion_id=uuid.uuid4(), hecho_ajustado_id=ajustado))
    with pytest.raises(ErrorMotor) as excinfo:
        anular(servicio, contexto, admin, ajustado)
    _rechazo_dependencias(excinfo)


@pytest.mark.parametrize("tipo", ["REPERCUSION_DE", "REVERSA_A", "PARTE_DE"])
def test_c_res_tipo_reservado_activo_bloquea(servicio, contexto, admin, tipo):
    destino = hecho_simple(servicio, contexto)
    origen = hecho_simple(servicio, contexto)
    relacion_reservada(admin, contexto.owner_user_id, origen, destino, tipo)
    with pytest.raises(ErrorMotor) as excinfo:
        anular(servicio, contexto, admin, destino)
    _rechazo_dependencias(excinfo)


def test_d_anular_cuando_la_unica_devolucion_esta_anulada(servicio, servicio_efectos, servicio_devoluciones,
                                                          contexto, admin):
    original = crear_origen(servicio, servicio_efectos, contexto)
    datos = datos_devolucion(original)
    servicio_devoluciones.devolver(contexto, datos)
    anular(servicio, contexto, admin, datos.hecho_id)
    anular(servicio, contexto, admin, original)
    assert estado_hecho(admin, contexto.owner_user_id, original) == "ANULADO"


def test_e_anular_la_propia_devolucion(servicio, servicio_efectos, servicio_devoluciones, contexto, admin):
    """Ser ORIGEN de una relacion nunca bloquea."""
    original = crear_origen(servicio, servicio_efectos, contexto)
    datos = datos_devolucion(original)
    servicio_devoluciones.devolver(contexto, datos)
    anular(servicio, contexto, admin, datos.hecho_id)
    assert estado_hecho(admin, contexto.owner_user_id, datos.hecho_id) == "ANULADO"


# ==================================================================
# G-R1-B · escritores de relaciones hacia un hecho ANULADO
# ==================================================================
def test_f_op14_hacia_causal_anulado(servicio, servicio_posiciones, contexto, admin, contraparte, cuenta):
    causal = hecho_simple(servicio, contexto)
    anular(servicio, contexto, admin, causal)
    datos_alta = alta(contraparte)
    creada = servicio_posiciones.crear_posicion(contexto, datos_alta)
    relacion_id = uuid.uuid4()
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.reembolsar(
            contexto, entidad_id=datos_alta.entidad_id, entidad_row_version_esperada=creada.entidad_row_version,
            datos=DatosReembolso(delta=delta("40.0000", causa=COBRO), tesoreria=tesoreria_nueva(cuenta),
                                 hecho_causal_id=causal, relacion_id=relacion_id))
    assert excinfo.value.codigo is CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO
    assert leer_fila(admin, contexto.owner_user_id, "SELECT count(*) FROM gapto.hecho_relaciones WHERE id = %s",
                     (relacion_id,)) == (0,)


def test_g_op18_hacia_ajustado_anulado(servicio, servicio_suplementos, contexto, admin):
    ajustado = hecho_simple(servicio, contexto)
    anular(servicio, contexto, admin, ajustado)
    datos = datos_suplemento(relacion_id=uuid.uuid4(), hecho_ajustado_id=ajustado)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_suplementos.registrar(contexto, datos)
    assert excinfo.value.codigo is CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO
    assert leer_fila(admin, contexto.owner_user_id, "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s",
                     (datos.hecho_id,)) == (0,)


# ==================================================================
# G-R1-C · porcion acumulada entre previsiones
# ==================================================================
def test_h_doble_asignacion_de_la_misma_porcion(servicio, servicio_previsiones, contexto, admin):
    hecho = hecho_simple(servicio, contexto, importe=D("76.1000"))
    p1, p2 = prevision_manual(servicio_previsiones, contexto), prevision_manual(servicio_previsiones, contexto)
    vincular(servicio_previsiones, contexto, p1, hecho, "76.1000")
    with pytest.raises(ErrorMotor) as excinfo:
        vincular(servicio_previsiones, contexto, p2, hecho, "76.1000")
    _rechazo_porcion(excinfo, "EXCEDE")
    assert vinculos_de(admin, contexto.owner_user_id, hecho) == [(p1, D("76.1000"))]


def test_i_asignaciones_que_suman_exactamente_el_total(servicio, servicio_previsiones, contexto, admin):
    hecho = hecho_simple(servicio, contexto, importe=D("76.1000"))
    p1, p2 = prevision_manual(servicio_previsiones, contexto), prevision_manual(servicio_previsiones, contexto)
    vincular(servicio_previsiones, contexto, p1, hecho, "40.0000")
    vincular(servicio_previsiones, contexto, p2, hecho, "36.1000")
    assert sum(v[1] for v in vinculos_de(admin, contexto.owner_user_id, hecho)) == D("76.1000")


def test_j1_corregir_vinculo_al_alza_por_encima_del_tope(servicio, servicio_previsiones, contexto, admin):
    hecho = hecho_simple(servicio, contexto, importe=D("76.1000"))
    p1 = prevision_manual(servicio_previsiones, contexto)
    vinculo_id = uuid.uuid4()
    vincular(servicio_previsiones, contexto, p1, hecho, "50.0000", vinculo_id=vinculo_id)
    version = servicio_previsiones.estado_de(contexto, p1).row_version
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_previsiones.corregir_vinculo(contexto, vinculo_id=vinculo_id, versiones_esperadas={p1: version},
                                              nuevo_importe=D("80.0000"), motivo="al alza")
    _rechazo_porcion(excinfo, "EXCEDE")
    assert vinculos_de(admin, contexto.owner_user_id, hecho) == [(p1, D("50.0000"))]


def test_k_importe_total_null_y_segundo_vinculo(servicio, servicio_previsiones, contexto, admin):
    hecho = hecho_simple(servicio, contexto, importe=None)
    p1, p2 = prevision_manual(servicio_previsiones, contexto), prevision_manual(servicio_previsiones, contexto)
    vincular(servicio_previsiones, contexto, p1, hecho, "10.0000")
    with pytest.raises(ErrorMotor) as excinfo:
        vincular(servicio_previsiones, contexto, p2, hecho, "10.0000")
    _rechazo_porcion(excinfo, "NO_DETERMINABLE")
    assert excinfo.value.contexto_extra.get("tope") is None
    assert len(vinculos_de(admin, contexto.owner_user_id, hecho)) == 1


def test_l_multidivisa_y_segundo_vinculo(servicio, servicio_previsiones, contexto, admin):
    hecho = hecho_simple(servicio, contexto, importe=D("100.0000"), moneda="USD")
    p1, p2 = prevision_manual(servicio_previsiones, contexto), prevision_manual(servicio_previsiones, contexto)
    vincular(servicio_previsiones, contexto, p1, hecho, "10.0000", equivalencia=True)
    with pytest.raises(ErrorMotor) as excinfo:
        vincular(servicio_previsiones, contexto, p2, hecho, "10.0000", equivalencia=True)
    _rechazo_porcion(excinfo, "NO_DETERMINABLE")
    assert len(vinculos_de(admin, contexto.owner_user_id, hecho)) == 1


# ==================================================================
# F2 · orden de validacion y owner del detalle
# ==================================================================
def test_op03_dependencia_gana_a_la_version_desfasada(servicio, servicio_efectos, servicio_devoluciones,
                                                     contexto, admin):
    original = crear_origen(servicio, servicio_efectos, contexto)
    devolucion = datos_devolucion(original)
    servicio_devoluciones.devolver(contexto, devolucion)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.anular_hecho(contexto, hecho_id=original,
                              row_version_esperada=version_hecho(admin, contexto.owner_user_id, original) + 7,
                              motivo_anulacion="version vieja")
    _rechazo_dependencias(excinfo)
    assert excinfo.value.contexto_extra["dependientes"] == [
        {"hecho_id": str(devolucion.hecho_id), "tipo_relacion": "DEVOLUCION_DE"}]


def test_op03_detalle_solo_lista_dependientes_del_mismo_owner(servicio, contexto, admin, otro_owner):
    destino = hecho_simple(servicio, contexto)
    propio = hecho_simple(servicio, contexto)
    relacion_reservada(admin, contexto.owner_user_id, propio, destino, "PARTE_DE")
    ajeno = hecho_simple(servicio, ContextoOperacion.de_usuario(otro_owner))
    with admin.cursor() as cur:  # solo posible con superusuario: el WITH CHECK exige el mismo owner
        cur.execute("RESET ROLE")
        ajena = uuid.uuid4()
        _RESERVADAS.append(ajena)
        cur.execute("INSERT INTO gapto.hecho_relaciones (id, hecho_origen_id, hecho_destino_id, tipo_relacion) "
                    "VALUES (%s, %s, %s, 'REPERCUSION_DE')", (ajena, ajeno, destino))
    with pytest.raises(ErrorMotor) as excinfo:
        anular(servicio, contexto, admin, destino)
    _rechazo_dependencias(excinfo)
    assert excinfo.value.contexto_extra["dependientes"] == [{"hecho_id": str(propio), "tipo_relacion": "PARTE_DE"}]


# ==================================================================
# F3 · G-R1-C: estado posterior, exceso previo, traslado y NO_DETERMINABLE
# ==================================================================
def _rebajar_importe(servicio, contexto, admin, hecho_id, importe: str) -> None:
    """R1-OBS-01: OP-02 no se bloquea por los vinculos y puede dejar exceso."""
    from app.core.modelos import CamposCorreccion
    servicio.corregir_hecho(contexto, hecho_id=hecho_id,
                            row_version_esperada=version_hecho(admin, contexto.owner_user_id, hecho_id),
                            campos=CamposCorreccion(importe_total=D(importe)), motivo="importe corregido")


def _corregir(servicio_previsiones, contexto, vinculo_id, previsiones, **cambios):
    versiones = {p: servicio_previsiones.estado_de(contexto, p).row_version for p in previsiones}
    return servicio_previsiones.corregir_vinculo(contexto, vinculo_id=vinculo_id, versiones_esperadas=versiones,
                                                 motivo="F04-R1 F3", **cambios)


@pytest.fixture()
def exceso_previo(servicio, servicio_previsiones, contexto, admin):
    """Hecho 76,10 con un vinculo de 70 en p1; OP-02 lo rebaja a 50: exceso previo 70 > 50."""
    hecho = hecho_simple(servicio, contexto, importe=D("76.1000"))
    p1, p2 = prevision_manual(servicio_previsiones, contexto), prevision_manual(servicio_previsiones, contexto)
    v1 = uuid.uuid4()
    vincular(servicio_previsiones, contexto, p1, hecho, "70.0000", vinculo_id=v1)
    _rebajar_importe(servicio, contexto, admin, hecho, "50.0000")
    return {"hecho": hecho, "p1": p1, "p2": p2, "v1": v1}


def test_j2_correccion_a_la_baja_con_exceso_previo(servicio_previsiones, contexto, admin, exceso_previo):
    e = exceso_previo
    _corregir(servicio_previsiones, contexto, e["v1"], [e["p1"]], nuevo_importe=D("60.0000"))
    assert vinculos_de(admin, contexto.owner_user_id, e["hecho"]) == [(e["p1"], D("60.0000"))]


def test_exceso_que_se_mantiene_al_mover_de_prevision(servicio_previsiones, contexto, admin, exceso_previo):
    e = exceso_previo
    _corregir(servicio_previsiones, contexto, e["v1"], [e["p1"], e["p2"]], nueva_prevision_id=e["p2"])
    assert vinculos_de(admin, contexto.owner_user_id, e["hecho"]) == [(e["p2"], D("70.0000"))]


def test_exceso_que_se_agrava(servicio_previsiones, contexto, admin, exceso_previo):
    e = exceso_previo
    with pytest.raises(ErrorMotor) as excinfo:
        _corregir(servicio_previsiones, contexto, e["v1"], [e["p1"]], nuevo_importe=D("75.0000"))
    _rechazo_porcion(excinfo, "EXCEDE")
    extra = excinfo.value.contexto_extra
    assert extra["tope"] == {"importe": "50.0000", "moneda": "EUR"}
    assert extra["asignado_previo"]["importe"] == "70.0000" and extra["solicitado"]["importe"] == "75.0000"
    assert vinculos_de(admin, contexto.owner_user_id, e["hecho"]) == [(e["p1"], D("70.0000"))]


def test_op17_sobre_un_exceso_previo(servicio_previsiones, contexto, admin, exceso_previo):
    e = exceso_previo
    with pytest.raises(ErrorMotor) as excinfo:
        vincular(servicio_previsiones, contexto, e["p2"], e["hecho"], "0.0100")
    _rechazo_porcion(excinfo, "EXCEDE")


def test_traslado_destino_en_exceso_y_origen_que_mejora(servicio, servicio_previsiones, contexto, admin):
    """El origen mejora (110 > 100 pasa a 90) pero el destino crearia exceso (40 -> 60 > 50): rechazo."""
    a = hecho_simple(servicio, contexto, importe=D("50.0000"))
    b = hecho_simple(servicio, contexto, importe=D("120.0000"))
    p1, p2, p3 = (prevision_manual(servicio_previsiones, contexto) for _ in range(3))
    vincular(servicio_previsiones, contexto, p1, a, "40.0000")
    vincular(servicio_previsiones, contexto, p2, b, "90.0000")
    vx = uuid.uuid4()
    vincular(servicio_previsiones, contexto, p3, b, "20.0000", vinculo_id=vx)
    _rebajar_importe(servicio, contexto, admin, b, "100.0000")  # b: 110 > 100
    with pytest.raises(ErrorMotor) as excinfo:
        _corregir(servicio_previsiones, contexto, vx, [p3], nuevo_hecho_id=a)
    _rechazo_porcion(excinfo, "EXCEDE")
    assert len(vinculos_de(admin, contexto.owner_user_id, b)) == 2
    assert len(vinculos_de(admin, contexto.owner_user_id, a)) == 1


def test_corregir_y_retirar_el_unico_vinculo_no_determinable(servicio, servicio_previsiones, contexto, admin):
    hecho = hecho_simple(servicio, contexto, importe=None)
    p1, p2 = prevision_manual(servicio_previsiones, contexto), prevision_manual(servicio_previsiones, contexto)
    v1 = uuid.uuid4()
    vincular(servicio_previsiones, contexto, p1, hecho, "10.0000", vinculo_id=v1)
    _corregir(servicio_previsiones, contexto, v1, [p1], nuevo_importe=D("999.0000"))  # corregir el unico: admitido
    _corregir(servicio_previsiones, contexto, v1, [p1, p2], nueva_prevision_id=p2)   # moverlo: admitido
    with pytest.raises(ErrorMotor) as excinfo:  # no se ha fabricado capacidad: un segundo vinculo sigue vetado
        vincular(servicio_previsiones, contexto, p1, hecho, "1.0000")
    _rechazo_porcion(excinfo, "NO_DETERMINABLE")
    servicio_previsiones.retirar_vinculo(contexto, vinculo_id=v1,
                                         prevision_row_version_esperada=servicio_previsiones.estado_de(contexto, p2).row_version)
    assert vinculos_de(admin, contexto.owner_user_id, hecho) == []
    vincular(servicio_previsiones, contexto, p1, hecho, "1.0000")  # vuelve a haber sitio para UN vinculo
    assert len(vinculos_de(admin, contexto.owner_user_id, hecho)) == 1


def test_vinculo_en_la_moneda_del_hecho_y_otro_en_moneda_distinta(servicio, servicio_previsiones, contexto, admin):
    hecho = hecho_simple(servicio, contexto, importe=D("100.0000"), moneda="USD")
    p_usd = prevision_manual(servicio_previsiones, contexto, moneda="USD")
    p_eur = prevision_manual(servicio_previsiones, contexto, moneda="EUR")
    vincular(servicio_previsiones, contexto, p_usd, hecho, "50.0000")
    with pytest.raises(ErrorMotor) as excinfo:
        vincular(servicio_previsiones, contexto, p_eur, hecho, "10.0000", equivalencia=True)
    _rechazo_porcion(excinfo, "NO_DETERMINABLE")
    assert excinfo.value.contexto_extra["tope"] == {"importe": "100.0000", "moneda": "USD"}


# ==================================================================
# Impacto en F05-06 M5 (confirmacion de previsiones: OP-22 + OP-17)
# ==================================================================
from app.core.modelos_compuesto import DatosHechoCompuesto, DatosPrevisionCompuesta  # noqa: E402
from f08_motor import efecto  # noqa: E402
from test_140_f04_r3_op22 import hecho as hecho_op22, op22  # noqa: E402,F401


def _op22_con_prevision(op22, servicio_previsiones, contexto, prevision_id, asignado: str):
    datos = hecho_op22()
    op22.registrar_hecho_compuesto(contexto, DatosHechoCompuesto(
        hecho=datos, efectos=[efecto("GASTO", D("100.0000"))],
        prevision=DatosPrevisionCompuesta(
            prevision_id=prevision_id,
            prevision_row_version_esperada=servicio_previsiones.estado_de(contexto, prevision_id).row_version,
            vinculo_id=uuid.uuid4(), importe_asignado=D(asignado), marcar_realizada=False)))
    return datos.hecho_id


def test_m5_op22_con_asignacion_mayor_que_el_total_no_deja_nada(op22, servicio_previsiones, contexto, admin):
    prevision = prevision_manual(servicio_previsiones, contexto)
    datos = hecho_op22()
    with pytest.raises(ErrorMotor) as excinfo:
        op22.registrar_hecho_compuesto(contexto, DatosHechoCompuesto(
            hecho=datos, efectos=[efecto("GASTO", D("100.0000"))],
            prevision=DatosPrevisionCompuesta(
                prevision_id=prevision,
                prevision_row_version_esperada=servicio_previsiones.estado_de(contexto, prevision).row_version,
                vinculo_id=uuid.uuid4(), importe_asignado=D("100.0001"), marcar_realizada=True)))
    _rechazo_porcion(excinfo, "EXCEDE")
    assert leer_fila(admin, contexto.owner_user_id, "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s",
                     (datos.hecho_id,)) == (0,)
    assert servicio_previsiones.estado_de(contexto, prevision).estado == "ABIERTA"


def test_m5_ya_lo_registre_sobre_un_hecho_ya_asignado_entero(op22, servicio_previsiones, contexto, admin):
    p1, p2 = prevision_manual(servicio_previsiones, contexto), prevision_manual(servicio_previsiones, contexto)
    hecho = _op22_con_prevision(op22, servicio_previsiones, contexto, p1, "100.0000")
    with pytest.raises(ErrorMotor) as excinfo:
        vincular(servicio_previsiones, contexto, p2, hecho, "0.0001")
    _rechazo_porcion(excinfo, "EXCEDE")
    assert vinculos_de(admin, contexto.owner_user_id, hecho) == [(p1, D("100.0000"))]
