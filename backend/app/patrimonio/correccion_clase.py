# ============================================================
# GAPTO MOBILE 2027
# Fichero: correccion_clase.py
# Ruta: backend/app/patrimonio/correccion_clase.py
# Descripcion: B3 · C-MEJ-03, correccion atomica de la naturaleza de un gasto de propiedad
#   (`corregir_naturaleza_patrimonial`; POST /v1/propiedades/{id}/gastos/{hecho_id}/corregir-clase).
#   Excepcion E-1 (R1 v0.9.5 Parte IV y §IV.1): corrección agregada PROPIA que actualiza `tipo_hecho_id` y
#   sustituye el efecto en una transaccion. NO llama a CorreccionesService (ni a `corregir` ni a ningun metodo
#   publico o privado; no importa su modulo: O5.34, N1-RF2-13), no amplia OP-02 y no anula ni recrea el hecho.
#   Matriz (v0.9 §III.3.1): MEJORA -> REPARACION / GASTO_CORRIENTE (VALOR_ACTIVO -> GASTO, MEJORA_PATRIMONIAL ->
#     GASTO, causa limpia) y REPARACION / GASTO_CORRIENTE -> MEJORA (GASTO -> VALOR_ACTIVO, GASTO ->
#     MEJORA_PATRIMONIAL, causa TRANSFORMACION_CAPITALIZABLE). Misma clase de efecto -> ENTRADA_INVALIDA.
#   Orden de guardas (§III.3.3 v0.9.3+): DTO -> locks 0 advisory de la raiz -> 1 INVERSIONES -> 2 propiedad FOR
#     SHARE -> 4 categoria FOR SHARE -> 7 hecho FOR NO KEY UPDATE y sus posiciones -> 2bis (hecho ACTIVO con
#     EXACTAMENTE un efecto vigente; si no, CORRECCION_NATURALEZA_NO_ADMITIDA sin mutaciones) -> 3 identidad
#     (§III.3.6: fila a replay exacto por el sello; fila b intencion vigente uuid5(e.id, ...cmej03.intencion);
#     fila c INTENCION_CORRECCION_NO_VIGENTE) -> elegibilidad restante (arquetipo, efecto y causa, procedencia
#     persistida por la marca uuid5 de C-MEJ-01/02, dependencias, propiedad disponible, localizacion de §III.1ter)
#     -> version -> periodo cerrado -> presupuestable frente al estado -> guarda C-a de la categoria -> impacto
#     (§III.3.5, contribuciones del hecho) -> escritura.
#   Algoritmo de sustitucion (§III.3.4 v0.9 con los pasos 2 y 3 de v0.9.3): 1 UPDATE de tipo_hecho_id y
#     presupuestable (row_version + 1 exacto); 2 INSERT de e1 = uuid5(I, "gapto.f06.cmej03.efecto:" + sello) por
#     efectos_repository (guarda comun de causa); 3 atribuciones copiadas con id uuid5(e1, "...atribucion:" +
#     actor); 4 vinculos de nivel efecto de e0 REAPUNTADOS por UPDATE (conservan su id: marca de procedencia y
#     E-3); 5 atribuciones de e0 retiradas ANTES que 6 e0 (FK RESTRICT inmediatas); 8 estado de atribucion de e1 =
#     el de e0; 9 guardas del estado final; 10 auditoria resumen {e0 -> e1}. Snapshots de auditoria con
#     `causa_valor_activo`, tambien NULL (§III.4); rechazos y replays sin auditoria.
#   Reserva de PROPIEDAD (Parte IV-bis): no expone OP-21 ni OP-03 sobre PROPIEDAD ni sobre H0/Hk.
# Version: 0.1.0 (F06 T1-F06 B3 N1)
# ============================================================

from __future__ import annotations

import hashlib
import json
import uuid
from decimal import Decimal
from typing import Any

from app.api.ejecucion_registro import tomar_inversiones
from app.api.elegibilidad_categoria import validar_seleccion_categoria
from app.comun.fecha_funcional import Reloj, reloj_sistema
from app.core.errores import CodigoError, ErrorMotor
from app.core.unidad_trabajo import SesionMotor
from app.patrimonio import gasto_propiedad as gp
from app.patrimonio.completitud import Rechazo
from app.repositories import auditoria_repository as auditoria
from app.repositories import compuesto_repository as repo_comp
from app.repositories import efectos_repository as repo_efectos
from app.repositories.correccion_tesoreria_repository import periodo_cerrado
from app.repositories.posiciones_repository import bloquear_posiciones, posiciones_de_hecho

