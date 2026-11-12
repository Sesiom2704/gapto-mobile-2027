# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_256_f06_01_b3_correccion_clase.py
# Ruta: tests/api/test_256_f06_01_b3_correccion_clase.py
# Descripcion: F06 T1-F06 · B3 N1 · C-MEJ-03 (correccion atomica de la naturaleza, excepcion E-1) por HTTP como
#   gapto_runtime con RLS (R1 v0.9.5 §III.3.3, §III.3.3bis, §III.3.4, §III.3.6, §III.1ter, Parte IV y §IV.1;
#   v0.9 §III.3.1, §III.3.2, §III.3.5 y §III.4; oraculos v0.7 O5′, §A.6, §A.9.3, §R, B.1 y B.2):
#   O5.1, O5.1b, O5.2, O5.3, O5.4, O5.6-O5.12, O5.13, O5.14a, O5.14b, O5.15-O5.33, O5.34 (espia de
#   CorreccionesService e inventario estatico), O5.35 (estado identico en los rechazos de 2bis), O5.36, O5.37,
#   O5.38, O8.1-O8.3, O9.17 (exacto: R-DM02-01), O10.8, O10.14 y O10.20 bis (L-COSTE de MEJORAS con C-MEJ-03; la
#   declaracion se ejercita con los consumidores de 0352 activados SOLO dentro del test, como en B2).
#   Fixtures declarados (SQL como gapto_owner con la GUC): O5.10, O5.11, O5.12, O5.13, O5.14b y O5.38.
# Version: 0.1.0 (F06 T1-F06 B3 N1)
# ============================================================

from __future__ import annotations

import ast
import json
import pathlib
import uuid

import pytest

import f05_05_helpers as x5
import f06_01_b1_helpers as b
import f06_01_b2_helpers as b2
import f06_01_b3_helpers as b3
import vs01_api_helpers as h

RAIZ = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture
def lab() -> b3.Lab:
    return b3.Lab()


def _mejora(lab, importe="8500.00", fecha="2026-02-10") -> str:
    c = lab.cuerpo(clase="MEJORA", importe=importe, fecha=fecha)
    lab.ok(c)
    return c["intencion_id"]


def _reparacion(lab, importe="300.00", fecha="2026-01-15") -> str:
    c = lab.cuerpo(clase="REPARACION", importe=importe, fecha=fecha)
    lab.ok(c)
    return c["intencion_id"]


def _rechazo(lab, hid, cuerpo, status, codigo, pid=None):
    antes = b3.huella()
    r = lab.corregir(hid, cuerpo, pid=pid)
    assert r.status_code == status, r.text
    assert r.json()["codigo"] == codigo, r.text
    assert b3.huella() == antes                                           # O5.35: estado identico
    return r


