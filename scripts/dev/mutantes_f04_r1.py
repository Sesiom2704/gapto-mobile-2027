# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f04_r1.py
# Ruta: scripts/dev/mutantes_f04_r1.py
# Descripcion: Arnes de mutacion de F04-R1 (mandato F04-R1 IMPL v1.0 §F5.4:
#   100 % muertos o equivalentes documentados, bajo el rol real
#   gapto_runtime con RLS). Mismo motor que mutantes_f05_06_m4.py (D-181,
#   D-192, D-193, WM 12C.2):
#     - cada mutante declara sustituciones de texto exacto (UNA ocurrencia) y
#       sus discriminantes (nodeid de pytest de tests/backend);
#     - journal durable ANTES de tocar el primer byte; si al arrancar hay un
#       journal pendiente: restaura, verifica y aborta;
#     - preflight verde de todos los discriminantes antes del primer mutante;
#     - tras cada mutante se restaura y se verifica la identidad byte a byte;
#     - veredicto: MUERTO | VIVO | NO_CLASIFICABLE. Un mutante declarado
#       EQUIVALENTE (con su justificacion) que sale VIVO se informa como
#       EQUIVALENTE; si sale MUERTO, como MUERTO.
#   Guardas: G-R1-A (R01 sin dependencias, R02 solo DEVOLUCION_DE, R03 origen
#   ANULADO cuenta), G-R1-B (R04 OP-14 sin ACTIVO, R05 OP-18 sin ACTIVO, R06
#   causal fuera de la raiz de OP-14), G-R1-C (R07 OP-17 sin tope, R08
#   corregir_vinculo sin tope, R09 `>` -> `>=`, R10 sin «agrava», R11 traslado
#   compensado, R12 sin rama NO_DETERMINABLE, R13 NULL como 0), G-R1-D (R14
#   OP-17 sin lock del hecho, R15 corregir_vinculo sin relectura, R16
#   adquisicion de la propagacion en el orden de procesamiento, R17 retorno de
#   tocar_prevision ignorado; R18 OP-17 con el estado releido antes que la
#   version, la causa del KO IL4 de F6; R19/R20 corregir_vinculo/retirar_vinculo
#   sin la guarda de version previa a la relectura). R15 pasa a EQUIVALENTE con
#   el patron CORR (ver su justificacion).
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable> GAPTO_F04R1_CONCURRENCIA=1
#        python scripts/dev/mutantes_f04_r1.py [--solo ID,ID]
#   Sin GAPTO_F04R1_CONCURRENCIA=1 los discriminantes de test_139 se omiten.
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.2.0 (F04-R1 CORR pasos 1.3 y 3.1): mutantes R18, R19 y R20; R15 equivalente.
# Version: 0.1.0 (F04-R1 IMPL F5)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f04_r1.journal.json"

HSERV = "backend/app/services/hechos_service.py"
HREPO = "backend/app/repositories/hechos_repository.py"
POS = "backend/app/services/posiciones_service.py"
SUP = "backend/app/services/suplementos_service.py"
PREV = "backend/app/services/previsiones_service.py"
T138 = "tests/backend/test_138_f04_r1_discriminantes.py::"
T139 = "tests/backend/test_139_f04_r1_concurrencia_serial.py::"


def par(escenario: str, primero: str) -> str:
    return f"{T139}test_f5_par_serial[{escenario}-{primero}-primero]"


