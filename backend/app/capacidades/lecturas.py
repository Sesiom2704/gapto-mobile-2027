# ============================================================
# GAPTO MOBILE 2027
# Fichero: lecturas.py
# Ruta: backend/app/capacidades/lecturas.py
# Descripcion: Lecturas de capacidades de cuenta (F05-06 M4 §2.2; F09
#   §12.105 CAP A1/A2/A4/B1/B2/B4). Solo lectura, bajo gapto_runtime y RLS
#   del tenant, SIN locks. API DE INTEGRACION F05, PENDIENTE DE
#   CONSOLIDACION F10.
#
#   - `lista`: cuentas del owner (orden, nombre, id) con lo que pueden hacer.
#     `sin_configurar` = ninguna de las cuatro capacidades del registro
#     (D-CAP-05, H2). `origen_v3` (PD-4): la cuenta tiene un mapeo de RV3 en
#     gapto.mapeos_importacion (tabla_destino 'cuentas'), legible por
#     gapto_runtime con RLS; sin DDL. No se devuelve el tipo de cuenta: nada
#     se deduce ni se propone por tipo, naturaleza o nombre (D-CAP-04).
#   - `detalle`: las cuatro capacidades del registro con su efecto, «Otras»
#     (COMPRA_TARJETA, DOMICILIAR) en solo lectura y `row_version` de la
#     cuenta (PD-1). Capacidad ausente = no permitida (H2).
#   - `impacto`: plantillas y preferencias del owner que usan la cuenta para
#     la operacion de la capacidad y que pasarian a «No disponible» al
#     desactivarla. Misma regla que sus lecturas: la plantilla no tiene hoy
#     aviso de cuenta (plantillas.lecturas) y la preferencia tiene
#     cuenta_disponible_hoy (preferencias.lecturas); ambas usan el contrato
#     unico motivo_cuenta. Las capacidades de transferencia no tienen
#     plantillas ni preferencias (son solo de GASTO e INGRESO).
#   - `historial`: entradas de gapto.auditoria del writer de capacidades de
#     esa cuenta (que, cuando, quien), de la mas reciente a la mas antigua.
#     No se inventan entradas: si RV3 no dejo auditoria, no aparece nada de
#     V3. No es un versionado temporal completo (AJ-F0506P-09).
#   - `sin_configurar`: numero de cuentas habilitadas y sin cerrar que no
#     tienen ninguna capacidad del registro (aviso B2, D-CAP-06).
# Version: 0.1.0 (F05-06 M4 F1)
# ============================================================

from __future__ import annotations

import uuid
from typing import Any

from app.comun.fecha_funcional import Reloj, reloj_sistema
from app.core.unidad_trabajo import SesionMotor

#: Capacidad -> (etiqueta, efecto en el registro) (D-CAP-01; lamina CAP A2).
REGISTRO: dict[str, tuple[str, str]] = {
    "PAGAR_GASTO": ("Pagar gastos", "Aparece en «Pagado con»"),
    "RECIBIR_INGRESO": ("Recibir ingresos", "Aparece en «Cobrado en»"),
    "TRANSFERIR_SALIDA": ("Enviar a otras cuentas tuyas", "Aparece en «Desde»"),
    "TRANSFERIR_ENTRADA": ("Recibir de otras cuentas tuyas", "Aparece en «A»"),
}
#: Capacidades de solo lectura (P-CAP-02).
OTRAS: dict[str, tuple[str, str]] = {
    "COMPRA_TARJETA": ("Compras con tarjeta", "Aún no se usa en el registro"),
    "DOMICILIAR": ("Domiciliar recibos", "Aún no se usa en el registro"),
}
#: Capacidad -> operacion de plantillas y preferencias (solo GASTO e INGRESO).
OPERACION_PLANTILLAS = {"PAGAR_GASTO": "GASTO", "RECIBIR_INGRESO": "INGRESO"}
MOTIVOS_HISTORIAL = {"F05-06 CAPACIDAD ACTIVAR": "ACTIVAR", "F05-06 CAPACIDAD DESACTIVAR": "DESACTIVAR"}

_CUENTAS = (
    "SELECT c.id, c.nombre, c.enabled, c.fecha_cierre, c.row_version, "
    "ARRAY(SELECT k.capacidad_codigo FROM gapto.cuenta_capacidades k WHERE k.cuenta_id = c.id "
    "ORDER BY k.capacidad_codigo)::text[] AS capacidades, "
    "EXISTS (SELECT 1 FROM gapto.mapeos_importacion m WHERE m.tabla_destino = 'cuentas' "
    "AND m.registro_destino_id = c.id) AS origen_v3 "
    "FROM gapto.cuentas c WHERE c.owner_user_id = current_setting('gapto.owner_user_id')::uuid"
)


