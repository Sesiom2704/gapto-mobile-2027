# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_vs01_backend.py
# Ruta: scripts/dev/mutantes_vs01_backend.py
# Descripcion: Ejecuta SOLO los mutantes de backend (suite "py") del arnes
#   de VS-01 (scripts/dev/mutantes_vs01.py), sin mobile/ ni Jest (D5 de
#   F05-D016). Sustituye al runner auxiliar no versionado que se uso como
#   corroboracion en S6-ICONO (R-EVID-RUNNER, F05 §30.6): este fichero es el
#   que produce el veredicto y esta versionado antes de ejecutarse (D-181).
#   - Localiza el repositorio por la ruta de este fichero (sin rutas
#     absolutas) y carga el arnes VS-01 como modulo, reutilizando su censo
#     MUTANTES, su preflight/ejecucion `correr`, su journal JOURNAL, su
#     `recuperar_si_pendiente` y su `sha` (D-181/D-192): journal durable
#     ANTES de tocar el primer byte; al arrancar, si hay journal pendiente,
#     restaura, verifica y aborta; preflight verde de la suite py; tras cada
#     mutante, restauracion y verificacion byte a byte; un veredicto unico
#     por mutante: MUERTO | VIVO | NO_CLASIFICABLE.
#   - Filtra MUTANTES por suite == "py"; los mutantes "js" no se aplican ni
#     se ejecutan, y se declaran en la salida.
#   Requiere GAPTO_TEST_DATABASE_URL (base local desechable). No es
#   evidencia de proveedor.
# Version: 0.1.0 (F05-01 R-LOCALE; R-EVID-RUNNER)
# ============================================================

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys

ARNES = pathlib.Path(__file__).resolve().parent / "mutantes_vs01.py"


def cargar_arnes():
    spec = importlib.util.spec_from_file_location("mutantes_vs01", ARNES)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def main() -> None:
    m = cargar_arnes()
    if not os.getenv("GAPTO_TEST_DATABASE_URL"):
        sys.exit("Falta GAPTO_TEST_DATABASE_URL (base local desechable).")
    if m.recuperar_si_pendiente():
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    if m.correr("py") != 0:
        sys.exit("PREFLIGHT ROJO en suite py: no se muta nada.")
    py = [x for x in m.MUTANTES if x[4] == "py"]
    js = [x[0] for x in m.MUTANTES if x[4] != "py"]
    print(f"censo arnes {len(m.MUTANTES)}; ejecutados py {len(py)}; omitidos js {len(js)}: {' '.join(js)}")
    veredictos = []
    for mid, fichero, a, b, suite in py:
        ruta = m.RAIZ / fichero
        original = ruta.read_bytes()
        texto = original.decode("utf-8")
        if texto.count(a) != 1:
            veredictos.append((mid, "NO_CLASIFICABLE", "transformacion no aplicable"))
            continue
        m.JOURNAL.write_text(
            json.dumps({"fichero": fichero, "original_hex": original.hex(), "sha256": m.sha(original)}),
            encoding="utf-8",
        )
        if hasattr(os, "sync"):
            os.sync()
        v = "NO_CLASIFICABLE"
        try:
            ruta.write_bytes(texto.replace(a, b).encode("utf-8"))
            v = "MUERTO" if m.correr(suite) != 0 else "VIVO"
        finally:
            ruta.write_bytes(original)
            ok = m.sha(ruta.read_bytes()) == m.sha(original)
            m.JOURNAL.unlink(missing_ok=True)
        veredictos.append((mid, v if ok else "NO_CLASIFICABLE", fichero))
    for v in veredictos:
        print(*v)
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    print("RESUMEN", muertos, "/", len(veredictos), "muertos")
    sys.exit(0 if muertos == len(veredictos) else 1)


if __name__ == "__main__":
    main()
