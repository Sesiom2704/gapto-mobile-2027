#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_mant_rb206.py
# Ruta: scripts/dev/mutantes_mant_rb206.py
# Descripcion: Arnes de mutacion del MANT N1 R-B2-06 (AJ-01; firma b88a3662…): un mutante por comportamiento nuevo del
#   cliente ante el timeout de la compra con hipoteca larga. Discriminantes: Jest
#   mobile/__tests__/compra_timeout_comprobacion.test.tsx. Motor identico al de scripts/dev/mutantes_f05_d052_ui.py
#   (sustitucion de texto exacto con UNA ocurrencia, journal durable antes de tocar el primer byte, restauracion verificada
#   por SHA-256, preflight verde, veredicto a disco en cuanto se conoce, --solo, --salida).
#     MRB-01  la pantalla vuelve a mostrar el falso aviso de fallo ante INDETERMINADO
#     MRB-02  sin comprobacion: un INDETERMINADO no se reenvia
#     MRB-03  la comprobacion reenvia con una intencion NUEVA (duplicaria la compra)
#     MRB-04  la compra usa el timeout general (10 s) en lugar de TIMEOUT_COMPRA_MS
#     MRB-05  un RECHAZADO definitivo tambien se reenvia
#   Uso: python scripts/dev/mutantes_mant_rb206.py [--solo ID,ID] [--salida fichero]
# Version: 0.1.0 (F06 T3-F06 · MANT N1 R-B2-06)
# ============================================================
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_mant_rb206.journal.json"

DOM = "mobile/src/domain/compra.ts"
PAT = "mobile/src/api/patrimonio.ts"
SCR = "mobile/src/screens/CompraScreen.tsx"
J = "jest:__tests__/compra_timeout_comprobacion.test.tsx::"

#: (id, descripcion, [(fichero, texto, sustituto)], [tests], equivalencia_o_None)
MUTANTES = [
    ("MRB-01", "pantalla: falso aviso «No se ha podido confirmar…» ante INDETERMINADO",
     [(SCR, "if (res.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: TEXTO_COMPRA_SIN_CONFIRMAR });",
       "if (res.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: TEXTO_INDETERMINADO_COMPRA });")],
     [J + "timeout persistente"], None),
    ("MRB-02", "dominio: un INDETERMINADO no se reenvia (sin comprobacion)",
     [(DOM, "while (respuesta.tipo === 'INDETERMINADO' && comprobaciones < n) {",
       "while (false && respuesta.tipo === 'INDETERMINADO' && comprobaciones < n) {")],
     [J + "INDETERMINADO y después OK", J + "timeout y la comprobación confirma"], None),
    ("MRB-03", "pantalla: la comprobacion reenvia con una intencion NUEVA (duplicaria)",
     [(SCR, "enviarCompraComprobando(() => p.patrimonio.registrarCompra(p.vista.id, cuerpo),",
       "enviarCompraComprobando(() => p.patrimonio.registrarCompra(p.vista.id, { ...cuerpo, intencion_id: p.nuevoId() }),")],
     [J + "timeout y la comprobación confirma", J + "timeout persistente"], None),
    ("MRB-04", "api: la compra usa el timeout general",
     [(PAT, "const llamarCompra = crearLlamada({ ...cfg, timeoutMs: Math.max(cfg.timeoutMs, TIMEOUT_COMPRA_MS) }, fetchImpl);",
       "const llamarCompra = crearLlamada(cfg, fetchImpl);")],
     [J + "registrarCompra no se corta"], None),
    ("MRB-05", "dominio: un RECHAZADO definitivo tambien se reenvia",
     [(DOM, "while (respuesta.tipo === 'INDETERMINADO' && comprobaciones < n) {",
       "while (respuesta.tipo !== 'OK' && comprobaciones < n) {")],
     [J + "un RECHAZADO es definitivo"], None),
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