def _ok(lab, hid, cuerpo) -> dict:
    r = lab.corregir(hid, cuerpo)
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ conversiones (O5.1, O5.1b, O5.2)
def test_o5_1_mejora_a_reparacion_estado_final_y_auditoria_exactos(lab):
    hid = _mejora(lab)
    e0 = lab.efectos(hid)[0][0]
    version = lab.hecho(hid)[1]
    vinculo = b3.marca(hid)
    atr0 = lab.sql("SELECT id, actor_id, importe_atribuido::text FROM gapto.efecto_atribuciones WHERE efecto_id = %s "
                   "ORDER BY actor_id", (e0,))
    cuerpo = lab.correccion(hid, "REPARACION", presupuestable=True)
    assert cuerpo["intencion_id"] == b3.intencion_vigente(e0)
    assert cuerpo["comparacion_vista"] == {"mes": "2026-02", "resultado_mes_delta_antes": "0.00",
                                           "resultado_mes_delta_despues": "-8500.00", "mejoras_antes": "8500.00",
                                           "mejoras_despues": "0.00", "presupuesto_delta_despues": "-8500.00"}
    r = _ok(lab, hid, cuerpo)
    assert r["idempotente"] is False
    codigo, v, presup, loc, estado = lab.hecho(hid)
    assert (codigo, v, presup, loc, estado) == ("GASTO", version + 1, True, "DESCONOCIDA", "ACTIVO")   # D2
    ef = lab.efectos(hid)
    assert len(ef) == 1 and ef[0][0] != e0
    e1 = ef[0][0]
    from app.patrimonio.correccion_clase import canonica, efecto_destino, sello
    canon = canonica(uuid.UUID(hid), uuid.UUID(lab.pid), {**cuerpo, "categoria_id": uuid.UUID(cuerpo["categoria_id"])})
    assert e1 == efecto_destino(uuid.UUID(cuerpo["intencion_id"]), sello(canon))
    assert ef[0][1:5] == ("GASTO", "8500.0000", lab.cat, None)                                     # causa NULL
    atr1 = lab.sql("SELECT id, actor_id, importe_atribuido::text FROM gapto.efecto_atribuciones WHERE efecto_id = %s "
                   "ORDER BY actor_id", (e1,))
    assert [(a[1], a[2]) for a in atr1] == [(a[1], a[2]) for a in atr0]
    assert [a[0] for a in atr1] == [uuid.uuid5(e1, f"gapto.f06.cmej03.atribucion:{a[1]}") for a in atr0]
    assert lab.sql("SELECT id, efecto_id FROM gapto.hecho_entidades WHERE hecho_id = %s", (hid,)) == [(vinculo, e1)]  # D3
    aud = sorted(b3.auditorias(lab.owner, cuerpo["intencion_id"]))
    assert aud == sorted([("hechos_financieros", "ACTUALIZAR"), ("hecho_efectos", "CREAR"),
                          ("efecto_atribuciones", "CREAR"), ("efecto_atribuciones", "CREAR"),
                          ("hecho_entidades", "ACTUALIZAR"), ("efecto_atribuciones", "ANULAR"),
                          ("efecto_atribuciones", "ANULAR"), ("hecho_efectos", "ANULAR"),
                          ("hechos_financieros", "ACTUALIZAR")])                                    # D5
    anulado = lab.sql("SELECT datos_antes::text FROM gapto.auditoria WHERE request_id = %s AND tabla = 'hecho_efectos' "
                      "AND accion = 'ANULAR'", (cuerpo["intencion_id"],))[0][0]
    assert json.loads(anulado)["causa_valor_activo"] == "TRANSFORMACION_CAPITALIZABLE"              # §III.4
    creado = lab.sql("SELECT datos_despues::text FROM gapto.auditoria WHERE request_id = %s AND tabla = 'hecho_efectos' "
                     "AND accion = 'CREAR'", (cuerpo["intencion_id"],))[0][0]
    assert "causa_valor_activo" in json.loads(creado) and json.loads(creado)["causa_valor_activo"] is None
    resumen = [json.loads(x[0]) for x in lab.sql(
        "SELECT datos_despues::text FROM gapto.auditoria WHERE request_id = %s AND tabla = 'hechos_financieros' "
        "AND datos_antes IS NULL", (cuerpo["intencion_id"],))]
    assert resumen[0]["e0"] == str(e0) and resumen[0]["e1"] == str(e1)
    g = lab.leer_gasto(hid)
    assert g["intencion_correccion_id"] == b3.intencion_vigente(e1)                                 # O5.32
    coste = b2.leer_coste(lab.cli, lab.pid)
    assert coste["MEJORAS"]["total"] == "0.00" and coste["MEJORAS"]["componentes"] == 0             # O10.8


def test_o5_1b_presupuestable_false(lab):
    hid = _mejora(lab)
    cuerpo = lab.correccion(hid, "GASTO_CORRIENTE", presupuestable=False)
    assert cuerpo["comparacion_vista"]["presupuesto_delta_despues"] == "0.00"
    _ok(lab, hid, cuerpo)
    assert lab.hecho(hid)[2] is False


def test_o5_2_reparacion_a_mejora(lab):
    hid = _reparacion(lab)
    cuerpo = lab.correccion(hid, "MEJORA")
    _ok(lab, hid, cuerpo)
    assert lab.hecho(hid)[0] == "MEJORA_PATRIMONIAL" and lab.hecho(hid)[2] is False
    ef = lab.efectos(hid)
    assert ef[0][1:5] == ("VALOR_ACTIVO", "300.0000", None, "TRANSFORMACION_CAPITALIZABLE")


# ------------------------------------------------------------------ guardas y precedencias
def test_o5_3_periodo_cerrado(lab):
    hid = _mejora(lab)
    cuerpo = lab.correccion(hid, "REPARACION", presupuestable=True)
    b3.como_owner(lab.owner,
                  "INSERT INTO gapto.cierres_mensuales (id, owner_user_id, periodo_desde, periodo_hasta, cerrado_at, "
                  "criterio, origen_cierre, metodologia_version, estado, version_cierre) VALUES (%s, %s, '2026-02-01', "
                  "'2026-02-28', now(), 'CAJA', 'CALCULADO_2027', 'v1', 'CERRADO', 1)", (uuid.uuid4(), lab.owner))
    _rechazo(lab, hid, cuerpo, 422, "PERIODO_CERRADO_SIN_POLITICA")


