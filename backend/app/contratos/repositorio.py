# ============================================================
# GAPTO MOBILE 2027
# Fichero: repositorio.py
# Ruta: backend/app/contratos/repositorio.py
# Descripcion: Acceso a datos de contratos, participantes, cláusula, servicios y terceros-hijas (F06-02/03).
#   SQL puro con psycopg. El owner NUNCA es parametro: GUC `gapto.owner_user_id`; la RLS hace el resto.
#   - Solo INSERT y UPDATE: gapto_runtime no tiene DELETE en estas tablas (0230, 0351). Toda retirada es
#     cerrar una vigencia con UPDATE.
#   - Ninguna funcion toca renta, reglas, previsiones ni OP-21 (guarda de no-composicion, VII.1).
#   - Este modulo esta FUERA de CAPA_F05 (test_182): el SQL de roles/clasificaciones de terceros vive aqui.
#   - row_version del contrato = `entidades.row_version`; la propiedad nunca sube su version desde aqui.
# Version: 0.1.0 (F06 T3-F06 Bloque 3, paso 3)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from app.core.unidad_trabajo import SesionMotor

OWNER = "current_setting('gapto.owner_user_id')::uuid"
COLUMNAS_CONTRATO = ("propiedad_id", "tipo_contrato", "estado_documental", "fecha_inicio", "fecha_fin_prevista",
                     "fecha_fin_real", "habitacion", "regla_renta_id", "notas", "nombre", "row_version", "enabled")
_COLS_CONTRATO = (
    "c.propiedad_entidad_id, c.tipo_contrato, c.estado_documental, c.fecha_inicio, c.fecha_fin_prevista, "
    "c.fecha_fin_real, c.habitacion, c.regla_renta_id, c.notas, e.nombre, e.row_version, e.enabled"
)
_SELECT_CONTRATO = (
    "SELECT " + _COLS_CONTRATO + " "
    "FROM gapto.contratos c JOIN gapto.entidades e ON e.id = c.entidad_id "
    f"WHERE c.entidad_id = %s AND e.tipo_entidad = 'CONTRATO' AND e.owner_user_id = {OWNER}"
)
#: Columnas de `contratos` que los writers pueden cambiar (jamas regla_renta_id, propiedad ni tipo).
COLUMNAS_EDITABLES_CONTRATO = frozenset({"fecha_inicio", "fecha_fin_prevista", "fecha_fin_real", "estado_documental",
                                         "habitacion", "notas"})
COLUMNAS_PARTICIPANTE = ("id", "actor_id", "tercero_id", "nombre", "rol", "principal", "vigente_desde",
                         "vigente_hasta")
COLUMNAS_CLAUSULA = ("id", "vigente_desde", "vigente_hasta", "tipo_revision", "indice_referencia",
                     "periodicidad_meses", "fecha_primera_revision", "porcentaje_fijo", "notas")
COLUMNAS_TRATAMIENTO = ("id", "servicio_id", "incluido_en_renta", "repercutible", "modo_reparto",
                        "actor_repercusion_id", "porcentaje_repercutible", "vigente_desde", "vigente_hasta")

_SNAPSHOT_CONTRATO = (
    "SELECT json_build_object('entidad', row_to_json(e), 'contrato', row_to_json(c), "
    "'participantes', (SELECT coalesce(json_agg(row_to_json(x) ORDER BY x.vigente_desde, x.id), '[]'::json) "
    "FROM gapto.contrato_participantes x WHERE x.contrato_entidad_id = e.id), "
    "'clausulas', (SELECT coalesce(json_agg(row_to_json(v) ORDER BY v.vigente_desde NULLS FIRST, v.id), '[]'::json) "
    "FROM gapto.contrato_revision_renta_versiones v WHERE v.contrato_entidad_id = e.id), "
    "'servicios', (SELECT coalesce(json_agg(row_to_json(s) ORDER BY s.vigente_desde, s.id), '[]'::json) "
    "FROM gapto.contrato_servicios s WHERE s.contrato_entidad_id = e.id))::text "
    "FROM gapto.entidades e JOIN gapto.contratos c ON c.entidad_id = e.id WHERE e.id = %s"
)


