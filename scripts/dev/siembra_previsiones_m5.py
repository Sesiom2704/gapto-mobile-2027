# ============================================================
# GAPTO MOBILE 2027
# Fichero: siembra_previsiones_m5.py
# Ruta: scripts/dev/siembra_previsiones_m5.py
# Descripcion: Siembra de previsiones de prueba de F05-06 M5 (F05 §59 F05-D044
#   decisiones 0 y 13; D-M5-14; dictamen Q12; mandato v1.0 «Siembra»).
#     - SOLO por servicio: PrevisionesService.crear_manual (previsiones),
#       app.terceros.servicio.alta (terceros) y OP-22 con
#       DatosPrevisionCompuesta (los 40 € ya cubiertos del seguro). Sin SQL de
#       negocio: el SQL de este fichero es solo de lectura (cuentas del owner).
#     - LISTA EXPLICITA de destinos permitidos (loopback y base): ENV-DEV
#       (gapto2027_dev en 5434), la base dev del E2E (gapto2027_dev en un
#       cluster desechable 5460-5469) y la de los tests de la siembra
#       (m5_siembra). Cualquier otro DSN aborta ANTES de conectar.
#     - uuid5 deterministas por owner, DIA y fixture (previsiones, pago parcial y
#       sus filas); los terceros, por owner y fixture (maestros compartidos).
#       Repetirla el mismo dia da 0 altas (los servicios son idempotentes por
#       identidad); otro dia crea un juego nuevo sin tocar el anterior.
#     - Manifiesto `siembra_m5_manifest.json` con uuid, fixture, destino SIN
#       credenciales, fecha y si fue alta o existente.
#   Fixtures (M5-RULE-01: ocurrencias concretas; nunca consumo generico):
#     luz vencida ~74 € (Iberdrola, recibo); seguro hogar 120 € con 40 €
#     cubiertos (Mapfre); alquiler 561 € futuro; Nómina -> Ahorro 500 €
#     futura (transferencia); agua con importe DESCONOCIDO (Emasesa); nómina
#     vencida 2.100 € (Empresa SL, ingreso); lavadora 450 € (compra singular).
#     Las fechas son relativas a hoy (Europe/Madrid). Las previsiones RODANTE
#     solo existen como fixtures de tests (M6 pospuesto).
#   Uso: python scripts/dev/siembra_previsiones_m5.py --dsn-env GAPTO_DATABASE_URL --owner <uuid>
#        [--manifiesto <ruta>] [--rol-runtime gapto_runtime] [--cuenta-nomina <uuid>] [--cuenta-ahorro <uuid>]
#   Sin cuentas explicitas: la primera CORRIENTE y la primera AHORRO habilitadas en EUR (por nombre).
#   El DSN se lee de la variable indicada y nunca se imprime.
# Version: 0.1.0 (F05-06 M5 §C1 / Fase 3)
# Version: 0.2.0 (MANT-M5-ARNESES, AJ-M5-CIERRE-06): siembra entre dias. Antes el
#   uuid5 dependia solo del fixture y las fechas de hoy: otro dia chocaba con la
#   prevision del dia anterior (IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION, R2 de M5
#   SWIPE). Ahora el juego de cada dia tiene su propia identidad.
# ============================================================

from __future__ import annotations

import argparse
import datetime as dt
import decimal
import json
import os
import pathlib
import sys
import uuid
from contextlib import contextmanager
from zoneinfo import ZoneInfo

import psycopg
from psycopg import conninfo

RAIZ = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "backend"))

D = decimal.Decimal
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
#: (base, puertos) permitidos; el host siempre loopback.
PERMITIDOS = {
    "gapto2027_dev": {5434} | set(range(5460, 5470)),
    "m5_siembra": set(range(5460, 5470)),
}
ESPACIO = uuid.UUID("6f0e2c1a-5d7b-4c39-9b8e-0a1f5e4d3c21")


class DestinoNoPermitido(SystemExit):
    pass


