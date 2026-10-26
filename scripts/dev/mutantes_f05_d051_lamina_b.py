# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_d051_lamina_b.py
# Ruta: scripts/dev/mutantes_f05_d051_lamina_b.py
# Descripcion: Arnes de mutacion de la lamina B (F05-D051 paso 8;
#   D-F0507L-03: una posicion CERRADA es «0,00 € · Saldado», nunca «Sin
#   determinar», y con apertura desconocida añade «Importe inicial
#   desconocido»). Un mutante por guarda nueva o modificada; resultado MUERTO
#   o EQUIVALENTE documentado.
#   Mismo motor que mutantes_f04_r3_q4.py:
#     - sustituciones de texto exacto (UNA ocurrencia) sobre el codigo del
#       repositorio (sin sustituciones en memoria);
#     - journal durable ANTES de tocar el primer byte; si al arrancar hay un
#       journal pendiente: restaura, verifica el SHA-256 y aborta;
#     - preflight verde de los discriminantes antes del primer mutante;
#     - tras cada mutante se restaura y se verifica la identidad byte a byte;
#     - el veredicto de CADA mutante se escribe a disco en cuanto se conoce
#       (--salida, append + fsync);
#     - veredicto: MUERTO | VIVO | NO_CLASIFICABLE (EQUIVALENTE si se declara).
#   Discriminantes: el bloque «Lámina B» (y el caso C4 de «Pendiente con») de mobile/__tests__/reparto.test.tsx
#   (jest --runInBand) y, con --e2e, ademas el E2E web
#   e2e_f05_d051_lamina_b.py (lanzador indicado en --lanzador: export web del
#   arbol mutado, base dev recreada en el cluster desechable). Con --e2e un
#   mutante es MUERTO si falla jest o el E2E, y se anota cada uno por separado.
#   Uso: python scripts/dev/mutantes_f05_d051_lamina_b.py [--solo ID,ID]
#        [--salida fichero] [--e2e --lanzador <ps1> --dist <carpeta> --evidencia <carpeta>]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F05-D051 paso 8; lamina B D-F0507L-03)
# Version: 0.2.0 (F05-D052 paso 3 · lamina B, F05 §66.2): texto «Saldo inicial desconocido» y mutante B10 (una ACTIVA con saldo desconocido vuelve a decir «Saldo inicial desconocido»).
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f05_d051_lamina_b.journal.json"
DOM = "mobile/src/domain/reparto.ts"
COR = "mobile/src/screens/CorregirRepartoScreen.tsx"
PEN = "mobile/src/screens/PendienteConScreen.tsx"
JEST_FICHERO = "__tests__/reparto.test.tsx"
JEST_FILTRO = "Lámina B|C4: con un saldo desconocido"  # F05-D052: C4 discrimina B10

SALDO_CERRADA = "    saldo: x.saldo === null ? TEXTO_SALDADO : `${formatearEur(x.saldo)} · ${TEXTO_SALDADO}`,\n"
INICIAL = "    inicial: x.apertura_indeterminada ? TEXTO_SALDO_INICIAL_DESCONOCIDO : null,\n"

