# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_mant_pre_gate_atomicidad.py
# Ruta: scripts/dev/mutantes_mant_pre_gate_atomicidad.py
# Descripcion: Arnes de mutacion de MANT-PRE-GATE · atomicidad multirregistro
#   (F05 §64.3 F05-D050, AJ-04; R-CAT-RECHAZO-COMMIT). Demuestra que cada
#   prueba de fallo inyectado de test_212 discrimina: un mutante por FRONTERA
#   transaccional de comando multirregistro de F05-06 (y, si la frontera es
#   compartida, uno por cada prueba que la ejerce). El mutante envuelve la
#   operacion que la frontera entrega a UnidadDeTrabajo con un `try` que
#   convierte un ErrorMotor posterior a la primera escritura en un rechazo
#   devuelto COMO VALOR (RechazoRegistro): la UdT confirma lo ya escrito, que
#   es exactamente el riesgo R-CAT-RECHAZO-COMMIT (rechazo funcional tras la
#   primera escritura). La prueba debe ver escrituras parciales y fallar.
#   Mas un mutante de la guarda nueva de inventario cerrado (una ruta POST
#   sin clasificar).
#   Mismo motor que mutantes_f05_06_m5b.py:
#     - sustituciones de texto exacto (UNA ocurrencia) y sus discriminantes
#       (nodeids de pytest de tests/api con su rootdir);
#     - journal durable ANTES de tocar el primer byte; si al arrancar hay un
#       journal pendiente: restaura, verifica y aborta;
#     - preflight verde de todos los discriminantes antes del primer mutante;
#     - tras cada mutante se restaura y se verifica la identidad byte a byte
#       (SHA-256);
#     - el veredicto de CADA mutante se escribe a disco en cuanto se conoce
#       (--salida, append + fsync);
#     - veredicto: MUERTO | VIVO | NO_CLASIFICABLE (EQUIVALENTE si se declara).
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable>
#        python scripts/dev/mutantes_mant_pre_gate_atomicidad.py [--solo ID,ID] [--salida fichero]
#               [--detalle carpeta]   (salida de pytest de cada mutante: motivo de la muerte)
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F05-07/GATE adenda 2, MANT-PRE-GATE atomicidad multirregistro)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_mant_pre_gate_atomicidad.journal.json"

API = "backend/app/api/"
APP = API + "app.py"
EJD = API + "ejecucion_devolucion.py"
REP = API + "ejecucion_reparto.py"
EJP = API + "ejecucion_prevision.py"
EJG = API + "ejecucion_gasto_pagado.py"
EJR = API + "ejecucion_registro.py"
EJC = API + "ejecucion_correccion.py"
EJA = API + "ejecucion_anulacion.py"
EJV = API + "ejecucion_categoria_v3.py"
T212 = "tests/api/test_212_f05_07_mpg_atomicidad_multirregistro.py::"
BARRIDO = T212 + "test_rechazo_tras_cada_escritura_no_deja_escrituras_parciales"


def barrido(*comandos: str) -> list[str]:
    return [f"{BARRIDO}[{c}]" for c in comandos]


def frontera(fichero: str, original: str) -> tuple[str, str, str]:
    """Sustitucion que, justo antes de la llamada a la UnidadDeTrabajo, define
    `_mut_tragar` (ErrorMotor -> RechazoRegistro devuelto como valor) y se la
    entrega en lugar de `operacion`."""
    sangria = original[: len(original) - len(original.lstrip(" "))]
    if "(operacion" in original:
        llamada = original.replace("(operacion", "(_mut_tragar", 1)
    else:
        assert original.count(", operacion,") == 1, original
        llamada = original.replace(", operacion,", ", _mut_tragar,", 1)
    s = sangria
    definicion = (
        f"{s}def _mut_tragar(sesion, _op=operacion):\n"
        f"{s}    from app.api.ejecucion_registro import RechazoRegistro as _R\n"
        f"{s}    from app.core.errores import ErrorMotor as _E\n"
        f"{s}    try:\n"
        f"{s}        return _op(sesion)\n"
        f"{s}    except _E as _exc:\n"
        f"{s}        return _R(_exc.codigo.value)\n"
    )
    return (fichero, original, definicion + llamada)