def exigir_destino(dsn: str) -> dict:
    """Valida el DSN SIN conectar: host loopback, base y puerto de la lista."""
    try:
        partes = conninfo.conninfo_to_dict(dsn)
    except psycopg.ProgrammingError as exc:
        raise DestinoNoPermitido(f"DSN ilegible: {type(exc).__name__}") from exc
    host, base = partes.get("host", ""), partes.get("dbname", "")
    puerto = int(partes.get("port") or 5432)
    if host not in LOOPBACK or base not in PERMITIDOS or puerto not in PERMITIDOS[base]:
        raise DestinoNoPermitido(f"destino no permitido: host={host or '?'} port={puerto} dbname={base or '?'}")
    return {"host": host, "port": puerto, "dbname": base}


def _id(owner: uuid.UUID, fixture: str) -> uuid.UUID:
    """Identidad sin dia: maestros compartidos entre juegos (terceros)."""
    return uuid.uuid5(ESPACIO, f"{owner}:m5:{fixture}")


def _id_dia(owner: uuid.UUID, hoy: dt.date, fixture: str) -> uuid.UUID:
    """Identidad del juego de un dia: previsiones, pago parcial y sus filas."""
    return uuid.uuid5(ESPACIO, f"{owner}:m5:{hoy.isoformat()}:{fixture}")


def fixtures(hoy: dt.date) -> list[dict]:
    d = lambda n: (hoy + dt.timedelta(days=n)).isoformat()  # noqa: E731
    return [
        {"fixture": "luz", "concepto": "Electricidad", "tipo": "GASTO", "desde": d(-9), "hasta": d(-5), "importe": "74.00",
         "tercero": "iberdrola", "cuenta": "nomina"},
        {"fixture": "seguro", "concepto": "Seguro hogar", "tipo": "GASTO", "desde": d(15), "hasta": d(20), "importe": "120.00",
         "tercero": "mapfre", "cuenta": "nomina", "cubierto": "40.00"},
        {"fixture": "alquiler", "concepto": "Alquiler", "tipo": "GASTO", "desde": d(22), "hasta": d(22), "importe": "561.00",
         "cuenta": "nomina"},
        {"fixture": "traspaso", "concepto": "Nómina → Ahorro", "tipo": "TRANSFERENCIA", "desde": d(20), "hasta": d(20),
         "importe": "500.00", "cuenta": "nomina", "destino": "ahorro"},
        {"fixture": "agua", "concepto": "Agua", "tipo": "GASTO", "desde": d(-3), "hasta": d(10), "importe": None,
         "tercero": "emasesa", "cuenta": "nomina"},
        {"fixture": "nomina", "concepto": "Nómina", "tipo": "INGRESO", "desde": d(-11), "hasta": d(-10), "importe": "2100.00",
         "tercero": "empresa", "cuenta_entrada": "nomina"},
        {"fixture": "lavadora", "concepto": "Lavadora (compra)", "tipo": "GASTO", "desde": d(28), "hasta": d(30), "importe": "450.00"},
    ]


TERCEROS = {"iberdrola": ("Iberdrola", "EMPRESA"), "mapfre": ("Mapfre", "EMPRESA"), "emasesa": ("Emasesa", "EMPRESA"),
            "empresa": ("Empresa SL", "EMPRESA")}
FLUJO = {"GASTO": "SALIDA", "INGRESO": "ENTRADA", "TRANSFERENCIA": "TRANSFERENCIA"}


def _unidad(dsn: str, rol_runtime: str | None):
    from app.core.unidad_trabajo import UnidadDeTrabajo

    @contextmanager
    def abrir():
        with psycopg.connect(dsn) as c:
            yield c

    return UnidadDeTrabajo(abrir, rol_runtime=rol_runtime)


def _cuentas(unidad, ctx) -> dict[str, uuid.UUID | None]:
    """Lectura: «nomina» = primera cuenta CORRIENTE habilitada en EUR; «ahorro» = primera AHORRO."""
    def leer(s):
        filas = s.conexion.execute(
            "SELECT id, tipo FROM gapto.cuentas WHERE enabled AND moneda = 'EUR' AND tipo IN ('CORRIENTE', 'AHORRO') "
            "ORDER BY tipo, nombre, id").fetchall()
        return {"nomina": next((f[0] for f in filas if f[1] == "CORRIENTE"), None),
                "ahorro": next((f[0] for f in filas if f[1] == "AHORRO"), None)}
    return unidad.ejecutar(ctx, leer, nombre="siembra M5 cuentas")


