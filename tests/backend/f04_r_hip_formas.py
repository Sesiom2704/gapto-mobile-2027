# ============================================================
# GAPTO MOBILE 2027
# Fichero: f04_r_hip_formas.py
# Ruta: tests/backend/f04_r_hip_formas.py
# Descripcion: Fixtures SINTETICOS de T3-F06 · F04-R-HIP (literal F04 v1.1
#   A2/A5/A9 y literal F05 v1.2) con la forma del contrato F06-01H v0.4
#   (§1.1, §3.2.3, §3.4), compartidos por tests/backend y tests/api:
#     - financiacion HIPOTECA con su cuota (financiacion_cuotas) y, si se pide,
#       la prevision MANUAL GASTO/SALIDA de la cuota (prevision_id);
#     - pago de una cuota: hecho GASTO con GASTO +intereses y DEUDA -capital,
#       con vinculo AFECTA_A de NIVEL EFECTO a la financiacion sobre la DEUDA y,
#       si se pide, movimiento -cuota conciliado entero;
#     - desembolso Hd: hecho GENERACION_DERECHO_OBLIGACION con DEUDA +P,
#       vinculo AFECTA_A de nivel efecto y, si se pide, movimiento +P conciliado;
#     - forma V3 (PC-HIP-10): HIPOTECA sin cuadro y apertura indeterminada
#       (saldo_principal_apertura y fecha_inicio_seguimiento NULL) con un hecho
#       DEUDA importado (mapeos_importacion) vinculado a nivel efecto.
#   Hechos, efectos, movimientos y conciliaciones se crean por los SERVICIOS
#   del motor como gapto_runtime; el vinculo de nivel efecto, la financiacion,
#   la cuota y el mapeo V3 se escriben bajo gapto_owner (el writer propio de
#   la hipoteca es de F06-01H; la ruta generica lo rechaza con OWNERSHIP_F07).
#   Datos sinteticos; base desechable. Fechas fijas.
# Version: 0.2.0 (F06 T3-F06 bloque 2 F06-01H; AJ-T3C-04, mandato v1.1 §5.2): cuadro coherente con
#   INV-0354-G2: la cuota 1 (CAPITAL, la que usan los tests) no cambia y una cuota 2 sin prevision
#   completa Σ capital_previsto = P; tipo, Hd, vinculos e importes de los efectos sin cambio.
# Version: 0.1.0 (F06 T3-F06 · F04-R-HIP)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from dataclasses import dataclass

import psycopg

D = decimal.Decimal
FECHA = dt.date(2026, 6, 1)
CUOTA = D("500.0000")
INTERES = D("100.0000")
CAPITAL = D("400.0000")
P = D("120000.0000")


@dataclass(frozen=True)
class Forma:
    hecho_id: uuid.UUID
    efecto_deuda: uuid.UUID
    efecto_gasto: uuid.UUID | None
    vinculo_id: uuid.UUID
    entidad_id: uuid.UUID
    movimiento_id: uuid.UUID | None
    version: int


def como_owner(dsn: str, owner: uuid.UUID, sentencias: list[tuple[str, tuple]]) -> None:
    """Sentencias en UNA transaccion bajo gapto_owner con el tenant fijado."""
    with psycopg.connect(dsn) as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute("SET LOCAL ROLE gapto_owner")
            cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
            for sql, params in sentencias:
                cur.execute(sql, params)


def version(dsn: str, owner: uuid.UUID, hecho_id: uuid.UUID) -> int:
    with psycopg.connect(dsn) as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute("SET LOCAL ROLE gapto_owner")
            cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
            cur.execute("SELECT row_version FROM gapto.hechos_financieros WHERE id = %s", (hecho_id,))
            return cur.fetchone()[0]


