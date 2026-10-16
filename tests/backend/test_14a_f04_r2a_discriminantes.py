# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_14a_f04_r2a_discriminantes.py
# Ruta: tests/backend/test_14a_f04_r2a_discriminantes.py
# Descripcion: F04-R2 R2-A (F04-D060; contrato F04-R2 v0.6 §7.1-§7.4;
#   mandato F04-R2A v1.0 §2). Discriminantes que FALLAN sobre bc6ddfa y pasan
#   con R2-A, todos con el rol real gapto_runtime (la UnidadDeTrabajo hace
#   SET LOCAL ROLE gapto_runtime y la RLS esta activa: V06-01).
#     D-A1 · pertenencia de OP-21 con ids EXISTENTES del mismo owner de otro
#       hecho H': actualizar y eliminar un efecto de H' y retirar una
#       conciliacion de H' (tambien una con aportaciones) -> rechazo y H'
#       intacto. OP-21 no tiene via que retire aportaciones
#       (`DatosCorreccion` no la ofrece): no se crea.
#     D-A2 · autoridad sobre relaciones (§7.2.1): origen -> se admite
#       (test_119 sin cambios); destino con origen ACTIVO ->
#       DEPENDENCIAS_ACTIVAS; destino con origen ANULADO -> RELACION_ENTRANTE;
#       hecho ajeno, id de otro owner e id inexistente -> AGREGADO_NO_ENCONTRADO
#       con el mismo mensaje y sin contexto (sin filtracion).
#     D-A3 · retirar_vinculo con dos previsiones de la MISMA row_version, en
#       llamada directa y tras un reintento por ConjuntoCambiado.
#   `_retirar` adapta la llamada a la firma de la base (sin
#   prevision_id_esperada) SOLO para poder ejecutar la discriminacion sobre
#   bc6ddfa por la conducta y no por un TypeError.
# Version: 0.1.0 (F04-R2 R2-A)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import inspect
import uuid

import pytest

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos_tesoreria import DatosConciliacion, DatosMovimiento
from app.repositories import previsiones_repository as repo_prev
from app.services.correcciones_service import DatosCorreccion
from conftest import leer_fila
from test_106_op06_op07_aportaciones import aportacion
from test_117_op13_devolucion import crear_origen, datos_devolucion
from test_119_op21_correccion import crear_hecho_con_efectos
from test_138_f04_r1_discriminantes import anular, hecho_simple, prevision_manual, version_hecho, vincular

D = decimal.Decimal
F = dt.date.fromisoformat


def corregir(servicio_correcciones, contexto, admin, raiz, **filas):
    return servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=raiz, row_version_esperada=version_hecho(admin, contexto.owner_user_id, raiz),
        motivo="F04-R2 R2-A", **filas))


def foto(admin, owner, hecho_id) -> dict:
    """Estado completo de H' que OP-21 sobre H no debe tocar."""
    def todas(sql):
        with admin.cursor() as cur:
            cur.execute("RESET ROLE")
            cur.execute(sql, (hecho_id,))
            return sorted(tuple(str(c) for c in f) for f in cur.fetchall())
    return {
        "hecho": todas("SELECT row_version, estado FROM gapto.hechos_financieros WHERE id = %s"),
        "efectos": todas("SELECT id, tipo_efecto, importe_delta, descripcion, estado_atribucion "
                         "FROM gapto.hecho_efectos WHERE hecho_id = %s"),
        "conciliaciones": todas("SELECT id, movimiento_tesoreria_id, importe_asignado "
                                "FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s"),
        "aportaciones": todas("SELECT id, importe, hecho_movimiento_tesoreria_id "
                              "FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s"),
        "relaciones": _relaciones(admin, hecho_id),
    }


