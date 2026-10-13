# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_06_m4.py
# Ruta: scripts/dev/mutantes_f05_06_m4.py
# Descripcion: Arnes de mutacion de F05-06 M4 (mandato §4.5: un mutante por
#   guarda, 100 % muertos o equivalentes documentados). Mismo motor que
#   mutantes_f05_j2j3.py (D-181, D-192, D-193, WM 12C.2):
#     - cada mutante declara sustituciones de texto exacto (UNA ocurrencia) y
#       sus discriminantes (nodeid de pytest o fichero Jest de mobile/);
#     - journal durable ANTES de tocar el primer byte; si al arrancar hay un
#       journal pendiente: restaura, verifica y aborta;
#     - preflight verde de todos los discriminantes antes del primer mutante;
#     - tras cada mutante se restaura y se verifica la identidad byte a byte;
#     - veredicto: MUERTO | VIVO | NO_CLASIFICABLE. Un mutante declarado
#       EQUIVALENTE (con su justificacion) que sale VIVO se informa como
#       EQUIVALENTE; si sale MUERTO, como MUERTO.
#   Guardas (§4.5): M01 lock de la cuenta, M02 row_version, M03 auditoria,
#   M04 DOMICILIAR editable, M05a/M05b default por tipo (elegibilidad y
#   lecturas de capacidades), M06a/M06b CUENTA_DESCONOCIDA en vez de
#   CUENTA_SIN_CAPACIDAD (registro y gasto VS-01), M07a/M07b comprobacion de
#   owner (writer y lecturas), M08 estado de la cuenta. Cliente: MU01 hoja A4
#   confirmable sin impacto, MU02 aviso B2 con N = 0.
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable> GAPTO_M4_CONCURRENCIA=1
#        python scripts/dev/mutantes_f05_06_m4.py [--solo ID,ID]
#   Sin GAPTO_M4_CONCURRENCIA=1 los discriminantes de test_194 se omiten y M01
#   saldria VIVO. No ejecutar en paralelo con otro arnes ni con la suite sobre
#   el mismo arbol.
# Version: 0.1.0 (F05-06 M4 F3)
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
JOURNAL = RAIZ / ".mutantes_f05_06_m4.journal.json"

SERV = "backend/app/capacidades/servicio.py"
LECT = "backend/app/capacidades/lecturas.py"
ELEG = "backend/app/comun/elegibilidad_cuentas.py"
REGI = "backend/app/api/ejecucion_registro.py"
EJEC = "backend/app/api/ejecucion_gasto_pagado.py"
T192 = "tests/api/test_192_f05_06_m4_capacidades.py"
T193 = "tests/api/test_193_f05_06_m4_h2_sin_deduccion.py"
T194 = "tests/api/test_194_f05_06_m4_concurrencia_serial.py"
M_CAP = "mobile/src/screens/CuentasCapacidadesScreen.tsx"
M_DOM = "mobile/src/domain/capacidades.ts"
J_CAP = "mobile/__tests__/capacidades.test.tsx"

