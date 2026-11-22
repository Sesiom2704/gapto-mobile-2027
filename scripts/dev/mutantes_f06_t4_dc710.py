# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f06_t4_dc710.py
# Ruta: scripts/dev/mutantes_f06_t4_dc710.py
# Descripcion: Arnes de mutacion de D-C7-10 («Pagado» deslizando en la cuota; mandato F06 T4 DC710 v1.0 §4
#   «Mutantes»). Un mutante por guarda: los ocho del diseno v0.1 §5 con el del lado CORREGIDO («se invierte el lado
#   principal aprobado por SWIPE-RULE», F09 §12.106 punto 1) y M1..M10 de AJ-DC710-06; ademas tres variantes de
#   superficie (D3s, D7b, M3c). Mismo motor que mutantes_f06_01h_f05_q3_hd.py (journal durable, preflight verde,
#   restauracion verificada por SHA-256, veredicto a disco en cuanto se conoce) con base limpia por mutante y
#   clasificacion de la muerte (scripts/dev/base_limpia_mutante.py; GAPTO_MUTANTES_CLASIFICACION). Discriminantes:
#   tests/api/test_311 (servidor) y Jest prevision_cuota_swipe, prevision_cuota_lados, dc710_cola_pago_cuota y
#   dc710_inicio_pago_cuota (cliente).
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable 0356> [GAPTO_MUTANTES_CLASIFICACION=<jsonl>]
#        python -u scripts/dev/mutantes_f06_t4_dc710.py [--solo ID,ID] [--salida fichero]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F06 T4 · D-C7-10, mandato 7041970a…)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import base_limpia_mutante

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f06_t4_dc710.journal.json"

SWC = "backend/app/hipotecas/swipe_cuota.py"
DOMP = "mobile/src/domain/prevision.ts"
SWP = "mobile/src/components/SwipePrevision.tsx"
COLA = "mobile/src/state/colaAccionRapida.ts"
EJEC = "mobile/src/components/ColaAccionRapida.tsx"
T311 = "tests/api/test_311_f06_t4_dc710_bloque_cuota.py::"
JSW = "jest:__tests__/prevision_cuota_swipe.test.ts::"
JLA = "jest:__tests__/prevision_cuota_lados.test.tsx::"
JCO = "jest:__tests__/dc710_cola_pago_cuota.test.ts::"
JIN = "jest:__tests__/dc710_inicio_pago_cuota.test.tsx::"

PRINCIPAL = "      return { principal: { etiqueta: 'Pagado', icono: 'checkmark', tono: 'confirmar', onEjecutar: () => pagarCuota(f) } };\n"

