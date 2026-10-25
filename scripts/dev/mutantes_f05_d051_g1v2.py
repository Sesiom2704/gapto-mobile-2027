# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_d051_g1v2.py
# Ruta: scripts/dev/mutantes_f05_d051_g1v2.py
# Descripcion: Arnes de mutacion de F05-D051 paso 9.1 (G1 v2, instrumentacion
#   por paso, solo __DEV__). Mismo motor que mutantes_f05_06_m5b_resueltas.py
#   (journal durable, preflight verde, restauracion verificada por SHA-256,
#   veredicto a disco en cuanto se conoce), solo con Jest (no necesita base de
#   datos). Un mutante por guarda nueva: emision fuera de __DEV__ (App, g1Paso,
#   g1Cambio, g1Suscribir), correlacion e identificador de ensayo (pasos del
#   ensayo anterior, abandonado sin sus pasos, sin `sesion`, reloj no relativo
#   al t0), tope de pasos, despacho de `cambio:` y via de la categoria (arbol y
#   chip).
#   Uso: python scripts/dev/mutantes_f05_d051_g1v2.py [--solo ID,ID] [--salida fichero]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F05-D051 paso 9.1 · G1 v2)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f05_d051_g1v2.journal.json"

G1 = "mobile/src/dev/g1.ts"
APP = "mobile/App.tsx"
SEL = "mobile/src/components/SelectorCategorias.tsx"
REG = "mobile/src/screens/RegistroGastoScreen.tsx"
INS = "jest:__tests__/g1_instrumentacion.test.ts::"
PAS = "jest:__tests__/g1_pasos.test.tsx::"

#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    # ---------------------------------------------------------------- fuera de __DEV__
    ("G01", "App: la traza llega a las pantallas tambien fuera de __DEV__",
     [(APP, "  const trazaG1 = __DEV__ ? g1Traza : undefined;\n", "  const trazaG1 = g1Traza;\n")],
     [PAS + "fuera de __DEV__"], None),
    ("G02", "g1Paso: sin la guarda de __DEV__ (guarda hitos fuera de desarrollo)",
     [(G1, "  if (!dev || !abierto) return;\n  if (abierto.pasos.length", "  if (!abierto) return;\n  if (abierto.pasos.length")],
     [INS + "g1Paso, g1Cambio y g1Traza no guardan nada"], None),
    ("G03", "g1Suscribir: se suscribe a teclado y AppState fuera de __DEV__",
     [(G1, "  if (!dev) return () => undefined;\n  const subs", "  const subs")],
     [INS + "g1Suscribir no se suscribe", INS + "flujo completo sin ninguna"], None),
    ("G04", "g1Cambio: sin la guarda de __DEV__",
     [(G1, "  if (!dev || !abierto) return;\n  const primero", "  if (!abierto) return;\n  const primero")],
     [INS + "g1Paso, g1Cambio y g1Traza no guardan nada"],
     "g1Cambio solo escribe a traves de g1Paso con el mismo `dev`, cuya guarda (G02) corta; la guarda propia es "
     "defensa en profundidad y su ausencia no cambia nada observable"),
    # ---------------------------------------------------------------- correlacion e id de ensayo
    ("G05", "correlacion: el ensayo nuevo hereda los pasos del anterior",
     [(G1, "abierto = { seq: secuencia, origen, t0: t, pasos: [], omitidos: 0 };",
       "abierto = { seq: secuencia, origen, t0: t, pasos: abierto?.pasos ?? [], omitidos: 0 };")],
     [INS + "cada ensayo lleva solo sus pasos"], None),
    ("G06", "correlacion: el ensayo abandonado se escribe sin sus pasos",
     [(G1, "  if (abierto) escribir(log, abierto, { resultado: 'ABANDONADO'", "  if (abierto) escribir(log, { ...abierto, pasos: [] }, { resultado: 'ABANDONADO'")],
     [INS + "cada ensayo lleva solo sus pasos"], None),
    ("G07", "id de ensayo: la linea pierde `sesion` (seq repetida tras una recarga)",
     [(G1, "JSON.stringify({ v: 2, sesion, seq: a.seq,", "JSON.stringify({ v: 2, seq: a.seq,")],
     [INS + "los hitos viajan en orden"], None),
    ("G08", "reloj: el hito no es relativo al t0 del ensayo",
     [(G1, "abierto.pasos.push({ e: evento, ms: round(reloj() - abierto.t0),", "abierto.pasos.push({ e: evento, ms: round(reloj()),")],
     [INS + "los hitos viajan en orden"], None),
    # ---------------------------------------------------------------- contenido
    ("G09", "tope: un paso de mas antes de contar omitidos",
     [(G1, "  if (abierto.pasos.length >= G1_MAX_PASOS) {", "  if (abierto.pasos.length > G1_MAX_PASOS) {")],
     [INS + "tope de pasos"], None),
    ("G10", "g1Traza: `cambio:` no va a g1Cambio (un hito por tecla)",
     [(G1, "  if (evento.startsWith('cambio:')) return g1Cambio(evento.slice('cambio:'.length), dev);\n", "")],
     [INS + "primer cambio y UN", PAS + "caso 5 en __DEV__"], None),
    ("G11", "selector: la eleccion en el arbol se traza con otra via",
     [(SEL, "    if (p.esSeleccionable(n)) elegirCon('arbol', n);", "    if (p.esSeleccionable(n)) elegirCon('sugerida', n);")],
     [PAS + "caso 5 en __DEV__"], None),
    ("G12", "registro: la via chip se traza con el selector abierto (y no con el chip)",
     [(REG, "    if (!selectorAbierto) p.traza?.('categoria_elegida', { via: 'chip' });", "    if (selectorAbierto) p.traza?.('categoria_elegida', { via: 'chip' });")],
     [PAS + "chip de"], None),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(tests: list[str]) -> int:
    """Jest en mobile/ (--runInBand), un fichero y patron por discriminante. rc != 0 si alguno falla."""
    npx = "npx.cmd" if os.name == "nt" else "npx"
    rc = 0
    for t in tests:
        fichero, patron = t[len("jest:"):].split("::", 1)
        cmd = [npx, "jest", fichero, "-t", patron, "--runInBand", "--silent", "--ci"]
        r = subprocess.run(cmd, cwd=RAIZ / "mobile", capture_output=True, text=True, encoding="utf-8", errors="replace")
        # Un patron que no casa con ningun test no discrimina: se trata como fallo de preflight.
        if r.returncode == 0 and "Tests:" in r.stderr and " passed" not in r.stderr.split("Tests:")[1].splitlines()[0]:
            return 2
        rc = rc or r.returncode
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
