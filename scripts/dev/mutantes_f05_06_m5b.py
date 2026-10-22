# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_06_m5b.py
# Ruta: scripts/dev/mutantes_f05_06_m5b.py
# Descripcion: Arnes de mutacion de F05-06 M5-B (F04-D065; F05 §61 F05-D047;
#   contrato M5-B §7: un mutante por guarda; 100 % muertos o equivalentes
#   documentados). Mismo motor que mutantes_f05_06_m5.py:
#     - sustituciones de texto exacto (UNA ocurrencia) y sus discriminantes:
#       nodeids de pytest (tests/api con su rootdir, tests/backend aparte) o
#       «jest:<fichero>::<patron>» (Jest del cliente, en mobile/);
#     - journal durable ANTES de tocar el primer byte; si al arrancar hay un
#       journal pendiente: restaura, verifica y aborta;
#     - preflight verde de todos los discriminantes antes del primer mutante;
#     - tras cada mutante se restaura y se verifica la identidad byte a byte;
#     - el veredicto de CADA mutante se escribe a disco en cuanto se conoce
#       (--salida, append + fsync);
#     - veredicto: MUERTO | VIVO | NO_CLASIFICABLE (EQUIVALENTE si se declara).
#   Guardas: motivo, estado, row_version, >=1 hecho ACTIVO bajo el lock,
#   uuid_sucesor (motor y adaptador), desviacion no persistida, recalculo y
#   auditoria; CANCELADA rechazada en el adaptador; acciones de la lectura;
#   guardas de la UI (motivo obligatorio, donde se ofrecen, version del
#   sucesor, misma identidad tras un fallo, rechazos explicados en la hoja).
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable>
#        python scripts/dev/mutantes_f05_06_m5b.py [--solo ID,ID] [--salida fichero]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F05-06 M5-B)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f05_06_m5b.journal.json"

SRV = "backend/app/services/previsiones_service.py"
EJP = "backend/app/api/ejecucion_prevision.py"
LEC = "backend/app/previsiones/lecturas.py"
COMP = "mobile/src/components/Prevision.tsx"
DOMM = "mobile/src/domain/prevision.ts"
DET = "mobile/src/screens/PrevisionDetalleScreen.tsx"
T14J = "tests/backend/test_14j_f05_06_m5b_dar_por_realizada.py::"
T207 = "tests/api/test_207_f05_06_m5b_dar_y_reabrir.py::"
JEST = "jest:__tests__/previsiones.test.tsx::"

