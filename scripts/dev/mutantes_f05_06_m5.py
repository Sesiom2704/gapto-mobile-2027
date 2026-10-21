# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_06_m5.py
# Ruta: scripts/dev/mutantes_f05_06_m5.py
# Descripcion: Arnes de mutacion de F05-06 M5 (mandato F05-06 M5 v1.0, cuerpo
#   v0.3 §A8; F05 §51.4 CC-06-C «un mutante por guarda nueva»; 100 % muertos o
#   equivalentes documentados). Mismo motor que mutantes_f05_06_m3.py (D-181,
#   D-192, D-193, WM 12C.2):
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
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable> GAPTO_M5_CONCURRENCIA=1 GAPTO_M4_CONCURRENCIA=1
#        python scripts/dev/mutantes_f05_06_m5.py [--solo ID,ID] [--salida fichero]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F05-06 M5 §A8)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f05_06_m5.journal.json"

DTO = "backend/app/api/dto_prevision.py"
EJP = "backend/app/api/ejecucion_prevision.py"
EJR = "backend/app/api/ejecucion_registro.py"
EGP = "backend/app/api/ejecucion_gasto_pagado.py"
TRA = "backend/app/api/traductor_registro.py"
LEC = "backend/app/previsiones/lecturas.py"
INI = "backend/app/inicio/lecturas.py"
APP = "backend/app/api/app.py"
REPO = "backend/app/repositories/previsiones_repository.py"
HOME = "mobile/src/screens/HomeScreen.tsx"
DOMM = "mobile/src/domain/prevision.ts"
DET = "mobile/src/screens/PrevisionDetalleScreen.tsx"
T204 = "tests/api/test_204_f05_06_m5_previsiones.py::"
T205 = "tests/api/test_205_f05_06_m5_concurrencia_serial.py::"
T203 = "tests/api/test_203_f05_06_m5_a0_transferencia.py::"
T154 = "tests/api/test_154_f05_01_inventario_categorias.py::"
JEST = "jest:__tests__/previsiones.test.tsx::"


def a(n: str) -> str:
    return T204 + n