def _relaciones(admin, hecho_id):
    with admin.cursor() as cur:
        cur.execute("RESET ROLE")
        cur.execute("SELECT id, hecho_origen_id, hecho_destino_id, tipo_relacion FROM gapto.hecho_relaciones "
                    "WHERE hecho_destino_id = %s OR hecho_origen_id = %s", (hecho_id, hecho_id))
        return sorted(tuple(str(c) for c in f) for f in cur.fetchall())


def existe_relacion(admin, relacion_id) -> bool:
    with admin.cursor() as cur:
        cur.execute("RESET ROLE")
        cur.execute("SELECT count(*) FROM gapto.hecho_relaciones WHERE id = %s", (relacion_id,))
        return cur.fetchone()[0] == 1


def conciliar(servicio_tesoreria, contexto, admin, hecho_id, cuenta, importe="-7.0000"):
    mov = servicio_tesoreria.registrar_movimiento(contexto, DatosMovimiento(
        movimiento_id=uuid.uuid4(), cuenta_id=cuenta, fecha_movimiento=F("2027-07-02"),
        importe=D(importe), clase_movimiento="OPERACION"))
    conciliacion = DatosConciliacion(uuid.uuid4(), hecho_id, mov.movimiento_id, D(importe))
    servicio_tesoreria.conciliar(contexto, conciliacion,
                                 hecho_row_version_esperada=version_hecho(admin, contexto.owner_user_id, hecho_id),
                                 movimiento_row_version_esperada=mov.row_version)
    return conciliacion.conciliacion_id


# ==================================================================
# D-A1 · pertenencia de OP-21 (contrato §7.1-§7.3)
# ==================================================================
def test_d_a1_actualizar_un_efecto_de_otro_hecho_rechazado(servicio, servicio_efectos, servicio_correcciones,
                                                           contexto, admin):
    h, _ = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    h2, efectos_h2 = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    antes = foto(admin, contexto.owner_user_id, h2)
    version_h = version_hecho(admin, contexto.owner_user_id, h)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(servicio_correcciones, contexto, admin, h,
                 efectos_a_actualizar={efectos_h2[0]: {"descripcion": "escrito desde H"}})
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO
    assert excinfo.value.contexto_extra == {}
    assert foto(admin, contexto.owner_user_id, h2) == antes
    assert version_hecho(admin, contexto.owner_user_id, h) == version_h  # rollback total


def test_d_a1_eliminar_un_efecto_de_otro_hecho_rechazado(servicio, servicio_efectos, servicio_correcciones,
                                                         contexto, admin):
    h, _ = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    h2, efectos_h2 = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    antes = foto(admin, contexto.owner_user_id, h2)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(servicio_correcciones, contexto, admin, h, efectos_a_eliminar=(efectos_h2[1],))
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO
    assert foto(admin, contexto.owner_user_id, h2) == antes


def test_d_a1_retirar_una_conciliacion_de_otro_hecho_rechazado(servicio, servicio_efectos, servicio_tesoreria,
                                                               servicio_correcciones, contexto, admin, cuenta):
    h, _ = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    h2, _ = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    conciliacion_id = conciliar(servicio_tesoreria, contexto, admin, h2, cuenta)
    antes = foto(admin, contexto.owner_user_id, h2)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(servicio_correcciones, contexto, admin, h, conciliaciones_a_eliminar=(conciliacion_id,))
    assert excinfo.value.codigo is CodigoError.CONCILIACION_DE_OTRO_HECHO
    assert foto(admin, contexto.owner_user_id, h2) == antes