def financiacion(dsn: str, owner: uuid.UUID, *, prevision_id: uuid.UUID | None = None,
                 v3: bool = False) -> tuple[uuid.UUID, uuid.UUID]:
    """(entidad_id, cuota_id). v3: HIPOTECA sin cuadro y apertura indeterminada
    (la cuota no se crea; cuota_id es None)."""
    entidad_id, cuota_id = uuid.uuid4(), uuid.uuid4()
    sentencias = [
        ("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
         "VALUES (%s, %s, 'FINANCIACION', 'Hipoteca sintetica')", (entidad_id, owner)),
    ]
    if v3:
        sentencias.append(("INSERT INTO gapto.financiaciones (entidad_id, tipo_financiacion, moneda) "
                           "VALUES (%s, 'HIPOTECA', 'EUR')", (entidad_id,)))
        como_owner(dsn, owner, sentencias)
        return entidad_id, None
    sentencias += [
        ("INSERT INTO gapto.financiaciones (entidad_id, tipo_financiacion, moneda, capital_original_contratado, "
         "saldo_principal_apertura, fecha_inicio_seguimiento, fecha_inicio) "
         "VALUES (%s, 'HIPOTECA', 'EUR', %s, 0, %s, %s)", (entidad_id, P, FECHA, FECHA)),
        ("INSERT INTO gapto.financiacion_cuotas (id, financiacion_entidad_id, numero_cuota, fecha_vencimiento, "
         "capital_previsto, interes_previsto, comisiones_previstas, importe_total_previsto, prevision_id) "
         "VALUES (%s, %s, 1, %s, %s, %s, 0, %s, %s)",
         (cuota_id, entidad_id, FECHA, CAPITAL, INTERES, CUOTA, prevision_id)),
        ("INSERT INTO gapto.financiacion_cuotas (id, financiacion_entidad_id, numero_cuota, fecha_vencimiento, "
         "capital_previsto, interes_previsto, comisiones_previstas, importe_total_previsto) "
         "VALUES (%s, %s, 2, %s, %s, 0, 0, %s)",
         (uuid.uuid4(), entidad_id, dt.date(2026, 7, 1), P - CAPITAL, P - CAPITAL)),
    ]
    como_owner(dsn, owner, sentencias)
    return entidad_id, cuota_id


def vincular_nivel_efecto(dsn: str, owner: uuid.UUID, hecho_id: uuid.UUID, efecto_id: uuid.UUID | None,
                          entidad_id: uuid.UUID) -> uuid.UUID:
    """Vinculo AFECTA_A a la financiacion (de nivel efecto; efecto_id None = nivel hecho)."""
    vinculo_id = uuid.uuid4()
    como_owner(dsn, owner, [(
        "INSERT INTO gapto.hecho_entidades (id, hecho_id, efecto_id, entidad_id, tipo_relacion, principal, "
        "owner_user_id) VALUES (%s, %s, %s, %s, 'AFECTA_A', %s, %s)",
        (vinculo_id, hecho_id, efecto_id, entidad_id, efecto_id is None, owner))])
    return vinculo_id


def _tesoreria(unidad, contexto, hecho_id, cuenta_id, importe, version_hecho,
               fecha: dt.date = FECHA) -> tuple[uuid.UUID, int]:
    from app.core.modelos_tesoreria import DatosConciliacion, DatosMovimiento
    from app.services.tesoreria_service import TesoreriaService

    tes = TesoreriaService(unidad)
    movimiento_id = uuid.uuid4()
    m = tes.registrar_movimiento(contexto, DatosMovimiento(
        movimiento_id=movimiento_id, cuenta_id=cuenta_id, fecha_movimiento=fecha, importe=importe,
        clase_movimiento="OPERACION", descripcion="sintetico F04-R-HIP"))
    r = tes.conciliar(contexto, DatosConciliacion(
        conciliacion_id=uuid.uuid4(), hecho_id=hecho_id, movimiento_tesoreria_id=movimiento_id,
        importe_asignado=importe), hecho_row_version_esperada=version_hecho,
        movimiento_row_version_esperada=m.row_version)
    return movimiento_id, r.hecho_row_version


def _hecho(unidad, contexto, tipo: str, total: D, presupuestable: bool, fecha: dt.date = FECHA):
    from app.core.modelos import DatosCreacionHecho
    from app.services.hechos_service import HechosService
    from app.services.previsiones_service import impacto_correccion_ancla

    hecho_id = uuid.uuid4()
    r = HechosService(unidad, impacto_ancla=impacto_correccion_ancla).crear_hecho(contexto, DatosCreacionHecho(
        hecho_id=hecho_id, fecha_hecho=fecha, moneda="EUR", presupuestable=presupuestable,
        estado_localizacion="DESCONOCIDA", tipo_hecho_codigo=tipo, concepto=f"sintetico {tipo}",
        importe_total=total))
    return hecho_id, r.row_version


