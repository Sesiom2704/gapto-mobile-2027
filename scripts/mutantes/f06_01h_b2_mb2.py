#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: f06_01h_b2_mb2.py
# Ruta: scripts/mutantes/f06_01h_b2_mb2.py
# Descripcion: Arnes de mutacion del bloque MB2 de la reapertura de B2 v1.1 (F06-01H; mandato T3-F06 bloque 2
#   v1.1 §11.3, tabla pieza -> mutante -> oraculo, 1:1, 14 piezas, 0 agrupaciones; enmienda e28be7c6… de MB2-13
#   «pertenencia: Hd sin aportaciones») mas los mutantes B3/B4/B6 de la compra con hipoteca: M-H-33 (reintroduce
#   P <= precio; O-H34), M-H-23 (altera Σ pagos propios = precio; O-H27) y M-H-38 (cuentas antes que la
#   propiedad; orden de locks). Resultado SEPARADO de los 41 de scripts/mutantes/f06_01_b2.py.
#   Motor: el de scripts/dev/mutantes_f06_01h_f05_q3_hd.py (sustitucion de texto EXACTO que aparece una sola vez,
#   secuencial dentro del mutante; journal durable .mutantes_f06_01h_b2_mb2.journal.json en la raiz ANTES del
#   primer byte mutado; si hay journal previo restaura, verifica SHA-256 y aborta NO-PASS; restauracion verificada
#   por SHA-256 tras cada mutante; preflight verde; veredicto a disco con fsync en cuanto se conoce).
#   Anadido: 6.º campo opcional `repeticiones` (por defecto 1). Con n > 1 el oraculo se corre n veces con la
#   mutacion aplicada; MUERTO solo si falla en TODAS; cada pasada se anota; mezcla -> INESTABLE (no cuenta como
#   muerto). El preflight de esos oraculos tambien se repite n veces (leccion M-CV-04, AJ-T2C-C04).
#   Clasificacion del rc de pytest: 0 pasa, 1 falla (incluye ERROR de fixture), otro -> NO_CLASIFICABLE.
#   Un preflight con tests omitidos (skipped) es ROJO: un oraculo omitido no discrimina.
#   Mutaciones MB2: se elimina en `comparador.coincide` SOLO la llamada a la pieza `_pNN_*`; la pertenencia por
#   identidad (`_pertenencia`) y las otras 13 piezas se conservan (un replay exacto sigue siendo idempotente).
#   Uso: GAPTO_TEST_DATABASE_URL=postgresql://<base desechable con 0354>
#        python -u scripts/mutantes/f06_01h_b2_mb2.py [--solo ID,ID] [--salida fichero]
#   M-H-38 activa GAPTO_F06HIP_CONCURRENCIA=1 en el subproceso (bateria serial test_295, COMMIT real: base
#   desechable). No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (T3-F06 F06-01H paso 12; mandato v1.1 §11.3/§12.1)
# Version: 0.2.0 (F06 T3 · MANT N1 arneses, AJ-03 del 19-11; enmienda 01): base limpia por mutante (cada llamada a correr clona la plantilla de GAPTO_TEST_DATABASE_URL y la elimina al terminar) y clasificacion de la muerte, con scripts/dev/base_limpia_mutante.py; sin cambios en mutaciones, discriminantes ni restauracion.
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1] / 'dev'))  # MANT N1 arneses
import base_limpia_mutante  # noqa: E402  MANT N1 arneses, AJ-03 del 19-11

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f06_01h_b2_mb2.journal.json"

COMP = "backend/app/hipotecas/comparador.py"
COMPRA = "backend/app/patrimonio/compra.py"
T292 = "tests/api/test_292_f06_01h_b2_comparador_hipoteca.py::"
T289 = "tests/api/test_289_f06_01h_alta_en_compra.py::"
T295 = "tests/api/test_295_f06_01h_concurrencia_serial.py::"


def _sin_pieza(funcion: str) -> tuple[str, str, str]:
    """Elimina en `coincide` la comparacion de una pieza (llamada y su return False); el resto queda intacto."""
    return (COMP, f"    if not {funcion}(sesion, e):\n        return False\n", "")


