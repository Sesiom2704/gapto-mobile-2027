# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f06_t4_aj05.py
# Ruta: scripts/dev/mutantes_f06_t4_aj05.py
# Descripcion: Arnes de mutacion de AJ-05 ampliado + R-C7-07 (F06 T4; mandato b4ff6b70… §5 «Mutantes», adenda 01
#   24113472… y adenda 02 9744307e… §5). Un mutante por guarda: los del diseno v0.2 §8 (DS1-DS15, con DS9b), uno por
#   guarda de AJ-R2 (R1-R8; R6 coincide con DS14 y no se duplica; R4b es la variante del manejador global) y los de la
#   adenda 02 (A02: COMMIT_INDETERMINADO -> TIEMPO_AGOTADO; A02b: el 25P04 del COMMIT sin persistencia indeterminada).
#   C19 (hallazgo en Neon, diseno §5.2): corte de sesion antes del COMMIT tratado como sin persistencia.
#   Mismo motor que mutantes_f06_t4_dc710.py (journal durable, preflight verde, restauracion verificada por SHA-256,
#   veredicto a disco en cuanto se conoce) con base limpia por llamada y clasificacion de la muerte
#   (scripts/dev/base_limpia_mutante.py; GAPTO_MUTANTES_CLASIFICACION). Discriminantes: tests/api/test_314 y test_315.
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable 0356> [GAPTO_MUTANTES_CLASIFICACION=<jsonl>]
#        python -u scripts/dev/mutantes_f06_t4_aj05.py [--solo ID,ID] [--salida fichero]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F06 T4 · AJ-05, mandato b4ff6b70…, adendas 01 y 02)
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
JOURNAL = RAIZ / ".mutantes_f06_t4_aj05.journal.json"

PET = "backend/app/core/peticion.py"
UT = "backend/app/core/unidad_trabajo.py"
MW = "backend/app/api/middleware_peticion.py"
REG = "backend/app/api/registro_peticiones.py"
APP = "backend/app/api/app.py"
CLA = "backend/app/core/clasificacion_errores.py"
T = "tests/api/test_314_f06_t4_aj05_plazos_desenlaces.py::"
S = "tests/api/test_315_f06_t4_aj05_semantica_postgres.py::"

C01A = T + "test_c01a_c08_lock_timeout_antes_del_commit_no_guardado_y_reenvio_crea_una_vez"
C01B = T + "test_c01b_statement_timeout_antes_del_commit_no_guardado"
C02 = T + "test_c02_b_c_transaction_timeout_corta_el_commit_diferido_indeterminado_y_se_reconcilia"
C04 = T + "test_c04_plazo_agotado_tras_escritura_confirmada_nunca_es_no_guardado"
C05 = T + "test_c05_o3_o6_replay_por_ruta_tras_fallo_de_la_segunda_lectura[corregir-categoria]"
C10 = T + "test_c10_ningun_intento_empieza_sin_plazo_y_el_deadline_no_se_reinicia"
C11 = T + "test_c11_conexion_y_esperas_no_superan_el_plazo_mas_el_margen"
C13 = T + "test_c13_plazo_agotado_no_es_error_motor_y_lo_traduce_un_manejador_global"
C15A = T + "test_c15a_recibida_y_terminada_con_identidades_separadas"
C15C = T + "test_c15c_excepcion_del_backend_registra_terminada_sin_mensaje"
C15F = T + "test_c15f_barrido_de_secretos_e_importes"
C16B = T + "test_c16_lock_timeout_por_clase_explicito_sin_herencia_de_sesion[POST-/v1/hipotecas/x/revision-0]"
C17 = T + "test_c17_57014_de_una_cancelacion_externa_no_es_plazo_ni_se_reintenta"
C18 = T + "test_c18_55p03_de_otro_origen_en_clase_b_no_es_plazo"
O1B = T + "test_o1b_el_xid_no_es_el_criterio"
O2 = T + "test_o2_rechazo_funcional_tras_commit_se_conserva"
O2C = T + "test_o2c_rechazo_de_error_motor_tras_commit_no_lo_convierte_el_manejador"
O45 = T + "test_o4_o5_c15e_el_logger_que_falla_no_cambia_ninguna_respuesta"
RED = T + "test_red_de_seguridad_sustituye_solo_un_no_guardado_falso"
SOLO = T + "test_solo_lectura_es_read_only_desde_la_primera_sentencia"
S_ST = S + "test_statement_timeout_propio_por_la_unidad_de_trabajo_es_plazo_y_cero_filas"
S_B = S + "test_adenda02_b_por_la_unidad_de_trabajo_commit_indeterminado"
C19 = T + "test_c19_corte_de_sesion_antes_del_commit_es_indeterminado_nunca_500_ni_no_guardado"
S_C = S + "test_corte_por_transaction_timeout_antes_del_commit_por_la_unidad_de_trabajo"

