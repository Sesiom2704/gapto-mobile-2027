# ============================================================
# GAPTO MOBILE 2027
# Fichero: f05_05_helpers.py
# Ruta: tests/api/f05_05_helpers.py
# Descripcion: Utilidades de los tests de F05-05 (K2 §1.2-§1.8). Los hechos
#   se registran SIEMPRE con los writers reales del adaptador
#   (/v1/intenciones/*), nunca con INSERT directos que salten guardas; solo
#   los fixtures sin writer (usuario, actor, cuentas, capacidades) se crean
#   como gapto_owner, igual que vs01_api_helpers.
#   Reloj fijo: 2026-10-10 12:00 UTC (fecha funcional 2026-10-10 en Madrid).
# Version: 0.1.0 (F05-05 K2 §1.2)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid

import f05_01_helpers as fh
import vs01_api_helpers as h

UTC = dt.timezone.utc
HOY = dt.date(2026, 10, 10)
GASTO = "/v1/intenciones/gasto-pagado"
INGRESO = "/v1/intenciones/ingreso-cobrado"
TRANSF = "/v1/intenciones/transferencia"


def reloj(iso: str = "2026-10-10T12:00:00"):
    instante = dt.datetime.fromisoformat(iso).replace(tzinfo=UTC)
    return lambda: instante


def entorno(iso: str = "2026-10-10T12:00:00"):
    """Owner nuevo con cuenta corriente y de ahorro y cliente con reloj fijo."""
    owner, actor = h.crear_tenant()
    corriente = h.crear_cuenta(owner, [(actor, 100)], tipo="CORRIENTE")
    ahorro = h.crear_cuenta(owner, [(actor, 100)], tipo="AHORRO")
    cli = h.cliente(owner, reloj=reloj(iso))
    return owner, actor, cli, corriente, ahorro


def categoria(owner, nombre: str, ambito: str = "GASTO", **kw) -> uuid.UUID:
    return fh.crear_categoria(owner, nombre, ambito, **kw)


