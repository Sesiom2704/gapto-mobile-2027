# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f04_r2c.py
# Ruta: scripts/dev/mutantes_f04_r2c.py
# Descripcion: Arnes de mutacion de F04-R2 R2-C (mandato F04-R2C v1.0 P5 y P7;
#   contrato F04-R2 v0.9 §2.3.6: «un mutante por guarda»; 100 % muertos o
#   equivalentes justificados). Mismo motor que mutantes_f05_06_m3.py (D-181,
#   D-192, D-193, WM 12C.2):
#     - sustituciones de texto exacto (UNA ocurrencia) y sus discriminantes
#       (nodeid de pytest de tests/backend);
#     - journal durable ANTES de tocar el primer byte; si al arrancar hay un
#       journal pendiente: restaura, verifica y aborta;
#     - preflight verde de todos los discriminantes antes del primer mutante;
#     - tras cada mutante se restaura y se verifica la identidad byte a byte;
#     - el veredicto de CADA mutante se escribe a disco en cuanto se conoce
#       (--salida, append + fsync): un corte no pierde los ya clasificados;
#     - veredicto: MUERTO | VIVO | NO_CLASIFICABLE (EQUIVALENTE si se declara).
#   Guardas: A-1..A-5, declaracion, request_id, motivo, cada fila de §2.5,
#   versiones (§6.3), identidad (§6.4), pertenencia de los DELETE (§7.2),
#   §2.3.6 (commit por pasos o por pata, omitir W1/W2/W3/W4 o una pata, W5 antes
#   de L6, propagacion adquirida despues de L6), orden de L y relectura L-R, y
#   el mutante de P5 (refactor: la adquisicion reintroducida tras los
#   movimientos).
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable> GAPTO_F04R2C_CONCURRENCIA=1
#        python scripts/dev/mutantes_f04_r2c.py [--solo ID,ID] [--salida fichero]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F04-R2 R2-C P5/P7)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f04_r2c.journal.json"
SVC = "backend/app/services/anulacion_tesoreria_service.py"
REPO = "backend/app/repositories/anulacion_tesoreria_repository.py"
T = "tests/backend/test_14e_f04_r2c_discriminantes.py::"
C = "tests/backend/test_14f_f04_r2c_concurrencia_serial.py"
ORDEN = T + "test_orden_de_fases_l_y_w"
ATOM = T + "test_atomicidad_fallos_inyectados"
D119 = ("fn_check_movimiento_padre (D-119) impide que un movimiento con conciliaciones quede ANULADO y A-3 "
        "exige que cada movimiento de C este conciliado solo con el hecho: no hay estado alcanzable")

