# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_comparador_normalizado.py
# Ruta: tests/gates/test_comparador_normalizado.py
# Descripcion: Pruebas sin base de datos del comparador normalizado de constraints
#   (scripts/gates/comparar_constraints_normalizado.py; AJ-T3C-06). Casos P1-P10 del borrador v0.1 §2 y P11-P13 de
#   la decision 16 (N1 con «<op> ANY/ALL»), sobre extracciones fijas escritas en tmp_path:
#     P1  par real de los 2 CHECK de la restauracion del bloque 1 -> IGUAL_NORMALIZADO (N1), exactamente esos 2
#     P2  definiciones identicas -> IGUAL_LITERAL
#     P3  valor del ARRAY cambiado (tambien en mayusculas o con espacios dentro del literal) -> DIFERENCIA_SEMANTICA
#     P4  elemento anadido o quitado -> DIFERENCIA_SEMANTICA
#     P5  orden de elementos cambiado (en la forma restaurada o en la original) -> DIFERENCIA_SEMANTICA
#     P6  operador cambiado, NOT anadido o agrupacion de parentesis cambiada -> DIFERENCIA_SEMANTICA
#     P7  columna distinta -> DIFERENCIA_SEMANTICA
#     P8  cast final distinto (text[] -> varchar[]), tipo base distinto o tipos base mixtos (fuera de N1)
#         -> DIFERENCIA_SEMANTICA
#     P9  constraint que falta o que sobra -> DIFERENCIA_SEMANTICA
#     P10 DEFERRABLE / NOT VALID cambiados (en el texto o en los atributos) -> DIFERENCIA_SEMANTICA
#     P11 «=» <-> «<>» delante del cuantificador con el ARRAY en las dos formas -> DIFERENCIA_SEMANTICA
#     P12 «ANY» <-> «ALL» con el ARRAY en las dos formas -> DIFERENCIA_SEMANTICA
#     P13 par real de ck_mapeos_importacion__destino_exigido («<> ALL») -> IGUAL_NORMALIZADO (N1)
#   Ademas: N2 y N3 por separado, formato de texto de varias lineas y CLI (rc y h2 literal copiada sin cambios).
#   El arnes scripts/mutantes/mant_t3_comparador_h2.py ejecuta este fichero contra copias mutadas del
#   comparador (variable GAPTO_COMPARADOR_RUTA); sin ella se usa el del arbol.
# Version: 1.0.0 (F06 — T3 · MANT N1 del comparador normalizado de constraints h2; decisiones 15 y 16)
# ============================================================
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import subprocess
import sys

import pytest

RUTA = pathlib.Path(os.environ.get("GAPTO_COMPARADOR_RUTA") or
                    pathlib.Path(__file__).resolve().parents[2] / "scripts" / "gates" / "comparar_constraints_normalizado.py")
_spec = importlib.util.spec_from_file_location("comparador_normalizado", RUTA)
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)

# --- pares reales (bloque 1 11_c7_restauracion y C7 0354 8b) -----------------------------------------------
MODO_REF = ("CHECK (((modo_reparto IS NULL) OR ((modo_reparto)::text = ANY ((ARRAY['FIJO'::character varying, "
            "'POR_FACTURA'::character varying])::text[]))))")
MODO_RES = ("CHECK (((modo_reparto IS NULL) OR ((modo_reparto)::text = ANY (ARRAY[('FIJO'::character varying)::text, "
            "('POR_FACTURA'::character varying)::text]))))")
CAUSA_REF = ("CHECK (((causa_valor_activo IS NULL) OR ((causa_valor_activo)::text = ANY ((ARRAY['ADQUISICION'::character "
             "varying, 'TRANSFORMACION_CAPITALIZABLE'::character varying, 'BAJA_TOTAL'::character varying, "
             "'BAJA_PARCIAL'::character varying, 'REDUCCION_ESTRUCTURAL'::character varying])::text[]))))")
CAUSA_RES = ("CHECK (((causa_valor_activo IS NULL) OR ((causa_valor_activo)::text = ANY (ARRAY[('ADQUISICION'::character "
             "varying)::text, ('TRANSFORMACION_CAPITALIZABLE'::character varying)::text, ('BAJA_TOTAL'::character "
             "varying)::text, ('BAJA_PARCIAL'::character varying)::text, ('REDUCCION_ESTRUCTURAL'::character "
             "varying)::text]))))")