MUTANTES = [
    # ---------------------------------------------------------------- diseno v0.1 §5 (con el del lado corregido)
    ("D1", "gesto en cuota futura (sin vencimiento <= hoy)",
     [(SWC, "        and vencimiento is not None and vencimiento <= hoy\n", "        and vencimiento is not None\n")],
     [T311 + "test_no_disponible_cuota_futura"], None),
    ("D2", "gesto en cuota que no es la mas antigua (sin primera == numero)",
     [(SWC, "        and primera is not None and primera == numero\n", "        and primera is not None\n")],
     [T311 + "test_inicio_lleva_el_mismo_bloque_y_las_posteriores_no_ofrecen_gesto"], None),
    ("D3", "pago directo con dudas (el cliente ignora sin_dudas)",
     [(DOMP, "  if (q.swipe_disponible !== true || q.sin_dudas !== true) return false;\n",
       "  if (q.swipe_disponible !== true) return false;\n")],
     [JSW + "Q3-C2 v1.2", JLA + "con dudas tampoco", JIN + "con dudas la cuota"], None),
    ("D4", "fecha_pago = hoy en lugar del vencimiento",
     [(DOMP, "    fecha_pago: q.fecha_vencimiento!, atribucion:",
       "    fecha_pago: new Date().toISOString().slice(0, 10), atribucion:")],
     [JSW + "payload exacto", JLA + "nada antes de 5 s"], None),
    ("D5", "intencion nueva en el reenvio (reconciliacion)",
     [(EJEC, "          const r = await cliente.pagarCuotaHipoteca(fid, numero, p);\n",
       "          const r = await cliente.pagarCuotaHipoteca(fid, numero, i.envios > 1 ? ({ ...(p as object), intencion_id: `${i.intencionId}-r` } as never) : p);\n")],
     [JCO + "respuesta perdida tras pagar"], None),
    ("D6", "envio por la ruta GASTO (gasto-pagado) en lugar de W-HIP-02",
     [(SWP, "      ruta: 'PAGO_CUOTA',\n", "      ruta: 'GASTO',\n")],
     [JLA + "nada antes de 5 s", JIN + "sin dudas ofrece SOLO"], None),
    ("D7", "se invierte el lado principal aprobado por SWIPE-RULE (corregido; = M8)",
     [(SWP, PRINCIPAL, PRINCIPAL.replace("{ principal:", "{ alternativa:"))],
     [JLA + "SOLO el lado principal", JIN + "sin dudas ofrece SOLO"], None),
    ("D8", "row_version de la prevision en lugar del de la financiacion",
     [(DOMP, "    intencion_id: intencionId, row_version_esperada: q.financiacion_row_version!,",
       "    intencion_id: intencionId, row_version_esperada: f.row_version,")],
     [JSW + "payload exacto", JLA + "nada antes de 5 s"], None),
    # ---------------------------------------------------------------- AJ-DC710-06
    ("M1", "una cuota anterior OMITIDA permite el gesto",
     [(SWC, "AND p.estado IS DISTINCT FROM 'REALIZADA' \"\n", "AND p.estado = 'ABIERTA' \"\n")],
     [T311 + "test_no_disponible_anterior_omitida", T311 + "test_no_disponible_anterior_cancelada"], None),
    ("M2", "se usa el aviso de reparto del desembolso (L-HIP) en lugar de la cuenta de cargo",
     [(SWC, "    return not alta.aviso_reparto_distinto(participacion, propuesta)\n",
       "    from app.hipotecas import lecturas as _l\n    return not _l.leer(sesion, fid, vencimiento)[\"aviso_reparto_distinto\"]\n")],
     [T311 + "test_dudas_reparto_de_la_cuenta_de_cargo_distinto_aunque_el_desembolso_coincida",
      T311 + "test_sin_dudas_aunque_el_desembolso_difiera"], None),
    ("M3", "una propuesta vacia o incompleta se considera sin dudas",
     [(SWC, "    if not _validas(propuesta):\n        return False\n    participacion", "    participacion")],
     [T311 + "test_dudas_propuesta_vacia_en_el_vencimiento"], None),
    ("M4", "cuenta con PAGAR_GASTO pero cerrada o no elegible permite pago rapido (solo se mira la capacidad)",
     [(SWC, "    if motivo_cuenta(sesion, cuenta, \"GASTO\", vencimiento) is not None:\n",
       "    if motivo_cuenta(sesion, cuenta, \"GASTO\", vencimiento) == \"SIN_CAPACIDAD\":\n")],
     [T311 + "test_dudas_cuenta_cerrada_antes_del_vencimiento", T311 + "test_dudas_ledger_de_la_cuenta_posterior_al_vencimiento",
      T311 + "test_dudas_cuenta_deshabilitada"], None),
    ("M5", "una prevision con realidad parcial permite el pago automatico",
     [(SWC, "        and fila[\"pagos\"] == 0 and not fila[\"con_realidad\"] and fila.get(\"_cubierto\") == 0\n", "")],
     [T311 + "test_no_disponible_con_realidad_previa"], None),
    ("M6", "una prevision REALIZADA por otra intencion confirma falsamente el swipe",
     [(COLA, "    if (i.ruta === 'NO_HUBO' && reintento && CODIGOS_409_OMITIR.includes(r.codigo)) return this.leerPrevision(i);\n",
       "    if (i.ruta === 'NO_HUBO' && reintento && CODIGOS_409_OMITIR.includes(r.codigo)) return this.leerPrevision(i);\n"
       "    if (i.ruta === 'PAGO_CUOTA' && reintento && (await this.ejecutor.estadoPrevision(i.clave)) === 'REALIZADA') return this.confirmar(i, null);\n")],
     [JCO + "M6"], None),
    ("M7", "el caso con dudas termina en el formulario generico (gesto que abre el registro)",
     [(SWP, "      if (!gestoPagoCuota(f)) return {};\n",
       "      if (!gestoPagoCuota(f)) return { principal: { etiqueta: 'Pagado', icono: 'checkmark', tono: 'confirmar', onEjecutar: () => p.onFormularioCompleto(f, null) } };\n")],
     [JLA + "con dudas tampoco", JIN + "con dudas la cuota"], None),
    ("M8", "se invierte el lado principal aprobado por SWIPE-RULE (misma mutacion que D7)",
     [(SWP, PRINCIPAL, PRINCIPAL.replace("{ principal:", "{ alternativa:"))],
     [JLA + "SOLO el lado principal", JIN + "sin dudas ofrece SOLO"], None),
    ("M9", "un reenvio tras restaurar crea otra intencion_id",
     [(COLA, "    i.pregunta = false;\n    if (this.t.ahora() < i.vence) {\n",
       "    i.pregunta = false;\n    i.payload = { ...i.payload, intencion_id: `${i.intencionId}-n` };\n    if (this.t.ahora() < i.vence) {\n")],
     [JCO + "M9"], None),
    ("M10", "PAGO_CUOTA_EXPUESTO = false deja visible el gesto",
     [(DOMP, "  if (!expuesto || f.codigo !== 'PREVISION_DE_CUOTA'", "  if (f.codigo !== 'PREVISION_DE_CUOTA'")],
     [JSW + "M10"], None),
    # ---------------------------------------------------------------- variantes de superficie
    ("D3s", "el servidor declara sin_dudas sin comprobar las dudas",
     [(SWC, "                      \"sin_dudas\": disponible and dudas_fuera}\n", "                      \"sin_dudas\": disponible}\n")],
     [T311 + "test_dudas_reparto_de_la_cuenta_de_cargo_distinto_aunque_el_desembolso_coincida"], None),
    ("D7b", "la cuota ofrece tambien «No hubo»",
     [(SWP, PRINCIPAL, PRINCIPAL.replace(" } };\n", " }, alternativa: { etiqueta: 'No hubo', icono: 'remove-circle-outline', "
                                                    "tono: 'neutro', onEjecutar: () => noHubo(f) } };\n"))],
     [JLA + "SOLO el lado principal"], None),
    ("M3c", "el cliente acepta una propuesta vacia",
     [(DOMP, " && !!q.propuesta_atribucion && q.propuesta_atribucion.length > 0;\n", " && !!q.propuesta_atribucion;\n")],
     [JSW + "fail-closed"], None),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@base_limpia_mutante.por_llamada
def correr(tests: list[str]) -> int:
    """pytest de tests/api con su rootdir y Jest en mobile/. rc != 0 si alguno falla."""
    api = [t for t in tests if t.startswith("tests/api/")]
    jest = [t[len("jest:"):] for t in tests if t.startswith("jest:")]
    rc = 0
    if api:
        cmd = [sys.executable, "-m", "pytest", *api, "-q", "-x", "-p", "no:cacheprovider", "--rootdir=tests/api"]
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
        v = (mid, resultado if ok else "NO_CLASIFICABLE", ",".join(t.split("::", 1)[-1] if "::" in t else t for t in tests), nota)
        veredictos.append(v)
        anotar(salida, " | ".join(v))
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    equivalentes = sum(1 for v in veredictos if v[1] == "EQUIVALENTE")
    anotar(salida, f"RESUMEN {muertos} muertos, {equivalentes} equivalentes documentados, "
                   f"{len(veredictos) - muertos - equivalentes} otros / {len(veredictos)}")
    sys.exit(0 if muertos + equivalentes == len(veredictos) else 1)


if __name__ == "__main__":
    main()