def test_d_a1_conciliacion_de_otro_hecho_con_aportaciones_no_se_revela(
        servicio, servicio_efectos, servicio_tesoreria, servicio_correcciones, contexto, admin, cuenta, actor_a):
    """El recuento de aportaciones tambien es del hecho raiz: la conciliacion de H' con aportaciones da el
    MISMO codigo que una sin ellas (sobre la base: OPERACION_NO_PERMITIDA_EN_ESTADO, que revela que existe)."""
    h, _ = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    h2, _ = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    conciliacion_id = conciliar(servicio_tesoreria, contexto, admin, h2, cuenta, "-100.0000")
    una = aportacion("10.0000", actor_id=actor_a)
    creada = servicio_tesoreria.registrar_aportaciones(
        contexto, hecho_id=h2, hecho_row_version_esperada=version_hecho(admin, contexto.owner_user_id, h2),
        aportaciones=[una])
    servicio_tesoreria.vincular_aportacion(contexto, hecho_id=h2, hecho_row_version_esperada=creada.hecho_row_version,
                                           aportacion_id=una.aportacion_id, destino=conciliacion_id)
    antes = foto(admin, contexto.owner_user_id, h2)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(servicio_correcciones, contexto, admin, h, conciliaciones_a_eliminar=(conciliacion_id,))
    assert excinfo.value.codigo is CodigoError.CONCILIACION_DE_OTRO_HECHO
    assert foto(admin, contexto.owner_user_id, h2) == antes


def test_d_a1_conciliacion_inexistente_o_de_otro_owner_mismo_codigo(
        servicio, servicio_efectos, servicio_tesoreria, servicio_correcciones, contexto, admin, otro_owner,
        cuenta_ajena):
    h, _ = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    ajeno_ctx = ContextoOperacion.de_usuario(otro_owner)
    h_ajeno, _ = crear_hecho_con_efectos(servicio, servicio_efectos, ajeno_ctx)
    de_otro_owner = conciliar(servicio_tesoreria, ajeno_ctx, admin, h_ajeno, cuenta_ajena)
    errores = []
    for conciliacion_id in (uuid.uuid4(), de_otro_owner):
        with pytest.raises(ErrorMotor) as excinfo:
            corregir(servicio_correcciones, contexto, admin, h, conciliaciones_a_eliminar=(conciliacion_id,))
        errores.append((excinfo.value.codigo, excinfo.value.mensaje, excinfo.value.contexto_extra))
    assert errores[0] == errores[1]
    assert errores[0][0] is CodigoError.CONCILIACION_DE_OTRO_HECHO


def test_d_a1_efecto_inexistente_o_de_otro_owner_mismo_codigo(servicio, servicio_efectos, servicio_correcciones,
                                                              contexto, admin, otro_owner):
    h, efectos_h = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    _, efectos_ajenos = crear_hecho_con_efectos(servicio, servicio_efectos, ContextoOperacion.de_usuario(otro_owner))
    h2, efectos_h2 = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    errores = []
    for efecto_id in (uuid.uuid4(), efectos_ajenos[0], efectos_h2[0]):
        with pytest.raises(ErrorMotor) as excinfo:
            corregir(servicio_correcciones, contexto, admin, h,
                     efectos_a_actualizar={efecto_id: {"descripcion": "x"}})
        errores.append((excinfo.value.codigo, excinfo.value.mensaje, excinfo.value.contexto_extra))
    assert errores[0] == errores[1] == errores[2]
    assert errores[0][0] is CodigoError.AGREGADO_NO_ENCONTRADO


def test_d_a1_efecto_propio_sigue_corrigiendose(servicio, servicio_efectos, servicio_correcciones, contexto, admin):
    """Control positivo: la pertenencia no rompe la correccion legitima."""
    h, efectos_h = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    r = corregir(servicio_correcciones, contexto, admin, h,
                 efectos_a_actualizar={efectos_h[0]: {"descripcion": "corregido"}})
    assert r.efectos_actualizados == 1
    assert leer_fila(admin, contexto.owner_user_id, "SELECT descripcion FROM gapto.hecho_efectos WHERE id = %s",
                     (efectos_h[0],)) == ("corregido",)