# SQL ESTATICO por tabla (sin SQL de tabla dinamica: test_154 I6). Lista cerrada; nunca DELETE.
_CIERRE = {
    "contrato_participantes": "UPDATE gapto.contrato_participantes SET vigente_hasta = %s WHERE id = ANY(%s)",
    "contrato_servicios": "UPDATE gapto.contrato_servicios SET vigente_hasta = %s WHERE id = ANY(%s)",
    "contrato_revision_renta_versiones":
        "UPDATE gapto.contrato_revision_renta_versiones SET vigente_hasta = %s WHERE id = ANY(%s)",
    "propiedad_servicios": "UPDATE gapto.propiedad_servicios SET vigente_hasta = %s WHERE id = ANY(%s)",
}
_MOVER = {
    ("contrato_participantes", "vigente_desde"):
        "UPDATE gapto.contrato_participantes SET vigente_desde = %s WHERE id = ANY(%s)",
    ("contrato_participantes", "vigente_hasta"):
        "UPDATE gapto.contrato_participantes SET vigente_hasta = %s WHERE id = ANY(%s)",
    ("contrato_servicios", "vigente_desde"):
        "UPDATE gapto.contrato_servicios SET vigente_desde = %s WHERE id = ANY(%s)",
    ("contrato_servicios", "vigente_hasta"):
        "UPDATE gapto.contrato_servicios SET vigente_hasta = %s WHERE id = ANY(%s)",
    ("contrato_revision_renta_versiones", "vigente_desde"):
        "UPDATE gapto.contrato_revision_renta_versiones SET vigente_desde = %s WHERE id = ANY(%s)",
    ("contrato_revision_renta_versiones", "vigente_hasta"):
        "UPDATE gapto.contrato_revision_renta_versiones SET vigente_hasta = %s WHERE id = ANY(%s)",
}


# ------------------------------------------------------------------ contratos
def contrato(sesion: SesionMotor, contrato_id: uuid.UUID, *, bloquear: bool = False) -> dict[str, Any] | None:
    """Contrato del owner. Con `bloquear`: FOR NO KEY UPDATE de la entidad (nivel 6 de §1.3)."""
    fila = sesion.uno(_SELECT_CONTRATO + (" FOR NO KEY UPDATE OF e" if bloquear else ""), (contrato_id,))
    return None if fila is None else dict(zip(COLUMNAS_CONTRATO, fila))