MUTANTES = [
    ("MB2-01", "comparador sin la pieza 1 (financiacion)",
     [_sin_pieza("_p01_financiacion")], [T292 + "test_mb2_01_financiacion"], None),
    ("MB2-02", "comparador sin la pieza 2 (entidad de la financiacion)",
     [_sin_pieza("_p02_entidad")], [T292 + "test_mb2_02_entidad"], None),
    ("MB2-03", "comparador sin la pieza 3 (participaciones del prestamo)",
     [_sin_pieza("_p03_participaciones")], [T292 + "test_mb2_03_participaciones"], None),
    ("MB2-04", "comparador sin la pieza 4 (relacion GARANTIZADA_POR)",
     [_sin_pieza("_p04_garantizada_por")], [T292 + "test_mb2_04_garantizada_por"], None),
    ("MB2-05", "comparador sin la pieza 5 (version ALTA)",
     [_sin_pieza("_p05_version_alta")], [T292 + "test_mb2_05_version_alta"], None),
    ("MB2-06", "comparador sin la pieza 6 (cuotas 1..N)",
     [_sin_pieza("_p06_cuotas")], [T292 + "test_mb2_06_cuotas"], None),
    ("MB2-07", "comparador sin la pieza 7 (previsiones 1..N)",
     [_sin_pieza("_p07_previsiones")], [T292 + "test_mb2_07_previsiones"], None),
    ("MB2-08", "comparador sin la pieza 8 (Hd; alias M-H-24, no se cuenta dos veces)",
     [_sin_pieza("_p08_hd")], [T292 + "test_mb2_08_hd"], None),
    ("MB2-09", "comparador sin la pieza 9 (efecto DEUDA +P)",
     [_sin_pieza("_p09_efecto_deuda")], [T292 + "test_mb2_09_efecto_deuda"], None),
    ("MB2-10", "comparador sin la pieza 10 (vinculo AFECTA_A de nivel efecto)",
     [_sin_pieza("_p10_vinculo_nivel_efecto")], [T292 + "test_mb2_10_vinculo_nivel_efecto"], None),
    ("MB2-11", "comparador sin la pieza 11 (movimiento +P)",
     [_sin_pieza("_p11_movimiento_p")], [T292 + "test_mb2_11_movimiento_p"], None),
    ("MB2-12", "comparador sin la pieza 12 (conciliacion de Hd)",
     [_sin_pieza("_p12_conciliacion")], [T292 + "test_mb2_12_conciliacion"], None),
    ("MB2-13", "comparador sin la pieza 13 (pertenencia: Hd sin aportaciones; enmienda e28be7c6…)",
     [_sin_pieza("_p13_aportacion")], [T292 + "test_mb2_13_aportacion"], None),
    ("MB2-14", "comparador sin la pieza 14 (atribuciones del efecto DEUDA)",
     [_sin_pieza("_p14_atribucion")], [T292 + "test_mb2_14_atribucion"], None),
    ("M-H-33", "la compra con hipoteca reintroduce P <= precio (PRESTAMO_SUPERA_PRECIO retirado, B3)",
     [(COMPRA, "        return Rechazo(hip.HIPOTECA_YA_REGISTRADA)\n",
       "        return Rechazo(hip.HIPOTECA_YA_REGISTRADA)\n"
       "    if plan_hip is not None and plan_hip.p > Decimal(canon[\"precio\"]):\n"
       "        return Rechazo(ENTRADA_INVALIDA)\n")],
     [T289 + "test_o_h34_prestamo_mayor_que_el_precio_es_valido"], None),
    ("M-H-23", "la compra vuelve a aceptar «pagos propios + prestamo = precio» (B4, C-COMPRA-01)",
     [(COMPRA, "    if sum((Decimal(p[\"importe\"]) for p in canon[\"pagos_propios\"]), Decimal(0)) "
               "!= Decimal(canon[\"precio\"]):\n",
       "    if sum((Decimal(p[\"importe\"]) for p in canon[\"pagos_propios\"]), Decimal(0)) "
       "!= Decimal(canon[\"precio\"]) - (\n"
       "            Decimal(0) if plan_hip is None else plan_hip.p):\n")],
     [T289 + "test_o_h27_pagos_propios_que_no_suman_el_precio"], None),
    ("M-H-38", "orden de locks del alta: cuentas (pagos, desembolso y cargo) ANTES que la propiedad (B6, R1)",
     [(COMPRA, "    tomar_inversiones(sesion)\n    raiz = repo.bloquear(sesion, propiedad_id)\n    if raiz is None:\n"
               "        return Rechazo(NO_ENCONTRADA)\n    hoy = hoy_owner(sesion, reloj)\n"
               "    vinculo_h0 = uuid.uuid5(h0, \"gapto.f06.compra.afecta_a:\" + s)\n",
       "    tomar_inversiones(sesion)\n"
       "    _bloquear_cuentas(sesion, {uuid.UUID(x[\"cuenta_id\"]) for x in [*canon[\"pagos_propios\"], *canon[\"gastos\"]]}\n"
       "                      | (set() if plan_hip is None else {plan_hip.cuenta_desembolso, plan_hip.cuenta_cargo}))\n"
       "    raiz = repo.bloquear(sesion, propiedad_id)\n    if raiz is None:\n"
       "        return Rechazo(NO_ENCONTRADA)\n    hoy = hoy_owner(sesion, reloj)\n"
       "    vinculo_h0 = uuid.uuid5(h0, \"gapto.f06.compra.afecta_a:\" + s)\n")],
     [T289 + "test_o_h_orden_locks_alta_inversiones_propiedad_cuentas",
      T295 + "test_ic09_compra_con_hipoteca_frente_a_gasto_op22_en_la_cuenta_de_desembolso",
      T295 + "test_ic10_compra_con_hipoteca_frente_a_pago_de_otra_hipoteca_misma_cuenta",
      T295 + "test_ic14_retirada_de_recibir_ingreso_frente_a_alta_con_hipoteca"], None, 3),
]


