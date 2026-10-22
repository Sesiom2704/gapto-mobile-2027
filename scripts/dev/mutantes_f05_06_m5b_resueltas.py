# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_06_m5b_resueltas.py
# Ruta: scripts/dev/mutantes_f05_06_m5b_resueltas.py
# Descripcion: Arnes de mutacion de F05-06 M5-B v1.1 · «Resueltas este mes»
#   (100 % muertos o equivalentes documentados). Mismo motor que
#   mutantes_f05_06_m1.py (journal durable, preflight verde, restauracion
#   verificada por SHA-256, veredicto a disco en cuanto se conoce). Guardas:
#   filtro de estados (REALIZADA y OMITIDA; CANCELADA nunca), filtro del mes
#   (limite inferior y superior), fecha de la transicion antes que la objetivo,
#   orden de mas reciente a mas antigua y, en la UI, plegado por defecto,
#   recuento, etiquetas y apertura del detalle.
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable>
#        python scripts/dev/mutantes_f05_06_m5b_resueltas.py [--solo ID,ID] [--salida fichero]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F05-06 M5-B v1.1)
# Version: 0.2.0 (F05-06 M5-B cierre, AJ-M5BM1-CIERRE-02): X06, procedencia de la fecha en la UI.
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f05_06_m5b_resueltas.journal.json"

LEC = "backend/app/previsiones/lecturas.py"
DOMP = "mobile/src/domain/prevision.ts"
PEND = "mobile/src/screens/PendientesScreen.tsx"
T211 = "tests/api/test_211_f05_06_m5b_resueltas_mes.py::"
JEST = "jest:__tests__/previsiones.test.tsx::"

#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    ("R01", "estados: CANCELADA tambien aparece",
     [(LEC, 'ESTADOS_RESUELTAS = ("REALIZADA", "OMITIDA")\n', 'ESTADOS_RESUELTAS = ("REALIZADA", "OMITIDA", "CANCELADA")\n')],
     [T211 + "test_abiertas_y_canceladas_no_aparecen"], None),
    ("R02", "estados: solo las OMITIDA (faltan las REALIZADA)",
     [(LEC, 'ESTADOS_RESUELTAS = ("REALIZADA", "OMITIDA")\n', 'ESTADOS_RESUELTAS = ("OMITIDA",)\n')],
     [T211 + "test_realizadas_cubierta_pagada_y_sin_realidad_activa"], None),
    ("R03", "estados: tambien las ABIERTA",
     [(LEC, 'ESTADOS_RESUELTAS = ("REALIZADA", "OMITIDA")\n', 'ESTADOS_RESUELTAS = ("REALIZADA", "OMITIDA", "ABIERTA")\n')],
     [T211 + "test_abiertas_y_canceladas_no_aparecen"], None),
    ("R04", "mes: sin limite inferior (entra el mes anterior)",
     [(LEC, "            if fecha is None or not inicio <= fecha < fin:\n", "            if fecha is None or not fecha < fin:\n")],
     [T211 + "test_sin_auditoria_de_la_transicion_usa_la_fecha_objetivo", T211 + "test_limite_del_mes"], None),
    ("R05", "mes: sin limite superior (entra el mes siguiente)",
     [(LEC, "            if fecha is None or not inicio <= fecha < fin:\n", "            if fecha is None or not inicio <= fecha:\n")],
     [T211 + "test_limite_del_mes"], None),
    ("R06", "fecha: siempre la objetivo, aunque haya auditoria de la transicion",
     [(LEC, "            if instante is not None:\n                fecha, origen = instante.astimezone(zona).date(), FECHAS_RESOLUCION[0]\n",
       "            if False:\n                fecha, origen = instante.astimezone(zona).date(), FECHAS_RESOLUCION[0]\n")],
     [T211 + "test_omitida_aparece_con_la_fecha_de_su_transicion"], None),
    ("R07", "fecha: cualquier auditoria de la prevision, no la de la transicion al estado vigente",
     [(LEC, "AND a.datos_despues ->> 'estado' = p.estado ", "")],
     [T211 + "test_reabrir_la_devuelve_a_vencidas", T211 + "test_omitida_aparece_con_la_fecha_de_su_transicion"],
     "si el estado vigente es terminal, la ultima ACTUALIZAR que cambia de estado es la transicion a el"),
    ("R08", "orden: la mas antigua primero",
     [(LEC, "                              str(x[0][\"id\"])), reverse=True)\n", "                              str(x[0][\"id\"])))\n")],
     [T211 + "test_orden_mas_reciente_primero_y_detalle_con_reabrir"], None),
    ("R09", "no suma: las resueltas entran en el recuento de pendientes",
     [(LEC, '        "n": len(atencion),\n        "por_pagar"', '        "n": len(atencion) + resueltas_mes(sesion, hoy)["n"],\n        "por_pagar"')],
     [T211 + "test_no_suma_a_pendientes"], None),
    # ---------------------------------------------------------------- UI
    ("X01", "UI: el apartado se abre desplegado",
     [(PEND, "  const [resueltasAbiertas, setResueltasAbiertas] = useState(false);\n",
       "  const [resueltasAbiertas, setResueltasAbiertas] = useState(true);\n")],
     [JEST + "plegado por defecto"], None),
    ("X02", "UI: el recuento no es el del servidor",
     [(PEND, "fontVariant: ['tabular-nums'] }]}>{r.n}</Text>", "fontVariant: ['tabular-nums'] }]}>{r.filas.length - 1}</Text>")],
     [JEST + "plegado por defecto"], None),
    ("X03", "UI: una OMITIDA no dice «No hubo»",
     [(DOMP, "  if (f.estado === 'OMITIDA') return 'No hubo';\n", "")],
     [JEST + "etiquetas"], None),
    ("X04", "UI: «Pagada» aunque no tenga registro activo",
     [(DOMP, "  const completa = f.estado_derivado === null && f.importe_esperado !== null", "  const completa = f.importe_esperado !== null")],
     [JEST + "etiquetas"], None),
    ("X05", "UI: tocar la fila no abre el detalle",
     [(PEND, "      onPress={() => p.onDetalle(f)}\n      style=", "      onPress={() => undefined}\n      style=")],
     [JEST + "sin swipe: tocar la fila"], None),
    ("X06", "UI: la fecha objetivo se rotula como fecha de resolucion (sin procedencia)",
     [(DOMP, "f.resuelta_por === 'OBJETIVO' ? `prevista el ${dia}` : dia", "dia")],
     [JEST + "procedencia de la fecha"], None),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(tests: list[str]) -> int:
    """pytest por suite (api con su rootdir; backend aparte) y Jest en mobile/. rc != 0 si alguno falla."""
    api = [t for t in tests if t.startswith("tests/api/")]
    resto = [t for t in tests if t.startswith("tests/") and not t.startswith("tests/api/")]
    jest = [t[len("jest:"):] for t in tests if t.startswith("jest:")]
    rc = 0
    for grupo, extra in ((api, ["--rootdir=tests/api"]), (resto, [])):
        if not grupo:
            continue
        cmd = [sys.executable, "-m", "pytest", *grupo, "-q", "-x", "-p", "no:cacheprovider", *extra]
        rc = rc or subprocess.run(cmd, cwd=RAIZ, capture_output=True).returncode
    npx = "npx.cmd" if os.name == "nt" else "npx"
    for t in jest:
        fichero, patron = t.split("::", 1)
        cmd = [npx, "jest", fichero, "-t", patron, "--silent"]
        rc = rc or subprocess.run(cmd, cwd=RAIZ / "mobile", capture_output=True).returncode
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