def bloquear_contratos(sesion: SesionMotor, ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
    """Contratos FOR NO KEY UPDATE por UUID ascendente (nivel 6). Los ausentes no figuran."""
    salida: dict[uuid.UUID, dict[str, Any]] = {}
    for cid in sorted(set(ids), key=str):
        fila = contrato(sesion, cid, bloquear=True)
        if fila is not None:
            salida[cid] = fila
    return salida


def contratos_de_propiedad(sesion: SesionMotor, propiedad_id: uuid.UUID) -> list[dict[str, Any]]:
    """TODOS los contratos de la propiedad (cualquier estado), con su nombre y version. Solo lectura."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT c.entidad_id, " + _COLS_CONTRATO + " "
            "FROM gapto.contratos c JOIN gapto.entidades e ON e.id = c.entidad_id "
            f"WHERE c.propiedad_entidad_id = %s AND e.tipo_entidad = 'CONTRATO' AND e.owner_user_id = {OWNER} "
            "ORDER BY c.fecha_inicio NULLS LAST, c.entidad_id", (propiedad_id,))
        return [dict(zip(("id",) + COLUMNAS_CONTRATO, f)) for f in cur.fetchall()]


def snapshot_contrato(sesion: SesionMotor, contrato_id: uuid.UUID) -> str:
    fila = sesion.uno(_SNAPSHOT_CONTRATO, (contrato_id,))
    assert fila is not None
    return fila[0]


def subir_version(sesion: SesionMotor, entidad_id: uuid.UUID) -> int:
    """Agregado contrato o servicio: `entidades.row_version + 1` (toda escritura en sus hijas)."""
    fila = sesion.uno(
        "UPDATE gapto.entidades SET row_version = row_version + 1, updated_at = now() WHERE id = %s "
        "RETURNING row_version", (entidad_id,))
    assert fila is not None
    return fila[0]


def insertar_contrato(sesion: SesionMotor, *, contrato_id: uuid.UUID, nombre: str, propiedad_id: uuid.UUID,
                      tipo: str, estado: str, fecha_inicio: dt.date | None, fecha_fin_prevista: dt.date | None,
                      habitacion: int | None, notas: str | None) -> None:
    """Entidad CONTRATO + subtipo. `regla_renta_id` NO se escribe: queda NULL (R-E-01; INV-ALQ-02)."""
    sesion.uno(
        "INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) VALUES (%s, "
        f"{OWNER}, 'CONTRATO', %s) RETURNING id", (contrato_id, nombre))
    sesion.uno(
        "INSERT INTO gapto.contratos (entidad_id, propiedad_entidad_id, tipo_contrato, estado_documental, "
        "fecha_inicio, fecha_fin_prevista, habitacion, notas) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
        "RETURNING entidad_id",
        (contrato_id, propiedad_id, tipo, estado, fecha_inicio, fecha_fin_prevista, habitacion, notas))


def actualizar_contrato(sesion: SesionMotor, contrato_id: uuid.UUID, cambios: dict[str, Any]) -> None:
    """UPDATE de nombre (entidad) y de columnas de `contratos` de una lista cerrada."""
    if "nombre" in cambios:
        sesion.ejecutar("UPDATE gapto.entidades SET nombre = %s, updated_at = now() WHERE id = %s",
                        (cambios["nombre"], contrato_id))
    columnas = sorted(set(cambios) - {"nombre"})
    if set(columnas) - COLUMNAS_EDITABLES_CONTRATO:
        raise ValueError(f"columnas no editables: {sorted(set(columnas) - COLUMNAS_EDITABLES_CONTRATO)}")
    if columnas:
        sesion.ejecutar(
            f"UPDATE gapto.contratos SET {', '.join(f'{c} = %s' for c in columnas)} WHERE entidad_id = %s",
            tuple(cambios[c] for c in columnas) + (contrato_id,))


# ------------------------------------------------------------------ participantes
def participantes(sesion: SesionMotor, contrato_id: uuid.UUID) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT p.id, p.actor_id, a.tercero_id, t.nombre, p.rol, p.principal, p.vigente_desde, p.vigente_hasta "
            "FROM gapto.contrato_participantes p JOIN gapto.actores_financieros a ON a.id = p.actor_id "
            "LEFT JOIN gapto.terceros t ON t.id = a.tercero_id WHERE p.contrato_entidad_id = %s "
            "ORDER BY p.vigente_desde, p.rol, p.id", (contrato_id,))
        return [dict(zip(COLUMNAS_PARTICIPANTE, f)) for f in cur.fetchall()]


def insertar_participante(sesion: SesionMotor, *, fila_id: uuid.UUID, contrato_id: uuid.UUID, actor_id: uuid.UUID,
                          rol: str, principal: bool, desde: dt.date, hasta: dt.date | None) -> None:
    sesion.uno(
        "INSERT INTO gapto.contrato_participantes (id, contrato_entidad_id, actor_id, rol, principal, "
        "vigente_desde, vigente_hasta) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (fila_id, contrato_id, actor_id, rol, principal, desde, hasta))


def actualizar_participante(sesion: SesionMotor, fila_id: uuid.UUID, cambios: dict[str, Any]) -> None:
    columnas = sorted(cambios)
    if not columnas or set(columnas) - {"vigente_desde", "vigente_hasta", "principal"}:
        raise ValueError("columnas de participante no editables")
    sesion.ejecutar(
        f"UPDATE gapto.contrato_participantes SET {', '.join(f'{c} = %s' for c in columnas)} WHERE id = %s",
        tuple(cambios[c] for c in columnas) + (fila_id,))


def cerrar_vigencia(sesion: SesionMotor, tabla: str, ids: list[uuid.UUID], hasta: dt.date) -> int:
    """Cierra (UPDATE vigente_hasta) las filas por id. Tablas de lista cerrada; nunca DELETE."""
    sql = _CIERRE.get(tabla)
    if sql is None or not ids:
        return 0
    return sesion.ejecutar(sql, (hasta, list(ids)))


def mover_vigencia(sesion: SesionMotor, tabla: str, ids: list[uuid.UUID], columna: str, fecha: dt.date) -> int:
    """UPDATE de `vigente_desde` o `vigente_hasta` de filas por id (errata auditada; lista cerrada)."""
    sql = _MOVER.get((tabla, columna))
    if sql is None or not ids:
        return 0
    return sesion.ejecutar(sql, (fecha, list(ids)))


# ------------------------------------------------------------------ clausula
def clausulas(sesion: SesionMotor, contrato_id: uuid.UUID) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, vigente_desde, vigente_hasta, tipo_revision, indice_referencia, periodicidad_meses, "
            "fecha_primera_revision, porcentaje_fijo, notas FROM gapto.contrato_revision_renta_versiones "
            "WHERE contrato_entidad_id = %s ORDER BY vigente_desde NULLS FIRST, id", (contrato_id,))
        return [dict(zip(COLUMNAS_CLAUSULA, f)) for f in cur.fetchall()]


def insertar_clausula(sesion: SesionMotor, *, fila_id: uuid.UUID, contrato_id: uuid.UUID, desde: dt.date,
                      hasta: dt.date | None, columnas: dict[str, Any]) -> None:
    sesion.uno(
        "INSERT INTO gapto.contrato_revision_renta_versiones (id, contrato_entidad_id, vigente_desde, "
        "vigente_hasta, tipo_revision, indice_referencia, periodicidad_meses, fecha_primera_revision, "
        "porcentaje_fijo, notas) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (fila_id, contrato_id, desde, hasta, columnas["tipo_revision"], columnas["indice_referencia"],
         columnas["periodicidad_meses"], columnas["fecha_primera_revision"], columnas["porcentaje_fijo"],
         columnas["notas"]))


def actualizar_clausula(sesion: SesionMotor, fila_id: uuid.UUID, cambios: dict[str, Any]) -> None:
    permitidas = {"vigente_desde", "vigente_hasta", "tipo_revision", "indice_referencia", "periodicidad_meses",
                  "fecha_primera_revision", "porcentaje_fijo", "notas"}
    columnas = sorted(cambios)
    if not columnas or set(columnas) - permitidas:
        raise ValueError("columnas de clausula no editables")
    sesion.ejecutar(
        "UPDATE gapto.contrato_revision_renta_versiones SET " + ", ".join(f"{c} = %s" for c in columnas)
        + ", updated_at = now() WHERE id = %s", tuple(cambios[c] for c in columnas) + (fila_id,))


# ------------------------------------------------------------------ tratamientos (contrato_servicios)
def tratamientos(sesion: SesionMotor, contrato_id: uuid.UUID) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, servicio_entidad_id, incluido_en_renta, repercutible, modo_reparto, actor_repercusion_id, "
            "porcentaje_repercutible, vigente_desde, vigente_hasta FROM gapto.contrato_servicios "
            "WHERE contrato_entidad_id = %s ORDER BY servicio_entidad_id, vigente_desde, id", (contrato_id,))
        return [dict(zip(COLUMNAS_TRATAMIENTO, f)) for f in cur.fetchall()]


def insertar_tratamiento(sesion: SesionMotor, *, fila_id: uuid.UUID, contrato_id: uuid.UUID,
                         servicio_id: uuid.UUID, columnas: dict[str, Any], desde: dt.date,
                         hasta: dt.date | None) -> None:
    sesion.uno(
        "INSERT INTO gapto.contrato_servicios (id, contrato_entidad_id, servicio_entidad_id, incluido_en_renta, "
        "repercutible, modo_reparto, actor_repercusion_id, porcentaje_repercutible, vigente_desde, vigente_hasta) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (fila_id, contrato_id, servicio_id, columnas["incluido_en_renta"], columnas["repercutible"],
         columnas["modo_reparto"], columnas["actor_repercusion_id"], columnas["porcentaje_repercutible"],
         desde, hasta))


def actualizar_tratamiento(sesion: SesionMotor, fila_id: uuid.UUID, columnas: dict[str, Any]) -> None:
    permitidas = {"incluido_en_renta", "repercutible", "modo_reparto", "actor_repercusion_id",
                  "porcentaje_repercutible"}
    cols = sorted(columnas)
    if not cols or set(cols) - permitidas:
        raise ValueError("columnas de tratamiento no editables")
    sesion.ejecutar("UPDATE gapto.contrato_servicios SET " + ", ".join(f"{c} = %s" for c in cols)
                    + " WHERE id = %s", tuple(columnas[c] for c in cols) + (fila_id,))


def tratamientos_abiertos_de_servicio(sesion: SesionMotor, servicio_id: uuid.UUID) -> list[dict[str, Any]]:
    """Filas de contrato_servicios del servicio con vigencia abierta (para la baja)."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT s.id, s.contrato_entidad_id, s.vigente_desde FROM gapto.contrato_servicios s "
            "WHERE s.servicio_entidad_id = %s AND s.vigente_hasta IS NULL ORDER BY s.contrato_entidad_id, s.id",
            (servicio_id,))
        return [dict(zip(("id", "contrato_id", "vigente_desde"), f)) for f in cur.fetchall()]