EXC_REG = "        except BaseException:  # noqa: BLE001 - nada del registro puede alterar la respuesta\n"

MUTANTES = [
    # ---------------------------------------------------------------- diseno v0.2 §8
    ("DS1", "sin statement_timeout propio",
     [(UT, '(f"{max(1, int(peticion.restante() * 1000))}ms", f"{peticion.lock_timeout_ms()}ms"),',
       '("0", f"{peticion.lock_timeout_ms()}ms"),')], [C01B, S_ST], None),
    ("DS2", "sin lock_timeout en la clase A",
     [(PET, 'LOCK_TIMEOUT_CLASE_MS: dict[str, int] = {"A": 3000, "B": 0}',
       'LOCK_TIMEOUT_CLASE_MS: dict[str, int] = {"A": 0, "B": 0}')], [C01A], None),
    ("DS3", "lock_timeout distinto de 0 en la clase B",
     [(PET, 'LOCK_TIMEOUT_CLASE_MS: dict[str, int] = {"A": 3000, "B": 0}',
       'LOCK_TIMEOUT_CLASE_MS: dict[str, int] = {"A": 3000, "B": 3000}')], [C16B], None),
    ("DS4", "deadline reiniciado en cada intento",
     [(UT, "                if peticion.restante() < pet.MINIMO_PARA_INTENTO_S:\n",
       "                peticion.deadline = time.monotonic() + pet.PLAZO_CLASE_S[peticion.clase]\n"
       "                if peticion.restante() < pet.MINIMO_PARA_INTENTO_S:\n")], [C10], None),
    ("DS5", "transaction_timeout fijado con transaccion implicita (sin autocommit el BEGIN pasa a savepoint)",
     [(UT, "    conexion.autocommit = True\n", "    pass\n")], [C02, S_B], None),
    ("DS6", "TIEMPO_AGOTADO con escritura confirmada",
     [(APP, "        if _persistencia(request) is pet.Persistencia.NINGUNA:\n", "        if True:\n")], [C04], None),
    ("DS7", "el tiempo agotado como ErrorMotor (cae en las envolturas de ruta)",
     [(PET, "class PlazoAgotado(Exception):",
       "from app.core.errores import ErrorMotor as _EM  # noqa: E402\n\n\nclass PlazoAgotado(_EM):")], [C13], None),
    ("DS8", "57014 reintentado en el servidor",
     [(CLA, 'SQLSTATES_REINTENTABLES: frozenset[str] = frozenset({"40P01", "40001"})',
       'SQLSTATES_REINTENTABLES: frozenset[str] = frozenset({"40P01", "40001", "57014"})')], [C17], None),
    ("DS9", "55P03 de otro origen tratado como plazo",
     [(UT, '    if sqlstate == "55P03" and peticion.lock_timeout_ms() > 0:', '    if sqlstate == "55P03":')],
     [C18], None),
    ("DS9b", "57014 de otro origen (cancelacion externa) tratado como plazo",
     [(UT, '    if sqlstate == "57014" and time.monotonic() >= peticion.deadline - pet.TOLERANCIA_DEADLINE_S:',
       '    if sqlstate == "57014":')], [C17], None),
    ("DS10", "sin seguimiento de escritura (la persistencia acumulada nunca es confirmada)",
     [(PET, "        if EstadoUnidad.COMMIT_CONFIRMADO in estados:\n            return Persistencia.ESCRITURA_CONFIRMADA\n",
       "")], [C04, C05], None),
    ("DS11", "sin red de seguridad del middleware",
     [(MW, "                        and estado.persistencia() is pet.Persistencia.ESCRITURA_CONFIRMADA):",
       "                        and False):")], [RED], None),
    ("DS12", "identidad HTTP igual a la intencion",
     [(MW, '        identidades = {"http_request_id": str(estado.http_request_id),',
       '        identidades = {"http_request_id": uuid_de_cabecera(cabeceras.get("x-gapto-intencion-id")),')],
     [C15A], None),
    ("DS13", "TERMINADA omitida en una excepcion",
     [(MW, '        ruta = scope.get("route")\n',
       '        if excepcion is not None:\n            return\n        ruta = scope.get("route")\n')], [C15C], None),
    ("DS14", "logger que rompe la respuesta (= R6 de AJ-R2: logger que altera la respuesta)",
     [(REG, EXC_REG + "            self.fallos += 1\n", EXC_REG + "            self.fallos += 1\n            raise\n"),
      (MW, "        except BaseException:  # noqa: BLE001 - fail-open: el registro nunca altera la respuesta\n"
           "            pass\n", "        finally:\n            pass\n")], [O45], None),
    ("DS15", "Authorization en el registro",
     [(MW, '        identidades = {"http_request_id": str(estado.http_request_id),',
       '        identidades = {"authorization": cabeceras.get("authorization"), '
       '"http_request_id": str(estado.http_request_id),')], [C15F], None),
    # ---------------------------------------------------------------- una por guarda de AJ-R2 (R6 = DS14)
    ("R1", "estado acumulado reiniciado por unidad",
     [(UT, "            peticion.unidades.append(registro)   # acumulado: nunca se borra lo de otra unidad",
       "            peticion.unidades[:] = [registro]")], [C05], None),
    ("R2", "XID usado como criterio de escritura",
     [(PET, "        estados = [i.estado for u in self.unidades if not u.solo_lectura for i in u.intentos]",
       "        estados = [i.estado for u in self.unidades if not u.solo_lectura for i in u.intentos if i.xid_auxiliar]")],
     [O1B], None),
    ("R3", "solo_lectura sin READ ONLY",
     [(UT, '                            conexion.execute("SET TRANSACTION READ ONLY")', "                            pass")],
     [SOLO], None),
    ("R4", "red de seguridad que convierte un 4xx",
     [(MW, '                if (inicio["status"] >= 500 and salida["codigo"] in NO_GUARDADO_5XX',
       '                if (inicio["status"] >= 400')], [O2], None),
    ("R4b", "el manejador global convierte un rechazo 4xx tras un COMMIT",
     [(APP, "        if status >= 500 and _persistencia(request) is not pet.Persistencia.NINGUNA:",
       "        if status >= 400 and _persistencia(request) is not pet.Persistencia.NINGUNA:")], [O2C], None),
    ("R5", "la traza rebaja un COMMIT confirmado a posible",
     [(MW, '        return "ESCRITURA_CONFIRMADA" if completa else "ESCRITURA_CONFIRMADA / RESPUESTA_NO_COMPLETADA"',
       '        return "ESCRITURA_CONFIRMADA" if completa else "COMMIT_INDETERMINADO"')], [C05], None),
    ("R7", "secreto en el aviso de consola",
     [(REG, EXC_REG + "            self.fallos += 1\n            try:\n                self._consola(AVISO_CONSOLA)",
       EXC_REG.replace("BaseException:", "BaseException as exc:") + "            self.fallos += 1\n            try:\n"
       "                self._consola(f\"{AVISO_CONSOLA} {exc}\")")], [O45], None),
    ("R8", "deadline reiniciado en el backoff",
     [(UT, "                        time.sleep(espera)\n                        continue\n",
       "                        time.sleep(espera)\n                        if peticion is not None:\n"
       "                            peticion.deadline += espera\n                        continue\n")], [C10, C11], None),
    # ---------------------------------------------------------------- adenda 02 §5 (AJ-R4-05)
    ("A02", "COMMIT_INDETERMINADO -> TIEMPO_AGOTADO (25P04 en el COMMIT tomado como rollback y plazo propio)",
     [(UT, "        return pet.EstadoUnidad.COMMIT_INDETERMINADO if _es_corte(exc) else pet.EstadoUnidad.ROLLBACK_CONFIRMADO",
       "        return pet.EstadoUnidad.ROLLBACK_CONFIRMADO"),
      (UT, '    if sqlstate == "55P03" and peticion.lock_timeout_ms() > 0:',
       '    if sqlstate == "25P04":\n        return "STATEMENT_TIMEOUT"\n'
       '    if sqlstate == "55P03" and peticion.lock_timeout_ms() > 0:')], [C02, S_B], None),
    ("A02b", "25P04 durante el COMMIT sin persistencia indeterminada (acaba en un 5xx sin «no confirmado»)",
     [(PET, "        if EstadoUnidad.COMMIT_INDETERMINADO in estados:\n            return Persistencia.COMMIT_INDETERMINADO\n",
       "")], [C02, S_B], None),
    ("C19", "corte de sesion antes del COMMIT, ya conectada, tratado como sin persistencia (acaba en 500 o no guardado)",
     [(UT, "        return pet.EstadoUnidad.CORTE_ANTES_DEL_COMMIT if conectada else pet.EstadoUnidad.ABORTADA_SIN_COMMIT",
       "        return pet.EstadoUnidad.ABORTADA_SIN_COMMIT")], [C19, S_C], None),
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