def test_o5_4_o5_25_hecho_sin_marca_de_procedencia_no_admitido(lab):
    hecho, ef = b2.componente_fixture(lab.owner, lab.pid, "2026-03-01", "1000.00")       # H0 por fixture
    cuerpo = {"intencion_id": b3.intencion_vigente(ef), "row_version_esperada": 1, "clase_nueva": "MEJORA",
              "motivo": "x", "comparacion_vista": {"mes": "2026-03", "resultado_mes_delta_antes": "0.00",
                                                   "resultado_mes_delta_despues": "0.00", "mejoras_antes": "1000.00",
                                                   "mejoras_despues": "1000.00", "presupuesto_delta_despues": "0.00"}}
    _rechazo(lab, hecho, cuerpo, 422, "CORRECCION_NATURALEZA_NO_ADMITIDA")
    _rechazo(lab, hecho, {**cuerpo, "row_version_esperada": 99}, 422, "CORRECCION_NATURALEZA_NO_ADMITIDA")  # O5.25
    _rechazo(lab, hecho, {**cuerpo, "intencion_id": str(uuid.uuid4()), "row_version_esperada": 99}, 409,
             "INTENCION_CORRECCION_NO_VIGENTE")


def test_o5_6_o5_7_o5_8_dto_y_o8_1_motivo(lab):
    hid = _mejora(lab)
    rep = _reparacion(lab)
    base = lab.correccion(hid, "REPARACION", presupuestable=True)
    _rechazo(lab, hid, {k: v for k, v in base.items() if k != "categoria_id"}, 422, "ENTRADA_INVALIDA")      # O5.6
    _rechazo(lab, hid, {**base, "presupuestable": None}, 422, "ENTRADA_INVALIDA")                           # O5.7
    m = lab.correccion(rep, "MEJORA")
    _rechazo(lab, rep, {**m, "presupuestable": True}, 422, "ENTRADA_INVALIDA")                              # O5.8
    _rechazo(lab, rep, {**m, "categoria_id": str(lab.cat)}, 422, "ENTRADA_INVALIDA")
    _rechazo(lab, hid, {**base, "motivo": "  "}, 422, "MOTIVO_AUSENTE")
    hecho, ef = b2.componente_fixture(lab.owner, lab.pid, "2026-03-01", "1000.00")
    _rechazo(lab, hecho, {**base, "motivo": None, "intencion_id": b3.intencion_vigente(ef)}, 422, "MOTIVO_AUSENTE")  # O8.1


def test_o5_9_misma_clase_de_efecto_entrada_invalida(lab):
    rep = _reparacion(lab)
    c = lab.correccion(rep, "GASTO_CORRIENTE", presupuestable=True)
    _rechazo(lab, rep, c, 422, "ENTRADA_INVALIDA")
    hid = _mejora(lab)
    _rechazo(lab, hid, lab.correccion(hid, "MEJORA"), 422, "ENTRADA_INVALIDA")


def _gasto_sin_marca(lab) -> tuple[uuid.UUID, uuid.UUID]:
    hecho, ef = uuid.uuid4(), uuid.uuid4()
    import psycopg
    with psycopg.connect(h.dsn()) as c, c.transaction():
        c.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(lab.owner),))
        c.execute("SET LOCAL ROLE gapto_owner")
        tid = c.execute("SELECT id FROM gapto.tipos_hecho WHERE codigo = 'GASTO'").fetchone()[0]
        c.execute("INSERT INTO gapto.hechos_financieros (id, owner_user_id, tipo_hecho_id, fecha_hecho, moneda, "
                  "presupuestable, estado_localizacion, importe_total) VALUES (%s, %s, %s, '2026-03-01', 'EUR', true, "
                  "'DESCONOCIDA', 50)", (hecho, lab.owner, tid))
        c.execute("INSERT INTO gapto.hecho_efectos (id, hecho_id, tipo_efecto, importe_delta, estado_atribucion, "
                  "categoria_id) VALUES (%s, %s, 'GASTO', 50, 'NO_DISPONIBLE', %s)", (ef, hecho, lab.cat))
        c.execute("INSERT INTO gapto.hecho_entidades (id, hecho_id, efecto_id, entidad_id, tipo_relacion, principal, "
                  "owner_user_id) VALUES (%s, %s, %s, %s, 'AFECTA_A', true, %s)", (uuid.uuid4(), hecho, ef, lab.pid,
                                                                                  lab.owner))
    return hecho, ef