#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    ("M01", "marcar_realizada con defecto true (registro desde la prevision)",
     [(DTO, "    marcar_realizada: StrictBool  # sin defecto: siempre una decision explicita\n",
       "    marcar_realizada: StrictBool = True  # sin defecto: siempre una decision explicita\n")],
     [a("test_marcar_realizada_obligatorio_sin_defecto[gasto]")], None),
    ("M01b", "marcar_realizada con defecto true («Ya lo registre»)",
     [(DTO, "    importe_a_vincular: decimal.Decimal = Field(gt=0, max_digits=18, decimal_places=4)\n    marcar_realizada: StrictBool\n",
       "    importe_a_vincular: decimal.Decimal = Field(gt=0, max_digits=18, decimal_places=4)\n    marcar_realizada: StrictBool = True\n")],
     [a("test_marcar_realizada_obligatorio_sin_defecto[vincular]")], None),
    ("M02", "adaptador sin uuid_sucesor en omitir",
     [(EJP, "            motivo=intencion.motivo, uuid_sucesor=uuid_sucesor(intencion.intencion_id))\n",
       "            motivo=intencion.motivo, uuid_sucesor=None)\n")],
     [a("test_rodante_omitir_crea_sucesor")], None),
    ("M02b", "adaptador sin uuid_sucesor en OP-17 suelto",
     [(EJP, "            uuid_sucesor=uuid_sucesor(intencion.intencion_id))\n        if not r.idempotente:\n",
       "            uuid_sucesor=None)\n        if not r.idempotente:\n")],
     [a("test_rodante_op17_realiza_y_crea_sucesor_replay_estable")], None),
    ("M02c", "adaptador sin uuid_sucesor en OP-22 + prevision",
     [(TRA, "        uuid_sucesor=uuid_sucesor(intencion_id) if bloque.marcar_realizada else None,\n",
       "        uuid_sucesor=None,\n")],
     [a("test_rodante_op22_realiza_y_crea_sucesor_replay_estable")], None),
    ("M03", "candidatos con preseleccion (campo que marca el primero)",
     [(LEC, "    return {**salida, \"candidatos\": [{k: v for k, v in c.items() if k != \"_d\"} for c in lista]}\n",
       "    return {**salida, \"candidatos\": [{**{k: v for k, v in c.items() if k != \"_d\"}, \"seleccionado\": i == 0} "
       "for i, c in enumerate(lista)]}\n")],
     [a("test_candidatos_filtros_orden_y_sin_preseleccion")], None),
    ("M04", "candidatos con porcion agotada",
     [(LEC, "        if disponible <= 0:\n            continue\n", "")],
     [a("test_candidatos_filtros_orden_y_sin_preseleccion")], None),
    ("M04b", "candidatos NO_DETERMINABLE (importe NULL)",
     [(LEC, "    \"AND h.importe_total IS NOT NULL \"\n", "")],
     [a("test_candidato_no_determinable_excluido")], None),
    ("M05", "previsiones sumadas al Resultado del mes",
     [(INI, "        \"resultado\": _texto(propios[\"INGRESO\"] - propios[\"GASTO\"]),\n",
       "        \"resultado\": _texto(propios[\"INGRESO\"] - propios[\"GASTO\"] - sesion.uno(\"SELECT COALESCE(sum(importe_esperado), 0) "
       "FROM gapto.previsiones WHERE estado = 'ABIERTA'\")[0]),\n")],
     [a("test_month_rule_06_resultado_identico_con_y_sin_previsiones")], None),
    ("M06", "desconocido -> 0",
     [(LEC, "    esperado = None if esperado is None else decimal.Decimal(esperado)\n",
       "    esperado = decimal.Decimal(esperado or 0)\n")],
     [a("test_importe_desconocido_nunca_cero")], None),
    ("M06b", "desconocido -> 0 en el cliente",
     [(DOMM, "  if (base === null) return TEXTO_DESCONOCIDO;\n", "  if (base === null) return formatearEur('0.00');\n")],
     [JEST + "importes por naturaleza"], None),
    ("M07", "vencida con la fecha UTC en lugar de hoy_owner (Inicio)",
     [(APP, "        salida = unidad.ejecutar(contexto(), lambda s: lect_prev.inicio(s, hoy_owner(s, reloj)),\n",
       "        salida = unidad.ejecutar(contexto(), lambda s: lect_prev.inicio(s, reloj().date()),\n")],
     [a("test_vencida_con_hoy_owner_y_no_utc")], None),
    ("M08", "Requiere atencion sin las parciales no vencidas",
     [(LEC, "    parciales = sorted((f for f in filas if not f[\"vencida\"] and f[\"con_realidad\"]), key=_clave)\n",
       "    parciales = []\n")],
     [a("test_parcial_sigue_en_requiere_atencion_aunque_no_venza")], None),
    ("M08bis", "bloque de Inicio que desaparece cuando la lectura falla",
     [(HOME, "      {previsiones.fase === 'ERROR' ? (\n        <Seccion testID=\"bloque-atencion\" titulo=\"Requiere atención\">\n",
       "      {false ? (\n        <Seccion testID=\"bloque-atencion\" titulo=\"Requiere atención\">\n")],
     [JEST + "I05"], None),
    ("M09", "swipe con esperado desconocido (servidor)",
     [(LEC, "    elif fila[\"_esperado\"] is None:\n", "    elif False:\n")],
     [a("test_importe_desconocido_nunca_cero")], None),
    ("M09b", "swipe con esperado desconocido (cliente)",
     [(DOMM, "f.con_realidad || f.importe_esperado === null) return false;", "f.con_realidad) return false;")],
     [JEST + "swipe solo con gasto", JEST + "sin swipe con esperado desconocido"], None),
    ("M10", "omitir que devuelve exito en el reintento",
     [(EJP, "    def operacion(sesion: SesionMotor) -> Omitida:\n",
       "    def operacion(sesion: SesionMotor) -> Omitida:\n        if lect_prev.estado_persistido(sesion, prevision_id) == \"OMITIDA\":\n"
       "            return Omitida(prevision_id=prevision_id, estado=\"OMITIDA\", row_version=intencion.row_version)\n")],
     [a("test_omitir_reintento_409_sin_escritura_ni_segundo_sucesor")], None),
    ("M11", "importe_asignado = min(porcion, esperado) en OP-22",
     [(EGP, "                intencion.intencion_id, intencion.prevision, intencion.importe.quantize(ESCALA)))\n",
       "                intencion.intencion_id, intencion.prevision, min(intencion.importe, sesion.uno(\"SELECT importe_esperado "
       "FROM gapto.previsiones WHERE id = %s\", (intencion.prevision.prevision_id,))[0] or intencion.importe).quantize(ESCALA)))\n")],
     [a("test_g2_prevision_confirmada_luz")], None),
    ("M12", "llamada a corregir_vinculo desde la frontera",
     [(EJP, "CODIGO_PORCION_CAMBIADA = \"PORCION_CAMBIADA\"\n",
       "CODIGO_PORCION_CAMBIADA = \"PORCION_CAMBIADA\"\n_x = lambda s: _previsiones(s).corregir_vinculo  # noqa: E731\n")],
     [T154 + "test_i3_m5_excepcion_limitada_a_vincular_realidad_y_omitir"], None),
    ("M12b", "llamada a corregir_vinculo con alias de importacion",
     [(EJP, "from app.services.previsiones_service import PrevisionesService\n",
       "from app.services.previsiones_service import PrevisionesService\nfrom app.services.previsiones_service import "
       "PrevisionesService as _P\n_y = lambda s: _P(UnidadDeTrabajoAdscrita(s)).corregir_vinculo  # noqa: E731\n")],
     [T154 + "test_i3_m5_excepcion_limitada_a_vincular_realidad_y_omitir"], None),
    ("M13", "total monetario unico en «Pendientes»",
     [(LEC, "        \"por_cobrar\": _por_naturaleza(atencion, \"INGRESO\"),\n",
       "        \"por_cobrar\": _por_naturaleza(atencion, \"INGRESO\"), \"total\": \"0.00\",\n")],
     [a("test_naturalezas_separadas_recuento_comun")], None),
    ("M13b", "las transferencias suman en «Por pagar»",
     [(LEC, "    propias = [f for f in filas if f[\"tipo\"] == tipo]\n",
       "    propias = [f for f in filas if f[\"tipo\"] in (tipo, \"TRANSFERENCIA\")]\n")],
     [a("test_naturalezas_separadas_recuento_comun")], None),
    ("M13c", "importes sumados en Inicio",
     [(LEC, "        \"requiere_atencion\": {\"n\": len(atencion),\n",
       "        \"requiere_atencion\": {\"n\": len(atencion), \"importe\": \"0.00\",\n")],
     [a("test_naturalezas_separadas_recuento_comun")], None),
    ("M14", "sin la relectura de PORCION_CAMBIADA",
     [(EJP, "        if not r.idempotente:\n            # Con el hecho bloqueado", "        if False:\n            # Con el hecho bloqueado")],
     [a("test_porcion_que_crece_entre_lista_y_post")], None),
    ("M14b", "relectura sin la rama NO_DETERMINABLE",
     [(EJP, "            if restante is None:\n                raise", "            if False:\n                raise")],
     [a("test_vincular_hecho_no_determinable_rechazado")], None),
    ("M15", "replay de la transferencia prevista que da exito con el hecho sin el vinculo",
     [(EJP, "        if lect_prev.vinculos_del_hecho(sesion, iid) != {vinculo: (bloque.prevision_id, importe)}:\n            return False\n", "")],
     [a("test_replay_transferencia_prevista[vinculo_ausente]"), a("test_replay_transferencia_prevista[prevision_distinta]"),
      a("test_replay_transferencia_prevista[modificada_sin_vinculo]")], None),
    ("M15b", "transferencia sin bloque que reconoce una prevista",
     [(EJR, "        return vinculo not in lect_prev.vinculos_del_hecho(sesion, intencion.intencion_id)\n", "        return True\n")],
     [a("test_transferencia_sin_bloque_no_reconoce_una_prevista")], None),
    ("M16", "OP-10 confirmada antes de OP-17 (dos unidades)",
     [(EJP, "        r = transferir_bajo_locks(sesion, contexto, intencion, reloj, replay_compuesto,\n"
            "                                  lambda s: validar_tipo_prevision(s, bloque, \"TRANSFERENCIA\"))\n",
       "        r = __import__(\"app.api.ejecucion_registro\", fromlist=[\"x\"]).registrar_transferencia(\n"
       "            unidad, contexto, intencion.model_copy(update={\"prevision\": None}), reloj)\n")],
     [T203 + "test_a0_op17_rechazado_revierte_op10", T205 + "test_p5_op10_op17_frente_a_omitir"], None),
    ("M17", "omitir sin la guarda row_version (UPDATE sin version)",
     [(REPO, "         WHERE p.id = %s::uuid\n           AND p.row_version = %s\n        RETURNING p.row_version\n",
       "         WHERE p.id = %s::uuid\n           AND %s IS NOT NULL\n        RETURNING p.row_version\n")],
     [a("test_omitir_version_desfasada_409"), T205 + "test_p3_omitir_frente_a_op17"], None),
    ("M18", "ruta compuesta: identidad y replay leidos ANTES de bloquear las cuentas",
     [(EJR, "    bloquear_cuentas(sesion, intencion.cuenta_origen_id, intencion.cuenta_destino_id)\n"
            "    if repo_hechos.leer_estado(sesion, intencion.intencion_id) is not None:\n"
            "        if not (_replay_transferencia(sesion, intencion) and replay_extra(sesion)):\n",
       "    _ya = repo_hechos.leer_estado(sesion, intencion.intencion_id) is not None\n"
       "    _ok = _ya and _replay_transferencia(sesion, intencion) and replay_extra(sesion)\n"
       "    bloquear_cuentas(sesion, intencion.cuenta_origen_id, intencion.cuenta_destino_id)\n"
       "    if _ya:\n"
       "        if not _ok:\n")],
     [a("test_replay_concurrente_de_la_misma_intencion[transferencia]")],
     "OP-10 reconoce su propia identidad (seis UUID) y OP-17 la del vinculo bajo sus locks: un replay "
     "concurrente que lea la identidad antes de la cuenta acaba igual en un idempotente, nunca en una segunda realidad"),
    # ---------------------------------------------------------------- guardas propias de M5
    ("M19", "registro desde la prevision sin exigir el tipo de la prevision",
     [(EJR, "    return CODIGO_PREVISION_TIPO_DISTINTO if actual is not None and actual != tipo else None\n", "    return None\n")],
     [a("test_tipo_distinto_rechazado_sin_escritura")], None),
    ("M20", "«Ya lo registre» sin exigir el tipo del hecho",
     [(EJP, "        if tipo_hecho is not None and tipo_prev is not None and tipo_hecho != tipo_prev:\n", "        if False:\n")],
     [a("test_tipo_distinto_rechazado_sin_escritura")], None),
    ("M21", "omitir 409 sin el estado releido",
     [(APP, "                detalle = {\"estado_actual\": _estado_actual(prevision_id)}\n", "                detalle = None\n")],
     [a("test_omitir_reintento_409_sin_escritura_ni_segundo_sucesor")], None),
    ("M22", "«¿Queda cubierta?» con respuesta marcada por defecto (cliente)",
     [(DOMM, "  if (marcar === null) return null;\n  return { prevision_id", "  return { prevision_id")],
     [JEST + "bloque `prevision` solo"], None),
    ("M23", "«Ya lo registre» con el primer candidato preseleccionado (cliente)",
     [(DET, "  const [elegido, setElegido] = useState<CandidatoPrevision | null>(null); // sin preselección\n",
       "  const [elegido, setElegido] = useState<CandidatoPrevision | null>(null); // sin preselección\n"
       "  useEffect(() => { if (lista.fase === 'OK' && lista.datos.candidatos[0] && !elegido) setElegido(lista.datos.candidatos[0]); }, [lista]); // eslint-disable-line\n")],
     [JEST + "B2"], None),
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
    if os.getenv("GAPTO_M5_CONCURRENCIA") != "1":
        sys.exit("Falta GAPTO_M5_CONCURRENCIA=1: los discriminantes seriales se omitirian.")
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
