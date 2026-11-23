# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_316_f06_t4_token_rotacion_aislamiento.py
# Ruta: tests/api/test_316_f06_t4_token_rotacion_aislamiento.py
# Descripcion: F06 T4 · token BETA_LOCAL (mandato 4f0e40af... par. 3 y par. 2.7;
#   dictamen AJ-TOK-03, AJ-TOK-07 caso E). Sin cambios de contrato del backend.
#   - Rotacion por HTTP (Bearer con compare_digest): con el backend en el token
#     A, A -> 200 y sin cabecera -> 401; "reiniciado" con el token B (app nueva
#     con la configuracion nueva), A -> 401, B -> 200, sin cabecera -> 401 y un
#     prefijo de B -> 401. Tokens generados en el momento (secrets), nunca fijos.
#   - scripts/dev/rotar_token_dev.ps1: genera >= 32 caracteres del alfabeto sin
#     ambiguos, distinto del anterior; en .env sustituye solo su linea; en
#     fichero plano escribe solo el token; NO imprime el valor ni lo registra;
#     una longitud menor de 32 falla sin tocar el destino.
#   - Aislamiento del secreto: ni el token valido ni uno invalido aparecen en
#     el JSONL de peticiones de AJ-05, en los logs del backend (caplog, DEBUG)
#     ni en la salida capturada, tampoco en un 401 ni en un 404.
# Version: 0.1.0 (F06 T4 token BETA_LOCAL)
# ============================================================
from __future__ import annotations

import logging
import pathlib
import re
import secrets
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

import aj05_helpers as aj
import vs01_api_helpers as h
from app.api.app import create_app

RAIZ = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "scripts" / "dev" / "rotar_token_dev.ps1"
ALFABETO = set("abcdefghjkmnpqrstuvwxyz23456789")


def _token() -> str:
    return "t316-" + secrets.token_urlsafe(32)


def _app(owner, token: str, **kw) -> TestClient:
    return TestClient(create_app(h.configuracion(owner, GAPTO_DEV_TOKEN=token), **kw), raise_server_exceptions=False)


def _salud(cli: TestClient, token: str | None) -> int:
    cab = {} if token is None else {"Authorization": f"Bearer {token}"}
    return cli.get("/v1/salud", headers=cab).status_code


# ---------------------------------------------------------------- rotacion por HTTP
def test_rotacion_token_antiguo_401_nuevo_200_sin_token_401():
    owner, _ = h.crear_tenant()
    a, b = _token(), _token()
    antes = _app(owner, a)
    assert _salud(antes, a) == 200
    assert _salud(antes, None) == 401
    assert _salud(antes, b) == 401
    despues = _app(owner, b)  # el backend reiniciado con la configuracion nueva
    assert _salud(despues, a) == 401
    assert _salud(despues, b) == 200
    assert _salud(despues, None) == 401
    assert _salud(despues, b[:-1]) == 401
    r = despues.get("/v1/salud", headers={"Authorization": f"Bearer {a}"})
    assert r.json()["codigo"] == "NO_AUTORIZADO"
    assert a not in r.text and b not in r.text


# ---------------------------------------------------------------- script de rotacion
def _rotar(destino: pathlib.Path, registro: pathlib.Path | None = None, *extra: str) -> subprocess.CompletedProcess:
    args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), "-Destino", str(destino)]
    if registro is not None:
        args += ["-Registro", str(registro)]
    return subprocess.run(args + list(extra), capture_output=True, text=True, timeout=120)


pytestmark_ps = pytest.mark.skipif(sys.platform != "win32", reason="rotar_token_dev.ps1 es de Windows (ENV-DEV)")


@pytestmark_ps
def test_script_rota_la_linea_del_env_sin_mostrar_ni_registrar_el_valor(tmp_path):
    env = tmp_path / "backend.env"
    viejo = "viejo-" + secrets.token_hex(16)
    env.write_text(f"OTRA=1\nGAPTO_DEV_TOKEN={viejo}\nZ=2\n", encoding="utf-8")
    reg = tmp_path / "rotacion.log"
    r = _rotar(env, reg)
    assert r.returncode == 0, r.stderr
    lineas = env.read_text(encoding="utf-8").splitlines()
    assert lineas[0] == "OTRA=1" and lineas[2] == "Z=2" and len(lineas) == 3
    nuevo = lineas[1].split("=", 1)[1]
    assert lineas[1].startswith("GAPTO_DEV_TOKEN=")
    assert len(nuevo) >= 32 and set(nuevo) <= ALFABETO and nuevo != viejo
    salida = r.stdout + r.stderr
    registro = reg.read_text(encoding="ascii")
    assert nuevo not in salida and viejo not in salida
    assert nuevo not in registro and viejo not in registro
    assert "resultado=ROTADO" in registro and "longitud=40" in registro and "valor=NO_REGISTRADO" in registro
    assert not list(tmp_path.glob(".rotar_*"))


@pytestmark_ps
def test_script_fichero_plano_y_dos_rotaciones_distintas(tmp_path):
    f = tmp_path / "dev_token.txt"
    f.write_text("anterior-" + secrets.token_hex(16) + "\n", encoding="ascii")
    assert _rotar(f).returncode == 0
    uno = f.read_text(encoding="utf-8").strip()
    assert _rotar(f, None, "-Longitud", "48").returncode == 0
    dos = f.read_text(encoding="utf-8").strip()
    assert len(uno) == 40 and len(dos) == 48 and uno != dos
    assert set(uno) <= ALFABETO and set(dos) <= ALFABETO
    assert re.fullmatch(r"[a-z0-9]+", dos)


@pytestmark_ps
def test_script_longitud_menor_de_32_falla_sin_tocar_el_destino(tmp_path):
    f = tmp_path / "dev_token.txt"
    original = "intacto-" + secrets.token_hex(16) + "\n"
    f.write_text(original, encoding="ascii")
    r = _rotar(f, None, "-Longitud", "31")
    assert r.returncode != 0
    assert f.read_text(encoding="ascii") == original


# ---------------------------------------------------------------- aislamiento del secreto (caso E)
def test_el_token_no_aparece_en_jsonl_logs_ni_salida(tmp_path, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    owner, _ = h.crear_tenant()
    valido, invalido = _token(), _token()
    reg = aj.registro(tmp_path / "logs")
    cli = _app(owner, valido, registro=reg)
    assert _salud(cli, valido) == 200
    assert _salud(cli, invalido) == 401
    assert cli.get("/v1/no-existe", headers={"Authorization": f"Bearer {valido}"}).status_code == 404
    assert cli.get("/v1/yo", headers={"Authorization": f"Bearer {invalido}"}).status_code == 401
    jsonl = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "logs").glob("*.jsonl"))
    assert jsonl.count('"evento": "TERMINADA"') + jsonl.count('"evento":"TERMINADA"') >= 4
    salida = capsys.readouterr()
    for secreto in (valido, invalido):
        assert secreto not in jsonl
        assert secreto not in caplog.text
        assert secreto not in salida.out and secreto not in salida.err
    assert "Bearer" not in jsonl and "authorization" not in jsonl.lower()
