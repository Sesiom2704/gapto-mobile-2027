# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_189_f05_05_resultado_mes.py
# Ruta: tests/api/test_189_f05_05_resultado_mes.py
# Descripcion: Read models de Inicio (K2 §1.6; F05 §49.4 A9, D13, M5-06;
#   AJ-F0505-03). Dominio RESULTADO. Dos oraculos:
#   (1) contraste con GET /v1/vs01/gasto-mes sobre datos de los writers
#       reales de F05 (SOLO_MIO / SIN_INDICAR: los unicos estados que F05
#       captura): gastos_propios == gasto_atribuible y sin_indicar.gastos.n ==
#       gastos_sin_reparto, en varios meses (caso 25);
#   (2) bateria independiente con fixtures controladas (OP-22 donde F05 no
#       captura) y valores calculados A MANO en el propio test desde hechos,
#       efectos y atribuciones: atribucion 0 explicita, PARCIAL con resto,
#       NO_DISPONIBLE, devolucion (GASTO negativo), reembolso (DERECHO_COBRO,
#       fuera), gasto repercutido (DERECHO_COBRO fuera), transferencia (0),
#       hecho con dos efectos (cuenta una vez en «sin indicar»), otra moneda
#       (fuera), dia 1 y ultimo dia (limites), mes anterior y siguiente
#       (fuera), prevision (fuera) (casos 26 y 32).
#   Ademas: «Hola» (caso 27), 00:30 en Madrid del dia 1, FECHA_FUTURA y
#   aislamiento. Nunca se ajusta el test al resultado.
#   Nota (D-RE-1): con efectos PARCIAL, A9 cuenta la parte propia atribuida y
#   gasto-mes (VS-01) no; por eso el oraculo (1) usa solo datos que F05 captura.
# Version: 0.1.0 (F05-05 K2 §1.6)
# Version: 0.2.0 (F05-05 K3 §3, mutantes RE05/RE06): hechos anulados fuera de
#   todas las cifras; un hecho con DOS efectos pendientes cuenta UNA vez en
#   «Sin indicar» (con la suma de los dos importes).
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid

import pytest

import f05_01_helpers as fh
import f05_05_helpers as x
import vs01_api_helpers as h

URL = "/v1/inicio/resultado-mes"
D = decimal.Decimal


