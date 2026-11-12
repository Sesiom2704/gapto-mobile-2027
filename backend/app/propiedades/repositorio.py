# ============================================================
# GAPTO MOBILE 2027
# Fichero: repositorio.py
# Ruta: backend/app/propiedades/repositorio.py
# Descripcion: Acceso a datos de propiedades (F06-01 B1; contratos R1 v0.8
#   Parte I). Entidad PROPIEDAD + subtipo `propiedades`, titularidad en
#   `entidad_participaciones` y `propiedad_valoraciones`. SQL puro.
#   - Solo INSERT y UPDATE: runtime no tiene DELETE en participaciones ni en
#     valoraciones (0200, 0230). Una titularidad se cierra con vigente_hasta.
#   - row_version del agregado = el de la entidad; toda escritura en sus
#     hijas la incrementa en la misma transaccion (v0.8 §1.4).
#   - El owner nunca es parametro (GUC); la RLS hace el resto. Un id de otro
#     owner no es visible: se trata como inexistente.
#   - Nivel 2 del orden de locks (v0.8 §1.4): FOR NO KEY UPDATE de la
#     entidad PROPIEDAD antes de leer participaciones o valoraciones.
# Version: 0.1.0 (F06-01 B1, lote 12)
# Version: 0.2.0 (F03 · N1 de 0352, AJ-0352-05): corte_adquisicion_declarado, lectura del corte de la
#   declaracion de adquisicion para la guarda de C-PROP-02. Las seis columnas de 0352 NO entran en
#   COLUMNAS_PROPIEDAD (AJ-0352-08): B1 nunca las escribe.
# Version: 0.3.0 (F06 T1-F06 B2 N1; FA-01 opcion a, decision de Moises 2026-11-12 `e0adb0be…`): lista cerrada de
#   funciones de acceso a las seis columnas de 0352 para los consumidores provisionales de B2 (conjunto_completitud,
#   declaracion_completitud, escribir_declaracion_completitud, leer_coste) y el predicado de componente de L-COSTE
#   (nivel efecto, HF-08; escala 4, HF-04; huella en PostgreSQL, HF-11). Nada de B1 cambia.
# ============================================================

from __future__ import annotations

import datetime as dt
import json
import uuid
from decimal import Decimal
from typing import Any

from app.core.unidad_trabajo import SesionMotor

TRIGGERS_SUBTIPO = "gapto.trg_entidades__subtipo_unico, gapto.trg_propiedades__subtipo_unico"

#: Columnas de `propiedades` que escribe B1 (direccion y salida: fuera de B1).
COLUMNAS_PROPIEDAD = (
    "tipo_propiedad", "fecha_adquisicion", "superficie_m2", "superficie_construida_m2", "habitaciones",
    "banos", "tiene_garaje", "tiene_trastero", "referencia_catastral", "incluir_en_rentabilidad", "notas",
)
COLUMNAS_LECTURA = COLUMNAS_PROPIEDAD + ("fecha_salida_patrimonio",)

_SNAPSHOT = (
    "SELECT json_build_object('entidad', row_to_json(e), 'propiedad', row_to_json(p), "
    "'participaciones', (SELECT coalesce(json_agg(row_to_json(x) ORDER BY x.vigente_desde, x.actor_id), '[]'::json) "
    "FROM gapto.entidad_participaciones x WHERE x.entidad_id = e.id), "
    "'valoraciones', (SELECT coalesce(json_agg(row_to_json(v) ORDER BY v.id), '[]'::json) "
    "FROM gapto.propiedad_valoraciones v WHERE v.propiedad_entidad_id = e.id))::text "
    "FROM gapto.entidades e JOIN gapto.propiedades p ON p.entidad_id = e.id WHERE e.id = %s"
)


def actor_self(sesion: SesionMotor) -> uuid.UUID | None:
    fila = sesion.uno(
        "SELECT id FROM gapto.actores_financieros WHERE tercero_id IS NULL "
        "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid"
    )
    return None if fila is None else fila[0]


def existe_entidad(sesion: SesionMotor, entidad_id: uuid.UUID) -> bool:
    """Cualquier entidad del owner con ese id (de cualquier tipo)."""
    return sesion.uno(
        "SELECT 1 FROM gapto.entidades WHERE id = %s "
        "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid", (entidad_id,)
    ) is not None


