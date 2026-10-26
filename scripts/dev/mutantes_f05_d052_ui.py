# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_d052_ui.py
# Ruta: scripts/dev/mutantes_f05_d052_ui.py
# Descripcion: Arnes de mutacion de la UI de F05-D052 (paso 2: C-03 C1–C4 y
#   espejo R6; paso 3: A′). Mismo motor que mutantes_f05_d051_g1v2.py
#   (journal durable, preflight verde, restauracion verificada por SHA-256,
#   veredicto a disco en cuanto se conoce), solo con Jest. Un mutante por
#   guarda nueva o modificada: foco y «Hecho» de A′ (siguiente obligatoria,
#   opcionales y «No lo se», cierre y desplazamiento, etiqueta VoiceOver);
#   C-03 (opcion solo en gastos, nada marcado, «Hecho» deshabilitado,
#   naturalezas y comercio excluidos, importe 0,01..total, payload sin
#   `atribucion`, `validar`, ruta de envio, textos tras el cobro, derecho
#   elegido, `entidad_id` del detalle, sin «Repartir», exito C3, rechazos y
#   devolucion bloqueada); R6 (igualdad, suma incompleta y codigo del servidor).
#   Uso: python scripts/dev/mutantes_f05_d052_ui.py [--solo ID,ID] [--salida fichero]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F05-D052 pasos 2 y 3 · UI)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f05_d052_ui.journal.json"

REG = "mobile/src/screens/RegistroGastoScreen.tsx"
MAG = "mobile/src/domain/magnitud.ts"
REE = "mobile/src/domain/reembolso.ts"
INT = "mobile/src/domain/intencion.ts"
ENV = "mobile/src/state/useEnvioGasto.ts"
PEN = "mobile/src/screens/PendienteConScreen.tsx"
ACT = "mobile/src/screens/ActividadScreen.tsx"
DEV = "mobile/src/domain/devolucion.ts"
SEL = "mobile/src/components/Reparto.tsx"
C2 = "mobile/src/components/Reembolso.tsx"
REP = "mobile/src/domain/reparto.ts"
GCO = "mobile/src/screens/GastoCompartidoScreen.tsx"
AP = "jest:__tests__/a_prima.test.tsx::"
C3 = "jest:__tests__/c03_reembolso.test.tsx::"
R6 = "jest:__tests__/reparto.test.tsx::R6"