# ==================================================================
# D-A2 · autoridad sobre relaciones (contrato §7.2.1)
# ==================================================================
def _devolucion(servicio, servicio_efectos, servicio_devoluciones, contexto):
    original = crear_origen(servicio, servicio_efectos, contexto)
    devolucion = datos_devolucion(original)
    servicio_devoluciones.devolver(contexto, devolucion)
    return original, devolucion


def test_d_a2_desde_el_origen_se_admite(servicio, servicio_efectos, servicio_devoluciones, servicio_correcciones,
                                        contexto, admin):
    original, devolucion = _devolucion(servicio, servicio_efectos, servicio_devoluciones, contexto)
    r = corregir(servicio_correcciones, contexto, admin, devolucion.hecho_id,
                 relaciones_a_eliminar=(devolucion.relacion_id,))
    assert r.relaciones_eliminadas == 1
    assert not existe_relacion(admin, devolucion.relacion_id)


def test_d_a2_desde_el_destino_con_origen_activo_rechazado(servicio, servicio_efectos, servicio_devoluciones,
                                                           servicio_correcciones, contexto, admin):
    original, devolucion = _devolucion(servicio, servicio_efectos, servicio_devoluciones, contexto)
    antes = foto(admin, contexto.owner_user_id, original)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(servicio_correcciones, contexto, admin, original, relaciones_a_eliminar=(devolucion.relacion_id,))
    assert excinfo.value.codigo is CodigoError.HECHO_CON_REALIDAD_ASOCIADA
    assert excinfo.value.contexto_extra.get("motivo") == "DEPENDENCIAS_ACTIVAS"
    assert existe_relacion(admin, devolucion.relacion_id)
    assert foto(admin, contexto.owner_user_id, original) == antes


def test_d_a2_desde_el_destino_con_origen_anulado_rechazado(servicio, servicio_efectos, servicio_devoluciones,
                                                            servicio_correcciones, contexto, admin):
    original, devolucion = _devolucion(servicio, servicio_efectos, servicio_devoluciones, contexto)
    anular(servicio, contexto, admin, devolucion.hecho_id)
    antes = foto(admin, contexto.owner_user_id, original)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(servicio_correcciones, contexto, admin, original, relaciones_a_eliminar=(devolucion.relacion_id,))
    assert excinfo.value.codigo is CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO
    assert excinfo.value.contexto_extra.get("motivo") == "RELACION_ENTRANTE"
    assert existe_relacion(admin, devolucion.relacion_id)
    assert foto(admin, contexto.owner_user_id, original) == antes


def test_d_a2_ajeno_otro_owner_e_inexistente_sin_filtracion(servicio, servicio_efectos, servicio_devoluciones,
                                                            servicio_correcciones, contexto, admin, otro_owner):
    original, devolucion = _devolucion(servicio, servicio_efectos, servicio_devoluciones, contexto)
    ajeno, _ = crear_hecho_con_efectos(servicio, servicio_efectos, contexto)
    ajeno_ctx = ContextoOperacion.de_usuario(otro_owner)
    _, devolucion_ajena = _devolucion(servicio, servicio_efectos, servicio_devoluciones, ajeno_ctx)
    errores = []
    for relacion_id in (devolucion.relacion_id, devolucion_ajena.relacion_id, uuid.uuid4()):
        with pytest.raises(ErrorMotor) as excinfo:
            corregir(servicio_correcciones, contexto, admin, ajeno, relaciones_a_eliminar=(relacion_id,))
        errores.append((excinfo.value.codigo, excinfo.value.mensaje, excinfo.value.contexto_extra))
    assert errores[0] == errores[1] == errores[2]
    assert errores[0][0] is CodigoError.AGREGADO_NO_ENCONTRADO and errores[0][2] == {}
    assert existe_relacion(admin, devolucion.relacion_id) and existe_relacion(admin, devolucion_ajena.relacion_id)


