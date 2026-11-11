# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_lanzador_gate.py
# Ruta: tests/gates/test_lanzador_gate.py
# Descripcion: Pruebas reales del lanzador N1 de gates (scripts/gates/lanzador_gate.py; Paso 0 del N1 de 0352,
#   C1 del dictamen de cierre de B1 v1.1, punto 9). Cada prueba crea un repositorio git temporal con un commit,
#   ejecuta el lanzador como proceso aparte y comprueba su resultado real: caso positivo (VERDE, rc 0, copia
#   intacta); pytest que falla (rc != 0, ROJO, junit concordante); «replay» que falla (rc real del script, no el
#   de un comando posterior); arbol modificado durante la ejecucion (INVALIDADA y marcador); arnes de mutantes
#   activo en la raiz de un worktree y en un directorio de diario externo (STOP_CERROJO sin copia); evidencia
#   existente (no se sobrescribe); copia fiel al commit (cambios sin commit del worktree no entran). Sin base
#   de datos.
# Version: 0.1.0 (F03 · N1 de 0352, Paso 0)
# ============================================================
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time

LANZADOR = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "gates" / "lanzador_gate.py"


def git(repo: pathlib.Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), "-c", "user.name=prueba", "-c", "user.email=prueba@example.invalid",
                        "-c", "core.autocrlf=false", *args], capture_output=True, text=True, check=True)
    return r.stdout.strip()


def repo_con(tmp: pathlib.Path, ficheros: dict[str, str]) -> tuple[pathlib.Path, str]:
    repo = tmp / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    for ruta, texto in ficheros.items():
        p = repo / ruta
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    return repo, git(repo, "rev-parse", "HEAD")


def lanzar(tmp: pathlib.Path, plan: dict, salida: str = "salida") -> tuple[int, pathlib.Path]:
    fplan = tmp / f"plan_{salida}.json"
    fplan.write_text(json.dumps(plan), encoding="utf-8")
    r = subprocess.run([sys.executable, str(LANZADOR), "--plan", str(fplan), "--salida", str(tmp / salida)], capture_output=True, text=True)
    return r.returncode, tmp / salida


def resultado(salida: pathlib.Path) -> dict:
    return json.loads((salida / "resultado.json").read_text(encoding="utf-8"))


OK = {"tests/test_ok.py": "def test_ok():\n    assert 1 + 1 == 2\n"}
FALLA = {"tests/test_falla.py": "def test_falla_a_proposito():\n    assert 1 == 2\n"}
REPLAY_FALLA = {"replay.py": "import sys\nprint('replay: base inexistente')\nsys.exit(3)\n"}


def test_positivo_verde_rc0_copia_intacta(tmp_path):
    repo, c = repo_con(tmp_path, {**OK, "replay.py": "print('ok')\n"})
    rc, sal = lanzar(tmp_path, {"repo": str(repo), "commit": c, "pasos": [
        {"etiqueta": "replay", "tipo": "script", "args": ["{PYTHON}", "replay.py"]},
        {"etiqueta": "suite", "tipo": "pytest", "args": ["tests", "-q"]},
        {"etiqueta": "huellas", "tipo": "verificacion", "args": ["{PYTHON}", "-c", "print('huellas ok')"]}]})
    r = resultado(sal)
    assert rc == 0 and r["veredicto"] == "VERDE"
    assert [p["rc"] for p in r["pasos"]] == [0, 0, 0]
    assert [p["tipo"] for p in r["pasos"]] == ["script", "pytest", "verificacion"]
    assert r["pasos"][1]["junit"]["passed"] == 1 and r["pasos"][1]["coherente"] is True
    assert all(p["copia_intacta"] for p in r["pasos"])
    assert not (sal / "EJECUCION_INVALIDADA.txt").exists()


def test_pytest_que_falla_rc_distinto_de_cero_y_rojo(tmp_path):
    repo, c = repo_con(tmp_path, {**OK, **FALLA})
    rc, sal = lanzar(tmp_path, {"repo": str(repo), "commit": c, "pasos": [{"etiqueta": "suite", "tipo": "pytest", "args": ["tests", "-q"]}]})
    r = resultado(sal)
    assert rc == 1 and r["veredicto"] == "ROJO"
    p = r["pasos"][0]
    assert p["rc"] == 1
    assert p["junit"]["failures"] == 1 and p["junit"]["passed"] == 1 and p["coherente"] is True
    assert "suite fin" in (sal / "tiempos.txt").read_text(encoding="utf-8") and "rc=1" in (sal / "tiempos.txt").read_text(encoding="utf-8")


