# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_06_m5_swipe.py
# Ruta: scripts/dev/mutantes_f05_06_m5_swipe.py
# Descripcion: Arnes de mutacion del swipe de M5 (F05-06 M5 SWIPE, SWIPE2 y SWIPE3;
#   SWIPE-RULE, F09 §12.106 D-SWIPE-01; lamina SWIPE-01 v0.3). Mismo motor que
#   scripts/dev/mutantes_f05_06_m5.py, solo Jest: sustitucion de texto exacto (UNA
#   ocurrencia), journal durable antes del primer byte (si hay uno pendiente:
#   restaura, verifica y aborta), preflight verde, restauracion verificada por
#   SHA-256 tras cada mutante y veredicto a disco en cuanto se conoce. Un
#   discriminante que no ejecuta ningun test cuenta como ROJO.
#   Uso (desde la raiz del repo o cualquier sitio):
#     python scripts/dev/mutantes_f05_06_m5_swipe.py [--solo ID,ID] [--salida fichero]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F05-06 M5 SWIPE): accion rapida con «Deshacer» (MS01-MS13).
# Version: 0.2.0 (F05-06 M5 SWIPE2): tonos (rojo), accion destructiva, «No hubo»
#   con pagos, datos dudosos en Pendiente con, Repetir hoy y Categorias (MS14-MS21).
# Version: 0.3.0 (F05-06 M5 SWIPE3): lados sin invertir (global y por pantalla),
#   cierre de la fila abierta (tocar fuera, scroll, otra fila) y vibracion
#   (MS22-MS30); discriminante vacio = ROJO.
# Version: 0.4.0 (MANT-M5-ARNESES, AJ-M5-CIERRE-06): pasa de la evidencia a
#   scripts/dev/; la raiz se deduce del propio fichero (sin --raiz).
# ============================================================

from __future__ import annotations

import hashlib
import re
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f05_06_m5_swipe.journal.json"

AR = "mobile/src/components/AccionRapida.tsx"
DOM = "mobile/src/domain/prevision.ts"
ACT = "mobile/src/screens/ActividadScreen.tsx"
J = "jest:__tests__/accion_rapida.test.tsx::"
JG = "jest:__tests__/swipe_gestos.test.tsx::"
JP = "jest:__tests__/swipe_pantallas.test.tsx::"
PEN = "mobile/src/screens/PendienteConScreen.tsx"
REP = "mobile/src/domain/repetir.ts"
CAT = "mobile/src/screens/CategoriasAjustesScreen.tsx"
TER = "mobile/src/screens/TercerosAjustesScreen.tsx"
JDEV = "jest:__tests__/devolucion.test.tsx::"