MAPEO_VIRGEN = ("CHECK ((((tipo_mapping)::text <> ALL ((ARRAY['CREADO'::character varying, 'VINCULADO'::character varying, "
                "'FUSIONADO'::character varying, 'DIVIDIDO'::character varying])::text[])) OR ((tabla_destino IS NOT NULL) "
                "AND (registro_destino_id IS NOT NULL))))")
MAPEO_ENVDEV = ("CHECK ((((tipo_mapping)::text <> ALL (ARRAY[('CREADO'::character varying)::text, ('VINCULADO'::character "
                "varying)::text, ('FUSIONADO'::character varying)::text, ('DIVIDIDO'::character varying)::text])) OR "
                "((tabla_destino IS NOT NULL) AND (registro_destino_id IS NOT NULL))))")
OTRA = "CHECK ((orden >= 0))"
N_MODO = "gapto.contrato_servicios.ck_contrato_servicios__modo_reparto_dominio"
N_CAUSA = "gapto.hecho_efectos.ck_hecho_efectos__causa_valor_activo_dominio"
N_MAPEO = "gapto.mapeos_importacion.ck_mapeos_importacion__destino_exigido"
N_OTRA = "gapto.acciones_rapidas.ck_acciones_rapidas__orden_no_negativo"


def _json(tmp_path, nombre, datos) -> pathlib.Path:
    p = tmp_path / nombre
    p.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return p


def comparar(tmp_path, a: dict, b: dict) -> dict:
    """Pasa por disco (formato JSON objeto) como en uso real."""
    return C.comparar(C.cargar(_json(tmp_path, "a.json", a)), C.cargar(_json(tmp_path, "b.json", b)))


def par(tmp_path, da: str, db: str) -> dict:
    return comparar(tmp_path, {N_MODO: da, N_OTRA: OTRA}, {N_MODO: db, N_OTRA: OTRA})


def semantica(r: dict) -> bool:
    return r["veredicto"] == "DIFERENCIA_SEMANTICA" and r["n_diferencia_semantica"] >= 1


# ---------------------------------------------------------------- P1, P2, P13

def test_p1_par_real_del_bloque_1_es_igual_normalizado_n1_con_exactamente_esos_2(tmp_path):
    r = comparar(tmp_path, {N_MODO: MODO_REF, N_CAUSA: CAUSA_REF, N_OTRA: OTRA},
                 {N_MODO: MODO_RES, N_CAUSA: CAUSA_RES, N_OTRA: OTRA})
    assert r["veredicto"] == "IGUAL_NORMALIZADO"
    assert r["igual_normalizado"] == [{"constraint": N_MODO, "reglas": ["N1"]}, {"constraint": N_CAUSA, "reglas": ["N1"]}]
    assert r["n_igual_literal"] == 1 and r["n_diferencia_semantica"] == 0
    filas = {f["constraint"]: f for f in r["filas"]}
    assert filas[N_MODO]["igual_literal"] is False and filas[N_MODO]["igual_normalizado"] is True


def test_p2_definiciones_identicas_son_igual_literal(tmp_path):
    r = comparar(tmp_path, {N_MODO: MODO_REF, N_OTRA: OTRA}, {N_MODO: MODO_REF, N_OTRA: OTRA})
    assert r["veredicto"] == "IGUAL_LITERAL" and r["n_igual_literal"] == 2 and r["igual_normalizado"] == []


def test_p13_par_real_de_destino_exigido_con_distinto_de_all_es_igual_normalizado_n1(tmp_path):
    r = comparar(tmp_path, {N_MAPEO: MAPEO_VIRGEN}, {N_MAPEO: MAPEO_ENVDEV})
    assert r["veredicto"] == "IGUAL_NORMALIZADO"
    assert r["igual_normalizado"] == [{"constraint": N_MAPEO, "reglas": ["N1"]}]


# ---------------------------------------------------------------- P3..P12 (deben seguir detectando)

@pytest.mark.parametrize("forma_b", [MODO_RES, MODO_REF], ids=["b_restaurada", "b_original"])
@pytest.mark.parametrize("cambio", [("'POR_FACTURA'", "'POR_FACTURB'"), ("'FIJO'", "'fijo'"),
                                    ("'POR_FACTURA'", "'POR FACTURA'")], ids=["valor", "mayusculas", "espacio_en_literal"])
def test_p3_valor_del_array_cambiado_es_diferencia_semantica(tmp_path, forma_b, cambio):
    assert semantica(par(tmp_path, MODO_REF, forma_b.replace(*cambio)))


def test_p3b_espacio_dentro_del_literal_frente_a_sin_espacio(tmp_path):
    a = MODO_REF.replace("'POR_FACTURA'", "'POR FACTURA'")
    b = MODO_RES.replace("'POR_FACTURA'", "'PORFACTURA'")
    assert semantica(par(tmp_path, a, b))