def test_d_a2_rechazo_no_deja_nada_escrito(servicio, servicio_efectos, servicio_devoluciones, servicio_correcciones,
                                           contexto, admin):
    """La relectura solo elige el codigo: la correccion entera revierte (efecto propio corregido en la misma
    peticion incluido) y no queda auditoria de la relacion."""
    original, devolucion = _devolucion(servicio, servicio_efectos, servicio_devoluciones, contexto)
    efecto_original = leer_fila(admin, contexto.owner_user_id,
                                "SELECT id FROM gapto.hecho_efectos WHERE hecho_id = %s LIMIT 1", (original,))[0]
    antes = foto(admin, contexto.owner_user_id, original)
    with pytest.raises(ErrorMotor):
        corregir(servicio_correcciones, contexto, admin, original, relaciones_a_eliminar=(devolucion.relacion_id,),
                 efectos_a_actualizar={efecto_original: {"descripcion": "no debe quedar"}})
    assert foto(admin, contexto.owner_user_id, original) == antes
    assert leer_fila(admin, contexto.owner_user_id, "SELECT count(*) FROM gapto.auditoria WHERE registro_id = %s "
                     "AND accion = 'ANULAR'", (devolucion.relacion_id,)) == (0,)


# ==================================================================
# D-A3 · retirar_vinculo (contrato §7.4)
# ==================================================================
def _retirar(servicio_previsiones, contexto, *, vinculo_id, prevision_id_esperada, version):
    kwargs = {"vinculo_id": vinculo_id, "prevision_row_version_esperada": version, "motivo": "F04-R2 R2-A"}
    if "prevision_id_esperada" in inspect.signature(servicio_previsiones.retirar_vinculo).parameters:
        kwargs["prevision_id_esperada"] = prevision_id_esperada
    return servicio_previsiones.retirar_vinculo(contexto, **kwargs)


def _dos_previsiones_misma_version(servicio, servicio_previsiones, contexto):
    p1, p2 = prevision_manual(servicio_previsiones, contexto), prevision_manual(servicio_previsiones, contexto)
    v1, v2 = uuid.uuid4(), uuid.uuid4()
    vincular(servicio_previsiones, contexto, p1, hecho_simple(servicio, contexto), "10.0000", vinculo_id=v1)
    vincular(servicio_previsiones, contexto, p2, hecho_simple(servicio, contexto), "10.0000", vinculo_id=v2)
    version = servicio_previsiones.estado_de(contexto, p1).row_version
    assert servicio_previsiones.estado_de(contexto, p2).row_version == version
    return p1, p2, v1, v2, version


def _vinculos(admin, *previsiones):
    with admin.cursor() as cur:
        cur.execute("RESET ROLE")
        cur.execute("SELECT id, prevision_id, hecho_id, importe_asignado FROM gapto.prevision_hechos "
                    "WHERE prevision_id = ANY(%s) ORDER BY id", (list(previsiones),))
        return cur.fetchall()


def _versiones(servicio_previsiones, contexto, *previsiones):
    return [servicio_previsiones.estado_de(contexto, p).row_version for p in previsiones]


def test_d_a3_vinculo_de_otra_prevision_con_la_misma_version(servicio, servicio_previsiones, contexto, admin):
    p1, p2, _, v2, version = _dos_previsiones_misma_version(servicio, servicio_previsiones, contexto)
    antes = (_vinculos(admin, p1, p2), _versiones(servicio_previsiones, contexto, p1, p2))
    with pytest.raises(ErrorMotor) as excinfo:
        _retirar(servicio_previsiones, contexto, vinculo_id=v2, prevision_id_esperada=p1, version=version)
    assert excinfo.value.codigo is CodigoError.VERSION_DESFASADA
    assert (_vinculos(admin, p1, p2), _versiones(servicio_previsiones, contexto, p1, p2)) == antes