#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    # ---------------------------------------------------------------- motor (F04-D065 §1)
    ("B01", "motor: sin la guarda de motivo",
     [(SRV, '        if not (motivo or "").strip():\n            raise ErrorMotor(\n                CodigoError.MOTIVO_AUSENTE,\n'
            '                "Dar por cubierta',
       '        if False:\n            raise ErrorMotor(\n                CodigoError.MOTIVO_AUSENTE,\n'
       '                "Dar por cubierta')],
     [T14J + "test_motivo_ausente"], None),
    ("B02", "motor: sin la guarda de estado ABIERTA",
     [(SRV, '            if prevision["estado"] != ABIERTA:\n                raise ErrorMotor(\n'
            '                    CodigoError.ESTADO_PREVISION_INCOMPATIBLE,\n                    "Solo una previsión ABIERTA puede darse',
       '            if False:\n                raise ErrorMotor(\n'
       '                    CodigoError.ESTADO_PREVISION_INCOMPATIBLE,\n                    "Solo una previsión ABIERTA puede darse')],
     [T14J + "test_estado_no_abierto"], None),
    ("B03", "motor: sin la version optimista (ni comprobacion ni UPDATE con la esperada)",
     [(SRV, '            if row_version_esperada != prevision["row_version"]:\n                raise ErrorMotor(\n'
            '                    CodigoError.VERSION_DESFASADA,\n                    "La previsión ha cambiado desde la version que conoce el "\n'
            '                    "llamante.",\n                )\n            # Recuento de realidad ACTIVA',
       '            if False:\n                raise ErrorMotor(\n'
       '                    CodigoError.VERSION_DESFASADA,\n                    "La previsión ha cambiado desde la version que conoce el "\n'
       '                    "llamante.",\n                )\n            # Recuento de realidad ACTIVA'),
      (SRV, '            nueva_version = self._tocar(sesion, prevision_id, row_version_esperada)\n            actualizada = repo_prev.actualizar_prevision(\n'
            '                sesion,\n                prevision_id,\n                {"estado": REALIZADA, "recalculo_automatico": False},',
       '            nueva_version = self._tocar(sesion, prevision_id, prevision["row_version"])\n            actualizada = repo_prev.actualizar_prevision(\n'
       '                sesion,\n                prevision_id,\n                {"estado": REALIZADA, "recalculo_automatico": False},')],
     [T14J + "test_version_desfasada", T207 + "test_dar_version_desfasada_409_con_estado_releido"], None),
    ("B04", "motor: sin exigir al menos un hecho ACTIVO bajo el lock",
     [(SRV, '            if realidad["hechos_activos"] < 1:\n', '            if False:\n')],
     [T14J + "test_sin_realidad_activa", T14J + "test_con_el_unico_hecho_anulado_no_hay_realidad"], None),
    ("B04b", "motor: cuenta tambien los hechos ANULADOS (>=1 vinculo de cualquier estado)",
     [(SRV, '            if realidad["hechos_activos"] < 1:\n',
       '            if not sesion.uno("SELECT count(*) FROM gapto.prevision_hechos WHERE prevision_id = %s", (prevision_id,))[0]:\n')],
     [T14J + "test_con_el_unico_hecho_anulado_no_hay_realidad"], None),
    ("B05", "motor: RODANTE sin uuid_sucesor admitido",
     [(SRV, '            if regla_id is not None and uuid_sucesor is None:\n                versiones = repo_reglas.listar_versiones(sesion, regla_id)\n'
            '                if any(\n                    s["cadencia"].anclaje == RODANTE\n                    for s in self._segmentos(versiones, self._resolver_ancla(sesion))\n'
            '                ):\n                    raise ErrorMotor(\n                        CodigoError.ENTRADA_INVALIDA,\n                        "La previsión es RODANTE',
       '            if False:\n                versiones = repo_reglas.listar_versiones(sesion, regla_id)\n'
       '                if any(\n                    s["cadencia"].anclaje == RODANTE\n                    for s in self._segmentos(versiones, self._resolver_ancla(sesion))\n'
       '                ):\n                    raise ErrorMotor(\n                        CodigoError.ENTRADA_INVALIDA,\n                        "La previsión es RODANTE')],
     [T14J + "test_rodante_sin_uuid_sucesor_se_rechaza"], None),
    ("B06", "motor: persiste la desviacion (el esperado pasa a ser lo registrado)",
     [(SRV, '                {"estado": REALIZADA, "recalculo_automatico": False},',
       '                {"estado": REALIZADA, "recalculo_automatico": False, "importe_esperado": realidad["suma_asignada"]},')],
     [T14J + "test_parcial_queda_realizada_sin_tocar_la_realidad_ni_la_desviacion",
      T207 + "test_dar_parcial_sin_realidad_nueva_ni_desviacion_persistida"], None),
    ("B07", "motor: deja la REALIZADA recalculable",
     [(SRV, '                {"estado": REALIZADA, "recalculo_automatico": False},',
       '                {"estado": REALIZADA, "recalculo_automatico": True},')],
     [T14J + "test_parcial_queda_realizada_sin_tocar_la_realidad_ni_la_desviacion"], None),
    ("B08", "motor: auditoria sin el prefijo «realizacion sin realidad nueva»",
     [(SRV, '                motivo=f"realizacion sin realidad nueva: {motivo}",\n', '                motivo=motivo,\n')],
     [T14J + "test_parcial_queda_realizada_sin_tocar_la_realidad_ni_la_desviacion"], None),
    ("B09", "motor: RODANTE sin crear el sucesor",
     [(SRV, '            if regla_id is not None:\n                self._crear_sucesor_si_rodante(sesion, regla_id, uuid_sucesor)\n'
            '            return self._resultado_actual(\n                sesion, prevision_id, row_version=nueva_version\n            )\n\n'
            '        return self._ejecutar(contexto, operacion, "dar_por_realizada")',
       '            return self._resultado_actual(\n                sesion, prevision_id, row_version=nueva_version\n            )\n\n'
       '        return self._ejecutar(contexto, operacion, "dar_por_realizada")')],
     [T14J + "test_rodante_con_uuid_sucesor_crea_el_sucesor"], None),
    # ---------------------------------------------------------------- adaptador y lectura
    ("A01", "adaptador: dar por cubierta sin uuid_sucesor determinista",
     [(EJP, "        r = _previsiones(sesion).dar_por_realizada(\n"
            "            contexto, prevision_id=prevision_id, row_version_esperada=intencion.row_version,\n"
            "            motivo=intencion.motivo,\n            uuid_sucesor=uuid_sucesor(intencion.intencion_id))\n",
       "        r = _previsiones(sesion).dar_por_realizada(\n"
       "            contexto, prevision_id=prevision_id, row_version_esperada=intencion.row_version,\n"
       "            motivo=intencion.motivo,\n            uuid_sucesor=None)\n")],
     [T207 + "test_dar_rodante_crea_sucesor_determinista"], None),
    ("A02", "adaptador: CANCELADA no rechazada (el motor la reabriria)",
     [(EJP, '        if lect_prev.estado_persistido(sesion, prevision_id) == "CANCELADA":\n', '        if False:\n')],
     [T207 + "test_reabrir_cancelada_rechazada_en_el_adaptador"], None),
    ("A03", "adaptador: reabrir sin la version del sucesor",
     [(EJP, "            motivo=intencion.motivo, sucesor_row_version_esperada=intencion.sucesor_row_version)\n",
       "            motivo=intencion.motivo, sucesor_row_version_esperada=None)\n")],
     [T207 + "test_reabrir_rodante_cancela_el_sucesor_con_su_version"], None),
    ("A04", "lectura: «Dar por cubierta» disponible sin realidad",
     [(LEC, '            dar = _accion(fila["con_realidad"], MOTIVO_SIN_REALIDAD)\n', '            dar = _accion(True, MOTIVO_SIN_REALIDAD)\n')],
     [T207 + "test_dar_sin_realidad_409_informa_de_no_hubo"], None),
    ("A05", "lectura: «Reabrir» disponible en una CANCELADA",
     [(LEC, '        reabrir = _accion(False, "Una previsión cancelada no se reabre desde la app.")\n', '        reabrir = _accion(True)\n')],
     [T207 + "test_reabrir_cancelada_rechazada_en_el_adaptador"], None),
    # ---------------------------------------------------------------- UI
    ("U01", "UI: «Dar por cubierta» se confirma sin motivo",
     [(COMP, "      <BotonPrimario testID=\"dar-confirmar\" titulo=\"Dar por cubierta\" onPress={p.onConfirmar} cargando={p.enviando} deshabilitado={!p.motivo.trim()} />\n",
       "      <BotonPrimario testID=\"dar-confirmar\" titulo=\"Dar por cubierta\" onPress={p.onConfirmar} cargando={p.enviando} deshabilitado={false} />\n"),
      (DET, "    if (!transicion || !transicion.motivo.trim()) return;\n", "    if (!transicion) return;\n")],
     [JEST + "hoja con Esperado"], None),
    ("U02", "UI: «Reabrir» se confirma sin motivo",
     [(COMP, "      <BotonPrimario testID=\"reabrir-confirmar\" titulo=\"Reabrir\" onPress={p.onConfirmar} cargando={p.enviando} deshabilitado={!p.motivo.trim()} />\n",
       "      <BotonPrimario testID=\"reabrir-confirmar\" titulo=\"Reabrir\" onPress={p.onConfirmar} cargando={p.enviando} deshabilitado={false} />\n")],
     [JEST + "en «Más» de una REALIZADA"], None),
    ("U03", "UI: «Dar por cubierta» ofrecido sin realidad",
     [(DOMM, "  return d.estado === 'ABIERTA' && d.estado_derivado === null && d.con_realidad;\n",
       "  return d.estado === 'ABIERTA' && d.estado_derivado === null;\n")],
     [JEST + "no se ofrece sin realidad"], None),
    ("U04", "UI: «Más» también en una ABIERTA",
     [(DOMM, "  return d.estado !== 'ABIERTA';\n", "  return true;\n")],
     [JEST + "no se ofrece sin realidad"], None),
    ("U05", "UI: «Reabrir» sin la version del sucesor",
     [(DET, "sucesor_row_version: d.sucesor?.row_version ?? null", "sucesor_row_version: null")],
     [JEST + "en «Más» de una REALIZADA"], None),
    ("U06", "UI: el reintento tras un fallo de conexion estrena identidad",
     [(DET, "      setFueIncierto(true);\n      return setTransicion(", "      setFueIncierto(true);\n      intencionTransicion.liberar();\n      return setTransicion(")],
     [JEST + "MISMA identidad"], None),
    ("U07", "UI: PREVISION_SIN_REALIDAD_ACTIVA sin explicar en la hoja",
     [(DET, "new Set(['PREVISION_SIN_REALIDAD_ACTIVA', ", "new Set([")],
     [JEST + "PREVISION_SIN_REALIDAD_ACTIVA"], None),
    ("U08", "UI: «Reabrir» atenuada se puede pulsar",
     [(COMP, '      <AccionPrevision testID="mas-reabrir" titulo="Reabrir" disponible={p.reabrir.disponible}',
       '      <AccionPrevision testID="mas-reabrir" titulo="Reabrir" disponible={true}')],
     [JEST + "CANCELADA"], None),
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