# ------------------------------------------------------------------ servicios
def servicio(sesion: SesionMotor, servicio_id: uuid.UUID, *, bloqueo: str | None = None) -> dict[str, Any] | None:
    """Servicio del owner. bloqueo: None, 'SHARE' (contratos que lo usan) o 'NK' (C-SRV-01..03)."""
    sufijo = {None: "", "SHARE": " FOR SHARE OF e", "NK": " FOR NO KEY UPDATE OF e"}[bloqueo]
    fila = sesion.uno(
        "SELECT e.id, e.nombre, e.enabled, e.row_version, s.tipo_servicio, s.categoria_default_id, s.fecha_inicio, "
        "s.fecha_fin_real, s.notas FROM gapto.entidades e JOIN gapto.servicios s ON s.entidad_id = e.id "
        f"WHERE e.id = %s AND e.tipo_entidad = 'SERVICIO' AND e.owner_user_id = {OWNER}" + sufijo, (servicio_id,))
    claves = ("id", "nombre", "enabled", "row_version", "tipo_servicio", "categoria_default_id", "fecha_inicio",
              "fecha_fin_real", "notas")
    return None if fila is None else dict(zip(claves, fila))


def servicios_de_propiedad(sesion: SesionMotor, propiedad_id: uuid.UUID) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT e.id, e.nombre, e.row_version, s.tipo_servicio, s.categoria_default_id, s.fecha_inicio, "
            "s.fecha_fin_real, s.notas, v.id, v.vigente_desde, v.vigente_hasta FROM gapto.propiedad_servicios v "
            "JOIN gapto.entidades e ON e.id = v.servicio_entidad_id JOIN gapto.servicios s ON s.entidad_id = e.id "
            f"WHERE v.propiedad_entidad_id = %s AND e.owner_user_id = {OWNER} ORDER BY e.nombre, e.id, "
            "v.vigente_desde", (propiedad_id,))
        claves = ("id", "nombre", "row_version", "tipo_servicio", "categoria_default_id", "fecha_inicio",
                  "fecha_fin_real", "notas", "vinculo_id", "vinculo_desde", "vinculo_hasta")
        return [dict(zip(claves, f)) for f in cur.fetchall()]