def resultado(cli, fecha="2026-10-10"):
    r = cli.get(URL, params={"fecha": fecha}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def test_oraculo1_contraste_con_gasto_mes_en_varios_meses():
    owner, actor, cli, cta, ahorro = x.entorno("2026-12-15T12:00:00")
    cat = x.categoria(owner, "Varios")
    for mes, gastos in (("2026-09", [("12.30", "SOLO_MIO"), ("8.00", "SIN_INDICAR"), ("40.10", "SOLO_MIO")]),
                        ("2026-10", [("5.55", "SIN_INDICAR"), ("7.45", "SIN_INDICAR"), ("100.00", "SOLO_MIO")]),
                        ("2026-11", [("3.00", "SOLO_MIO")])):
        for i, (importe, atrib) in enumerate(gastos):
            x.gasto(cli, cta, fecha=f"{mes}-{10 + i}", importe=importe, atribucion=atrib, categoria_id=cat)
        x.ingreso(cli, cta, fecha=f"{mes}-05", importe="1000.00")
        x.transferencia(cli, cta, ahorro, fecha=f"{mes}-06")
    for mes in ("2026-09", "2026-10", "2026-11"):
        r = resultado(cli, f"{mes}-15")
        vs01 = cli.get("/v1/vs01/gasto-mes", params={"mes": mes}, headers=h.AUTH).json()
        assert r["mes"] == mes
        assert r["gastos_propios"] == vs01["gasto_atribuible"], (mes, r, vs01)
        assert r["sin_indicar"]["gastos"]["n"] == vs01["gastos_sin_reparto"], (mes, r, vs01)


def test_oraculo2_bateria_calculada_a_mano():
    owner, actor, cli, cta, ahorro = x.entorno()
    otro = h.crear_actor_tercero(owner)
    a, b = x.categoria(owner, "A"), x.categoria(owner, "B")
    # ---- dentro de octubre de 2026 (fecha funcional 2026-10-10)
    x.gasto(cli, cta, fecha="2026-10-05", importe="30.00", atribucion="SOLO_MIO")             # G1: +30 propio
    x.hecho_motor(owner, [("GASTO", "12.00", "COMPLETA", None, [(otro, "12.00")])])          # G2: atribucion 0 propia
    x.hecho_motor(owner, [("GASTO", "90.00", "PARCIAL", None, [(actor, "30.00"), (otro, "20.00")])])  # G3: +30, pendiente 40
    x.gasto(cli, cta, fecha="2026-10-06", importe="44.50", atribucion="SIN_INDICAR")          # G4: pendiente 44.50
    x.hecho_motor(owner, [("GASTO", "-10.00", "COMPLETA", None, [(actor, "-10.00")])], total="10.00")  # G5: devolucion -10
    x.hecho_motor(owner, [("DERECHO_COBRO", "-15.00", "COMPLETA", None, [(actor, "-15.00")])], tipo="REEMBOLSO",
                  total="15.00")                                                               # G6: reembolso, fuera
    x.hecho_motor(owner, [("GASTO", "40.00", "COMPLETA", a, [(actor, "40.00")]),
                          ("DERECHO_COBRO", "40.00", "COMPLETA", None, [(actor, "40.00")])], total="40.00")  # G7: +40; derecho fuera
    x.transferencia(cli, cta, ahorro, fecha="2026-10-07")                                     # G8: 0
    x.hecho_motor(owner, [("GASTO", "10.00", "COMPLETA", a, [(actor, "10.00")]),
                          ("GASTO", "5.00", "PARCIAL", b, [(actor, "2.00"), (otro, "1.00")])])  # G9: +12, pendiente 2
    x.hecho_motor(owner, [("GASTO", "100.00", "COMPLETA", None, [(actor, "100.00")])], moneda="USD")  # G10: otra moneda
    x.gasto(cli, cta, fecha="2026-10-01", importe="7.00")                                    # G11: dia 1, +7
    x.hecho_motor(owner, [("GASTO", "3.00", "COMPLETA", None, [(actor, "3.00")])], fecha="2026-10-31")  # G12: ultimo dia, +3
    x.ingreso(cli, cta, fecha="2026-10-02", importe="1000.00", atribucion="SOLO_MIO")         # I1: +1000
    x.ingreso(cli, cta, fecha="2026-10-03", importe="200.00", atribucion="SIN_INDICAR")       # I2: pendiente 200
    # ---- fuera del mes
    x.gasto(cli, cta, fecha="2026-09-30", importe="999.00")
    x.hecho_motor(owner, [("GASTO", "888.00", "COMPLETA", None, [(actor, "888.00")])], fecha="2026-11-01")
    _prevision(owner, "2026-10-20", "77.00")
    gastos = D("30") + D("0") + D("30") - D("10") + D("40") + D("12") + D("7") + D("3")
    ingresos = D("1000")
    esperado = {
        "mes": "2026-10", "moneda": "EUR",
        "gastos_propios": f"{gastos:.2f}", "ingresos_propios": f"{ingresos:.2f}",
        "resultado": f"{ingresos - gastos:.2f}",
        "sin_indicar": {"gastos": {"n": 3, "importe": f"{D('40') + D('44.50') + D('2'):.2f}"},
                        "ingresos": {"n": 1, "importe": "200.00"}},
    }
    assert esperado["gastos_propios"] == "112.00" and esperado["resultado"] == "888.00"  # aritmetica del test
    assert resultado(cli) == esperado


def _prevision(owner, fecha, importe):
    from app.core.contexto import ContextoOperacion
    from app.core.modelos_prevision import DatosPrevisionManual
    from app.services.previsiones_service import PrevisionesService

    f = dt.date.fromisoformat(fecha)
    datos = DatosPrevisionManual(prevision_id=uuid.uuid4(), concepto="luz", tipo_hecho_codigo="GASTO",
                                 fecha_esperada_desde=f, fecha_esperada_hasta=f, flujo_tesoreria_esperado="SALIDA",
                                 moneda="EUR", presupuestable=True, importe_esperado=D(importe))
    PrevisionesService(fh.unidad()).crear_manual(ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4()), datos)