def test_replay_que_falla_registra_su_rc_real_y_sigue_en_rojo(tmp_path):
    repo, c = repo_con(tmp_path, {**OK, **REPLAY_FALLA})
    rc, sal = lanzar(tmp_path, {"repo": str(repo), "commit": c, "pasos": [
        {"etiqueta": "replay", "tipo": "script", "args": ["{PYTHON}", "replay.py"]},
        {"etiqueta": "completar", "tipo": "script", "args": ["{PYTHON}", "-c", "print('completar')"]}]})
    r = resultado(sal)
    assert rc == 1 and r["veredicto"] == "ROJO"
    assert [p["rc"] for p in r["pasos"]] == [3, 0]
    t = (sal / "tiempos.txt").read_text(encoding="utf-8")
    assert "replay fin" in t and "tipo=script rc=3" in t      # el rc del script, no el de `date`


def test_parar_si_falla_no_ejecuta_los_pasos_siguientes(tmp_path):
    repo, c = repo_con(tmp_path, {**OK, **REPLAY_FALLA})
    rc, sal = lanzar(tmp_path, {"repo": str(repo), "commit": c, "pasos": [
        {"etiqueta": "replay", "tipo": "script", "args": ["{PYTHON}", "replay.py"], "parar_si_falla": True},
        {"etiqueta": "suite", "tipo": "pytest", "args": ["tests", "-q"]}]})
    r = resultado(sal)
    assert rc == 1 and [p["etiqueta"] for p in r["pasos"]] == ["replay"]


def test_arbol_modificado_durante_la_ejecucion_invalida(tmp_path):
    lento = {"tests/test_lento.py": "import time\n\ndef test_lento():\n    time.sleep(4)\n"}
    repo, c = repo_con(tmp_path, {**OK, **lento, "app/modulo.py": "VALOR = 1\n"})
    fplan = tmp_path / "plan.json"
    fplan.write_text(json.dumps({"repo": str(repo), "commit": c, "pasos": [{"etiqueta": "suite", "tipo": "pytest", "args": ["tests", "-q"]}]}), encoding="utf-8")
    sal = tmp_path / "salida"
    proc = subprocess.Popen([sys.executable, str(LANZADOR), "--plan", str(fplan), "--salida", str(sal)])
    objetivo = sal / "copia" / "app" / "modulo.py"
    limite = time.time() + 30
    while time.time() < limite:   # espera a que la suite este corriendo sobre la copia
        if (sal / "tiempos.txt").exists() and "suite inicio" in (sal / "tiempos.txt").read_text(encoding="utf-8"):
            break
        time.sleep(0.1)
    objetivo.write_text("VALOR = 2  # otro proceso modifica la copia\n", encoding="utf-8")
    assert proc.wait(timeout=60) == 2
    r = resultado(sal)
    assert r["veredicto"] == "INVALIDADA"
    marcador = (sal / "EJECUCION_INVALIDADA.txt").read_text(encoding="utf-8")
    assert "cambiado app/modulo.py" in marcador


def test_modificacion_revertida_dentro_del_paso_tambien_invalida(tmp_path):
    # mismo contenido final pero otro mtime: la instantanea incluye el mtime
    script = ("import pathlib, time\np = pathlib.Path('app/modulo.py')\nt = p.read_text()\np.write_text('X = 9\\n')\n"
              "time.sleep(0.05)\np.write_text(t)\n")
    repo, c = repo_con(tmp_path, {"app/modulo.py": "VALOR = 1\n", "tocar.py": script})
    rc, sal = lanzar(tmp_path, {"repo": str(repo), "commit": c, "pasos": [{"etiqueta": "toca", "tipo": "script", "args": ["{PYTHON}", "tocar.py"]}]})
    assert rc == 2 and resultado(sal)["veredicto"] == "INVALIDADA"


def test_cerrojo_marcador_de_arnes_en_la_raiz_del_worktree(tmp_path):
    repo, c = repo_con(tmp_path, OK)
    (repo / ".mutante_f06_01_b1_en_curso").write_text("backend/app/x.py\n00", encoding="ascii")
    rc, sal = lanzar(tmp_path, {"repo": str(repo), "commit": c, "pasos": [{"etiqueta": "suite", "tipo": "pytest", "args": ["tests"]}]})
    r = resultado(sal)
    assert rc == 3 and r["veredicto"] == "STOP_CERROJO" and r["pasos"] == []
    assert not (sal / "copia").exists()


def test_cerrojo_journal_de_mutantes_dev_en_la_raiz(tmp_path):
    repo, c = repo_con(tmp_path, OK)
    (repo / ".mutantes_f04_r3.journal.json").write_text("{}", encoding="ascii")
    rc, sal = lanzar(tmp_path, {"repo": str(repo), "commit": c, "pasos": [{"etiqueta": "suite", "tipo": "pytest", "args": ["tests"]}]})
    assert rc == 3 and resultado(sal)["veredicto"] == "STOP_CERROJO"


