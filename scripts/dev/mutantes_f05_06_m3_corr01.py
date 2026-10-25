# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_06_m3_corr01.py
# Ruta: scripts/dev/mutantes_f05_06_m3_corr01.py
# Descripcion: Arnes de mutacion de F05-06 M3 CORR-01 (R-M3-05): en el exito
#   del gasto compartido, cada «Pendiente con <persona>» sale del `tercero_id`
#   que el servidor devuelve en cada posicion, nunca del importe. Procede del
#   arnes historico C:/DEV/evidencia_f0506_m3/corr01/mutante_corr01.py
#   (HUECO-05), que tenia cableadas la raiz del worktree (C:\DEV\wt_f05_06_m3)
#   y la ruta del journal en la evidencia. Mismo motor que
#   mutantes_f05_06_m2.py (D-181, D-192, D-193, WM 12C.2): sustitucion de texto
#   exacto (UNA ocurrencia), journal durable antes del primer byte (si al
#   arrancar hay uno pendiente: restaura, verifica y aborta), preflight verde,
#   restauracion verificada por SHA-256 y veredicto MUERTO | VIVO |
#   NO_CLASIFICABLE.
#     MUT-CORR01 el emparejamiento vuelve a hacerse por importe (la persona se
#       deduce del pagador o de la parte con el mismo importe).
#   Discriminante: Jest `__tests__/reparto.test.tsx -t CORR-01` (en serie).
#   Uso: python scripts/dev/mutantes_f05_06_m3_corr01.py
#   Solo Jest: no necesita base de datos. No ejecutar en paralelo con otro
#   arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F05-06 M3 CORR-01, fuera del repo: evidencia_f0506_m3/corr01)
# Version: 0.2.0 (F05-07/GATE adenda 2, MANT-PRE-GATE arneses, HUECO-05; F05
#   §63.6 (1)): pasa a scripts/dev/; la raiz se deduce del propio fichero y el
#   journal vive en la raiz del repo; se anade el preflight (el historico no lo
#   tenia) y Jest va en serie (`--runInBand`). El texto protegido sigue anclando
#   en 5e39673 (GastoCompartidoScreen.tsx no cambia desde c9c2932): sin
#   reanclaje.
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f05_06_m3_corr01.journal.json"

F = "mobile/src/screens/GastoCompartidoScreen.tsx"
TEXTO = "            const tid = x.tercero_id;\n"
MUTADO = ("            const tid = envio.payload.pagado_por.tipo === 'PERSONA' && x.tipo === 'OBLIGACION_PAGO'\n"
          "              ? envio.payload.pagado_por.tercero_id\n"
          "              : envio.payload.reparto.modo === 'REPARTIR'\n"
          "                ? envio.payload.reparto.partes.find((q) => q.me_debe === 'SI' && q.importe === x.importe)?.tercero_id ?? null\n"
          "                : null;\n")
JEST = ["__tests__/reparto.test.tsx", "-t", "CORR-01"]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr() -> subprocess.CompletedProcess:
    npx = shutil.which("npx") or "npx"
    return subprocess.run([npx, "jest", "--runInBand", *JEST], cwd=RAIZ / "mobile", capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def resumen(rc: subprocess.CompletedProcess) -> list[str]:
    return [x.strip() for x in (rc.stdout + rc.stderr).splitlines() if x.startswith("Tests:")]


def main() -> None:
    if JOURNAL.exists():
        j = json.loads(JOURNAL.read_text(encoding="utf-8"))
        ruta = RAIZ / j["fichero"]
        ruta.write_bytes(bytes.fromhex(j["original_hex"]))
        if sha(ruta.read_bytes()) != j["sha256"]:
            sys.exit("RECUPERACION FALLIDA: identidad no verificada")
        JOURNAL.unlink()
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    pre = correr()
    if pre.returncode != 0:
        sys.exit(f"PREFLIGHT ROJO: no se muta nada. {resumen(pre)}")
    ruta = RAIZ / F
    original = ruta.read_bytes()
    texto = original.decode("utf-8")
    if texto.count(TEXTO) != 1:
        print("MUT-CORR01 | NO_CLASIFICABLE | transformacion no aplicable")
        print("RESUMEN 0 muertos, 0 equivalentes documentados, 1 otros / 1")
        sys.exit(1)
    JOURNAL.write_text(json.dumps({"mutante": "MUT-CORR01", "fichero": F, "original_hex": original.hex(),
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
    print("MUT-CORR01 |", v, "| reparto.test.tsx -t CORR-01 | restaurado", "OK" if ok else "FALLO", "|",
          resumen(rc) if rc else [])
    print(f"RESUMEN {1 if v == 'MUERTO' else 0} muertos, 0 equivalentes documentados, {0 if v == 'MUERTO' else 1} otros / 1")
    sys.exit(0 if v == "MUERTO" else 1)


if __name__ == "__main__":
    main()