#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    ("R01", "OP-03 sin comprobacion de dependencias activas",
     [(HSERV, "            if dependientes:\n", "            if False and dependientes:\n")],
     [T138 + "test_a_anular_original_con_devolucion_activa"], None),
    ("R02", "dependencias limitadas a DEVOLUCION_DE",
     [(HREPO, "             WHERE r.hecho_destino_id = %s::uuid\n               AND o.estado = 'ACTIVO'",
       "             WHERE r.hecho_destino_id = %s::uuid AND r.tipo_relacion = 'DEVOLUCION_DE'\n"
       "               AND o.estado = 'ACTIVO'")],
     [T138 + "test_b_anular_causal_con_reembolso_activo"], None),
    ("R03", "relacion con origen ANULADO cuenta como activa",
     [(HREPO, "               AND o.estado = 'ACTIVO'\n               AND o.owner_user_id",
       "               AND o.owner_user_id")],
     [T138 + "test_d_anular_cuando_la_unica_devolucion_esta_anulada"], None),
    ("R04", "OP-14 sin comprobacion ACTIVO del causal",
     [(POS, "        if estado_causal[1] != \"ACTIVO\":", "        if False:")],
     [T138 + "test_f_op14_hacia_causal_anulado"], None),
    ("R05", "OP-18 sin comprobacion ACTIVO del ajustado",
     [(SUP, "                if ajustado is None or ajustado[1] != \"ACTIVO\":", "                if ajustado is None:")],
     [T138 + "test_g_op18_hacia_ajustado_anulado"], None),
    ("R06", "causal fuera de la raiz de OP-14",
     [(POS, "            hechos_raiz = [relacion[0]] if relacion[0] is not None else []",
       "            hechos_raiz = []")],
     [par("op03_op14", "OP-03"), par("op03_op14", "OP-14")], None),
    ("R07", "OP-17 sin tope de porcion",
     [(PREV, "            exigir_porcion(\n                sesion,\n                datos.hecho_id,",
       "            (lambda *a, **k: None)(\n                sesion,\n                datos.hecho_id,")],
     [T138 + "test_h_doble_asignacion_de_la_misma_porcion"], None),
    ("R08", "corregir_vinculo sin tope de porcion (mismo hecho)",
     [(PREV, "                exigir_porcion(sesion, hecho_viejo, {vinculo_id: solicitado}, solicitado=solicitado)",
       "                pass")],
     [T138 + "test_j1_corregir_vinculo_al_alza_por_encima_del_tope"], None),
    ("R09", "`>` -> `>=` en el tope",
     [(PREV, "    if sigma_posterior > tope and (", "    if sigma_posterior >= tope and (")],
     [T138 + "test_i_asignaciones_que_suman_exactamente_el_total"], None),
    ("R10", "sin la condicion «agrava»",
     [(PREV, "sigma_previa is None or sigma_previa <= tope or sigma_posterior > sigma_previa",
       "sigma_previa is None or sigma_previa <= tope")],
     [T138 + "test_exceso_que_se_agrava"], None),
    ("R11", "traslado entre hechos compensado (no se evalua el destino)",
     [(PREV, "                exigir_porcion(sesion, hecho_nuevo, {vinculo_id: solicitado}, solicitado=solicitado)",
       "                pass")],
     [T138 + "test_traslado_destino_en_exceso_y_origen_que_mejora"], None),
    ("R12", "sin rama NO_DETERMINABLE",
     [(PREV, "        if aumenta or sube:\n            raise rechazo(\"NO_DETERMINABLE\")\n        return",
       "        return")],
     [T138 + "test_k_importe_total_null_y_segundo_vinculo", T138 + "test_l_multidivisa_y_segundo_vinculo"], None),
    ("R13", "importe_total NULL tratado como 0",
     [(PREV, "    tope, moneda_hecho = porcion\n",
       "    tope, moneda_hecho = (CERO if porcion[0] is None else porcion[0]), porcion[1]\n")],
     [T138 + "test_k_importe_total_null_y_segundo_vinculo"], None),
    ("R14", "OP-17 sin lock del hecho",
     [(PREV, "            repo_rel.bloquear_hechos(sesion, [datos.hecho_id])\n", "")],
     [par("dos_op17", "OP-17a"), par("dos_op17", "OP-17b"), par("cv_op17", "cv"), par("cv_op17", "OP-17")], None),
    ("R15", "corregir_vinculo sin relectura del vinculo",
     [(PREV, "            if (\n                releido is None\n", "            if False and (\n                releido is None\n")],
     [par("relectura_hecho", "cv_hecho"), par("relectura_prevision", "cv_a_p2")],
     "CORR: la guarda de version de las previsiones bloqueadas precede a la relectura, y todo writer de "
     "prevision_hechos (insertar en OP-17, actualizar en corregir_vinculo, borrar en retirar_vinculo) toca "
     "antes, en la misma transaccion, la previsión de origen del vinculo (corr/precedencias.md): un vinculo "
     "movido o retirado siempre deja una version distinta y la relectura no es alcanzable. Defensa en profundidad"),
    ("R16", "propagacion: adquisicion en el orden de procesamiento (por fecha, sin reglas)",
     [(PREV, "    _bloquear_reglas(sesion, reglas)\n    for sucesor_id in sucesores:\n"
             "        repo_prev.bloquear_prevision(sesion, sucesor_id)\n", "")],
     [f"{T139}test_c1_corregir_vinculo_frente_a_propagacion_de_op02"], None),
    ("R17", "retorno de tocar_prevision ignorado en la propagacion",
     [(PREV, "        if repo_prev.tocar_prevision(sesion, sucesor[\"id\"], detalle[\"row_version\"]) is None:\n",
       "        if repo_prev.tocar_prevision(sesion, sucesor[\"id\"], detalle[\"row_version\"]) is None and False:\n")],
     [f"{T139}test_c1_corregir_vinculo_frente_a_propagacion_de_op02", par("op17_op02", "OP-17")],
     "con G-R1-D el sucesor ya esta bajo FU y su row_version se lee despues del lock y de la relectura del "
     "conjunto: tocar_prevision no puede fallar. Es defensa en profundidad; no hay entrelazado que lo alcance"),
    ("R18", "OP-17 con el estado releido antes que la version (KO IL4 de F6)",
     [(PREV, "            if prevision[\"row_version\"] != row_version_esperada:\n",
       "            if prevision[\"estado\"] != ABIERTA:\n"
       "                raise ErrorMotor(CodigoError.ESTADO_PREVISION_INCOMPATIBLE, \"mutante R18\")\n"
       "            if prevision[\"row_version\"] != row_version_esperada:\n")],
     [par("op22r_op17", "OP-22")], None),
    ("R19", "corregir_vinculo sin la guarda de version previa a la relectura",
     [(PREV, "                if bloqueadas[identificador] != esperada:\n",
       "                if False and bloqueadas[identificador] != esperada:\n")],
     [par("relectura_prevision", "cv_a_p2"), par("cv_retirar", "retirar")], None),
    ("R20", "retirar_vinculo sin la guarda de version previa a la relectura",
     [(PREV, "            if version_bloqueada != prevision_row_version_esperada:\n",
       "            if False and version_bloqueada != prevision_row_version_esperada:\n")],
     [par("dos_retirar", "retirar_a"), par("cv_retirar", "cv")], None),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(tests: list[str]) -> int:
    cmd = [sys.executable, "-m", "pytest", *tests, "-q", "-x", "-p", "no:cacheprovider"]
    return subprocess.run(cmd, cwd=RAIZ, capture_output=True).returncode


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


