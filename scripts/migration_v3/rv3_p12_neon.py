#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: rv3_p12_neon.py
# Ruta: scripts/migration_v3/rv3_p12_neon.py
# Descripcion: RV3 / P12. Ejecuta en un laboratorio PostgreSQL remoto (Neon) el MISMO pipeline autorizado
#              (Python + psycopg + P5/P6/P7/P8/P9) sobre un corpus SINTETICO determinista, sin PII V3 real y sin
#              bifurcacion semantica por proveedor: solo cambia la conexion. Secuencia: preflight local (hashes
#              certificados, P5 v0.36.0, 0001..0330, sin 0340) -> laboratorio virgen -> migraciones desde cero ->
#              D-111 pre -> corpus determinista (hash x2) -> carga con COMMIT real -> persistencia en conexion
#              nueva -> D-111 post e integridad (P7) -> reconciliacion material (P8) -> sondas runtime y
#              R-RV3-016 A/B (P9) -> replay terminal y replay en conflicto (P6). Escribe evidencia JSON sin
#              secretos ni PII. Fail-closed: cualquier comprobacion en FAIL deja el veredicto global en FAIL.
#              La credencial se toma de la variable de entorno GAPTO_P12_DSN y nunca se imprime ni se guarda.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
MV3 = RAIZ / "scripts" / "migration_v3"
HASHES_CERTIFICADOS = {
    "scripts/migration_v3/rv3_p5_transformacion.py": "0299505e330654c0c8a2e1006007fcb420c44f6ea2a63a26f42ad273405b1902",
    "scripts/migration_v3/rv3_s1_suplementario.py": "fc447972d4fbcdeaf8c1f29e3375cbd79b1a3da8274626ca77dd2600da03bd0b",
    "scripts/mutantes/rv3_p5.py": "3fa1fc7c02fa66073b32a85843831f7d722d7783142e388e1fa53642a1f54196",
    "tests/migration/test_rv3_032_p5_b0_s1_decisiones.py": "a1dda23d3ad565a22791574b55077a4a736c491f6d95ca099cd0ea2e0a8621ca",
    "tests/migration/test_rv3_033_s1_suplementario.py": "b960b4f9097afc1f6f3cf9c586d48ea71554b8a8ccaf7bae03b18ab3e4bb0c87",
}
P5_VERSION_ESPERADA = "0.36.0"
SHA_SINTETICO = "0" * 64
N = "141"
CB, MV, G, GC, I, CC, CP, PC = ("public.cuentas_bancarias", "public.movimientos_cuenta", "public.gastos",
                                "public.gastos_cotidianos", "public.ingresos", "public.contratos",
                                "public.contratos_participantes", "public.patrimonio_compra")


