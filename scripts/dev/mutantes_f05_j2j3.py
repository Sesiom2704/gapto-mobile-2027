# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_j2j3.py
# Ruta: scripts/dev/mutantes_f05_j2j3.py
# Descripcion: Arnes de mutacion de F05-03/F05-04 J2+J3 (mandato §3: un
#   mutante por guarda nueva o modificada, con tabla guarda -> mutante ->
#   test que lo mata). Mismo motor que mutantes_f05_02.py (D-181, D-192,
#   D-193, WM 12C.2):
#     - cada mutante declara sustituciones de texto exacto (UNA ocurrencia) y
#       sus discriminantes (fichero o nodeid);
#     - journal durable ANTES de tocar el primer byte; si al arrancar hay un
#       journal pendiente: restaura, verifica y aborta;
#     - preflight verde de todos los discriminantes antes del primer mutante;
#     - tras cada mutante se restaura y se verifica la identidad byte a byte;
#     - veredicto unico: MUERTO | VIVO | NO_CLASIFICABLE.
#   Las guardas de §1.5 (preferencias) viven en mutantes_f05_02.py
#   (PF30..PF38). Equivalentes documentados (no se mutan): el filtro de owner
#   del contrato de elegibilidad (redundante con FORCE RLS) y la guarda de
#   cierre (ck_cuentas__cierre_deshabilita hace que toda cuenta cerrada este
#   deshabilitada, motivo previo).
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable> python scripts/dev/mutantes_f05_j2j3.py [--solo ID,ID]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F05-03/F05-04 J2 §1.1: EL01..EL08)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f05_j2j3.journal.json"

T167 = "tests/api/test_167_f05_02_resolver.py"
T168 = "tests/api/test_168_f05_02_writers.py"
T174 = "tests/api/test_174_f05_03_elegibilidad_cuentas.py"
ELEG = "backend/app/comun/elegibilidad_cuentas.py"
EJEC = "backend/app/api/ejecucion_gasto_pagado.py"
RES = "backend/app/preferencias/resolver.py"

