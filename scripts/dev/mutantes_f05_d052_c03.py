# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_d052_c03.py
# Ruta: scripts/dev/mutantes_f05_d052_c03.py
# Descripcion: Arnes de mutacion del gasto propio reembolsable C-03 (F05-D052
#   paso 2; F05 §66.A.11.8): un mutante por guarda nueva o modificada,
#   resultado MUERTO o EQUIVALENTE documentado. Mismo motor que
#   mutantes_f04_r3_q4.py (D-181, D-192, D-193, WM 12C.2):
#     - sustituciones de texto exacto (UNA ocurrencia) y sus discriminantes
#       (nodeid de pytest; los de tests/api se lanzan con --rootdir=tests/api);
#     - journal durable ANTES de tocar el primer byte; si al arrancar hay un
#       journal pendiente: restaura, verifica y aborta;
#     - preflight verde de todos los discriminantes antes del primer mutante;
#     - tras cada mutante se restaura y se verifica la identidad byte a byte;
#     - el veredicto de CADA mutante se escribe a disco en cuanto se conoce
#       (--salida, append + fsync);
#     - veredicto: MUERTO | VIVO | NO_CLASIFICABLE (EQUIVALENTE si se declara).
#   Mutantes: C03-M01..M10 del borrador tecnico (M09 es de la UI: arnes del
#   cliente; M11 no tiene guarda nueva: el cobro sin INGRESO lo cubren
#   test_131 y M3 sin cambios), politica en el servidor, reutilizacion entre
#   rutas y sello del importe recuperable, lectura unica por entidad, bloqueo
#   de devolucion (tambien con vinculo AFECTA_A de RV3), exclusion M1 en el
#   servidor, anulacion POSICIONES (escritura y lectura), orden de locks,
#   codigo estable de validacion y posiciones_vinculadas sin duplicar.
#   La bateria serial (test_218) necesita GAPTO_C03_CONCURRENCIA=1: el arnes
#   la fija para sus subprocesos.
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable>
#        python scripts/dev/mutantes_f05_d052_c03.py [--solo ID,ID] [--salida fichero]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F05-D052 paso 2; F05 §66.A.11.8)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f05_d052_c03.journal.json"
API = "backend/app/api/"
DTO = API + "dto_reembolsable.py"
EJR = API + "ejecucion_reembolsable.py"
REP = API + "ejecucion_reparto.py"
DREP = API + "dto_reparto.py"
EJD = API + "ejecucion_devolucion.py"
EJA = API + "ejecucion_anulacion.py"
APP = API + "app.py"
EDI = "backend/app/actividad/edicion.py"
ACTS = "backend/app/actores/servicio.py"
OP21P = "backend/app/services/correccion_tesoreria_service.py"
T = "tests/api/test_217_f05_d052_c03_reembolsable.py::"
C = "tests/api/test_218_f05_d052_c03_concurrencia_serial.py::"
ORACULO = T + "test_oraculo_fisico_y_economico_empresa_parcial_y_dos_cobros"
POSITIVOS = [T + "test_persona_y_empresa_recuperacion_total"]
POSTERIORES = [T + "test_posteriores_correccion_anulacion_y_devolucion_bloqueadas"]
AFECTA = [T + "test_posteriores_bloqueadas_con_vinculo_rv3_afecta_a"]
T199_EMPRESA = "tests/api/test_199_f05_06_m3_reparto.py::test_writer_actor_rechaza_sin_efectos"