def test_o5_10_gasto_con_forma_de_c_mej_01_sin_la_marca(lab):
    hecho, ef = _gasto_sin_marca(lab)
    cuerpo = {"intencion_id": b3.intencion_vigente(ef), "row_version_esperada": 1, "clase_nueva": "MEJORA",
              "motivo": "x", "comparacion_vista": lab.impacto(hecho, "MEJORA") if lab.gasto(hecho).status_code == 200
              else {"mes": "2026-03", "resultado_mes_delta_antes": "-50.00", "resultado_mes_delta_despues": "0.00",
                    "mejoras_antes": "0.00", "mejoras_despues": "50.00", "presupuesto_delta_despues": "0.00"}}
    assert lab.gasto(hecho).status_code == 404                     # la lectura tampoco lo reconoce
    _rechazo(lab, hecho, cuerpo, 422, "CORRECCION_NATURALEZA_NO_ADMITIDA")


def test_o5_11_o5_35_segundo_efecto_2bis_con_cualquier_intencion(lab):
    hid = _reparacion(lab)
    cuerpo = lab.correccion(hid, "MEJORA")
    b3.como_owner(lab.owner, "INSERT INTO gapto.hecho_efectos (id, hecho_id, tipo_efecto, importe_delta, "
                             "estado_atribucion, categoria_id) VALUES (%s, %s, 'GASTO', 10, 'NO_DISPONIBLE', %s)",
                  (uuid.uuid4(), hid, lab.cat))
    for intencion in (cuerpo["intencion_id"], str(uuid.uuid4())):
        for version in (cuerpo["row_version_esperada"], 999):
            _rechazo(lab, hid, {**cuerpo, "intencion_id": intencion, "row_version_esperada": version}, 422,
                     "CORRECCION_NATURALEZA_NO_ADMITIDA")
    assert lab.leer_gasto(hid)["intencion_correccion_id"] is None                                  # O5.33 (b)


def test_o5_12_relacion_entre_hechos_no_admitida(lab):
    hid = _reparacion(lab)
    otro, _ = b2.componente_fixture(lab.owner, lab.pid, "2026-03-01", "10.00")
    b3.como_owner(lab.owner, "INSERT INTO gapto.hecho_relaciones (id, hecho_origen_id, hecho_destino_id, tipo_relacion) "
                             "VALUES (%s, %s, %s, 'PARTE_DE')", (uuid.uuid4(), otro, hid))
    _rechazo(lab, hid, lab.correccion(hid, "MEJORA"), 422, "CORRECCION_NATURALEZA_NO_ADMITIDA")


def test_o5_13_magnitudes_hacia_mejora_no_admitidas(lab):
    hid = _reparacion(lab)
    mag = h.crear_magnitud(lab.owner)
    b3.como_owner(lab.owner, "INSERT INTO gapto.hecho_magnitudes (id, hecho_id, magnitud_id, valor, unidad) "
                             "VALUES (%s, %s, %s, 1, 'l')", (uuid.uuid4(), hid, mag))
    _rechazo(lab, hid, lab.correccion(hid, "MEJORA"), 422, "CORRECCION_NATURALEZA_NO_ADMITIDA")


def _mejora_historica(lab, fecha="2026-02-10", importe="3000.00") -> str:
    c = lab.cuerpo_mh(fecha=fecha, importe=importe)
    r = lab.mejora_historica(c)
    assert r.status_code == 200, r.text
    return c["intencion_id"]


def test_o5_14a_anulado_conservando_el_efecto_y_o5_33a(lab):
    hid = _mejora_historica(lab)
    cuerpo = lab.correccion(hid, "REPARACION", presupuestable=True)
    b2.op03_anular(lab.owner, uuid.UUID(hid))
    assert lab.hecho(hid)[4] == "ANULADO" and len(lab.efectos(hid)) == 1
    assert lab.leer_gasto(hid)["intencion_correccion_id"] is None                                  # O5.33 (a)
    _rechazo(lab, hid, cuerpo, 422, "CORRECCION_NATURALEZA_NO_ADMITIDA")                           # (i)
    _rechazo(lab, hid, {**cuerpo, "intencion_id": str(uuid.uuid4())}, 422,
             "CORRECCION_NATURALEZA_NO_ADMITIDA")                                                  # (ii) M-ID-12


def test_o5_14b_sin_efecto_vigente_por_fixture_y_o5_33c(lab):
    hid = _mejora_historica(lab)
    cuerpo = lab.correccion(hid, "REPARACION", presupuestable=True)
    e0 = lab.efectos(hid)[0][0]
    import psycopg
    try:
        with psycopg.connect(h.dsn()) as c, c.transaction():
            c.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(lab.owner),))
            c.execute("SET LOCAL ROLE gapto_owner")
            c.execute("DELETE FROM gapto.efecto_atribuciones WHERE efecto_id = %s", (e0,))
            c.execute("UPDATE gapto.hecho_entidades SET efecto_id = NULL WHERE hecho_id = %s", (hid,))
            c.execute("DELETE FROM gapto.hecho_efectos WHERE id = %s", (e0,))
    except psycopg.Error as exc:                                    # el estado fisico no lo admite (HF-20)
        pytest.skip(f"O5.14b: el estado fisico no admite un hecho ACTIVO sin efecto ({exc.sqlstate})")
    assert lab.efectos(hid) == []
    _rechazo(lab, hid, cuerpo, 422, "CORRECCION_NATURALEZA_NO_ADMITIDA")
    _rechazo(lab, hid, {**cuerpo, "intencion_id": str(uuid.uuid4())}, 422, "CORRECCION_NATURALEZA_NO_ADMITIDA")