def cuota_pagada(dsn: str, unidad, contexto, owner: uuid.UUID, entidad_id: uuid.UUID, *,
                 cuenta_id: uuid.UUID | None = None, actor_id: uuid.UUID | None = None,
                 vincular: bool = True, fecha: dt.date = FECHA,
                 categoria_id: uuid.UUID | None = None) -> Forma:
    """Pago de una cuota (contrato v0.4 §3.4): GASTO +intereses, DEUDA -capital
    vinculada a nivel efecto; movimiento -cuota conciliado si hay cuenta."""
    from app.core.modelos_efectos import DatosAtribucion, DatosEfecto
    from app.services.efectos_service import EfectosService

    hecho_id, v = _hecho(unidad, contexto, "GASTO", CUOTA, True, fecha)
    gasto, deuda = uuid.uuid4(), uuid.uuid4()
    atribuciones = () if actor_id is None else (DatosAtribucion(
        atribucion_id=uuid.uuid4(), actor_id=actor_id, importe_atribuido=INTERES, criterio_atribucion="MANUAL"),)
    r = EfectosService(unidad).registrar_efectos(contexto, hecho_id=hecho_id, row_version_esperada=v, efectos=[
        DatosEfecto(efecto_id=gasto, tipo_efecto="GASTO", importe_delta=INTERES, categoria_id=categoria_id,
                    estado_atribucion="NO_DISPONIBLE" if actor_id is None else "COMPLETA", atribuciones=atribuciones),
        DatosEfecto(efecto_id=deuda, tipo_efecto="DEUDA", importe_delta=-CAPITAL, estado_atribucion="NO_DISPONIBLE"),
    ], presupuestable=True)
    v = r.row_version
    movimiento_id = None
    if cuenta_id is not None:
        movimiento_id, v = _tesoreria(unidad, contexto, hecho_id, cuenta_id, -CUOTA, v, fecha)
    vinculo = vincular_nivel_efecto(dsn, owner, hecho_id, deuda, entidad_id) if vincular else None
    return Forma(hecho_id, deuda, gasto, vinculo, entidad_id, movimiento_id, version(dsn, owner, hecho_id))


def desembolso_hd(dsn: str, unidad, contexto, owner: uuid.UUID, entidad_id: uuid.UUID, *,
                  cuenta_id: uuid.UUID | None = None) -> Forma:
    """Hd (contrato v0.4 §3.2.3-5, §3.2.7-9 propuesta): GENERACION_DERECHO_OBLIGACION
    con DEUDA +P vinculada a nivel efecto; movimiento +P conciliado si hay cuenta."""
    from app.core.modelos_efectos import DatosEfecto
    from app.services.efectos_service import EfectosService

    hecho_id, v = _hecho(unidad, contexto, "GENERACION_DERECHO_OBLIGACION", P, False)
    deuda = uuid.uuid4()
    r = EfectosService(unidad).registrar_efectos(contexto, hecho_id=hecho_id, row_version_esperada=v, efectos=[
        DatosEfecto(efecto_id=deuda, tipo_efecto="DEUDA", importe_delta=P, estado_atribucion="NO_DISPONIBLE"),
    ])
    v = r.row_version
    movimiento_id = None
    if cuenta_id is not None:
        movimiento_id, v = _tesoreria(unidad, contexto, hecho_id, cuenta_id, P, v)
    vinculo = vincular_nivel_efecto(dsn, owner, hecho_id, deuda, entidad_id)
    return Forma(hecho_id, deuda, None, vinculo, entidad_id, movimiento_id, version(dsn, owner, hecho_id))


def gasto_ordinario(dsn: str, unidad, contexto, owner: uuid.UUID, *, cuenta_id: uuid.UUID | None = None,
                    entidad_nivel_hecho: uuid.UUID | None = None) -> Forma:
    """Control: GASTO ordinario (un efecto GASTO). Con entidad_nivel_hecho, vinculo
    FINANCIACION de NIVEL HECHO (no ampliacion)."""
    from app.core.modelos_efectos import DatosEfecto
    from app.services.efectos_service import EfectosService

    hecho_id, v = _hecho(unidad, contexto, "GASTO", CUOTA, True)
    gasto = uuid.uuid4()
    r = EfectosService(unidad).registrar_efectos(contexto, hecho_id=hecho_id, row_version_esperada=v, efectos=[
        DatosEfecto(efecto_id=gasto, tipo_efecto="GASTO", importe_delta=CUOTA, estado_atribucion="NO_DISPONIBLE"),
    ], presupuestable=True)
    v = r.row_version
    movimiento_id = None
    if cuenta_id is not None:
        movimiento_id, v = _tesoreria(unidad, contexto, hecho_id, cuenta_id, -CUOTA, v)
    vinculo = None
    if entidad_nivel_hecho is not None:
        vinculo = vincular_nivel_efecto(dsn, owner, hecho_id, None, entidad_nivel_hecho)
    return Forma(hecho_id, None, gasto, vinculo, entidad_nivel_hecho, movimiento_id, version(dsn, owner, hecho_id))


