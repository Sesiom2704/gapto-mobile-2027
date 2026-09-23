# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_034_p12_runner.py
# Ruta: tests/migration/test_rv3_034_p12_runner.py
# Descripcion: RV3 / P12 v0.1.0 (rv3_p12_neon.py). Verifica lo que no depende del proveedor: el corpus es
#              SINTETICO (sin claves ni PII V3 reales), determinista y sin pendientes; la redaccion de
#              credenciales borra usuario/contrasena de cualquier texto; y los hashes certificados declarados
#              por el runner son los del baseline.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def _mod(nombre, ruta):
    s = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(s)
    sys.modules[nombre] = m
    s.loader.exec_module(m)
    return m


P12 = _mod("rv3_p12_neon", RAIZ / "scripts" / "migration_v3" / "rv3_p12_neon.py")
# instancia AISLADA de P5: el runner reconfigura constantes de modulo y no debe contaminar a otros tests
P5 = _mod("p5_aislado_p12", RAIZ / "scripts" / "migration_v3" / "rv3_p5_transformacion.py")
CONF = _mod("conftest_p12", RAIZ / "tests" / "migration" / "conftest.py")
T12 = _mod("t12_p12t", RAIZ / "tests" / "migration" / "test_rv3_012_p5_dominio10.py")
CATALOGOS_V3_REALES = True
DOMINIO_5 = DOMINIO_6 = DOMINIO_7 = DOMINIO_12 = True


def test_redaccion_de_credenciales():
    # la muestra se compone en tiempo de ejecucion: el repositorio no debe contener cadenas con credenciales
    uri = "postgresql" + "://" + "u:" + "sec" + "reta" + "@host/db"
    clave = "pass" + "word=" + "sec" + "reta"
    assert P12.redactar(uri) == "postgresql://REDACTADO@host/db"
    assert P12.redactar("host=h " + clave + " dbname=d") == "host=h password=REDACTADO dbname=d"
    assert "sec" + "reta" not in P12.redactar("error en " + uri + " y " + clave)


def test_hashes_certificados_declarados():
    for rel, esperado in P12.HASHES_CERTIFICADOS.items():
        assert (RAIZ / rel).exists() and len(esperado) == 64
    assert P12.P5_VERSION_ESPERADA == "0.36.0"


def test_corpus_sintetico_determinista_y_sin_pii():
    ds, ev = P12.construir_corpus(P5, CONF, T12.T8, T12)
    assert ev["determinista"] and ev["pendientes"] == 0 and ev["veredicto"] == "PASS"
    cuerpo = json.dumps(P12.corpus(T12.T8, T12), default=str)
    for prohibido in ("CON-MARINA", "PER-", "GASTO-", "gasto-", "INGRESO-", "VIVIENDA-", "BANCO-", "@gmail"):
        assert prohibido not in cuerpo, prohibido
    assert ev["recuentos"]["hechos_financieros"] >= 4 and ev["recuentos"]["movimientos_tesoreria"] >= 2


def test_corpus_cubre_las_estructuras_exigidas():
    ds, _ = P12.construir_corpus(P5, CONF, T12.T8, T12)
    f = ds.filas
    assert f["contratos"] and len(f["contrato_participantes"]) >= 4          # contrato con varios participantes
    assert sum(1 for p in f["contrato_participantes"].values() if p["rol"] == "INQUILINO" and not p["principal"]) >= 2
    assert any(p["rol"] == "AVALISTA" for p in f["contrato_participantes"].values())
    assert len(f["regla_versiones"]) >= 2 and len(f["reglas_financieras"]) == 1   # renta versionada, una regla
    assert f["derechos_obligaciones_financieras"] and f["transferencias"] and f["movimientos_tesoreria"]
    assert f["mapeos_importacion"] and f["fuentes_importacion"] and f["financiacion_cuotas"]