def test_o5_15_ruta_de_otra_propiedad(lab):
    hid = _mejora(lab)
    otra = b.crear(lab.cli, b.alta(b.solo_mia(), nombre="Otra"))
    cuerpo = lab.correccion(hid, "REPARACION", presupuestable=True)
    _rechazo(lab, hid, cuerpo, 422, "CORRECCION_NATURALEZA_NO_ADMITIDA", pid=otra["id"])


def test_o5_16_impacto_desfasado(lab):
    hid = _mejora(lab)
    cuerpo = lab.correccion(hid, "REPARACION", presupuestable=True)
    vista = dict(cuerpo["comparacion_vista"], resultado_mes_delta_despues="0.00")
    _rechazo(lab, hid, {**cuerpo, "comparacion_vista": vista}, 409, "IMPACTO_CORRECCION_DESFASADO")


def test_o5_17_op21_conserva_el_efecto_version_e_impacto(lab):
    hid = _reparacion(lab)
    cuerpo = lab.correccion(hid, "MEJORA")
    e0 = lab.efectos(hid)[0][0]
    b2.op21_importe(lab.owner, uuid.UUID(hid), e0, "320.00")
    assert lab.efectos(hid)[0][0] == e0
    _rechazo(lab, hid, cuerpo, 409, "VERSION_DESFASADA")                                           # O8.3 tambien
    nueva = {**cuerpo, "row_version_esperada": lab.hecho(hid)[1]}
    _rechazo(lab, hid, nueva, 409, "IMPACTO_CORRECCION_DESFASADO")
    _ok(lab, hid, lab.correccion(hid, "MEJORA"))


def test_o5_18_otro_gasto_del_mes_no_desfasa(lab):
    hid = _mejora(lab)
    cuerpo = lab.correccion(hid, "REPARACION", presupuestable=True)
    lab.ok(lab.cuerpo(clase="REPARACION", importe="77.00", fecha="2026-02-11"))
    _ok(lab, hid, cuerpo)


def test_o5_5_op21_generico_sigue_rechazando_la_conversion(lab):
    """CC-R1-11: el OP-21 generico conserva la restriccion de B0 (C-MEJ-03 no la relaja)."""
    import decimal

    from app.core.errores import ErrorMotor
    from app.core.modelos_efectos import DatosEfecto
    from app.services.correcciones_service import CorreccionesService, DatosCorreccion
    hid = _mejora(lab)
    e0 = lab.efectos(hid)[0][0]
    atrs = tuple(a[0] for a in lab.sql("SELECT id FROM gapto.efecto_atribuciones WHERE efecto_id = %s", (e0,)))
    datos = DatosCorreccion(
        hecho_id=uuid.UUID(hid), row_version_esperada=lab.hecho(hid)[1], motivo="O5.5", efectos_a_eliminar=(e0,),
        atribuciones_a_eliminar=atrs,
        efectos_a_crear=(DatosEfecto(efecto_id=uuid.uuid4(), tipo_efecto="GASTO", importe_delta=decimal.Decimal("8500"),
                                     estado_atribucion="NO_DISPONIBLE", categoria_id=lab.cat),))
    antes = b3.huella()
    with pytest.raises(ErrorMotor) as exc:
        CorreccionesService(b2.unidad()).corregir(b2.ctx(lab.owner), datos)
    assert exc.value.codigo.value == "CORRECCION_CONVERSION_VALOR_ACTIVO_NO_ADMITIDA"
    assert b3.huella() == antes


# ------------------------------------------------------------------ identidad (§III.3.6)
def test_o5_19_o5_29_replay_inmediato_idempotente(lab):
    hid = _mejora(lab)
    cuerpo = lab.correccion(hid, "REPARACION", presupuestable=True)
    _ok(lab, hid, cuerpo)
    antes = b3.huella()
    r = _ok(lab, hid, cuerpo)
    assert r["idempotente"] is True and b3.huella() == antes


