# ============================================================
# GAPTO MOBILE 2027
# Fichero: lecturas.py
# Ruta: backend/app/plantillas/lecturas.py
# Descripcion: Lecturas de plantillas y acciones rapidas para Inicio y
#   Ajustes › Plantillas (F05-03 J2 §1.9; lamina SET-PLT / REG-PLT / HOME-QA
#   v0.2, S01 «No disponible»). Solo lectura, sin locks, RLS del tenant.
#   - `listar`: todas las plantillas del owner (habilitadas o no) en orden
#     estable (nombre normalizado, id) con `avisos`: campos que HOY no se
#     aplicarian (categoria no elegible para su tipo, cuenta no elegible para
#     la operacion del tipo en la fecha funcional del owner, tercero o
#     contexto desactivados o ajenos). Solo informa: nunca corrige la
#     plantilla ni la desactiva.
#   - `acciones`: acciones rapidas HABILITADAS del owner en el orden de
#     Inicio (orden, id), con el tipo de su plantilla (ver iconos en el
#     cliente: icono_key o el de la categoria).
# Version: 0.1.0 (F05-03/F05-04 J2 §1.6)
# ============================================================

from __future__ import annotations

from typing import Any

from app.api.elegibilidad_categoria import ambito_compatible
from app.categorias.normalizacion import normalizar
from app.comun.elegibilidad_cuentas import motivo_cuenta
from app.comun.fecha_funcional import Reloj, hoy_owner, reloj_sistema
from app.core.unidad_trabajo import SesionMotor
from app.plantillas import repositorio as repo


def _codigos_tipo(sesion: SesionMotor) -> dict:
    with sesion.conexion.cursor() as cur:
        cur.execute("SELECT id, codigo FROM gapto.tipos_hecho")
        return dict(cur.fetchall())


def _avisos(sesion: SesionMotor, p: dict[str, Any], tipo: str | None, hoy) -> list[dict[str, str]]:
    avisos: list[dict[str, str]] = []
    owner = " AND owner_user_id = current_setting('gapto.owner_user_id')::uuid"
    if p["categoria_id"] is not None:
        f = sesion.uno("SELECT enabled, ambito FROM gapto.categorias_financieras WHERE id = %s" + owner,
                       (p["categoria_id"],))
        if f is None or not f[0] or tipo is None or not ambito_compatible(tipo, f[1]):
            avisos.append({"campo": "categoria", "motivo": "NO_ELEGIBLE"})
    if p["cuenta_default_id"] is not None and (
        tipo not in ("GASTO", "INGRESO") or motivo_cuenta(sesion, p["cuenta_default_id"], tipo, hoy) is not None
    ):
        avisos.append({"campo": "cuenta", "motivo": "NO_ELEGIBLE"})
    if p["tercero_id"] is not None:
        f = sesion.uno("SELECT enabled FROM gapto.terceros WHERE id = %s" + owner, (p["tercero_id"],))
        if f is None or not f[0]:
            avisos.append({"campo": "tercero", "motivo": "NO_ELEGIBLE"})
    if p["entidad_id"] is not None:
        f = sesion.uno("SELECT enabled, tipo_entidad FROM gapto.entidades WHERE id = %s" + owner, (p["entidad_id"],))
        if f is None or not f[0] or f[1] != "CONTEXTO":
            avisos.append({"campo": "contexto", "motivo": "NO_ELEGIBLE"})
    return avisos


def listar(sesion: SesionMotor, reloj: Reloj = reloj_sistema) -> list[dict[str, Any]]:
    hoy = hoy_owner(sesion, reloj)
    tipos = _codigos_tipo(sesion)
    salida = []
    for p in repo.plantillas(sesion):
        tipo = tipos.get(p["tipo_hecho_id"])
        salida.append({**p, "tipo": tipo, "avisos": _avisos(sesion, p, tipo, hoy)})
    return sorted(salida, key=lambda x: (normalizar(x["nombre"]), str(x["id"])))


def acciones(sesion: SesionMotor) -> list[dict[str, Any]]:
    return [a for a in repo.acciones(sesion) if a["enabled"]]