MUTANTES = [
    # --- §1.1 contrato unico de elegibilidad (R1, C1)
    ("EL01", "elegibilidad sin la guarda de habilitada",
     [(ELEG, "    if not enabled:\n        return DESHABILITADA\n", "")],
     [f"{T174}::test_motivos_en_orden_fijo"]),
    ("EL02", "elegibilidad sin la regla de ledger",
     [(ELEG, "    if inicio_ledger is not None and inicio_ledger > fecha:\n        return LEDGER_POSTERIOR\n", "")],
     [f"{T174}::test_motivos_en_orden_fijo"]),
    ("EL03", "ledger exige fecha estrictamente posterior al inicio",
     [(ELEG, "    if inicio_ledger is not None and inicio_ledger > fecha:",
       "    if inicio_ledger is not None and inicio_ledger >= fecha:")],
     [f"{T174}::test_motivos_en_orden_fijo"]),
    ("EL04", "operacion GASTO exige la capacidad equivocada",
     [(ELEG, '    "GASTO": "PAGAR_GASTO",', '    "GASTO": "RECIBIR_INGRESO",')],
     [f"{T174}::test_matriz_r1_sobre_las_cuentas_sinteticas"]),
    ("EL05", "OP-10 destino exige TRANSFERIR_SALIDA",
     [(ELEG, '    "TRANSFERENCIA_DESTINO": "TRANSFERIR_ENTRADA",', '    "TRANSFERENCIA_DESTINO": "TRANSFERIR_SALIDA",')],
     [f"{T174}::test_matriz_r1_sobre_las_cuentas_sinteticas"]),
    ("EL06", "COMPRA_TARJETA implica PAGAR_GASTO",
     [(ELEG, '"AND k.capacidad_codigo = %s) AS capacidad "',
       '"AND k.capacidad_codigo IN (%s, \'COMPRA_TARJETA\')) AS capacidad "')],
     [f"{T174}::test_compra_tarjeta_y_domiciliar_no_implican_pagar_gasto"]),
    ("EL07", "confirmacion VS-01 sin la regla unica (solo moneda)",
     [(EJEC, "    if motivo is not None:\n        raise ErrorMotor(CodigoError.CUENTA_DESCONOCIDA",
       "    if False:\n        raise ErrorMotor(CodigoError.CUENTA_DESCONOCIDA")],
     [f"{T174}::test_gasto_pagado_con_cuenta_no_elegible"]),
    ("EL08", "preferencia de INGRESO validada con la regla de GASTO",
     [(RES, '    return "INGRESO" if fila is not None and fila[0] == "INGRESO" else "GASTO"',
       '    return "GASTO"')],
     [f"{T168}::test_preferencia_de_ingreso_exige_recibir_ingreso"]),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(tests: list[str]) -> int:
    cmd = [sys.executable, "-m", "pytest", *tests, "-q", "-x", "-p", "no:cacheprovider", "--rootdir=tests/api"]
    return subprocess.run(cmd, cwd=RAIZ, capture_output=True).returncode


def recuperar_si_pendiente() -> bool:
    if not JOURNAL.exists():
        return False
    j = json.loads(JOURNAL.read_text(encoding="utf-8"))
    for f in j["ficheros"]:
        ruta = RAIZ / f["fichero"]
        ruta.write_bytes(bytes.fromhex(f["original_hex"]))
        if sha(ruta.read_bytes()) != f["sha256"]:
            sys.exit(f"RECUPERACION FALLIDA: identidad no verificada en {f['fichero']}")
    JOURNAL.unlink()
    return True


def main() -> None:
    if not os.getenv("GAPTO_TEST_DATABASE_URL"):
        sys.exit("Falta GAPTO_TEST_DATABASE_URL (base local desechable).")
    if recuperar_si_pendiente():
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    solo = None
    if "--solo" in sys.argv:
        solo = set(sys.argv[sys.argv.index("--solo") + 1].split(","))
    elegidos = [m for m in MUTANTES if solo is None or m[0] in solo]
    preflight = sorted({t.split("::")[0] for m in elegidos for t in m[3]})
    if correr(preflight) != 0:
        sys.exit("PREFLIGHT ROJO: no se muta nada.")
    veredictos = []
    for mid, desc, cambios, tests in elegidos:
        ficheros = sorted({c[0] for c in cambios})
        originales = {f: (RAIZ / f).read_bytes() for f in ficheros}
        textos = {f: b.decode("utf-8") for f, b in originales.items()}
        aplicable = True
        for f, a, b in cambios:
            if textos[f].count(a) != 1:
                aplicable = False
                break
            textos[f] = textos[f].replace(a, b)
        if not aplicable:
            veredictos.append((mid, "NO_CLASIFICABLE", "transformacion no aplicable", desc))
            continue
        JOURNAL.write_text(
            json.dumps({"mutante": mid, "ficheros": [
                {"fichero": f, "original_hex": originales[f].hex(), "sha256": sha(originales[f])} for f in ficheros
            ]}),
            encoding="utf-8",
        )
        if hasattr(os, "sync"):
            os.sync()
        v = "NO_CLASIFICABLE"
        try:
            for f in ficheros:
                (RAIZ / f).write_bytes(textos[f].encode("utf-8"))
            v = "MUERTO" if correr(tests) != 0 else "VIVO"
        finally:
            ok = True
            for f in ficheros:
                (RAIZ / f).write_bytes(originales[f])
                ok = ok and sha((RAIZ / f).read_bytes()) == sha(originales[f])
            JOURNAL.unlink(missing_ok=True)
        veredictos.append((mid, v if ok else "NO_CLASIFICABLE", ",".join(pathlib.Path(t).name for t in tests), desc))
    for v in veredictos:
        print(*v, sep=" | ")
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    print(f"RESUMEN {muertos} / {len(veredictos)} muertos")
    sys.exit(0 if muertos == len(veredictos) else 1)


if __name__ == "__main__":
    main()