def main() -> None:
    if not os.getenv("GAPTO_TEST_DATABASE_URL"):
        sys.exit("Falta GAPTO_TEST_DATABASE_URL (base local desechable).")
    if os.getenv("GAPTO_F04R1_CONCURRENCIA") != "1":
        sys.exit("Falta GAPTO_F04R1_CONCURRENCIA=1: los discriminantes de test_139 se omitirian.")
    if recuperar_si_pendiente():
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    solo = None
    if "--solo" in sys.argv:
        solo = set(sys.argv[sys.argv.index("--solo") + 1].split(","))
    elegidos = [m for m in MUTANTES if solo is None or m[0] in solo]
    preflight = sorted({t for m in elegidos for t in m[3]})
    if correr(preflight) != 0:
        sys.exit("PREFLIGHT ROJO: no se muta nada.")
    veredictos = []
    for mid, desc, cambios, tests, equivalencia in elegidos:
        ficheros = sorted({c[0] for c in cambios})
        originales = {f: (RAIZ / f).read_bytes() for f in ficheros}
        textos = {f: b.decode("utf-8") for f, b in originales.items()}
        aplicable = True
        for f, a, b in cambios:
            if textos[f].count(a) != 1:
                aplicable = False
                break
            textos[f] = textos[f].replace(a, b)
        if not aplicable:
            veredictos.append((mid, "NO_CLASIFICABLE", "transformacion no aplicable", desc))
            continue
        JOURNAL.write_text(
            json.dumps({"mutante": mid, "ficheros": [
                {"fichero": f, "original_hex": originales[f].hex(), "sha256": sha(originales[f])} for f in ficheros
            ]}),
            encoding="utf-8",
        )
        if hasattr(os, "sync"):
            os.sync()
        v = "NO_CLASIFICABLE"
        try:
            for f in ficheros:
                (RAIZ / f).write_bytes(textos[f].encode("utf-8"))
            v = "MUERTO" if correr(tests) != 0 else "VIVO"
        finally:
            ok = True
            for f in ficheros:
                (RAIZ / f).write_bytes(originales[f])
                ok = ok and sha((RAIZ / f).read_bytes()) == sha(originales[f])
            JOURNAL.unlink(missing_ok=True)
        if v == "VIVO" and equivalencia:
            v = "EQUIVALENTE"
        nota = f"{desc} [equivalente: {equivalencia}]" if v == "EQUIVALENTE" else desc
        veredictos.append((mid, v if ok else "NO_CLASIFICABLE",
                           ",".join(sorted({pathlib.Path(t.split("::")[0]).name for t in tests})), nota))
    for v in veredictos:
        print(*v, sep=" | ")
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    equivalentes = sum(1 for v in veredictos if v[1] == "EQUIVALENTE")
    print(f"RESUMEN {muertos} muertos, {equivalentes} equivalentes documentados, "
          f"{len(veredictos) - muertos - equivalentes} otros / {len(veredictos)}")
    sys.exit(0 if muertos + equivalentes == len(veredictos) else 1)


if __name__ == "__main__":
    main()