def test_o5_20_o5_31_misma_intencion_otro_contenido(lab):
    hid = _mejora(lab)
    cuerpo = lab.correccion(hid, "REPARACION", presupuestable=True)
    _ok(lab, hid, cuerpo)
    _rechazo(lab, hid, {**cuerpo, "presupuestable": False}, 409, "INTENCION_CORRECCION_NO_VIGENTE")
    _rechazo(lab, hid, {**cuerpo, "motivo": "otro"}, 409, "INTENCION_CORRECCION_NO_VIGENTE")


def test_o5_21_intencion_de_otro_hecho(lab):
    h1 = _mejora(lab)
    h2 = _mejora(lab, fecha="2026-02-12")
    c1 = lab.correccion(h1, "REPARACION", presupuestable=True)
    c2 = lab.correccion(h2, "REPARACION", presupuestable=True)
    _rechazo(lab, h2, {**c2, "intencion_id": c1["intencion_id"]}, 409, "INTENCION_CORRECCION_NO_VIGENTE")


def test_o5_22_reintento_de_la_alta_tras_la_correccion(lab):
    c = lab.cuerpo(clase="MEJORA", importe="8500.00", fecha="2026-02-10")
    lab.ok(c)
    _ok(lab, c["intencion_id"], lab.correccion(c["intencion_id"], "REPARACION", presupuestable=True))
    antes = b3.huella()
    r = lab.registrar(c)
    assert r.status_code == 409 and r.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert b3.huella() == antes


@pytest.mark.parametrize("paso", list(range(1, 10)))
def test_o5_23_fallo_inyectado_tras_cada_paso_deshace_todo(lab, monkeypatch, paso):
    hid = _mejora(lab)
    cuerpo = lab.correccion(hid, "REPARACION", presupuestable=True)
    from app.patrimonio import correccion_clase as cc
    real = cc._auditar
    llamadas = {"n": 0}

    def con_fallo(*a, **k):
        llamadas["n"] += 1
        if llamadas["n"] == paso:
            raise RuntimeError(f"fallo inyectado en la auditoria {paso}")
        return real(*a, **k)
    monkeypatch.setattr(cc, "_auditar", con_fallo)
    antes = b3.huella()
    with pytest.raises(Exception):
        r = lab.corregir(hid, cuerpo)
        assert r.status_code >= 500
        raise RuntimeError("500")
    assert b3.huella() == antes


def test_o5_24_ida_y_vuelta_conserva_el_vinculo_y_la_procedencia(lab):
    hid = _mejora(lab)
    v0 = lab.hecho(hid)[1]
    _ok(lab, hid, lab.correccion(hid, "REPARACION", presupuestable=True))
    e1 = lab.efectos(hid)[0][0]
    vuelta = lab.correccion(hid, "MEJORA")
    assert vuelta["intencion_id"] == b3.intencion_vigente(e1)
    _ok(lab, hid, vuelta)
    assert lab.hecho(hid)[0] == "MEJORA_PATRIMONIAL" and lab.hecho(hid)[1] == v0 + 2
    assert lab.sql("SELECT id FROM gapto.hecho_entidades WHERE hecho_id = %s", (hid,)) == [(b3.marca(hid),)]
    assert lab.leer_gasto(hid)["intencion_correccion_id"] is not None                              # sigue elegible
    assert lab.efectos(hid)[0][4] == "TRANSFORMACION_CAPITALIZABLE"


def test_o5_26_hecho_ajeno_404(lab):
    hid = _mejora(lab)
    cuerpo = lab.correccion(hid, "REPARACION", presupuestable=True)
    otro = b3.Lab(cambio=False)
    antes = b3.huella()
    r = otro.corregir(hid, cuerpo, pid=otro.pid)
    assert r.status_code == 404 and r.json()["codigo"] == "AGREGADO_NO_ENCONTRADO" and b3.huella() == antes


def test_o5_27_o5_28_intencion_consumida_nunca_vuelve(lab):
    hid = _mejora(lab)
    i1 = lab.correccion(hid, "REPARACION", presupuestable=True)
    _ok(lab, hid, i1)
    _ok(lab, hid, lab.correccion(hid, "MEJORA"))
    _rechazo(lab, hid, i1, 409, "INTENCION_CORRECCION_NO_VIGENTE")                                 # O5.27
    nueva = lab.hecho(hid)[1]
    _rechazo(lab, hid, {**i1, "row_version_esperada": nueva}, 409, "INTENCION_CORRECCION_NO_VIGENTE")  # O5.28 (a)
    _rechazo(lab, hid, {**i1, "row_version_esperada": nueva, "clase_nueva": "MEJORA", "categoria_id": None,
                        "presupuestable": None}, 409, "INTENCION_CORRECCION_NO_VIGENTE")          # O5.28 (b)


