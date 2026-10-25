# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f04_r3_q4.py
# Ruta: scripts/dev/mutantes_f04_r3_q4.py
# Descripcion: Arnes de mutacion del contrato HTTP Q4/Q4-H2 de F04-R3 (F05-D051
#   paso 2; F05 §65.4: ampliacion aditiva con `apertura_indeterminada` y
#   `estado`; el reparto del hecho lee PosicionesService.saldo). Un mutante por
#   guarda nueva o modificada; resultado MUERTO o EQUIVALENTE documentado.
#   Mismo motor que mutantes_f04_r3.py (D-181, D-192, D-193, WM 12C.2):
#     - sustituciones de texto exacto (UNA ocurrencia) y sus discriminantes
#       (nodeid de pytest; los de tests/api se lanzan con --rootdir=tests/api);
#     - journal durable ANTES de tocar el primer byte; si al arrancar hay un
#       journal pendiente: restaura, verifica y aborta;
#     - preflight verde de todos los discriminantes antes del primer mutante;
#     - tras cada mutante se restaura y se verifica la identidad byte a byte;
#     - el veredicto de CADA mutante se escribe a disco en cuanto se conoce
#       (--salida, append + fsync);
#     - veredicto: MUERTO | VIVO | NO_CLASIFICABLE (EQUIVALENTE si se declara).
#   Guardas: Q1 indicador ignorado en cobro/pago/perdon (PosicionAplicada);
#   Q2 indicador ignorado en la respuesta HTTP (_posicion_http); Q3 indicador
#   del reparto ignorado; Q4 indicador del reparto calculado mal (cualquier
#   CERRADA); Q5 estado omitido en el reparto; Q6 saldo del reparto tomado del
#   neto OP-20 y no de PosicionesService.saldo; Q7 indicador de «Pendiente con»
#   distinto de false; Q8 y Q9 filtro de owner del adaptador (hecho y posicion
#   no visibles para el owner). El filtro fisico es RLS con FORCE, que no se
#   muta desde Python: Q8/Q9 mutan la guarda del adaptador que lo consume.
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable>
#        python scripts/dev/mutantes_f04_r3_q4.py [--solo ID,ID] [--salida fichero]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F05-D051 paso 2; F05 §65.4 contrato HTTP Q4/Q4-H2)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f04_r3_q4.journal.json"
REP = "backend/app/api/ejecucion_reparto.py"
APP = "backend/app/api/app.py"
T216 = "tests/api/test_216_f04_r3_q4_contrato_posiciones.py"
T199 = "tests/api/test_199_f05_06_m3_reparto.py::test_lectura_reparto_cena"
DESCONOCIDA = [T216 + "::test_derecho_apertura_desconocida_tres_estados_por_http",
               T216 + "::test_obligacion_apertura_desconocida_pago_y_cierre_por_http"]
CONOCIDA = [T216 + "::test_derecho_apertura_conocida_cerrado_por_http_es_cero_y_false",
            T216 + "::test_obligacion_apertura_conocida_pagada_por_http_es_cero_y_false"]
AISLAMIENTO = [T216 + "::test_aislamiento_por_owner"]
SALDO = '            lecturas[entidad] = {"saldo": _texto(r.saldo.importe) if r.saldo.conocido else None,\n'
LECTURA = SALDO + '                                 "estado": r.estado, "apertura_indeterminada": r.apertura_indeterminada}\n'
BUCLE = ('        for _, _, _, entidad in estado["vinculos"]:\n'
         "            r = servicio_pos.saldo(contexto, entidad)\n" + SALDO)
NETO = ('        for _, _, _c, entidad in estado["vinculos"]:\n'
        "            r = servicio_pos.saldo(contexto, entidad)\n"
        "            _seg = NetoService(UnidadDeTrabajoAdscrita(sesion)).posicion_neta(\n"
        "                contexto, contraparte_actor_id=_c).segmento(_c, MONEDA)\n"
        "            _det = [d for d in (_seg.posiciones if _seg is not None else ()) if d.entidad_id == entidad]\n"
        '            lecturas[entidad] = {"saldo": _texto(_det[0].saldo.importe) if _det and _det[0].saldo.conocido\n'
        "                                 else None,\n")
VISIBLE = ("    estado = _estado_reparto(sesion, hecho_id)\n    if estado is None:\n        return None\n"
           "    actor_self = leer_actor_self(sesion)\n")
NO_ENCONTRADA = "        if posicion is None:\n            return RechazoRegistro(POSICION_NO_ENCONTRADA)\n"

#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    ("Q1", "cobro/pago/perdon: PosicionAplicada ignora el indicador del motor (siempre false)",
     [(REP, "apertura_indeterminada=r.apertura_indeterminada)", "apertura_indeterminada=False)")],
     DESCONOCIDA, None),
    ("Q2", "respuesta HTTP de cobro/pago/perdon: el indicador no se serializa del resultado (false)",
     [(APP, '"apertura_indeterminada": salida.apertura_indeterminada,', '"apertura_indeterminada": False,')],
     DESCONOCIDA, None),
    ("Q3", "reparto del hecho: indicador ignorado (siempre false)",
     [(REP, '"apertura_indeterminada": r.apertura_indeterminada}', '"apertura_indeterminada": False}')],
     DESCONOCIDA, None),
    ("Q4", "reparto del hecho: indicador calculado mal (true en cualquier CERRADA)",
     [(REP, '"apertura_indeterminada": r.apertura_indeterminada}',
       '"apertura_indeterminada": r.estado == "CERRADA"}')],
     CONOCIDA, None),
    ("Q5", "reparto del hecho: estado omitido de la posicion",
     [(REP, LECTURA, SALDO + '                                 "apertura_indeterminada": r.apertura_indeterminada}\n')],
     CONOCIDA + [T199], None),
    ("Q6", "reparto del hecho: saldo tomado del neto OP-20 (solo ACTIVAS) y no de PosicionesService.saldo",
     [(REP, BUCLE, NETO)],
     CONOCIDA, None),
    ("Q7", "«Pendiente con»: indicador distinto de false",
     [(REP, '"apertura_indeterminada": False,  # OP-20', '"apertura_indeterminada": True,  # OP-20')],
     [T216 + "::test_derecho_apertura_conocida_cerrado_por_http_es_cero_y_false"], None),
    ("Q8", "filtro de owner: el reparto de un hecho no visible deja de responder «no encontrado»",
     [(REP, VISIBLE, "    estado = _estado_reparto(sesion, hecho_id)\n    actor_self = leer_actor_self(sesion)\n")],
     AISLAMIENTO, None),
    ("Q9", "filtro de owner: cobro/pago/perdon sobre una posicion no visible deja de rechazarse en el adaptador",
     [(REP, NO_ENCONTRADA,
       '        if posicion is None:\n            posicion = {"tipo": "DERECHO_COBRO", "row_version": 1, "origen": None}\n')],
     AISLAMIENTO, None),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(tests: list[str]) -> int:
    """Ejecuta los nodeids: los de tests/backend y los de tests/api (con su
    --rootdir) por separado. rc != 0 si alguno falla."""
    rc = 0
    for grupo, extra in (("tests/backend/", []), ("tests/api/", ["--rootdir=tests/api"])):
        ids = [t for t in tests if t.startswith(grupo)]
        if ids:
            cmd = [sys.executable, "-m", "pytest", *ids, "-q", "-x", "-p", "no:cacheprovider", *extra]
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
