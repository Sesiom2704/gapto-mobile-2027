# ============================================================
# GAPTO MOBILE 2027
# Fichero: f05_06_m5_helpers.py
# Ruta: tests/api/f05_06_m5_helpers.py
# Descripcion: Helpers de los tests de F05-06 M5 (confirmacion de
#   previsiones): previsiones por SERVICIO (crear_manual; regla RODANTE con
#   ReglasService + generar_rodante, solo en fixtures), cuerpos de las rutas
#   de prevision y del registro con bloque `prevision`, y lecturas fisicas
#   como gapto_runtime. Datos sinteticos (M5-RULE-01: recibos, compra
#   singular, importe desconocido, ingreso, transferencia y RODANTE; nunca
#   consumo generico); base desechable. Reloj fijo 2026-10-10 (Madrid).
# Version: 0.1.0 (F05-06 M5 §A6)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid

import f05_01_helpers as fh
import f05_05_helpers as x
import vs01_api_helpers as h

D = decimal.Decimal
F = dt.date.fromisoformat
HOY = dt.date(2026, 10, 10)
GASTO = x.GASTO
INGRESO = x.INGRESO
TRANSF = x.TRANSF
COMPARTIDO = "/v1/intenciones/gasto-compartido"
INICIO = "/v1/inicio/previsiones"
PENDIENTES = "/v1/previsiones/pendientes"
RESULTADO = "/v1/inicio/resultado-mes"
FLUJO = {"GASTO": "SALIDA", "INGRESO": "ENTRADA", "TRANSFERENCIA": "TRANSFERENCIA"}


def entorno(iso: str = "2026-10-10T12:00:00"):
    """(owner, actor_self, cliente, cuenta corriente, cuenta ahorro)."""
    return x.entorno(iso)


def ctx(owner):
    from app.core.contexto import ContextoOperacion

    return ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4())


def prevision(owner, concepto: str, *, tipo: str = "GASTO", desde: str = "2026-10-01", hasta: str | None = None,
              importe: str | None = "74.00", tercero=None, categoria=None, cuenta_salida=None, cuenta_entrada=None,
              moneda: str = "EUR", prevision_id=None) -> uuid.UUID:
    """Prevision manual ABIERTA por OP de servicio (crear_manual), nunca SQL."""
    from app.core.modelos_prevision import DatosPrevisionManual
    from app.services.previsiones_service import PrevisionesService

    pid = prevision_id or uuid.uuid4()
    PrevisionesService(fh.unidad()).crear_manual(ctx(owner), DatosPrevisionManual(
        prevision_id=pid, concepto=concepto, tipo_hecho_codigo=tipo, fecha_esperada_desde=F(desde),
        fecha_esperada_hasta=F(hasta or desde), flujo_tesoreria_esperado=FLUJO[tipo], moneda=moneda,
        presupuestable=tipo != "TRANSFERENCIA", categoria_id=categoria, tercero_id=tercero,
        cuenta_salida_esperada_id=cuenta_salida, cuenta_entrada_esperada_id=cuenta_entrada,
        importe_esperado=None if importe is None else D(importe)))
    return pid


def rodante(owner, nombre: str = "Seguro coche", *, desde: str = "2026-09-20", importe: str = "45.00",
            cuenta_salida=None, tercero=None) -> tuple[uuid.UUID, uuid.UUID]:
    """Regla RODANTE mensual con su cabeza (solo fixture de tests; M6 pospuesto). (regla, cabeza)."""
    from app.core.modelos_prevision import Cadencia, DatosRegla, DatosVersionRegla, MENSUAL, RODANTE
    from app.services.previsiones_service import PrevisionesService
    from app.services.reglas_service import ReglasService

    regla, cabeza = uuid.uuid4(), uuid.uuid4()
    version = DatosVersionRegla(
        version_id=uuid.uuid4(), vigente_desde=F(desde), vigente_hasta=None, tipo_hecho_codigo="GASTO",
        flujo_tesoreria_esperado="SALIDA", moneda="EUR", fecha_modo="ANCLA", importe_modo="FIJO",
        presupuestable=True, cadencia=Cadencia(MENSUAL, 1, RODANTE), importe_fijo=D(importe),
        cuenta_salida_esperada_id=cuenta_salida, tercero_id=tercero)
    ReglasService(fh.unidad()).crear_regla(ctx(owner), DatosRegla(regla_id=regla, nombre=nombre), version)
    PrevisionesService(fh.unidad()).generar_rodante(ctx(owner), regla_id=regla, uuid_nuevo=cabeza)
    return regla, cabeza