#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    # ---------------------------------------------------------------- A′ (D-F0507L-07)
    ("AP01", "A′: al elegir la categoria no se abre el teclado en la primera obligatoria",
     [(REG, "    setFocoMagnitud(bloqueado ? null : primeraMagnitudPendiente(nuevas, conservadas, b.desconocidas ?? []));",
       "    setFocoMagnitud(null);")], [AP + "formulario"], None),
    ("AP02", "A′: «Hecho» no pasa a la siguiente obligatoria (va directo a presupuesto)",
     [(MAG, "  const m = ms.slice(i + 1).find((x) => x.obligatoria && !desconocidas.includes(x.magnitud_id));",
       "  const m = undefined as MagnitudPedida | undefined;")], [AP + "formulario"], None),
    ("AP03", "A′: «Hecho» tambien se para en las opcionales",
     [(MAG, "  const m = ms.slice(i + 1).find((x) => x.obligatoria && !desconocidas.includes(x.magnitud_id));",
       "  const m = ms.slice(i + 1).find((x) => !desconocidas.includes(x.magnitud_id));")], [AP + "varias magnitudes"], None),
    ("AP04", "A′: «Hecho» no salta las obligatorias marcadas «No lo se»",
     [(MAG, "  const m = ms.slice(i + 1).find((x) => x.obligatoria && !desconocidas.includes(x.magnitud_id));",
       "  const m = ms.slice(i + 1).find((x) => x.obligatoria);")], [AP + "No lo s"], None),
    ("AP05", "A′: el foco inicial ignora los valores ya conservados al cambiar de categoria",
     [(MAG, "x.obligatoria && !desconocidas.includes(x.magnitud_id) && (textos[x.magnitud_id] ?? '').trim() === ''",
       "x.obligatoria && !desconocidas.includes(x.magnitud_id)")], [AP + "cambio de categor"], None),
    ("AP06", "A′: tras la ultima, «Hecho» no cierra el teclado",
     [(REG, "    Keyboard.dismiss();\n", "")], [AP + "formulario"], None),
    ("AP07", "A′: tras la ultima, la pantalla no sube a presupuesto",
     [(REG, "    if (yPresupuesto.current !== null) formRef.current?.scrollTo(", "    if (false) formRef.current?.scrollTo(")], [AP + "A′1/A′2"], None),
    ("AP08", "A′: VoiceOver anuncia solo «Hecho»",
     [(REG, "export const ETIQUETA_HECHO = 'Hecho, siguiente campo';", "export const ETIQUETA_HECHO = 'Hecho';")], [AP + "accesible"], None),
    # ---------------------------------------------------------------- C-03 (F05 §66.A)
    ("C01", "C1: la opcion de reembolso aparece tambien en ingresos",
     [(REG, "            {!esIngreso && (!enviado || b.reembolso) ? (", "            {(!enviado || b.reembolso) ? (")], [C3 + "C1:"], None),
    ("C02", "C2: «Todo» viene marcado por defecto",
     [(REE, "Object.freeze({ terceroId: null, nombre: null, modo: null, importeTexto: '' })",
       "Object.freeze({ terceroId: null, nombre: null, modo: 'TODO' as ModoImporteReembolso | null, importeTexto: '' })")],
     [C3 + "C2: nada marcado"], None),
    ("C03", "C2: «Hecho» siempre activo",
     [(C2, '<BotonPrimario testID="reembolso-hecho" titulo="Hecho" deshabilitado={faltan.length > 0}',
       '<BotonPrimario testID="reembolso-hecho" titulo="Hecho" deshabilitado={false}')], [C3 + "C2: nada marcado"], None),
    ("C04", "C2: el selector admite cualquier naturaleza (ORGANISMO, OTRO, sin naturaleza)",
     [(SEL, ".filter((t) => t.enabled && naturalezas.includes(t.naturaleza as NaturalezaAdmitida) && !p.excluir.includes(t.id))",
       ".filter((t) => t.enabled && !p.excluir.includes(t.id))")], [C3 + "selector ofrece"], None),
    ("C05", "C2: el comercio del gasto aparece como quien te lo debe",
     [(C2, "excluir={p.comercioId ? [p.comercioId] : []}", "excluir={[]}")], [C3 + "selector ofrece"], None),
    ("C06", "dominio: el importe recuperable puede superar el total",
     [(REE, "centimos(imp.valor) >= 1 && centimos(imp.valor) <= centimos(total) ? imp.valor : null",
       "centimos(imp.valor) >= 1 ? imp.valor : null")], [C3 + "importe recuperable", C3 + "C2: nada marcado"], None),
    ("C07", "dominio: el importe recuperable admite 0,00 €",
     [(REE, "centimos(imp.valor) >= 1 && centimos(imp.valor) <= centimos(total) ? imp.valor : null",
       "centimos(imp.valor) >= 0 && centimos(imp.valor) <= centimos(total) ? imp.valor : null")], [C3 + "importe recuperable"], None),
    ("C08", "sellado: el payload C-03 conserva `atribucion`",
     [(INT, "  const { atribucion: _atribucion, ...comun } = sellar(b, intencionId).payload;", "  const comun = sellar(b, intencionId).payload;")],
     [C3 + "sellado", C3 + "C2→C3"], None),
    ("C09", "validar: no revisa el reembolso (comercio igual o total menor)",
     [(INT, "  if (tipo === 'GASTO' && b.reembolso) {", "  if (false && b.reembolso) {")], [C3 + "sellado", C3 + "comercio pasa"], None),
    ("C10", "envio: con reembolso se envia por la ruta del gasto pagado",
     [(ENV, "          : b.reembolso ? sellarReembolsable(b, nuevoId()) : sellar(b, nuevoId());", "          : sellar(b, nuevoId());")],
     [C3 + "C2→C3"], None),
    ("C11", "cobro: «Saldado» tambien con un cobro parcial",
     [(REE, "  if (r.estado === 'CERRADA' && centimos(r.saldo) === 0) return TEXTO_SALDADO_NO_INGRESO;", "  return TEXTO_SALDADO_NO_INGRESO;")],
     [C3 + "tras el cobro", C3 + "cobro parcial"], None),
    ("C12", "cobro: «Saldado» con saldo indeterminado",
     [(REE, "  if (r.saldo === null) return TEXTO_COBRO_REGISTRADO;", "  if (r.saldo === null) return TEXTO_SALDADO_NO_INGRESO;")],
     [C3 + "tras el cobro"], None),
    ("C13", "C4: «Pendiente con…» no abre el derecho elegido",
     [(PEN, "      if (x) setSel(x);\n", "")], [C3 + "dos derechos"], None),
    ("C14", "detalle: «Pendiente con» no pasa el `entidad_id` del derecho",
     [(ACT, "nombre: x.contraparte_nombre, entidadId: x.entidad_id });", "nombre: x.contraparte_nombre });")], [C3 + "posiciones_vinculadas"], None),
    ("C15", "formulario: con reembolso se sigue ofreciendo «Repartir»",
     [(REG, "            {!esIngreso && p.onGastoCompartido && !enviado && !b.reembolso ? (\n              <Chip testID=\"repartir\"",
       "            {!esIngreso && p.onGastoCompartido && !enviado ? (\n              <Chip testID=\"repartir\"")], [C3 + "C2→C3"], None),
    ("C16", "C3: el exito no separa lo que te deben",
     [(REG, "          {r.reembolso ? (", "          {false ? (")], [C3 + "C2→C3"], None),
    ("C17", "rechazos C-03: se muestra el mensaje tecnico del servidor",
     [(REG, "                    : MOTIVO_RECHAZO_REEMBOLSO[estado.codigo] && b.reembolso", "                    : false && b.reembolso")], [C3 + "rechazo"], None),
    ("C18", "devolucion: sin motivo propio para el gasto con derecho de cobro",
     [(DEV, "  GASTO_CON_DERECHO_DE_COBRO: 'Este gasto tiene", "  GASTO_CON_DERECHO_DE_COBRO_X: 'Este gasto tiene")], [C3 + "devoluci"], None),
    ("C19", "C4: el derecho de un reembolso usa la explicacion del reparto («te devuelve lo que pagaste por…»)",
     [(PEN, "esCobro ? (esDerechoReembolso(sel) ? TEXTO_COBRO_NO_INGRESO : TEXTO_NO_ES_INGRESO(nombre))", "esCobro ? TEXTO_NO_ES_INGRESO(nombre)")],
     [C3 + "dos derechos"], None),
    # ---------------------------------------------------------------- R6 (F05 §66.A.10)
    ("R6-1", "R6: la igualdad con alguna parte sin indicar no bloquea",
     [(REP, "  return r.invalidas === 0 && !r.excede && !r.sinIndicar && filas.some((f) => !f.importeTexto.trim());", "  return false;")], [R6], None),
    ("R6-2", "R6: la suma incompleta con alguna parte sin indicar tambien se bloquea",
     [(REP, "  return r.invalidas === 0 && !r.excede && !r.sinIndicar && filas.some((f) => !f.importeTexto.trim());",
       "  return r.invalidas === 0 && !r.excede && filas.some((f) => !f.importeTexto.trim());")], [R6], None),
    ("R6-3", "R6: el rechazo del servidor se explica con su mensaje libre",
     [(GCO, ": envio.codigo === CODIGO_SIN_MARGEN ? `No se ha registrado. ${TEXTO_REPARTO_SIN_MARGEN}`", ": false ? `No se ha registrado. ${TEXTO_REPARTO_SIN_MARGEN}`")], [R6], None),
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