def insertar_servicio(sesion: SesionMotor, *, servicio_id: uuid.UUID, nombre: str, tipo_servicio: str,
                      categoria_default_id: uuid.UUID | None, fecha_inicio: dt.date | None,
                      notas: str | None) -> None:
    sesion.uno(
        "INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) VALUES (%s, "
        f"{OWNER}, 'SERVICIO', %s) RETURNING id", (servicio_id, nombre))
    sesion.uno(
        "INSERT INTO gapto.servicios (entidad_id, tipo_servicio, categoria_default_id, fecha_inicio, notas) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING entidad_id",
        (servicio_id, tipo_servicio, categoria_default_id, fecha_inicio, notas))


def actualizar_servicio(sesion: SesionMotor, servicio_id: uuid.UUID, cambios: dict[str, Any]) -> None:
    if "nombre" in cambios:
        sesion.ejecutar("UPDATE gapto.entidades SET nombre = %s, updated_at = now() WHERE id = %s",
                        (cambios["nombre"], servicio_id))
    columnas = sorted(set(cambios) & {"categoria_default_id", "notas", "fecha_fin_real"})
    if set(cambios) - set(columnas) - {"nombre"}:
        raise ValueError("columnas de servicio no editables")
    if columnas:
        sesion.ejecutar(f"UPDATE gapto.servicios SET {', '.join(f'{c} = %s' for c in columnas)} "
                        "WHERE entidad_id = %s", tuple(cambios[c] for c in columnas) + (servicio_id,))


