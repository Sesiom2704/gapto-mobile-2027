# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_258_f06_01_b3_inventarios.py
# Ruta: tests/api/test_258_f06_01_b3_inventarios.py
# Descripcion: F06 T1-F06 · B3 N1 · inventarios estaticos (sin base de datos):
#   - M-ID-08 (E-3; N1-RF2-14): ningun writer de backend/app hace UPDATE de `id` en hecho_entidades ni en
#     hecho_efectos (las identidades selladas son inmutables);
#   - E-1 / O5.34 (§IV.1, D1): el modulo de C-MEJ-03 no importa ni referencia CorreccionesService ni sus pasos
#     internos; es el UNICO writer de `hechos_financieros.tipo_hecho_id` fuera del motor F04 y solo dentro de la
#     correccion agregada;
#   - procedencia (v0.9 §III.3.2, opcion b): los prefijos de rol `gapto.f06.gasto_propiedad.` y
#     `gapto.f06.mejora_historica.` solo aparecen en los modulos de B3 (gasto_propiedad.py y correccion_clase.py);
#   - Parte IV-bis (reserva de PROPIEDAD; O10.23 de B3): ninguna ruta, adaptador ni modulo de B3 expone OP-21 ni
#     OP-03 (no importa correcciones_service, hechos_service ni anulacion_tesoreria_service) y las rutas de B3 son
#     exactamente las siete declaradas;
#   - consumidores de 0352: B3 no escribe las columnas de completitud ni cambia la habilitacion (O10.29 sigue).
# Version: 0.1.0 (F06 T1-F06 B3 N1)
# ============================================================

from __future__ import annotations

import ast
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[2]
APP = RAIZ / "backend" / "app"
MODULOS_B3 = ("patrimonio/gasto_propiedad.py", "patrimonio/correccion_clase.py", "patrimonio/rutas_b3.py",
              "patrimonio/dto_b3.py")


def _python() -> dict[str, str]:
    return {str(p.relative_to(APP)).replace("\\", "/"): p.read_text(encoding="utf-8")
            for p in APP.rglob("*.py") if "__pycache__" not in p.parts}


def _sql_literales(fuente: str) -> list[str]:
    arbol = ast.parse(fuente)
    return [n.value for n in ast.walk(arbol) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def test_m_id_08_ningun_writer_actualiza_el_id_de_vinculos_ni_efectos():
    patron = re.compile(r"UPDATE\s+gapto\.(hecho_entidades|hecho_efectos)\b[^;]*?\bSET\b(?P<set>.*?)(\bWHERE\b|$)",
                        re.IGNORECASE | re.DOTALL)
    culpables = []
    for ruta, fuente in _python().items():
        texto = " ".join(_sql_literales(fuente))
        for m in patron.finditer(texto):
            columnas = [c.split("=")[0].strip().lower() for c in m.group("set").split(",")]
            if "id" in columnas:
                culpables.append(ruta)
    assert culpables == []


def test_e1_c_mej_03_sin_correcciones_service_y_unico_writer_de_tipo_hecho():
    fuentes = _python()
    cc = fuentes["patrimonio/correccion_clase.py"]
    arbol = ast.parse(cc)
    nombres = {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)} | {
        a.name for n in ast.walk(arbol) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names} | {
        n.module or "" for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)}
    assert not any("correcciones_service" in n or n == "CorreccionesService" for n in nombres)
    for privado in ("_eliminar_atribuciones", "_eliminar_vinculos_de_efecto", "_eliminar_efectos", "corregir"):
        assert privado not in nombres
    writers = sorted(r for r, f in fuentes.items()
                     if re.search(r"SET\s+tipo_hecho_id\s*=", " ".join(_sql_literales(f)), re.IGNORECASE))
    assert writers == ["patrimonio/correccion_clase.py"]


def test_prefijos_de_procedencia_solo_en_los_modulos_de_b3():
    for prefijo in ("gapto.f06.gasto_propiedad.", "gapto.f06.mejora_historica.", "gapto.f06.cmej03."):
        usos = sorted(r for r, f in _python().items() if prefijo in f)
        assert set(usos) <= {"patrimonio/gasto_propiedad.py", "patrimonio/correccion_clase.py"}, (prefijo, usos)
    assert "gapto.f06.gasto_propiedad." in _python()["patrimonio/gasto_propiedad.py"]


def test_parte_iv_bis_b3_no_expone_op21_ni_op03():
    prohibidos = ("correcciones_service", "hechos_service", "anulacion_tesoreria_service", "correccion_tesoreria_service",
                  "ejecucion_correccion", "ejecucion_anulacion", "ejecucion_reparto", "ejecucion_categoria_v3")
    for modulo in MODULOS_B3:
        fuente = (APP / modulo).read_text(encoding="utf-8")
        arbol = ast.parse(fuente)
        importados = {n.module or "" for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)} | {
            a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
        assert not any(p in m for m in importados for p in prohibidos), (modulo, importados)
    rutas = re.findall(r'@app\.(get|post)\("([^"]+)"', (APP / "patrimonio/rutas_b3.py").read_text(encoding="utf-8"))
    assert sorted(rutas) == sorted([
        ("post", "/v1/intenciones/gasto-propiedad"),
        ("post", "/v1/propiedades/{propiedad_id}/mejoras-historicas"),
        ("post", "/v1/propiedades/{propiedad_id}/gastos/{hecho_id}/corregir-clase"),
        ("get", "/v1/propiedades/{propiedad_id}/propuesta-gasto"),
        ("get", "/v1/propiedades/{propiedad_id}/gastos"),
        ("get", "/v1/propiedades/{propiedad_id}/gastos/{hecho_id}"),
        ("get", "/v1/propiedades/{propiedad_id}/gastos/{hecho_id}/impacto-correccion"),
    ])


def test_b3_no_escribe_la_completitud_ni_habilita_consumidores_0352():
    for modulo in MODULOS_B3:
        fuente = (APP / modulo).read_text(encoding="utf-8")
        assert "escribir_declaracion_completitud" not in fuente and "CONSUMIDORES_0352_HABILITADOS" not in fuente
        assert "habilitacion" not in fuente