def bloquear(sesion: SesionMotor, entidad_id: uuid.UUID) -> dict[str, Any] | None:
    """Nivel 2: FOR NO KEY UPDATE de la entidad PROPIEDAD del owner."""
    fila = sesion.uno(
        "SELECT e.row_version, e.enabled, p.fecha_adquisicion FROM gapto.entidades e "
        "JOIN gapto.propiedades p ON p.entidad_id = e.id WHERE e.id = %s AND e.tipo_entidad = 'PROPIEDAD' "
        "AND e.owner_user_id = current_setting('gapto.owner_user_id')::uuid FOR NO KEY UPDATE OF e",
        (entidad_id,),
    )
    return None if fila is None else {"row_version": fila[0], "enabled": fila[1], "fecha_adquisicion": fila[2]}


_SELECT = (
    "SELECT e.id, e.nombre, e.enabled, e.row_version, " + ", ".join(f"p.{c}" for c in COLUMNAS_LECTURA)
    + " FROM gapto.entidades e JOIN gapto.propiedades p ON p.entidad_id = e.id "
    "WHERE e.tipo_entidad = 'PROPIEDAD' AND e.owner_user_id = current_setting('gapto.owner_user_id')::uuid"
)
_CLAVES = ("id", "nombre", "enabled", "row_version") + COLUMNAS_LECTURA


def corte_adquisicion_declarado(sesion: SesionMotor, entidad_id: uuid.UUID) -> dt.date | None:
    """0352 (AJ-0352-05): fecha de corte si la adquisicion esta declarada completa; None si no. Solo lectura,
    tras bloquear la entidad. Las columnas de declaracion no estan en COLUMNAS_PROPIEDAD (AJ-0352-08)."""
    fila = sesion.uno(
        "SELECT p.coste_adquisicion_declarado_en FROM gapto.propiedades p WHERE p.entidad_id = %s "
        "AND p.coste_adquisicion_declarado_completo IS TRUE",
        (entidad_id,),
    )
    return None if fila is None else fila[0]


def leer(sesion: SesionMotor, entidad_id: uuid.UUID) -> dict[str, Any] | None:
    fila = sesion.uno(_SELECT + " AND e.id = %s", (entidad_id,))
    return None if fila is None else dict(zip(_CLAVES, fila))


def listar(sesion: SesionMotor) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(_SELECT + " ORDER BY e.nombre, e.id")
        return [dict(zip(_CLAVES, f)) for f in cur.fetchall()]


def participaciones(sesion: SesionMotor, entidad_id: uuid.UUID, *, bloquear_filas: bool = False) -> list[dict[str, Any]]:
    """Todas las filas de titularidad con su actor y tercero (FOR UPDATE por id si se van a cerrar)."""
    sufijo = " ORDER BY x.id FOR UPDATE OF x" if bloquear_filas else " ORDER BY x.vigente_desde, x.actor_id"
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT x.id, x.actor_id, a.tercero_id, t.nombre, x.porcentaje, x.vigente_desde, x.vigente_hasta "
            "FROM gapto.entidad_participaciones x JOIN gapto.actores_financieros a ON a.id = x.actor_id "
            "LEFT JOIN gapto.terceros t ON t.id = a.tercero_id WHERE x.entidad_id = %s" + sufijo, (entidad_id,))
        claves = ("id", "actor_id", "tercero_id", "nombre", "porcentaje", "vigente_desde", "vigente_hasta")
        return [dict(zip(claves, f)) for f in cur.fetchall()]


def snapshot(sesion: SesionMotor, entidad_id: uuid.UUID) -> str:
    fila = sesion.uno(_SNAPSHOT, (entidad_id,))
    assert fila is not None
    return fila[0]


def insertar_propiedad(sesion: SesionMotor, *, entidad_id: uuid.UUID, nombre: str, datos: dict[str, Any]) -> None:
    sesion.uno(
        "INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) VALUES (%s, "
        "current_setting('gapto.owner_user_id')::uuid, 'PROPIEDAD', %s) RETURNING id",
        (entidad_id, nombre),
    )
    columnas = ("entidad_id",) + COLUMNAS_PROPIEDAD
    sesion.uno(
        f"INSERT INTO gapto.propiedades ({', '.join(columnas)}) VALUES ({', '.join(['%s'] * len(columnas))}) "
        "RETURNING entidad_id",
        (entidad_id,) + tuple(datos[c] for c in COLUMNAS_PROPIEDAD),
    )