MUTANTES = [
    ("MS01", "envio inmediato (sin esperar los 5 s)",
     [(AR, "    v.temporizador = setTimeout(() => void enviar(a.clave), ESPERA_DESHACER_MS);\n",
       "    void enviar(a.clave);\n")],
     [J + "gesto → aviso «Electricidad pagada"], None),
    ("MS02", "«Deshacer» que no cancela (la peticion sale igual)",
     [(AR, "    const v = vivas.current.get(clave);\n    if (!v || v.fase !== 'ESPERA') return;\n    if (v.temporizador)",
       "    const v = vivas.current.get(clave);\n    if (v) return;\n    if (v!.temporizador)")],
     [J + "«Deshacer» → 0 peticiones"], None),
    ("MS03", "swipe rapido con importe desconocido",
     [(DOM, "  if (f.importe_esperado === null) return null;\n  if (f.tipo !== 'GASTO'", "  if (false) return null;\n  if (f.tipo !== 'GASTO'")],
     [J + "si falta algo no hay acción rápida"], None),
    ("MS04", "dos intenciones por doble gesto (sin guarda de la fila viva)",
     [(AR, "    if (vivas.current.has(a.clave)) return false;\n", "    if (false) return false;\n")],
     [J + "doble gesto"], None),
    ("MS05", "identidad nueva en cada gesto (el reintento no es idempotente)",
     [(AR, "    const id = identidades.current.get(a.clave) ?? p.nuevoId();\n", "    const id = p.nuevoId();\n")],
     [J + "gesto nuevo tras un INDETERMINADO"], None),
    ("MS06", "rechazo tratado como exito (exito falso)",
     [(AR, "    if (r.tipo === 'OK') {\n      identidades", "    if (r.tipo !== 'INDETERMINADO') {\n      identidades")],
     [J + "rechazo del servidor"], None),
    ("MS07", "segundo plano no cancela la espera",
     [(AR, "      if (e === 'background') cancelarTodas();\n", "      if (false) cancelarTodas();\n")],
     [J + "segundo plano"], None),
    ("MS08", "desmontar no cancela la espera",
     [(AR, "      for (const v of vivas.current.values()) if (v.fase === 'ESPERA' && v.temporizador) clearTimeout(v.temporizador);\n", "")],
     [J + "se desmonta"], None),
    ("MS09", "cuenta prevista sin la capacidad de hoy",
     [(DOM, "  if (!lista || !lista.some((x) => x.cuenta_id === cuenta.id)) return null;\n", "  if (!lista) return null;\n")],
     [J + "si falta algo no hay acción rápida", J + "datos incompletos"], None),
    ("MS10", "fecha prevista en lugar de hoy",
     [(DOM, "    importe: f.importe_esperado, fecha: hoy,", "    importe: f.importe_esperado, fecha: f.fecha_hasta ?? hoy,")],
     [J + "acción rápida de un gasto", J + "gesto → aviso «Electricidad pagada"], None),
    ("MS11", "sin marcar la prevision como cubierta",
     [(DOM, "    conCategoria: !!f.categoria, propuestaSelf100: self100, marcar: true,\n", "    conCategoria: !!f.categoria, propuestaSelf100: self100, marcar: false,\n")],
     [J + "acción rápida de un gasto"], None),
    ("MS12", "abono rapido sin cuenta original",
     [(ACT, "!f.importe_total || !cuenta) return abrirAbono(f, null);", "!f.importe_total) return abrirAbono(f, null);")],
     [J + "sin cuenta original → la hoja"], None),
    ("MS13", "MU04 reubicado: el contenedor comun no captura el movimiento (el Pressable se lo queda)",
     [(AR, "      onMoveShouldSetPanResponderCapture: (_, g) => horizontal(g),", "      onMoveShouldSetPanResponderCapture: () => false,")],
     [JDEV + "P-DEV-04: el gesto real", J + "gesto real: a medias a la izquierda"], None),
    ("MS14", "rojo en un swipe: el tono de aviso pasa a critical",
     [(AR, "  if (tono === 'aviso') return { fondo: c.partialSurface, circulo: c.warning,", "  if (tono === 'aviso') return { fondo: c.partialSurface, circulo: c.critical,")],
     [JP + "tonos del swipe"], None),
    ("MS15", "accion destructiva en un swipe: «Más» de Pendiente con perdona la deuda",
     [(PEN, "onEjecutar: () => setSel(x) },", "onEjecutar: () => void p.cliente.perdonarPosicion(x.entidad_id, { intencion_id: p.nuevoId(), importe: x.saldo ?? '0', fecha: hoyIso }) },")],
     [JP + "«Más» abre las acciones"], None),
    ("MS16", "«No hubo» ofrecido con pagos enlazados",
     [(DOM, "  return f.estado === 'ABIERTA' && f.pagos === 0 && !f.con_realidad;", "  return f.estado === 'ABIERTA';")],
     [J + "«No hubo» no se ofrece con pagos enlazados"], None),
    ("MS17", "dato dudoso: Pendiente con salda con varias cuentas posibles (la primera)",
     [(PEN, "lista.length !== 1) {", "lista.length < 1) {")],
     [JP + "con varias cuentas posibles"], None),
    ("MS18", "dato dudoso: «Repetir hoy» con magnitudes",
     [(REP, "  if (!repetibleHoy(f) || d.magnitudes.length > 0) return null;", "  if (!repetibleHoy(f)) return null;")],
     [JP + "dominio: solo sin reparto", JP + "con magnitudes hay dudas"], None),
    ("MS19", "dato dudoso: «Repetir hoy» con reparto",
     [(REP, "  return f.estado_reparto === 'COMPLETA' && f.tu_parte === f.importe_total && !f.pendiente;", "  return f.estado_reparto === 'COMPLETA';")],
     [JP + "dominio: solo sin reparto", JP + "del café"], None),
    ("MS20", "dato dudoso: categoria con subcategorias activas desactivada por swipe",
     [(CAT, "    const conHijos = subcategoriasActivas(arbol, n.id).length > 0;", "    const conHijos = false;")],
     [JP + "categorías: sin subcategorías activas"], None),
    ("MS21", "«Desactivar» ofrecido en un tercero ya inactivo",
     [(TER, "    t.enabled\n      ? { etiqueta: 'Desactivar'", "    true\n      ? { etiqueta: 'Desactivar'")],
     [JP + "terceros: «Desactivar»"], None),
    ("MS22", "lados sin invertir en toda la app (principal a la derecha)",
     [(AR, "export const PRINCIPAL_SE_DESLIZA: DireccionSwipe = 'izquierda';", "export const PRINCIPAL_SE_DESLIZA: DireccionSwipe = 'derecha';")],
     [JG + "la acción principal se desliza a la izquierda", JG + "Pendientes: lados invertidos"], None),
    ("MS23", "lados sin invertir en una pantalla: Pendiente con",
     [(PEN, "principal={l.principal} alternativa={l.alternativa}>", "principal={l.alternativa} alternativa={l.principal}>")],
     [JG + "«Pendiente con»: izquierda del todo"], None),
    ("MS24", "lados sin invertir en una pantalla: Actividad",
     [(ACT, "<FilaDeslizable id={f.id} principal={p.principal} alternativa={p.alternativa}>", "<FilaDeslizable id={f.id} principal={p.alternativa} alternativa={p.principal}>")],
     [JG + "Actividad: izquierda del todo"], None),
    ("MS25", "tocar fuera no cierra la fila abierta",
     [(AR, "    if (filaAbierta && filaAbierta.clave !== boton) cerrarFilaAbierta();", "    if (false) cerrarFilaAbierta();")],
     [JG + "fila abierta: se cierra"], None),
    ("MS26", "el scroll no cierra la fila abierta",
     [(AR, "export const propsScrollSwipe = { onScrollBeginDrag: () => cerrarFilaAbierta() };", "export const propsScrollSwipe = { onScrollBeginDrag: () => undefined };")],
     [JG + "fila abierta: se cierra"], None),
    ("MS27", "abrir otra fila no cierra la anterior",
     [(AR, "        if (filaAbierta && filaAbierta.clave !== clave) cerrarFilaAbierta();", "        if (false) cerrarFilaAbierta();")],
     [JG + "fila abierta: se cierra"], None),
    ("MS28", "vibracion que falla en silencio (sin reserva)",
     [(AR, "    Vibration.vibrate(15);\n", "")],
     [JG + "si expo-haptics falla"], None),
    ("MS29", "vibra en cada movimiento pasado el umbral",
     [(AR, "        if (pasa && !pasado.current) vibrarUmbral();", "        if (pasa) vibrarUmbral();")],
     [JG + "vibración: una sola vez"], None),
    ("MS30", "impacto ligero (el que no se notaba en el iPhone)",
     [(AR, "    promesa = Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);", "    promesa = Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);")],
     [JG + "vibración: una sola vez"], None),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(tests: list[str]) -> int:
    npx = "npx.cmd" if os.name == "nt" else "npx"
    rc = 0
    for t in tests:
        fichero, patron = t[len("jest:"):].split("::", 1)
        cmd = [npx, "jest", fichero, "-t", patron, "--silent"]
        r = subprocess.run(cmd, cwd=RAIZ / "mobile", capture_output=True, text=True, encoding="utf-8", errors="replace")
        ejecutados = re.search(r"Tests:.*\d+ (passed|failed)", r.stdout + r.stderr)
        rc = rc or r.returncode or (0 if ejecutados else 1)  # un patron que no casa con ningun test es ROJO
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
    solo = set(sys.argv[sys.argv.index("--solo") + 1].split(",")) if "--solo" in sys.argv else None
    salida = pathlib.Path(sys.argv[sys.argv.index("--salida") + 1]) if "--salida" in sys.argv else None
    elegidos = [mu for mu in MUTANTES if solo is None or mu[0] in solo]
    preflight = sorted({t for mu in elegidos for t in mu[3]})
    if correr(preflight) != 0:
        sys.exit("PREFLIGHT ROJO: no se muta nada.")
    anotar(salida, f"PREFLIGHT verde ({len(preflight)} discriminantes)")
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
        v = (mid, resultado if ok else "NO_CLASIFICABLE",
             ",".join(sorted({pathlib.Path(t.split("::")[0].replace("jest:", "")).name for t in tests})), desc)
        veredictos.append(v)
        anotar(salida, " | ".join(v))
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    equivalentes = sum(1 for v in veredictos if v[1] == "EQUIVALENTE")
    anotar(salida, f"RESUMEN {muertos} muertos, {equivalentes} equivalentes documentados, "
                   f"{len(veredictos) - muertos - equivalentes} otros / {len(veredictos)}")
    sys.exit(0 if muertos + equivalentes == len(veredictos) else 1)


if __name__ == "__main__":
    main()
