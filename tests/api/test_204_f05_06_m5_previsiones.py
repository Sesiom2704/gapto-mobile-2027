# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_204_f05_06_m5_previsiones.py
# Ruta: tests/api/test_204_f05_06_m5_previsiones.py
# Descripcion: Confirmacion de previsiones de F05-06 M5 (§A6; F05 §59
#   F05-D044; AJ-M5-DEC-02..08 y 11; laminas PREV v0.2 y HOME-01 v0.4). Con el
#   rol real gapto_runtime (adaptador HTTP) y RLS. Cada oraculo economico es
#   una DIFERENCIA respecto de la base, con su signo (AJ-M5-DEC-11):
#     - G2 «prevision confirmada (luz)» 74 -> 81,37 con «Si»;
#     - parcial (seguro 120, 40 con «No»), sobrepago con «No» (desviacion);
#     - REALIZADA solo con marcar_realizada = true; 422 si falta (4 rutas);
#     - OMITIDA sin hecho ni movimiento, rechazada con realidad, reintento 409
#       con el estado releido, sin escritura ni segundo sucesor;
#     - MONTH-RULE-06: resultado_mes identico con y sin previsiones;
#     - guarda de doble porcion desde la API (consumida y crecida);
#     - naturalezas separadas y recuento comun; importe desconocido;
#     - RODANTE: omitir, OP-17 y OP-22 crean el sucesor; replay estable;
#     - replay compuesto (A3 y A4): los cuatro casos de AJ-M5-DEC-02;
#     - transferencia desde la prevision por HTTP; prevision + reparto M3;
#     - ids de otro owner; estados excluidos; candidatos (ventana, filtros,
#       ampliado) y vincular fuera de la ventana; Inicio con 0, 2 y 3;
#     - vencida con hoy_owner (no UTC).
#   Reloj fijo 2026-10-10 12:00Z (Madrid) salvo donde se indica.
# Version: 0.1.0 (F05-06 M5 §A6)
# ============================================================

from __future__ import annotations

import threading
import uuid

import pytest

import f05_01_helpers as fh
import f05_06_m3_helpers as r3
import f05_06_m5_helpers as m
import vs01_api_helpers as h

D = m.D


@pytest.fixture()
def t():
    owner, actor, cli, cta, ahorro = m.entorno()
    iber = m.x.tercero(cli, "Iberdrola")
    hogar = m.x.categoria(owner, "Electricidad")
    return owner, actor, cli, cta, ahorro, iber, hogar


def _luz(owner, cta, iber, hogar=None, **kw):
    base = dict(desde="2026-10-01", hasta="2026-10-05", importe="74.00", tercero=iber, categoria=hogar,
                cuenta_salida=cta)
    base.update(kw)
    return m.prevision(owner, "Electricidad", **base)


def _cod(r):
    return r.json().get("codigo")


def _dif(antes: dict, despues: dict) -> dict:
    return {k: D(despues[k]) - D(antes[k]) for k in ("ingresos_propios", "gastos_propios", "resultado")}


def _ids(lista):
    return [uuid.UUID(f["id"]) for f in lista]


