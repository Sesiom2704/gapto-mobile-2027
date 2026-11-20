# ============================================================
# GAPTO MOBILE 2027
# Fichero: f06_02_03_helpers.py
# Ruta: tests/api/f06_02_03_helpers.py
# Descripcion: Helpers de las pruebas de F06-02/03 (contratos de alquiler, servicios y terceros SIN RENTA):
#   entorno con reloj fijo en 2026-11-18 (el «hoy» de los oraculos O-1a/O-1b), propiedades con habitaciones,
#   cuerpos de alta, personas, rechazos y huella SHA-256 del estado completo (patron de f06_01_b1_helpers: un
#   rechazo debe dejar la huella IDENTICA). Se ejecutan por HTTP como gapto_runtime con RLS (adaptador real).
# Version: 0.1.0 (F06 T3-F06 Bloque 3, pasos 3 y 4; escrito sin ejecutar: la base no esta disponible esta noche)
# ============================================================

from __future__ import annotations

import uuid

import f05_05_helpers as x5
import f06_01_b1_helpers as b
import vs01_api_helpers as h

HOY = "2026-11-18"
RELOJ = "2026-11-18T12:00:00"
TABLAS_RENTA = ("reglas_financieras", "regla_versiones", "previsiones", "hechos_financieros", "hecho_efectos",
                "hecho_entidades", "movimientos_tesoreria")
huella = b.huella


def entorno(iso: str = RELOJ):
    """(owner, actor_self, cliente con reloj fijo)."""
    owner, actor, cli, _, _ = x5.entorno(iso)
    return owner, actor, cli


def propiedad(cli, *, habitaciones: int | None = 4, nombre: str = "Piso Gran Vía") -> uuid.UUID:
    extra = {} if habitaciones is None else {"habitaciones": habitaciones}
    p = b.crear(cli, b.alta(b.solo_mia("2025-01-01"), nombre=nombre, **extra))
    return uuid.UUID(p["id"])


def tercero(cli, nombre: str, naturaleza: str | None = "PERSONA") -> uuid.UUID:
    return b.tercero(cli, nombre, naturaleza)


# ---------------------------------------------------------------- personas
def yo(rol: str, principal: bool = False) -> dict:
    return {"actor": "YO", "rol": rol, "principal": principal}


def de(tercero_id, rol: str, principal: bool = False) -> dict:
    return {"actor": {"tercero_id": str(tercero_id)}, "rol": rol, "principal": principal}


def nuevo(nombre: str, rol: str, principal: bool = False, naturaleza: str | None = "EMPRESA", id_=None) -> dict:
    return {"actor": {"nuevo_tercero": {"id": str(id_ or uuid.uuid4()), "nombre": nombre, "naturaleza": naturaleza}},
            "rol": rol, "principal": principal}


def partes(inquilino_id) -> list[dict]:
    """Propietario (yo, principal) e inquilino principal: lo minimo para formalizar."""
    return [yo("PROPIETARIO", True), de(inquilino_id, "INQUILINO", True)]


# ---------------------------------------------------------------- contratos
def alta_cuerpo(propiedad_id, *, tipo: str = "HABITACION", habitacion: int | None = 1, estado: str = "FORMALIZADO",
                inicio: str | None = "2026-09-01", personas: list[dict] | None = None, intencion_id=None,
                nombre: str | None = None, **extra) -> dict:
    cuerpo = {"intencion_id": str(intencion_id or uuid.uuid4()), "propiedad_id": str(propiedad_id), "tipo": tipo,
              "nombre": nombre or f"26-{tipo[:3]}{habitacion or ''}", "estado": estado}
    if habitacion is not None:
        cuerpo["habitacion"] = habitacion
    if inicio is not None:
        cuerpo["fecha_inicio"] = inicio
    if personas is not None:
        cuerpo["personas"] = personas
    cuerpo.update(extra)
    return cuerpo


def post(cli, ruta: str, cuerpo: dict):
    return cli.post(ruta, json=cuerpo, headers=h.AUTH)


def get(cli, ruta: str):
    return cli.get(ruta, headers=h.AUTH)


def alta(cli, propiedad_id, **kw):
    return post(cli, "/v1/intenciones/contrato-alquiler", alta_cuerpo(propiedad_id, **kw))


def crear(cli, propiedad_id, **kw) -> dict:
    """Alta que debe salir bien; devuelve el contrato completo (L-CON-02)."""
    r = alta(cli, propiedad_id, **kw)
    assert r.status_code == 200, r.text
    return r.json()["contrato"]


def crear_firmado(cli, propiedad_id, inquilino_id, **kw) -> dict:
    return crear(cli, propiedad_id, personas=partes(inquilino_id), **kw)


def leer(cli, contrato_id) -> dict:
    r = get(cli, f"/v1/contratos/{contrato_id}")
    assert r.status_code == 200, r.text
    return r.json()["contrato"]


def ruta(contrato_id, sufijo: str = "") -> str:
    return f"/v1/contratos/{contrato_id}{sufijo}"


def cuerpo_v(contrato: dict, **extra) -> dict:
    """Cuerpo de una escritura sobre un contrato con la version que el cliente leyo."""
    cuerpo = {"intencion_id": str(uuid.uuid4()), "row_version_esperada": contrato["row_version"]}
    cuerpo.update(extra)
    return cuerpo


def rechazo(r, status: int, codigo: str, motivo: str | None = None):
    assert r.status_code == status, r.text
    cuerpo = r.json()
    assert cuerpo["codigo"] == codigo, r.text
    if motivo is not None:
        assert cuerpo["motivo"] == motivo, r.text
    return cuerpo


def rechazo_sin_cambios(cli, r, status: int, codigo: str, antes: str, motivo: str | None = None):
    """Rechazo y huella IDENTICA a la de antes (el rechazo no deja ni una fila ni un row_version distintos)."""
    rechazo(r, status, codigo, motivo)
    assert huella() == antes, f"{codigo}: el rechazo modifico el estado"


def uno(owner, sql: str, params: tuple = ()):
    return h.leer(owner, sql, params)[0][0]


def filas_renta(owner) -> int:
    """Total de filas en las tablas de renta, reglas, previsiones y hechos (debe ser 0 en un owner nuevo)."""
    return sum(uno(owner, f"SELECT count(*) FROM gapto.{t}") for t in TABLAS_RENTA)


def servicio(cli, propiedad_id, *, tipo: str = "LUZ", nombre: str = "Luz", desde: str = "2026-01-01", **extra) -> uuid.UUID:
    sid = uuid.uuid4()
    cuerpo = {"intencion_id": str(sid), "tipo_servicio": tipo, "nombre": nombre, "propiedad_id": str(propiedad_id),
              "desde": desde}
    cuerpo.update(extra)
    r = post(cli, "/v1/intenciones/servicio", cuerpo)
    assert r.status_code == 200, r.text
    return sid


def con_regla_renta(owner, contrato_id) -> None:
    """Fixture de DATO MIGRADO DE V3: un contrato con `regla_renta_id` (los writers del bloque no lo escriben).
    Se fija con SQL bajo gapto_owner. SIN EJECUTAR: la forma minima de la regla debe confirmarse con la base."""
    regla = uuid.uuid4()
    h.como_owner(owner, "INSERT INTO gapto.reglas_financieras (id, owner_user_id, nombre) "
                        "VALUES (%s, current_setting('gapto.owner_user_id')::uuid, 'Renta migrada V3')", (regla,))
    h.como_owner(owner, "UPDATE gapto.contratos SET regla_renta_id = %s WHERE entidad_id = %s", (regla, contrato_id))
