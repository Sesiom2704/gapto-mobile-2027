# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f06_t1_ux1.py
# Ruta: scripts/dev/mutantes_f06_t1_ux1.py
# Descripcion: Arnes de mutacion de UX-1 (T1-F06; mandato MANDATO_UX-1_v1.0 §5.1).
#   Mismo motor que mutantes_f05_d052_ui.py: sustitucion de TEXTO EXACTO con una
#   sola ocurrencia (0 o mas de 1 = NO_CLASIFICABLE y STOP del arnes), journal
#   durable (escrito y fsync antes del primer byte mutado); si al arrancar hay un
#   journal pendiente, restaura, verifica por SHA-256 y aborta; preflight verde de
#   todos los discriminantes; restauracion verificada por SHA-256 tras cada
#   mutante; veredicto a disco en cuanto se conoce (append + fsync); `npx`
#   resuelto con shutil.which; discriminantes `jest:<fichero>::<patron -t>`.
#   Mutantes exigibles: MU-M03-01, MU-M04-01..03, MU-M09-01..04 (con variantes
#   a/b donde el mandato dice «invierte o anula» u «ordena por importe o por
#   orden de llegada»); adicionales de M-03 (App) y M-07 (D-M2-04 y mascara).
#   Uso: python scripts/dev/mutantes_f06_t1_ux1.py [--solo ID,ID] [--salida fichero]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F06 T1 UX-1)
# Version: 0.2.0 (F06 T1 UX-1 · DUD-UX1-01, lote 26): mutantes MU-DUD01-01..03 de la salida por «Cancelar»
#   con cambios (`salir` de usarCambiosSinGuardar y su uso en el alta de categoria).
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
JOURNAL = RAIZ / ".mutantes_f06_t1_ux1.journal.json"

CSG = "mobile/src/components/CambiosSinGuardar.tsx"
NCA = "mobile/src/screens/NuevaCategoriaScreen.tsx"
APP = "mobile/App.tsx"
PRE = "mobile/src/domain/preferencias.ts"
GPR = "mobile/src/components/GuardarPreferencia.tsx"
PCO = "mobile/src/components/PendienteCompacto.tsx"
INT = "mobile/src/domain/intencion.ts"
FEC = "mobile/src/domain/fechas.ts"
M03 = "jest:__tests__/ux1_m03_mas.test.tsx::"
M04 = "jest:__tests__/ux1_m04_recordar.test.tsx::"
M07 = "jest:__tests__/ux1_m07_fechas.test.tsx::"
M09 = "jest:__tests__/ux1_m09_pendiente.test.tsx::"
B1N = "jest:__tests__/b1_campo_fecha_ux1.test.tsx::"

_TE_DEBE = "<Text testID={`${base}-te-debe`} style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{textoSaldo(d.te_debe)}</Text>"

