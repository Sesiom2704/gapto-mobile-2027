# ============================================================
# GAPTO MOBILE 2027
# Fichero: envdev_convertir_preferencias_sin_tipo.py
# Ruta: scripts/envdev/envdev_convertir_preferencias_sin_tipo.py
# Descripcion: Conversion C4 de las preferencias sin tipo de ENV-DEV
#   (F05-03/F05-04 J2 §1.0/§1.5; F05 §46.4 R6; F05-D032 C4 y D-032.5). Solo
#   contra el DSN de ENV-DEV (D-196), nunca Neon ni Supabase.
#   - UNA transaccion de la UdT como gapto_runtime con el owner de ENV-DEV:
#     lectura del estado previo y, si procede, el comando unico
#     preferencias/servicio.py::convertir_preferencias_sin_tipo (advisory
#     PREFERENCIAS, auditoria por fila). Ningun writer alternativo.
#   - Estado previo esperado: --esperadas (2) preferencias sin tipo. Con 0 la
#     conversion ya esta hecha: SIN_CAMBIOS (idempotente). Cualquier otro
#     numero -> STOP (salida 3) sin escribir nada (mandato §6).
#   - Escribe pre/post en --salida (sin secretos).
#   C4: el registro de INGRESO no se habilita en un entorno antes de que esta
#   conversion haya corrido en el.
#   Uso:
#     python scripts/envdev/envdev_convertir_preferencias_sin_tipo.py --owner <uuid> --salida <carpeta>
# Version: 0.1.0 (F05-03/F05-04 J2 §1.0)
# ============================================================

from __future__ import annotations

import argparse
import pathlib
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import comun_envdev as ce  # noqa: E402


def estado(sesion) -> list[dict]:
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT p.id, t.codigo, p.categoria_id, p.tercero_id, p.cuenta_default_id, p.presupuestable_default, "
            "p.enabled, p.row_version FROM gapto.preferencias_registro p "
            "LEFT JOIN gapto.tipos_hecho t ON t.id = p.tipo_hecho_id "
            "WHERE p.owner_user_id = current_setting('gapto.owner_user_id')::uuid ORDER BY p.id"
        )
        claves = ("id", "tipo", "categoria_id", "tercero_id", "cuenta_default_id", "presupuestable_default",
                  "enabled", "row_version")
        return [dict(zip(claves, (str(v) if isinstance(v, uuid.UUID) else v for v in f))) for f in cur.fetchall()]


def aplicar(sesion, esperadas: int = 2) -> dict:
    from app.preferencias import servicio

    previo = estado(sesion)
    sin_tipo = [p for p in previo if p["tipo"] is None]
    if not sin_tipo:
        return {"resultado": "SIN_CAMBIOS", "previo": previo, "posterior": previo}
    if len(sin_tipo) != esperadas:
        return {"resultado": "STOP", "motivo": f"se esperaban {esperadas} preferencias sin tipo y hay {len(sin_tipo)}",
                "previo": previo}
    r = servicio.convertir_preferencias_sin_tipo(sesion)
    return {"resultado": "APLICADO", "convertidas": sorted(str(x) for x in r.convertidas), "previo": previo,
            "posterior": estado(sesion)}


def main(argv: list[str] | None = None) -> int:
    from app.core.contexto import ContextoOperacion

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=ce.DSN_ENVDEV)
    ap.add_argument("--owner", required=True, type=uuid.UUID)
    ap.add_argument("--salida", required=True, type=pathlib.Path)
    ap.add_argument("--esperadas", type=int, default=2)
    a = ap.parse_args(argv)
    ce.exigir_envdev(a.dsn)
    ctx = ContextoOperacion.de_usuario(a.owner, request_id=uuid.uuid4())
    r = ce.unidad(a.dsn).ejecutar(ctx, lambda s: aplicar(s, a.esperadas), nombre="ENVDEV convertir_preferencias")
    ce.escribir_json(a.salida, "preferencias_previo.json", r["previo"])
    if "posterior" in r:
        ce.escribir_json(a.salida, "preferencias_posterior.json", r["posterior"])
    ce.escribir_json(a.salida, "preferencias_resultado.json",
                     {"resultado": r["resultado"], "motivo": r.get("motivo"), "convertidas": r.get("convertidas"),
                      "request_id": str(ctx.request_id)})
    print(f"preferencias: {r['resultado']}" + (f" ({r['motivo']})" if r.get("motivo") else ""))
    return ce.SALIDA_STOP if r["resultado"] == "STOP" else 0


if __name__ == "__main__":
    sys.exit(main())