def actualizar_propiedad(sesion: SesionMotor, entidad_id: uuid.UUID, cambios: dict[str, Any]) -> None:
    """UPDATE de nombre (entidad) y de columnas de `propiedades`; las claves vienen de listas cerradas."""
    if "nombre" in cambios:
        sesion.ejecutar("UPDATE gapto.entidades SET nombre = %s, updated_at = now() WHERE id = %s",
                        (cambios["nombre"], entidad_id))
    columnas = [c for c in COLUMNAS_PROPIEDAD if c in cambios]
    if columnas:
        sesion.ejecutar(
            f"UPDATE gapto.propiedades SET {', '.join(f'{c} = %s' for c in columnas)} WHERE entidad_id = %s",
            tuple(cambios[c] for c in columnas) + (entidad_id,))


def insertar_participacion(sesion: SesionMotor, *, fila_id: uuid.UUID, entidad_id: uuid.UUID,
                           actor_id: uuid.UUID, porcentaje: Decimal, desde: dt.date) -> None:
    sesion.uno(
        "INSERT INTO gapto.entidad_participaciones (id, entidad_id, actor_id, porcentaje, vigente_desde) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (fila_id, entidad_id, actor_id, porcentaje, desde),
    )


def cerrar_participacion(sesion: SesionMotor, fila_id: uuid.UUID, hasta: dt.date) -> None:
    sesion.ejecutar("UPDATE gapto.entidad_participaciones SET vigente_hasta = %s WHERE id = %s", (hasta, fila_id))


def subir_version(sesion: SesionMotor, entidad_id: uuid.UUID) -> int:
    fila = sesion.uno(
        "UPDATE gapto.entidades SET row_version = row_version + 1, updated_at = now() WHERE id = %s "
        "RETURNING row_version", (entidad_id,))
    assert fila is not None
    return fila[0]


def max_habitacion_en_uso(sesion: SesionMotor, entidad_id: uuid.UUID) -> tuple[int | None, list[uuid.UUID]]:
    """Mayor `contratos.habitacion` de los contratos no CANCELADOS de la propiedad y sus ids (Q-CON-03 A)."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT entidad_id, habitacion FROM gapto.contratos WHERE propiedad_entidad_id = %s "
            "AND estado_documental <> 'CANCELADO' AND habitacion IS NOT NULL ORDER BY entidad_id", (entidad_id,))
        filas = cur.fetchall()
    return (max((f[1] for f in filas), default=None), [f[0] for f in filas])


# ------------------------------------------------------------------ valoraciones
COLUMNAS_VALORACION = ("id", "valor_total", "fecha_valoracion", "metodo", "fuente", "notas", "moneda",
                       "propiedad_id")


def leer_valoracion(sesion: SesionMotor, valoracion_id: uuid.UUID) -> dict | None:
    fila = sesion.uno(
        "SELECT id, valor_total, fecha_valoracion, metodo, fuente, notas, moneda, propiedad_entidad_id "
        "FROM gapto.propiedad_valoraciones WHERE id = %s",
        (valoracion_id,))
    return None if fila is None else dict(zip(COLUMNAS_VALORACION, fila))


def insertar_valoracion(sesion: SesionMotor, *, valoracion_id: uuid.UUID, propiedad_id: uuid.UUID,
                        valor_total: Decimal, fecha: dt.date, metodo: str, fuente, notas) -> None:
    sesion.uno(
        "INSERT INTO gapto.propiedad_valoraciones (id, propiedad_entidad_id, fecha_valoracion, valor_total, "
        "moneda, metodo, fuente, notas) VALUES (%s, %s, %s, %s, 'EUR', %s, %s, %s) RETURNING id",
        (valoracion_id, propiedad_id, fecha, valor_total, metodo, fuente, notas),
    )


def valoraciones(sesion: SesionMotor, propiedad_id: uuid.UUID) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, valor_total, fecha_valoracion, metodo, fuente, notas, moneda, propiedad_entidad_id "
            "FROM gapto.propiedad_valoraciones WHERE propiedad_entidad_id = %s "
            "ORDER BY fecha_valoracion NULLS FIRST, id", (propiedad_id,))
        return [dict(zip(COLUMNAS_VALORACION, f)) for f in cur.fetchall()]


# ------------------------------------------------------------------ idempotencia (auditoria por request_id)
def auditorias_de_intencion(sesion: SesionMotor, intencion_id: uuid.UUID) -> list[dict[str, Any]]:
    """Auditoria visible (RLS por owner) escrita con request_id = intencion_id."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT tabla, registro_id, motivo, datos_despues::text FROM gapto.auditoria WHERE request_id = %s "
            "ORDER BY created_at, id", (intencion_id,))
        return [dict(zip(("tabla", "registro_id", "motivo", "despues"), f)) for f in cur.fetchall()]