@pytest.mark.parametrize("b", [
    MODO_RES.replace(", ('POR_FACTURA'::character varying)::text", ""),
    MODO_RES.replace("::text]", "::text, ('OTRO'::character varying)::text]"),
], ids=["quitado", "anadido"])
def test_p4_elemento_anadido_o_quitado_es_diferencia_semantica(tmp_path, b):
    assert semantica(par(tmp_path, MODO_REF, b))


def test_p5_orden_cambiado_es_diferencia_semantica(tmp_path):
    b = ("CHECK (((modo_reparto IS NULL) OR ((modo_reparto)::text = ANY (ARRAY[('POR_FACTURA'::character varying)::text, "
         "('FIJO'::character varying)::text]))))")
    assert semantica(par(tmp_path, MODO_REF, b))


def test_p5b_orden_cambiado_en_la_forma_original_es_diferencia_semantica(tmp_path):
    a = ("CHECK (((modo_reparto IS NULL) OR ((modo_reparto)::text = ANY ((ARRAY['POR_FACTURA'::character varying, "
         "'FIJO'::character varying])::text[]))))")
    assert semantica(par(tmp_path, a, MODO_RES))


@pytest.mark.parametrize("a,b", [
    (MODO_REF, MODO_RES.replace("::text = ANY", "::text <> ANY")),
    (MODO_REF, MODO_RES.replace("OR ((modo_reparto)", "OR (NOT (modo_reparto)")),
    ("CHECK ((((a IS NULL) OR (b = 1)) AND (c = 2)))", "CHECK (((a IS NULL) OR ((b = 1) AND (c = 2))))"),
    ("CHECK ((orden >= 0))", "CHECK ((orden > 0))"),
], ids=["igual_a_distinto", "not_anadido", "agrupacion", "mayor_igual_a_mayor"])
def test_p6_operador_not_o_agrupacion_cambiados_es_diferencia_semantica(tmp_path, a, b):
    assert semantica(par(tmp_path, a, b))


def test_p7_columna_distinta_es_diferencia_semantica(tmp_path):
    assert semantica(par(tmp_path, MODO_REF, MODO_RES.replace("(modo_reparto)::text", "(modo_cobro)::text")))


@pytest.mark.parametrize("a,b", [
    (MODO_REF, MODO_REF.replace("])::text[]", "])::character varying[]")),
    (MODO_REF, MODO_RES.replace("::character varying)::text", "::character varying)::character varying")),
    (MODO_REF, MODO_RES.replace("::character varying)::text", "::text)::text")),
    (MODO_REF.replace("'POR_FACTURA'::character varying", "'POR_FACTURA'::text"),
     MODO_RES.replace("('POR_FACTURA'::character varying)", "('POR_FACTURA'::text)")),
], ids=["cast_final_literal", "cast_final_restaurada", "tipo_base", "tipos_base_mixtos_fuera_de_n1"])
def test_p8_cast_final_o_tipo_base_distinto_es_diferencia_semantica(tmp_path, a, b):
    assert semantica(par(tmp_path, a, b))


@pytest.mark.parametrize("lado", ["falta", "sobra"])
def test_p9_constraint_que_falta_o_sobra_es_diferencia_semantica(tmp_path, lado):
    completo = {N_MODO: MODO_REF, N_OTRA: OTRA}
    parcial = {N_MODO: MODO_REF}
    r = comparar(tmp_path, completo, parcial) if lado == "falta" else comparar(tmp_path, parcial, completo)
    assert semantica(r)
    assert r["diferencia_semantica"][0]["constraint"] == N_OTRA


@pytest.mark.parametrize("a,b", [
    ("FOREIGN KEY (x) REFERENCES gapto.t(id) DEFERRABLE INITIALLY DEFERRED", "FOREIGN KEY (x) REFERENCES gapto.t(id)"),
    ("FOREIGN KEY (x) REFERENCES gapto.t(id) DEFERRABLE", "FOREIGN KEY (x) REFERENCES gapto.t(id) DEFERRABLE INITIALLY DEFERRED"),
    ("CHECK ((orden >= 0))", "CHECK ((orden >= 0)) NOT VALID"),
], ids=["deferrable_quitado", "initially_deferred", "not_valid"])
def test_p10_deferrable_o_not_valid_cambiados_en_el_texto_es_diferencia_semantica(tmp_path, a, b):
    assert semantica(par(tmp_path, a, b))


