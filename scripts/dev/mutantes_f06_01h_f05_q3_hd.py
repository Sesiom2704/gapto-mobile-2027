# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f06_01h_f05_q3_hd.py
# Ruta: scripts/dev/mutantes_f06_01h_f05_q3_hd.py
# Descripcion: Arnes de mutacion de la reapertura nominal y acotada de F05 Q3-Hd (literal
#   LITERAL_REAPERTURA_F05_Q3_HD_v1.1, tabla de mutantes; mandato T3-F06 bloque 2 F06-01H v1.1 §11.5 y §12.1),
#   con resultado separado. Mismo motor que mutantes_f05_06_m5b_resueltas.py (journal durable, preflight verde,
#   restauracion verificada por SHA-256, veredicto a disco en cuanto se conoce). Un mutante por superficie:
#   MQ3-S1/S2 (marca de la cuota en las listas del servidor; S2 con su variante codigo: null), MQ3-C1/C2 (gesto y
#   accion rapida del cliente), MHD-S1/S2 (rol PRESTAMO_RECIBIDO del Hd y su predicado), MHD-C1/C2/C3 (nombre,
#   linea secundaria y detalle rapido del cliente). Discriminantes: test_297/test_298 (O-Q3-1/2, O-HD-1/2) y Jest
#   prevision_cuota_swipe / actividad_prestamo_recibido.
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable>
#        python -u scripts/dev/mutantes_f06_01h_f05_q3_hd.py [--solo ID,ID] [--salida fichero]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F06 T3-F06 bloque 2 F06-01H; literal F05 Q3-Hd v1.1, paso 9)
# Version: 0.2.0 (F06 T3-F06 bloque 2 F06-01H; enmienda 52ef5511…, firma 0f3e5633…, STOP_F06-T3-2_3 opcion A):
#   MQ3-C5 (lados() de SwipePrevision.tsx ofrece gestos sobre la fila de la cuota); discriminante Jest
#   prevision_cuota_lados (Q3-C5).
# Version: 0.3.0 (F06 T3 · MANT N1 arneses, AJ-03 del 19-11; enmienda 01): base limpia por mutante (cada llamada a correr clona la plantilla de GAPTO_TEST_DATABASE_URL y la elimina al terminar) y clasificacion de la muerte, con scripts/dev/base_limpia_mutante.py; sin cambios en mutaciones, discriminantes ni restauracion.
# Version: 0.4.0 (F06 T4 · D-C7-10, mandato 7041970a…; Q3-Hd v1.2 candidato): MQ3-C1 y MQ3-C5 se reescriben para la
#   regla nueva (sus lineas protegidas cambian: la cuota tiene el gesto «Pagado» solo con `gestoPagoCuota`); la mutacion
#   sigue siendo «ignorar la marca» y los discriminantes son los mismos ficheros Jest versionados. MQ3-S1/S2/S2b,
#   MQ3-C2 (texto intacto) y MHD-* sin cambios.
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import base_limpia_mutante  # MANT N1 arneses, AJ-03 del 19-11

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f06_01h_f05_q3_hd.journal.json"

LPREV = "backend/app/previsiones/lecturas.py"
DTOP = "backend/app/api/dto_prevision.py"
LACT = "backend/app/actividad/lecturas.py"
DOMP = "mobile/src/domain/prevision.ts"
TIT = "mobile/src/domain/titulos_dia.ts"
DACT = "mobile/src/domain/actividad.ts"
PACT = "mobile/src/screens/ActividadScreen.tsx"
T297 = "tests/api/test_297_f06_01h_f05_q3_listas.py::"
T298 = "tests/api/test_298_f06_01h_f05_actividad_hd.py::"
JQ3 = "jest:__tests__/prevision_cuota_swipe.test.ts::"
JHD = "jest:__tests__/actividad_prestamo_recibido.test.tsx::"
SWP = "mobile/src/components/SwipePrevision.tsx"
JC5 = "jest:__tests__/prevision_cuota_lados.test.tsx::"
LISTAS = [T297 + "test_o_q3_1_inicio_marca_solo_la_cuota", T297 + "test_o_q3_1_pendientes_marca_solo_la_cuota"]