def sembrar(dsn: str, owner: uuid.UUID, *, rol_runtime: str | None = None, hoy: dt.date | None = None,
            cuentas: dict[str, uuid.UUID] | None = None) -> list[dict]:
    destino = exigir_destino(dsn)
    from app.core.contexto import ContextoOperacion
    from app.core.modelos_prevision import DatosPrevisionManual
    from app.services.previsiones_service import PrevisionesService
    from app.terceros import servicio as st

    hoy = hoy or dt.datetime.now(ZoneInfo("Europe/Madrid")).date()
    ctx = lambda: ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4())  # noqa: E731
    unidad = _unidad(dsn, rol_runtime)
    cuentas = {**_cuentas(unidad, ctx()), **(cuentas or {})}
    registro: list[dict] = []
    ahora = dt.datetime.now(dt.timezone.utc).isoformat()

    terceros: dict[str, uuid.UUID] = {}
    for clave, (nombre, naturaleza) in TERCEROS.items():
        tid = _id(owner, f"tercero.{clave}")
        r = unidad.ejecutar(ctx(), lambda s, t=tid, n=nombre, na=naturaleza: st.alta(s, tercero_id=t, nombre=n, naturaleza=na),
                            nombre="siembra M5 tercero")
        if not hasattr(r, "tercero"):
            raise SystemExit(f"tercero {clave}: rechazo {getattr(r, 'codigo', r)}")
        terceros[clave] = tid
        registro.append({"uuid": str(tid), "fixture": f"tercero.{clave}", "alta": not r.idempotente})

    servicio = PrevisionesService(unidad)
    for f in fixtures(hoy):
        pid = _id_dia(owner, hoy, f"prevision.{f['fixture']}")
        existia = unidad.ejecutar(ctx(), lambda s, p=pid: s.uno("SELECT 1 FROM gapto.previsiones WHERE id = %s", (p,)),
                                  nombre="siembra M5 existe") is not None
        servicio.crear_manual(ctx(), DatosPrevisionManual(
            prevision_id=pid, concepto=f["concepto"], tipo_hecho_codigo=f["tipo"],
            fecha_esperada_desde=dt.date.fromisoformat(f["desde"]), fecha_esperada_hasta=dt.date.fromisoformat(f["hasta"]),
            flujo_tesoreria_esperado=FLUJO[f["tipo"]], moneda="EUR", presupuestable=f["tipo"] != "TRANSFERENCIA",
            tercero_id=terceros.get(f.get("tercero")), cuenta_salida_esperada_id=cuentas.get(f.get("cuenta")),
            cuenta_entrada_esperada_id=cuentas.get(f.get("cuenta_entrada") or f.get("destino")),
            importe_esperado=None if f["importe"] is None else D(f["importe"])))
        registro.append({"uuid": str(pid), "fixture": f"prevision.{f['fixture']}", "alta": not existia})
        if f.get("cubierto"):
            registro.append(_cubrir(unidad, ctx, owner, pid, f, cuentas["nomina"], terceros, hoy))
    for r in registro:
        r.update({"destino": destino, "fecha": ahora})
    return registro