def test_p10b_atributos_deferrable_distintos_con_el_mismo_texto_es_diferencia_semantica(tmp_path):
    defin = "CONSTRAINT TRIGGER x"
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text(f"gapto.t.trg_x|t|t|t|{defin}\n", encoding="utf-8")
    b.write_text(f"gapto.t.trg_x|t|t|f|{defin}\n", encoding="utf-8")
    r = C.comparar(C.cargar(a), C.cargar(b))
    assert semantica(r) and "deferred" in r["diferencia_semantica"][0]["motivo"]


@pytest.mark.parametrize("a,b", [
    (MODO_REF, MODO_RES.replace("::text = ANY", "::text <> ANY")),
    (MAPEO_VIRGEN, MAPEO_ENVDEV.replace("::text <> ALL", "::text = ALL")),
    (MAPEO_VIRGEN.replace("::text <> ALL", "::text = ALL"), MAPEO_ENVDEV),
], ids=["igual_any_a_distinto_any", "distinto_all_a_igual_all", "igual_all_a_distinto_all"])
def test_p11_operador_cambiado_delante_del_cuantificador_es_diferencia_semantica(tmp_path, a, b):
    assert semantica(par(tmp_path, a, b))


@pytest.mark.parametrize("a,b", [
    (MODO_REF, MODO_RES.replace("= ANY", "= ALL")),
    (MAPEO_VIRGEN, MAPEO_ENVDEV.replace("<> ALL", "<> ANY")),
    (MAPEO_VIRGEN.replace("<> ALL", "<> ANY"), MAPEO_ENVDEV),
], ids=["any_a_all", "all_a_any_restaurada", "all_a_any_original"])
def test_p12_cuantificador_cambiado_es_diferencia_semantica(tmp_path, a, b):
    assert semantica(par(tmp_path, a, b))


# ---------------------------------------------------------------- N2, N3 y entrada

def test_n2_parentesis_alrededor_de_un_unico_operando(tmp_path):
    r = par(tmp_path, "CHECK (((modo_reparto)::text <> ''::text))", "CHECK ((modo_reparto::text <> ''::text))")
    assert r["veredicto"] == "IGUAL_NORMALIZADO" and r["igual_normalizado"][0]["reglas"] == ["N2"]


def test_n2_no_quita_los_parentesis_de_una_llamada(tmp_path):
    assert semantica(par(tmp_path, "CHECK ((lower(nombre) <> ''::text))", "CHECK ((lowernombre <> ''::text))"))


def test_n3_espacios_fuera_de_literales(tmp_path):
    r = par(tmp_path, "CHECK ((orden >= 0))", "CHECK ((orden  >=  0))")
    assert r["veredicto"] == "IGUAL_NORMALIZADO" and r["igual_normalizado"][0]["reglas"] == ["N3"]


def test_formato_texto_de_varias_lineas(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text("gapto.t.ck_a|c|f|f|CHECK ((((\nCASE\n    WHEN (x IS NOT NULL) THEN 1\n    ELSE 0\nEND) = 1)))\n"
                 "gapto.t.ck_b|c|f|f|CHECK ((y > 0))\n", encoding="utf-8")
    d = C.cargar(p)
    assert list(d) == ["gapto.t.ck_a", "gapto.t.ck_b"]
    assert d["gapto.t.ck_a"]["definicion"].count("\n") == 4 and d["gapto.t.ck_a"]["tipo"] == "c"


def test_cli_rc_y_h2_literal_copiada_sin_cambios(tmp_path):
    a = _json(tmp_path, "a.json", {N_MODO: MODO_REF})
    b = _json(tmp_path, "b.json", {N_MODO: MODO_RES})
    huellas = {"h2": {"observada": "70d5f5f7", "referencia": "f73b3905", "igual": False}}
    h = _json(tmp_path, "huellas.json", huellas)
    salida = tmp_path / "s.json"
    r = subprocess.run([sys.executable, str(RUTA), "--a", str(a), "--b", str(b), "--huellas", str(h),
                        "--salida", str(salida)], capture_output=True, text=True)
    assert r.returncode == 0
    res = json.loads(salida.read_text(encoding="utf-8"))
    assert res["veredicto"] == "IGUAL_NORMALIZADO" and res["huellas_d111_literales"][str(h)] == huellas
    b2 = _json(tmp_path, "b2.json", {N_MODO: MODO_RES.replace("'FIJO'", "'FIJA'")})
    r = subprocess.run([sys.executable, str(RUTA), "--a", str(a), "--b", str(b2)], capture_output=True, text=True)
    assert r.returncode == 1