#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    ("M01", "writer sin lock de la cuenta",
     [(SERV, "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid FOR NO KEY UPDATE\",",
       "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid\",")],
     [f"{T194}::test_e_dos_writers_misma_cuenta", f"{T194}::test_a_desactivar_pagar_gasto_frente_a_gasto"], None),
    ("M02", "writer sin control de row_version",
     [(SERV, "    if version != row_version:\n        return Rechazo(VERSION_DESFASADA)\n", "")],
     [f"{T192}::test_version_desfasada_no_pisa"], None),
    ("M03", "writer sin auditoria",
     [(SERV, "    auditoria.registrar(\n", "    (lambda *a, **k: None)(\n")],
     [f"{T192}::test_activar_y_desactivar_con_version_y_auditoria", f"{T192}::test_historial_desde_auditoria"], None),
    ("M04", "DOMICILIAR editable",
     [(SERV, 'NO_EDITABLES = ("COMPRA_TARJETA", "DOMICILIAR")', 'NO_EDITABLES = ("COMPRA_TARJETA",)'),
      (SERV, 'EDITABLES = ("PAGAR_GASTO", "RECIBIR_INGRESO", "TRANSFERIR_SALIDA", "TRANSFERIR_ENTRADA")',
       'EDITABLES = ("PAGAR_GASTO", "RECIBIR_INGRESO", "TRANSFERIR_SALIDA", "TRANSFERIR_ENTRADA", "DOMICILIAR")')],
     [f"{T192}::test_capacidades_no_editables"], None),
    ("M05a", "default por tipo en la elegibilidad (CORRIENTE puede todo)",
     [(ELEG, '"AND k.capacidad_codigo = %s) AS capacidad "',
       '"AND k.capacidad_codigo = %s) OR c.tipo = \'CORRIENTE\' AS capacidad "')],
     [f"{T193}::test_siete_tipos_sin_filas_no_son_elegibles"], None),
    ("M05b", "default por tipo en las lecturas de capacidades (CORRIENTE paga gastos)",
     [(LECT, '"ORDER BY k.capacidad_codigo)::text[] AS capacidades, "',
       '"ORDER BY k.capacidad_codigo)::text[] || CASE WHEN c.tipo = \'CORRIENTE\' THEN ARRAY[\'PAGAR_GASTO\'] '
       'ELSE ARRAY[]::text[] END AS capacidades, "')],
     [f"{T193}::test_lecturas_sin_propuesta_ni_default_por_tipo"], None),
    ("M06a", "registro (ingreso, OP-10) devuelve CUENTA_DESCONOCIDA al perder la capacidad",
     [(REGI, "    if motivo == SIN_CAPACIDAD:\n        raise CuentaSinCapacidad(detalle_sin_capacidad(sesion, cuenta_id, operacion))\n", "")],
     [f"{T192}::test_rechazo_especifico_en_ingreso_y_transferencia"], None),
    ("M06b", "gasto VS-01 devuelve CUENTA_DESCONOCIDA al perder la capacidad",
     [(EJEC, "    if motivo == SIN_CAPACIDAD:\n        raise CuentaSinCapacidad(detalle_sin_capacidad(sesion, intencion.cuenta_id, \"GASTO\"))\n", "")],
     [f"{T192}::test_rechazo_especifico_en_gasto_con_texto_b3"], None),
    ("M07a", "writer sin comprobacion de owner",
     [(SERV, "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid FOR NO KEY UPDATE\",",
       "FOR NO KEY UPDATE\",")],
     [f"{T192}::test_ids_de_otro_owner_o_inexistentes_sin_efectos"],
     "FORCE RLS de cuentas (0120 tenant_isolation) oculta la cuenta ajena al rol gapto_runtime: "
     "el SELECT ... FOR NO KEY UPDATE devuelve 0 filas igual, y la RLS de cuenta_capacidades impide escribir"),
    ("M07b", "lecturas de capacidades sin comprobacion de owner",
     [(LECT, "\"FROM gapto.cuentas c WHERE c.owner_user_id = current_setting('gapto.owner_user_id')::uuid\"",
       "\"FROM gapto.cuentas c WHERE true\"")],
     [f"{T192}::test_ids_de_otro_owner_o_inexistentes_sin_efectos"],
     "FORCE RLS de cuentas oculta las ajenas a gapto_runtime: la lista y el detalle no cambian"),
    ("M08", "writer sin comprobacion del estado de la cuenta (PD-2)",
     [(SERV, "    if not enabled or fecha_cierre is not None:\n        return Rechazo(NO_PERMITIDA_EN_ESTADO)\n", "")],
     [f"{T192}::test_cuenta_cerrada_o_deshabilitada"], None),
    ("MU01", "cliente: hoja A4 confirmable antes de cargar el impacto",
     [(M_CAP, "deshabilitado={ocupado || !impactoListo}", "deshabilitado={ocupado}")],
     [J_CAP], None),
    ("MU02", "cliente: aviso B2 tambien con N = 0",
     [(M_DOM, "  return n > 0 ? `¿Falta una cuenta? ${n} sin configurar` : null;",
       "  return `¿Falta una cuenta? ${n} sin configurar`;")],
     [J_CAP], None),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(tests: list[str]) -> int:
    py = [t for t in tests if not t.startswith("mobile/")]
    js = [t.removeprefix("mobile/") for t in tests if t.startswith("mobile/")]
    rc = 0
    if py:
        cmd = [sys.executable, "-m", "pytest", *py, "-q", "-x", "-p", "no:cacheprovider", "--rootdir=tests/api"]
        rc = rc or subprocess.run(cmd, cwd=RAIZ, capture_output=True).returncode
    if js:
        npx = shutil.which("npx") or "npx"
        rc = rc or subprocess.run([npx, "jest", "--silent", *js], cwd=RAIZ / "mobile", capture_output=True).returncode
    return rc


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
    if os.getenv("GAPTO_M4_CONCURRENCIA") != "1":
        sys.exit("Falta GAPTO_M4_CONCURRENCIA=1: los discriminantes de test_194 se omitirian.")
    if recuperar_si_pendiente():
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    solo = None
    if "--solo" in sys.argv:
        solo = set(sys.argv[sys.argv.index("--solo") + 1].split(","))
    elegidos = [m for m in MUTANTES if solo is None or m[0] in solo]
    preflight = sorted({t for m in elegidos for t in m[3]})
    if correr(preflight) != 0:
        sys.exit("PREFLIGHT ROJO: no se muta nada.")
    veredictos = []
    for mid, desc, cambios, tests, equivalencia in elegidos:
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
        if v == "VIVO" and equivalencia:
            v = "EQUIVALENTE"
        nota = f"{desc} [equivalente: {equivalencia}]" if v == "EQUIVALENTE" else desc
        veredictos.append((mid, v if ok else "NO_CLASIFICABLE", ",".join(pathlib.Path(t.split("::")[0]).name for t in tests), nota))
    for v in veredictos:
        print(*v, sep=" | ")
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    equivalentes = sum(1 for v in veredictos if v[1] == "EQUIVALENTE")
    print(f"RESUMEN {muertos} muertos, {equivalentes} equivalentes documentados, "
          f"{len(veredictos) - muertos - equivalentes} otros / {len(veredictos)}")
    sys.exit(0 if muertos + equivalentes == len(veredictos) else 1)


if __name__ == "__main__":
    main()