#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    # ---------------------------------------------------------------- M2
    ("AT01", "M2 devolucion: rechazo tras escribir devuelto como valor (commit parcial)",
     [frontera(EJD, '    return unidad.ejecutar(contexto, _como_valor(operacion),\n'
                    '                           nombre="F05-06 M2 devolucion (locks + OP-13 + OP-05 [+ OP-08 + OP-09])")\n')],
     barrido("M2_devolucion_cobrada"), None),
    ("AT02", "M2 abono: rechazo tras escribir devuelto como valor",
     [frontera(EJD, '    return unidad.ejecutar(contexto, _como_valor(operacion), nombre="F05-06 M2 abono (locks + OP-08 + OP-09)")\n')],
     barrido("M2_abono"), None),
    # ---------------------------------------------------------------- M3
    # AT03/AT04: frontera compartida por varios comandos; un mutante por prueba
    # (misma transformacion) para demostrar que CADA barrido discrimina.
    ("AT03", "M3 gasto compartido: rechazo tras escribir devuelto como valor",
     [_GC := frontera(REP, '    return unidad.ejecutar(contexto, con_rechazo_capacidad(operacion, RechazoRegistro),\n'
                           '                           nombre="F05-06 M3 gasto_compartido (locks + writer de actor + OP-22)")\n')],
     barrido("M3_gasto_compartido"), None),
    ("AT03b", "M5 gasto compartido con prevision (misma frontera que AT03)",
     [_GC], barrido("M5_gasto_compartido_prevision"), None),
    ("AT04", "M3 cobro (_aplicar_reduccion): rechazo tras escribir devuelto como valor",
     [_RD := frontera(REP, '    return unidad.ejecutar(contexto, con_rechazo_capacidad(operacion, RechazoRegistro), nombre=nombre)\n')],
     barrido("M3_cobro"), None),
    ("AT04b", "M3 pago (misma frontera que AT04)", [_RD], barrido("M3_pago"), None),
    ("AT04c", "M3 perdon (misma frontera que AT04)", [_RD], barrido("M3_perdon"), None),
    ("AT05", "M3 corregir reparto: rechazo tras escribir devuelto como valor",
     [frontera(REP, '    return unidad.ejecutar(contexto, operacion, nombre="F05-06 M3 corregir_reparto (OP-21 whitelist)")\n')],
     barrido("M3_corregir_reparto"), None),
    # ---------------------------------------------------------------- M4
    ("AT06", "M4 capacidades (_comando_capacidad): rechazo tras escribir devuelto como valor",
     [frontera(APP, '        salida = unidad.ejecutar(contexto(), operacion, nombre=f"F05-06 capacidad {nombre_op}")\n')],
     barrido("M4_capacidad_activar"), None),
    # ---------------------------------------------------------------- M5
    ("AT07", "M5 vincular: rechazo tras escribir devuelto como valor",
     [frontera(EJP, '        return unidad.ejecutar(contexto, operacion, nombre="F05-06 M5 vincular (OP-17)")\n')],
     barrido("M5_vincular"), None),
    ("AT08", "M5 omitir: rechazo tras escribir devuelto como valor",
     [frontera(EJP, '    return unidad.ejecutar(contexto, operacion, nombre="F05-06 M5 omitir")\n')],
     barrido("M5_omitir"), None),
    ("AT09", "M5 transferencia prevista (OP-10 + OP-17): rechazo tras escribir devuelto como valor",
     [frontera(EJP, '    return unidad.ejecutar(contexto, con_rechazo_capacidad(operacion, RechazoRegistro),\n'
                    '                           nombre="F05-06 M5 transferencia prevista (locks + OP-10 + OP-17)")\n')],
     barrido("M5_transferencia_prevision"), None),
    ("AT10", "M5 gasto pagado con prevision (OP-22 + OP-17): rechazo tras escribir devuelto como valor",
     [frontera(EJG, '    return unidad.ejecutar(contexto, con_rechazo_capacidad(operacion, RechazoIntegracion),\n'
                    '                           nombre="VS01 gasto_pagado (lock cuenta + OP-22)")\n')],
     barrido("M5_gasto_pagado_prevision"), None),
    ("AT11", "M5 ingreso con prevision (OP-22 + OP-17): rechazo tras escribir devuelto como valor",
     [frontera(EJR, '    return unidad.ejecutar(contexto, con_rechazo_capacidad(operacion, RechazoRegistro),\n'
                    '                           nombre="F05-04 ingreso_cobrado (locks + OP-22)")\n')],
     barrido("M5_ingreso_prevision"), None),
    # ---------------------------------------------------------------- M5-B
    ("AT12", "M5-B dar por cubierta: rechazo tras escribir devuelto como valor",
     [frontera(EJP, '    return unidad.ejecutar(contexto, operacion, nombre="F05-06 M5-B dar por cubierta")\n')],
     barrido("M5B_dar_por_realizada"), None),
    ("AT13", "M5-B reabrir: rechazo tras escribir devuelto como valor",
     [frontera(EJP, '    return unidad.ejecutar(contexto, operacion, nombre="F05-06 M5-B reabrir")\n')],
     barrido("M5B_reabrir"), None),
    # ---------------------------------------------------------------- M1
    ("AT14", "M1 corregir pago (OP-21P): rechazo tras escribir devuelto como valor",
     [frontera(EJC, '    return unidad.ejecutar(contexto, con_rechazo_capacidad(operacion, RechazoRegistro),\n'
                    '                           nombre="F04-R2 OP-21P (capacidad + motor)")\n')],
     barrido("M1_corregir_pago"), None),
    ("AT15", "M1 corregir transferencia (OP-21T): rechazo tras escribir devuelto como valor",
     [frontera(EJC, '    return unidad.ejecutar(contexto, con_rechazo_capacidad(operacion, RechazoRegistro),\n'
                    '                           nombre="F04-R2 OP-21T (capacidad + motor)")\n')],
     barrido("M1_corregir_transferencia"), None),
    ("AT16", "M1 anular duplicado (OP-03P): rechazo tras escribir devuelto como valor",
     [frontera(EJA, '    return unidad.ejecutar(contexto, operacion, nombre="F04-R2 OP-03P (adaptador F05)")\n')],
     barrido("M1_anular_duplicado"), None),
    ("AT17", "M1 corregir categoria V3 (OP-21 lista blanca): rechazo tras escribir devuelto como valor",
     [frontera(EJV, '    return unidad.ejecutar(contexto, operacion, nombre="F05-06 M1 corregir_categoria_v3 (OP-21 lista blanca)")\n')],
     barrido("M1_corregir_categoria_v3"), None),
    # ---------------------------------------------------------------- guarda nueva: inventario cerrado
    ("IN01", "inventario: ruta POST nueva sin clasificar",
     [(APP, '    @app.post("/v1/afinidades", **_RAF)\n',
       '    @app.post("/v1/mutante/sin-clasificar", dependencies=[Depends(autorizar)])\n'
       '    def _mutante_sin_clasificar():\n        return {}\n\n'
       '    @app.post("/v1/afinidades", **_RAF)\n')],
     [T212 + "test_inventario_post_cerrado"], None),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(tests: list[str], detalle: pathlib.Path | None = None) -> int:
    """pytest de tests/api con su rootdir. rc != 0 si alguno falla. Con
    `detalle`, guarda la salida de pytest (motivo del fallo de cada mutante)."""
    cmd = [sys.executable, "-m", "pytest", *tests, "-q", "-x", "-p", "no:cacheprovider", "--rootdir=tests/api"]
    proc = subprocess.run(cmd, cwd=RAIZ, capture_output=True)
    if detalle is not None:
        detalle.write_bytes(proc.stdout + proc.stderr)
    return proc.returncode


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
    detalle = pathlib.Path(sys.argv[sys.argv.index("--detalle") + 1]) if "--detalle" in sys.argv else None
    if detalle is not None:
        detalle.mkdir(parents=True, exist_ok=True)
    elegidos = [mu for mu in MUTANTES if solo is None or mu[0] in solo]
    preflight = sorted({t for mu in elegidos for t in mu[3]})
    if correr(preflight) != 0:
        sys.exit("PREFLIGHT ROJO: no se muta nada.")
    anotar(salida, f"PREFLIGHT VERDE ({len(preflight)} discriminantes)")
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
            resultado = "MUERTO" if correr(tests, None if detalle is None else detalle / f"{mid}.txt") != 0 else "VIVO"
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
             ",".join(sorted({t.split("::", 1)[1] for t in tests})), nota)
        veredictos.append(v)
        anotar(salida, " | ".join(v))
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    equivalentes = sum(1 for v in veredictos if v[1] == "EQUIVALENTE")
    anotar(salida, f"RESUMEN {muertos} muertos, {equivalentes} equivalentes documentados, "
                   f"{len(veredictos) - muertos - equivalentes} otros / {len(veredictos)}")
    sys.exit(0 if muertos + equivalentes == len(veredictos) else 1)


if __name__ == "__main__":
    main()