#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    # ---------------------------------------------------------------- A-1
    ("A01", "A-1 sin rechazar un hecho ya ANULADO",
     [(SVC, "        if hecho[\"estado\"] != ESTADO_ACTIVO:\n            raise _estado(\"HECHO_ANULADO\"",
       "        if False:\n            raise _estado(\"HECHO_ANULADO\"")],
     [T + "test_a1_ya_anulado_y_sin_tesoreria"], None),
    ("A02", "A-1 admite tipos fuera de GASTO/INGRESO/TRANSFERENCIA",
     [(SVC, "        if hecho[\"tipo\"] not in TIPOS_ANULABLES:\n", "        if False:\n")],
     [T + "test_a1_tipo_no_anulable"], None),
    ("A03", "A-1 admite inversiones (§3.3)",
     [(SVC, "        if repo_lect.tiene_entidad_de_inversion(sesion, hecho_id):\n", "        if False:\n")],
     [T + "test_a1_inversion_fuera"], None),
    # ---------------------------------------------------------------- A-2
    ("A04", "A-2 sin rechazar dependencias entrantes activas (G-R1-A)",
     [(SVC, "        if previo[\"dependencias\"]:\n", "        if False:\n")],
     [T + "test_dependencias_activas_g_r1_a"], None),
    ("A05", "§2.3.4 un hecho sin tesoreria se anula por OP-03P (no es OP-03 ordinaria)",
     [(SVC, "        if not previo[\"conciliaciones\"]:\n", "        if False:\n")],
     [T + "test_a1_ya_anulado_y_sin_tesoreria"], None),
    # ---------------------------------------------------------------- A-4 / §2.5
    ("A06", "§2.5 fila importado: sin rechazar registros importados",
     [(SVC, "        if repo_lect.importado(sesion, destinos):\n", "        if False:\n")],
     [T + "test_origen_importado_hecho_y_movimiento"], None),
    ("A07", "§2.5 importado: solo mira el hecho (no el movimiento, §2.3.7)",
     [(SVC, "        destinos = [(repo.TABLA_HECHOS, hecho_id)] + [(repo.TABLA_MOVIMIENTOS, m[\"id\"]) for m in movimientos]\n",
       "        destinos = [(repo.TABLA_HECHOS, hecho_id)]\n")],
     [T + "test_origen_importado_hecho_y_movimiento"], None),
    ("A08", "§2.5 importado: solo mira los movimientos (no el hecho)",
     [(SVC, "        destinos = [(repo.TABLA_HECHOS, hecho_id)] + [(repo.TABLA_MOVIMIENTOS, m[\"id\"]) for m in movimientos]\n",
       "        destinos = [(repo.TABLA_MOVIMIENTOS, m[\"id\"]) for m in movimientos]\n")],
     [T + "test_origen_importado_hecho_y_movimiento"], None),
    ("A09", "§2.5 fila AJUSTE_SALDO: sin rechazar ajustes",
     [(SVC, "        if any(m[\"clase\"] == CLASE_AJUSTE for m in movimientos):\n", "        if False:\n")],
     [T + "test_ajuste_de_saldo"], None),
    # ---------------------------------------------------------------- A-3
    ("A10", "A-3 sin exigir movimientos ACTIVOS",
     [(SVC, "            if movimiento[\"estado\"] != ESTADO_ACTIVO:\n", "            if False:\n")],
     [T + "test_a1_ya_anulado_y_sin_tesoreria", T + "test_transferencia_las_dos_patas_y_su_fila"], D119),
    ("A11", "§2.5 fila movimiento compartido: sin rechazarlo",
     [(SVC, "            if repo_lect.hechos_conciliados(sesion, movimiento[\"id\"]) != [hecho_id]:\n",
       "            if False:\n")],
     [T + "test_movimiento_compartido"], None),
    ("A12", "§2.5 fila reversiones: ignora las reversiones del movimiento",
     [(SVC, "movimiento[\"reversiones\"] > 0 or movimiento[\"reversion_de\"] is not None",
       "movimiento[\"reversion_de\"] is not None")],
     [T + "test_reversion_existente"], None),
    ("A13", "§2.5 fila reversiones: ignora que el movimiento sea a su vez una reversion",
     [(SVC, "movimiento[\"reversiones\"] > 0 or movimiento[\"reversion_de\"] is not None",
       "movimiento[\"reversiones\"] > 0")],
     [T + "test_a3_movimiento_que_es_reversion"], None),
    ("A14", "A-3 / I-03P-3 una TRANSFERENCIA sin su fila o sin sus dos patas se anula",
     [(SVC, "            if (len(transferencias) != 1 or len(movimientos) != 2\n"
            "                    or {transferencias[0][1], transferencias[0][2]} != conciliados):\n",
       "            if False:\n")],
     [T + "test_a3_transferencia_sin_su_fila"], None),
    ("A15", "A-3 un gasto o ingreso conciliado con las patas de una transferencia se anula",
     [(SVC, "        elif transferencias:\n            raise _fuera(\"TIPO_NO_SOPORTADO\")",
       "        elif False:\n            raise _fuera(\"TIPO_NO_SOPORTADO\")")],
     [T + "test_a3_gasto_con_las_patas_de_una_transferencia"], None),
    # ---------------------------------------------------------------- A-5 / §2.5 cierres y ledger
    ("A16", "§2.5 fila cierres_mensuales: sin rechazar periodos cerrados",
     [(SVC, "        if repo_lect.periodo_cerrado(sesion, fechas):\n", "        if False:\n")],
     [T + "test_periodo_cerrado"], None),
    ("A17", "§2.5 cierres: solo la fecha del hecho (no la de los movimientos)",
     [(SVC, "        fechas = {hecho[\"fecha\"]} | {m[\"fecha\"] for m in movimientos}\n",
       "        fechas = {hecho[\"fecha\"]}\n")],
     [T + "test_a5_periodo_cerrado_por_la_fecha_del_movimiento"], None),
    ("A18", "§2.5 fila fecha_inicio_ledger: sin rechazar movimientos anteriores",
     [(SVC, "        if any(inicio is not None and fecha < inicio\n", "        if any(False\n")],
     [T + "test_ledger_de_la_cuenta"], None),
    ("A19", "§2.5 ledger: frontera (rechaza el propio dia de inicio)",
     [(SVC, "        if any(inicio is not None and fecha < inicio\n",
       "        if any(inicio is not None and fecha <= inicio\n")],
     [T + "test_ledger_de_la_cuenta"], None),
    # ---------------------------------------------------------------- §6.3 versiones
    ("V01", "§6.3 sin comprobar la version del hecho",
     [(SVC, "        if hecho[\"row_version\"] != datos.row_version_esperada:\n            raise _desfasada(\"El hecho\")",
       "        if False:\n            raise _desfasada(\"El hecho\")")],
     [T + "test_versiones_desfasadas"], None),
    ("V02", "§6.3 sin comprobar la version de cada movimiento",
     [(SVC, "        if dict(datos.movimientos_row_version_esperadas) != {m[\"id\"]: m[\"row_version\"] for m in movimientos}:\n",
       "        if False:\n")],
     [T + "test_versiones_desfasadas"], None),
    # ---------------------------------------------------------------- declaracion, request_id, motivo
    ("D01", "§2.3.3 la declaracion ausente (None) se toma como false",
     [(SVC, "    if datos.movimiento_en_banco is not False:\n", "    if datos.movimiento_en_banco is True:\n")],
     [T + "test_sin_declaracion_explicita_no_se_anula"], None),
    ("D02", "§2.3.3 sin exigir la declaracion",
     [(SVC, "    if datos.movimiento_en_banco is not False:\n", "    if False:\n")],
     [T + "test_sin_declaracion_explicita_no_se_anula",
      T + "test_devolucion_con_abono_y_movimiento_en_banco_true"], None),
    ("R01", "§8.1 sin exigir request_id (ninguna de las dos barreras)",
     [(SVC, "    if getattr(contexto, \"request_id\", None) is None:\n", "    if False:\n"),
      (SVC, "            _exigir_request_id_en_transaccion(sesion)\n", "")],
     [T + "test_sin_request_id_y_sin_motivo"], None),
    ("R02", "§8.1 sin la barrera de entrada del request_id",
     [(SVC, "    if getattr(contexto, \"request_id\", None) is None:\n", "    if False:\n")],
     [T + "test_sin_request_id_y_sin_motivo"],
     "la segunda barrera (_exigir_request_id_en_transaccion) rechaza con el mismo codigo y motivo "
     "REQUEST_ID_AUSENTE antes de cualquier lectura o escritura; R01 mata la ausencia de ambas"),
    ("R03", "§8.1 sin la barrera en la transaccion",
     [(SVC, "            _exigir_request_id_en_transaccion(sesion)\n", "")],
     [T + "test_sin_request_id_y_sin_motivo"],
     "la UnidadDeTrabajo fija gapto.request_id desde el contexto ya validado por _validar_entrada: "
     "defensa en profundidad no alcanzable por la entrada publica; R01 mata la ausencia de ambas"),
    ("M01", "§9 sin exigir motivo",
     [(SVC, "    if not (datos.motivo or \"\").strip():\n", "    if False:\n")],
     [T + "test_sin_request_id_y_sin_motivo"], None),
    # ---------------------------------------------------------------- §6.4 identidad
    ("I01", "§6.4 sin idempotencia (el mismo request_id vuelve a ejecutar)",
     [(SVC, "        if not auditadas:\n            return None\n", "        if True:\n            return None\n")],
     [T + "test_idempotencia_e_identidad_reutilizada"], None),
    ("I02", "§6.4 cualquier reutilizacion del request_id es idempotente",
     [(SVC, "        hechos = [a for a in auditadas if a[\"tabla\"] == repo.TABLA_HECHOS]\n",
       "        return True\n        hechos = [a for a in auditadas if a[\"tabla\"] == repo.TABLA_HECHOS]\n")],
     [T + "test_idempotencia_e_identidad_reutilizada"], None),
    ("I03", "§6.4 la identidad no mira el motivo",
     [(SVC, "            if acciones.get(fila[\"tabla\"]) != fila[\"accion\"] or fila[\"motivo\"] != motivo:\n",
       "            if acciones.get(fila[\"tabla\"]) != fila[\"accion\"]:\n")],
     [T + "test_idempotencia_e_identidad_reutilizada"], None),
    ("I04", "§6.4 la identidad no mira la version del hecho",
     [(SVC, "        if int(hechos[0][\"antes\"].get(\"row_version\", -1)) != datos.row_version_esperada:\n"
            "            return False\n",
       "        if False:\n            return False\n")],
     [T + "test_idempotencia_e_identidad_reutilizada"], None),
    ("I05", "§6.4 la identidad no mira las versiones de los movimientos",
     [(SVC, "        return movimientos == dict(datos.movimientos_row_version_esperadas)\n", "        return True\n")],
     [T + "test_idempotencia_e_identidad_reutilizada"], None),
    # ---------------------------------------------------------------- §7.2 pertenencia
    ("P01", "§7.2 DELETE de aportacion sin la pertenencia al hecho raiz",
     [(REPO, "WHERE a.id = %s::uuid AND a.hecho_id = %s::uuid ", "WHERE a.id = %s::uuid AND %s::uuid IS NOT NULL ")],
     [T + "test_gasto_pagado_con_aportacion"],
     "los ids se leen de las aportaciones DEL hecho (repo_lect.aportaciones) y L-R los relee bajo la raiz: "
     "la pertenencia en el SQL es defensa en profundidad (§7.2) no alcanzable sin otro defecto"),
    ("P02", "§7.2 DELETE de conciliacion sin la pertenencia al hecho raiz",
     [(REPO, "WHERE r.id = %s::uuid AND r.hecho_id = %s::uuid ", "WHERE r.id = %s::uuid AND %s::uuid IS NOT NULL ")],
     [T + "test_ingreso_cobrado"],
     "los ids se leen de las conciliaciones DEL hecho y L-R los relee bajo los locks: defensa en "
     "profundidad (§7.2) no alcanzable sin otro defecto"),
    ("P03", "§7.2 DELETE de transferencia sin sus dos patas exactas",
     [(REPO, "\"AND t.movimiento_salida_id = %s::uuid AND t.movimiento_entrada_id = %s::uuid \"",
       "\"AND %s::uuid IS NOT NULL AND %s::uuid IS NOT NULL \"")],
     [T + "test_transferencia_las_dos_patas_y_su_fila"],
     "la fila y sus patas se releen en L-R con las dos patas bloqueadas (L6): defensa en profundidad"),
    ("P04", "W4 sin la guarda de estado ACTIVO en el UPDATE",
     [(REPO, "WHERE m.id = %s::uuid AND m.row_version = %s AND m.estado = 'ACTIVO'",
       "WHERE m.id = %s::uuid AND m.row_version = %s")],
     [T + "test_transferencia_las_dos_patas_y_su_fila"],
     "la version leida bajo el lock (L6) y A-3 ya fijan el estado ACTIVO: defensa en profundidad; " + D119),
    # ---------------------------------------------------------------- §2.3.6 atomicidad y fases W
    ("W01", "§2.3.6 omitir W1 (aportaciones)",
     [(SVC, "            for aportacion_id in sorted(previo[\"aportaciones\"], key=str):        # W1\n",
       "            for aportacion_id in ():        # W1\n")],
     [T + "test_gasto_pagado_con_aportacion"], None),
    ("W02", "§2.3.6 omitir W2 (conciliaciones)",
     [(SVC, "for conciliacion_id, _ in sorted(previo[\"conciliaciones\"], key=lambda c: str(c[0])):  # W2\n",
       "for conciliacion_id, _ in ():  # W2\n")],
     [T + "test_ingreso_cobrado"], None),
    ("W03", "§2.3.6 omitir W3 (fila de transferencia)",
     [(SVC, "            for transferencia_id, salida, entrada in previo[\"transferencias\"]:   # W3\n",
       "            for transferencia_id, salida, entrada in ():   # W3\n")],
     [T + "test_transferencia_las_dos_patas_y_su_fila"], None),
    ("W04", "§2.3.6 omitir W4 (movimientos)",
     [(SVC, "            for movimiento in movimientos:                                       # W4 (por UUID)\n",
       "            for movimiento in ():                                       # W4 (por UUID)\n")],
     [T + "test_ingreso_cobrado"], None),
    ("W05", "§2.3.6 W4 de una sola pata",
     [(SVC, "            for movimiento in movimientos:                                       # W4 (por UUID)\n",
       "            for movimiento in movimientos[:1]:                                       # W4 (por UUID)\n")],
     [T + "test_transferencia_las_dos_patas_y_su_fila"], None),
    ("W06", "§2.3.6 commit por pasos (tras W3)",
     [(SVC, "                filas += 1\n            versiones: dict[uuid.UUID, int] = {}\n",
       "                filas += 1\n            sesion.conexion.commit()\n            versiones: dict[uuid.UUID, int] = {}\n")],
     [ATOM], None),
    ("W07", "§2.3.6 una transaccion por pata (commit tras cada W4)",
     [(SVC, "                versiones[movimiento[\"id\"]] = resultado[0]\n",
       "                versiones[movimiento[\"id\"]] = resultado[0]\n                sesion.conexion.commit()\n")],
     [ATOM], None),
    ("W08", "§2.3.6 W5 antes de L6",
     [(SVC, "            repo_lect.bloquear_movimientos(sesion, previo[\"movimientos\"])        # L6\n",
       "            repo.anular_hecho(sesion, hecho_id, repo_lect.leer_hecho(sesion, hecho_id)[\"row_version\"], motivo)\n"
       "            repo_lect.bloquear_movimientos(sesion, previo[\"movimientos\"])        # L6\n")],
     [ORDEN], None),
    ("W09", "§2.3.6 propagacion adquirida despues de L6 (L5 y L6 intercambiados)",
     [(SVC, "            plan = self._adquirir_impacto(sesion, hecho_id)                      # L5\n"
            "            repo_lect.bloquear_movimientos(sesion, previo[\"movimientos\"])        # L6\n",
       "            repo_lect.bloquear_movimientos(sesion, previo[\"movimientos\"])        # L6\n"
       "            plan = self._adquirir_impacto(sesion, hecho_id)                      # L5\n")],
     [ORDEN], None),
    ("W10", "P5 refactor: la adquisicion reintroducida tras los movimientos (W6 = adquirir + aplicar)",
     [(SVC, "            impacto = self._aplicar_impacto(sesion, plan)                        # W6\n",
       "            impacto = self._aplicar_impacto(sesion, self._adquirir_impacto(sesion, hecho_id))  # W6\n")],
     [ORDEN], None),
    ("W11", "W5 sin la guarda tiene_realidad_asociada",
     [(SVC, "            if repo_hechos.tiene_realidad_asociada(sesion, hecho_id):  # I-03P-1\n",
       "            if False:  # I-03P-1\n")],
     [T + "test_gasto_pagado_con_aportacion"],
     "W1 y W2 ya retiraron todas las aportaciones y conciliaciones releidas bajo la raiz: la guarda es "
     "defensa en profundidad de I-03P-1; W01 y W02 matan su omision"),
    # ---------------------------------------------------------------- orden de L y relectura
    ("L01", "orden de L: L5 (reglas/previsiones) antes que la raiz L3/L4",
     [(SVC, "            posiciones = integridad_posicion.adquirir_raiz(sesion, owner, hechos=[hecho_id])  # L3 + L4\n"
            "            fotos = integridad_posicion.fotografiar(sesion, posiciones, hechos=[hecho_id])\n"
            "            plan = self._adquirir_impacto(sesion, hecho_id)                      # L5\n",
       "            plan = self._adquirir_impacto(sesion, hecho_id)                      # L5\n"
       "            posiciones = integridad_posicion.adquirir_raiz(sesion, owner, hechos=[hecho_id])  # L3 + L4\n"
       "            fotos = integridad_posicion.fotografiar(sesion, posiciones, hechos=[hecho_id])\n")],
     [ORDEN], None),
    ("L02", "orden de L: sin L6 (movimientos sin lock)",
     [(SVC, "            repo_lect.bloquear_movimientos(sesion, previo[\"movimientos\"])        # L6\n", "")],
     [ORDEN], None),
    ("L03", "sin la relectura L-R (ConjuntoCambiado)",
     [(SVC, "            if conjunto(sesion, hecho_id) != previo:                             # L-R\n"
            "                raise ConjuntoCambiado()\n", "")],
     [C], None),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(tests: list[str]) -> int:
    """Ejecuta los nodeids (tests/backend). rc != 0 si alguno falla."""
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
    if os.getenv("GAPTO_F04R2C_CONCURRENCIA") != "1":
        sys.exit("Falta GAPTO_F04R2C_CONCURRENCIA=1: los discriminantes seriales se omitirian.")
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