def _estado(enabled: bool, fecha_cierre) -> str:
    if fecha_cierre is not None:
        return "CERRADA"
    return "ACTIVA" if enabled else "DESHABILITADA"


def _cuenta(fila: tuple) -> dict[str, Any]:
    cid, nombre, enabled, fecha_cierre, row_version, capacidades, origen_v3 = fila
    tiene = set(capacidades)
    return {
        "cuenta_id": cid,
        "nombre": nombre,
        "estado": _estado(enabled, fecha_cierre),
        "row_version": row_version,
        "origen_v3": origen_v3,
        "sin_configurar": not (tiene & set(REGISTRO)),
        "capacidades": [{"codigo": c, "etiqueta": e, "efecto": f, "permitida": c in tiene, "editable": True}
                        for c, (e, f) in REGISTRO.items()],
        "otras": [{"codigo": c, "etiqueta": e, "efecto": f, "permitida": c in tiene, "editable": False}
                  for c, (e, f) in OTRAS.items()],
    }


def lista(sesion: SesionMotor) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(_CUENTAS + " ORDER BY c.orden, c.nombre, c.id")
        return [_cuenta(f) for f in cur.fetchall()]


def detalle(sesion: SesionMotor, cuenta_id: uuid.UUID) -> dict[str, Any] | None:
    fila = sesion.uno(_CUENTAS + " AND c.id = %s", (cuenta_id,))
    return None if fila is None else _cuenta(fila)


def contar_sin_configurar(cuentas: list[dict[str, Any]]) -> int:
    return sum(1 for c in cuentas if c["sin_configurar"] and c["estado"] == "ACTIVA")


def sin_configurar(sesion: SesionMotor) -> int:
    return contar_sin_configurar(lista(sesion))


def impacto(sesion: SesionMotor, cuenta_id: uuid.UUID, capacidad: str,
            reloj: Reloj = reloj_sistema) -> dict[str, list[dict[str, Any]]]:
    """Plantillas y preferencias que pasarian a «No disponible» (ver cabecera)."""
    from app.plantillas import lecturas as lect_plt
    from app.preferencias import lecturas as lect_pref
    from app.preferencias.resolver import operacion_de_tipo

    operacion = OPERACION_PLANTILLAS.get(capacidad)
    if operacion is None:
        return {"plantillas": [], "preferencias": []}
    plantillas = [
        {"plantilla_id": p["id"], "nombre": p["nombre"], "enabled": p["enabled"]}
        for p in lect_plt.listar(sesion, reloj)
        if p["cuenta_default_id"] == cuenta_id and p["tipo"] == operacion
        and not any(a["campo"] == "cuenta" for a in p["avisos"])
    ]
    preferencias = [
        {"preferencia_id": p["id"], "enabled": p["enabled"], "categoria_id": p["categoria_id"],
         "categoria_nombre": _nombre(sesion, "categorias_financieras", p["categoria_id"]),
         "tercero_id": p["tercero_id"], "tercero_nombre": _nombre(sesion, "terceros", p["tercero_id"])}
        for p in lect_pref.listar(sesion, reloj)
        if p["cuenta_default_id"] == cuenta_id and p["cuenta_disponible_hoy"]
        and operacion_de_tipo(sesion, p["tipo_hecho_id"]) == operacion
    ]
    return {"plantillas": plantillas, "preferencias": preferencias}


def _nombre(sesion: SesionMotor, tabla: str, ident) -> str | None:
    if ident is None:
        return None
    fila = sesion.uno(f"SELECT nombre FROM gapto.{tabla} WHERE id = %s "
                      "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid", (ident,))
    return None if fila is None else fila[0]


def historial(sesion: SesionMotor, cuenta_id: uuid.UUID) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT a.created_at, a.motivo, a.datos_despues->>'capacidad_codigo', a.actor_tipo, "
            "a.actor_user_id = a.owner_user_id "
            "FROM gapto.auditoria a WHERE a.tabla = 'cuentas' AND a.registro_id = %s AND a.motivo = ANY(%s) "
            "ORDER BY a.created_at DESC, a.id",
            (cuenta_id, list(MOTIVOS_HISTORIAL)),
        )
        filas = cur.fetchall()
    etiquetas = {**REGISTRO, **OTRAS}
    return [
        {"cuando": f[0], "accion": MOTIVOS_HISTORIAL[f[1]], "capacidad": f[2],
         "etiqueta": etiquetas.get(f[2], (f[2],))[0], "actor_tipo": f[3], "actor_es_owner": bool(f[4])}
        for f in filas
    ]
