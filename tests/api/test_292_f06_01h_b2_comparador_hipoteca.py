# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_292_f06_01h_b2_comparador_hipoteca.py
# Ruta: tests/api/test_292_f06_01h_b2_comparador_hipoteca.py
# Descripcion: Oraculos MB2 de la reapertura de B2 v1.1 (tabla pieza -> mutante -> oraculo, 1:1, 14 piezas, 0
#   agrupaciones; mandato T3-F06 bloque 2 v1.1 §11.3). Patron vigente de test_o6_15: alta con hipoteca; replay
#   exacto idempotente (control); UNA fila de la pieza alterada por fixture (base desechable); MISMO cuerpo
#   reenviado -> 409 IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION con huella identica antes y despues (0 escrituras,
#   0 auditoria); al revertir la alteracion, el replay exacto vuelve a ser idempotente. OG-2: lote parcial con
#   hipoteca (falta Hd) -> rechazo sin completar con OP-22.
#   Alteraciones que un guard fisico de 0354 impide (declaradas, regla de §11.3): MB2-05 (G3 congela la version
#   ALTA de F en M) se altera la MISMA fila y columna con los triggers de usuario desactivados en la transaccion
#   del fixture (session_replication_role = replica, superusuario de la base desechable). MB2-13 (enmendado por la
#   firma del STOP n.º 2, 5f3f5f8e…): pertenencia «Hd sin aportaciones» (aportacion anadida -> 409).
# Version: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 5)
# Version: 0.2.0 (F06 T3-F06 bloque 2 F06-01H, paso 6): test_mb2_13_aportacion por la enmienda de MB2-13.
# ============================================================
from __future__ import annotations

import uuid

import psycopg
import pytest

import f06_01_b2_helpers as c2
import vs01_api_helpers as h
from app.services.compuesto_service import HechosCompuestosService
from test_289_f06_01h_alta_en_compra import LabHip, huella

REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"


@pytest.fixture()
def lab():
    return LabHip()


def _ids(cuerpo) -> dict[str, uuid.UUID]:
    h0 = uuid.UUID(cuerpo["intencion_id"])
    hd = uuid.uuid5(h0, "gapto.f06.compra.desembolso")
    f = uuid.uuid5(h0, "gapto.f06.hipoteca.financiacion")
    return {"h0": h0, "hd": hd, "f": f, "efecto": uuid.uuid5(hd, "gapto.f06.hipoteca.efecto_deuda"),
            "mov": uuid.uuid5(hd, "gapto.f06.hipoteca.movimiento"), "conc": uuid.uuid5(hd, "gapto.f06.hipoteca.conciliacion"),
            "vinculo": uuid.uuid5(hd, "gapto.f06.hipoteca.vinculo_financiacion"),
            "relacion": uuid.uuid5(f, "gapto.f06.hipoteca.garantizada_por"),
            "version": uuid.uuid5(f, "gapto.f06.hipoteca.version_alta"),
            "cuota2": uuid.uuid5(f, "gapto.f06.hipoteca.cuota:2"), "prev1": uuid.uuid5(f, "gapto.f06.hipoteca.prevision:1")}


def _alterar(owner, sql: str, params: tuple, *, sin_triggers: bool = False) -> None:
    if not sin_triggers:
        c2.como_owner(owner, sql, params)
        return
    with psycopg.connect(h.dsn()) as c, c.transaction():       # superusuario de la base desechable
        c.execute("SET LOCAL session_replication_role = replica")
        c.execute(sql, params)


def _replay_rechazado_y_reversible(lab, cuerpo, alterar, revertir) -> None:
    j = lab.compra(cuerpo)
    assert j.status_code == 200 and j.json()["idempotente"] is True, j.text      # control
    alterar()
    antes = huella()
    r = lab.compra(cuerpo)
    assert r.status_code == 409 and r.json()["codigo"] == REUTILIZADA, r.text
    assert huella() == antes
    revertir()
    r = lab.compra(cuerpo)
    assert r.status_code == 200 and r.json()["idempotente"] is True, r.text


def _alta(lab, **hip) -> tuple[dict, dict]:
    cuerpo = lab.peticion_hip(hip=lab.bloque(**hip))
    r = lab.compra(cuerpo)
    assert r.status_code == 200, r.text
    return cuerpo, _ids(cuerpo)


def test_mb2_01_financiacion(lab):
    cuerpo, i = _alta(lab)
    otro = h.leer(lab.owner, "SELECT id FROM gapto.actores_financieros WHERE tercero_id IS NULL")[0][0]
    previo = h.leer(lab.owner, "SELECT financiador_actor_id FROM gapto.financiaciones WHERE entidad_id = %s", (i["f"],))[0][0]
    sql = "UPDATE gapto.financiaciones SET financiador_actor_id = %s WHERE entidad_id = %s"
    _replay_rechazado_y_reversible(lab, cuerpo, lambda: _alterar(lab.owner, sql, (otro, i["f"])),
                                   lambda: _alterar(lab.owner, sql, (previo, i["f"])))