OPERACION = "CORRECCION_NATURALEZA_PATRIMONIAL"
NO_ADMITIDA = "CORRECCION_NATURALEZA_NO_ADMITIDA"
NO_VIGENTE = "INTENCION_CORRECCION_NO_VIGENTE"
IMPACTO_DESFASADO = "IMPACTO_CORRECCION_DESFASADO"
MOTIVO_AUSENTE = "MOTIVO_AUSENTE"
PERIODO_CERRADO = "PERIODO_CERRADO_SIN_POLITICA"
IDENTIDAD_REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"

_EFECTO_JSON = (
    "SELECT json_build_object('id', e.id, 'hecho_id', e.hecho_id, 'tipo_efecto', e.tipo_efecto, "
    "'importe_delta', e.importe_delta, 'categoria_id', e.categoria_id, 'estado_atribucion', e.estado_atribucion, "
    "'descripcion', e.descripcion, 'causa_valor_activo', e.causa_valor_activo)::text "
    "FROM gapto.hecho_efectos e WHERE e.id = %s")


def _dto(p: dict) -> str | None:
    """Paso 1: lo que el DTO puede juzgar sin estado (clase DECLARADA)."""
    if p.get("motivo") is None or not str(p["motivo"]).strip():
        return MOTIVO_AUSENTE
    if p["clase_nueva"] == "MEJORA":
        if p.get("categoria_id") is not None or p.get("presupuestable") is not None:
            return gp.ENTRADA_INVALIDA
    elif p.get("categoria_id") is None or p.get("presupuestable") is None:
        return gp.ENTRADA_INVALIDA
    return None


def canonica(hecho_id: uuid.UUID, propiedad_id: uuid.UUID, p: dict) -> dict[str, Any]:
    c = p["comparacion_vista"]
    return {"hecho_id": str(hecho_id), "propiedad_id": str(propiedad_id),
            "row_version_esperada": p["row_version_esperada"], "clase_nueva": p["clase_nueva"],
            "categoria_id": None if p.get("categoria_id") is None else str(p["categoria_id"]),
            "presupuestable": p.get("presupuestable"), "motivo": p["motivo"],
            "comparacion_vista": {k: c[k] for k in sorted(c)}}


