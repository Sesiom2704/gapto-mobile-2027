# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_mant_vinculo.py
# Ruta: scripts/dev/mutantes_mant_vinculo.py
# Descripcion: Arnes de mutacion de MANT DEU-F04-VINCULO-ANULADO: la guarda de
#   PrevisionesService.corregir_vinculo que, al corregir solo el importe
#   asignado (sin cambiar de hecho), lee el estado del hecho vinculado.
#     MUT-MANT-01 se quita la guarda (`if False:`).
#   Discriminantes: tests/backend/test_14g_mant_vinculo_anulado.py y
#   tests/backend/test_14h_mant_vinculo_concurrencia_serial.py (serie).
#   Procede de dos arneses historicos identicos salvo rutas (HUECO-05):
#     - C:/DEV/evidencia_mant_vinculo/mutante_mant.py (raiz cableada
#       worktree wt_mant_vinculo);
#     - C:/DEV/evidencia_f04_r2_rec/p5/mutante_mant_rec.py (copia del anterior
#       sobre el worktree wt_f04_r2_rec para el recierre F04-R2 P5).
#   Mismo mutante, mismo texto protegido y mismos discriminantes: en el
#   repositorio quedan consolidados en este unico arnes.
#   Motor (D-181, D-192, D-193, WM 12C.2): sustitucion de texto exacto (UNA
#   ocurrencia), journal durable antes del primer byte (si al arrancar hay uno
#   pendiente: restaura, verifica y aborta), preflight verde, restauracion
#   verificada por SHA-256 y veredicto MUERTO | VIVO | NO_CLASIFICABLE.
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable> GAPTO_MANT_VINCULO_CONCURRENCIA=1
#        python scripts/dev/mutantes_mant_vinculo.py
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (MANT DEU-F04-VINCULO-ANULADO, fuera del repo: evidencia_mant_vinculo;
#   copia F04-R2 RECIERRE P5 en evidencia_f04_r2_rec/p5)
# Version: 0.2.0 (F05-07/GATE adenda 2, MANT-PRE-GATE arneses, HUECO-05; F05
#   §63.6 (1)): pasa a scripts/dev/; la raiz se deduce del propio fichero y el
#   journal vive en la raiz del repo; consolida mutante_mant.py y
#   mutante_mant_rec.py. El texto protegido sigue anclando en 5e39673
#   (previsiones_service.py): sin reanclaje.
# Version: 0.2.1 (F05-07/GATE adenda 2, integracion MANT-PRE-GATE: la cabecera nombra los
#   worktrees historicos sin ruta absoluta (test_rv3_000, ruta_absoluta_windows))
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_mant_vinculo.journal.json"

F = "backend/app/services/previsiones_service.py"
TEXTO = ("            if nuevo_importe is not None and nuevo_hecho_id is None:\n"
         "                estado_actual = repo_hechos.leer_estado(sesion, vinculo[\"hecho_id\"])\n")
MUTADO = ("            if False:\n"
          "                estado_actual = repo_hechos.leer_estado(sesion, vinculo[\"hecho_id\"])\n")
TESTS = ["tests/backend/test_14g_mant_vinculo_anulado.py", "tests/backend/test_14h_mant_vinculo_concurrencia_serial.py"]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr() -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", "pytest", *TESTS, "-q", "-p", "no:cacheprovider"]
    return subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace")


def resumen(rc: subprocess.CompletedProcess) -> list[str]:
    return [x for x in rc.stdout.splitlines() if " passed" in x or " failed" in x or " skipped" in x][-1:]


def main() -> None:
    if JOURNAL.exists():
        j = json.loads(JOURNAL.read_text(encoding="utf-8"))
        ruta = RAIZ / j["fichero"]
        ruta.write_bytes(bytes.fromhex(j["original_hex"]))
        if sha(ruta.read_bytes()) != j["sha256"]:
            sys.exit("RECUPERACION FALLIDA: identidad no verificada")
        JOURNAL.unlink()
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    if not os.getenv("GAPTO_TEST_DATABASE_URL"):
        sys.exit("Falta GAPTO_TEST_DATABASE_URL (base local desechable).")
    if os.getenv("GAPTO_MANT_VINCULO_CONCURRENCIA") != "1":
        sys.exit("Falta GAPTO_MANT_VINCULO_CONCURRENCIA=1: test_14h se omitiria.")
    pre = correr()
    if pre.returncode != 0:
        sys.exit(f"PREFLIGHT ROJO: no se muta nada. {resumen(pre)}")
    ruta = RAIZ / F
    original = ruta.read_bytes()
    texto = original.decode("utf-8")
    if texto.count(TEXTO) != 1:
        print("MUT-MANT-01 | NO_CLASIFICABLE | transformacion no aplicable")
        print("RESUMEN 0 muertos, 0 equivalentes documentados, 1 otros / 1")
        sys.exit(1)
    JOURNAL.write_text(json.dumps({"mutante": "MUT-MANT-01", "fichero": F, "original_hex": original.hex(),
                                   "sha256": sha(original)}), encoding="utf-8")
    if hasattr(os, "sync"):
        os.sync()
    v = "NO_CLASIFICABLE"
    rc = None
    try:
        ruta.write_bytes(texto.replace(TEXTO, MUTADO).encode("utf-8"))
        rc = correr()
        v = "MUERTO" if rc.returncode != 0 else "VIVO"
    finally:
        ruta.write_bytes(original)
        ok = sha(ruta.read_bytes()) == sha(original)
        JOURNAL.unlink(missing_ok=True)
    v = v if ok else "NO_CLASIFICABLE"
    print("MUT-MANT-01 (sin la guarda) |", v, "| test_14g,test_14h | restaurado", "OK" if ok else "FALLO", "|",
          resumen(rc) if rc else [])
    print(f"RESUMEN {1 if v == 'MUERTO' else 0} muertos, 0 equivalentes documentados, {0 if v == 'MUERTO' else 1} otros / 1")
    sys.exit(0 if v == "MUERTO" else 1)


if __name__ == "__main__":
    main()
