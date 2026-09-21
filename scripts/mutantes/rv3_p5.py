# ============================================================
# GAPTO MOBILE 2027
# Fichero: rv3_p5.py
# Ruta: scripts/mutantes/rv3_p5.py
# Descripcion: Arnes de mutacion de RV3 / P5 (transformacion V3 -> 0330).
#   Cada mutante declara su transformacion textual exacta sobre
#   scripts/migration_v3/rv3_p5_transformacion.py y su test DISCRIMINANTE.
#   Un mutante solo esta MUERTO si cae su discriminante; si solo caen tests
#   colaterales se informa DUDOSO. El arbol del repositorio NUNCA se modifica:
#   cada mutante se ejecuta sobre una copia temporal (tests/migration +
#   scripts/migration_v3), de modo que un aborto no puede dejar codigo mutado.
#   Antes de mutar se exige que la suite de la copia sin mutar este VERDE.
#   Los tests fisicos usan GAPTO_RV3_IMPORT_URL si esta definida.
#
# Uso:
#   python scripts/mutantes/rv3_p5.py            # todos
#   python scripts/mutantes/rv3_p5.py M30 M33    # subconjunto
#
# Version: 0.1.0 (M30..M40 P5 v0.6.0 respuestas S20; M41..M47 P5 v0.7.0 dominio 8B)
# ============================================================
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
OBJ = "scripts/migration_v3/rv3_p5_transformacion.py"
T9 = "tests/migration/test_rv3_009_p5_s20_decisiones.py"
T10 = "tests/migration/test_rv3_010_p5_dominio8b.py"

MUTANTES = {
    "M30": ("gate de la fuente suplementaria siempre abierto",
            [('    if ARQ_FUENTE_DECISIONES_ESTADO == "APROBADA":\n', '    if True:\n')],
            T9 + "::test_fuente_suplementaria_falla_cerrada_fuera_de_lab"),
    "M31": ("decision que contradice V3 sin corrige_v3 aceptada",
            [('and not it.get("corrige_v3"):', 'and False:')],
            T9 + "::test_decision_que_contradice_v3_exige_correccion_explicita"),
    "M32": ("reparto que no suma 100 aceptado",
            [('!= Decimal(100) or \\', '!= Decimal(100) and False or \\')],
            T9 + "::test_reparto_no_100_y_actor_desconocido_fallan"),
    "M33": ("financiador no demostrado sustituido por el proveedor V3",
            [('        if cp in FINANCIADOR_NO_DEMOSTRADO:\n', '        if False:\n')],
            T9 + "::test_financiador_no_demostrado_es_null_sin_rol"),
    "M34": ("vigencia PROPUESTA aceptada fuera de laboratorio",
            [('if PARTICIPACION_FIN_VIGENCIA_ESTADO != "CONFIRMADA" and not ds.modo_lab:', 'if False:')],
            T9 + "::test_participacion_fin_self_vigencia_propuesta_solo_en_lab"),
    "M35": ("participacion de financiacion inferida sin decision",
            [('    if (co, cl) not in PARTICIPACION_FIN_SELF:\n        ds.ledger.append({"regla": "D8-H", "origen": origen})\n        return\n', ''),
             ('desde = PARTICIPACION_FIN_SELF[(co, cl)]', 'desde = PARTICIPACION_FIN_SELF.get((co, cl))')],
            T9 + "::test_financiacion_sin_decision_no_recibe_participacion"),
    "M36": ("tipo de financiacion decidido ignorado",
            [('    if cp in TIPO_FINANCIACION_DECIDIDO:\n        return', '    if False:\n        return')],
            T9 + "::test_tipo_decidido_prevalece_y_prestamo_con_vivienda_sin_garantia"),
    "M37": ("garantia creada para financiacion no HIPOTECA",
            [('        if tipo == "HIPOTECA" and viv:\n', '        if viv:\n')],
            T9 + "::test_tipo_decidido_prevalece_y_prestamo_con_vivienda_sin_garantia"),
    "M38": ("conflicto de vigencia anterior al inicio no elevado",
            [('        if fecha_inicio and str(desde) < str(fecha_inicio):\n', '        if False:\n')],
            T9 + "::test_vigencia_anterior_al_inicio_se_eleva"),
    "M39": ("configuracion de cuentas devuelta a PROPUESTA",
            [('CONFIG_CUENTAS_ESTADO = "CONFIRMADA"', 'CONFIG_CUENTAS_ESTADO = "PROPUESTA"')],
            T9 + "::test_configuracion_confirmada_en_produccion"),
    "M40": ("persona suplementaria sin mapeo a su registro origen",
            [('        ds.mapear(CONT_DECISIONES, clave, "terceros", tid, "tercero", confianza="VALIDADA")\n', '')],
            T9 + "::test_todo_destino_tiene_mapeo_a_registro_existente"),
    "M41": ("derecho indeterminado abierto con saldo 0",
            [('"importe_original_documentado": None, "saldo_apertura": None, "fecha_inicio_seguimiento": None,',
              '"importe_original_documentado": None, "saldo_apertura": Decimal("0"), "fecha_inicio_seguimiento": FECHA_INICIO_LEDGER,')],
            T10 + "::test_indeterminada_nunca_cero"),
    "M42": ("transitoria cobrada tras el corte aceptada",
            [('or cobros[0][1] >= FECHA_INICIO_LEDGER:', ':')],
            T10 + "::test_transitoria_cobrada_tras_el_corte_falla"),
    "M43": ("canon de transitorias no comprobado",
            [('    if (trans_n, trans_total) != CANON_TRANSITORIAS:\n', '    if False:\n')],
            T10 + "::test_canon_de_transitorias"),
    "M44": ("principal de Universidad inventado desde los cobros",
            [('            sub.update(saldo_apertura=Decimal("0"), fecha_inicio_seguimiento=FECHA_INICIO_LEDGER,\n',
              '            sub.update(importe_original_documentado=CANON_UNIVERSIDAD, saldo_apertura=Decimal("0"), fecha_inicio_seguimiento=FECHA_INICIO_LEDGER,\n')],
            T10 + "::test_liquidada_sin_principal_nunca_inventa_principal"),
    "M45": ("cobros de evidencia sin mapeo",
            [('        for eo, ec in origenes[1:]:\n', '        for eo, ec in []:\n')],
            T10 + "::test_trazabilidad_y_evidencia_vinculada"),
    "M46": ("contraparte desconocida sustituida por el propietario",
            [('            ds.ledger.append({"regla": "D8B-C", "origen": f"{co}/{cl}"})\n',
              '            sub["contraparte_actor_id"] = ds.self_id\n            ds.ledger.append({"regla": "D8B-C", "origen": f"{co}/{cl}"})\n')],
            T10 + "::test_abierto_saldo_igual_a_importe_y_contraparte_desconocida_null"),
    "M47": ("transitoria con importe distinto del cobro aceptada",
            [('if co != _GC and _importe_v3(fuente, ctx, co, cl) != cobros[0][0]:', 'if False:')],
            T10 + "::test_transitoria_con_importe_distinto_falla"),
}