#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    ("C03-M01", "tope del importe recuperable <= total eliminado (DTO)",
     [(DTO, "        if self.reembolso.importe > self.importe:\n", "        if False:\n")],
     [T + "test_negativo_importe_recuperable_excede_el_total"], None),
    ("C03-M02", "importe recuperable con valor por defecto (opcional)",
     [(DTO, "    tercero_id: uuid.UUID\n    importe: Importe\n", "    tercero_id: uuid.UUID\n    importe: Importe | None = None\n")],
     [T + "test_negativo_reembolso_mal_formado_422"], None),
    ("C03-M03", "atribucion del total al actor de la contraparte en lugar del propio",
     [(EJR, "atribuciones=(DatosAtribucion(atribucion_id=_id(iid, \"atribucion.self\"), actor_id=actor_self,",
       "atribuciones=(DatosAtribucion(atribucion_id=_id(iid, \"atribucion.self\"), actor_id=actor_contraparte,")],
     [ORACULO], None),
    ("C03-M04", "la posicion no se declara (nunca nace el derecho)",
     [(EJR, "hecho=hecho, efectos=[efecto], posiciones=[posicion],", "hecho=hecho, efectos=[efecto], posiciones=[],")],
     [ORACULO], None),
    ("C03-M05a", "naturaleza: cualquier naturaleza admitida en C-03",
     [(ACTS, "    if tercero[\"naturaleza\"] not in NATURALEZAS_REEMBOLSO:\n", "    if False:\n")],
     [T + "test_negativo_naturaleza_no_admitida"], None),
    ("C03-M05b", "naturaleza: C-03 solo admite PERSONA",
     [(ACTS, "NATURALEZAS_REEMBOLSO = frozenset({repo.NATURALEZA_PERSONA, repo.NATURALEZA_EMPRESA})",
       "NATURALEZAS_REEMBOLSO = frozenset({repo.NATURALEZA_PERSONA})")],
     POSITIVOS, None),
    ("C03-M06", "el reparto aplica la politica C-03 (admite EMPRESA)",
     [(REP, "                        actores.validar_tercero_persona(sesion, tercero)\n",
       "                        actores.validar_tercero_reembolso(sesion, tercero)\n")],
     [T + "test_el_reparto_sigue_rechazando_empresa", T199_EMPRESA], None),
    ("C03-M07", "cuenta pagadora opcional",
     [(DTO, "    cuenta_id: uuid.UUID  # cuenta pagadora, obligatoria\n",
       "    cuenta_id: uuid.UUID | None = None  # cuenta pagadora, obligatoria\n")],
     [T + "test_negativo_comunes_obligatorios_sin_default"], None),
    ("C03-M08", "R6 en el validador del gasto compartido eliminada",
     [(DREP, "            if desconocida and sum(conocidas, decimal.Decimal(0)) == self.importe:\n",
       "            if False:\n")],
     [T + "test_r6_tres_casos"], None),
    ("C03-M10", "writer de actor antes de validar (alta antes de categoria, contexto y terceros)",
     [(EJR, "            rechazo_cuenta(sesion, intencion.cuenta_id, \"GASTO\", intencion.fecha_hecho)\n",
       "            rechazo_cuenta(sesion, intencion.cuenta_id, \"GASTO\", intencion.fecha_hecho)\n"
       "            actores.actor_de_tercero(sesion, contraparte, motivo=actores.MOTIVO_ALTA_REEMBOLSO)\n")],
     [T + "test_negativo_validaciones_antes_del_writer_sin_actor_huerfano"], None),
    ("C03-POL", "politica de la ruta C-03 sustituida por la del reparto (servidor)",
     [(EJR, "                        actores.validar_tercero_reembolso(sesion, tercero)\n",
       "                        actores.validar_tercero_persona(sesion, tercero)\n")],
     POSITIVOS, None),
    ("C03-SELLO", "replay: el importe recuperable deja de compararse",
     [(EJR, "                    or persistido != intencion.reembolso.importe.quantize(ESCALA)):\n", "                    ):\n")],
     [T + "test_reintento_identico_idempotente_y_con_otro_contenido_rechazado"], None),
    ("C03-RUTA", "ruta fuera del agregado: prefijo de identidad de C-03 igual al de M3",
     [(EJR, "PREFIJO = \"gapto.f05d052.c03.\"", "PREFIJO = \"gapto.f0506.m3.\"")],
     [T + "test_reutilizacion_entre_rutas_en_ambos_sentidos"],
     "la composicion C-03 SIEMPRE declara la posicion y su efecto DERECHO_COBRO, que el gasto pagado y el "
     "compartido SOLO_MIO no declaran; OP-22 exige igualdad EXACTA del agregado (F04-D050) y el replay de "
     "C-03 exige el vinculo propio: la reutilizacion se rechaza en ambos sentidos aun con el mismo prefijo. "
     "El prefijo propio es defensa adicional, no la guarda discriminante"),
    ("C03-LECT", "lectura de posiciones repetida por vinculo (sin lectura unica)",
     [(REP, "        if entidad in lecturas:\n            continue\n", "")],
     [T + "test_lectura_una_vez_por_entidad_con_vinculos_repetidos"], None),
    ("C03-POSV", "posiciones_vinculadas repite la posicion ya mostrada en una parte",
     [(REP, "        if entidad in vistas:\n            continue\n", "")],
     [T + "test_detalle_posiciones_vinculadas_separadas_sin_duplicar"], None),
    ("C03-DEV", "devolucion de un gasto con derecho de cobro admitida",
     [(EJD, "        if con_derecho_de_cobro(sesion, origen_id):\n            raise _Rechazo(GASTO_CON_DERECHO_DE_COBRO)\n", "")],
     POSTERIORES, None),
    ("C03-DEVL", "contexto de devolucion: el motivo GASTO_CON_DERECHO_DE_COBRO no se informa",
     [(EJD, "    elif con_derecho_de_cobro(sesion, origen_id):\n        motivo = GASTO_CON_DERECHO_DE_COBRO\n", "")],
     POSTERIORES, None),
    ("C03-DEVA", "bloqueo de devolucion limitado a vinculos GENERADO_POR (RV3 AFECTA_A expuesto)",
     [(EJD, "\"ON p.entidad_id = v.entidad_id WHERE v.hecho_id = %s AND p.tipo = 'DERECHO_COBRO')\"",
       "\"ON p.entidad_id = v.entidad_id WHERE v.hecho_id = %s AND p.tipo = 'DERECHO_COBRO' "
       "AND v.tipo_relacion = 'GENERADO_POR')\"")],
     AFECTA, None),
    ("C03-M1", "exclusion M1 en el servidor: OP-21P toma el primer efecto aunque haya varios",
     [(OP21P, "        estado[\"efecto\"] = estado[\"efectos\"][0] if len(estado[\"efectos\"]) == 1 else None\n",
       "        estado[\"efecto\"] = estado[\"efectos\"][0] if len(estado[\"efectos\"]) >= 1 else None\n")],
     [T + "test_exclusion_m1_en_servidor_aunque_el_efecto_gasto_ordene_primero"], None),
    ("C03-M1L", "lectura M1: «Corregir» de un hecho con posiciones y sin reparto deja de explicar POSICIONES",
     [(EDI, "        if con_posiciones(sesion, hecho_id) and _atribuciones(sesion, hecho_id) <= 1:\n"
            "            return \"POSICIONES\"\n", "")],
     POSTERIORES, None),
    ("C03-ANU", "anulacion por duplicado de un hecho con posiciones admitida (escritura)",
     [(EJA, "        if activo is not None and activo[0] and con_posiciones(sesion, hecho_id):\n", "        if False:\n")],
     POSTERIORES, None),
    ("C03-ANUL", "lectura M1: «Anular por duplicado» ofrecido con posiciones",
     [(EDI, "    if con_posiciones(sesion, hecho_id):\n        return \"POSICIONES\"\n", "")],
     POSTERIORES, None),
    ("C03-ANUA", "guarda POSICIONES limitada a vinculos GENERADO_POR (RV3 AFECTA_A expuesto)",
     [(EDI, "\"ON p.entidad_id = v.entidad_id WHERE v.hecho_id = %s)\", (hecho_id,))\n    return bool(fila and fila[0])\n\n\ndef _atribuciones",
       "\"ON p.entidad_id = v.entidad_id WHERE v.hecho_id = %s AND v.tipo_relacion = 'GENERADO_POR')\", "
       "(hecho_id,))\n    return bool(fila and fila[0])\n\n\ndef _atribuciones")],
     AFECTA, None),
    ("C03-COM", "contraparte igual al comercio admitida",
     [(DTO, "        if self.tercero_id is not None and self.reembolso.tercero_id == self.tercero_id:\n",
       "        if False:\n")],
     [T + "test_negativo_contraparte_es_el_comercio"], None),
    ("C03-COD", "codigo estable de validacion perdido (todo ENTRADA_INVALIDA)",
     [(APP, "        estable = next((e[\"type\"] for e in exc.errors() if e.get(\"type\") in eh.CODIGOS_VALIDACION), None)\n",
       "        estable = None\n")],
     [T + "test_negativo_importe_recuperable_excede_el_total", T + "test_r6_tres_casos"], None),
    ("C03-ORD1", "orden de locks: cuenta antes que INVERSIONES",
     [(EJR, "        tomar_inversiones(sesion)\n        # 3. Cuenta pagadora FNKU.\n        bloquear_cuentas(sesion, intencion.cuenta_id)\n",
       "        bloquear_cuentas(sesion, intencion.cuenta_id)\n        tomar_inversiones(sesion)\n")],
     [C + "test_c6_orden_de_locks_c03"], None),
    ("C03-ORD2", "orden de locks: terceros por UUID descendente",
     [(EJR, "            for tercero in sorted({intencion.tercero_id, contraparte} - {None}, key=str):\n",
       "            for tercero in sorted({intencion.tercero_id, contraparte} - {None}, key=str, reverse=True):\n")],
     [C + "test_c6_orden_de_locks_c03"], None),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(tests: list[str]) -> int:
    """Ejecuta los nodeids: los de tests/backend y los de tests/api (con su
    --rootdir) por separado. rc != 0 si alguno falla."""
    rc = 0
    entorno = {**os.environ, "GAPTO_C03_CONCURRENCIA": "1"}
    for grupo, extra in (("tests/backend/", []), ("tests/api/", ["--rootdir=tests/api"])):
        ids = [t for t in tests if t.startswith(grupo)]
        if ids:
            cmd = [sys.executable, "-m", "pytest", *ids, "-q", "-x", "-p", "no:cacheprovider", *extra]
            rc = rc or subprocess.run(cmd, cwd=RAIZ, capture_output=True, env=entorno).returncode
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
