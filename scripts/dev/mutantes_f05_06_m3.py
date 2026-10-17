# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_06_m3.py
# Ruta: scripts/dev/mutantes_f05_06_m3.py
# Descripcion: Arnes de mutacion de F05-06 M3 (mandato F05-06 M3 v1.0 §A8;
#   F05 §51.4 CC-06-C «un mutante por guarda nueva»; 100 % muertos o
#   equivalentes documentados). Mismo motor que mutantes_f04_r2b.py (D-181,
#   D-192, D-193, WM 12C.2):
#     - sustituciones de texto exacto (UNA ocurrencia) y sus discriminantes
#       (nodeid de pytest; tests/api y tests/backend se ejecutan por separado,
#       cada uno con su rootdir);
#     - journal durable ANTES de tocar el primer byte; si al arrancar hay un
#       journal pendiente: restaura, verifica y aborta;
#     - preflight verde de todos los discriminantes antes del primer mutante;
#     - tras cada mutante se restaura y se verifica la identidad byte a byte;
#     - el veredicto de CADA mutante se escribe a disco en cuanto se conoce
#       (--salida, append + fsync): un corte no pierde los ya clasificados;
#     - veredicto: MUERTO | VIVO | NO_CLASIFICABLE (EQUIVALENTE si se declara).
#   Guardas: (i) REPARTO_CAMBIA_POSICIONES por cada caso (b), su llamada y su
#   alcance; writer de actor (PERSONA, enabled, owner, FOR SHARE, ON CONFLICT,
#   auditoria); INV-04 (derecho y deuda); G3; whitelist de «Corregir reparto»
#   (partes, tipo, devolucion, V3, suma, coherencia y no demostrable);
#   capacidad del cobro; orden de P4 (advisory antes de la cuenta en OP-22 y en
#   las reducciones; advisory antes del hecho en OP-21).
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable> GAPTO_M3_CONCURRENCIA=1
#        python scripts/dev/mutantes_f05_06_m3.py [--solo ID,ID] [--salida fichero]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F05-06 M3 §A8)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f05_06_m3.journal.json"

CORR = "backend/app/services/correcciones_service.py"
ACTS = "backend/app/actores/servicio.py"
ACTR = "backend/app/actores/repositorio.py"
REP = "backend/app/api/ejecucion_reparto.py"
T199 = "tests/api/test_199_f05_06_m3_reparto.py::"
T200 = "tests/api/test_200_f05_06_m3_concurrencia_serial.py::"
T201 = "tests/api/test_201_f05_06_m3_orden_locks.py::"
T145 = "tests/backend/test_145_f04_d052_e1_op04_op21.py::"


def a(n: str) -> str:
    return T199 + n