# ==================================================================
# G2 · prevision confirmada (luz)
# ==================================================================
def test_g2_prevision_confirmada_luz(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    luz = _luz(owner, cta, iber, hogar)
    antes_res, antes_saldo, antes_h = m.resultado(cli), m.saldo(owner, cta), m.huella(owner)
    assert luz in _ids(m.inicio(cli)["requiere_atencion"]["primeras"])

    c, r = m.gasto_desde(cli, owner, cta, luz, "81.37", True, tercero=iber, categoria=hogar)
    assert r.status_code == 200, r.text
    hid = uuid.UUID(c["intencion_id"])
    # Un hecho GASTO de 81,37 con su efecto y su atribucion propia.
    assert m.efectos(owner, hid) == [("GASTO", D("81.3700"))]
    assert m.uno(owner, "SELECT a.actor_id, a.importe_atribuido FROM gapto.efecto_atribuciones a JOIN "
                        "gapto.hecho_efectos e ON e.id = a.efecto_id WHERE e.hecho_id = %s", (hid,)) == (actor, D("81.3700"))
    # Un movimiento de salida de 81,37 en la cuenta (diferencia de saldo con signo).
    assert m.movimientos(owner, hid) == [(cta, D("-81.3700"))]
    assert m.saldo(owner, cta) - antes_saldo == D("-81.37")
    # Un vinculo de 81,37 y la prevision REALIZADA.
    assert m.vinculos(owner, luz) == [(hid, D("81.3700"))]
    assert m.estado(owner, luz) == "REALIZADA"
    # Resultado del mes: cambia EXACTAMENTE en el efecto de ese gasto, una vez (signo de A9:
    # gastos_propios suma el delta, resultado = ingresos - gastos). La prevision no aporta nada.
    assert _dif(antes_res, m.resultado(cli)) == {"ingresos_propios": D(0), "gastos_propios": D("81.37"),
                                                 "resultado": D("-81.37")}
    despues_h = m.huella(owner)
    assert despues_h[0] - antes_h[0] == 1 and despues_h[6] - antes_h[6] == 1 and despues_h[7] == antes_h[7]
    # Ya no aparece en Requiere atencion.
    assert m.inicio(cli)["requiere_atencion"]["n"] == 0
    assert m.detalle(cli, luz)["estado"] == "REALIZADA"


# ==================================================================
# Parcial, sobrepago y cobertura explicita
# ==================================================================
def test_parcial_sigue_en_requiere_atencion_aunque_no_venza(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    mapfre = m.x.tercero(cli, "Mapfre")
    seguro = m.prevision(owner, "Seguro hogar", desde="2026-10-25", hasta="2026-10-30", importe="120.00",
                         tercero=mapfre, cuenta_salida=cta)
    assert m.inicio(cli)["requiere_atencion"]["n"] == 0
    assert seguro in _ids(m.inicio(cli)["proximos"])
    c, r = m.gasto_desde(cli, owner, cta, seguro, "40.00", False, tercero=mapfre)
    assert r.status_code == 200, r.text
    assert m.estado(owner, seguro) == "ABIERTA"
    d = m.detalle(cli, seguro)
    assert (d["cubierto"], d["queda"], d["desviacion"], d["vencida"], d["pagos"]) == ("40.00", "80.00", None, False, 1)
    ini = m.inicio(cli)
    assert ini["requiere_atencion"]["n"] == 1 and _ids(ini["requiere_atencion"]["primeras"]) == [seguro]
    assert seguro not in _ids(ini["proximos"])
    p = m.pendientes(cli)
    assert _ids(p["secciones"]["con_pago_parcial"]) == [seguro] and p["por_pagar"]["importe"] == "80.00"
    assert d["acciones"]["omitir"] == {"disponible": False,
                                       "motivo": "«No hubo este mes» no está disponible: ya tiene un pago enlazado."}
    assert d["acciones"]["swipe"]["disponible"] is False


def test_sobrepago_con_no_muestra_desviacion_y_sigue_abierta(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    gas = m.prevision(owner, "Gas", desde="2026-10-01", hasta="2026-10-10", importe="120.00", tercero=iber)
    _, r = m.gasto_desde(cli, owner, cta, gas, "130.00", False)
    assert r.status_code == 200, r.text
    d = m.detalle(cli, gas)
    assert (d["estado"], d["cubierto"], d["queda"], d["desviacion"]) == ("ABIERTA", "130.00", None, "10.00")


@pytest.mark.parametrize("ruta", ["gasto", "ingreso", "transferencia", "vincular"])
def test_marcar_realizada_obligatorio_sin_defecto(t, ruta):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    tipo = {"gasto": "GASTO", "ingreso": "INGRESO", "transferencia": "TRANSFERENCIA", "vincular": "GASTO"}[ruta]
    pid = m.prevision(owner, "P", tipo=tipo, importe="10.00", tercero=iber if tipo != "TRANSFERENCIA" else None)
    base = m.huella(owner)
    if ruta == "gasto":
        _, r = m.gasto_desde(cli, owner, cta, pid, "10.00", None)
    elif ruta == "ingreso":
        _, r = m.ingreso_desde(cli, owner, cta, pid, "10.00", None)
    elif ruta == "transferencia":
        _, r = m.transferencia_desde(cli, owner, cta, ahorro, pid, "10.00", None)
    else:
        hid = m.x.gasto(cli, cta, importe="10.00", tercero_id=iber)
        base = m.huella(owner)
        _, r = m.vincular(cli, owner, pid, hid, "10.00", None)
    assert r.status_code == 422 and "marcar_realizada" in r.json()["mensaje"]
    assert m.huella(owner) == base
    # Un valor no booleano tampoco se acepta (StrictBool).
    if ruta == "gasto":
        c, _ = m.gasto_desde(cli, owner, cta, pid, "10.00", None)
        c["prevision"]["marcar_realizada"] = "true"
        assert cli.post(m.GASTO, json=c, headers=h.AUTH).status_code == 422


def test_realizada_solo_con_si(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    a = _luz(owner, cta, iber)
    b = _luz(owner, cta, iber)
    m.gasto_desde(cli, owner, cta, a, "74.00", False)
    m.gasto_desde(cli, owner, cta, b, "74.00", True)
    assert (m.estado(owner, a), m.estado(owner, b)) == ("ABIERTA", "REALIZADA")


# ==================================================================
# Omitir
# ==================================================================
def test_omitir_sin_hecho_ni_movimiento(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    luz = _luz(owner, cta, iber)
    base, saldo = m.huella(owner), m.saldo(owner, cta)
    c, r = m.omitir(cli, owner, luz, motivo="  Facturación bimestral  ")
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "OMITIDA"
    despues = m.huella(owner)
    assert despues[:7] == base[:7] and despues[7] == base[7]  # sin hechos, efectos, movimientos ni vinculos
    assert m.saldo(owner, cta) == saldo
    assert m.uno(owner, "SELECT motivo_ajuste FROM gapto.previsiones WHERE id = %s", (luz,))[0] == "Facturación bimestral"
    assert luz not in _ids(m.pendientes(cli)["secciones"]["vencidas"])


def test_omitir_rechazada_con_realidad_activa(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    seguro = m.prevision(owner, "Seguro", importe="120.00", tercero=iber)
    m.gasto_desde(cli, owner, cta, seguro, "40.00", False)
    base = m.huella(owner)
    _, r = m.omitir(cli, owner, seguro)
    assert r.status_code == 409 and _cod(r) == "ESTADO_PREVISION_INCOMPATIBLE"
    assert r.json()["detalle"]["estado_actual"]["estado"] == "ABIERTA"
    assert m.huella(owner) == base and m.estado(owner, seguro) == "ABIERTA"


def test_omitir_reintento_409_sin_escritura_ni_segundo_sucesor(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    regla, cabeza = m.rodante(owner, cuenta_salida=cta)
    c, r = m.omitir(cli, owner, cabeza)
    assert r.status_code == 200, r.text
    cadena = m.previsiones_de_regla(owner, regla)
    assert [e for _, e, _ in cadena] == ["OMITIDA", "ABIERTA"]
    base = m.huella(owner)
    # Reintento de LA MISMA intencion (respuesta perdida): nunca exito, 409 con el estado releido.
    r2 = cli.post(f"/v1/previsiones/{cabeza}/omitir", json=c, headers=h.AUTH)
    assert r2.status_code == 409 and _cod(r2) == "ESTADO_PREVISION_INCOMPATIBLE"
    assert r2.json()["detalle"]["estado_actual"]["estado"] == "OMITIDA"
    assert m.huella(owner) == base and len(m.previsiones_de_regla(owner, regla)) == 2


def test_omitir_version_desfasada_409(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    luz = _luz(owner, cta, iber)
    base = m.huella(owner)
    _, r = m.omitir(cli, owner, luz, row_version=5)
    assert r.status_code == 409 and _cod(r) == "VERSION_DESFASADA" and r.json()["mensaje"].startswith("Ha cambiado; revisa")
    assert r.json()["detalle"]["estado_actual"]["estado"] == "ABIERTA"
    assert m.huella(owner) == base


# ==================================================================
# MONTH-RULE-06 · las previsiones no suman
# ==================================================================
def test_month_rule_06_resultado_identico_con_y_sin_previsiones(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    m.x.gasto(cli, cta, importe="12.00")
    m.x.ingreso(cli, cta, importe="100.00")
    sin = m.resultado(cli)
    _luz(owner, cta, iber)
    m.prevision(owner, "Nómina", tipo="INGRESO", importe="2100.00", cuenta_entrada=cta)
    m.prevision(owner, "Nómina → Ahorro", tipo="TRANSFERENCIA", importe="500.00")
    m.prevision(owner, "Agua", importe=None)
    assert m.resultado(cli) == sin


# ==================================================================
# Guarda de doble porcion desde la API
# ==================================================================
def test_candidato_consumido_antes_del_post(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    a = _luz(owner, cta, iber)
    b = _luz(owner, cta, iber)
    hid = m.x.gasto(cli, cta, fecha="2026-10-03", importe="76.10", tercero_id=iber)
    assert [c["porcion_disponible"] for c in m.candidatos(cli, b)["candidatos"]] == ["76.10"]
    _, r = m.vincular(cli, owner, a, hid, "76.10")  # otro enlace consume la porcion
    assert r.status_code == 200, r.text
    base = m.huella(owner)
    _, r = m.vincular(cli, owner, b, hid, "76.10")
    assert r.status_code == 409 and _cod(r) == "PORCION_DE_REALIDAD_EXCEDIDA"
    assert r.json()["detalle"]["motivo"] == "EXCEDE"
    assert m.huella(owner) == base and m.vinculos(owner, b) == []


def test_porcion_que_crece_entre_lista_y_post(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    a = _luz(owner, cta, iber)
    b = _luz(owner, cta, iber)
    hid = m.x.gasto(cli, cta, fecha="2026-10-03", importe="100.00", tercero_id=iber)
    m.vincular(cli, owner, a, hid, "100.00", False)  # A no queda cubierta: 100 del hecho
    # B lista el hecho sin porcion; luego el vinculo de A se retira (porcion crece a 100).
    assert m.candidatos(cli, b)["candidatos"] == []
    vid = m.uno(owner, "SELECT id FROM gapto.prevision_hechos WHERE prevision_id = %s", (a,))[0]
    from app.services.previsiones_service import PrevisionesService

    PrevisionesService(fh.unidad()).retirar_vinculo(m.ctx(owner), vinculo_id=vid, prevision_id_esperada=a,
                                                    prevision_row_version_esperada=m.version(owner, a))
    base = m.huella(owner)
    _, r = m.vincular(cli, owner, b, hid, "60.00")  # lo que el usuario vio en otra lista
    assert r.status_code == 409 and _cod(r) == "PORCION_CAMBIADA"
    assert r.json()["detalle"]["porcion_disponible"] == "100.00"
    assert m.huella(owner) == base and m.vinculos(owner, b) == [] and m.estado(owner, b) == "ABIERTA"


def test_vincular_hecho_no_determinable_rechazado(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    luz = _luz(owner, cta, iber)
    hid = m.x.hecho_motor(owner, [("GASTO", "50.00", "NO_DISPONIBLE", None, [])], fecha="2026-10-03", total=None)
    m.h.como_owner(owner, "UPDATE gapto.hechos_financieros SET importe_total = NULL WHERE id = %s", (hid,))
    base = m.huella(owner)
    _, r = m.vincular(cli, owner, luz, hid, "50.00")
    assert r.status_code == 409 and _cod(r) == "PORCION_DE_REALIDAD_EXCEDIDA"
    assert r.json()["detalle"]["motivo"] == "NO_DETERMINABLE" and m.huella(owner) == base


# ==================================================================
# Naturalezas, desconocido e Inicio
# ==================================================================
def test_naturalezas_separadas_recuento_comun(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    luz = _luz(owner, cta, iber)
    nomina = m.prevision(owner, "Nómina", tipo="INGRESO", desde="2026-09-30", importe="2100.00", cuenta_entrada=cta)
    traspaso = m.prevision(owner, "Nómina → Ahorro", tipo="TRANSFERENCIA", desde="2026-10-02", importe="500.00")
    ini = m.inicio(cli)
    assert ini["requiere_atencion"]["n"] == 3
    assert _ids(ini["requiere_atencion"]["primeras"]) == [nomina, traspaso]  # vencidas por fecha
    assert "importe" not in ini["requiere_atencion"] and "por_pagar" not in ini  # sin importes sumados en Inicio
    p = m.pendientes(cli)
    assert p["n"] == 3
    assert p["por_pagar"] == {"importe": "74.00", "n": 1, "desconocidos": 0}
    assert p["por_cobrar"] == {"importe": "2100.00", "n": 1, "desconocidos": 0}
    assert "total" not in p and set(p) == {"hoy", "n", "por_pagar", "por_cobrar", "secciones", "aviso"}
    naturalezas = {f["id"]: f["naturaleza"] for f in p["secciones"]["vencidas"]}
    assert naturalezas == {str(luz): "POR_PAGAR", str(nomina): "POR_COBRAR", str(traspaso): "ENTRE_CUENTAS"}


def test_importe_desconocido_nunca_cero(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    agua = m.prevision(owner, "Agua", desde="2026-10-05", importe=None, tercero=iber, cuenta_salida=cta)
    d = m.detalle(cli, agua)
    assert d["importe_esperado"] is None and d["queda"] is None
    assert d["acciones"]["swipe"]["disponible"] is False
    assert d["acciones"]["registrar"]["disponible"] is True
    assert m.pendientes(cli)["por_pagar"] == {"importe": None, "n": 1, "desconocidos": 1}
    _, r = m.gasto_desde(cli, owner, cta, agua, "23.10", True)
    assert r.status_code == 200, r.text
    assert m.estado(owner, agua) == "REALIZADA"


def test_inicio_con_0_2_y_3(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    assert m.inicio(cli)["requiere_atencion"] == {"n": 0, "primeras": []}
    a = _luz(owner, cta, iber, hasta="2026-10-03")
    b = _luz(owner, cta, iber, hasta="2026-10-04")
    ini = m.inicio(cli)
    assert ini["requiere_atencion"]["n"] == 2 and _ids(ini["requiere_atencion"]["primeras"]) == [a, b]
    m.prevision(owner, "Seguro", desde="2026-10-20", hasta="2026-10-30", importe="120.00")
    _luz(owner, cta, iber, hasta="2026-10-02")
    ini = m.inicio(cli)
    assert ini["requiere_atencion"]["n"] == 3 and len(ini["requiere_atencion"]["primeras"]) == 2
    assert len(ini["proximos"]) == 1


def test_proximos_tres_por_fecha_e_id(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    fechas = ["2026-11-01", "2026-10-30", "2026-10-15", "2026-12-01"]
    ids = {f: m.prevision(owner, f"P {f}", desde=f, importe="10.00") for f in fechas}
    assert _ids(m.inicio(cli)["proximos"]) == [ids["2026-10-15"], ids["2026-10-30"], ids["2026-11-01"]]


def test_vencida_con_hoy_owner_y_no_utc():
    owner, actor, cli, cta, ahorro = m.entorno("2026-10-09T23:30:00")  # Madrid: 10 oct 01:30
    p = m.prevision(owner, "Luz", desde="2026-10-09", importe="74.00")
    assert m.detalle(cli, p)["vencida"] is True
    assert m.inicio(cli)["requiere_atencion"]["n"] == 1


# ==================================================================
# RODANTE (AJ-M5-DEC-03)
# ==================================================================
def _sucesor_abierto(owner, regla, cabeza):
    cadena = m.previsiones_de_regla(owner, regla)
    return [p for p, e, _ in cadena if e == "ABIERTA" and p != cabeza]


def test_rodante_omitir_crea_sucesor(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    regla, cabeza = m.rodante(owner, cuenta_salida=cta)
    c, r = m.omitir(cli, owner, cabeza)
    assert r.status_code == 200, r.text
    assert _sucesor_abierto(owner, regla, cabeza) == [uuid.uuid5(uuid.UUID(c["intencion_id"]), "sucesor")]


def test_rodante_op17_realiza_y_crea_sucesor_replay_estable(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    regla, cabeza = m.rodante(owner, cuenta_salida=cta)
    hid = m.x.gasto(cli, cta, fecha="2026-10-01", importe="45.00")
    c, r = m.vincular(cli, owner, cabeza, hid, "45.00", True)
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "REALIZADA"
    sucesor = uuid.uuid5(uuid.UUID(c["intencion_id"]), "sucesor")
    assert _sucesor_abierto(owner, regla, cabeza) == [sucesor]
    base = m.huella(owner)
    r2 = cli.post(f"/v1/previsiones/{cabeza}/vincular", json=c, headers=h.AUTH)
    assert r2.status_code == 200 and r2.json()["idempotente"] is True
    assert m.huella(owner) == base and _sucesor_abierto(owner, regla, cabeza) == [sucesor]


def test_rodante_op22_realiza_y_crea_sucesor_replay_estable(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    regla, cabeza = m.rodante(owner, cuenta_salida=cta)
    c, r = m.gasto_desde(cli, owner, cta, cabeza, "45.00", True, fecha="2026-10-01")
    assert r.status_code == 200, r.text
    sucesor = uuid.uuid5(uuid.UUID(c["intencion_id"]), "sucesor")
    assert _sucesor_abierto(owner, regla, cabeza) == [sucesor]
    base = m.huella(owner)
    r2 = cli.post(m.GASTO, json=c, headers=h.AUTH)
    assert r2.status_code == 200 and r2.json()["idempotente"] is True
    assert m.huella(owner) == base and _sucesor_abierto(owner, regla, cabeza) == [sucesor]


# ==================================================================
# Replay compuesto (AJ-M5-DEC-02)
# ==================================================================
def test_replay_op22_exacto_es_idempotente(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    luz = _luz(owner, cta, iber)
    c, r = m.gasto_desde(cli, owner, cta, luz, "81.37", True)
    base = m.huella(owner)
    r2 = cli.post(m.GASTO, json=c, headers=h.AUTH)
    assert r2.status_code == 200 and r2.json()["idempotente"] is True and m.huella(owner) == base


def test_replay_op22_vinculo_ausente(t):
    """El hecho de la intencion existe SIN vinculo: con el bloque no se completa."""
    owner, actor, cli, cta, ahorro, iber, hogar = t
    luz = _luz(owner, cta, iber)
    c, _ = m.gasto_desde(cli, owner, cta, luz, "81.37", True)
    sin = dict(c)
    sin.pop("prevision")
    otra = dict(sin, intencion_id=str(uuid.uuid4()))
    assert cli.post(m.GASTO, json=otra, headers=h.AUTH).status_code == 200
    luz2 = m.prevision(owner, "Luz 2", importe="81.37")
    base = m.huella(owner)
    con = dict(otra, prevision=m.bloque(owner, luz2, True))
    r = cli.post(m.GASTO, json=con, headers=h.AUTH)
    assert r.status_code == 409 and _cod(r) == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert m.huella(owner) == base


def test_replay_op22_vinculo_con_otro_id(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    luz = _luz(owner, cta, iber)
    c = m.h.intencion(cta, importe="81.37", fecha_hecho="2026-10-07")
    assert cli.post(m.GASTO, json=c, headers=h.AUTH).status_code == 200
    m.vincular(cli, owner, luz, c["intencion_id"], "81.37", False)  # vinculo con id = otra intencion
    base = m.huella(owner)
    r = cli.post(m.GASTO, json=dict(c, prevision=m.bloque(owner, luz, False)), headers=h.AUTH)
    assert r.status_code == 409 and _cod(r) == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert m.huella(owner) == base


def test_replay_op22_prevision_distinta(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    a, b = _luz(owner, cta, iber), _luz(owner, cta, iber)
    c, _ = m.gasto_desde(cli, owner, cta, a, "74.00", False)
    base = m.huella(owner)
    r = cli.post(m.GASTO, json=dict(c, prevision=m.bloque(owner, b, False)), headers=h.AUTH)
    assert r.status_code == 409 and _cod(r) == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert m.huella(owner) == base and m.vinculos(owner, b) == []


def test_replay_op22_prevision_modificada_sin_el_vinculo(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    luz = _luz(owner, cta, iber)
    c, _ = m.gasto_desde(cli, owner, cta, luz, "74.00", False)
    vid = uuid.uuid5(uuid.UUID(c["intencion_id"]), "vinculo")
    from app.services.previsiones_service import PrevisionesService

    PrevisionesService(fh.unidad()).retirar_vinculo(m.ctx(owner), vinculo_id=vid, prevision_id_esperada=luz,
                                                    prevision_row_version_esperada=m.version(owner, luz))
    base = m.huella(owner)
    r = cli.post(m.GASTO, json=c, headers=h.AUTH)  # misma intencion: nunca recrea el vinculo
    assert r.status_code == 409 and _cod(r) == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert m.huella(owner) == base and m.vinculos(owner, luz) == []


def test_replay_op17_suelto_otro_contenido(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    luz = _luz(owner, cta, iber)
    h1 = m.x.gasto(cli, cta, fecha="2026-10-03", importe="74.00", tercero_id=iber)
    h2 = m.x.gasto(cli, cta, fecha="2026-10-04", importe="74.00", tercero_id=iber)
    c, r = m.vincular(cli, owner, luz, h1, "74.00", False)
    assert r.status_code == 200
    base = m.huella(owner)
    r2 = cli.post(f"/v1/previsiones/{luz}/vincular", json=dict(c, hecho_id=str(h2), row_version=m.version(owner, luz)),
                  headers=h.AUTH)
    assert r2.status_code == 409 and _cod(r2) == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert m.huella(owner) == base


@pytest.mark.parametrize("caso", ["exacto", "vinculo_ausente", "prevision_distinta", "modificada_sin_vinculo"])
def test_replay_transferencia_prevista(t, caso):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    p = m.prevision(owner, "Nómina → Ahorro", tipo="TRANSFERENCIA", importe="500.00")
    if caso == "vinculo_ausente":
        c = {"intencion_id": str(uuid.uuid4()), "importe": "500.00", "moneda": "EUR", "fecha_hecho": "2026-10-07",
             "cuenta_origen_id": str(cta), "cuenta_destino_id": str(ahorro), "nota": None}
        assert cli.post(m.TRANSF, json=c, headers=h.AUTH).status_code == 200
        c["prevision"] = m.bloque(owner, p, True)
    else:
        c, r = m.transferencia_desde(cli, owner, cta, ahorro, p, "500.00", caso != "modificada_sin_vinculo")
        assert r.status_code == 200, r.text
        if caso == "prevision_distinta":
            c = dict(c, prevision=m.bloque(owner, m.prevision(owner, "Otra", tipo="TRANSFERENCIA", importe="500.00"),
                                           True))
        elif caso == "modificada_sin_vinculo":
            from app.services.previsiones_service import PrevisionesService

            PrevisionesService(fh.unidad()).retirar_vinculo(
                m.ctx(owner), vinculo_id=uuid.uuid5(uuid.UUID(c["intencion_id"]), "vinculo"),
                prevision_id_esperada=p, prevision_row_version_esperada=m.version(owner, p))
    base = m.huella(owner)
    r = cli.post(m.TRANSF, json=c, headers=h.AUTH)
    if caso == "exacto":
        assert r.status_code == 200 and r.json()["idempotente"] is True
    else:
        assert r.status_code == 409 and _cod(r) == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert m.huella(owner) == base


def test_transferencia_sin_bloque_no_reconoce_una_prevista(t):
    """El replay SIN bloque de una intencion materializada CON prevision no es exito."""
    owner, actor, cli, cta, ahorro, iber, hogar = t
    p = m.prevision(owner, "Nómina → Ahorro", tipo="TRANSFERENCIA", importe="500.00")
    c, _ = m.transferencia_desde(cli, owner, cta, ahorro, p, "500.00", True)
    c.pop("prevision")
    r = cli.post(m.TRANSF, json=c, headers=h.AUTH)
    assert r.status_code == 409 and _cod(r) == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"


@pytest.mark.parametrize("ruta", ["gasto", "vincular", "transferencia"])
def test_replay_concurrente_de_la_misma_intencion(t, ruta):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    luz = _luz(owner, cta, iber) if ruta != "transferencia" else m.prevision(owner, "Traspaso", tipo="TRANSFERENCIA",
                                                                             importe="500.00")
    if ruta == "transferencia":
        c = {"intencion_id": str(uuid.uuid4()), "importe": "500.00", "moneda": "EUR", "fecha_hecho": "2026-10-07",
             "cuenta_origen_id": str(cta), "cuenta_destino_id": str(ahorro), "nota": None,
             "prevision": m.bloque(owner, luz, True)}
        url = m.TRANSF
    elif ruta == "gasto":
        c = m.h.intencion(cta, importe="81.37", fecha_hecho="2026-10-07")
        c["prevision"] = m.bloque(owner, luz, True)
        url = m.GASTO
    else:
        hid = m.x.gasto(cli, cta, fecha="2026-10-03", importe="74.00", tercero_id=iber)
        c = {"intencion_id": str(uuid.uuid4()), "row_version": m.version(owner, luz), "hecho_id": str(hid),
             "importe_a_vincular": "74.00", "marcar_realizada": True}
        url = f"/v1/previsiones/{luz}/vincular"
    clientes = [h.cliente(owner, reloj=m.x.reloj()) for _ in range(2)]
    barrera, resp = threading.Barrier(2), []

    def enviar(k):
        barrera.wait()
        resp.append(clientes[k].post(url, json=c, headers=h.AUTH))

    hilos = [threading.Thread(target=enviar, args=(k,)) for k in range(2)]
    [x.start() for x in hilos]
    [x.join() for x in hilos]
    assert sorted(r.status_code for r in resp) == [200, 200], [r.text for r in resp]
    assert len(m.vinculos(owner, luz)) == 1 and m.estado(owner, luz) == "REALIZADA"
    assert sorted(r.json()["idempotente"] for r in resp) == [False, True]


# ==================================================================
# Transferencia por HTTP y prevision + reparto M3
# ==================================================================
def test_transferencia_desde_la_prevision_http(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    p = m.prevision(owner, "Nómina → Ahorro", tipo="TRANSFERENCIA", importe="500.00", cuenta_salida=cta,
                    cuenta_entrada=ahorro)
    antes, s_cta, s_aho = m.resultado(cli), m.saldo(owner, cta), m.saldo(owner, ahorro)
    c, r = m.transferencia_desde(cli, owner, cta, ahorro, p, "500.00", True)
    assert r.status_code == 200, r.text
    assert r.json()["tipo"] == "TRANSFERENCIA"
    assert m.vinculos(owner, p) == [(uuid.UUID(c["intencion_id"]), D("500.0000"))]
    assert m.estado(owner, p) == "REALIZADA" and m.efectos(owner, c["intencion_id"]) == []
    assert (m.saldo(owner, cta) - s_cta, m.saldo(owner, ahorro) - s_aho) == (D("-500"), D("500"))
    assert m.resultado(cli) == antes  # sin efecto economico


def test_transferencia_desde_la_prevision_rollback_conjunto(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    p = m.prevision(owner, "Nómina → Ahorro", tipo="TRANSFERENCIA", importe="500.00")
    base = m.huella(owner)
    _, r = m.transferencia_desde(cli, owner, cta, ahorro, p, "500.00", True, row_version=9)
    assert r.status_code == 409 and _cod(r) == "VERSION_DESFASADA"
    assert m.huella(owner) == base


def test_prevision_con_reparto_m3(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    tania = r3.persona(cli)
    cena = m.prevision(owner, "Cena de grupo", desde="2026-10-09", importe="44.50", tercero=None, cuenta_salida=cta)
    antes = m.resultado(cli)
    c = r3.cuerpo("44.50", pagado_por=r3.con_cuenta(cta), fecha="2026-10-09", nota="Cena",
                  reparto=r3.repartir("29.50", (tania, "15.00", "SI")))
    c["prevision"] = m.bloque(owner, cena, True)
    r = r3.registrar(cli, c)
    assert r.status_code == 200, r.text
    hid = uuid.UUID(c["intencion_id"])
    assert m.vinculos(owner, cena) == [(hid, D("44.5000"))]  # vinculo por importe_total
    assert m.estado(owner, cena) == "REALIZADA"
    assert len(r3.posiciones(owner, hid)) == 1
    # Sin doble conteo: el Resultado cuenta solo mi parte (29,50), una vez; la prevision nada.
    assert _dif(antes, m.resultado(cli))["gastos_propios"] == D("29.50")


def test_prevision_con_reparto_rollback_conjunto(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    tania = r3.persona(cli)
    cena = m.prevision(owner, "Cena", desde="2026-10-09", importe="44.50")
    base = m.huella(owner)
    c = r3.cuerpo("44.50", pagado_por=r3.con_cuenta(cta), fecha="2026-10-09",
                  reparto=r3.repartir("29.50", (tania, "15.00", "SI")))
    c["prevision"] = m.bloque(owner, cena, True, row_version=7)
    r = r3.registrar(cli, c)
    assert r.status_code == 409 and _cod(r) == "VERSION_DESFASADA"
    assert m.huella(owner) == base
    assert m.uno(owner, "SELECT count(*) FROM gapto.derechos_obligaciones_financieras")[0] == 0


# ==================================================================
# Ids de otro owner, tipos y estados excluidos
# ==================================================================
def test_ids_de_otro_owner(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    otro, _, cli_otro, cta_otro, _ = m.entorno()
    ajena = m.prevision(otro, "Ajena")
    hecho_ajeno = m.x.gasto(cli_otro, cta_otro, importe="74.00")
    luz = _luz(owner, cta, iber)
    base = m.huella(owner)
    for r in (cli.get(f"/v1/previsiones/{ajena}", headers=h.AUTH),
              cli.get(f"/v1/previsiones/{ajena}/candidatos", headers=h.AUTH),
              m.vincular(cli, owner, ajena, hecho_ajeno, "74.00", row_version=1)[1],
              m.omitir(cli, owner, ajena, row_version=1)[1],
              m.vincular(cli, owner, luz, hecho_ajeno, "74.00")[1]):
        assert r.status_code == 404 and _cod(r) == "AGREGADO_NO_ENCONTRADO", r.text
    _, r = m.gasto_desde(cli, owner, cta, ajena, "74.00", True, row_version=1)
    assert r.status_code == 404
    assert m.huella(owner) == base


def test_tipo_distinto_rechazado_sin_escritura(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    nomina = m.prevision(owner, "Nómina", tipo="INGRESO", importe="2100.00")
    luz = _luz(owner, cta, iber)
    hid = m.x.ingreso(cli, cta, importe="74.00")
    base = m.huella(owner)
    _, r1 = m.gasto_desde(cli, owner, cta, nomina, "2100.00", True)
    _, r2 = m.vincular(cli, owner, luz, hid, "74.00")
    _, r3_ = m.transferencia_desde(cli, owner, cta, ahorro, luz, "74.00", True)
    for r in (r1, r2, r3_):
        assert r.status_code == 409 and _cod(r) == "PREVISION_TIPO_DISTINTO", r.text
    assert m.huella(owner) == base


def test_vincular_hecho_anulado(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    luz = _luz(owner, cta, iber)
    hid = m.x.gasto(cli, cta, fecha="2026-10-03", importe="74.00", tercero_id=iber)
    m.x.anular(owner, hid)
    _, r = m.vincular(cli, owner, luz, hid, "74.00")
    assert r.status_code == 409 and _cod(r) == "OPERACION_NO_PERMITIDA_EN_ESTADO"
    assert "anulado" in r.json()["mensaje"]


def test_vincular_dos_veces_la_misma_pareja(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    luz = _luz(owner, cta, iber)
    hid = m.x.gasto(cli, cta, fecha="2026-10-03", importe="150.00", tercero_id=iber)
    m.vincular(cli, owner, luz, hid, "150.00", False)
    _, r = m.vincular(cli, owner, luz, hid, "1.00", False)
    assert r.status_code == 409 and _cod(r) == "PREVISION_YA_MATERIALIZADA_POR_ESTA_REALIDAD"


def test_estados_excluidos_visibles_en_detalle_y_fuera_de_listas(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    luz = _luz(owner, cta, iber)
    c, _ = m.gasto_desde(cli, owner, cta, luz, "74.00", True)
    m.x.anular(owner, uuid.UUID(c["intencion_id"]))  # REALIZADA sin realidad ACTIVA
    omitida = _luz(owner, cta, iber)
    m.omitir(cli, owner, omitida)
    d = m.detalle(cli, luz)
    assert (d["estado"], d["estado_derivado"]) == ("REALIZADA", "REALIZADA_SIN_REALIDAD_ACTIVA")
    assert all(not a["disponible"] and a["motivo"] for a in d["acciones"].values())
    assert m.detalle(cli, omitida)["estado"] == "OMITIDA"
    # REQUIERE_REVISION (OMITIDA con realidad ACTIVA): solo por fixture como gapto_owner (ninguna ruta lo produce).
    revision = _luz(owner, cta, iber)
    m.omitir(cli, owner, revision)
    hid = m.x.gasto(cli, cta, fecha="2026-10-03", importe="10.00")
    m.h.como_owner(owner, "INSERT INTO gapto.prevision_hechos (id, prevision_id, hecho_id, importe_asignado) "
                          "VALUES (%s, %s, %s, 10)", (uuid.uuid4(), revision, hid))
    d = m.detalle(cli, revision)
    assert (d["estado"], d["estado_derivado"]) == ("OMITIDA", "REQUIERE_REVISION")
    assert all(not a["disponible"] for a in d["acciones"].values())
    p, ini = m.pendientes(cli), m.inicio(cli)
    listas = p["secciones"]["vencidas"] + p["secciones"]["con_pago_parcial"] + ini["proximos"]
    assert not {str(luz), str(omitida), str(revision)} & {f["id"] for f in listas} and p["n"] == 0


def test_moneda_distinta_sin_acciones(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    usd = m.prevision(owner, "Suscripción", importe="10.00", moneda="USD")
    d = m.detalle(cli, usd)
    assert all(not a["disponible"] and "euros" in a["motivo"] for a in d["acciones"].values())


def test_swipe_solo_con_esperado_cuenta_y_sin_realidad(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    con = _luz(owner, cta, iber)
    sin_cuenta = _luz(owner, None, iber)
    nomina = m.prevision(owner, "Nómina", tipo="INGRESO", importe="2100.00", cuenta_entrada=cta)
    traspaso = m.prevision(owner, "Traspaso", tipo="TRANSFERENCIA", importe="500.00", cuenta_salida=cta,
                           cuenta_entrada=ahorro)
    sw = lambda p: m.detalle(cli, p)["acciones"]["swipe"]["disponible"]  # noqa: E731
    assert (sw(con), sw(sin_cuenta), sw(nomina), sw(traspaso)) == (True, False, True, False)


# ==================================================================
# Candidatos de «Ya lo registre» (AJ-M5-DEC-08)
# ==================================================================
def test_candidatos_filtros_orden_y_sin_preseleccion(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    luz = _luz(owner, cta, iber, hogar)
    otro = m.x.tercero(cli, "Endesa")
    cerca = m.x.gasto(cli, cta, fecha="2026-10-03", importe="76.10", tercero_id=iber)
    por_cat = m.x.gasto(cli, cta, fecha="2026-09-28", importe="12.00", categoria_id=hogar)
    lejos = m.x.gasto(cli, cta, fecha="2026-09-10", importe="20.00", tercero_id=iber)
    m.x.gasto(cli, cta, fecha="2026-10-03", importe="30.00", tercero_id=otro)  # otro tercero y sin categoria
    m.x.ingreso(cli, cta, fecha="2026-10-03", importe="30.00", tercero_id=iber)  # otro tipo
    agotado = m.x.gasto(cli, cta, fecha="2026-10-02", importe="50.00", tercero_id=iber)
    m.vincular(cli, owner, m.prevision(owner, "Otra", importe="50.00"), agotado, "50.00", False)
    ya = m.x.gasto(cli, cta, fecha="2026-10-04", importe="40.00", tercero_id=iber)
    m.vincular(cli, owner, luz, ya, "40.00", False)
    anulado = m.x.gasto(cli, cta, fecha="2026-10-04", importe="40.00", tercero_id=iber)
    m.x.anular(owner, anulado)
    cand = m.candidatos(cli, luz)
    ids = [uuid.UUID(c["hecho_id"]) for c in cand["candidatos"]]
    assert ids == [cerca, por_cat] and cand["ventana_dias"] == 15
    assert {c["porcion_disponible"] for c in cand["candidatos"]} == {"76.10", "12.00"}
    assert all(set(c) == {"hecho_id", "fecha_hecho", "concepto", "tercero", "categoria", "cuenta", "importe_total",
                          "porcion_disponible"} for c in cand["candidatos"])  # sin campo de preseleccion
    amp = m.candidatos(cli, luz, ampliado=True)
    assert [uuid.UUID(c["hecho_id"]) for c in amp["candidatos"]] == [cerca, por_cat, lejos] and amp["ventana_dias"] == 60


def test_candidatos_ampliado_y_vincular_fuera_de_ventana(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    luz = _luz(owner, cta, iber)
    a40 = m.x.gasto(cli, cta, fecha="2026-08-22", importe="74.00", tercero_id=iber)  # 40 dias antes del desde
    a100 = m.x.gasto(cli, cta, fecha="2026-06-23", importe="74.00", tercero_id=iber)
    assert m.candidatos(cli, luz)["candidatos"] == []
    assert [uuid.UUID(c["hecho_id"]) for c in m.candidatos(cli, luz, ampliado=True)["candidatos"]] == [a40]
    _, r = m.vincular(cli, owner, luz, a100, "74.00")  # vincular no aplica la ventana: la autoridad es OP-17
    assert r.status_code == 200, r.text
    assert m.vinculos(owner, luz) == [(a100, D("74.0000"))]


def test_candidatos_sin_tercero_ni_categoria(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    p = m.prevision(owner, "Sin criterio", importe="10.00")
    m.x.gasto(cli, cta, fecha="2026-10-01", importe="10.00")
    cand = m.candidatos(cli, p)
    assert cand["candidatos"] == [] and "no tiene tercero ni categoría" in cand["mensaje"]


def test_candidato_no_determinable_excluido(t):
    owner, actor, cli, cta, ahorro, iber, hogar = t
    luz = _luz(owner, cta, iber)
    hid = m.x.gasto(cli, cta, fecha="2026-10-03", importe="74.00", tercero_id=iber)
    m.h.como_owner(owner, "UPDATE gapto.hechos_financieros SET importe_total = NULL WHERE id = %s", (hid,))
    assert m.candidatos(cli, luz)["candidatos"] == []