def _cubrir(unidad, ctx, owner, pid, f, cuenta, terceros, hoy) -> dict:
    """Pago parcial ya registrado: OP-22 con DatosPrevisionCompuesta y marcar_realizada = False."""
    from app.api.traductor_gasto_pagado import leer_actor_self
    from app.core.modelos import DatosCreacionHecho
    from app.core.modelos_compuesto import DatosHechoCompuesto, DatosPagoCompuesto, DatosPrevisionCompuesta
    from app.core.modelos_efectos import DatosAtribucion, DatosEfecto
    from app.core.modelos_tesoreria import DatosConciliacion, DatosMovimiento
    from app.core.unidad_adscrita import UnidadDeTrabajoAdscrita
    from app.services.compuesto_service import HechosCompuestosService
    from app.services.previsiones_service import impacto_correccion_ancla

    hid = _id_dia(owner, hoy, f"hecho.{f['fixture']}.cubierto")
    x = D(f["cubierto"]).quantize(D("0.0001"))
    fecha = hoy - dt.timedelta(days=2)

    def op(s):
        if s.uno("SELECT 1 FROM gapto.hechos_financieros WHERE id = %s", (hid,)) is not None:
            return False
        actor = leer_actor_self(s)
        version = s.uno("SELECT row_version FROM gapto.previsiones WHERE id = %s", (pid,))[0]
        mov = _id_dia(owner, hoy, f"mov.{f['fixture']}")
        datos = DatosHechoCompuesto(
            hecho=DatosCreacionHecho(hecho_id=hid, fecha_hecho=fecha, moneda="EUR", presupuestable=True,
                                     estado_localizacion="DESCONOCIDA", tipo_hecho_codigo="GASTO", concepto=None, importe_total=x),
            efectos=[DatosEfecto(efecto_id=_id_dia(owner, hoy, f"efecto.{f['fixture']}"), tipo_efecto="GASTO", importe_delta=x,
                                 estado_atribucion="COMPLETA",
                                 atribuciones=(DatosAtribucion(atribucion_id=_id_dia(owner, hoy, f"atr.{f['fixture']}"), actor_id=actor,
                                                               importe_atribuido=x, criterio_atribucion="MANUAL",
                                                               porcentaje_aplicado=D("100")),))],
            pagos=[DatosPagoCompuesto(
                movimiento=DatosMovimiento(movimiento_id=mov, cuenta_id=cuenta, fecha_movimiento=fecha, importe=-x,
                                           clase_movimiento="OPERACION", descripcion=None),
                conciliacion=DatosConciliacion(conciliacion_id=_id_dia(owner, hoy, f"conc.{f['fixture']}"), hecho_id=hid,
                                               movimiento_tesoreria_id=mov, importe_asignado=-x))],
            prevision=DatosPrevisionCompuesta(prevision_id=pid, prevision_row_version_esperada=version,
                                              vinculo_id=_id_dia(owner, hoy, f"vinculo.{f['fixture']}"), importe_asignado=x,
                                              marcar_realizada=False))
        HechosCompuestosService(UnidadDeTrabajoAdscrita(s), impacto_ancla=impacto_correccion_ancla).registrar_hecho_compuesto(
            s.contexto, datos)
        return True

    alta = unidad.ejecutar(ctx(), op, nombre="siembra M5 pago parcial (OP-22 + prevision)")
    return {"uuid": str(hid), "fixture": f"hecho.{f['fixture']}.cubierto", "alta": alta}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn-env", default="GAPTO_DATABASE_URL")
    ap.add_argument("--owner", required=True, type=uuid.UUID)
    ap.add_argument("--manifiesto", default="siembra_m5_manifest.json")
    ap.add_argument("--rol-runtime", default=None)
    ap.add_argument("--cuenta-nomina", type=uuid.UUID)
    ap.add_argument("--cuenta-ahorro", type=uuid.UUID)
    a = ap.parse_args()
    dsn = os.environ.get(a.dsn_env)
    if not dsn:
        raise SystemExit(f"Falta la variable {a.dsn_env}.")
    exigir_destino(dsn)  # antes de conectar
    explicitas = {k: v for k, v in (("nomina", a.cuenta_nomina), ("ahorro", a.cuenta_ahorro)) if v is not None}
    registro = sembrar(dsn, a.owner, rol_runtime=a.rol_runtime, cuentas=explicitas)
    pathlib.Path(a.manifiesto).write_text(json.dumps(registro, indent=1, ensure_ascii=False), encoding="utf-8")
    altas = sum(1 for r in registro if r["alta"])
    print(f"siembra M5: {altas} altas, {len(registro) - altas} existentes; manifiesto {a.manifiesto}")


if __name__ == "__main__":
    main()
