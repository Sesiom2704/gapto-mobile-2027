# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_06_m2.py
# Ruta: scripts/dev/mutantes_f05_06_m2.py
# Descripcion: Arnes de mutacion de F05-06 M2 (mandato §A5: mutantes de las
#   guardas nuevas al 100 % muertos o equivalentes documentados). Mismo motor
#   que mutantes_f05_06_m4.py (D-181, D-192, D-193, WM 12C.2): sustituciones
#   de texto exacto (UNA ocurrencia), journal durable antes del primer byte,
#   preflight verde, restauracion verificada por SHA-256 y veredicto
#   MUERTO | VIVO | EQUIVALENTE | NO_CLASIFICABLE.
#   Guardas: M01 lock del origen, M02 guarda de replay, M03 FECHA_FUTURA,
#   M04 origen ACTIVO, M05 solo gastos positivos (nunca INGRESO ni devolver
#   una devolucion), M06 V3 con un unico efecto GASTO, M07 multicategoria,
#   M08 «Tuya» del actor propio, M09 capacidad de la cuenta del abono,
#   M10 sin abono doble, M11 «lo que queda» en EXCEDE, M12 abono solo sobre
#   devoluciones, M13 abono solo sobre devoluciones ACTIVAS. Cliente: MU01
#   limite D-DEV-08, MU02 «Tuya» solo demostrada (P-DEV-01), MU03 «Abono
#   pendiente» en la fila (D-DEV-07), MU04 el swipe «Cobrado» captura el
#   movimiento horizontal (P-DEV-04).
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable> GAPTO_M2_CONCURRENCIA=1
#        python scripts/dev/mutantes_f05_06_m2.py [--solo ID,ID]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F05-06 M2-A §A5)
# Version: 0.2.0 (F05-06 M2-B §B2): MU04, captura del gesto «Cobrado» en el
#   contenedor de la fila (autocorreccion del swipe en M2-B).
# Version: 0.3.0 (F05-06 M2-D §3): un mutante por guarda de la cuenta del abono
#   (opcion b): MD01 sin excepcion de cuenta original, MD02 excepcion para
#   cualquier cuenta, MD03 RECIBIR_INGRESO -> PAGAR_GASTO, MD04 cuenta original
#   con varias conciliaciones (la primera, como un LIMIT 1), MD05 excepcion que
#   omite habilitada/cierre/owner/moneda; cliente MU05/MU06 propuesta de la
#   original solo si esta en la lista (comportamiento de M2-B).
# Version: 0.4.0 (MANT-M5-ARNESES, AJ-M5-CIERRE-06): MU04 rehecho sobre el componente
#   comun del swipe (mobile/src/components/AccionRapida.tsx, FilaDeslizable): el gesto de
#   la fila de la devolucion ya no vive en ActividadScreen.tsx desde M5 SWIPE. Mismo
#   mutante (el contenedor no captura el movimiento) y mismo discriminante.
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
JOURNAL = RAIZ / ".mutantes_f05_06_m2.journal.json"

EJEC = "backend/app/api/ejecucion_devolucion.py"
T196 = "tests/api/test_196_f05_06_m2_devolucion.py"
T197 = "tests/api/test_197_f05_06_m2_concurrencia_serial.py"
M_DOM = "mobile/src/domain/devolucion.ts"
M_ACT = "mobile/src/screens/ActividadScreen.tsx"
M_SWIPE = "mobile/src/components/AccionRapida.tsx"
ELEG = "backend/app/comun/elegibilidad_cuentas.py"
T198 = "tests/api/test_198_f05_06_m2d_cuenta_abono.py"
M_DEV = "mobile/src/screens/DevolucionScreen.tsx"
M_HOJA = "mobile/src/components/AbonoHoja.tsx"
J_DEV = "mobile/__tests__/devolucion.test.tsx"