MUTANTES = [
    ("MQ3-S1", "la lista no marca la fila de una cuota",
     [(LPREV, '            f["codigo"] = CODIGO_PREVISION_DE_CUOTA\n', '            pass\n')], LISTAS, None),
    ("MQ3-S2", "la marca se serializa en todas las filas",
     [(LPREV, '        if f["id"] in cuotas:\n            f["codigo"]', '        if True:\n            f["codigo"]')],
     LISTAS, None),
    ("MQ3-S2b", "variante de MQ3-S2: codigo: null en las filas ordinarias",
     [(DTOP, "    presupuestable: bool  # propuesta «De la prevision» del registro\n",
       "    presupuestable: bool  # propuesta «De la prevision» del registro\n    codigo: str | None = None\n")],
     LISTAS, None),
    ("MQ3-C1", "admiteSwipe ignora la marca",
     [(DOMP, "  if (f.codigo === 'PREVISION_DE_CUOTA') return gestoPagoCuota(f); // Q3-C2 v1.2: solo el gesto «Pagado» sin dudas (D-C7-10)\n",
       "")], [JQ3 + "Q3-C2"], None),
    ("MQ3-C2", "planRapidoPrevision ignora la marca",
     [(DOMP, "  if (f.codigo === 'PREVISION_DE_CUOTA') return null; // Q3-C3: comprobación propia, sin apoyarse en admiteSwipe\n",
       "")], [JQ3 + "Q3-C3"], None),
    ("MQ3-C5", "lados() ofrece gestos sobre la fila de la cuota",
     [(SWP, "    if (f.codigo === 'PREVISION_DE_CUOTA') {\n"
            "      // Q3-C5 v1.2 (D-C7-10): solo el lado principal «Pagado» y solo sin dudas; nunca «No hubo».\n"
            "      if (!gestoPagoCuota(f)) return {};\n"
            "      return { principal: { etiqueta: 'Pagado', icono: 'checkmark', tono: 'confirmar', onEjecutar: () => pagarCuota(f) } };\n"
            "    }\n",
       "")], [JC5 + "Q3-C5"], None),
    ("MHD-S1", "el rol del Hd vuelve a COBRO",
     [(LACT, '            elif c["importe"] > 0 and hid in desembolsos:\n', '            elif False:\n')],
     [T298 + "test_o_hd_1_lista_y_detalle_del_hd"], None),
    ("MHD-S2", "el rol se aplica a todo GDO con entrada (sin vinculo de nivel efecto a FINANCIACION)",
     [(LACT, "    return {r[0] for r in cur.fetchall()}\n\n\ndef _componer(",
       "    cur.execute(\"SELECT h.id FROM gapto.hechos_financieros h JOIN gapto.tipos_hecho th ON th.id = h.tipo_hecho_id \"\n"
       "                \"WHERE h.id = ANY(%s) AND th.codigo = 'GENERACION_DERECHO_OBLIGACION'\", (ids,))\n"
       "    return {r[0] for r in cur.fetchall()}\n\n\ndef _componer(")],
     [T298 + "test_o_hd_2_negativos_siguen_con_cobro_byte_a_byte"], None),
    ("MHD-C1", "nombreTipoFila ignora PRESTAMO_RECIBIDO",
     [(TIT, "  if (r.cuentas[0]?.rol === 'PRESTAMO_RECIBIDO') return 'Préstamo recibido'; // HD-C2: desembolso Hd, por rol\n",
       "")], [JHD + "HD-C2"], None),
    ("MHD-C2", "secundariaFila vuelve a la rama generica («Sin categoría»)",
     [(DACT, "  } else if (r.cuentas[0]?.rol === 'PRESTAMO_RECIBIDO') {\n", "  } else if (false) {\n")],
     [JHD + "HD-C3"], None),
    ("MHD-C3", "el detalle vuelve a «Cobrado en» / «Pagado con»",
     [(PACT, "d.cuentas[0]?.rol === 'PRESTAMO_RECIBIDO' ? 'Recibido en' : ", "")],
     [JHD + "HD-C4"], None),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@base_limpia_mutante.por_llamada
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
