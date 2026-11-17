# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_14o_f06_01h_calculadora.py
# Ruta: tests/backend/test_14o_f06_01h_calculadora.py
# Descripcion: T3-F06 bloque 2 F06-01H · calculadora del cuadro frances anual/12 (contrato v0.4 §2 y §9.1;
#   mandato v1.1 §2.2, §11.1 y §13.3). Comparacion CUOTA A CUOTA contra la fuente independiente del paso 12
#   (tests/api/oraculos_f06h: oraculos.json ab8ec92f… y los CSV con SHA256SUMS.txt), cuyas huellas se
#   verifican antes de usarlos. Oraculos: O-H1 (160.000 €, 2,5 %, 360: cuota 632,19; c1 capital 298,86 interes
#   333,33; Σ intereses 67.590,10; final 0,00), O-H3a (1.200 € al 0 % en 12), O-H3b (1.000 € al 5 % en 1:
#   interes 4,17), O-H3c (100 € al 7 % en 2: cuotas 50,44 y 50,43; capitales 49,86 y 50,14), O-H4 (12 cuotas de
#   O-H1 y despues 2,95 % en 348: pendiente 156.372,35, cuota 669,15, Σ intereses 76.492,02) y O-H18 (empate
#   HALF_UP: 1.001 € al 6 % -> interes 5,005 -> 5,01). Ademas: vencimientos acotados al ultimo dia del mes,
#   CONDICIONES_INCOMPLETAS por sistema, periodicidad y rango, y CUADRO_NO_CUADRA ante un tramo incoherente.
#   La calculadora no importa nada del laboratorio ni cuadro.py (comprobado por AST). Sin base de datos.
# Version: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 4)
# ============================================================

from __future__ import annotations

import ast
import csv
import datetime as dt
import hashlib
import json
import pathlib
import sys
from decimal import Decimal as D

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
if str(RAIZ / "backend") not in sys.path:
    sys.path.insert(0, str(RAIZ / "backend"))

from app.hipotecas import calculadora as calc  # noqa: E402

ORACULOS = RAIZ / "tests" / "api" / "oraculos_f06h"
SHA_ORACULOS_JSON = "ab8ec92f9270da214b87230d90bfaf2e4b740413917996ffa172e815fec5e159"
CSV_USADOS = ("caso1_frances_160000_2.5_360.csv", "caso3a_tasa0_1200_12.csv", "caso3b_una_cuota_1000_5.csv",
              "caso3c_dos_cuotas_residuo_100_7.csv", "caso4_revision_2.95_348.csv")