def anotar(salida: pathlib.Path | None, linea: str) -> None:
    print(linea, flush=True)
    if salida is not None:
        with salida.open("a", encoding="utf-8") as f:
            f.write(linea + "\n")
            f.flush()
            os.fsync(f.fileno())


def main() -> None:
    if not os.getenv("GAPTO_TEST_DATABASE_URL"):
        sys.exit("Falta GAPTO_TEST_DATABASE_URL (base local desechable).")
    if recuperar_si_pendiente():
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    solo = None
    if "--solo" in sys.argv:
        solo = set(sys.argv[sys.argv.index("--solo") + 1].split(","))
    salida = pathlib.Path(sys.argv[sys.argv.index("--salida") + 1]) if "--salida" in sys.argv else None
    elegidos = [mu for mu in MUTANTES if solo is None or mu[0] in solo]
    preflight = sorted({t for mu in elegidos for t in mu[3]})
    if correr(preflight) != 0:
        sys.exit("PREFLIGHT ROJO: no se muta nada.")
    veredictos = []
    for mid, desc, cambios, tests, equivalencia in elegidos:
        ficheros = sorted({c[0] for c in cambios})
        originales = {f: (RAIZ / f).read_bytes() for f in ficheros}
        textos = {f: b.decode("utf-8") for f, b in originales.items()}
        aplicable = True
        for f, texto, sustituto in cambios:
            if textos[f].count(texto) != 1:
                aplicable = False
                break
            textos[f] = textos[f].replace(texto, sustituto)
        if not aplicable:
            v = (mid, "NO_CLASIFICABLE", "transformacion no aplicable", desc)
            veredictos.append(v)
            anotar(salida, " | ".join(v))
            continue
        JOURNAL.write_text(json.dumps({"mutante": mid, "ficheros": [
            {"fichero": f, "original_hex": originales[f].hex(), "sha256": sha(originales[f])} for f in ficheros
        ]}), encoding="utf-8")
        resultado = "NO_CLASIFICABLE"
        try:
            for f in ficheros:
                (RAIZ / f).write_bytes(textos[f].encode("utf-8"))
            resultado = "MUERTO" if correr(tests) != 0 else "VIVO"
        finally:
            ok = True
            for f in ficheros:
                (RAIZ / f).write_bytes(originales[f])
                ok = ok and sha((RAIZ / f).read_bytes()) == sha(originales[f])
            JOURNAL.unlink(missing_ok=True)
        if resultado == "VIVO" and equivalencia:
            resultado = "EQUIVALENTE"
        nota = f"{desc} [equivalente: {equivalencia}]" if resultado == "EQUIVALENTE" else desc
        v = (mid, resultado if ok else "NO_CLASIFICABLE",
             ",".join(sorted({pathlib.Path(t.split("::")[0].replace("jest:", "")).name for t in tests})), nota)
        veredictos.append(v)
        anotar(salida, " | ".join(v))
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    equivalentes = sum(1 for v in veredictos if v[1] == "EQUIVALENTE")
    anotar(salida, f"RESUMEN {muertos} muertos, {equivalentes} equivalentes documentados, "
                   f"{len(veredictos) - muertos - equivalentes} otros / {len(veredictos)}")
    sys.exit(0 if muertos + equivalentes == len(veredictos) else 1)


if __name__ == "__main__":
    main()