#: (id, descripcion, [(fichero, texto, sustituto)], usa_e2e, equivalencia o None)
MUTANTES = [
    ("B1", "dominio: una CERRADA muestra «Sin determinar»",
     [(DOM, SALDO_CERRADA, "    saldo: 'Sin determinar',\n")], True, None),
    ("B2", "dominio: se omite «Saldo inicial desconocido» en una CERRADA con apertura desconocida",
     [(DOM, INICIAL, "    inicial: null,\n")], True, None),
    ("B3", "dominio: «Saldo inicial desconocido» en cualquier CERRADA (indicador ignorado)",
     [(DOM, INICIAL, "    inicial: TEXTO_SALDO_INICIAL_DESCONOCIDO,\n")], True, None),
    ("B4", "dominio: la etiqueta accesible pierde la linea de saldo inicial",
     [(DOM, "  return inicial ? `${linea.replace(/\\.$/, '')}. ${inicial}` : linea;", "  return linea;")], True, None),
    ("B5", "Corregir reparto: ignora el estado (una CERRADA sale «pendiente 0,00 €»)",
     [(COR, "const tp = textoPosicion(x.posicion);", "const tp = textoPosicion({ ...x.posicion, estado: 'ACTIVA' });")], True, None),
    ("B6", "Corregir reparto: no pinta la linea «Saldo inicial desconocido»",
     [(COR, "{tp.inicial ? (", "{false ? (")], True, None),
    ("B7", "Pendiente con · exito: ignora el estado (una CERRADA sale «Sigue pendiente: 0,00 €»)",
     [(PEN, "const tp = textoPosicion(r);", "const tp = textoPosicion({ ...r, estado: 'ACTIVA' });")], True, None),
    ("B8", "Pendiente con · exito: no pinta la linea «Saldo inicial desconocido»",
     [(PEN, '{tp.inicial ? <Text testID="posicion-exito-inicial"', '{false ? <Text testID="posicion-exito-inicial"')], False, None),
    ("B9", "Pendiente con · lista: importe con textoSaldo en vez de textoPosicion",
     [(PEN, "{textoPosicion(x).saldo}</Text>", "{textoSaldo(x.saldo)}</Text>")], False,
     "la lista solo recibe ACTIVAS (activasDe filtra estado === 'ACTIVA'), y para una ACTIVA "
     "textoPosicion(x).saldo === textoSaldo(x.saldo); el cambio es defensivo, sin salida observable distinta"),
    ("B10", "Pendiente con · lista: una ACTIVA con saldo desconocido vuelve a decir «Saldo inicial desconocido» (F05 §66.2)",
     [(PEN, "                    ? textoPosicion(x).inicial\n                    : [",
       "                    ? textoPosicion(x).inicial\n                    : x.saldo === null && x.estado !== 'CERRADA'\n"
       "                    ? 'Saldo inicial desconocido'\n                    : [")], True, None),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr_jest() -> int:
    cmd = ["npx.cmd" if os.name == "nt" else "npx", "jest", JEST_FICHERO, "--runInBand", "-t", JEST_FILTRO]
    return subprocess.run(cmd, cwd=RAIZ / "mobile", capture_output=True).returncode


def _leer_log(ruta: pathlib.Path) -> str:
    b = ruta.read_bytes() if ruta.exists() else b""
    if b.startswith(b"\xff\xfe") or b[1:2] == b"\x00":
        return b.decode("utf-16", errors="replace")
    return b.decode("utf-8", errors="replace")


def correr_e2e(args: dict, nombre: str) -> int:
    """Export del arbol (mutado o no) y E2E web; 0 solo si el E2E imprime PASS y rc=0."""
    salida = pathlib.Path(args["evidencia"]) / nombre
    cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", args["lanzador"],
           "-Script", "e2e_f05_d051_lamina_b.py", "-Salida", str(salida), "-Repo", str(RAIZ),
           "-Dist", args["dist"], "-Exportar"]
    subprocess.run(cmd, cwd=RAIZ, capture_output=True)
    log = _leer_log(salida / "e2e.log")
    return 0 if ("PASS " in log and "rc=0" in log) else 1


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


def _arg(nombre: str) -> str | None:
    return sys.argv[sys.argv.index(nombre) + 1] if nombre in sys.argv else None


def main() -> None:
    if recuperar_si_pendiente():
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    solo = set(_arg("--solo").split(",")) if _arg("--solo") else None
    salida = pathlib.Path(_arg("--salida")) if _arg("--salida") else None
    e2e = None
    if "--e2e" in sys.argv:
        e2e = {"lanzador": _arg("--lanzador"), "dist": _arg("--dist"), "evidencia": _arg("--evidencia")}
        if not all(e2e.values()):
            sys.exit("--e2e exige --lanzador, --dist y --evidencia.")
    elegidos = [mu for mu in MUTANTES if solo is None or mu[0] in solo]
    if correr_jest() != 0:
        sys.exit("PREFLIGHT ROJO (jest): no se muta nada.")
    anotar(salida, "PREFLIGHT jest verde")
    if e2e and any(mu[3] for mu in elegidos):
        if correr_e2e(e2e, "preflight") != 0:
            sys.exit("PREFLIGHT ROJO (E2E): no se muta nada.")
        anotar(salida, "PREFLIGHT e2e verde")
    veredictos = []
    for mid, desc, cambios, usa_e2e, equivalencia in elegidos:
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
        resultado, detalle = "NO_CLASIFICABLE", ""
        try:
            for f in ficheros:
                (RAIZ / f).write_bytes(textos[f].encode("utf-8"))
            rj = correr_jest()
            detalle = f"jest={'FALLA' if rj else 'pasa'}"
            muerto = rj != 0
            if e2e and usa_e2e:
                re2e = correr_e2e(e2e, f"mutante_{mid}")
                detalle += f" e2e={'FALLA' if re2e else 'pasa'}"
                muerto = muerto or re2e != 0
            resultado = "MUERTO" if muerto else "VIVO"
        finally:
            ok = True
            for f in ficheros:
                (RAIZ / f).write_bytes(originales[f])
                ok = ok and sha((RAIZ / f).read_bytes()) == sha(originales[f])
            JOURNAL.unlink(missing_ok=True)
        if resultado == "VIVO" and equivalencia:
            resultado = "EQUIVALENTE"
        nota = f"{desc} [equivalente: {equivalencia}]" if resultado == "EQUIVALENTE" else desc
        v = (mid, resultado if ok else "NO_CLASIFICABLE", detalle, nota)
        veredictos.append(v)
        anotar(salida, " | ".join(v))
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    equivalentes = sum(1 for v in veredictos if v[1] == "EQUIVALENTE")
    anotar(salida, f"RESUMEN {muertos} muertos, {equivalentes} equivalentes documentados, "
                   f"{len(veredictos) - muertos - equivalentes} otros / {len(veredictos)}")
    sys.exit(0 if muertos + equivalentes == len(veredictos) else 1)


if __name__ == "__main__":
    main()