def _sha(ruta: pathlib.Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _sumas_declaradas() -> dict[str, str]:
    salida = {}
    for linea in (ORACULOS / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines():
        sha, nombre = linea.split(" ", 1)
        salida[nombre.lstrip("*").removeprefix("./")] = sha
    return salida


@pytest.fixture(scope="module")
def oraculos() -> dict:
    assert _sha(ORACULOS / "oraculos.json") == SHA_ORACULOS_JSON
    return json.loads((ORACULOS / "oraculos.json").read_text(encoding="utf-8"))


def _csv(nombre: str) -> list[dict[str, str]]:
    assert _sha(ORACULOS / nombre) == _sumas_declaradas()[nombre], nombre
    with (ORACULOS / nombre).open(encoding="ascii", newline="") as f:
        return list(csv.DictReader(f))


def _igual_cuota_a_cuota(filas: list[calc.Cuota], esperadas: list[dict[str, str]]) -> None:
    assert len(filas) == len(esperadas)
    for f, e in zip(filas, esperadas):
        assert (f.numero, f.cuota, f.interes, f.capital, f.pendiente) == (
            int(e["n"]), D(e["cuota"]), D(e["interes"]), D(e["capital"]), D(e["pendiente"])), (f, e)


def _cuadra(filas: list[calc.Cuota], caso: dict) -> None:
    s = calc.resumen(filas)
    assert s["suma_capital"] == D(caso["sigma_capital"])
    assert s["suma_intereses"] == D(caso["sigma_intereses"])
    assert filas[-1].pendiente == D(caso["pendiente_final"]) == 0
    assert all(f.capital >= 0 and f.interes >= 0 and f.cuota > 0 for f in filas)
    assert all(f.cuota == f.capital + f.interes and f.comision == D("0.00") for f in filas)


def test_fuente_independiente_integra(oraculos) -> None:
    sumas = _sumas_declaradas()
    assert sumas["oraculos.json"] == SHA_ORACULOS_JSON
    for nombre in CSV_USADOS:
        assert _sha(ORACULOS / nombre) == sumas[nombre], nombre
    assert oraculos["discrepancias"] == []


def test_o_h1_frances_160000_25_360(oraculos) -> None:
    caso = oraculos["caso1_frances_160000_2.5_360"]
    filas = calc.cuadro_frances(D("160000.00"), D("2.5"), 360, dt.date(2027, 1, 5))
    _igual_cuota_a_cuota(filas, _csv("caso1_frances_160000_2.5_360.csv"))
    _cuadra(filas, caso)
    assert calc.cuota_francesa(D("160000.00"), D("2.5"), 360) == D("632.19") == D(caso["cuota_1"])
    assert (filas[0].cuota, filas[0].capital, filas[0].interes) == (D("632.19"), D("298.86"), D("333.33"))
    assert calc.resumen(filas)["suma_intereses"] == D("67590.10")
    assert filas[-1].pendiente == D("0.00")
    assert filas[-1].cuota == D("633.89")          # la ultima absorbe el residuo
    assert [f.vencimiento for f in filas[:2]] == [dt.date(2027, 1, 5), dt.date(2027, 2, 5)]
    assert filas[-1].vencimiento == dt.date(2056, 12, 5)


def test_o_h3a_tasa_cero(oraculos) -> None:
    filas = calc.cuadro_frances(D("1200.00"), D("0"), 12)
    _igual_cuota_a_cuota(filas, _csv("caso3a_tasa0_1200_12.csv"))
    _cuadra(filas, oraculos["caso3a_tasa0_1200_12"])
    assert {f.cuota for f in filas} == {D("100.00")} and {f.interes for f in filas} == {D("0.00")}


def test_o_h3b_una_cuota(oraculos) -> None:
    filas = calc.cuadro_frances(D("1000.00"), D("5"), 1)
    _igual_cuota_a_cuota(filas, _csv("caso3b_una_cuota_1000_5.csv"))
    _cuadra(filas, oraculos["caso3b_una_cuota_1000_5"])
    assert (filas[0].interes, filas[0].capital, filas[0].cuota) == (D("4.17"), D("1000.00"), D("1004.17"))


def test_o_h3c_dos_cuotas_con_residuo(oraculos) -> None:
    caso = oraculos["caso3c_dos_cuotas_residuo_100_7"]
    filas = calc.cuadro_frances(D("100.00"), D("7"), 2)
    _igual_cuota_a_cuota(filas, _csv("caso3c_dos_cuotas_residuo_100_7.csv"))
    _cuadra(filas, caso)
    assert [f.cuota for f in filas] == [D(x) for x in caso["cuotas"]] == [D("50.44"), D("50.43")]
    assert [f.capital for f in filas] == [D(x) for x in caso["capitales"]] == [D("49.86"), D("50.14")]


def test_o_h4_revision_tras_12_cuotas(oraculos) -> None:
    caso = oraculos["caso4_revision_2.95_348"]
    o_h1 = calc.cuadro_frances(D("160000.00"), D("2.5"), 360, dt.date(2027, 1, 5))
    pendiente = o_h1[11].pendiente
    assert pendiente == D("156372.35") == D(caso["pendiente_tras_12"])
    restantes = o_h1[12:]
    tramo = calc.tramo_desde(pendiente, D("2.95"), [f.numero for f in restantes], [f.vencimiento for f in restantes])
    _igual_cuota_a_cuota(tramo, _csv("caso4_revision_2.95_348.csv"))
    _cuadra(tramo, caso)
    assert tramo[0].cuota == D("669.15") == D(caso["cuota_nueva"])
    assert calc.resumen(tramo)["suma_intereses"] == D("76492.02")
    assert [f.vencimiento for f in tramo] == [f.vencimiento for f in restantes]   # numeros y fechas existentes


def test_o_h18_empate_half_up() -> None:
    filas = calc.cuadro_frances(D("1001.00"), D("6"), 1)
    assert filas[0].interes == D("5.01")           # 1001 * 0,005 = 5,005 -> HALF_UP 5,01 (HALF_EVEN daria 5,00)
    assert (filas[0].capital, filas[0].cuota) == (D("1001.00"), D("1006.01"))


def test_tasa_del_periodo_es_anual_entre_12() -> None:
    from decimal import localcontext
    with localcontext() as ctx:
        ctx.prec = 50
        assert calc.tasa_periodo(D("2.5")) == D("2.5") / D(1200)
    assert calc.tasa_periodo(D("6")) == D("0.005")
    assert calc.tasa_periodo(D("2.5")).adjusted() == -3 and len(calc.tasa_periodo(D("2.5")).as_tuple().digits) == 50


@pytest.mark.parametrize("primera, esperados", [
    (dt.date(2027, 1, 31), [dt.date(2027, 1, 31), dt.date(2027, 2, 28), dt.date(2027, 3, 31), dt.date(2027, 4, 30)]),
    (dt.date(2027, 12, 30), [dt.date(2027, 12, 30), dt.date(2028, 1, 30), dt.date(2028, 2, 29), dt.date(2028, 3, 30)]),
    (dt.date(2027, 3, 15), [dt.date(2027, 3, 15), dt.date(2027, 4, 15), dt.date(2027, 5, 15), dt.date(2027, 6, 15)]),
])
def test_vencimientos_acotados_al_ultimo_dia_del_mes(primera, esperados) -> None:
    filas = calc.cuadro_frances(D("400.00"), D("3"), 4, primera)
    assert [f.vencimiento for f in filas] == esperados


@pytest.mark.parametrize("kw, motivo", [
    ({"sistema": "LINEAL"}, calc.SISTEMA_NO_SOPORTADO),
    ({"periodicidad": "SEMANAL"}, calc.PERIODICIDAD_NO_SOPORTADA),
    ({"periodicidad": "ANUAL"}, calc.PERIODICIDAD_NO_SOPORTADA),
    ({"sistema": "LINEAL", "periodicidad": "ANUAL"}, calc.PERIODICIDAD_NO_SOPORTADA),
])
def test_condiciones_no_soportadas(kw, motivo) -> None:
    with pytest.raises(calc.CondicionesIncompletas) as e:
        calc.cuadro_frances(D("1000.00"), D("3"), 12, **kw)
    assert (e.value.codigo, e.value.motivo) == ("CONDICIONES_INCOMPLETAS", motivo)


@pytest.mark.parametrize("capital, tasa, n", [
    (D("0"), D("3"), 12), (D("-1.00"), D("3"), 12), (D("10.001"), D("3"), 12), (D("1000.00"), D("-0.1"), 12),
    (D("1000.00"), D("30.000001"), 12), (D("1000.00"), D("3"), 0), (D("1000.00"), D("3"), 601),
    (D("1000.00"), D("3.0000001"), 12),
])
def test_valores_fuera_de_rango(capital, tasa, n) -> None:
    with pytest.raises(calc.CondicionesIncompletas) as e:
        calc.cuadro_frances(capital, tasa, n)
    assert e.value.motivo == calc.VALORES_FUERA_DE_RANGO


def test_cuadro_no_cuadra_es_defecto() -> None:
    with pytest.raises(calc.CuadroNoCuadra) as e:
        calc.tramo_desde(D("100.005"), D("3"), [1, 2], [None, None])    # pendiente fuera de centimos
    assert e.value.codigo == "CUADRO_NO_CUADRA"
    with pytest.raises(calc.CuadroNoCuadra):
        calc.tramo_desde(D("100.00"), D("3"), [1, 2], [None])           # tramo incoherente
    with pytest.raises(calc.CuadroNoCuadra):
        calc.tramo_desde(D("0"), D("3"), [1], [None])


def test_la_calculadora_no_importa_el_laboratorio_ni_cuadro_py() -> None:
    fuente = (RAIZ / "backend" / "app" / "hipotecas" / "calculadora.py").read_text(encoding="utf-8")
    modulos = set()
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.Import):
            modulos |= {a.name for a in nodo.names}
        elif isinstance(nodo, ast.ImportFrom):
            modulos.add(nodo.module or "")
    assert modulos <= {"__future__", "calendar", "datetime", "dataclasses", "decimal", "typing"}, modulos