def test_mb2_02_entidad(lab):
    cuerpo, i = _alta(lab)
    nombre = h.leer(lab.owner, "SELECT nombre FROM gapto.entidades WHERE id = %s", (i["f"],))[0][0]
    sql = "UPDATE gapto.entidades SET nombre = %s WHERE id = %s"
    _replay_rechazado_y_reversible(lab, cuerpo, lambda: _alterar(lab.owner, sql, ("Hipoteca · otra", i["f"])),
                                   lambda: _alterar(lab.owner, sql, (nombre, i["f"])))


def test_mb2_03_participaciones(lab):
    cuerpo, i = _alta(lab)                       # prestamo a dos titulares (60/40, titularidad del inmueble)
    ida = ("UPDATE gapto.entidad_participaciones SET porcentaje = porcentaje + CASE WHEN actor_id = %s THEN 1 ELSE -1 "
           "END WHERE entidad_id = %s")
    vuelta = ("UPDATE gapto.entidad_participaciones SET porcentaje = porcentaje - CASE WHEN actor_id = %s THEN 1 "
              "ELSE -1 END WHERE entidad_id = %s")
    _replay_rechazado_y_reversible(lab, cuerpo, lambda: _alterar(lab.owner, ida, (lab.a, i["f"])),
                                   lambda: _alterar(lab.owner, vuelta, (lab.a, i["f"])))


def test_mb2_04_garantizada_por(lab):
    cuerpo, i = _alta(lab)
    _replay_rechazado_y_reversible(
        lab, cuerpo,
        lambda: _alterar(lab.owner, "UPDATE gapto.entidad_relaciones SET vigente_desde = vigente_desde + 1 WHERE id = %s",
                         (i["relacion"],)),
        lambda: _alterar(lab.owner, "UPDATE gapto.entidad_relaciones SET vigente_desde = vigente_desde - 1 WHERE id = %s",
                         (i["relacion"],)))


def test_mb2_05_version_alta(lab):
    cuerpo, i = _alta(lab)
    sql = "UPDATE gapto.financiacion_condiciones_versiones SET tasa_anual_pct = tasa_anual_pct {} 0.0001 WHERE id = %s"
    _replay_rechazado_y_reversible(lab, cuerpo,
                                   lambda: _alterar(lab.owner, sql.format("+"), (i["version"],), sin_triggers=True),
                                   lambda: _alterar(lab.owner, sql.format("-"), (i["version"],), sin_triggers=True))


def test_mb2_05_g3_impide_la_alteracion_con_triggers(lab):
    """Declaracion de §11.3: con 0354, G3 rechaza la alteracion de la version ALTA de F en M."""
    _, i = _alta(lab)
    with pytest.raises(psycopg.errors.RaiseException, match="INV-0354-G3"):
        _alterar(lab.owner, "UPDATE gapto.financiacion_condiciones_versiones SET tasa_anual_pct = tasa_anual_pct + "
                            "0.0001 WHERE id = %s", (i["version"],))


def test_mb2_06_cuotas(lab):
    cuerpo, i = _alta(lab)
    sql = "UPDATE gapto.financiacion_cuotas SET fecha_vencimiento = fecha_vencimiento {} 1 WHERE id = %s"
    _replay_rechazado_y_reversible(lab, cuerpo, lambda: _alterar(lab.owner, sql.format("+"), (i["cuota2"],)),
                                   lambda: _alterar(lab.owner, sql.format("-"), (i["cuota2"],)))


def test_mb2_07_previsiones(lab):
    cuerpo, i = _alta(lab)
    sql = "UPDATE gapto.previsiones SET cuenta_salida_esperada_id = %s WHERE id = %s"
    _replay_rechazado_y_reversible(lab, cuerpo, lambda: _alterar(lab.owner, sql, (lab.c1, i["prev1"])),
                                   lambda: _alterar(lab.owner, sql, (lab.cd, i["prev1"])))


def test_mb2_08_hd(lab):
    cuerpo, i = _alta(lab)
    sql = "UPDATE gapto.hechos_financieros SET concepto = %s WHERE id = %s"
    _replay_rechazado_y_reversible(lab, cuerpo, lambda: _alterar(lab.owner, sql, ("DESEMBOLSO ALTERADO", i["hd"])),
                                   lambda: _alterar(lab.owner, sql, ("PRESTAMO RECIBIDO", i["hd"])))


def test_mb2_09_efecto_deuda(lab):
    cuerpo, i = _alta(lab, titularidad={"modo": "NO_LO_SE"})            # sin atribuciones, como test_o6_15
    sql = "UPDATE gapto.hecho_efectos SET importe_delta = importe_delta {} 0.01 WHERE id = %s"
    _replay_rechazado_y_reversible(lab, cuerpo, lambda: _alterar(lab.owner, sql.format("+"), (i["efecto"],)),
                                   lambda: _alterar(lab.owner, sql.format("-"), (i["efecto"],)))