# ------------------------------------------------------------------ 0352 · completitud del coste (B2; FA-01)
# Decision de Moisés FA-01 (opcion a; `F06-00_Decisiones_Moises_2026-11-12_FA01_y_regla_tests_v1.0.md`): el
# acceso de B2 a las columnas de 0352 se concentra AQUI, en una lista cerrada de funciones que inventaria
# test_235 (con el numero exacto de columnas). Las escriben solo C-PROP-05 y C-COMPRA-01/03 con declaracion
# (modulo backend/app/patrimonio), siempre con la entidad ya en NK; C-PROP-01/02 nunca (AJ-0352-08).

#: ambito -> (causa del componente, completo, corte, conjunto)
AMBITOS_COMPLETITUD = {
    "ADQUISICION": ("ADQUISICION", "coste_adquisicion_declarado_completo", "coste_adquisicion_declarado_en",
                    "coste_adquisicion_conjunto_declarado"),
    "MEJORAS": ("TRANSFORMACION_CAPITALIZABLE", "mejoras_declaradas_completas", "mejoras_declaradas_en",
                "mejoras_conjunto_declarado"),
}

#: Componentes de una propiedad (R1 v0.9.5 §II.6): efecto VALOR_ACTIVO con causa ADQUISICION o
#: TRANSFORMACION_CAPITALIZABLE, de un hecho ACTIVO, con AFECTA_A principal a la propiedad DE NIVEL EFECTO
#: (HF-08: un vinculo de nivel hecho no hace componente), deduplicado por efecto. Fecha = fecha economica.
_COMPONENTES = (
    "SELECT DISTINCT ON (e.id) e.id AS efecto_id, e.hecho_id, e.importe_delta AS importe, h.fecha_hecho AS fecha, "
    "e.causa_valor_activo AS causa, e.estado_atribucion FROM gapto.hecho_efectos e "
    "JOIN gapto.hechos_financieros h ON h.id = e.hecho_id AND h.estado = 'ACTIVO' "
    "JOIN gapto.hecho_entidades x ON x.hecho_id = e.hecho_id AND x.entidad_id = %(p)s "
    "AND x.tipo_relacion = 'AFECTA_A' AND x.principal AND x.efecto_id = e.id "
    "WHERE e.tipo_efecto = 'VALOR_ACTIVO' AND e.causa_valor_activo IN ('ADQUISICION', 'TRANSFORMACION_CAPITALIZABLE') "
    "ORDER BY e.id"
)


def _conjunto_sql(causa: str, limite: str) -> str:
    """Expresion canonica UNICA del conjunto (§II.6; HF-04: importe con la escala de la columna, 4 decimales)."""
    return (
        "coalesce((SELECT jsonb_agg(jsonb_build_object('efecto_id', c.efecto_id::text, 'hecho_id', c.hecho_id::text, "
        "'importe', round(c.importe, 4)::numeric(20,4)::text, 'fecha', to_char(c.fecha, 'YYYY-MM-DD'), "
        f"'causa', c.causa) ORDER BY c.efecto_id) FROM comp c WHERE c.causa = '{causa}' AND c.fecha <= {limite}), "
        "'[]'::jsonb)"
    )


def _huella_sql(expr: str) -> str:
    """HF-11: sha256 del texto jsonb del conjunto, calculada SOLO en PostgreSQL."""
    return f"encode(sha256(convert_to(({expr})::text, 'UTF8')), 'hex')"


def conjunto_completitud(sesion: SesionMotor, entidad_id: uuid.UUID, ambito: str,
                         hasta: dt.date) -> tuple[Any, str]:
    """(conjunto canonico como jsonb ya decodificado, huella) del ambito hasta `hasta`, en una sentencia."""
    expr = _conjunto_sql(AMBITOS_COMPLETITUD[ambito][0], "%(f)s::date")
    fila = sesion.uno(f"WITH comp AS ({_COMPONENTES}) SELECT ({expr})::text, {_huella_sql(expr)}",
                      {"p": entidad_id, "f": hasta})
    return json.loads(fila[0]), fila[1]