def test_mes_vacio_y_solo_transferencias():
    owner, actor, cli, cta, ahorro = x.entorno()
    vacio = {"gastos": {"n": 0, "importe": "0.00"}, "ingresos": {"n": 0, "importe": "0.00"}}
    assert resultado(cli) == {"mes": "2026-10", "moneda": "EUR", "ingresos_propios": "0.00", "gastos_propios": "0.00",
                              "resultado": "0.00", "sin_indicar": vacio}
    x.transferencia(cli, cta, ahorro)
    assert resultado(cli)["resultado"] == "0.00" and resultado(cli)["sin_indicar"] == vacio


def test_resultado_negativo():
    owner, actor, cli, cta, _ = x.entorno()
    x.gasto(cli, cta, importe="50.00")
    x.ingreso(cli, cta, importe="20.00")
    assert resultado(cli)["resultado"] == "-30.00"


def test_medianoche_en_madrid_del_dia_1():
    """A las 00:30 del 1 de noviembre en Madrid (aun 31 de octubre en UTC) la
    fecha funcional del cliente es 2026-11-01: el mes es noviembre y no es
    futura."""
    owner, actor, cli, cta, _ = x.entorno("2026-10-31T23:30:00")
    x.gasto(cli, cta, fecha="2026-11-01", importe="9.00")
    x.gasto(cli, cta, fecha="2026-10-31", importe="1.00")
    r = resultado(cli, "2026-11-01")
    assert (r["mes"], r["gastos_propios"]) == ("2026-11", "9.00")


def test_fecha_futura():
    owner, actor, cli, cta, _ = x.entorno()
    r = cli.get(URL, params={"fecha": "2026-10-11"}, headers=h.AUTH)
    assert r.status_code == 422 and r.json()["codigo"] == "FECHA_FUTURA"
    assert cli.get(URL, headers=h.AUTH).status_code == 422  # fecha obligatoria


def test_caso27_hola_con_el_nombre_del_owner_y_aislamiento():
    owner, actor, cli, cta, _ = x.entorno()
    h.como_owner(owner, "UPDATE gapto.usuarios SET nombre='Moisés' WHERE id=%s", (owner,))
    assert cli.get("/v1/yo", headers=h.AUTH).json() == {"nombre": "Moisés"}
    owner_b, _, cli_b, cta_b, _ = x.entorno()
    x.gasto(cli_b, cta_b, importe="500.00")
    assert cli_b.get("/v1/yo", headers=h.AUTH).json() == {"nombre": "VS-01 test"}
    assert resultado(cli)["gastos_propios"] == "0.00"  # los hechos de B no cuentan para A


# ------------------------------------------------------------------ K3 §3: refuerzo (mutantes)
def test_hechos_anulados_fuera_de_todas_las_cifras():
    owner, actor, cli, cta, _ = x.entorno()
    x.gasto(cli, cta, importe="10.00")
    x.anular(owner, x.gasto(cli, cta, importe="99.00"))
    x.anular(owner, x.gasto(cli, cta, importe="7.00", atribucion="SIN_INDICAR"))
    x.anular(owner, x.ingreso(cli, cta, importe="500.00"))
    r = resultado(cli)
    assert (r["gastos_propios"], r["ingresos_propios"], r["resultado"]) == ("10.00", "0.00", "-10.00")
    assert r["sin_indicar"]["gastos"] == {"n": 0, "importe": "0.00"}


def test_dos_efectos_pendientes_de_un_hecho_cuentan_una_vez():
    owner, actor, cli, cta, _ = x.entorno()
    a, b = x.categoria(owner, "A"), x.categoria(owner, "B")
    x.hecho_motor(owner, [("GASTO", "4.00", "NO_DISPONIBLE", a, []), ("GASTO", "6.00", "NO_DISPONIBLE", b, [])])
    assert resultado(cli)["sin_indicar"]["gastos"] == {"n": 1, "importe": "10.00"}