def foto(dsn: str, owner: uuid.UUID, hecho_id: uuid.UUID, prevision_id: uuid.UUID | None = None,
         cuota_id: uuid.UUID | None = None) -> dict:
    """Estado del agregado para el oraculo «estado identico» (orden explicito)."""
    consultas = {
        "hecho": ("SELECT estado, row_version, importe_total FROM gapto.hechos_financieros WHERE id = %s", (hecho_id,)),
        "efectos": ("SELECT id, tipo_efecto, importe_delta, estado_atribucion FROM gapto.hecho_efectos "
                    "WHERE hecho_id = %s ORDER BY id", (hecho_id,)),
        "atribuciones": ("SELECT a.id, a.importe_atribuido FROM gapto.efecto_atribuciones a JOIN gapto.hecho_efectos e "
                         "ON e.id = a.efecto_id WHERE e.hecho_id = %s ORDER BY a.id", (hecho_id,)),
        "vinculos": ("SELECT id, efecto_id, entidad_id, tipo_relacion FROM gapto.hecho_entidades WHERE hecho_id = %s "
                     "ORDER BY id", (hecho_id,)),
        "conciliaciones": ("SELECT id, movimiento_tesoreria_id, importe_asignado FROM gapto.hecho_movimientos_tesoreria "
                           "WHERE hecho_id = %s ORDER BY id", (hecho_id,)),
        "aportaciones": ("SELECT id, importe FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s ORDER BY id",
                         (hecho_id,)),
        "movimientos": ("SELECT m.id, m.estado, m.row_version, m.importe FROM gapto.movimientos_tesoreria m "
                        "JOIN gapto.hecho_movimientos_tesoreria c ON c.movimiento_tesoreria_id = m.id "
                        "WHERE c.hecho_id = %s ORDER BY m.id", (hecho_id,)),
        "relaciones": ("SELECT id, tipo_relacion FROM gapto.hecho_relaciones WHERE hecho_origen_id = %s "
                       "OR hecho_destino_id = %s ORDER BY id", (hecho_id, hecho_id)),
        "prevision_hechos": ("SELECT id, prevision_id, importe_asignado FROM gapto.prevision_hechos WHERE hecho_id = %s "
                             "ORDER BY id", (hecho_id,)),
        "auditoria": ("SELECT count(*) FROM gapto.auditoria WHERE registro_id = %s", (hecho_id,)),
    }
    if prevision_id is not None:
        consultas["prevision"] = ("SELECT estado, row_version FROM gapto.previsiones WHERE id = %s", (prevision_id,))
        consultas["auditoria_prevision"] = ("SELECT count(*) FROM gapto.auditoria WHERE registro_id = %s",
                                            (prevision_id,))
    if cuota_id is not None:
        consultas["cuota"] = ("SELECT numero_cuota, prevision_id, importe_total_previsto FROM gapto.financiacion_cuotas "
                              "WHERE id = %s", (cuota_id,))
    salida = {}
    with psycopg.connect(dsn) as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute("SET LOCAL ROLE gapto_owner")
            cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
            for k, (sql, params) in consultas.items():
                cur.execute(sql, params)
                salida[k] = cur.fetchall()
    return salida


def marcar_v3(dsn: str, owner: uuid.UUID, hecho_id: uuid.UUID) -> None:
    """Procedencia V3 sintetica del hecho (patron f05_06_m2_helpers.marcar_v3)."""
    fuente, origen = uuid.uuid4(), uuid.uuid4()
    como_owner(dsn, owner, [
        ("INSERT INTO gapto.fuentes_importacion (id, owner_user_id, tipo_fuente, nombre_fuente) "
         "VALUES (%s, %s, 'DB', 'V3 sintetica')", (fuente, owner)),
        ("INSERT INTO gapto.registros_origen_importacion (id, fuente_importacion_id, contenedor_origen, "
         "clave_origen, datos_origen) VALUES (%s, %s, 'public.prestamos', %s, '{}'::jsonb)",
         (origen, fuente, str(hecho_id))),
        ("INSERT INTO gapto.mapeos_importacion (registro_origen_id, tabla_destino, registro_destino_id, "
         "tipo_mapping, confianza) VALUES (%s, 'hechos_financieros', %s, 'CREADO', 'ALTA')", (origen, hecho_id)),
    ])