def declaracion_completitud(sesion: SesionMotor, entidad_id: uuid.UUID, ambito: str) -> tuple[Any, Any, Any]:
    """Terna vigente (completo, corte, conjunto) del ambito. Solo lectura, con la entidad ya bloqueada."""
    _, ok, en, conj = AMBITOS_COMPLETITUD[ambito]
    fila = sesion.uno(f"SELECT p.{ok}, p.{en}, p.{conj}::text FROM gapto.propiedades p WHERE p.entidad_id = %s",
                      (entidad_id,))
    return fila[0], fila[1], (None if fila[2] is None else json.loads(fila[2]))


def escribir_declaracion_completitud(sesion: SesionMotor, entidad_id: uuid.UUID, ambito: str,
                                     terna: tuple[Any, Any, Any]) -> None:
    """UNICO writer de las columnas de 0352 (C-PROP-05; C-COMPRA-01/03 con declaracion). Escribe las TRES columnas
    del ambito juntas (CHECK de 0352: o las tres NULL, o completas). La entidad ya esta en NK."""
    _, ok, en, conj = AMBITOS_COMPLETITUD[ambito]
    sesion.ejecutar(f"UPDATE gapto.propiedades SET {ok} = %s, {en} = %s, {conj} = %s::jsonb WHERE entidad_id = %s",
                    (terna[0], terna[1], None if terna[2] is None else json.dumps(terna[2]), entidad_id))


def _ambito_coste_sql(ambito: str, con_declaracion: bool) -> str:
    causa, ok, en, conj = AMBITOS_COMPLETITUD[ambito]
    hasta = _conjunto_sql(causa, "%(a)s::date")
    if con_declaracion:
        declaracion = (f"p.{ok}, p.{en}, CASE WHEN p.{ok} IS TRUE THEN p.{conj} = {_conjunto_sql(causa, f'p.{en}')} END, "
                       f"(SELECT count(*) FROM comp c WHERE c.causa = '{causa}' AND c.fecha > p.{en} "
                       "AND c.fecha <= %(a)s::date)")
    else:
        declaracion = "NULL::boolean, NULL::date, NULL::boolean, 0::bigint"
    return (
        f"SELECT '{ambito}', "
        f"(SELECT coalesce(sum(c.importe), 0) FROM comp c WHERE c.causa = '{causa}' AND c.fecha <= %(a)s::date), "
        f"(SELECT count(*) FROM comp c WHERE c.causa = '{causa}' AND c.fecha <= %(a)s::date), "
        "(SELECT coalesce(sum(t.importe_atribuido), 0) FROM comp c JOIN gapto.efecto_atribuciones t "
        f"ON t.efecto_id = c.efecto_id AND t.actor_id = (SELECT id FROM yo) WHERE c.causa = '{causa}' "
        "AND c.fecha <= %(a)s::date), "
        f"(SELECT array_agg(DISTINCT c.estado_atribucion) FROM comp c WHERE c.causa = '{causa}' "
        "AND c.fecha <= %(a)s::date), "
        f"{declaracion}, {_huella_sql(hasta)} FROM p"
    )


def leer_coste(sesion: SesionMotor, entidad_id: uuid.UUID, a_fecha: dt.date,
               con_declaracion: bool) -> list[tuple] | None:
    """L-COSTE (§II.6): por ambito (ambito, total, n, tu parte, estados de atribucion, completo, corte, igual,
    posteriores, huella) en UNA sentencia (una instantanea). Sin `con_declaracion` (consumidores de 0352 no
    habilitados) la sentencia no lee la declaracion."""
    sql = ("WITH p AS (SELECT q.* FROM gapto.propiedades q JOIN gapto.entidades e ON e.id = q.entidad_id "
           "WHERE q.entidad_id = %(p)s AND e.tipo_entidad = 'PROPIEDAD' "
           "AND e.owner_user_id = current_setting('gapto.owner_user_id')::uuid), "
           "yo AS (SELECT id FROM gapto.actores_financieros WHERE tercero_id IS NULL "
           "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid), "
           f"comp AS ({_COMPONENTES}) "
           + " UNION ALL ".join(_ambito_coste_sql(a, con_declaracion) for a in AMBITOS_COMPLETITUD))
    with sesion.conexion.cursor() as cur:
        cur.execute(sql, {"p": entidad_id, "a": a_fecha})
        filas = cur.fetchall()
    return filas or None