def tercero(cli, nombre: str = "ALDI", naturaleza: str | None = "EMPRESA") -> uuid.UUID:
    tid = uuid.uuid4()
    r = cli.post("/v1/terceros", json={"id": str(tid), "nombre": nombre, "naturaleza": naturaleza}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return tid


def contexto(cli, nombre: str = "Cumpleaños Tania") -> uuid.UUID:
    cid = uuid.uuid4()
    r = cli.post("/v1/contextos", json={"id": str(cid), "nombre": nombre, "tipo_contexto": "EVENTO"}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return cid


def _cat(cid):
    return {"estado": "CATEGORIA", "categoria_id": str(cid)} if cid else {"estado": "SIN_CATEGORIA"}


def gasto(cli, cuenta, *, fecha="2026-10-05", importe="10.00", categoria_id=None, tercero_id=None,
          contexto_id=None, atribucion="SOLO_MIO", concepto=None, intencion_id=None) -> uuid.UUID:
    cuerpo = h.intencion(cuenta, fecha_hecho=str(fecha), importe=importe, atribucion=atribucion,
                         categoria=_cat(categoria_id), concepto=concepto,
                         intencion_id=str(intencion_id or uuid.uuid4()))
    if str(fecha) < "2026-01-01":  # las participaciones de los fixtures rigen desde 2026-01-01
        cuerpo["financiacion"] = h.NO_DETERMINADA
    if tercero_id:
        cuerpo["tercero_id"] = str(tercero_id)
    if contexto_id:
        cuerpo["contexto_id"] = str(contexto_id)
    r = cli.post(GASTO, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return uuid.UUID(cuerpo["intencion_id"])


def ingreso(cli, cuenta, *, fecha="2026-10-05", importe="100.00", categoria_id=None, tercero_id=None,
            contexto_id=None, atribucion="SOLO_MIO", nota=None) -> uuid.UUID:
    cuerpo = {"intencion_id": str(uuid.uuid4()), "importe": importe, "moneda": "EUR", "fecha_hecho": str(fecha),
              "cuenta_id": str(cuenta), "presupuestable": True, "atribucion": atribucion,
              "categoria": _cat(categoria_id), "nota": nota}
    if tercero_id:
        cuerpo["tercero_id"] = str(tercero_id)
    if contexto_id:
        cuerpo["contexto_id"] = str(contexto_id)
    r = cli.post(INGRESO, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return uuid.UUID(cuerpo["intencion_id"])


def transferencia(cli, origen, destino, *, fecha="2026-10-05", importe="500.00", nota=None) -> uuid.UUID:
    cuerpo = {"intencion_id": str(uuid.uuid4()), "importe": importe, "moneda": "EUR", "fecha_hecho": str(fecha),
              "cuenta_origen_id": str(origen), "cuenta_destino_id": str(destino), "nota": nota}
    r = cli.post(TRANSF, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return uuid.UUID(cuerpo["intencion_id"])


def desactivar_tercero(cli, tid):
    t = next(x for x in cli.get("/v1/terceros", headers=h.AUTH).json()["terceros"] if x["id"] == str(tid))
    r = cli.post(f"/v1/terceros/{tid}/desactivar", json={"row_version": t["row_version"]}, headers=h.AUTH)
    assert r.status_code == 200, r.text


def reactivar_tercero(cli, tid):
    t = next(x for x in cli.get("/v1/terceros", headers=h.AUTH).json()["terceros"] if x["id"] == str(tid))
    r = cli.post(f"/v1/terceros/{tid}/reactivar", json={"row_version": t["row_version"]}, headers=h.AUTH)
    assert r.status_code == 200, r.text


def desactivar_categoria(owner, cid):
    h.como_owner(owner, "UPDATE gapto.categorias_financieras SET enabled=false WHERE id=%s", (cid,))


# ------------------------------------------------------------------ fixtures de motor (OP-22)
def hecho_motor(owner, efectos, *, fecha="2026-10-05", tipo="GASTO", moneda="EUR", concepto=None, total=None):
    """Hecho por OP-22 (HechosCompuestosService) para casos que los writers de
    F05 no capturan: varios efectos, atribucion PARCIAL o 0, devolucion (GASTO
    negativo), DERECHO_COBRO, otra moneda, concepto historico.
    `efectos`: lista de (tipo_efecto, delta, estado_atribucion, categoria_id,
    [(actor_id, importe), ...])."""
    import decimal

    from app.core.modelos import DatosCreacionHecho
    from app.core.modelos_compuesto import DatosHechoCompuesto
    from app.core.modelos_efectos import DatosAtribucion, DatosEfecto
    from app.core.contexto import ContextoOperacion
    from app.services.compuesto_service import HechosCompuestosService
    from app.services.previsiones_service import impacto_correccion_ancla

    D = decimal.Decimal
    hid = uuid.uuid4()
    lista = [DatosEfecto(efecto_id=uuid.uuid4(), tipo_efecto=t, importe_delta=D(str(d)), estado_atribucion=e,
                         categoria_id=c,
                         atribuciones=tuple(DatosAtribucion(atribucion_id=uuid.uuid4(), actor_id=a,
                                                            importe_atribuido=D(str(i)), criterio_atribucion="MANUAL")
                                            for a, i in at))
             for t, d, e, c, at in efectos]
    importe = D(str(total)) if total is not None else sum((abs(D(str(d))) for _, d, _, _, _ in efectos), D(0))
    hecho = DatosCreacionHecho(hecho_id=hid, fecha_hecho=dt.date.fromisoformat(str(fecha)), moneda=moneda,
                               presupuestable=True, estado_localizacion="DESCONOCIDA", tipo_hecho_codigo=tipo,
                               concepto=concepto, importe_total=importe)
    servicio = HechosCompuestosService(fh.unidad(), impacto_ancla=impacto_correccion_ancla)
    servicio.registrar_hecho_compuesto(ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4()),
                                       DatosHechoCompuesto(hecho=hecho, efectos=lista))
    return hid