def test_mb2_10_vinculo_nivel_efecto(lab):
    cuerpo, i = _alta(lab)
    _replay_rechazado_y_reversible(
        lab, cuerpo,
        lambda: _alterar(lab.owner, "UPDATE gapto.hecho_entidades SET efecto_id = NULL WHERE id = %s", (i["vinculo"],)),
        lambda: _alterar(lab.owner, "UPDATE gapto.hecho_entidades SET efecto_id = %s WHERE id = %s",
                         (i["efecto"], i["vinculo"])))


def test_mb2_11_movimiento_p(lab):
    cuerpo, i = _alta(lab)
    otra = h.crear_cuenta(lab.owner, [(lab.actor, 100)], capacidades=("RECIBIR_INGRESO",))
    sql = "UPDATE gapto.movimientos_tesoreria SET cuenta_id = %s WHERE id = %s"
    _replay_rechazado_y_reversible(lab, cuerpo, lambda: _alterar(lab.owner, sql, (otra, i["mov"])),
                                   lambda: _alterar(lab.owner, sql, (lab.cd, i["mov"])))


def test_mb2_12_conciliacion(lab):
    cuerpo, i = _alta(lab)
    sql = "UPDATE gapto.hecho_movimientos_tesoreria SET importe_asignado = importe_asignado {} 0.01 WHERE id = %s"
    _replay_rechazado_y_reversible(lab, cuerpo, lambda: _alterar(lab.owner, sql.format("-"), (i["conc"],)),
                                   lambda: _alterar(lab.owner, sql.format("+"), (i["conc"],)))


def test_mb2_14_atribucion(lab):
    cuerpo, i = _alta(lab)                       # prestamo 60/40: intercambia los actores de las dos filas
    filas = h.leer(lab.owner, "SELECT id, actor_id FROM gapto.efecto_atribuciones WHERE efecto_id = %s ORDER BY id",
                   (i["efecto"],))
    (a1, x1), (a2, x2) = filas
    temporal = uuid.uuid4()                      # paso intermedio: la UNIQUE (efecto, actor) no es diferible

    def poner(primero, segundo):
        sql = "UPDATE gapto.efecto_atribuciones SET actor_id = %s WHERE id = %s"
        _alterar(lab.owner, sql, (temporal, a1), sin_triggers=True)
        _alterar(lab.owner, sql, (segundo, a2), sin_triggers=True)
        _alterar(lab.owner, sql, (primero, a1), sin_triggers=True)
    _replay_rechazado_y_reversible(lab, cuerpo, lambda: poner(x2, x1), lambda: poner(x1, x2))


def test_mb2_13_aportacion(lab):
    """MB2-13 enmendado (firma STOP n.º 2, 5f3f5f8e…; enmienda e28be7c6…): pertenencia «Hd sin aportaciones»;
    una aportacion que aparece en Hd rompe el replay (409, huella identica)."""
    cuerpo, i = _alta(lab)
    nueva = uuid.uuid4()
    _replay_rechazado_y_reversible(
        lab, cuerpo,
        lambda: _alterar(lab.owner, "INSERT INTO gapto.hecho_aportaciones_pago (id, hecho_id, importe, "
                                    "criterio_aportacion, actor_id, porcentaje_aplicado, hecho_movimiento_tesoreria_id) "
                                    "VALUES (%s, %s, 1, 'MANUAL', %s, 100, %s)",
                         (nueva, i["hd"], lab.actor, i["conc"]), sin_triggers=True),
        lambda: _alterar(lab.owner, "DELETE FROM gapto.hecho_aportaciones_pago WHERE id = %s", (nueva,),
                         sin_triggers=True))


def test_og2_lote_parcial_con_hipoteca_no_se_completa(lab, monkeypatch):
    """La compra existe sin Hd (misma intencion registrada antes sin hipoteca): pedirla con hipoteca es un lote
    parcial (raiz Hd ausente) -> 409 sin invocar OP-22 y sin escrituras (extiende test_o6_19)."""
    cuerpo = lab.peticion_hip()
    sin_hip = {k: v for k, v in cuerpo.items() if k != "hipoteca"}
    assert lab.compra(sin_hip).status_code == 200
    llamadas = []
    original = HechosCompuestosService.registrar_hecho_compuesto
    monkeypatch.setattr(HechosCompuestosService, "registrar_hecho_compuesto",
                        lambda self, *a, **k: llamadas.append(1) or original(self, *a, **k))
    antes = huella()
    r = lab.compra(cuerpo)
    assert r.status_code == 409 and r.json()["codigo"] == REUTILIZADA, r.text
    assert llamadas == [] and huella() == antes
