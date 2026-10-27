# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_d053_o3.py
# Ruta: scripts/dev/mutantes_f05_d053_o3.py
# Descripcion: Arnes de mutacion de la correccion O3 (F05-D053 §67.2, opcion 1;
#   AJ-F0507G4-05). Mismo motor que mutantes_f05_d052_ui.py (journal durable,
#   preflight verde, restauracion verificada por SHA-256, veredicto a disco en
#   cuanto se conoce), solo con Jest. Un mutante por guarda nueva: el rechazo
#   CATEGORIA_NO_ELEGIBLE de la propuesta vuelve a retirar la cuenta (ambas
#   propuestas), deja de invalidar la categoria (ambas), la invalidacion borra la
#   cuenta, no se marca, cambia el motivo, la guarda de la categoria elegida en el
#   dominio y la de respuesta obsoleta.
#   Uso: python scripts/dev/mutantes_f05_d053_o3.py [--solo ID,ID] [--salida fichero]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F05-D053 paso 1 · O3)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f05_d053_o3.journal.json"

REG = "mobile/src/screens/RegistroGastoScreen.tsx"
PRE = "mobile/src/domain/preferencias.ts"
PR = "jest:__tests__/preferencias_registro.test.tsx::"
RT = "jest:__tests__/registro_tipo.test.tsx::O3"

#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    ("O301", "O3: el rechazo de la propuesta vuelve a retirar la cuenta (SIN_PROPUESTA tras invalidar)",
     [(REG, "      if (r.tipo === 'RECHAZADO' && categoriaNoValida(categoriaId, r.codigo)) return;",
       "      if (r.tipo === 'RECHAZADO') categoriaNoValida(categoriaId, r.codigo);")],
     [PR + "O3: la propuesta de la categor"], None),
    ("O302", "O3 (registro por tipo): el rechazo vuelve a retirar la cuenta",
     [(REG, "        if (r2.tipo === 'RECHAZADO' && categoriaNoValida(categoriaId, r2.codigo)) return;",
       "        if (r2.tipo === 'RECHAZADO') categoriaNoValida(categoriaId, r2.codigo);")], [RT], None),
    ("O303", "O3: el rechazo se trata como SIN_PROPUESTA (comportamiento anterior)",
     [(REG, "      if (r.tipo === 'RECHAZADO' && categoriaNoValida(categoriaId, r.codigo)) return;\n", "")],
     [PR + "O3: la propuesta de la categor"], None),
    ("O304", "O3 (registro por tipo): el rechazo se trata como SIN_PROPUESTA",
     [(REG, "        if (r2.tipo === 'RECHAZADO' && categoriaNoValida(categoriaId, r2.codigo)) return;\n", "")], [RT], None),
    ("O305", "O3: la invalidacion tambien borra la cuenta",
     [(PRE, "  return { ...b, categoria: { estado: 'PENDIENTE' } };",
       "  return { ...b, categoria: { estado: 'PENDIENTE' }, cuentaId: null, cuentaOrigen: 'PENDIENTE', cuentaPropuesta: null };")],
     [PR + "O3"], None),
    ("O306", "O3: la categoria no se marca no valida (sin motivo visible)",
     [(REG, "    setCategoriaInvalida({ nombre: nodo?.nombre ?? '', codigo: CODIGO_CATEGORIA_NO_DISPONIBLE });\n", "")],
     [PR + "O3: la propuesta de la categor"], None),
    ("O307", "O3: motivo distinto del de §67.2",
     [(PRE, "export const TEXTO_CATEGORIA_NO_DISPONIBLE = 'Esta categoría ya no está disponible. Elige otra categoría.';",
       "export const TEXTO_CATEGORIA_NO_DISPONIBLE = 'Elige otra categoría.';")],
     [PR + "O3: la propuesta de la categor"], None),
    ("O308", "O3 (dominio): invalida aunque la categoria elegida sea otra",
     [(PRE, "  if (b.categoria.estado !== 'CATEGORIA' || b.categoria.id !== categoriaId) return null;",
       "  if (b.categoria.estado !== 'CATEGORIA') return null;")],
     [PR + "solo invalida la categor"], None),
    ("O309", "O3: una respuesta obsoleta de otra categoria se aplica sobre la seleccion posterior",
     [(REG, "    const caducada = () => n !== peticionPropuesta.current || !editable.current;",
       "    const caducada = () => !editable.current;")],
     [PR + "O3 respuesta obsoleta"], None),
    ("O310", "O3: la invalidacion no comprueba que la categoria rechazada siga elegida en la pantalla",
     [(REG, "    if (codigo !== 'CATEGORIA_NO_ELEGIBLE' || categoriaId === null || categoriaActual.current !== categoriaId) return false;",
       "    if (codigo !== 'CATEGORIA_NO_ELEGIBLE' || categoriaId === null) return false;")],
     [PR + "O3 respuesta obsoleta"],
     "defensiva: todo cambio de categoria con cuentas cargadas pide otra propuesta, y sin cuentas cargadas "
     "`cargarCuentas` ya incremento `peticionPropuesta`; en ambos casos `caducada` descarta la respuesta "
     "antigua antes de llegar aqui"),
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