def snapshot_servicio(sesion: SesionMotor, servicio_id: uuid.UUID) -> str:
    fila = sesion.uno(
        "SELECT json_build_object('entidad', row_to_json(e), 'servicio', row_to_json(s), "
        "'vinculos', (SELECT coalesce(json_agg(row_to_json(v) ORDER BY v.vigente_desde, v.id), '[]'::json) "
        "FROM gapto.propiedad_servicios v WHERE v.servicio_entidad_id = e.id))::text "
        "FROM gapto.entidades e JOIN gapto.servicios s ON s.entidad_id = e.id WHERE e.id = %s", (servicio_id,))
    assert fila is not None
    return fila[0]


def vinculos_servicio(sesion: SesionMotor, servicio_id: uuid.UUID) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, propiedad_entidad_id, vigente_desde, vigente_hasta FROM gapto.propiedad_servicios "
            "WHERE servicio_entidad_id = %s ORDER BY vigente_desde, id", (servicio_id,))
        return [dict(zip(("id", "propiedad_id", "vigente_desde", "vigente_hasta"), f)) for f in cur.fetchall()]


def insertar_vinculo_propiedad(sesion: SesionMotor, *, fila_id: uuid.UUID, servicio_id: uuid.UUID, propiedad_id: uuid.UUID,
                     desde: dt.date, hasta: dt.date | None) -> None:
    sesion.uno(
        "INSERT INTO gapto.propiedad_servicios (id, servicio_entidad_id, propiedad_entidad_id, vigente_desde, "
        "vigente_hasta) VALUES (%s, %s, %s, %s, %s) RETURNING id", (fila_id, servicio_id, propiedad_id, desde, hasta))


def servicio_vinculado_en(sesion: SesionMotor, servicio_id: uuid.UUID, propiedad_id: uuid.UUID,
                          fecha: dt.date) -> bool:
    return sesion.uno(
        "SELECT 1 FROM gapto.propiedad_servicios WHERE servicio_entidad_id = %s AND propiedad_entidad_id = %s "
        "AND vigente_desde <= %s AND (vigente_hasta IS NULL OR vigente_hasta >= %s)",
        (servicio_id, propiedad_id, fecha, fecha)) is not None