def sello(canon: dict[str, Any]) -> str:
    texto = json.dumps(canon, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def efecto_destino(intencion_id: uuid.UUID, s: str) -> uuid.UUID:
    return uuid.uuid5(intencion_id, "gapto.f06.cmej03.efecto:" + s)


def _hecho(sesion: SesionMotor, hecho_id: uuid.UUID) -> dict[str, Any] | None:
    fila = sesion.uno(
        "SELECT h.estado, h.row_version, th.codigo, h.fecha_hecho, h.presupuestable, h.estado_localizacion "
        "FROM gapto.hechos_financieros h JOIN gapto.tipos_hecho th ON th.id = h.tipo_hecho_id WHERE h.id = %s",
        (hecho_id,))
    return None if fila is None else dict(zip(("estado", "row_version", "tipo", "fecha", "presupuestable",
                                               "localizacion"), fila))


def _efectos(sesion: SesionMotor, hecho_id: uuid.UUID) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute("SELECT id, tipo_efecto, importe_delta, categoria_id, causa_valor_activo, estado_atribucion "
                    "FROM gapto.hecho_efectos WHERE hecho_id = %s ORDER BY id", (hecho_id,))
        return [dict(zip(("id", "tipo", "importe", "categoria_id", "causa", "estado_atribucion"), f))
                for f in cur.fetchall()]


def _procedencia(sesion: SesionMotor, hecho_id: uuid.UUID, propiedad_id: uuid.UUID, efecto_id: uuid.UUID) -> bool:
    """v0.9 §III.3.2 punto 4 (opcion b): la fila de la marca uuid5(hecho, R) existe, es AFECTA_A principal a la
    propiedad de la ruta y apunta al efecto vigente."""
    return sesion.uno(
        "SELECT 1 FROM gapto.hecho_entidades WHERE id IN (%s, %s) AND hecho_id = %s AND entidad_id = %s "
        "AND tipo_relacion = 'AFECTA_A' AND principal AND efecto_id = %s",
        (gp.ident(hecho_id, gp.PREFIJO_GP, "afecta_a"), gp.ident(hecho_id, gp.PREFIJO_MH, "afecta_a"), hecho_id,
         propiedad_id, efecto_id)) is not None


def _dependencias(sesion: SesionMotor, hecho_id: uuid.UUID, a_mejora: bool) -> bool:
    """v0.9 §III.3.2 punto 5: relaciones entre hechos, posiciones alimentadas, previsiones y, hacia MEJORA,
    magnitudes (cuelgan de la categoria, que desaparece)."""
    fila = sesion.uno(
        "SELECT EXISTS (SELECT 1 FROM gapto.hecho_relaciones r WHERE r.hecho_origen_id = %(h)s "
        "OR r.hecho_destino_id = %(h)s) OR EXISTS (SELECT 1 FROM gapto.prevision_hechos v WHERE v.hecho_id = %(h)s) "
        "OR (%(m)s AND EXISTS (SELECT 1 FROM gapto.hecho_magnitudes g WHERE g.hecho_id = %(h)s))",
        {"h": hecho_id, "m": a_mejora})
    return bool(fila[0]) or bool(posiciones_de_hecho(sesion, hecho_id))


def _json(sesion: SesionMotor, sql: str, params: tuple) -> str | None:
    fila = sesion.uno(sql, params)
    return None if fila is None else fila[0]


def _auditar(sesion: SesionMotor, tabla: str, registro: uuid.UUID, accion: str, antes: str | None,
             despues: str | None, motivo: str) -> None:
    auditoria.registrar(sesion, tabla=tabla, registro_id=registro, accion=accion, datos_antes_json=antes,
                        datos_despues_json=despues, motivo=motivo)


def _clase_de(tipo_efecto: str) -> str:
    return "MEJORA" if tipo_efecto == "VALOR_ACTIVO" else "GASTO"


def corregir_naturaleza_patrimonial(sesion: SesionMotor, *, propiedad_id: uuid.UUID, hecho_id: uuid.UUID,
                                    peticion: dict, reloj: Reloj = reloj_sistema) -> dict | Rechazo:
    p = peticion
    rechazo = _dto(p)                                                             # 1 DTO
    if rechazo:
        return Rechazo(rechazo)
    intencion = p["intencion_id"]
    a_mejora = p["clase_nueva"] == "MEJORA"
    s = sello(canonica(hecho_id, propiedad_id, p))
    # 2 locks: 0 -> 1 -> 2 -> 4 -> 7
    repo_comp.tomar_advisory_raiz(sesion, hecho_id)
    tomar_inversiones(sesion)
    raiz = gp.bloquear_propiedad_compartida(sesion, propiedad_id)
    if raiz is None:
        return Rechazo(gp.NO_ENCONTRADA)
    if not a_mejora:
        sesion.uno("SELECT id FROM gapto.categorias_financieras WHERE id = %s FOR SHARE", (p["categoria_id"],))
    if sesion.uno("SELECT 1 FROM gapto.hechos_financieros WHERE id = %s FOR NO KEY UPDATE", (hecho_id,)) is None:
        return Rechazo(gp.NO_ENCONTRADA)                                          # ajeno = inexistente (O5.26)
    bloquear_posiciones(sesion, posiciones_de_hecho(sesion, hecho_id))
    h = _hecho(sesion, hecho_id)
    efectos = _efectos(sesion, hecho_id)
    # 2bis: hecho ACTIVO con exactamente un efecto vigente (§III.3.3bis)
    if h["estado"] != "ACTIVO" or len(efectos) != 1:
        return Rechazo(NO_ADMITIDA)
    e0 = efectos[0]
    destino = "MEJORA_PATRIMONIAL" if a_mejora else "GASTO"
    # 3 identidad (§III.3.6)
    if e0["id"] == efecto_destino(intencion, s) and h["tipo"] == destino:          # fila a: replay exacto
        return {**(gp.leer_gasto(sesion, propiedad_id, hecho_id) or {}), "idempotente": True}
    if intencion != gp.intencion_vigente(e0["id"]):                               # fila c
        return Rechazo(NO_VIGENTE)
    # elegibilidad restante (v0.9 §III.3.2 puntos 2-6; §III.1ter)
    if h["tipo"] not in ("MEJORA_PATRIMONIAL", "GASTO"):
        return Rechazo(NO_ADMITIDA)
    if not (e0["tipo"] == "GASTO" or (e0["tipo"] == "VALOR_ACTIVO" and e0["causa"] == gp.CAUSA_MEJORA)):
        return Rechazo(NO_ADMITIDA)
    if not _procedencia(sesion, hecho_id, propiedad_id, e0["id"]):
        return Rechazo(NO_ADMITIDA)
    if _dependencias(sesion, hecho_id, a_mejora):
        return Rechazo(NO_ADMITIDA)
    if not gp.disponible(raiz):
        return Rechazo(gp.PROPIEDAD_NO_DISPONIBLE)
    if not a_mejora and h["localizacion"] == "NO_APLICA":                         # §III.1ter, guarda HF-03
        return Rechazo(NO_ADMITIDA)
    # version, periodo cerrado
    if h["row_version"] != p["row_version_esperada"]:
        return Rechazo(gp.VERSION_DESFASADA)
    if periodo_cerrado(sesion, [h["fecha"]]):
        return Rechazo(PERIODO_CERRADO)
    # presupuestable frente al estado REAL (§III.3.3 paso 7): la clase de efecto tiene que cambiar
    if (e0["tipo"] == "VALOR_ACTIVO") == a_mejora:
        return Rechazo(gp.ENTRADA_INVALIDA)
    presupuestable = False if a_mejora else bool(p["presupuestable"])
    if not a_mejora:
        rechazo = validar_seleccion_categoria(sesion, p["categoria_id"], "GASTO")
        if rechazo:
            return Rechazo(rechazo)
    # impacto bajo lock (§III.3.5)
    vista = gp.comparacion(fecha=h["fecha"], importe=Decimal(e0["importe"]), tipo_efecto=e0["tipo"],
                           clase_nueva=p["clase_nueva"], presupuestable_nuevo=p.get("presupuestable"))
    if vista != {k: str(v) for k, v in p["comparacion_vista"].items()}:
        return Rechazo(IMPACTO_DESFASADO)
    _escribir(sesion, hecho_id=hecho_id, h=h, e0=e0, e1_id=efecto_destino(intencion, s), destino=destino,
              a_mejora=a_mejora, categoria_id=None if a_mejora else p["categoria_id"], presupuestable=presupuestable,
              motivo=p["motivo"], resumen={"operacion": OPERACION, "intencion_id": str(intencion), "sello": s,
                                           "clase_antes": _clase_de(e0["tipo"]), "clase_despues": p["clase_nueva"],
                                           "comparacion_vista": vista})
    return {**(gp.leer_gasto(sesion, propiedad_id, hecho_id) or {}), "idempotente": False}


def _escribir(sesion: SesionMotor, *, hecho_id: uuid.UUID, h: dict, e0: dict, e1_id: uuid.UUID, destino: str,
              a_mejora: bool, categoria_id, presupuestable: bool, motivo: str, resumen: dict) -> None:
    hecho_json = ("SELECT json_build_object('tipo_hecho', th.codigo, 'presupuestable', h.presupuestable, "
                  "'row_version', h.row_version)::text FROM gapto.hechos_financieros h "
                  "JOIN gapto.tipos_hecho th ON th.id = h.tipo_hecho_id WHERE h.id = %s")
    # 1: tipo_hecho_id y presupuestable, row_version + 1 exacto
    antes = _json(sesion, hecho_json, (hecho_id,))
    fila = sesion.uno(
        "UPDATE gapto.hechos_financieros h SET tipo_hecho_id = (SELECT id FROM gapto.tipos_hecho WHERE codigo = %s), "
        "presupuestable = %s, row_version = h.row_version + 1, updated_at = CURRENT_TIMESTAMP "
        "WHERE h.id = %s AND h.row_version = %s AND h.estado = 'ACTIVO' RETURNING h.row_version",
        (destino, presupuestable, hecho_id, h["row_version"]))
    if fila is None:
        raise ErrorMotor(CodigoError.VERSION_DESFASADA, "El hecho ha cambiado.")
    _auditar(sesion, "hechos_financieros", hecho_id, auditoria.ACCION_ACTUALIZAR, antes,
             _json(sesion, hecho_json, (hecho_id,)), motivo)
    # 2: e1 por el repositorio comun (guarda comun de causa); nunca UPDATE en sitio de tipo_efecto
    creado = repo_efectos.insertar_efecto_si_no_existe(
        sesion, hecho_id, efecto_id=e1_id, tipo_efecto="VALOR_ACTIVO" if a_mejora else "GASTO",
        importe_delta=e0["importe"], estado_atribucion=e0["estado_atribucion"], categoria_id=categoria_id,
        descripcion=_json(sesion, "SELECT descripcion FROM gapto.hecho_efectos WHERE id = %s", (e0["id"],)),
        causa_valor_activo=gp.CAUSA_MEJORA if a_mejora else None)
    if creado is None:                                                            # PK ocupada (otro owner)
        raise ErrorMotor(CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION, "Identidad ya usada.")
    _auditar(sesion, "hecho_efectos", e1_id, auditoria.ACCION_CREAR, None, _json(sesion, _EFECTO_JSON, (e1_id,)),
             motivo)
    # 3: atribuciones copiadas
    with sesion.conexion.cursor() as cur:
        cur.execute("SELECT id, actor_id, importe_atribuido, criterio_atribucion, porcentaje_aplicado, "
                    "row_to_json(t)::text FROM gapto.efecto_atribuciones t WHERE efecto_id = %s ORDER BY actor_id",
                    (e0["id"],))
        atribuciones = cur.fetchall()
    for _, actor, importe, criterio, pct, _snap in atribuciones:
        nueva = uuid.uuid5(e1_id, f"gapto.f06.cmej03.atribucion:{actor}")
        if repo_efectos.insertar_atribucion_si_no_existe(
                sesion, atribucion_id=nueva, efecto_id=e1_id, actor_id=actor, importe_atribuido=importe,
                criterio_atribucion=criterio, porcentaje_aplicado=pct) is None:
            raise ErrorMotor(CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION, "Identidad ya usada.")
        _auditar(sesion, "efecto_atribuciones", nueva, auditoria.ACCION_CREAR, None,
                 _json(sesion, "SELECT row_to_json(t)::text FROM gapto.efecto_atribuciones t WHERE t.id = %s",
                       (nueva,)), motivo)
    # 4: reapuntar los vinculos de nivel efecto de e0 (conservan id, entidad, tipo y principal)
    with sesion.conexion.cursor() as cur:
        cur.execute("SELECT id, row_to_json(x)::text FROM gapto.hecho_entidades x WHERE x.hecho_id = %s "
                    "AND x.efecto_id = %s ORDER BY x.id", (hecho_id, e0["id"]))
        vinculos = cur.fetchall()
    for vid, antes_v in vinculos:
        sesion.ejecutar("UPDATE gapto.hecho_entidades SET efecto_id = %s WHERE id = %s AND efecto_id = %s",
                        (e1_id, vid, e0["id"]))
        _auditar(sesion, "hecho_entidades", vid, auditoria.ACCION_ACTUALIZAR, antes_v,
                 _json(sesion, "SELECT row_to_json(x)::text FROM gapto.hecho_entidades x WHERE x.id = %s", (vid,)),
                 motivo)
    # 5: atribuciones de e0 ANTES que e0 (FK RESTRICT inmediata)
    for aid, _a, _i, _c, _p, snap in atribuciones:
        sesion.ejecutar("DELETE FROM gapto.efecto_atribuciones WHERE id = %s", (aid,))
        _auditar(sesion, "efecto_atribuciones", aid, auditoria.ACCION_ANULAR, snap, None, motivo)
    # 6: e0, con el snapshot ampliado con la causa (§III.4)
    snap_e0 = _json(sesion, _EFECTO_JSON, (e0["id"],))
    sesion.ejecutar("DELETE FROM gapto.hecho_efectos WHERE id = %s AND hecho_id = %s", (e0["id"], hecho_id))
    _auditar(sesion, "hecho_efectos", e0["id"], auditoria.ACCION_ANULAR, snap_e0, None, motivo)
    # 8 y 9: guardas de defensa del estado final
    finales = _efectos(sesion, hecho_id)
    vinculos_e1 = sesion.uno("SELECT count(*) FROM gapto.hecho_entidades WHERE hecho_id = %s AND efecto_id = %s",
                             (hecho_id, e1_id))[0]
    if (len(finales) != 1 or finales[0]["id"] != e1_id
            or finales[0]["estado_atribucion"] != e0["estado_atribucion"]
            or (finales[0]["causa"] == gp.CAUSA_MEJORA) != a_mejora
            or vinculos_e1 != len(vinculos)):
        raise ErrorMotor(CodigoError.VIOLACION_INVARIANTE_FISICA, "Estado final incoherente en C-MEJ-03.")
    # 10: auditoria resumen en el hecho
    _auditar(sesion, "hechos_financieros", hecho_id, auditoria.ACCION_ACTUALIZAR, None,
             json.dumps({**resumen, "e0": str(e0["id"]), "e1": str(e1_id)}, ensure_ascii=False), motivo)
