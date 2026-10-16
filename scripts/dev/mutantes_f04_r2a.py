# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f04_r2a.py
# Ruta: scripts/dev/mutantes_f04_r2a.py
# Descripcion: Arnes de mutacion de F04-R2 R2-A (F04-D060; mandato F04-R2A
#   v1.0 §4 y encadenado 2026-10-16 v1.2: un mutante por guarda, 100 % muertos
#   o equivalentes documentados, bajo el rol real gapto_runtime con RLS).
#   Mismo motor que mutantes_f04_r1.py (D-181, D-192, D-193, WM 12C.2):
#     - sustituciones de texto exacto (UNA ocurrencia) y sus discriminantes
#       (nodeid de pytest de tests/backend);
#     - journal durable ANTES de tocar el primer byte; si al arrancar hay un
#       journal pendiente: restaura, verifica y aborta;
#     - preflight verde de todos los discriminantes antes del primer mutante;
#     - tras cada mutante se restaura y se verifica la identidad byte a byte;
#     - veredicto: MUERTO | VIVO | NO_CLASIFICABLE (EQUIVALENTE si se declara).
#   Guardas: pertenencia en el propio UPDATE/DELETE (A01 actualizar_efecto,
#   A02 eliminar_efecto, A03 eliminar_conciliacion, A04 recuento de
#   aportaciones); autoridad sobre relaciones (A05 sin AND hecho_origen_id,
#   A06 regla v0.5 «origen o destino», A07 relectura que tras 0 filas vuelve a
#   borrar); retirar_vinculo (A08 sin prevision_id_esperada, A09 sin la
#   relectura tras los locks, A10 version comparada antes de los locks,
#   V05-02); C3 (A11 orden antiguo: sin advisory antes del hecho, V05-03,
#   reproduce el 40P01); oraculo «sin lock del destino» (A12 FOR SHARE del
#   destino en OP-21, AJ-NEON-04).
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable> GAPTO_F04R2A_CONCURRENCIA=1
#        GAPTO_F04R1_CONCURRENCIA=1 python scripts/dev/mutantes_f04_r2a.py [--solo ID,ID]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F04-R2 R2-A)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f04_r2a.journal.json"

REPO = "backend/app/repositories/correcciones_repository.py"
SERV = "backend/app/services/correcciones_service.py"
PREV = "backend/app/services/previsiones_service.py"
POS = "backend/app/services/posiciones_service.py"
T14A = "tests/backend/test_14a_f04_r2a_discriminantes.py::"
T14B = "tests/backend/test_14b_f04_r2a_concurrencia_serial.py::"
T129 = "tests/backend/test_129_f04_r1_huecos.py::"
T139 = "tests/backend/test_139_f04_r1_concurrencia_serial.py::"
T142 = "tests/backend/test_142_f04_r3_interleavings.py::"


def par139(escenario: str, primero: str) -> str:
    return f"{T139}test_f5_par_serial[{escenario}-{primero}-primero]"