def test_cerrojo_journal_en_directorio_de_diario_externo(tmp_path):
    repo, c = repo_con(tmp_path, OK)
    diario = tmp_path / "diario_f03_06_0352"
    diario.mkdir()
    (diario / "journal_en_sitio.json").write_text("{}", encoding="ascii")
    rc, sal = lanzar(tmp_path, {"repo": str(repo), "commit": c, "diarios": [str(diario)], "pasos": [{"etiqueta": "suite", "tipo": "pytest", "args": ["tests"]}]})
    r = resultado(sal)
    assert rc == 3 and r["veredicto"] == "STOP_CERROJO" and any("journal_en_sitio.json" in x for x in r["cerrojo"])


def test_cerrojo_en_otro_worktree_del_mismo_repositorio(tmp_path):
    repo, c = repo_con(tmp_path, OK)
    otro = tmp_path / "otro_wt"
    git(repo, "worktree", "add", "-q", str(otro), c)
    (otro / ".mutante_activo").write_text("x", encoding="ascii")
    rc, sal = lanzar(tmp_path, {"repo": str(repo), "commit": c, "pasos": [{"etiqueta": "suite", "tipo": "pytest", "args": ["tests"]}]})
    assert rc == 3 and resultado(sal)["veredicto"] == "STOP_CERROJO"


def test_evidencia_existente_no_se_sobrescribe(tmp_path):
    repo, c = repo_con(tmp_path, OK)
    (tmp_path / "salida").mkdir()
    (tmp_path / "salida" / "previo.txt").write_text("evidencia anterior", encoding="utf-8")
    rc, sal = lanzar(tmp_path, {"repo": str(repo), "commit": c, "pasos": []})
    assert rc == 4
    assert (sal / "previo.txt").read_text(encoding="utf-8") == "evidencia anterior"
    assert not (sal / "resultado.json").exists()


def test_plan_ilegible_es_error_de_preparacion_no_rojo(tmp_path):
    fplan = tmp_path / "plan_roto.json"
    fplan.write_text('{"repo": "C:\\DEV\\x", "commit": "abc", "pasos": []}', encoding="utf-8")   # escape invalido
    r = subprocess.run([sys.executable, str(LANZADOR), "--plan", str(fplan), "--salida", str(tmp_path / "salida")], capture_output=True, text=True)
    assert r.returncode == 4 and "plan ilegible" in r.stderr
    assert not (tmp_path / "salida").exists()


def test_la_copia_es_el_commit_no_el_worktree(tmp_path):
    repo, c = repo_con(tmp_path, {**OK, "app/modulo.py": "VALOR = 1\n"})
    (repo / "app" / "modulo.py").write_text("VALOR = 999  # sin commit\n", encoding="utf-8")
    (repo / "sin_versionar.py").write_text("x = 1\n", encoding="utf-8")
    rc, sal = lanzar(tmp_path, {"repo": str(repo), "commit": c, "pasos": [
        {"etiqueta": "lee", "tipo": "verificacion", "args": ["{PYTHON}", "-c", "import pathlib,sys; sys.exit(0 if pathlib.Path('app/modulo.py').read_text()=='VALOR = 1\\n' and not pathlib.Path('sin_versionar.py').exists() else 7)"]}]})
    assert rc == 0 and resultado(sal)["pasos"][0]["rc"] == 0


def test_secretos_heredados_no_se_escriben_en_la_evidencia(tmp_path, monkeypatch):
    repo, c = repo_con(tmp_path, OK)
    # DSN ficticia montada en ejecucion: el texto del fichero no debe parecer una credencial (test_rv3_000)
    monkeypatch.setenv("GAPTO_SECRETO_PRUEBA", "postgresql://" + "u" + ":" + "clave-que-no-debe-salir" + "@h/db")
    rc, sal = lanzar(tmp_path, {"repo": str(repo), "commit": c, "pasos": [
        {"etiqueta": "usa", "tipo": "verificacion", "heredar": ["GAPTO_SECRETO_PRUEBA"],
         "args": ["{PYTHON}", "-c", "import os,sys; sys.exit(0 if os.environ['GAPTO_SECRETO_PRUEBA'].startswith('postgresql://') else 5)"]}]})
    assert rc == 0
    for f in sal.glob("*"):
        if f.is_file():
            assert "clave-que-no-debe-salir" not in f.read_text(encoding="utf-8", errors="replace"), f.name


def test_las_variables_gapto_del_entorno_no_se_filtran_salvo_heredadas(tmp_path, monkeypatch):
    repo, c = repo_con(tmp_path, OK)
    monkeypatch.setenv("GAPTO_TEST_DATABASE_URL", "postgresql://no-debe-llegar")
    rc, sal = lanzar(tmp_path, {"repo": str(repo), "commit": c, "pasos": [
        {"etiqueta": "env", "tipo": "verificacion", "args": ["{PYTHON}", "-c", "import os,sys; sys.exit(6 if 'GAPTO_TEST_DATABASE_URL' in os.environ else 0)"]}]})
    assert rc == 0