def tiene_regla_financiera(sesion: SesionMotor, servicio_id: uuid.UUID) -> bool:
    """SOLO LECTURA: ¿hay una regla financiera cuyo origen es el servicio? (AJ-DELTA-05). Nunca la toca."""
    return sesion.uno(
        f"SELECT 1 FROM gapto.reglas_financieras WHERE entidad_origen_id = %s AND owner_user_id = {OWNER} LIMIT 1",
        (servicio_id,)) is not None


def categoria_admitida_para_gasto(sesion: SesionMotor, ident: uuid.UUID) -> bool:
    """Categoria del owner, habilitada y de ambito GASTO o AMBOS (FOR SHARE: nivel de servicios)."""
    return sesion.uno(
        "SELECT 1 FROM gapto.categorias_financieras WHERE id = %s AND enabled AND ambito IN ('GASTO', 'AMBOS') "
        f"AND owner_user_id = {OWNER} FOR SHARE", (ident,)) is not None


# ------------------------------------------------------------------ auditoria (lecturas)
def auditorias_de_registro(sesion: SesionMotor, registro_id: uuid.UUID) -> list[dict[str, Any]]:
    """Auditoria visible de un registro, la mas reciente primero (para identificar lo que cerro una terminacion)."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT motivo, datos_despues::text FROM gapto.auditoria WHERE tabla = 'entidades' AND registro_id = %s "
            "ORDER BY created_at DESC, id DESC", (registro_id,))
        return [dict(zip(("motivo", "despues"), f)) for f in cur.fetchall()]


# ------------------------------------------------------------------ terceros: hijas (C-TER-01/03)
def tercero_con_hijas(sesion: SesionMotor, tercero_id: uuid.UUID) -> dict[str, Any] | None:
    """Tercero del owner (sin bloqueo; el writer lo bloquea con terceros.repositorio.leer)."""
    fila = sesion.uno(
        f"SELECT id, nombre, naturaleza, enabled, row_version FROM gapto.terceros WHERE id = %s "
        f"AND owner_user_id = {OWNER}", (tercero_id,))
    return None if fila is None else dict(zip(("id", "nombre", "naturaleza", "enabled", "row_version"), fila))


def roles_de_tercero(sesion: SesionMotor, tercero_id: uuid.UUID) -> list[str]:
    with sesion.conexion.cursor() as cur:
        cur.execute("SELECT rol_codigo FROM gapto.tercero_roles WHERE tercero_id = %s ORDER BY rol_codigo",
                    (tercero_id,))
        return [f[0] for f in cur.fetchall()]


def insertar_rol_si_no_existe(sesion: SesionMotor, tercero_id: uuid.UUID, rol: str) -> bool:
    """True si inserto; False si ya estaba (UNIQUE natural; idempotente)."""
    fila = sesion.uno(
        "INSERT INTO gapto.tercero_roles (tercero_id, rol_codigo) VALUES (%s, %s) "
        "ON CONFLICT ON CONSTRAINT uq_tercero_roles__tercero_rol DO NOTHING RETURNING id", (tercero_id, rol))
    return fila is not None


def clasificaciones_de_tercero(sesion: SesionMotor, tercero_id: uuid.UUID) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT tc.id, tc.clasificacion_id, c.nombre, tc.principal, c.enabled FROM gapto.tercero_clasificaciones tc "
            "JOIN gapto.clasificaciones_tercero c ON c.id = tc.clasificacion_id WHERE tc.tercero_id = %s "
            "ORDER BY c.nombre, tc.id", (tercero_id,))
        return [dict(zip(("id", "clasificacion_id", "nombre", "principal", "enabled"), f)) for f in cur.fetchall()]


def clasificacion(sesion: SesionMotor, clasificacion_id: uuid.UUID, *, bloquear: bool = False) -> dict[str, Any] | None:
    fila = sesion.uno(
        "SELECT id, parent_id, nombre, enabled, row_version FROM gapto.clasificaciones_tercero WHERE id = %s "
        f"AND owner_user_id = {OWNER}" + (" FOR NO KEY UPDATE" if bloquear else ""), (clasificacion_id,))
    return None if fila is None else dict(zip(("id", "parent_id", "nombre", "enabled", "row_version"), fila))


def clasificaciones(sesion: SesionMotor) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, parent_id, nombre, enabled, row_version FROM gapto.clasificaciones_tercero "
            f"WHERE owner_user_id = {OWNER} ORDER BY nombre, id")
        return [dict(zip(("id", "parent_id", "nombre", "enabled", "row_version"), f)) for f in cur.fetchall()]


def insertar_asignacion_si_no_existe(sesion: SesionMotor, tercero_id: uuid.UUID, clasificacion_id: uuid.UUID,
                                     principal: bool) -> bool:
    fila = sesion.uno(
        "INSERT INTO gapto.tercero_clasificaciones (tercero_id, clasificacion_id, principal) VALUES (%s, %s, %s) "
        "ON CONFLICT ON CONSTRAINT uq_tercero_clasificaciones__tercero_clasificacion DO NOTHING RETURNING id",
        (tercero_id, clasificacion_id, principal))
    return fila is not None


def fijar_principal_asignacion(sesion: SesionMotor, tercero_id: uuid.UUID, clasificacion_id: uuid.UUID | None) -> int:
    """Como mucho UNA principal por tercero (regla de servicio: no hay restriccion fisica, D-DISC-12).
    Devuelve las filas realmente cambiadas (0 = ya estaba asi)."""
    return sesion.ejecutar(
        "UPDATE gapto.tercero_clasificaciones SET principal = (clasificacion_id IS NOT DISTINCT FROM %s) "
        "WHERE tercero_id = %s AND principal IS DISTINCT FROM (clasificacion_id IS NOT DISTINCT FROM %s)",
        (clasificacion_id, tercero_id, clasificacion_id))


def insertar_clasificacion(sesion: SesionMotor, *, clasificacion_id: uuid.UUID, parent_id: uuid.UUID | None,
                           nombre: str) -> None:
    sesion.uno(
        "INSERT INTO gapto.clasificaciones_tercero (id, owner_user_id, parent_id, nombre) VALUES (%s, "
        f"{OWNER}, %s, %s) RETURNING id", (clasificacion_id, parent_id, nombre))


def actualizar_clasificacion(sesion: SesionMotor, clasificacion_id: uuid.UUID, cambios: dict[str, Any]) -> None:
    columnas = sorted(cambios)
    if not columnas or set(columnas) - {"nombre", "parent_id", "enabled"}:
        raise ValueError("columnas de clasificacion no editables")
    sesion.ejecutar(
        f"UPDATE gapto.clasificaciones_tercero SET {', '.join(f'{c} = %s' for c in columnas)}, "
        "row_version = row_version + 1, updated_at = now() WHERE id = %s",
        tuple(cambios[c] for c in columnas) + (clasificacion_id,))


def snapshot_clasificacion(sesion: SesionMotor, clasificacion_id: uuid.UUID) -> str:
    fila = sesion.uno("SELECT row_to_json(c)::text FROM gapto.clasificaciones_tercero c WHERE c.id = %s",
                      (clasificacion_id,))
    assert fila is not None
    return fila[0]


def snapshot_tercero_con_hijas(sesion: SesionMotor, tercero_id: uuid.UUID) -> str:
    fila = sesion.uno(
        "SELECT json_build_object('tercero', row_to_json(t), "
        "'roles', (SELECT coalesce(json_agg(r.rol_codigo ORDER BY r.rol_codigo), '[]'::json) "
        "FROM gapto.tercero_roles r WHERE r.tercero_id = t.id), "
        "'clasificaciones', (SELECT coalesce(json_agg(json_build_object('clasificacion_id', c.clasificacion_id, "
        "'principal', c.principal) ORDER BY c.clasificacion_id), '[]'::json) "
        "FROM gapto.tercero_clasificaciones c WHERE c.tercero_id = t.id))::text "
        "FROM gapto.terceros t WHERE t.id = %s", (tercero_id,))
    assert fila is not None
    return fila[0]