#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    ("A01", "actualizar_efecto sin el filtro hecho_id",
     [(REPO, "         WHERE e.id = %s::uuid\n           AND e.hecho_id = %s::uuid\n        RETURNING antes.snapshot",
       "         WHERE e.id = %s::uuid AND %s::uuid IS NOT NULL\n        RETURNING antes.snapshot")],
     [T14A + "test_d_a1_actualizar_un_efecto_de_otro_hecho_rechazado",
      T129 + "test_caracterizacion_op21_actualiza_un_efecto_de_otro_hecho"], None),
    ("A02", "eliminar_efecto sin el filtro hecho_id",
     [(REPO, "         WHERE e.id = %s::uuid\n           AND e.hecho_id = %s::uuid\n        RETURNING ({})::text",
       "         WHERE e.id = %s::uuid AND %s::uuid IS NOT NULL\n        RETURNING ({})::text")],
     [T14A + "test_d_a1_eliminar_un_efecto_de_otro_hecho_rechazado"], None),
    ("A03", "eliminar_conciliacion sin el filtro hecho_id",
     [(REPO, "         WHERE h.id = %s::uuid\n           AND h.hecho_id = %s::uuid\n",
       "         WHERE h.id = %s::uuid AND %s::uuid IS NOT NULL\n")],
     [T14A + "test_d_a1_retirar_una_conciliacion_de_otro_hecho_rechazado",
      T129 + "test_caracterizacion_op21_retira_una_conciliacion_de_otro_hecho"], None),
    ("A04", "recuento de aportaciones sin el filtro hecho_id",
     [(REPO, "WHERE a.hecho_movimiento_tesoreria_id = %s::uuid AND h.hecho_id = %s::uuid\",",
       "WHERE a.hecho_movimiento_tesoreria_id = %s::uuid AND %s::uuid IS NOT NULL\",")],
     [T14A + "test_d_a1_conciliacion_de_otro_hecho_con_aportaciones_no_se_revela"], None),
    ("A05", "eliminar_relacion sin AND hecho_origen_id",
     [(REPO, "         WHERE r.id = %s::uuid\n           AND r.hecho_origen_id = %s::uuid\n",
       "         WHERE r.id = %s::uuid AND %s::uuid IS NOT NULL\n")],
     [T14A + "test_d_a2_desde_el_destino_con_origen_activo_rechazado",
      T14A + "test_d_a2_desde_el_destino_con_origen_anulado_rechazado",
      T14A + "test_d_a2_ajeno_otro_owner_e_inexistente_sin_filtracion",
      T129 + "test_caracterizacion_op21_retira_una_relacion_de_otro_hecho"], None),
    ("A06", "regla v0.5: el origen O el destino retiran la relacion",
     [(REPO, "           AND r.hecho_origen_id = %s::uuid\n",
       "           AND %s::uuid IN (r.hecho_origen_id, r.hecho_destino_id)\n")],
     [T14A + "test_d_a2_desde_el_destino_con_origen_activo_rechazado",
      T14A + "test_d_a2_desde_el_destino_con_origen_anulado_rechazado"], None),
    ("A07", "relectura que, tras 0 filas, vuelve a borrar (desde el destino, con el origen releido)",
     [(SERV, "            if snapshot is None:\n                raise self._rechazo_relacion(sesion, relacion_id, datos.hecho_id)",
       "            if snapshot is None:\n"
       "                fila = repo_corr.leer_relacion(sesion, relacion_id)\n"
       "                if fila is not None and fila[1] == datos.hecho_id:\n"
       "                    snapshot = repo_corr.eliminar_relacion(sesion, relacion_id, fila[0])\n"
       "            if snapshot is None:\n                raise self._rechazo_relacion(sesion, relacion_id, datos.hecho_id)")],
     [T14A + "test_d_a2_desde_el_destino_con_origen_activo_rechazado",
      T14A + "test_d_a2_desde_el_destino_con_origen_anulado_rechazado",
      T14B + "test_c_rel_04_destino_mientras_el_origen_retira"], None),
    ("A08", "retirar_vinculo sin la comprobacion de prevision_id_esperada",
     [(PREV, "                releido[\"prevision_id\"] != prevision_id_esperada\n                or ",
       "                False\n                or ")],
     [T14A + "test_d_a3_vinculo_de_otra_prevision_con_la_misma_version",
      T14A + "test_d_a3_tras_reintento_por_conjunto_cambiado"], None),
    ("A09", "retirar_vinculo sin la relectura tras los locks (usa la lectura previa)",
     [(PREV, "            releido = repo_prev.leer_vinculo(sesion, vinculo_id)\n"
             "            if releido is None or releido[\"prevision_id\"] != prevision_id:\n"
             "                raise ConjuntoCambiado()\n            # F04-R2 §7.4",
       "            releido = vinculo\n"
       "            if releido is None or releido[\"prevision_id\"] != prevision_id:\n"
       "                raise ConjuntoCambiado()\n            # F04-R2 §7.4")],
     [T14A + "test_d_a3_tras_reintento_por_conjunto_cambiado",
      T14A + "test_d_a3_hecho_del_vinculo_cambiado_tras_la_lectura"], None),
    ("A10", "retirar_vinculo con la version comparada ANTES de los locks (V05-02)",
     [(PREV, "            prevision_id = vinculo[\"prevision_id\"]\n            hecho_leido = vinculo[\"hecho_id\"]\n",
       "            prevision_id = vinculo[\"prevision_id\"]\n            hecho_leido = vinculo[\"hecho_id\"]\n"
       "            if repo_prev.leer_prevision(sesion, prevision_id)[\"row_version\"] != prevision_row_version_esperada:\n"
       "                raise ErrorMotor(CodigoError.VERSION_DESFASADA, \"mutante A10\")\n"),
      (PREV, "            if version_bloqueada != prevision_row_version_esperada:\n",
       "            if False and version_bloqueada != prevision_row_version_esperada:\n")],
     [par139("dos_retirar", "retirar_a"), par139("dos_retirar", "retirar_b"), par139("cv_retirar", "cv")], None),
    ("A11", "C3: OP-12A enganchado sin advisory antes del hecho (orden antiguo, V05-03)",
     [(POS, "            if datos.importe_inicial is not None:\n                # F04-R2 C3",
       "            if False:\n                # F04-R2 C3")],
     [T142 + "test_il5_r_f04_033_op12_enganchado_contra_op21_toca_inversion[toca_inversion-OP-12A-primero]"], None),
    ("A12", "OP-21 bloquea el destino FOR SHARE al retirar la relacion (oraculo sin lock)",
     [(REPO, "    es el origen (destino, ajena, inexistente o no visible).\"\"\"\n",
       "    es el origen (destino, ajena, inexistente o no visible).\"\"\"\n"
       "    sesion.uno(\"SELECT 1 FROM gapto.hechos_financieros WHERE id = (SELECT hecho_destino_id FROM \"\n"
       "               \"gapto.hecho_relaciones WHERE id = %s::uuid) FOR SHARE\", (relacion_id,))\n")],
     [T14B + "test_c_rel_01_op21_origen_frente_a_op13_destino[80.0000-OP-21-primero]",
      T14B + "test_c_rel_02_op21_origen_frente_a_op03_destino[OP-21-primero]"], None),
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
    for flag in ("GAPTO_F04R2A_CONCURRENCIA", "GAPTO_F04R1_CONCURRENCIA"):
        if os.getenv(flag) != "1":
            sys.exit(f"Falta {flag}=1: los discriminantes seriales se omitirian.")
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