def test_d_a3_tras_reintento_por_conjunto_cambiado(servicio, servicio_previsiones, contexto, admin, monkeypatch):
    """Primer intento: la lectura previa ve el vinculo en P1 (la que cree el llamante), la relectura bajo lock lo
    ve en P2 -> ConjuntoCambiado (40001) y reintento COMPLETO. En el reintento el vinculo ya se lee en P2, que tiene
    la misma version: sobre la base se retira; con R2-A la identidad lo rechaza."""
    p1, p2, _, v2, version = _dos_previsiones_misma_version(servicio, servicio_previsiones, contexto)
    original = repo_prev.leer_vinculo
    llamadas = {"n": 0}

    def leer_vinculo(sesion, vinculo_id):
        llamadas["n"] += 1
        fila = original(sesion, vinculo_id)
        if llamadas["n"] == 1 and fila is not None:  # la lectura previa del primer intento
            fila = dict(fila, prevision_id=p1)
        return fila

    monkeypatch.setattr(repo_prev, "leer_vinculo", leer_vinculo)
    antes = (_vinculos(admin, p1, p2), _versiones(servicio_previsiones, contexto, p1, p2))
    with pytest.raises(ErrorMotor) as excinfo:
        _retirar(servicio_previsiones, contexto, vinculo_id=v2, prevision_id_esperada=p1, version=version)
    assert excinfo.value.codigo is CodigoError.VERSION_DESFASADA
    assert llamadas["n"] >= 3  # hubo reintento: lectura previa y relectura del primer intento + el segundo
    monkeypatch.undo()
    assert (_vinculos(admin, p1, p2), _versiones(servicio_previsiones, contexto, p1, p2)) == antes


def test_d_a3_hecho_del_vinculo_cambiado_tras_la_lectura(servicio, servicio_previsiones, contexto, admin,
                                                         monkeypatch):
    """La relectura exige el hecho_id leido antes de los locks."""
    p1, p2, v1, _, version = _dos_previsiones_misma_version(servicio, servicio_previsiones, contexto)
    original = repo_prev.leer_vinculo
    llamadas = {"n": 0}

    def leer_vinculo(sesion, vinculo_id):
        llamadas["n"] += 1
        fila = original(sesion, vinculo_id)
        if llamadas["n"] == 1 and fila is not None:
            fila = dict(fila, hecho_id=uuid.uuid4())
        return fila

    monkeypatch.setattr(repo_prev, "leer_vinculo", leer_vinculo)
    antes = (_vinculos(admin, p1, p2), _versiones(servicio_previsiones, contexto, p1, p2))
    with pytest.raises(ErrorMotor) as excinfo:
        _retirar(servicio_previsiones, contexto, vinculo_id=v1, prevision_id_esperada=p1, version=version)
    assert excinfo.value.codigo is CodigoError.VERSION_DESFASADA
    monkeypatch.undo()
    assert (_vinculos(admin, p1, p2), _versiones(servicio_previsiones, contexto, p1, p2)) == antes


def test_d_a3_retirada_legitima(servicio, servicio_previsiones, contexto, admin):
    p1, p2, v1, v2, version = _dos_previsiones_misma_version(servicio, servicio_previsiones, contexto)
    r = _retirar(servicio_previsiones, contexto, vinculo_id=v1, prevision_id_esperada=p1, version=version)
    assert r.row_version == version + 1
    assert [f[0] for f in _vinculos(admin, p1, p2)] == [v2]
    assert leer_fila(admin, contexto.owner_user_id, "SELECT count(*) FROM gapto.auditoria WHERE registro_id = %s "
                     "AND accion = 'ANULAR'", (v1,)) == (1,)


def test_d_a3_vinculo_inexistente(servicio, servicio_previsiones, contexto, admin):
    p1, _, _, _, version = _dos_previsiones_misma_version(servicio, servicio_previsiones, contexto)
    with pytest.raises(ErrorMotor) as excinfo:
        _retirar(servicio_previsiones, contexto, vinculo_id=uuid.uuid4(), prevision_id_esperada=p1, version=version)
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO
