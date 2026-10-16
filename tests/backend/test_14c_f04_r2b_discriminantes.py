# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_14c_f04_r2b_discriminantes.py
# Ruta: tests/backend/test_14c_f04_r2b_discriminantes.py
# Descripcion: F04-R2 R2-B (contrato F04-R2 v0.8 §1.5, §2.1, §2.2, §2.4,
#   §2.5, §3.4, §4.1, §5, §8.1, §10.1-§10.3; mandato F04-R2B v1.0 §3).
#   Discriminantes que FALLAN sobre bad0b5f y pasan con R2-B, todos con el rol
#   real gapto_runtime (UnidadDeTrabajo con SET LOCAL ROLE y RLS activa).
#     OP-21P: C1 seis dimensiones (48,72 -> 47,82) con id, row_version, saldo
#       y auditoria fila a fila; C3 50/50 con porcentaje congelado; residual
#       33,33/33,33/33,34; decisiones exigidas; fecha y cuenta; reglas de la
#       cuenta nueva; R-10; reversiones (PRE M1/M2); declaraciones; E-2 bis;
#       evidencia persistida (§2.5); periodo cerrado y ledger; previsiones
#       (R1-OBS-01 y vinculos_a_corregir); fuera de v1 (devolucion, ingreso,
#       varios movimientos, compartido).
#     OP-21T: importe, fecha, cuenta de una pata y de las dos, MISMA_CUENTA,
#       T-1 bis.
#     §3.4 (OP-21 completo): sonda de R2-A, casos de §3.4.1 y bajada.
#     Auditoria: sin request_id, request_id con otra intencion, repeticion
#       idempotente, rollback tras la ultima escritura, reconstruccion.
#     Capacidad: CUENTA_SIN_CAPACIDAD desde el adaptador, sin escritura.
#     §10.3: ninguna ruta de R2-B anula un movimiento.
#   Las identidades de OP-21P/OP-21T se importan DENTRO de los fixtures para
#   que, sobre la base, cada test falle por si mismo (no la coleccion entera).
# Version: 0.1.0 (F04-R2 R2-B)
# ============================================================

from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import json
import uuid

import psycopg
import pytest

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import DatosCreacionHecho
from app.core.modelos_compuesto import DatosHechoCompuesto, DatosPagoCompuesto
from app.core.modelos_efectos import DatosAtribucion, DatosEfecto
from app.core.modelos_tesoreria import DatosAportacion, DatosConciliacion, DatosMovimiento, DatosReversion
from app.core.modelos_transferencia import DatosTransferencia
from app.services.correcciones_service import DatosCorreccion
from conftest import _crear_cuenta, leer_fila
from test_117_op13_devolucion import crear_origen, datos_devolucion
from test_138_f04_r1_discriminantes import prevision_manual, version_hecho, vincular
from test_140_f04_r3_op22 import como_owner, op22  # noqa: F401

D = decimal.Decimal
F = dt.date.fromisoformat
FECHA = F("2027-06-01")
MOTIVO = "importe tecleado mal"


# ==================================================================
# Utilidades
# ==================================================================
@pytest.fixture()
def op21(unidad):
    """OP-21P / OP-21T con los colaboradores de previsiones cableados."""
    from app.services.correccion_tesoreria_service import CorreccionTesoreriaService
    from app.services.previsiones_service import conjunto_impacto_correccion_ancla, impacto_correccion_ancla

    return CorreccionTesoreriaService(unidad, impacto_ancla=impacto_correccion_ancla,
                                      conjunto_impacto=conjunto_impacto_correccion_ancla)


def nuevo(contexto: ContextoOperacion) -> ContextoOperacion:
    """Cada correccion es una peticion con su propio request_id (§6.4)."""
    return ContextoOperacion.de_usuario(contexto.owner_user_id, request_id=uuid.uuid4())


@dataclasses.dataclass
class Gasto:
    hecho: uuid.UUID
    efecto: uuid.UUID
    movimiento: uuid.UUID
    conciliacion: uuid.UUID
    cuenta: uuid.UUID
    atribuciones: list[uuid.UUID]
    aportaciones: list[uuid.UUID]


def gasto(op22, contexto, cuenta, importe="48.7200", *, atribuciones=(), aportaciones=(), movimiento=None,
          fecha=FECHA, tipo="GASTO") -> Gasto:
    """Gasto pagado como el de VS-01 (OP-22): hecho + efecto GASTO + movimiento
    -X + conciliacion -X (+ atribuciones y aportaciones opcionales).
    atribuciones: (actor, importe, porcentaje); aportaciones: (actor, importe,
    criterio, porcentaje, suelta)."""
    h = DatosCreacionHecho(hecho_id=uuid.uuid4(), fecha_hecho=fecha, moneda="EUR", presupuestable=True,
                           estado_localizacion="DESCONOCIDA", tipo_hecho_codigo=tipo, concepto="gasto R2-B",
                           importe_total=D(importe))
    atribs = tuple(DatosAtribucion(atribucion_id=uuid.uuid4(), actor_id=a, importe_atribuido=D(i),
                                   criterio_atribucion="MANUAL", porcentaje_aplicado=None if p is None else D(p))
                   for a, i, p in atribuciones)
    efecto = DatosEfecto(efecto_id=uuid.uuid4(), tipo_efecto="GASTO" if tipo == "GASTO" else "INGRESO",
                         importe_delta=D(importe), estado_atribucion="COMPLETA" if atribs else "NO_DISPONIBLE",
                         atribuciones=atribs)
    signo = -1 if tipo == "GASTO" else 1
    mov = DatosMovimiento(movimiento_id=uuid.uuid4(), cuenta_id=cuenta, fecha_movimiento=fecha,
                          importe=signo * D(movimiento or importe), clase_movimiento="OPERACION")
    conc = DatosConciliacion(uuid.uuid4(), h.hecho_id, mov.movimiento_id, signo * D(importe))
    aps = [DatosAportacion(aportacion_id=uuid.uuid4(), importe=D(i), criterio_aportacion=c, actor_id=a,
                           porcentaje_aplicado=None if p is None else D(p),
                           hecho_movimiento_tesoreria_id=None if suelta else conc.conciliacion_id)
           for a, i, c, p, suelta in aportaciones]
    op22.registrar_hecho_compuesto(nuevo(contexto), DatosHechoCompuesto(
        hecho=h, efectos=[efecto], pagos=[DatosPagoCompuesto(movimiento=mov, conciliacion=conc)], aportaciones=aps))
    return Gasto(h.hecho_id, efecto.efecto_id, mov.movimiento_id, conc.conciliacion_id, cuenta,
                 [a.atribucion_id for a in atribs], [a.aportacion_id for a in aps])


def version_mov(admin, owner, movimiento_id) -> int:
    return leer_fila(admin, owner, "SELECT row_version FROM gapto.movimientos_tesoreria WHERE id = %s",
                     (movimiento_id,))[0]


def datos_pago(admin, owner, g: Gasto, **kw):
    from app.services.correccion_tesoreria_service import DatosCorreccionPago

    base = dict(hecho_id=g.hecho, row_version_esperada=version_hecho(admin, owner, g.hecho),
                movimiento_row_version_esperada=version_mov(admin, owner, g.movimiento), motivo=MOTIVO,
                error_de_registro=True)
    base.update(kw)
    return DatosCorreccionPago(**base)


def corregir(op21, contexto, admin, g: Gasto, **kw):
    ctx = kw.pop("ctx", None) or nuevo(contexto)
    return op21.corregir_pago(ctx, datos_pago(admin, contexto.owner_user_id, g, **kw))


def _todas(admin, sql, params):
    with admin.cursor() as cur:
        cur.execute("RESET ROLE")
        cur.execute(sql, params)
        return cur.fetchall()


def estado6(admin, g: Gasto) -> dict:
    """Oraculo de §10.2: las seis dimensiones, identidad, version y saldo."""
    return {
        "hecho": _todas(admin, "SELECT importe_total, fecha_hecho, row_version, estado FROM gapto.hechos_financieros "
                               "WHERE id = %s", (g.hecho,)),
        "efecto": _todas(admin, "SELECT id, importe_delta FROM gapto.hecho_efectos WHERE hecho_id = %s", (g.hecho,)),
        "atribuciones": _todas(admin, "SELECT id, importe_atribuido FROM gapto.efecto_atribuciones "
                                      "WHERE efecto_id = %s ORDER BY id", (g.efecto,)),
        "movimiento": _todas(admin, "SELECT id, importe, fecha_movimiento, cuenta_id, row_version, estado "
                                    "FROM gapto.movimientos_tesoreria WHERE id = %s", (g.movimiento,)),
        "conciliacion": _todas(admin, "SELECT id, importe_asignado FROM gapto.hecho_movimientos_tesoreria "
                                      "WHERE hecho_id = %s", (g.hecho,)),
        "aportaciones": _todas(admin, "SELECT id, importe FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s "
                                      "ORDER BY id", (g.hecho,)),
    }


def saldo(admin, cuenta) -> decimal.Decimal:
    return _todas(admin, "SELECT COALESCE(sum(importe), 0) FROM gapto.movimientos_tesoreria "
                         "WHERE cuenta_id = %s AND estado = 'ACTIVO'", (cuenta,))[0][0]


def auditorias(admin, request_id) -> list[tuple]:
    return _todas(admin, "SELECT tabla, registro_id, accion, datos_antes, datos_despues, motivo "
                         "FROM gapto.auditoria WHERE request_id = %s ORDER BY tabla, registro_id", (request_id,))


def rechazo(excinfo, codigo: CodigoError, motivo: str | None = None, detalle: str | None = None) -> None:
    assert excinfo.value.codigo is codigo, excinfo.value
    if motivo is not None:
        assert excinfo.value.contexto_extra.get("motivo") == motivo, excinfo.value.contexto_extra
    if detalle is not None:
        assert excinfo.value.contexto_extra.get("detalle") == detalle, excinfo.value.contexto_extra


def sin_cambios(admin, g: Gasto, antes: dict) -> None:
    assert estado6(admin, g) == antes


def capacidad(admin, owner, cuenta, *codigos) -> None:
    for codigo in codigos:
        como_owner(admin, owner, "INSERT INTO gapto.cuenta_capacidades (id, cuenta_id, capacidad_codigo) "
                                 "VALUES (%s, %s, %s)", (uuid.uuid4(), cuenta, codigo))


def cierre(admin, owner, estado: str, version: int, reemplaza=None, desde="2027-06-01", hasta="2027-06-30"):
    i = uuid.uuid4()
    como_owner(admin, owner,
               "INSERT INTO gapto.cierres_mensuales (id, owner_user_id, periodo_desde, periodo_hasta, cerrado_at, "
               "criterio, origen_cierre, metodologia_version, estado, version_cierre, reemplaza_cierre_id, "
               "reabierto_at) VALUES (%s, %s, %s, %s, now(), 'CAJA', 'CALCULADO_2027', 'v1', %s, %s, %s, "
               "CASE WHEN %s = 'REABIERTO' THEN now() END)",
               (i, owner, F(desde), F(hasta), estado, version, reemplaza, estado))
    return i


def importar(admin, owner, tabla, registro) -> None:
    fuente, origen = uuid.uuid4(), uuid.uuid4()
    como_owner(admin, owner, "INSERT INTO gapto.fuentes_importacion (id, owner_user_id, tipo_fuente, nombre_fuente) "
                             "VALUES (%s, %s, 'OTRO', 'fuente R2-B')", (fuente, owner))
    como_owner(admin, owner, "INSERT INTO gapto.registros_origen_importacion (id, fuente_importacion_id, "
                             "contenedor_origen, datos_origen) VALUES (%s, %s, 'hoja', '{}'::jsonb)", (origen, fuente))
    como_owner(admin, owner, "INSERT INTO gapto.mapeos_importacion (id, registro_origen_id, tabla_destino, "
                             "registro_destino_id, tipo_mapping, confianza) VALUES (%s, %s, %s, %s, 'CREADO', 'ALTA')",
               (uuid.uuid4(), origen, tabla, registro))


def sql_admin(admin, sql, params=()) -> None:
    with admin.cursor() as cur:
        cur.execute("RESET ROLE")
        cur.execute(sql, params)


# ==================================================================
# OP-21P · C1, seis dimensiones (§2.1.2, §10.2)
# ==================================================================
def test_c1_seis_dimensiones_en_sitio_con_saldo_y_auditoria(op22, op21, contexto, admin, cuenta, actor_a):
    g = gasto(op22, contexto, cuenta, atribuciones=[(actor_a, "48.7200", None)],
              aportaciones=[(actor_a, "48.7200", "PARTICIPACION_CUENTA", "100", False)])
    antes = estado6(admin, g)
    saldo_antes = saldo(admin, cuenta)
    ctx = nuevo(contexto)
    r = corregir(op21, contexto, admin, g, ctx=ctx, importe=D("47.82"))
    despues = estado6(admin, g)
    assert despues["hecho"][0][:2] == (D("47.8200"), FECHA) and despues["hecho"][0][2] == antes["hecho"][0][2] + 1
    assert despues["efecto"] == [(g.efecto, D("47.8200"))]
    assert despues["atribuciones"] == [(g.atribuciones[0], D("47.8200"))]
    assert despues["movimiento"][0][:4] == (g.movimiento, D("-47.8200"), FECHA, cuenta)
    assert despues["movimiento"][0][4] == antes["movimiento"][0][4] + 1 and despues["movimiento"][0][5] == "ACTIVO"
    assert despues["conciliacion"] == [(g.conciliacion, D("-47.8200"))]
    assert despues["aportaciones"] == [(g.aportaciones[0], D("47.8200"))]
    assert saldo(admin, cuenta) == saldo_antes + D("0.9000")
    assert r.hecho_row_version == despues["hecho"][0][2] and r.movimientos == {g.movimiento: despues["movimiento"][0][4]}
    filas = auditorias(admin, ctx.request_id)
    assert sorted((t, a) for t, _, a, _, _, _ in filas) == sorted([
        ("hechos_financieros", "ACTUALIZAR"), ("hecho_efectos", "ACTUALIZAR"), ("efecto_atribuciones", "ACTUALIZAR"),
        ("movimientos_tesoreria", "ACTUALIZAR"), ("hecho_movimientos_tesoreria", "ACTUALIZAR"),
        ("hecho_aportaciones_pago", "ACTUALIZAR")])
    assert r.filas_auditadas == len(filas) == 6 and {m for *_, m in filas} == {MOTIVO}
    por_tabla = {t: (a, d) for t, _, _, a, d, _ in filas}
    assert por_tabla["movimientos_tesoreria"][0]["row_version"] == antes["movimiento"][0][4]
    assert por_tabla["movimientos_tesoreria"][1]["row_version"] == despues["movimiento"][0][4]
    assert por_tabla["hechos_financieros"][0]["row_version"] == antes["hecho"][0][2]
    assert D(str(por_tabla["hecho_efectos"][0]["importe_delta"])) == D("48.72")


def test_c1_reconstruccion_del_estado_previo_desde_la_auditoria(op22, op21, contexto, admin, cuenta, actor_a):
    g = gasto(op22, contexto, cuenta, atribuciones=[(actor_a, "48.7200", None)])
    antes = estado6(admin, g)
    ctx = nuevo(contexto)
    corregir(op21, contexto, admin, g, ctx=ctx, importe=D("47.82"), fecha=F("2027-06-03"))
    fotos = {(t, r): a for t, r, _, a, _, _ in auditorias(admin, ctx.request_id)}
    hecho = fotos[("hechos_financieros", g.hecho)]
    mov = fotos[("movimientos_tesoreria", g.movimiento)]
    assert (D(str(hecho["importe_total"])), F(hecho["fecha_hecho"]), hecho["row_version"], hecho["estado"]) == antes["hecho"][0]
    assert (uuid.UUID(mov["id"]), D(str(mov["importe"])), F(mov["fecha_movimiento"]), uuid.UUID(mov["cuenta_id"]),
            mov["row_version"], mov["estado"]) == antes["movimiento"][0]
    efecto = fotos[("hecho_efectos", g.efecto)]
    assert (uuid.UUID(efecto["id"]), D(str(efecto["importe_delta"]))) == antes["efecto"][0]
    conc = fotos[("hecho_movimientos_tesoreria", g.conciliacion)]
    assert (uuid.UUID(conc["id"]), D(str(conc["importe_asignado"]))) == antes["conciliacion"][0]
    atrib = fotos[("efecto_atribuciones", g.atribuciones[0])]
    assert (uuid.UUID(atrib["id"]), D(str(atrib["importe_atribuido"]))) == antes["atribuciones"][0]


# ==================================================================
# OP-21P · reparto y aportaciones (§2.1.4)
# ==================================================================
def test_c3_reparto_50_50_con_porcentaje_congelado(op22, op21, contexto, admin, cuenta, actor_a, actor_b):
    g = gasto(op22, contexto, cuenta, atribuciones=[(actor_a, "24.3600", "50"), (actor_b, "24.3600", "50")],
              aportaciones=[(actor_a, "24.3600", "PARTICIPACION_CUENTA", "50", False),
                            (actor_b, "24.3600", "PARTICIPACION_CUENTA", "50", False)])
    corregir(op21, contexto, admin, g, importe=D("47.82"),
             atribuciones_nuevas={g.atribuciones[0]: D("23.91"), g.atribuciones[1]: D("23.91")})
    despues = estado6(admin, g)
    assert [i for _, i in despues["atribuciones"]] == [D("23.9100"), D("23.9100")]
    assert sorted(i for _, i in despues["aportaciones"]) == [D("23.9100"), D("23.9100")]


@pytest.mark.parametrize("porcentajes, importe, esperado", [
    (("33.3333", "33.3333", "33.3334"), "100.01", {2: D("33.3368")}),
    (("33.3333", "33.3333", "33.3333"), "100.01", {"menor": D("33.3367")}),
])
def test_residual_de_redondeo_en_la_de_mayor_porcentaje(op22, op21, contexto, admin, cuenta, actor_a, porcentajes,
                                                       importe, esperado):
    iniciales = [D("100") * D(p) / 100 for p in porcentajes]
    g = gasto(op22, contexto, cuenta, "100.0000",
              aportaciones=[(actor_a, str(i.quantize(D("0.0001"))), "PARTICIPACION_CUENTA", p, False)
                            for i, p in zip(iniciales, porcentajes)])
    corregir(op21, contexto, admin, g, importe=D(importe))
    finales = dict(estado6(admin, g)["aportaciones"])
    assert sum(finales.values()) == (D(importe) * sum(D(p) for p in porcentajes) / 100).quantize(D("0.0001"))
    if 2 in esperado:
        assert finales[g.aportaciones[2]] == esperado[2]
        assert finales[g.aportaciones[0]] == finales[g.aportaciones[1]] == D("33.3366")
    else:
        menor = min(g.aportaciones, key=str)
        assert finales[menor] == esperado["menor"]
        assert all(v == D("33.3366") for k, v in finales.items() if k != menor)


def test_reparto_no_determinista_exige_decision(op22, op21, contexto, admin, cuenta, actor_a, actor_b):
    g = gasto(op22, contexto, cuenta, atribuciones=[(actor_a, "24.3600", None), (actor_b, "24.3600", None)])
    antes = estado6(admin, g)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, importe=D("47.82"))
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "REPARTO_REQUIERE_DECISION")
    sin_cambios(admin, g, antes)


def test_aportacion_no_determinista_exige_decision(op22, op21, contexto, admin, cuenta, actor_a):
    g = gasto(op22, contexto, cuenta, aportaciones=[(actor_a, "48.7200", "MANUAL", None, False)])
    antes = estado6(admin, g)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, importe=D("47.82"))
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "APORTACION_REQUIERE_DECISION")
    sin_cambios(admin, g, antes)
    corregir(op21, contexto, admin, g, importe=D("47.82"), aportaciones_nuevas={g.aportaciones[0]: D("47.82")})
    assert estado6(admin, g)["aportaciones"] == [(g.aportaciones[0], D("47.8200"))]


def test_aportacion_no_vinculada_rechazada(op22, op21, contexto, admin, cuenta, actor_a):
    g = gasto(op22, contexto, cuenta, aportaciones=[(actor_a, "10.0000", "MANUAL", None, True)])
    antes = estado6(admin, g)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, importe=D("47.82"))
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "APORTACION_NO_VINCULADA")
    sin_cambios(admin, g, antes)


# ==================================================================
# OP-21P · fecha y cuenta (§2.1.2, §2.1.5)
# ==================================================================
def test_cambio_de_fecha_mueve_hecho_y_movimiento(op22, op21, contexto, admin, cuenta):
    g = gasto(op22, contexto, cuenta)
    corregir(op21, contexto, admin, g, fecha=F("2027-06-05"))
    e = estado6(admin, g)
    assert e["hecho"][0][1] == F("2027-06-05") and e["movimiento"][0][2] == F("2027-06-05")
    assert e["movimiento"][0][0] == g.movimiento and e["conciliacion"][0][1] == D("-48.7200")


def test_cambio_de_cuenta_mueve_el_saldo_y_conserva_el_id(op22, op21, contexto, admin, cuenta, cuenta_destino):
    g = gasto(op22, contexto, cuenta)
    s1, s2 = saldo(admin, cuenta), saldo(admin, cuenta_destino)
    corregir(op21, contexto, admin, g, cuenta_id=cuenta_destino)
    e = estado6(admin, g)
    assert e["movimiento"][0][0] == g.movimiento and e["movimiento"][0][3] == cuenta_destino
    assert saldo(admin, cuenta) == s1 + D("48.7200") and saldo(admin, cuenta_destino) == s2 - D("48.7200")


def test_cambio_de_cuenta_con_participacion_exige_aportaciones(op22, op21, contexto, admin, cuenta, cuenta_destino,
                                                              actor_a):
    g = gasto(op22, contexto, cuenta, aportaciones=[(actor_a, "48.7200", "PARTICIPACION_CUENTA", "100", False)])
    antes = estado6(admin, g)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, cuenta_id=cuenta_destino)
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "APORTACION_REQUIERE_DECISION")
    sin_cambios(admin, g, antes)
    corregir(op21, contexto, admin, g, cuenta_id=cuenta_destino, aportaciones_nuevas={g.aportaciones[0]: D("48.72")})
    assert estado6(admin, g)["movimiento"][0][3] == cuenta_destino


@pytest.mark.parametrize("caso", ["deshabilitada", "cerrada_antes", "otra_moneda", "otro_owner"])
def test_cuenta_nueva_no_valida_rechazada(op22, op21, contexto, admin, cuenta, otro_owner, caso):
    g = gasto(op22, contexto, cuenta)
    owner = contexto.owner_user_id
    if caso == "otra_moneda":
        nueva = _crear_cuenta(admin, owner, "USD")
    elif caso == "otro_owner":
        nueva = _crear_cuenta(admin, otro_owner, "EUR")
    else:
        nueva = _crear_cuenta(admin, owner, "EUR")
        sql_admin(admin, "UPDATE gapto.cuentas SET enabled = false WHERE id = %s" if caso == "deshabilitada"
                  # ck_cuentas__cierre_deshabilita: una cuenta cerrada esta siempre deshabilitada.
                  else "UPDATE gapto.cuentas SET enabled = false, fecha_cierre = '2027-05-31' WHERE id = %s", (nueva,))
    antes = estado6(admin, g)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, cuenta_id=nueva)
    if caso == "otra_moneda":
        rechazo(excinfo, CodigoError.MONEDA_INVALIDA)
    elif caso == "otro_owner":
        rechazo(excinfo, CodigoError.CUENTA_DESCONOCIDA)
    else:
        rechazo(excinfo, CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO, "CUENTA_DESACTIVADA")
    sin_cambios(admin, g, antes)


def test_r10_importe_en_una_cuenta_hoy_deshabilitada_se_admite(op22, op21, contexto, admin, cuenta):
    g = gasto(op22, contexto, cuenta)
    sql_admin(admin, "UPDATE gapto.cuentas SET enabled = false WHERE id = %s", (cuenta,))
    corregir(op21, contexto, admin, g, importe=D("47.82"))
    assert estado6(admin, g)["movimiento"][0][1] == D("-47.8200")


# ==================================================================
# OP-21P · reversiones (E-4, PRE M1 y M2)
# ==================================================================
def _revertir(servicio_tesoreria, contexto, g: Gasto, importe="10.00"):
    servicio_tesoreria.revertir_movimiento(nuevo(contexto), DatosReversion(
        reversion_id=uuid.uuid4(), movimiento_original_id=g.movimiento, cuenta_id=g.cuenta,
        fecha_movimiento=F("2027-06-10"), importe=D(importe)))


@pytest.mark.parametrize("dimension", ["fecha", "importe", "cuenta"])
@pytest.mark.parametrize("estado_reversion", ["ACTIVA", "ANULADA"])
def test_reversion_existente_en_las_tres_dimensiones(op22, op21, servicio_tesoreria, contexto, admin, cuenta,
                                                     cuenta_destino, dimension, estado_reversion):
    g = gasto(op22, contexto, cuenta)
    _revertir(servicio_tesoreria, contexto, g)
    if estado_reversion == "ANULADA":
        sql_admin(admin, "UPDATE gapto.movimientos_tesoreria SET estado = 'ANULADO', anulado_at = now() "
                         "WHERE reversion_de_movimiento_id = %s", (g.movimiento,))
    antes = estado6(admin, g)
    cambio = {"fecha": {"fecha": F("2027-06-02")}, "importe": {"importe": D("47.82")},
              "cuenta": {"cuenta_id": cuenta_destino}}[dimension]
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, **cambio)
    rechazo(excinfo, CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO, "REVERSION_EXISTENTE")
    assert excinfo.value.sqlstate != "23503"
    sin_cambios(admin, g, antes)


# ==================================================================
# OP-21P · declaracion y elegibilidad (§1.5, §2.1.1, §2.5)
# ==================================================================
@pytest.mark.parametrize("declaracion", [None, False])
def test_sin_error_de_registro_es_acontecimiento_posterior(op22, op21, contexto, admin, cuenta, declaracion):
    g = gasto(op22, contexto, cuenta)
    antes = estado6(admin, g)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, importe=D("47.82"), error_de_registro=declaracion)
    rechazo(excinfo, CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO, "ACONTECIMIENTO_POSTERIOR")
    assert excinfo.value.contexto_extra["vias"] == ["OP-13", "OP-11", "OP-18"]
    sin_cambios(admin, g, antes)


def test_e2_bis_conciliacion_parcial(op22, op21, contexto, admin, cuenta):
    g = gasto(op22, contexto, cuenta, movimiento="60.0000")
    antes = estado6(admin, g)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, importe=D("47.82"))
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "CONCILIACION_PARCIAL")
    sin_cambios(admin, g, antes)


@pytest.mark.parametrize("tabla", ["hechos_financieros", "movimientos_tesoreria"])
def test_origen_importado_rechazado(op22, op21, contexto, admin, cuenta, tabla):
    g = gasto(op22, contexto, cuenta)
    importar(admin, contexto.owner_user_id, tabla, g.hecho if tabla == "hechos_financieros" else g.movimiento)
    antes = estado6(admin, g)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, importe=D("47.82"))
    rechazo(excinfo, CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO, "ORIGEN_IMPORTADO")
    sin_cambios(admin, g, antes)


def test_ajuste_de_saldo_rechazado(op22, op21, contexto, admin, cuenta):
    g = gasto(op22, contexto, cuenta)
    sql_admin(admin, "UPDATE gapto.movimientos_tesoreria SET clase_movimiento = 'AJUSTE_SALDO' WHERE id = %s",
              (g.movimiento,))
    antes = estado6(admin, g)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, importe=D("47.82"))
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "TIPO_NO_SOPORTADO")
    sin_cambios(admin, g, antes)


@pytest.mark.parametrize("cierres, cambio, rechaza", [
    (["CERRADO"], {"importe": D("47.82")}, True),
    (["CERRADO", "REABIERTO"], {"importe": D("47.82")}, False),
    (["CERRADO", "REABIERTO", "CERRADO"], {"importe": D("47.82")}, True),
    (["CERRADO@07"], {"fecha": F("2027-07-03")}, True),
    (["CERRADO@07"], {"importe": D("47.82")}, False),
])
def test_periodo_cerrado_con_cierres_sinteticos(op22, op21, contexto, admin, cuenta, cierres, cambio, rechaza):
    g = gasto(op22, contexto, cuenta)
    owner = contexto.owner_user_id
    anterior = None
    for version, marca in enumerate(cierres, start=1):
        estado, _, mes = marca.partition("@")
        desde, hasta = (("2027-07-01", "2027-07-31") if mes == "07" else ("2027-06-01", "2027-06-30"))
        anterior = cierre(admin, owner, estado, version, anterior, desde, hasta)
    antes = estado6(admin, g)
    if not rechaza:
        corregir(op21, contexto, admin, g, **cambio)
        return
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, **cambio)
    rechazo(excinfo, CodigoError.PERIODO_CERRADO_SIN_POLITICA)
    sin_cambios(admin, g, antes)


def test_ledger_de_la_cuenta(op22, op21, contexto, admin, cuenta, cuenta_destino):
    g = gasto(op22, contexto, cuenta)
    sql_admin(admin, "UPDATE gapto.cuentas SET fecha_inicio_ledger = '2027-06-02', saldo_apertura = 0 WHERE id IN (%s, %s)",
              (cuenta, cuenta_destino))
    antes = estado6(admin, g)
    for cambio in ({"cuenta_id": cuenta_destino}, {"fecha": F("2027-05-30")}):
        with pytest.raises(ErrorMotor) as excinfo:
            corregir(op21, contexto, admin, g, **cambio)
        rechazo(excinfo, CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO, "FECHA_ANTERIOR_INICIO")
        sin_cambios(admin, g, antes)
    # Ya era anterior y no cambian ni fecha ni cuenta: se respeta.
    corregir(op21, contexto, admin, g, importe=D("47.82"))


@pytest.mark.parametrize("version", ["hecho", "movimiento"])
def test_version_desfasada(op22, op21, contexto, admin, cuenta, version):
    g = gasto(op22, contexto, cuenta)
    antes = estado6(admin, g)
    kw = {"row_version_esperada": antes["hecho"][0][2] - 1} if version == "hecho" else {
        "movimiento_row_version_esperada": antes["movimiento"][0][4] - 1}
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, importe=D("47.82"), **kw)
    rechazo(excinfo, CodigoError.VERSION_DESFASADA)
    sin_cambios(admin, g, antes)


# ==================================================================
# OP-21P · fuera de v1 (§2.4, §3.3, §4.2)
# ==================================================================
def test_devolucion_con_abono_no_se_corrige(servicio, servicio_efectos, servicio_devoluciones, op21, contexto, admin,
                                            cuenta):
    original = crear_origen(servicio, servicio_efectos, contexto)
    dev = datos_devolucion(original, movimiento_id=uuid.uuid4(), conciliacion_id=uuid.uuid4(), cuenta_id=cuenta,
                           fecha_movimiento=F("2027-05-20"))
    servicio_devoluciones.devolver(nuevo(contexto), dev)
    g = Gasto(dev.hecho_id, dev.efecto_id, dev.movimiento_id, dev.conciliacion_id, cuenta, [], [])
    antes = estado6(admin, g)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, importe=D("40.00"))
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "DEVOLUCION")
    sin_cambios(admin, g, antes)


def test_ingreso_cobrado_fuera_de_v1(op22, op21, contexto, admin, cuenta):
    g = gasto(op22, contexto, cuenta, tipo="INGRESO")
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, importe=D("47.82"))
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "TIPO_NO_SOPORTADO")


def test_movimiento_compartido_fuera_de_v1(op22, op21, servicio_tesoreria, contexto, admin, cuenta):
    g = gasto(op22, contexto, cuenta, "30.0000", movimiento="50.0000")
    otro = gasto(op22, contexto, cuenta, "20.0000")
    sql_admin(admin, "UPDATE gapto.hecho_movimientos_tesoreria SET movimiento_tesoreria_id = %s WHERE id = %s",
              (g.movimiento, otro.conciliacion))
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, importe=D("29.00"))
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "MOVIMIENTO_COMPARTIDO")


# ==================================================================
# OP-21P · previsiones (§4.1, R1-OBS-01)
# ==================================================================
def test_p1_bajada_con_exceso_requiere_revision_sin_recortar(op22, op21, servicio_previsiones, contexto, admin,
                                                            cuenta):
    g = gasto(op22, contexto, cuenta)
    prevision = prevision_manual(servicio_previsiones, contexto)
    vincular(servicio_previsiones, contexto, prevision, g.hecho, "48.7200")
    r = corregir(op21, contexto, admin, g, importe=D("47.82"))
    assert r.requiere_revision and r.motivo_revision == "PORCION_EXCEDIDA" and r.previsiones_afectadas == (prevision,)
    assert _todas(admin, "SELECT importe_asignado FROM gapto.prevision_hechos WHERE hecho_id = %s",
                  (g.hecho,)) == [(D("48.7200"),)]


def test_vinculos_a_corregir_ajusta_la_prevision(op22, op21, servicio_previsiones, contexto, admin, cuenta):
    from app.services.correccion_tesoreria_service import DatosVinculoACorregir

    g = gasto(op22, contexto, cuenta)
    prevision = prevision_manual(servicio_previsiones, contexto)
    vincular(servicio_previsiones, contexto, prevision, g.hecho, "48.7200")
    vinculo = _todas(admin, "SELECT id FROM gapto.prevision_hechos WHERE hecho_id = %s", (g.hecho,))[0][0]
    version = servicio_previsiones.estado_de(contexto, prevision).row_version
    ctx = nuevo(contexto)
    r = corregir(op21, contexto, admin, g, ctx=ctx, importe=D("47.82"), vinculos_a_corregir=(
        DatosVinculoACorregir(vinculo, prevision, version, D("47.82")),))
    assert not r.requiere_revision
    assert _todas(admin, "SELECT importe_asignado FROM gapto.prevision_hechos WHERE id = %s", (vinculo,)) == [
        (D("47.8200"),)]
    assert servicio_previsiones.estado_de(contexto, prevision).row_version == version + 1
    assert ("prevision_hechos", vinculo) in {(t, i) for t, i, *_ in auditorias(admin, ctx.request_id)}


def test_vinculos_a_corregir_de_otro_hecho_rechazado(op22, op21, servicio_previsiones, contexto, admin, cuenta):
    from app.services.correccion_tesoreria_service import DatosVinculoACorregir

    g = gasto(op22, contexto, cuenta)
    otro = gasto(op22, contexto, cuenta)
    prevision = prevision_manual(servicio_previsiones, contexto)
    vincular(servicio_previsiones, contexto, prevision, otro.hecho, "48.7200")
    vinculo = _todas(admin, "SELECT id FROM gapto.prevision_hechos WHERE hecho_id = %s", (otro.hecho,))[0][0]
    version = servicio_previsiones.estado_de(contexto, prevision).row_version
    antes = estado6(admin, g)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, importe=D("47.82"), vinculos_a_corregir=(
            DatosVinculoACorregir(vinculo, prevision, version, D("47.82")),))
    rechazo(excinfo, CodigoError.AGREGADO_NO_ENCONTRADO)
    sin_cambios(admin, g, antes)


# ==================================================================
# OP-21T (§2.2)
# ==================================================================
@dataclasses.dataclass
class Transf:
    hecho: uuid.UUID
    salida: uuid.UUID
    entrada: uuid.UUID
    origen: uuid.UUID
    destino: uuid.UUID


def transferencia(servicio_transferencias, contexto, origen, destino, importe="100.0000") -> Transf:
    d = DatosTransferencia(transferencia_id=uuid.uuid4(), hecho_id=uuid.uuid4(), movimiento_salida_id=uuid.uuid4(),
                           movimiento_entrada_id=uuid.uuid4(), conciliacion_salida_id=uuid.uuid4(),
                           conciliacion_entrada_id=uuid.uuid4(), cuenta_origen_id=origen, cuenta_destino_id=destino,
                           fecha_hecho=FECHA, fecha_movimiento=FECHA, moneda="EUR", importe_salida=D(importe),
                           importe_entrada=D(importe))
    servicio_transferencias.transferir(nuevo(contexto), d)
    return Transf(d.hecho_id, d.movimiento_salida_id, d.movimiento_entrada_id, origen, destino)


def corregir_t(op21, contexto, admin, t: Transf, **kw):
    from app.services.correccion_tesoreria_service import DatosCorreccionTransferencia

    owner = contexto.owner_user_id
    base = dict(hecho_id=t.hecho, row_version_esperada=version_hecho(admin, owner, t.hecho),
                movimientos_row_version_esperadas={m: version_mov(admin, owner, m) for m in (t.salida, t.entrada)},
                motivo=MOTIVO, error_de_registro=True)
    ctx = kw.pop("ctx", None) or nuevo(contexto)
    base.update(kw)
    return op21.corregir_transferencia(ctx, DatosCorreccionTransferencia(**base))


def patas(admin, t: Transf):
    return _todas(admin, "SELECT m.id, m.importe, m.fecha_movimiento, m.cuenta_id, c.importe_asignado "
                         "FROM gapto.movimientos_tesoreria m JOIN gapto.hecho_movimientos_tesoreria c "
                         "ON c.movimiento_tesoreria_id = m.id WHERE m.id IN (%s, %s) ORDER BY m.importe",
                  (t.salida, t.entrada))


def test_op21t_importe_y_fecha_las_dos_patas_juntas(servicio_transferencias, op21, contexto, admin, cuenta,
                                                    cuenta_destino):
    t = transferencia(servicio_transferencias, contexto, cuenta, cuenta_destino)
    corregir_t(op21, contexto, admin, t, importe=D("90"), fecha=F("2027-06-04"))
    assert patas(admin, t) == [(t.salida, D("-90.0000"), F("2027-06-04"), cuenta, D("-90.0000")),
                               (t.entrada, D("90.0000"), F("2027-06-04"), cuenta_destino, D("90.0000"))]
    assert _todas(admin, "SELECT importe_total, fecha_hecho FROM gapto.hechos_financieros WHERE id = %s",
                  (t.hecho,)) == [(D("90.0000"), F("2027-06-04"))]


def test_op21t_cuenta_de_una_pata_y_de_las_dos(servicio_transferencias, op21, contexto, admin, cuenta, cuenta_destino):
    tercera, cuarta = (_crear_cuenta(admin, contexto.owner_user_id) for _ in range(2))
    t = transferencia(servicio_transferencias, contexto, cuenta, cuenta_destino)
    corregir_t(op21, contexto, admin, t, cuenta_origen_id=tercera)
    assert [p[3] for p in patas(admin, t)] == [tercera, cuenta_destino]
    corregir_t(op21, contexto, admin, t, cuenta_origen_id=cuenta, cuenta_destino_id=cuarta)
    assert [p[3] for p in patas(admin, t)] == [cuenta, cuarta]


def test_op21t_misma_cuenta(servicio_transferencias, op21, contexto, admin, cuenta, cuenta_destino):
    t = transferencia(servicio_transferencias, contexto, cuenta, cuenta_destino)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir_t(op21, contexto, admin, t, cuenta_destino_id=cuenta)
    rechazo(excinfo, CodigoError.MISMA_CUENTA)


def test_op21t_t1_bis_cobertura_por_pata(servicio_transferencias, op21, contexto, admin, cuenta, cuenta_destino):
    t = transferencia(servicio_transferencias, contexto, cuenta, cuenta_destino)
    sql_admin(admin, "UPDATE gapto.hecho_movimientos_tesoreria SET importe_asignado = -90 "
                     "WHERE movimiento_tesoreria_id = %s", (t.salida,))
    antes = patas(admin, t)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir_t(op21, contexto, admin, t, fecha=F("2027-06-02"))
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "CONCILIACION_PARCIAL")
    assert patas(admin, t) == antes


# ==================================================================
# §3.4 · OP-21 sobre una devolucion (capacidad del original)
# ==================================================================
def _devolucion(servicio, servicio_efectos, servicio_devoluciones, contexto, importe="45.0000"):
    original = crear_origen(servicio, servicio_efectos, contexto)
    dev = datos_devolucion(original, importe=D(importe))
    servicio_devoluciones.devolver(nuevo(contexto), dev)
    return original, dev


def _corregir_dev(servicio_correcciones, contexto, admin, dev, **filas):
    return servicio_correcciones.corregir(nuevo(contexto), DatosCorreccion(
        hecho_id=dev.hecho_id, row_version_esperada=version_hecho(admin, contexto.owner_user_id, dev.hecho_id),
        motivo="devolucion tecleada mal", **filas))


def _delta(admin, efecto_id):
    return _todas(admin, "SELECT importe_delta FROM gapto.hecho_efectos WHERE id = %s", (efecto_id,))[0][0]


def test_34_sonda_r2a_devolucion_por_encima_de_la_capacidad(servicio, servicio_efectos, servicio_devoluciones,
                                                           servicio_correcciones, contexto, admin):
    _, dev = _devolucion(servicio, servicio_efectos, servicio_devoluciones, contexto)
    with pytest.raises(ErrorMotor) as excinfo:
        _corregir_dev(servicio_correcciones, contexto, admin, dev,
                      efectos_a_actualizar={dev.efecto_id: {"importe_delta": D("-200")}})
    rechazo(excinfo, CodigoError.EXCEDE_CAPACIDAD_REVERSIBLE)
    assert _delta(admin, dev.efecto_id) == D("-45.0000")


def test_34_subida_y_bajada_bloquean_el_original(servicio, servicio_efectos, servicio_devoluciones,
                                                servicio_correcciones, contexto, admin, monkeypatch):
    """§3.4.1 ultima fila: tambien la bajada toma el lock del original, en UNA
    adquisicion {devolucion, original} del nivel de hechos (una sola via)."""
    from app.repositories import relaciones_repository as repo_rel

    original, dev = _devolucion(servicio, servicio_efectos, servicio_devoluciones, contexto)
    llamadas: list[list[uuid.UUID]] = []
    real = repo_rel.bloquear_hechos
    monkeypatch.setattr(repo_rel, "bloquear_hechos",
                        lambda sesion, ids: llamadas.append(sorted(ids, key=str)) or real(sesion, ids))
    for delta, esperado in (("-120", D("-120.0000")), ("-30", D("-30.0000"))):
        llamadas.clear()
        _corregir_dev(servicio_correcciones, contexto, admin, dev,
                      efectos_a_actualizar={dev.efecto_id: {"importe_delta": D(delta)}})
        assert _delta(admin, dev.efecto_id) == esperado
        assert llamadas[0] == sorted([dev.hecho_id, original], key=str), llamadas


def test_34_segunda_devolucion_cuenta_en_el_acumulado(servicio, servicio_efectos, servicio_devoluciones,
                                                     servicio_correcciones, contexto, admin):
    original, dev = _devolucion(servicio, servicio_efectos, servicio_devoluciones, contexto)
    servicio_devoluciones.devolver(nuevo(contexto), datos_devolucion(original, importe=D("50.0000")))
    with pytest.raises(ErrorMotor) as excinfo:
        _corregir_dev(servicio_correcciones, contexto, admin, dev,
                      efectos_a_actualizar={dev.efecto_id: {"importe_delta": D("-71")}})
    rechazo(excinfo, CodigoError.EXCEDE_CAPACIDAD_REVERSIBLE)
    _corregir_dev(servicio_correcciones, contexto, admin, dev,
                  efectos_a_actualizar={dev.efecto_id: {"importe_delta": D("-70")}})


@pytest.mark.parametrize("caso", ["multiples_originales", "naturaleza", "combinacion", "original_no_activo",
                                  "devolucion_anulada"])
def test_34_1_casos_limite(servicio, servicio_efectos, servicio_devoluciones, servicio_correcciones, contexto, admin,
                           caso):
    original, dev = _devolucion(servicio, servicio_efectos, servicio_devoluciones, contexto)
    filas = {"efectos_a_actualizar": {dev.efecto_id: {"importe_delta": D("-40")}}}
    if caso == "multiples_originales":
        otro = crear_origen(servicio, servicio_efectos, contexto)
        como_owner(admin, contexto.owner_user_id, "INSERT INTO gapto.hecho_relaciones (id, hecho_origen_id, "
                   "hecho_destino_id, tipo_relacion) VALUES (%s, %s, %s, 'DEVOLUCION_DE')",
                   (uuid.uuid4(), dev.hecho_id, otro))
        esperado = (CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "MULTIPLES_ORIGINALES")
    elif caso == "naturaleza":
        filas = {"efectos_a_actualizar": {dev.efecto_id: {"tipo_efecto": "DEUDA"}}}
        esperado = (CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "DEVOLUCION_NATURALEZA")
    elif caso == "combinacion":
        filas["relaciones_a_eliminar"] = (dev.relacion_id,)
        esperado = (CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "COMBINACION_NO_SOPORTADA")
    elif caso == "original_no_activo":
        sql_admin(admin, "UPDATE gapto.hechos_financieros SET estado = 'ANULADO', anulado_at = now() WHERE id = %s",
                  (original,))
        esperado = (CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO, "ORIGINAL_NO_ACTIVO", None)
    else:
        sql_admin(admin, "UPDATE gapto.hechos_financieros SET estado = 'ANULADO', anulado_at = now() WHERE id = %s",
                  (dev.hecho_id,))
        esperado = (CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO, None, None)
    with pytest.raises(ErrorMotor) as excinfo:
        _corregir_dev(servicio_correcciones, contexto, admin, dev, **filas)
    rechazo(excinfo, *esperado)
    assert _delta(admin, dev.efecto_id) == D("-45.0000")


# ==================================================================
# Auditoria (§8.1, §6.4)
# ==================================================================
def test_sin_request_id_rechazado(op22, op21, contexto, admin, cuenta):
    g = gasto(op22, contexto, cuenta)
    sin = object.__new__(ContextoOperacion)
    for campo, valor in (("owner_user_id", contexto.owner_user_id), ("actor_tipo", "USUARIO"),
                         ("actor_user_id", contexto.owner_user_id), ("request_id", None)):
        object.__setattr__(sin, campo, valor)
    antes = estado6(admin, g)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, ctx=sin, importe=D("47.82"))
    rechazo(excinfo, CodigoError.ENTRADA_INVALIDA, "REQUEST_ID_AUSENTE")
    sin_cambios(admin, g, antes)


def test_repeticion_idempotente_y_request_id_con_otra_intencion(op22, op21, contexto, admin, cuenta):
    g = gasto(op22, contexto, cuenta)
    otro = gasto(op22, contexto, cuenta)
    ctx = nuevo(contexto)
    datos = datos_pago(admin, contexto.owner_user_id, g, importe=D("47.82"))
    primera = op21.corregir_pago(ctx, datos)
    n = len(auditorias(admin, ctx.request_id))
    despues = estado6(admin, g)
    repetida = op21.corregir_pago(ctx, datos)  # versiones ya consumidas
    assert repetida.idempotente and repetida.hecho_row_version == primera.hecho_row_version
    assert len(auditorias(admin, ctx.request_id)) == n and estado6(admin, g) == despues
    for intento in (dataclasses.replace(datos, importe=D("47.00")),
                    dataclasses.replace(datos, motivo="otra razon"),
                    datos_pago(admin, contexto.owner_user_id, otro, importe=D("47.82"))):
        with pytest.raises(ErrorMotor) as excinfo:
            op21.corregir_pago(ctx, intento)
        rechazo(excinfo, CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION)
    assert len(auditorias(admin, ctx.request_id)) == n and estado6(admin, g) == despues


def test_rollback_tras_la_ultima_escritura_no_deja_nada(op22, op21, contexto, admin, cuenta, actor_a, monkeypatch):
    from app.services import correccion_tesoreria_service as servicio_mod

    g = gasto(op22, contexto, cuenta, atribuciones=[(actor_a, "48.7200", None)],
              aportaciones=[(actor_a, "48.7200", "PARTICIPACION_CUENTA", "100", False)])
    antes = estado6(admin, g)
    saldo_antes = saldo(admin, cuenta)

    def fallo(*_a, **_k):
        raise RuntimeError("fallo forzado tras la ultima escritura")

    monkeypatch.setattr(servicio_mod.CorreccionTesoreriaService, "_resultado", fallo)
    ctx = nuevo(contexto)
    with pytest.raises(Exception):
        corregir(op21, contexto, admin, g, ctx=ctx, importe=D("47.82"), fecha=F("2027-06-02"))
    sin_cambios(admin, g, antes)
    assert saldo(admin, cuenta) == saldo_antes and auditorias(admin, ctx.request_id) == []


# ==================================================================
# Capacidad desde el adaptador F05 (§2.1.5) y §10.3
# ==================================================================
def test_adaptador_cuenta_sin_capacidad_sin_escritura(op22, unidad, contexto, admin, cuenta, cuenta_destino):
    from app.api.ejecucion_correccion import corregir_pago, corregir_transferencia
    from app.api.ejecucion_registro import RechazoRegistro
    from app.services.transferencias_service import TransferenciasService

    owner = contexto.owner_user_id
    g = gasto(op22, contexto, cuenta)
    antes = estado6(admin, g)
    r = corregir_pago(unidad, nuevo(contexto), datos_pago(admin, owner, g, cuenta_id=cuenta_destino))
    assert isinstance(r, RechazoRegistro) and r.codigo == "CUENTA_SIN_CAPACIDAD"
    assert r.detalle["capacidad"] == "PAGAR_GASTO" and r.detalle["cuenta_id"] == str(cuenta_destino)
    sin_cambios(admin, g, antes)
    capacidad(admin, owner, cuenta_destino, "PAGAR_GASTO")
    hecho = corregir_pago(unidad, nuevo(contexto), datos_pago(admin, owner, g, cuenta_id=cuenta_destino))
    assert not isinstance(hecho, RechazoRegistro) and estado6(admin, g)["movimiento"][0][3] == cuenta_destino

    tercera = _crear_cuenta(admin, owner)
    t = transferencia(TransferenciasService(unidad), contexto, cuenta, tercera)
    from app.services.correccion_tesoreria_service import DatosCorreccionTransferencia
    datos_t = DatosCorreccionTransferencia(
        hecho_id=t.hecho, row_version_esperada=version_hecho(admin, owner, t.hecho),
        movimientos_row_version_esperadas={m: version_mov(admin, owner, m) for m in (t.salida, t.entrada)},
        motivo=MOTIVO, error_de_registro=True, cuenta_destino_id=_crear_cuenta(admin, owner))
    r = corregir_transferencia(unidad, nuevo(contexto), datos_t)
    assert isinstance(r, RechazoRegistro) and r.detalle["capacidad"] == "TRANSFERIR_ENTRADA"


def test_ninguna_ruta_de_r2b_anula_un_movimiento(op22, op21, servicio_transferencias, contexto, admin, cuenta,
                                                 cuenta_destino):
    from app.repositories import correccion_tesoreria_repository as repo

    assert "estado" not in repo.CORREGIBLES_MOVIMIENTO and "anulado_at" not in repo.CORREGIBLES_MOVIMIENTO
    g = gasto(op22, contexto, cuenta)
    t = transferencia(servicio_transferencias, contexto, cuenta, cuenta_destino)
    corregir(op21, contexto, admin, g, importe=D("47.82"), fecha=F("2027-06-02"), cuenta_id=cuenta_destino)
    corregir_t(op21, contexto, admin, t, importe=D("10"), fecha=F("2027-06-02"))
    assert _todas(admin, "SELECT count(*) FROM gapto.movimientos_tesoreria WHERE id IN (%s, %s, %s) "
                         "AND estado <> 'ACTIVO'", (g.movimiento, t.salida, t.entrada)) == [(0,)]


# ==================================================================
# Inventario de writers de la realidad confirmada (§10.6, R-F04R2-07)
# ==================================================================
#: Registro CERRADO (fichero, tabla) de UPDATE en backend/ y scripts/. Altas de
#: R2-B, justificadas: correccion_tesoreria_repository (OP-21P/OP-21T, correccion
#: EN SITIO de hecho, movimiento, conciliacion y aportacion; contrato §2.1.3,
#: §8.3: GRANT de 0130, sin DDL). Las demas son las existentes en bad0b5f.
WRITERS_UPDATE = {
    ("backend/app/repositories/hechos_repository.py", "hechos_financieros"),
    ("backend/app/repositories/tesoreria_repository.py", "movimientos_tesoreria"),
    ("backend/app/repositories/tesoreria_repository.py", "hecho_aportaciones_pago"),
    ("backend/app/repositories/correccion_tesoreria_repository.py", "hechos_financieros"),
    ("backend/app/repositories/correccion_tesoreria_repository.py", "movimientos_tesoreria"),
    ("backend/app/repositories/correccion_tesoreria_repository.py", "hecho_movimientos_tesoreria"),
    ("backend/app/repositories/correccion_tesoreria_repository.py", "hecho_aportaciones_pago"),
}


def test_inventario_writers_update_de_tesoreria_y_hechos():
    import pathlib
    import re

    raiz = pathlib.Path(__file__).resolve().parents[2]
    patron = re.compile(r"UPDATE\s+gapto\.(movimientos_tesoreria|hecho_movimientos_tesoreria|"
                        r"hecho_aportaciones_pago|hechos_financieros)\b")
    encontrados = set()
    for base in ("backend", "scripts"):
        for p in (raiz / base).rglob("*.py"):
            ruta = p.relative_to(raiz).as_posix()
            if ruta.startswith("scripts/dev/mutantes_"):
                continue  # los mutantes son texto
            for m in patron.finditer(p.read_text(encoding="utf-8")):
                encontrados.add((ruta, m.group(1)))
    assert encontrados == WRITERS_UPDATE


# ==================================================================
# Guardas restantes (una prueba por guarda, para su mutante)
# ==================================================================
def test_motivo_ausente(op22, op21, contexto, admin, cuenta):
    g = gasto(op22, contexto, cuenta)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, importe=D("47.82"), motivo="   ")
    rechazo(excinfo, CodigoError.MOTIVO_AUSENTE)


def test_e1_hecho_que_no_es_gasto(op22, op21, contexto, admin, cuenta):
    g = gasto(op22, contexto, cuenta)
    sql_admin(admin, "UPDATE gapto.hechos_financieros SET tipo_hecho_id = (SELECT id FROM gapto.tipos_hecho "
                     "WHERE codigo = 'INGRESO') WHERE id = %s", (g.hecho,))
    antes = estado6(admin, g)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, importe=D("47.82"))
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "TIPO_NO_SOPORTADO")
    sin_cambios(admin, g, antes)


def test_e1_inversion_fuera_de_v1(op22, op21, contexto, admin, cuenta):
    from test_140_f04_r3_op22 import nueva_entidad

    g = gasto(op22, contexto, cuenta)
    entidad = nueva_entidad(admin, contexto.owner_user_id, "INVERSION")
    como_owner(admin, contexto.owner_user_id, "INSERT INTO gapto.hecho_entidades (id, owner_user_id, hecho_id, entidad_id, "
               "tipo_relacion, principal) VALUES (%s, %s, %s, %s, 'RELACIONADO_CON', false)",
               (uuid.uuid4(), contexto.owner_user_id, g.hecho, entidad))
    antes = estado6(admin, g)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, importe=D("47.82"))
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "INVERSION")
    sin_cambios(admin, g, antes)


def _compuesto(op22, contexto, cuenta, efectos: list[str], pagos: list[str]) -> Gasto:
    total = sum(D(i) for i in efectos)
    h = DatosCreacionHecho(hecho_id=uuid.uuid4(), fecha_hecho=FECHA, moneda="EUR", presupuestable=True,
                           estado_localizacion="DESCONOCIDA", tipo_hecho_codigo="GASTO", importe_total=total)
    efs = [DatosEfecto(efecto_id=uuid.uuid4(), tipo_efecto="GASTO", importe_delta=D(i),
                       estado_atribucion="NO_DISPONIBLE") for i in efectos]
    movs = [DatosMovimiento(movimiento_id=uuid.uuid4(), cuenta_id=cuenta, fecha_movimiento=FECHA,
                            importe=-D(i), clase_movimiento="OPERACION") for i in pagos]
    concs = [DatosConciliacion(uuid.uuid4(), h.hecho_id, m.movimiento_id, m.importe) for m in movs]
    op22.registrar_hecho_compuesto(nuevo(contexto), DatosHechoCompuesto(
        hecho=h, efectos=efs, pagos=[DatosPagoCompuesto(movimiento=m, conciliacion=c) for m, c in zip(movs, concs)]))
    return Gasto(h.hecho_id, efs[0].efecto_id, movs[0].movimiento_id, concs[0].conciliacion_id, cuenta, [], [])


def test_e1_varios_efectos_fuera_de_v1(op22, op21, contexto, admin, cuenta):
    g = _compuesto(op22, contexto, cuenta, ["30.0000", "18.7200"], ["48.7200"])
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, importe=D("47.82"))
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "TIPO_NO_SOPORTADO")


def test_e2_varios_movimientos_fuera_de_v1(op22, op21, contexto, admin, cuenta):
    g = _compuesto(op22, contexto, cuenta, ["48.7200"], ["30.0000", "18.7200"])
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, importe=D("47.82"))
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "VARIOS_MOVIMIENTOS")


def test_e5_multidivisa_fuera_de_v1(op22, op21, contexto, admin, cuenta_usd):
    g = gasto(op22, contexto, cuenta_usd)
    antes = estado6(admin, g)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, importe=D("47.82"))
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "MULTIDIVISA")
    sin_cambios(admin, g, antes)


def test_bajar_la_compra_por_debajo_de_lo_devuelto(op22, op21, servicio_devoluciones, contexto, admin, cuenta):
    g = gasto(op22, contexto, cuenta, "120.0000")
    servicio_devoluciones.devolver(nuevo(contexto), datos_devolucion(g.hecho, importe=D("45.0000"),
                                                                     fecha_hecho=F("2027-06-02")))
    antes = estado6(admin, g)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir(op21, contexto, admin, g, importe=D("40.00"))
    rechazo(excinfo, CodigoError.EXCEDE_CAPACIDAD_REVERSIBLE)
    sin_cambios(admin, g, antes)
    corregir(op21, contexto, admin, g, importe=D("45.00"))


def test_op21t_sobre_un_gasto_no_aplica(op22, op21, contexto, admin, cuenta):
    g = gasto(op22, contexto, cuenta)
    t = Transf(g.hecho, g.movimiento, g.movimiento, cuenta, cuenta)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir_t(op21, contexto, admin, t, fecha=F("2027-06-02"))
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "TIPO_NO_SOPORTADO")


def test_op21t_con_reversion_de_una_pata(servicio_transferencias, servicio_tesoreria, op21, contexto, admin, cuenta,
                                         cuenta_destino):
    t = transferencia(servicio_transferencias, contexto, cuenta, cuenta_destino)
    servicio_tesoreria.revertir_movimiento(nuevo(contexto), DatosReversion(
        reversion_id=uuid.uuid4(), movimiento_original_id=t.entrada, cuenta_id=cuenta_destino,
        fecha_movimiento=F("2027-06-10"), importe=D("10.00")))
    antes = patas(admin, t)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir_t(op21, contexto, admin, t, importe=D("90"))
    rechazo(excinfo, CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO, "REVERSION_EXISTENTE")
    assert patas(admin, t) == antes


def test_op21t_multidivisa_fuera_de_v1(servicio_transferencias, op21, contexto, admin, cuenta, cuenta_usd):
    t = transferencia(servicio_transferencias, contexto, cuenta, cuenta_usd)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir_t(op21, contexto, admin, t, fecha=F("2027-06-02"))
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "MULTIDIVISA")


@pytest.mark.parametrize("caso", ["deshabilitada", "periodo_cerrado"])
def test_op21t_cuenta_nueva_y_periodo(servicio_transferencias, op21, contexto, admin, cuenta, cuenta_destino, caso):
    owner = contexto.owner_user_id
    t = transferencia(servicio_transferencias, contexto, cuenta, cuenta_destino)
    nueva = _crear_cuenta(admin, owner)
    if caso == "deshabilitada":
        sql_admin(admin, "UPDATE gapto.cuentas SET enabled = false WHERE id = %s", (nueva,))
    else:
        cierre(admin, owner, "CERRADO", 1)
    antes = patas(admin, t)
    with pytest.raises(ErrorMotor) as excinfo:
        corregir_t(op21, contexto, admin, t, cuenta_destino_id=nueva)
    if caso == "deshabilitada":
        rechazo(excinfo, CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO, "CUENTA_DESACTIVADA")
    else:
        rechazo(excinfo, CodigoError.PERIODO_CERRADO_SIN_POLITICA)
    assert patas(admin, t) == antes


def test_op21t_t1_transferencia_sin_su_fila(servicio_transferencias, op21, contexto, admin, cuenta, cuenta_destino):
    """T-1: TRANSFERENCIA sin efectos pero sin su fila de `transferencias` (patas desemparejadas, nota de
    0320): no es una transferencia corregible."""
    t = transferencia(servicio_transferencias, contexto, cuenta, cuenta_destino)
    sql_admin(admin, "DELETE FROM gapto.transferencias WHERE movimiento_salida_id = %s", (t.salida,))
    with pytest.raises(ErrorMotor) as excinfo:
        corregir_t(op21, contexto, admin, t, fecha=F("2027-06-02"))
    rechazo(excinfo, CodigoError.CORRECCION_AGREGADA_REQUERIDA, "FUERA_DE_ALCANCE_V1", "TIPO_NO_SOPORTADO")