# ------------------------------------------------------------------ lecturas HTTP
def detalle(cli, pid) -> dict:
    r = cli.get(f"/v1/previsiones/{pid}", headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def inicio(cli) -> dict:
    r = cli.get(INICIO, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def pendientes(cli) -> dict:
    r = cli.get(PENDIENTES, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def candidatos(cli, pid, ampliado: bool = False) -> dict:
    r = cli.get(f"/v1/previsiones/{pid}/candidatos", params={"ampliado": str(ampliado).lower()}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def resultado(cli, fecha: str = "2026-10-10") -> dict:
    r = cli.get(RESULTADO, params={"fecha": fecha}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def version(owner, pid) -> int:
    return uno(owner, "SELECT row_version FROM gapto.previsiones WHERE id = %s", (pid,))[0]


# ------------------------------------------------------------------ escrituras HTTP
def bloque(owner, pid, marcar, row_version=None) -> dict:
    b = {"prevision_id": str(pid), "row_version": row_version or version(owner, pid)}
    if marcar is not None:
        b["marcar_realizada"] = marcar
    return b


def vincular(cli, owner, pid, hecho, importe: str, marcar=True, *, row_version=None, intencion_id=None):
    c = {"intencion_id": str(intencion_id or uuid.uuid4()), "row_version": row_version or version(owner, pid),
         "hecho_id": str(hecho), "importe_a_vincular": importe}
    if marcar is not None:
        c["marcar_realizada"] = marcar
    return c, cli.post(f"/v1/previsiones/{pid}/vincular", json=c, headers=h.AUTH)


def omitir(cli, owner, pid, *, row_version=None, intencion_id=None, motivo=None):
    c = {"intencion_id": str(intencion_id or uuid.uuid4()), "row_version": row_version or version(owner, pid),
         "motivo": motivo}
    return c, cli.post(f"/v1/previsiones/{pid}/omitir", json=c, headers=h.AUTH)


def gasto_desde(cli, owner, cuenta, pid, importe: str, marcar=True, *, fecha="2026-10-07", row_version=None,
                intencion_id=None, tercero=None, categoria=None):
    c = h.intencion(cuenta, fecha_hecho=fecha, importe=importe, concepto=None,
                    intencion_id=str(intencion_id or uuid.uuid4()), categoria=x._cat(categoria))
    if tercero is not None:
        c["tercero_id"] = str(tercero)
    c["prevision"] = bloque(owner, pid, marcar, row_version)
    return c, cli.post(GASTO, json=c, headers=h.AUTH)


def ingreso_desde(cli, owner, cuenta, pid, importe: str, marcar=True, *, fecha="2026-10-07", row_version=None,
                  intencion_id=None, tercero=None):
    c = {"intencion_id": str(intencion_id or uuid.uuid4()), "importe": importe, "moneda": "EUR",
         "fecha_hecho": fecha, "cuenta_id": str(cuenta), "presupuestable": True, "atribucion": "SOLO_MIO",
         "categoria": {"estado": "SIN_CATEGORIA"}, "nota": None}
    if tercero is not None:
        c["tercero_id"] = str(tercero)
    c["prevision"] = bloque(owner, pid, marcar, row_version)
    return c, cli.post(INGRESO, json=c, headers=h.AUTH)


def transferencia_desde(cli, owner, origen, destino, pid, importe: str, marcar=True, *, fecha="2026-10-07",
                        row_version=None, intencion_id=None, nota=None):
    c = {"intencion_id": str(intencion_id or uuid.uuid4()), "importe": importe, "moneda": "EUR",
         "fecha_hecho": fecha, "cuenta_origen_id": str(origen), "cuenta_destino_id": str(destino), "nota": nota,
         "prevision": bloque(owner, pid, marcar, row_version)}
    return c, cli.post(TRANSF, json=c, headers=h.AUTH)


# ------------------------------------------------------------------ lecturas fisicas (gapto_runtime)
def leer(owner, sql: str, params: tuple = ()) -> list[tuple]:
    return h.leer(owner, sql, params)


def uno(owner, sql: str, params: tuple = ()):
    filas = h.leer(owner, sql, params)
    return filas[0] if filas else None


def estado(owner, pid) -> str:
    return uno(owner, "SELECT estado FROM gapto.previsiones WHERE id = %s", (pid,))[0]


def vinculos(owner, pid) -> list[tuple]:
    """(hecho_id, importe_asignado) de los vinculos de la prevision."""
    return sorted(leer(owner, "SELECT hecho_id, importe_asignado FROM gapto.prevision_hechos WHERE prevision_id = %s",
                       (pid,)), key=str)


def previsiones_de_regla(owner, regla) -> list[tuple]:
    """(id, estado, fecha_objetivo_regla) de la cadena, por fecha objetivo."""
    return leer(owner, "SELECT p.id, p.estado, p.fecha_objetivo_regla FROM gapto.previsiones p "
                       "JOIN gapto.regla_versiones v ON v.id = p.regla_version_id WHERE v.regla_id = %s "
                       "ORDER BY p.fecha_objetivo_regla", (regla,))


def huella(owner) -> tuple:
    """Recuentos de todo lo que M5 podria escribir (oraculo «sin efectos»)."""
    return tuple(uno(owner, f"SELECT count(*) FROM gapto.{t}")[0] for t in (
        "hechos_financieros", "hecho_efectos", "efecto_atribuciones", "movimientos_tesoreria",
        "hecho_movimientos_tesoreria", "transferencias", "prevision_hechos", "previsiones", "auditoria"))


def auditoria_de(owner, request_id) -> int:
    return uno(owner, "SELECT count(*) FROM gapto.auditoria WHERE request_id = %s", (request_id,))[0]


def movimientos(owner, hecho) -> list[tuple]:
    """(cuenta_id, importe) de los movimientos conciliados con el hecho."""
    return sorted(leer(owner, "SELECT m.cuenta_id, m.importe FROM gapto.hecho_movimientos_tesoreria hm "
                              "JOIN gapto.movimientos_tesoreria m ON m.id = hm.movimiento_tesoreria_id "
                              "WHERE hm.hecho_id = %s", (hecho,)), key=str)


def efectos(owner, hecho) -> list[tuple]:
    return sorted(leer(owner, "SELECT tipo_efecto, importe_delta FROM gapto.hecho_efectos WHERE hecho_id = %s",
                       (hecho,)), key=str)


def saldo(owner, cuenta) -> D:
    return uno(owner, "SELECT COALESCE(sum(importe), 0) FROM gapto.movimientos_tesoreria WHERE cuenta_id = %s",
               (cuenta,))[0]
