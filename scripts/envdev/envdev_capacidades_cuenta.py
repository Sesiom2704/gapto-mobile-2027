# ============================================================
# GAPTO MOBILE 2027
# Fichero: envdev_capacidades_cuenta.py
# Ruta: scripts/envdev/envdev_capacidades_cuenta.py
# Descripcion: Capacidades EXPLICITAS de la cuenta sintetica de ENV-DEV
#   (F05-03/F05-04 J2 §1.0; F05-D032 C1 y D-032.5). Solo contra el DSN de
#   ENV-DEV (D-196), nunca Neon ni Supabase.
#   - UNA transaccion de la UdT como gapto_runtime con el owner de ENV-DEV.
#   - Estado previo registrado: cuentas del owner con tipo, naturaleza y
#     capacidades. Esperado: EXACTAMENTE 1 cuenta; si no -> STOP (salida 3)
#     sin escribir nada (mandato §6).
#   - Capacidades objetivo = matriz de datos de capacidades_sinteticas.py
#     segun el tipo de la cuenta (CORRIENTE -> las cuatro).
#   - Idempotente: si la cuenta ya tiene exactamente las objetivo, no escribe.
#     Si tiene otras distintas -> STOP (no se corrigen datos ajenos al plan).
#   - Auditoria CREAR por fila insertada (tabla cuenta_capacidades, motivo
#     «F05-03 ENVDEV CAPACIDADES»).
#   - Escribe pre/post en --salida (sin secretos: el DSN no lleva contrasena).
#   Uso:
#     python scripts/envdev/envdev_capacidades_cuenta.py --owner <uuid> --salida <carpeta evidencia>
# Version: 0.1.0 (F05-03/F05-04 J2 §1.0)
# ============================================================

from __future__ import annotations

import argparse
import pathlib
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import comun_envdev as ce  # noqa: E402

MOTIVO = "F05-03 ENVDEV CAPACIDADES"


def estado(sesion) -> list[dict]:
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT c.id, c.nombre, c.tipo, c.naturaleza, c.moneda, c.enabled, "
            "COALESCE(array_agg(k.capacidad_codigo ORDER BY k.capacidad_codigo) "
            "FILTER (WHERE k.capacidad_codigo IS NOT NULL), '{}') "
            "FROM gapto.cuentas c LEFT JOIN gapto.cuenta_capacidades k ON k.cuenta_id = c.id "
            "WHERE c.owner_user_id = current_setting('gapto.owner_user_id')::uuid "
            "GROUP BY c.id ORDER BY c.id"
        )
        return [
            {"id": str(f[0]), "nombre": f[1], "tipo": f[2], "naturaleza": f[3], "moneda": f[4], "enabled": f[5],
             "capacidades": list(f[6])}
            for f in cur.fetchall()
        ]


def aplicar(sesion) -> dict:
    """Devuelve {resultado: APLICADO|SIN_CAMBIOS|STOP, previo, posterior, motivo?}."""
    from app.repositories import auditoria_repository as auditoria
    from capacidades_sinteticas import capacidades_de

    previo = estado(sesion)
    if len(previo) != 1:
        return {"resultado": "STOP", "motivo": f"se esperaba 1 cuenta y hay {len(previo)}", "previo": previo}
    cuenta = previo[0]
    objetivo = sorted(capacidades_de(cuenta["tipo"]))
    actuales = sorted(cuenta["capacidades"])
    if actuales == objetivo:
        return {"resultado": "SIN_CAMBIOS", "previo": previo, "posterior": previo}
    if actuales:
        return {"resultado": "STOP", "motivo": f"capacidades previas inesperadas {actuales}", "previo": previo}
    if not objetivo:
        return {"resultado": "STOP", "motivo": f"tipo {cuenta['tipo']} sin capacidades en la matriz", "previo": previo}
    cuenta_id = uuid.UUID(cuenta["id"])
    for capacidad in objetivo:
        fila = sesion.uno(
            "INSERT INTO gapto.cuenta_capacidades (cuenta_id, capacidad_codigo) VALUES (%s, %s) "
            "RETURNING id, row_to_json(cuenta_capacidades)::text",
            (cuenta_id, capacidad),
        )
        auditoria.registrar(sesion, tabla="cuenta_capacidades", registro_id=fila[0],
                            accion=auditoria.ACCION_CREAR, datos_despues_json=fila[1], motivo=MOTIVO)
    return {"resultado": "APLICADO", "previo": previo, "posterior": estado(sesion)}


def main(argv: list[str] | None = None) -> int:
    from app.core.contexto import ContextoOperacion

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=ce.DSN_ENVDEV)
    ap.add_argument("--owner", required=True, type=uuid.UUID)
    ap.add_argument("--salida", required=True, type=pathlib.Path)
    a = ap.parse_args(argv)
    ce.exigir_envdev(a.dsn)
    ctx = ContextoOperacion.de_usuario(a.owner, request_id=uuid.uuid4())
    r = ce.unidad(a.dsn).ejecutar(ctx, aplicar, nombre="ENVDEV capacidades_cuenta")
    ce.escribir_json(a.salida, "capacidades_previo.json", r["previo"])
    if "posterior" in r:
        ce.escribir_json(a.salida, "capacidades_posterior.json", r["posterior"])
    ce.escribir_json(a.salida, "capacidades_resultado.json",
                     {"resultado": r["resultado"], "motivo": r.get("motivo"), "request_id": str(ctx.request_id)})
    print(f"capacidades: {r['resultado']}" + (f" ({r['motivo']})" if r.get("motivo") else ""))
    return ce.SALIDA_STOP if r["resultado"] == "STOP" else 0


if __name__ == "__main__":
    sys.exit(main())
