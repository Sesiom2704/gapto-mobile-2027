# ============================================================
# GAPTO MOBILE 2027
# Fichero: f05_06_m2_helpers.py
# Ruta: tests/api/f05_06_m2_helpers.py
# Descripcion: Helpers de los tests de la devolucion contextual (F05-06 M2):
#   origenes por la API (gasto pagado) o por el motor (OP-22 sin pago, varios
#   efectos, atribuciones a medida), marca V3 (mapeos_importacion), cuerpos de
#   devolucion y abono, anulacion por OP-03 (no tiene ruta HTTP: M1) y
#   lecturas fisicas como gapto_runtime. Datos sinteticos; base desechable.
# Version: 0.1.0 (F05-06 M2-A §A5)
# ============================================================

from __future__ import annotations

import uuid

import f05_01_helpers as fh
import f05_05_helpers as x
import vs01_api_helpers as h

FECHA_COMPRA = "2026-08-20"
FECHA_DEVOLUCION = "2026-09-10"


def url_devoluciones(origen) -> str:
    return f"/v1/hechos/{origen}/devoluciones"


def url_abono(devolucion) -> str:
    return f"/v1/hechos/{devolucion}/abono"


def cuerpo(importe="40.00", *, atribucion="SOLO_MIO", abono=None, fecha=FECHA_DEVOLUCION, nota="Talla equivocada",
           intencion_id=None) -> dict:
    return {"intencion_id": str(intencion_id or uuid.uuid4()), "importe": importe, "moneda": "EUR",
            "fecha_hecho": fecha, "atribucion": atribucion, "nota": nota,
            "abono": abono or {"estado": "PENDIENTE"}}


def cobrado(cuenta, fecha=FECHA_DEVOLUCION) -> dict:
    return {"estado": "COBRADO", "cuenta_id": str(cuenta), "fecha": fecha}


def devolver(cli, origen, **kw):
    c = cuerpo(**kw)
    return c, cli.post(url_devoluciones(origen), json=c, headers=h.AUTH)


def abonar(cli, devolucion, cuenta, fecha="2026-09-12", intencion_id=None):
    c = {"intencion_id": str(intencion_id or uuid.uuid4()), "cuenta_id": str(cuenta), "fecha": fecha}
    return c, cli.post(url_abono(devolucion), json=c, headers=h.AUTH)


def compra(cli, cuenta, *, importe="120.00", atribucion="SOLO_MIO", categoria_id=None, concepto="Abrigo",
           fecha=FECHA_COMPRA) -> uuid.UUID:
    return x.gasto(cli, cuenta, fecha=fecha, importe=importe, atribucion=atribucion, categoria_id=categoria_id,
                   concepto=concepto)


def marcar_v3(owner, hecho_id) -> None:
    fuente, origen = uuid.uuid4(), uuid.uuid4()
    h.como_owner(owner, "INSERT INTO gapto.fuentes_importacion (id, owner_user_id, tipo_fuente, nombre_fuente) "
                        "VALUES (%s, %s, 'DB', 'V3 sintetica')", (fuente, owner))
    h.como_owner(owner, "INSERT INTO gapto.registros_origen_importacion (id, fuente_importacion_id, contenedor_origen, "
                        "clave_origen, datos_origen) VALUES (%s, %s, 'public.gastos', %s, '{}'::jsonb)",
                 (origen, fuente, str(hecho_id)))
    h.como_owner(owner, "INSERT INTO gapto.mapeos_importacion (registro_origen_id, tabla_destino, registro_destino_id, "
                        "tipo_mapping, confianza) VALUES (%s, 'hechos_financieros', %s, 'CREADO', 'ALTA')",
                 (origen, hecho_id))


def anular_op03(owner, hecho_id):
    """OP-03 real (HechosService) con la row_version vigente. Devuelve el
    resultado o el ErrorMotor (no se lanza)."""
    from app.core.contexto import ContextoOperacion
    from app.core.errores import ErrorMotor
    from app.services.hechos_service import HechosService
    from app.services.previsiones_service import impacto_correccion_ancla

    version = h.leer(owner, "SELECT row_version FROM gapto.hechos_financieros WHERE id=%s", (hecho_id,))[0][0]
    try:
        return HechosService(fh.unidad(), impacto_ancla=impacto_correccion_ancla).anular_hecho(
            ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4()), hecho_id=hecho_id,
            row_version_esperada=version, motivo_anulacion="F05-06 M2 test")
    except ErrorMotor as exc:
        return exc


def contar(owner, sql, params=()) -> int:
    return h.leer(owner, sql, params)[0][0]


def huella(owner) -> tuple:
    """Recuentos de todo lo que una devolucion o un abono podrian escribir."""
    return tuple(contar(owner, f"SELECT count(*) FROM gapto.{t}") for t in (
        "hechos_financieros", "hecho_efectos", "efecto_atribuciones", "hecho_relaciones", "movimientos_tesoreria",
        "hecho_movimientos_tesoreria", "auditoria"))