#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    # ---------------------------------------------------------------- (i) REPARTO_CAMBIA_POSICIONES
    ("M01", "(i) sin rechazar la baja de un efecto vinculado a una posicion",
     [(CORR, "        if efecto_id in efectos_vinculados:\n            raise _reparto_cambia_posiciones(\"RETIRA_EFECTO_DE_POSICION\")\n",
       "        if False:\n            raise _reparto_cambia_posiciones(\"RETIRA_EFECTO_DE_POSICION\")\n")],
     [a("test_b_guarda_motor_reparto_cambia_posiciones[RETIRA_EFECTO_DE_POSICION]")], None),
    ("M02", "(i) sin rechazar el alta de un efecto DERECHO_COBRO/DEUDA (invitado -> deudor)",
     [(CORR, "        if efecto.tipo_efecto in NATURALEZAS_DE_POSICION:\n", "        if False:\n")],
     [a("test_b_guarda_motor_reparto_cambia_posiciones[CREA_EFECTO_DE_POSICION]")], None),
    ("M03", "(i) sin rechazar el cambio de naturaleza hacia o desde una posicion",
     [(CORR, "        if \"tipo_efecto\" in cambios and (\n", "        if False and (\n")],
     [a("test_b_guarda_motor_reparto_cambia_posiciones[CAMBIA_NATURALEZA_DE_POSICION]")], None),
    ("M04", "(i) sin rechazar la baja de un AFECTA_A con efecto de posicion (R-M3PRE2-02)",
     [(CORR, "            if cur.fetchone() is not None:\n                raise _reparto_cambia_posiciones(\"RETIRA_VINCULO_DE_POSICION\")\n",
       "            if False:\n                raise _reparto_cambia_posiciones(\"RETIRA_VINCULO_DE_POSICION\")\n")],
     [a("test_b_retirar_afecta_a_con_efecto_de_posicion_r_m3pre2_02")], None),
    ("M05", "(i) sin rechazar vincular el hecho a una posicion",
     [(CORR, "            if cur.fetchone() is not None:\n                raise _reparto_cambia_posiciones(\"VINCULA_POSICION\")\n",
       "            if False:\n                raise _reparto_cambia_posiciones(\"VINCULA_POSICION\")\n")],
     [a("test_b_guarda_motor_reparto_cambia_posiciones[VINCULA_POSICION]")], None),
    ("M06", "(i) sin rechazar altas ni bajas de participantes en un hecho con posiciones",
     [(CORR, "    if tiene_posiciones and (datos.atribuciones_a_crear or datos.atribuciones_a_eliminar):\n",
       "    if False:\n")],
     [a("test_b_guarda_motor_reparto_cambia_posiciones[ALTA_O_BAJA_DE_PARTICIPANTE:alta]"),
      a("test_b_guarda_motor_reparto_cambia_posiciones[ALTA_O_BAJA_DE_PARTICIPANTE:baja]")], None),
    ("M07", "(i) la guarda no se invoca en OP-21",
     [(CORR, "            exigir_reparto_sin_cambio_de_posiciones(sesion, datos)\n", "")],
     [a("test_b_guarda_motor_reparto_cambia_posiciones[RETIRA_EFECTO_DE_POSICION]")], None),
    ("M08", "(i) la guarda se salta los GASTO (alcance invertido)",
     [(CORR, "    if repo_corr.tipo_de_hecho(sesion, datos.hecho_id) != ARQUETIPO_REPARTO:\n",
       "    if repo_corr.tipo_de_hecho(sesion, datos.hecho_id) == ARQUETIPO_REPARTO:\n")],
     [a("test_b_guarda_motor_reparto_cambia_posiciones[CREA_EFECTO_DE_POSICION]")], None),
    ("M09", "(i) la guarda alcanza tambien REEMBOLSO/CONDONACION (pisa los codigos E1)",
     [(CORR, "    if repo_corr.tipo_de_hecho(sesion, datos.hecho_id) != ARQUETIPO_REPARTO:\n        return\n", "")],
     [T145 + "test_i2_op21_derecho_cobro_a_gasto_rechazado"], None),
    # ---------------------------------------------------------------- (ii) writer de actor
    ("M10", "writer: admite terceros que no son PERSONA",
     [(ACTS, "    if tercero[\"naturaleza\"] != repo.NATURALEZA_PERSONA:\n", "    if False:\n")],
     [a("test_writer_actor_rechaza_sin_efectos[empresa]")], None),
    ("M11", "writer: admite terceros deshabilitados",
     [(ACTS, "    if tercero is None or not tercero[\"enabled\"]:\n", "    if tercero is None:\n")],
     [a("test_writer_actor_rechaza_sin_efectos[deshabilitado]")], None),
    ("M12", "writer: sin el filtro de owner explicito (lo cubre la RLS)",
     [(ACTR, "        \"SELECT id, naturaleza, enabled FROM gapto.terceros WHERE id = %s \"\n"
             "        \"AND owner_user_id = current_setting('gapto.owner_user_id')::uuid FOR SHARE\",\n",
       "        \"SELECT id, naturaleza, enabled FROM gapto.terceros WHERE id = %s FOR SHARE\",\n")],
     [a("test_writer_actor_rechaza_sin_efectos[otro_owner]")],
     "RLS FORCE de terceros (0120): un tercero de otro owner no es visible para gapto_runtime, asi "
     "que el filtro explicito es defensa en profundidad no alcanzable"),
    ("M13", "writer: tercero sin FOR SHARE (no serializa frente a desactivarlo)",
     [(ACTR, "        \"AND owner_user_id = current_setting('gapto.owner_user_id')::uuid FOR SHARE\",\n",
       "        \"AND owner_user_id = current_setting('gapto.owner_user_id')::uuid\",\n")],
     [T200 + "test_p2_alta_del_actor_frente_a_desactivar_el_tercero[B-primero]"], None),
    ("M14", "writer: INSERT sin ON CONFLICT (segunda alta del mismo tercero falla)",
     [(ACTR, "        \"ON CONFLICT ON CONSTRAINT uq_actores_financieros__owner_tercero DO NOTHING \"\n", "")],
     [a("test_writer_actor_idempotente_y_auditado")], None),
    ("M15", "writer: alta sin auditoria",
     [(ACTS, "        auditoria.registrar(\n            sesion,\n            tabla=repo.TABLA,\n",
       "        (lambda *a, **k: None)(\n            sesion,\n            tabla=repo.TABLA,\n")],
     [a("test_writer_actor_idempotente_y_auditado")], None),
    # ---------------------------------------------------------------- INV-04 y G3
    ("M16", "INV-04: el invitado («No») tambien crea derecho de cobro",
     [(REP, "            if parte.me_debe == \"SI\":\n", "            if parte.me_debe in (\"SI\", \"NO\"):\n")],
     [a("test_inv04_invitado_y_pago_de_mas_no_crean_derecho")], None),
    ("M17", "INV-04: «No lo se» crea la deuda",
     [(REP, "    elif intencion.pagado_por.le_debo == \"SI\":\n", "    elif intencion.pagado_por.le_debo != \"NO\":\n")],
     [a("test_inv04_sin_si_no_hay_deuda[NO_LO_SE]")], None),
    ("M18", "G3: sin ninguna parte conocida se marca PARCIAL (se rellena a cero)",
     [(REP, "    return \"PARCIAL\" if conocidas else \"NO_DISPONIBLE\"\n", "    return \"PARCIAL\"\n")],
     [a("test_g3_sin_ninguna_parte_es_no_disponible")], None),
    ("M19", "G3: un reparto incompleto se da por COMPLETO",
     [(REP, "    if todas and total == intencion.importe:\n", "    if conocidas:\n")],
     [a("test_g3_parte_sin_indicar_queda_parcial")], None),
    # ---------------------------------------------------------------- whitelist de «Corregir reparto»
    ("M20", "whitelist: admite partes que no son de este gasto",
     [(REP, "        if not set(nuevas) <= set(propias):\n", "        if False:\n")],
     [a("test_whitelist_rechaza_sin_efectos[<lambda>-REPARTO_NO_CORREGIBLE1]")], None),
    ("M21", "whitelist: admite devoluciones",
     [(REP, "        if (estado[\"estado\"] != \"ACTIVO\" or estado[\"tipo\"] != \"GASTO\" or estado[\"es_devolucion\"]\n",
       "        if (estado[\"estado\"] != \"ACTIVO\" or estado[\"tipo\"] != \"GASTO\"\n")],
     [a("test_c_fuera_de_m3[devolucion]")], None),
    ("M22", "whitelist: admite registros de V3",
     [(REP, "        if estado[\"importado\"]:\n", "        if False:\n")],
     [a("test_c_fuera_de_m3[v3]")], None),
    ("M23", "whitelist: sin exigir que el reparto cuadre (G3 en la correccion)",
     [(REP, "        if (estado_atr == \"COMPLETA\" and total != importe_gasto) or (\n",
       "        if False and (\n")],
     [a("test_whitelist_rechaza_sin_efectos[<lambda>-REPARTO_NO_CORREGIBLE0]")], None),
    ("M24", "coherencia: el derecho no acompana a la parte corregida",
     [(REP, "            efectos_a_actualizar[efecto_pos] = {\"importe_delta\": nuevas[atr[0]]}\n", "")],
     [a("test_a_cambiar_importes_actualiza_el_derecho_coherente")], None),
    ("M25", "coherencia: se corrige aunque el efecto de la posicion no sea demostrable",
     [(REP, "            if abs(importes_efecto[efecto_pos]) != atr[3]:\n", "            if False:\n")],
     [a("test_a_coherencia_no_demostrable_se_rechaza")], None),
    # ---------------------------------------------------------------- capacidad (M4) en cobro/pago
    ("M26", "cobro sin comprobar la capacidad de la cuenta",
     [(REP, "                rechazo_cuenta(sesion, cuenta_id, \"INGRESO\" if operacion_motor == \"COBRO\" else \"GASTO\", fecha)\n",
       "")],
     [a("test_cobro_sin_capacidad_y_posicion_ajena")], None),
    # ---------------------------------------------------------------- orden de P4
    ("M27", "orden (i): OP-22 sin el advisory antes de la cuenta (lo pide OP-22 despues)",
     [(REP, "        if declaradas:\n            tomar_inversiones(sesion)\n", "")],
     [T201 + "test_orden_op22_con_posicion"], None),
    ("M28", "orden (ii): OP-22 bloquea la cuenta ANTES del advisory (candidato A)",
     [(REP, "        if declaradas:\n            tomar_inversiones(sesion)\n        # 1. Cuenta FNKU (solo si pague yo).\n"
            "        if isinstance(intencion.pagado_por, PagadoConCuenta):\n"
            "            bloquear_cuentas(sesion, intencion.pagado_por.cuenta_id)\n",
       "        if isinstance(intencion.pagado_por, PagadoConCuenta):\n"
       "            bloquear_cuentas(sesion, intencion.pagado_por.cuenta_id)\n"
       "        if declaradas:\n            tomar_inversiones(sesion)\n        # 1. Cuenta FNKU (solo si pague yo).\n")],
     [T201 + "test_orden_op22_con_posicion"], None),
    ("M29", "orden (ii): cobro/pago bloquean la cuenta ANTES del advisory",
     [(REP, "        tomar_inversiones(sesion)\n        if cuenta_id is not None:\n            bloquear_cuentas(sesion, cuenta_id)\n",
       "        if cuenta_id is not None:\n            bloquear_cuentas(sesion, cuenta_id)\n        tomar_inversiones(sesion)\n")],
     [T201 + "test_orden_reducciones[cobro]", T201 + "test_orden_reducciones[pago]"], None),
    ("M30", "orden (iii): «Corregir reparto» bloquea el hecho antes que el advisory",
     [(REP, "        integridad_posicion.adquirir_raiz(sesion, owner, hechos=[hecho_id], advisory=True)\n",
       "        integridad_posicion.adquirir_raiz(sesion, owner, hechos=[hecho_id], advisory=False)\n")],
     [T201 + "test_orden_op21_corregir_reparto"], None),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(tests: list[str]) -> int:
    """Ejecuta los nodeids por suite (api con su rootdir; backend aparte). rc != 0 si alguno falla."""
    api = [t for t in tests if t.startswith("tests/api/")]
    resto = [t for t in tests if not t.startswith("tests/api/")]
    rc = 0
    for grupo, extra in ((api, ["--rootdir=tests/api"]), (resto, [])):
        if not grupo:
            continue
        cmd = [sys.executable, "-m", "pytest", *grupo, "-q", "-x", "-p", "no:cacheprovider", *extra]
        rc = rc or subprocess.run(cmd, cwd=RAIZ, capture_output=True).returncode
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
    if os.getenv("GAPTO_M3_CONCURRENCIA") != "1":
        sys.exit("Falta GAPTO_M3_CONCURRENCIA=1: los discriminantes seriales se omitirian.")
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
             ",".join(sorted({pathlib.Path(t.split("::")[0]).name for t in tests})), nota)
        veredictos.append(v)
        anotar(salida, " | ".join(v))
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    equivalentes = sum(1 for v in veredictos if v[1] == "EQUIVALENTE")
    anotar(salida, f"RESUMEN {muertos} muertos, {equivalentes} equivalentes documentados, "
                   f"{len(veredictos) - muertos - equivalentes} otros / {len(veredictos)}")
    sys.exit(0 if muertos + equivalentes == len(veredictos) else 1)


if __name__ == "__main__":
    main()