#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    ("M01", "devolucion sin lock del origen en el adaptador",
     [(EJEC, '"FROM gapto.hechos_financieros h WHERE h.id = %s FOR NO KEY UPDATE OF h"',
       '"FROM gapto.hechos_financieros h WHERE h.id = %s"')],
     [f"{T197}::test_a_dos_devoluciones_que_juntas_exceden", f"{T197}::test_b_devolucion_frente_a_anulacion_del_origen"],
     "OP-13 toma el mismo lock del origen (FOR NO KEY UPDATE) antes de escribir y revalida estado y capacidad "
     "bajo el; sin el lock del adaptador el resultado observable es el mismo"),
    ("M02", "replay sin comparar lo persistido con la intencion",
     [(EJEC, '            or fila[8] != "GASTO" or not abono_coincide):',
       '            or fila[8] != "GASTO" or not abono_coincide) and False:')],
     [f"{T196}::test_repeticion_idempotente_y_otra_intencion"], None),
    ("M03", "devolucion sin FECHA_FUTURA",
     [(EJEC, "        if es_futura(sesion, i.fecha_hecho, reloj) or (cobrado and es_futura(sesion, i.abono.fecha, reloj)):",
       "        if False:")],
     [f"{T196}::test_fecha_futura"], None),
    ("M04", "devolucion de un origen no ACTIVO",
     [(EJEC, '        if estado != "ACTIVO":', "        if False:")],
     [f"{T196}::test_origen_anulado_despues_g_r1_a"], None),
    ("M05", "devolucion de un efecto no positivo (devolver una devolucion)",
     [(EJEC, "    if not gastos or any(decimal.Decimal(f[2]) <= CERO for f in gastos):",
       "    if not gastos:")],
     [f"{T196}::test_nunca_ingreso"], None),
    ("M06", "V3 con varios efectos GASTO admitido",
     [(EJEC, "    if es_v3 and len(gastos) != 1:", "    if False:")],
     [f"{T196}::test_v3_solo_con_un_unico_efecto_gasto"], None),
    ("M07", "varias categorias admitidas",
     [(EJEC, "    if len({f[4] for f in gastos}) > 1:", "    if False:")],
     [f"{T196}::test_varias_categorias_fuera"], None),
    ("M08", "«Tuya» sin exigir que la unica fila sea del actor propio",
     [(EJEC, 'f[3] == "COMPLETA" and f[5] == 1 and f[6] == 1 for f in gastos',
       'f[3] == "COMPLETA" and f[5] == 1 for f in gastos')],
     [f"{T196}::test_solo_mio_exige_completa_de_un_unico_actor_propio"], None),
    ("M09", "cuenta del abono sin comprobacion de capacidad",
     [(EJEC, "    if motivo == SIN_CAPACIDAD:", "    if False:")],
     [f"{T196}::test_cuenta_sin_capacidad_sin_escritura"], None),
    ("M10", "abono doble (sin comprobar conciliacion previa)",
     [(EJEC, "                      (devolucion_id,)) is not None:",
       "                      (devolucion_id,)) is not None and False:")],
     [f"{T196}::test_pendiente_sin_liquidez_y_abono_posterior", f"{T196}::test_ya_cobrado_en_la_misma_transaccion",
      f"{T197}::test_c_abono_doble"], None),
    ("M11", "EXCEDE sin «lo que queda»",
     [(EJEC, '                raise _Rechazo(EXCEDE, {"queda": _texto(queda)}) from exc',
       "                raise _Rechazo(EXCEDE) from exc")],
     [f"{T196}::test_parciales_40_mas_60_y_exceso_30"], None),
    ("M12", "abono sobre algo que no es devolucion",
     [(EJEC, "            raise _Rechazo(NO_ES_DEVOLUCION)", "            pass")],
     [f"{T196}::test_abono_sobre_algo_que_no_es_devolucion"], None),
    ("M13", "abono sobre una devolucion anulada",
     [(EJEC, "            raise _Rechazo(DEVOLUCION_NO_ACTIVA)", "            pass")],
     [f"{T196}::test_origen_anulado_despues_g_r1_a"], None),
    ("MU01", "cliente: deja revisar mas de lo que queda (D-DEV-08)",
     [(M_DOM, "  return r.ok && centimos(r.valor) > centimos(queda);", "  return false;")],
     [J_DEV], None),
    ("MU02", "cliente: «Tuya» propuesta sin demostrar (P-DEV-01)",
     [(M_DOM, "  return ctx.tuya_disponible ? 'SOLO_MIO' : 'SIN_INDICAR';", "  return 'SOLO_MIO';")],
     [J_DEV], None),
    ("MU03", "cliente: «Abono pendiente» perdido en la fila (D-DEV-07)",
     [(M_DOM, "  return f.abono === 'PENDIENTE' ? ETIQUETA_ABONO_PENDIENTE : ETIQUETA_DEVOLUCION;",
       "  return ETIQUETA_DEVOLUCION;")],
     [J_DEV], None),
    ("MU04", "cliente: swipe «Cobrado» sin capturar el movimiento (el Pressable se lo queda) (P-DEV-04)",
     [(M_SWIPE, "      onMoveShouldSetPanResponderCapture: (_, g) => horizontal(g),", "      onMoveShouldSetPanResponderCapture: () => false,")],
     [J_DEV], None),
    ("MD01", "abono: sin excepcion de la cuenta original (toda cuenta exige RECIBIR_INGRESO)",
     [(EJEC, "    if original is not None and cuenta_id == original:", "    if False:")],
     [f"{T198}::test_1_cuenta_original_tarjeta_sin_recibir_ingreso", f"{T198}::test_2_cuenta_original_sin_pagar_gasto"],
     None),
    ("MD02", "abono: excepcion de capacidad ampliada a cualquier cuenta",
     [(EJEC, "    if original is not None and cuenta_id == original:", "    if True:")],
     [f"{T198}::test_4_otra_cuenta_sin_recibir_ingreso", f"{T198}::test_6_origen_con_dos_conciliaciones"], None),
    ("MD03", "abono: la otra cuenta exige PAGAR_GASTO en lugar de RECIBIR_INGRESO",
     [(EJEC, 'OPERACION_CUENTA_ABONO = "INGRESO"', 'OPERACION_CUENTA_ABONO = "GASTO"')],
     [f"{T198}::test_3_otra_cuenta_con_recibir_ingreso", f"{T198}::test_4_otra_cuenta_sin_recibir_ingreso"], None),
    ("MD04", "abono: cuenta original elegida con varias conciliaciones (la primera, LIMIT 1)",
     [(EJEC, "    if len(filas) != 1 or not filas[0][1]:", "    if not filas or not filas[0][1]:")],
     [f"{T198}::test_6_origen_con_dos_conciliaciones"], None),
    ("MD05", "abono: la excepcion de la original omite habilitada, cierre, owner y moneda",
     [(ELEG, "    fila = sesion.uno(_SELECT_SIN_CAPACIDAD, (cuenta_id,))", "    return None")],
     [f"{T198}::test_5_cuenta_original_cerrada_o_deshabilitada", f"{T198}::test_5_cuenta_original_de_otra_moneda_no_se_exime"],
     None),
    ("MU05", "cliente: «Sí, en <original>» solo si la original esta en la lista de RECIBIR_INGRESO",
     [(M_DEV, "  const compraElegible = !!ctx?.cuenta_compra;",
       "  const compraElegible = !!ctx?.cuenta_compra && cuentas.fase === 'OK' && cuentas.lista.some((x) => x.cuenta_id === ctx.cuenta_compra!.cuenta_id);")],
     [J_DEV], None),
    ("MU06", "cliente: la hoja B2 propone la original solo si esta en la lista de RECIBIR_INGRESO",
     [(M_HOJA, "  const propuestaElegible = !!propuesta;",
       "  const propuestaElegible = !!propuesta && cuentas.fase === 'OK' && cuentas.lista.some((x) => x.cuenta_id === propuesta.cuenta_id);")],
     [J_DEV], None),
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
    if os.getenv("GAPTO_M2_CONCURRENCIA") != "1":
        sys.exit("Falta GAPTO_M2_CONCURRENCIA=1: los discriminantes de test_197 se omitirian.")
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