def repeticiones(mu: tuple) -> int:
    return mu[5] if len(mu) > 5 else 1


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@base_limpia_mutante.por_llamada
def correr(tests: list[str]) -> tuple[str, str]:
    """pytest de tests/api con su rootdir. Devuelve ('pasa' | 'falla' | 'rc=<n>', salida)."""
    entorno = dict(os.environ)
    if any(t.startswith(T295) for t in tests):
        entorno["GAPTO_F06HIP_CONCURRENCIA"] = "1"
    cmd = [sys.executable, "-m", "pytest", *tests, "-q", "-x", "-rfEs", "-p", "no:cacheprovider", "--rootdir=tests/api"]
    r = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace", env=entorno)
    salida = r.stdout + r.stderr
    return ({0: "pasa", 1: "falla"}.get(r.returncode, f"rc={r.returncode}"), salida)


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


def volcar(salida: pathlib.Path | None, cabecera: str, texto: str) -> None:
    """Salida de pytest de cada pasada en <salida>.pytest.log (evidencia; la terminal no lo es)."""
    if salida is None:
        return
    with salida.with_name(salida.name + ".pytest.log").open("a", encoding="utf-8") as f:
        f.write(f"===== {cabecera}\n{texto}\n")
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
    if solo is not None and len(elegidos) != len(solo):
        sys.exit(f"--solo con IDs desconocidos: {sorted(solo - {mu[0] for mu in elegidos})}")
    # preflight: cada oraculo tantas veces como el maximo de repeticiones de los mutantes que lo citan
    veces: dict[str, int] = {}
    for mu in elegidos:
        for t in mu[3]:
            veces[t] = max(veces.get(t, 1), repeticiones(mu))
    for k in range(1, max(veces.values(), default=1) + 1):
        grupo = sorted(t for t, v in veces.items() if v >= k)       # pasada 1: todos; despues, los repetidos
        estado, texto = correr(grupo)
        volcar(salida, f"PREFLIGHT pasada {k}", texto)
        if estado != "pasa" or " skipped" in texto:
            anotar(salida, f"PREFLIGHT ROJO (pasada {k}: {estado}"
                           f"{', con omitidos' if ' skipped' in texto else ''}): no se muta nada.")
            sys.exit(1)
        anotar(salida, f"PREFLIGHT pasada {k}: verde ({len(grupo)} oraculos)")
    anotar(salida, f"PREFLIGHT VERDE ({len(veces)} oraculos)")
    veredictos = []
    for mu in elegidos:
        mid, desc, cambios, tests, equivalencia = mu[:5]
        n = repeticiones(mu)
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
        pasadas: list[str] = []
        try:
            for f in ficheros:
                (RAIZ / f).write_bytes(textos[f].encode("utf-8"))
            for k in range(1, n + 1):
                estado, texto = correr(tests)
                pasadas.append(estado)
                volcar(salida, f"{mid} pasada {k}/{n}", texto)
                anotar(salida, f"  {mid} pasada {k}/{n}: {estado}")
            if all(p == "falla" for p in pasadas):
                resultado = "MUERTO"
            elif all(p == "pasa" for p in pasadas):
                resultado = "VIVO"
            elif all(p in ("pasa", "falla") for p in pasadas):
                resultado = "INESTABLE"
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
             ",".join(sorted({pathlib.Path(t.split("::")[0]).name for t in tests})),
             f"x{n} [{' '.join(pasadas)}]", nota)
        veredictos.append(v)
        anotar(salida, " | ".join(v))
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    equivalentes = sum(1 for v in veredictos if v[1] == "EQUIVALENTE")
    anotar(salida, f"RESUMEN {muertos} muertos, {equivalentes} equivalentes documentados, "
                   f"{len(veredictos) - muertos - equivalentes} otros / {len(veredictos)}")
    sys.exit(0 if muertos + equivalentes == len(veredictos) else 1)


if __name__ == "__main__":
    main()