def _mod(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = m
    spec.loader.exec_module(m)
    return m


def redactar(texto: str) -> str:
    """Nunca deben salir credenciales: se borra cualquier user:password@ y cualquier password=..."""
    t = re.sub(r"://[^/@\s]+@", "://REDACTADO@", str(texto))
    return re.sub(r"(?i)password\s*=\s*\S+", "password=REDACTADO", t)


def host_de(dsn: str) -> str:
    m = re.search(r"@([^/:?\s]+)", dsn) or re.search(r"host=([^\s]+)", dsn)
    return m.group(1) if m else "desconocido"


# ------------------------------------------------------------------ corpus sintetico (sin PII)
def corpus(T8, T12) -> list:
    """Corpus adversarial minimo: cuentas y movimientos, contrato con cotitulares sin principal, avalista y
    gestor, contrato recreado con cambio de renta, regla recurrente versionada, gasto, ingreso, reembolso que
    reduce un derecho de cobro con contraparte, transferencia propia y devolucion."""
    c2 = (CB, "C2", {"id": "C2", "anagrama": "CTA DOS", "banco_id": "PA", "liquidez": "5.00",
                     "liquidez_inicial": "0.00", "participacion_pct": "100.00", "activo": True})

    def g(k, **kw):
        d = {"id": k, "nombre": f"GASTO {k}", "tipo_id": "TX", "prestamo_id": N, "periodicidad": "PAGO UNICO",
             "cuotas": 1, "fecha": "2026-03-10", "createon": "2026-03-10T10:00:00", "rango_pago": N, "importe": 40,
             "total": 40, "cuenta_id": "C1", "proveedor_id": N, "activo": False, "inactivatedon": N,
             "comentarios": N, "ultimo_pago_on": "2026-03-10T10:00:00", "referencia_vivienda_id": N}
        d.update(kw)
        return (G, k, d)

    def i(k, **kw):
        d = {"id": k, "concepto": f"INGRESO {k}", "tipo_id": "TX", "periodicidad": "PAGO UNICO",
             "fecha_inicio": "2026-04-02", "createon": "2026-04-02T10:00:00", "rango_cobro": N, "importe": 40,
             "cuenta_id": "C1", "activo": False, "inactivatedon": N, "ultimo_ingreso_on": "2026-04-02T10:00:00",
             "contrato_alquiler": N, "referencia_vivienda_id": N}
        d.update(kw)
        return (I, k, d)

    def ren(k, **kw):
        d = {"id": k, "concepto": f"RENTA {k}", "tipo_id": "TX", "periodicidad": "MENSUAL",
             "fecha_inicio": "2024-09-01", "createon": "2024-09-01T10:00:00", "rango_cobro": "1-3", "importe": 550,
             "cuenta_id": "C1", "activo": True, "inactivatedon": N, "ultimo_ingreso_on": N,
             "contrato_alquiler": "K1", "referencia_vivienda_id": N}
        d.update(kw)
        return (I, k, d)

    def mov(k, **kw):
        d = {"id": k, "comentarios": "Nota", "createdon": "2026-02-01T10:00:00+00:00", "cuenta_origen_id": "C1",
             "cuenta_destino_id": "C2", "fecha": "2026-02-01", "importe": "50.00", "modifiedon": N,
             "saldo_origen_antes": "100.00", "saldo_origen_despues": "50.00", "saldo_destino_antes": "10.00",
             "saldo_destino_despues": "60.00", "user_id": 2}
        d.update(kw)
        return (MV, k, d)

    con = {"renta_mensual": "550.00", "fianza": "550.00", "estado": "cancelado",
           "inactivatedon": "2026-09-01T17:03:39+00:00"}
    k2 = {"id": "K2", "patrimonio_id": "V1", "estado": "activo", "objeto_alquiler": "completa",
          "fecha_inicio": "2026-09-01", "fecha_fin": "2027-09-01", "incremento_ipc": True, "observaciones": N,
          "renta_mensual": "561.00", "fianza": "550.00", "createon": "2026-09-01T17:04:16+00:00",
          "inactivatedon": None}
    extra = [
        c2,
        ("public.personas", "PF", {"id": "PF", "nombre_completo": "Cotitular", "email": "f@example.invalid"}),
        (CP, "P5", {"id": "P5", "contrato_id": "K1", "persona_id": "PF", "rol": "inquilino", "es_principal": False,
                    "inactivatedon": N}),
        (CC, "K2", k2),
        (CP, "P6", {"id": "P6", "contrato_id": "K2", "persona_id": "PI", "rol": "inquilino", "es_principal": False,
                    "inactivatedon": None}),
        (CP, "P7", {"id": "P7", "contrato_id": "K2", "persona_id": "PF", "rol": "inquilino", "es_principal": False,
                    "inactivatedon": None}),
        ren("IR", activo=False, inactivatedon="2026-09-01T17:03:40"),
        ren("IR2", contrato_alquiler="K2", importe=561, fecha_inicio="2026-09-01", createon="2026-09-01T17:05:00"),
        g("GA", importe=40, total=40),                                   # gasto ordinario
        g("GLUZ", nombre="SUMINISTRO REPERCUTIDO", importe=88.44, total=88.44, fecha="2026-03-01",
          createon="2026-03-01T09:00:00", ultimo_pago_on="2026-03-01T09:00:00", referencia_vivienda_id="V1"),
        i("IREE", tipo_id="TR", concepto="REEMBOLSO SUMINISTRO", importe=88.44, fecha_inicio="2026-03-05",
          createon="2026-03-05T09:00:00", ultimo_ingreso_on="2026-03-05T09:00:00"),
        g("GTRA", tipo_id="TT", nombre="TRASPASO PROPIO", importe=25, total=25),   # transferencia propia
        mov("M1"),                                                        # movimiento de tesoreria (transferencia)
        mov("M2", cuenta_destino_id="C1", importe="7.00", saldo_origen_antes="50.00", saldo_origen_despues="57.00",
            saldo_destino_antes="50.00", saldo_destino_despues="57.00", comentarios="Ajuste manual de liquidez",
            fecha="2026-02-05"),
    ]
    return T12._filas(con=con, extra=tuple(extra))


def configurar(P5, conftest) -> None:
    """Misma configuracion que usan los corpus sinteticos del repositorio (catalogos anclados a claves V3 reales
    aislados). No cambia la semantica: solo evita que catalogos de datos reales fallen sobre un corpus sintetico."""
    for nombre, vacio in conftest.CATALOGOS.items():
        if hasattr(P5, nombre):
            setattr(P5, nombre, vacio)
    for k, v in (("CONFIG_CUENTAS", {(CB, "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR"),
                                     (CB, "C2"): ("AHORRO", "ACTIVO", True, True, False, "EUR")}),
                 ("CUENTAS_DERIVADAS", {}), ("CONDICIONES_DECIDIDAS", {}), ("PARTICIPACION_FIN_SELF", {(G, "G1"): None}),  # compra del corpus base: 100 % propia
                 ("FECHA_INICIO_CONTRATO_VALIDADA", {}), ("PARTICIPANTE_DUPLICADO_CAPTURA", {}),
                 ("SERVICIOS_REPERCUTIDOS", {}), ("ISA_TIPO_HECHO_DECIDIDO", None), ("CUENTA_AHORRO", (CB, "C2")),
                 ("DOMINIO_5_ACTIVO", True), ("DOMINIO_6_ACTIVO", True), ("DOMINIO_7_ACTIVO", True),
                 ("DOMINIO_11_ACTIVO", False), ("DOMINIO_12_R02_ACTIVO", False),
                 ("DOMINIO_12_R02_COMPLEMENTOS_ACTIVO", False), ("DOMINIO_12_DISPOSICION_ACTIVO", True),
                 ("FIANZA_CONTRAPARTE_DECIDIDA", {"K1": ("public.personas", "PF")}),
                 ("CONTRATO_RECREADO_V3", {"K2": {"original": "K1", "ingreso_original": "IR",
                                                  "ingreso_recreado": "IR2"}}),
                 ("CLASIFICACION_REGISTRO_S1", {}), ("DERECHOS_S1", []),
                 ("CONTRAPARTE_V3_DECIDIDA", {"D-REE": ("public.personas", "PF")}),
                 ("ATRIBUCION_CONTRAPARTE_100", {"D-REE"}),
                 ("DERECHOS_V3", [{"id": "D-REE", "genera": (G, "GLUZ"), "evidencia": [(I, "IREE")],
                                   "modo": "TRANSITORIA"}]),
                 ("CANON_TRANSITORIAS", (1, Decimal("88.44"))),
                 ("TRANSFERENCIA_LEGACY_DECIDIDA", {(G, "GTRA")})):
        setattr(P5, k, v)
    P5.CATEGORIA_POR_TIPO_V3 = {**P5.CATEGORIA_POR_TIPO_V3, "TX": "SIN_CATEGORIA_TEST",
                                "TT": "FUERA: transferencia entre cuentas propias",
                                "TR": "FUERA: reembolso de suministros (reduce derecho)"}
    real = P5.clasificar
    P5.clasificar = lambda ds, co, cl, f: ("NULL", None) if f.get("tipo_id") in ("TX", "TF") else real(ds, co, cl, f)


# ------------------------------------------------------------------ pasos
def preflight_local(ensayo: bool = False) -> dict:
    def git(*a):
        return subprocess.run(["git", *a], cwd=RAIZ, capture_output=True, text=True).stdout.strip()
    hashes, fallos = {}, []
    for rel, esperado in HASHES_CERTIFICADOS.items():
        obtenido = hashlib.sha256((RAIZ / rel).read_bytes()).hexdigest()
        hashes[rel] = obtenido
        if obtenido != esperado:
            fallos.append(rel)
    migs = sorted(p.name for p in (RAIZ / "migrations").glob("*.sql"))
    P5 = _mod("rv3_p5_transformacion", MV3 / "rv3_p5_transformacion.py")
    r = {"git_head": git("rev-parse", "HEAD"), "git_origin_main": git("rev-parse", "origin/main"),
         "working_tree_limpio": git("status", "--porcelain") == "", "hashes": hashes,
         "hashes_incorrectos": fallos, "p5_version": P5.VERSION, "migrations": len(migs),
         "primera_migration": migs[0] if migs else None, "ultima_migration": migs[-1] if migs else None,
         "existe_0340": any(m.startswith("0340") for m in migs),
         "python": sys.version.split()[0]}
    try:
        import psycopg
        r["psycopg"] = psycopg.__version__
    except Exception as e:  # noqa: BLE001
        r["psycopg"] = None
        r["psycopg_error"] = type(e).__name__
    r["ensayo_local"] = ensayo  # ensayo: solo relaja la exigencia de arbol limpio (tooling aun sin publicar)
    r["veredicto"] = "PASS" if (not fallos and r["p5_version"] == P5_VERSION_ESPERADA and not r["existe_0340"]
                                and r["migrations"] == 41 and r["psycopg"] and r["git_head"] == r["git_origin_main"]
                                and (r["working_tree_limpio"] or ensayo)) else "FAIL"
    return r


def laboratorio(psycopg, dsn: str) -> dict:
    with psycopg.connect(dsn, autocommit=True) as c:
        version = c.execute("SELECT version()").fetchone()[0]
        virgen = c.execute("SELECT count(*) FROM pg_namespace WHERE nspname = 'gapto'").fetchone()[0] == 0
        roles = c.execute("SELECT count(*) FROM pg_roles WHERE rolname LIKE 'gapto\\_%'").fetchone()[0]
        usuario = c.execute("SELECT current_user, current_database()").fetchone()
    return {"postgresql": version.split(" on ")[0], "host": host_de(dsn), "esquema_gapto_ausente": virgen,
            "roles_gapto_previos": roles, "rol_sesion": usuario[0], "base": usuario[1],
            "veredicto": "PASS" if virgen and roles == 0 else "FAIL"}


def migrar(psycopg, dsn: str) -> dict:
    ficheros = sorted((RAIZ / "migrations").glob("*.sql"))
    aplicadas = []
    with psycopg.connect(dsn, autocommit=True) as c:
        for f in ficheros:
            c.execute(f.read_text(encoding="utf-8"))
            aplicadas.append(f.name)
        # el rol de la sesion (propietario del proveedor) asume los roles contractuales: adaptacion de conexion
        for rol in ("gapto_migrator", "gapto_owner", "gapto_runtime"):
            c.execute(f'GRANT {rol} TO CURRENT_USER WITH INHERIT FALSE, SET TRUE')
    return {"aplicadas": len(aplicadas), "head": aplicadas[-1][:4] if aplicadas else None,
            "veredicto": "PASS" if len(aplicadas) == 41 else "FAIL"}


def huellas(psycopg, dsn: str, P7) -> dict:
    with psycopg.connect(dsn) as c:
        c.execute("SET TRANSACTION READ ONLY")
        h = P7.huellas(c)
        c.rollback()
    ref = P7.huellas_referencia("0330")
    dif = P7.comparar_huellas(h, ref)
    return {"obtenidas": h, "diferencias": dif, "veredicto": "PASS" if not dif else "FAIL"}


def construir_corpus(P5, conftest, T8, T12) -> tuple:
    configurar(P5, conftest)
    filas = corpus(T8, T12)
    ds1 = P5.transformar(T8._b0(filas), SHA_SINTETICO, modo_lab=True)
    ds2 = P5.transformar(T8._b0(filas), SHA_SINTETICO, modo_lab=True)
    cuerpo = json.dumps([[co, k, d] for co, k, d in filas], sort_keys=True, default=str).encode("utf-8")
    ev = {"filas_origen": len(filas), "sha256_corpus": hashlib.sha256(cuerpo).hexdigest(),
          "hash_dataset": ds1.hash(), "hash_dataset_repeticion": ds2.hash(),
          "determinista": ds1.hash() == ds2.hash(), "pendientes": len(ds1.pendientes),
          "recuentos": {t: n for t, n in ds1.recuentos().items() if n}}
    ev["veredicto"] = "PASS" if ev["determinista"] and not ds1.pendientes else "FAIL"
    return ds1, ev


def cargar(P5, P6, ds, dsn: str, psycopg) -> dict:
    ev = P6.ejecutar(P5, ds, dsn, True)
    with psycopg.connect(dsn) as c:  # persistencia observada desde una conexion nueva
        P6._contexto(c, ds.owner)
        persiste = {t: c.execute(f"SELECT count(*) FROM gapto.{t}").fetchone()[0]
                    for t in ("hechos_financieros", "mapeos_importacion", "registros_origen_importacion")}
        c.rollback()
    ev = {k: v for k, v in ev.items() if k not in ("perfil",)}
    ev["persistencia_conexion_nueva"] = persiste
    ev["veredicto"] = "PASS" if ev.get("commit") == "COMMIT" and ev.get("txid_confirmado") == "committed" \
        and persiste["hechos_financieros"] == len(ds.filas["hechos_financieros"]) else "FAIL"
    return ev


def reconciliar(P5, P8M, ds, dsn: str, psycopg) -> dict:
    with psycopg.connect(dsn) as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        material = P8M.leer_material(P5, c)
        c.rollback()
    q = {}
    dif = P8M.comparar_celdas(P5, material, ds, q)
    return {"filas_materiales": sum(len(v) for v in material.values()), "diferencias": dif,
            "cuantizacion_fisica": q, "veredicto": "PASS" if not dif else "FAIL"}


def replay(P5, P6, ds, dsn: str) -> dict:
    ev = {}
    r = P6.ejecutar(P5, ds, dsn, True)
    ev["identico"] = {"replay": r.get("replay"), "commit": r.get("commit"), "xid_asignado": r.get("xid_asignado")}
    import copy
    alterado = copy.deepcopy(ds)
    tabla = "hechos_financieros" if alterado.filas["hechos_financieros"] else "terceros"
    clave = sorted(alterado.filas[tabla])[0]
    col = "concepto" if tabla == "hechos_financieros" else "nombre"
    alterado.filas[tabla][clave] = {**alterado.filas[tabla][clave], col: "ALTERADO P12"}
    try:
        P6.ejecutar(P5, alterado, dsn, True)
        ev["conflicto"] = {"resultado": "ACEPTADO"}
    except P6.StopP6 as e:
        ev["conflicto"] = {"resultado": "STOP", "codigo": e.codigo}
    ok = (ev["identico"]["replay"] or {}).get("resultado") == "YA_APLICADA_SIN_CAMBIOS" \
        and ev["identico"]["xid_asignado"] is None and ev["conflicto"].get("codigo") == "S7_CONFLICTO_REPLAY"
    ev["veredicto"] = "PASS" if ok else "FAIL"
    return ev


def sondas(P9, ds, dsn: str, psycopg) -> dict:
    with psycopg.connect(dsn, autocommit=True) as c:
        acl = P9.sonda_acl(c)
        rls = P9.sonda_rls(c, ds.owner)
        pos = P9._posiciones(c)
        pa = P9.probe_a(c, ds.owner, pos) if pos else {"posiciones": 0, "resultado": "SIN_POSICIONES"}
        pb = P9.probe_b(c, ds.owner, pos, P9._p5b()) if pos else {"posiciones": 0}
        recuentos = P9.recuentos(c)
    for d in pa.get("detalle", []):
        d.pop("mensaje", None)
    for d in pb.get("detalle", []):
        d.pop("mensaje", None)
    r16 = {"probe_A": {k: v for k, v in pa.items() if k != "detalle"},
           "probe_B": {k: v for k, v in pb.items() if k != "detalle"},
           "detalle_A": pa.get("detalle", []), "detalle_B": pb.get("detalle", []),
           "clasificacion": ("PROTEGIDA_FRENTE_A_DELETE_DIRECTO; EVASION_UPDATE_DELETE_MATERIAL_CONFIRMADA"
                             if pb.get("evadidas") else "PROTEGIDA_FRENTE_A_DELETE_DIRECTO; "
                             "EVASION_UPDATE_DELETE_NO_ALCANZABLE")}
    ok = acl["resultado"] == "PASS" and rls["resultado"] == "PASS" and pa.get("resultado") == "PASS"
    return {"acl": acl, "rls": rls, "R_RV3_016": r16, "recuentos_tras_sondas": recuentos,
            "veredicto": "PASS" if ok else "FAIL"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="RV3 P12: mismo pipeline contra PostgreSQL remoto (Neon)")
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--etiqueta-laboratorio", default="neon-p12", help="identificador NO sensible del laboratorio")
    ap.add_argument("--ensayo", action="store_true", help="ensayo local previo a publicar el runner")
    a = ap.parse_args(argv)
    a.salida.mkdir(parents=True, exist_ok=True)
    dsn = os.environ.get("GAPTO_P12_DSN", "")
    ev = {"inicio_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(), "laboratorio": a.etiqueta_laboratorio}
    try:
        if not dsn:
            raise RuntimeError("falta la variable de entorno GAPTO_P12_DSN")
        ev["preflight"] = preflight_local(a.ensayo)
        if ev["preflight"]["veredicto"] != "PASS":
            raise RuntimeError("preflight local en FAIL: no se toca el proveedor")
        import psycopg
        P5 = sys.modules["rv3_p5_transformacion"]
        P6 = _mod("rv3_p6_carga", MV3 / "rv3_p6_carga.py")
        P7 = _mod("rv3_p7_integridad", MV3 / "rv3_p7_integridad.py")
        P8M = _mod("rv3_p8_material", MV3 / "rv3_p8_material.py")
        P9 = _mod("rv3_p9_runtime", MV3 / "rv3_p9_runtime.py")
        conftest = _mod("conftest_rv3", RAIZ / "tests" / "migration" / "conftest.py")
        T12 = _mod("t12_p12", RAIZ / "tests" / "migration" / "test_rv3_012_p5_dominio10.py")
        T8 = T12.T8
        ev["laboratorio_estado"] = laboratorio(psycopg, dsn)
        if ev["laboratorio_estado"]["veredicto"] != "PASS":
            raise RuntimeError("el laboratorio remoto no esta virgen")
        ev["migraciones"] = migrar(psycopg, dsn)
        ev["d111_pre"] = huellas(psycopg, dsn, P7)
        ds, ev["corpus"] = construir_corpus(P5, conftest, T8, T12)
        ev["carga"] = cargar(P5, P6, ds, dsn, psycopg)
        ev["integridad"] = {k: v for k, v in P7.auditar(dsn, "gapto", ev["carga"]["txid"],
                                                        {"mapeos": len(ds.filas["mapeos_importacion"]),
                                                         "hechos": len(ds.filas["hechos_financieros"]),
                                                         "registros_origen": len(ds.filas["registros_origen_importacion"])},
                                                        P7.huellas_referencia("0330")).items()
                            if k not in ("transaccion",)}
        ev["integridad"]["veredicto"] = "PASS" if ev["integridad"].get("veredicto") == "SUPERADO" else "FAIL"
        ev["d111_post"] = huellas(psycopg, dsn, P7)
        ev["reconciliacion"] = reconciliar(P5, P8M, ds, dsn, psycopg)
        ev["sondas"] = sondas(P9, ds, dsn, psycopg)
        ev["replay"] = replay(P5, P6, ds, dsn)
    except Exception as e:  # noqa: BLE001
        ev["error"] = {"tipo": type(e).__name__, "detalle": redactar(str(e))[:2000]}
    bloques = [k for k in ("preflight", "laboratorio_estado", "migraciones", "d111_pre", "corpus", "carga",
                           "integridad", "d111_post", "reconciliacion", "sondas", "replay") if k in ev]
    ev["veredictos"] = {k: ev[k].get("veredicto") for k in bloques}
    ev["veredicto_global"] = "PASS" if ("error" not in ev and len(bloques) == 11
                                        and all(v == "PASS" for v in ev["veredictos"].values())) else "FAIL"
    ev["fin_utc"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    texto = redactar(json.dumps(ev, ensure_ascii=False, indent=1, default=str))
    (a.salida / "RV3_P12_NEON_RESULT.json").write_text(texto, encoding="utf-8")
    print(json.dumps({"veredicto_global": ev["veredicto_global"], "veredictos": ev["veredictos"],
                      "error": ev.get("error")}, ensure_ascii=False, default=str))
    return 0 if ev["veredicto_global"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