#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    # ---------------------------------------------------------------- M-03 (Q-UX-06)
    ("MU-M03-01", "M-03: sin la comprobacion de cambios, «Mas» en «Mas» vuelve al menu aunque haya cambios",
     [(CSG, "  return hayCambios ? { tipo: 'PREGUNTAR' } : { tipo: 'MENU_MAS' };", "  return { tipo: 'MENU_MAS' };")],
     [M03 + "O-M03-01", M03 + "con cambios"], None),
    ("MU-M03-02", "M-03: la barra vuelve a `setDestino` (no regresa al menu «Mas»)",
     [(APP, "<BarraInferior actual={destino} onCambiar={pulsarBarra} />", "<BarraInferior actual={destino} onCambiar={setDestino} />")],
     [M03 + "vuelve al menú"], None),
    # ---------------------------------------------------------------- DUD-UX1-01 (salida por «Cancelar»)
    ("MU-DUD01-01", "DUD-01: `salir` sale sin comprobar los cambios",
     [(CSG, "    if (hay) setPendiente(() => accion);\n    else accion();", "    accion();")],
     [M03 + "DUD-UX1-01"], None),
    ("MU-DUD01-02", "DUD-01: el alta de categoria vuelve a salir por `onCancelar` sin pasar por `salir`",
     [(NCA, "onPress={() => salida.salir(p.onCancelar)}", "onPress={p.onCancelar}")],
     [M03 + "DUD-UX1-01 · App"], None),
    ("MU-DUD01-03", "DUD-01: «Descartar» cierra la hoja pero no sale",
     [(CSG, "        setPendiente(null);\n        a();", "        setPendiente(null);")],
     [M03 + "DUD-UX1-01"], None),
    # ---------------------------------------------------------------- M-04 (TR1-05)
    ("MU-M04-01", "M-04: casillas iniciales cambiadas (presupuestable siempre false)",
     [(PRE, "  const presupuestable = f.presupuestable !== (p?.presupuestable ?? null);", "  const presupuestable = false;")],
     [M04 + "O-M04-01"], None),
    ("MU-M04-02a", "M-04: se anula la comparacion con la preferencia guardada (nunca «Recordado»)",
     [(GPR, "  const recordado = fase.f === 'EDITANDO' && lista !== null && yaRecordado(", "  const recordado = false && lista !== null && yaRecordado(")],
     [M04 + "O-M04-02"], None),
    ("MU-M04-02b", "M-04: se invierte la comparacion con la preferencia guardada",
     [(GPR, "  const recordado = fase.f === 'EDITANDO' && lista !== null && yaRecordado(", "  const recordado = fase.f === 'EDITANDO' && lista !== null && !yaRecordado(")],
     [M04 + "O-M04-02"], None),
    ("MU-M04-03", "M-04: escribe una preferencia al montar la tarjeta",
     [(GPR, "        const l = await p.cliente.listarPreferencias();\n        if (vivo && l.tipo === 'OK') setLista(l.datos);",
       "        void p.cliente.altaPreferencia({ id: idAlta, tipo_hecho_id: 't', categoria_id: null, tercero_id: null, entidad_id: null, cuenta_default_id: null, presupuestable_default: null, prioridad: 100 });\n        const l = await p.cliente.listarPreferencias();\n        if (vivo && l.tipo === 'OK') setLista(l.datos);")],
     [M04 + "O-M04-03"], None),
    # ---------------------------------------------------------------- M-09 (TR1-05)
    ("MU-M09-01", "M-09: «Te debe» = suma de las partidas en lugar de `te_debe`",
     [(PCO, _TE_DEBE, _TE_DEBE.replace("{textoSaldo(d.te_debe)}", "{textoSaldo(d.posiciones.reduce((a, x) => a + Number(x.saldo ?? 0), 0).toFixed(2))}"))],
     [M09 + "O-M09-01"], None),
    ("MU-M09-02", "M-09: muestra el `neto` en lugar de `te_debe`",
     [(PCO, _TE_DEBE, _TE_DEBE.replace("{textoSaldo(d.te_debe)}", "{textoSaldo(d.neto)}"))],
     [M09 + "O-M09-01"], None),
    ("MU-M09-03a", "M-09: ordena las partidas por importe (mayor primero) en lugar de por fecha",
     [(PCO, "    if (fa && fb && fa !== fb) return fa < fb ? 1 : -1;", "    if (true) return Number(b.x.saldo ?? 0) - Number(a.x.saldo ?? 0);")],
     [M09 + "O-M09-02"], None),
    ("MU-M09-03b", "M-09: deja las partidas en el orden de llegada",
     [(PCO, "  conIndice.sort((a, b) => {", "  [].sort((a: any, b: any) => {")],
     [M09 + "O-M09-02"], None),
    ("MU-M09-04", "M-09: muestra el componente con SIN_POSICIONES",
     [(PCO, "  return p.neto_estado !== 'SIN_POSICIONES' && p.posiciones.length > 0;", "  return true;")],
     [M09 + "O-M09-03", M09 + "MU-M09-04"], None),
    # ---------------------------------------------------------------- M-07 (adicionales)
    ("MU-M07-01", "M-07/D-M2-04: esFechaIso vuelve a `new Date(a, m - 1, d)` (0–99 → 1900–1999)",
     [(INT, "  f.setFullYear(a, m - 1, d); // D-M2-04: new Date(a, …) convertiria 0–99 en 1900–1999".replace("convertiria", "convertiría"),
       "  f.setFullYear(a < 100 ? a + 1900 : a, m - 1, d);")],
     [M07 + "D-M2-04", B1N + "D-M2-04"], None),
    ("MU-M07-02", "M-07: la mascara no inserta barras",
     [(FEC, "  if (!conMascara) return t;", "  if (conMascara) return t;")],
     [M07 + "máscara: solo cifras"], None),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def npx() -> str:
    ruta = shutil.which("npx")
    if not ruta:
        sys.exit("npx no encontrado en el PATH")
    return ruta


def correr(tests: list[str]) -> int:
    """Jest en mobile/ (--runInBand), un fichero y patron por discriminante. rc != 0 si alguno falla."""
    rc = 0
    for t in tests:
        fichero, patron = t[len("jest:"):].split("::", 1)
        cmd = [npx(), "jest", fichero, "-t", patron, "--runInBand", "--silent", "--ci"]
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


def escribir_durable(ruta: pathlib.Path, texto: str) -> None:
    with ruta.open("w", encoding="utf-8") as f:
        f.write(texto)
        f.flush()
        os.fsync(f.fileno())


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
    # Aplicabilidad antes de nada: cada texto exacto tiene que aparecer UNA vez (si no, STOP del arnes).
    for mid, _d, cambios, _t, _e in elegidos:
        for f, texto, _s in cambios:
            n = (RAIZ / f).read_text(encoding="utf-8").count(texto)
            if n != 1:
                anotar(salida, f"{mid} | NO_CLASIFICABLE | {f}: {n} ocurrencias del texto exacto | STOP del arnes")
                sys.exit(3)
    preflight = sorted({t for mu in elegidos for t in mu[3]})
    if correr(preflight) != 0:
        anotar(salida, "PREFLIGHT ROJO: no se muta nada.")
        sys.exit(2)
    anotar(salida, f"PREFLIGHT VERDE: {len(preflight)} discriminantes")
    veredictos = []
    for mid, desc, cambios, tests, equivalencia in elegidos:
        ficheros = sorted({c[0] for c in cambios})
        originales = {f: (RAIZ / f).read_bytes() for f in ficheros}
        textos = {f: b.decode("utf-8") for f, b in originales.items()}
        for f, texto, sustituto in cambios:
            textos[f] = textos[f].replace(texto, sustituto)
        escribir_durable(JOURNAL, json.dumps({"mutante": mid, "ficheros": [
            {"fichero": f, "original_hex": originales[f].hex(), "sha256": sha(originales[f])} for f in ficheros
        ]}))
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
        if not ok:
            anotar(salida, f"STOP: restauracion no verificada tras {mid}")
            sys.exit(4)
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    equivalentes = sum(1 for v in veredictos if v[1] == "EQUIVALENTE")
    anotar(salida, f"RESUMEN {muertos} muertos, {equivalentes} equivalentes documentados, "
                   f"{len(veredictos) - muertos - equivalentes} otros / {len(veredictos)}")
    sys.exit(0 if muertos + equivalentes == len(veredictos) else 1)


if __name__ == "__main__":
    main()