def test_o5_30_replay_tras_subir_solo_la_version(lab):
    hid = _mejora(lab)
    cuerpo = lab.correccion(hid, "REPARACION", presupuestable=True)
    _ok(lab, hid, cuerpo)
    b2.op02_fecha(lab.owner, uuid.UUID(hid), "2026-02-11")
    antes = b3.huella()
    assert _ok(lab, hid, cuerpo)["idempotente"] is True and b3.huella() == antes


def test_o5_33_d_y_o9_17_con_deuda_no_hay_intencion_ni_correccion(lab):
    c = lab.cuerpo(deuda=[{"actor_id": lab.ta, "me_debe": "SI"}], derechos=[{"actor_id": lab.ta, "importe": "150.00"}])
    lab.ok(c)
    hid = c["intencion_id"]
    g = lab.leer_gasto(hid)
    assert g["intencion_correccion_id"] is None and g["limitacion"] == b3.LIMITACION and g["con_deuda"] is True
    principal = lab.sql("SELECT efecto_id FROM gapto.hecho_entidades WHERE id = %s", (b3.marca(hid),))[0][0]
    cuerpo = {"intencion_id": b3.intencion_vigente(principal), "row_version_esperada": g["row_version"],
              "clase_nueva": "MEJORA", "motivo": "x",
              "comparacion_vista": lab.impacto(hid, "MEJORA")}
    _rechazo(lab, hid, cuerpo, 422, "CORRECCION_NATURALEZA_NO_ADMITIDA")
    assert b3.auditorias(lab.owner, cuerpo["intencion_id"]) == []
    r = _reparacion(lab)
    assert lab.leer_gasto(r)["intencion_correccion_id"] == b3.intencion_vigente(lab.efectos(r)[0][0])  # O5.33 (d)


def test_o5_36_replay_exacto_tras_anular_da_2bis(lab):
    hid = _mejora_historica(lab)
    cuerpo = lab.correccion(hid, "REPARACION", presupuestable=True)
    _ok(lab, hid, cuerpo)
    b2.op03_anular(lab.owner, uuid.UUID(hid))
    _rechazo(lab, hid, cuerpo, 422, "CORRECCION_NATURALEZA_NO_ADMITIDA")


# ------------------------------------------------------------------ localizacion (§III.1ter)
def test_o5_37_mejora_a_reparacion_queda_desconocida_y_op21_posterior_se_acepta(lab):
    hid = _mejora(lab)
    _ok(lab, hid, lab.correccion(hid, "REPARACION", presupuestable=True))
    assert lab.hecho(hid)[0] == "GASTO" and lab.hecho(hid)[3] == "DESCONOCIDA"
    b2.op21_importe(lab.owner, uuid.UUID(hid), lab.efectos(hid)[0][0], "8600.00")
    assert lab.efectos(hid)[0][2] == "8600.0000"


def test_o5_38_mejora_legada_no_aplica_a_gasto_no_admitida(lab):
    hid = _mejora_historica(lab)
    b3.como_owner(lab.owner, "UPDATE gapto.hechos_financieros SET estado_localizacion = 'NO_APLICA' WHERE id = %s",
                  (hid,))
    _rechazo(lab, hid, lab.correccion(hid, "REPARACION", presupuestable=True), 422,
             "CORRECCION_NATURALEZA_NO_ADMITIDA")


# ------------------------------------------------------------------ O8
def test_o8_2_no_elegible_y_periodo_cerrado(lab):
    hid = _reparacion(lab)
    otro, _ = b2.componente_fixture(lab.owner, lab.pid, "2026-03-01", "10.00")
    b3.como_owner(lab.owner, "INSERT INTO gapto.hecho_relaciones (id, hecho_origen_id, hecho_destino_id, tipo_relacion) "
                             "VALUES (%s, %s, %s, 'PARTE_DE')", (uuid.uuid4(), otro, hid))
    b3.como_owner(lab.owner,
                  "INSERT INTO gapto.cierres_mensuales (id, owner_user_id, periodo_desde, periodo_hasta, cerrado_at, "
                  "criterio, origen_cierre, metodologia_version, estado, version_cierre) VALUES (%s, %s, '2026-01-01', "
                  "'2026-01-31', now(), 'CAJA', 'CALCULADO_2027', 'v1', 'CERRADO', 1)", (uuid.uuid4(), lab.owner))
    _rechazo(lab, hid, lab.correccion(hid, "MEJORA"), 422, "CORRECCION_NATURALEZA_NO_ADMITIDA")