def _copia() -> Path:
    d = Path(tempfile.mkdtemp(prefix="rv3mut_"))
    for sub in ("scripts/migration_v3", "tests/migration"):
        shutil.copytree(RAIZ / sub, d / sub, ignore=shutil.ignore_patterns("__pycache__"))
    return d


def _pytest(d: Path, objetivo: str) -> tuple[int, str]:
    # test_rv3_000 audita el arbol real del repositorio: no aplica a la copia parcial.
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", objetivo,
                        "--ignore=tests/migration/test_rv3_000_repo_sin_datos_v3.py"],
                       cwd=d, capture_output=True, text=True)
    return r.returncode, (r.stdout.strip().splitlines() or ["(sin salida)"])[-1]


def main(sel: list[str]) -> int:
    t0 = time.time()
    base = _copia()
    rc, res = _pytest(base, "tests/migration")
    print(f"[{time.strftime('%H:%M:%S')}] linea base: {res}", flush=True)
    shutil.rmtree(base, ignore_errors=True)
    if rc != 0 or " passed" not in res:
        print("ABORTO: la suite sin mutar no esta verde")
        return 2
    vivos = 0
    for mid in (sel or list(MUTANTES)):
        desc, cambios, disc = MUTANTES[mid]
        d = _copia()
        try:
            f = d / OBJ
            src = f.read_bytes().decode("utf-8")
            for a, b in cambios:
                if src.count(a) != 1:
                    print(f"{mid}: TRANSFORMACION NO APLICABLE ({src.count(a)} coincidencias) -> DUDOSO")
                    vivos += 1
                    break
                src = src.replace(a, b)
            else:
                f.write_bytes(src.encode("utf-8"))
                rd, _ = _pytest(d, disc)
                rt, rest = _pytest(d, "tests/migration")
                if rd != 0:
                    v = "MUERTO"
                elif rt != 0:
                    v, vivos = "DUDOSO (solo colaterales)", vivos + 1
                else:
                    v, vivos = "VIVO", vivos + 1
                print(f"[{time.strftime('%H:%M:%S')}] {mid} {v:<26} {desc} | suite: {rest}", flush=True)
        finally:
            shutil.rmtree(d, ignore_errors=True)
    print(f"RESULTADO: {'OK' if vivos == 0 else 'FALLO'} vivos/dudosos={vivos} ({time.time() - t0:.1f} s)")
    return 0 if vivos == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