# ------------------------------------------------------------------ O5.34 · E-1 sin delegar en OP-21 (§IV.1, D1)
def test_o5_34_espia_cero_llamadas_a_correcciones_service(lab, monkeypatch):
    from app.services import correcciones_service as cs
    llamadas: list[str] = []

    def espia(nombre):
        def _f(*a, **k):
            llamadas.append(nombre)
            raise AssertionError(f"C-MEJ-03 llamo a CorreccionesService.{nombre}")
        return _f
    for nombre, valor in list(vars(cs.CorreccionesService).items()):
        if callable(valor) and not nombre.startswith("__"):
            monkeypatch.setattr(cs.CorreccionesService, nombre, espia(nombre))
    hid = _mejora(lab)
    _ok(lab, hid, lab.correccion(hid, "REPARACION", presupuestable=True))                         # O5.1
    _ok(lab, hid, lab.correccion(hid, "MEJORA"))                                                   # O5.24
    rep = _reparacion(lab)
    _ok(lab, rep, lab.correccion(rep, "MEJORA"))                                                   # O5.2
    assert llamadas == []


def test_o5_34_inventario_estatico_del_modulo_de_c_mej_03():
    fuente = (RAIZ / "backend/app/patrimonio/correccion_clase.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    modulos = {n.module for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)} | {
        a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m and "correcciones_service" in m for m in modulos)
    nombres = _nombres_de_codigo(fuente)
    assert not any(n == "CorreccionesService" or n.startswith("_eliminar_") or n == "corregir" for n in nombres)


def _nombres_de_codigo(fuente: str) -> set[str]:
    """Identificadores y atributos del CODIGO (no de comentarios ni de cadenas)."""
    arbol = ast.parse(fuente)
    nombres = {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}
    nombres |= {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}
    nombres |= {a.name for n in ast.walk(arbol) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    nombres |= {n.module or "" for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)}
    return nombres


# ------------------------------------------------------------------ L-COSTE de MEJORAS (O10.14, O10.20 bis)
def test_o10_14_c_mej_03_desactualiza_la_declaracion_de_mejoras_sin_tocar_la_propiedad(lab, monkeypatch):
    b2.habilitar_0352(monkeypatch)
    _mejora(lab, fecha="2026-02-10")
    rep = _reparacion(lab, fecha="2026-01-15")
    huella = lab.cli.get(f"/v1/propiedades/{lab.pid}/coste", params={"a_fecha": "2026-06-30"},
                         headers=h.AUTH).json()["coste"]["MEJORAS"]["huella_conjunto"]
    r = lab.cli.post(
        f"/v1/propiedades/{lab.pid}/completitud", json={"intencion_id": str(uuid.uuid4()),
                                                        "row_version_esperada": lab.version_propiedad(),
                                                        "ambito": "MEJORAS", "completo": True,
                                                        "fecha_corte": "2026-06-30", "huella_conjunto_vista": huella},
        headers=h.AUTH)
    assert r.status_code == 200, r.text
    fila = lab.sql("SELECT row_to_json(p)::text FROM gapto.propiedades p WHERE entidad_id = %s", (lab.pid,))
    version = lab.version_propiedad()
    assert b2.leer_coste(lab.cli, lab.pid)["MEJORAS"]["estado"] == "COMPLETO"
    _ok(lab, rep, lab.correccion(rep, "MEJORA"))
    m = b2.leer_coste(lab.cli, lab.pid)["MEJORAS"]
    assert (m["estado"], m["motivo_estado"]) == ("PARCIAL", "DECLARACION_DESACTUALIZADA")
    assert lab.sql("SELECT row_to_json(p)::text FROM gapto.propiedades p WHERE entidad_id = %s", (lab.pid,)) == fila
    assert lab.version_propiedad() == version


def test_o10_20_bis_ida_y_vuelta_con_ids_nuevos_no_recupera(lab, monkeypatch):
    b2.habilitar_0352(monkeypatch)
    hid = _mejora(lab, fecha="2026-02-10")
    huella = lab.cli.get(f"/v1/propiedades/{lab.pid}/coste", params={"a_fecha": "2026-06-30"},
                         headers=h.AUTH).json()["coste"]["MEJORAS"]["huella_conjunto"]
    r = lab.cli.post(f"/v1/propiedades/{lab.pid}/completitud", json={
        "intencion_id": str(uuid.uuid4()), "row_version_esperada": lab.version_propiedad(), "ambito": "MEJORAS",
        "completo": True, "fecha_corte": "2026-06-30", "huella_conjunto_vista": huella}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    _ok(lab, hid, lab.correccion(hid, "REPARACION", presupuestable=True))
    assert b2.leer_coste(lab.cli, lab.pid)["MEJORAS"]["estado"] == "PARCIAL"
    _ok(lab, hid, lab.correccion(hid, "MEJORA"))
    m = b2.leer_coste(lab.cli, lab.pid)["MEJORAS"]
    assert (m["estado"], m["motivo_estado"]) == ("PARCIAL", "DECLARACION_DESACTUALIZADA")
