# ============================================================
# GAPTO MOBILE 2027
# Fichero: rv3_p5_transformacion.py
# Ruta: scripts/migration_v3/rv3_p5_transformacion.py
# Descripcion: RV3 / P5. Transformacion B0 (y S1 por las mismas reglas) hacia
#              el contrato fisico 0330, por dominios del plan R2:
#                1 tenant/geografia   (IMPLEMENTADO v0.1.0)
#                2 maestros: terceros, personas, clasificaciones de tercero
#                  (IMPLEMENTADO PARCIAL v0.2.0; categorias, roles y direcciones
#                  pendientes de decision/dominio)
#                3 cuentas (IMPLEMENTADO v0.3.0; configuracion sin dato V3 bajo
#                  PROPUESTA pendiente de confirmacion del propietario -> S20)
#               12 importacion: fuente + registros origen + mapeos (base)
#               2..11 pendientes.
#   Principios aplicados en codigo:
#     - identidad UUIDv5 canonica v3|contenedor|clave|tabla|rol (rv3_fuente);
#     - todo destino creado lleva al menos un mapeo a su registro origen;
#     - colision de identidad o de clave natural -> fallo cerrado (S7);
#     - ausencia/UNKNOWN nunca se convierte en valor; un NOT NULL sin fuente
#       solo se cubre por una regla de ledger declarada y visible;
#     - el dataset se serializa ordenado y se resume en un hash determinista;
#     - pendientes S20 bloquean la fila afectada: se conserva su origen y se
#       registra, sin crear destino.
#   Validacion fisica: carga el dataset en UNA transaccion bajo el perfil
#   RV3_IMPORT (rol login no superusuario -> gapto_migrator -> gapto_owner),
#   fuerza los diferidos con SET CONSTRAINTS ALL IMMEDIATE y hace ROLLBACK.
#   No es P6 (P6 hace COMMIT real).
# Versión: 0.3.0
# ============================================================
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

VERSION = "0.3.0"
TRANSFORMACION = "RV3_P5"
_AQUI = Path(__file__).resolve().parent


def _cargar(nombre: str):
    spec = importlib.util.spec_from_file_location(nombre, _AQUI / f"{nombre}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = mod
    spec.loader.exec_module(mod)
    return mod


fu = _cargar("rv3_fuente")

# Orden de insercion: padres antes que hijos (FK inmediatas de 0330).
ORDEN_TABLAS = [
    "usuarios", "paises", "regiones", "localidades", "actores_financieros",
    "terceros", "tercero_personas", "clasificaciones_tercero", "tercero_clasificaciones",
    "cuentas", "cuenta_participaciones",
    "fuentes_importacion", "registros_origen_importacion", "mapeos_importacion",
]

# Autorreferencias: el padre se inserta antes que el hijo (orden por profundidad).
AUTOREF = {"regiones": "parent_region_id", "clasificaciones_tercero": "parent_id"}

# Dominio 3. Convencion de corte de la simulacion (Migration V3 §29, RUN03):
# corte logico 2026-09-04, ledger exacto desde 2026-09-05. saldo_apertura = liquidez V3.
FECHA_INICIO_LEDGER = "2026-09-05"
# Configuracion de cuenta SIN dato V3 (DB Schema §22: NOT NULL y sin default fisico).
# Estado PROPUESTA: la carga falla cerrada (S20) salvo confirmacion del propietario o
# modo laboratorio explicito, que deja la marca PROPUESTA_NO_CONFIRMADA en el ledger.
# clave -> (tipo, naturaleza, computa_liquidez, computa_patrimonio, permite_negativo, moneda)
CONFIG_CUENTAS = {
    ("public.cuentas_bancarias", "BANCO-0TBZZI"): ("EFECTIVO", "ACTIVO", True, True, True, "EUR"),
    ("public.cuentas_bancarias", "BANCO-96C620E0"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR"),
    ("public.cuentas_bancarias", "BANCO-679A92B7"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR"),
    ("public.cuentas_bancarias", "CTA-H3PG1R"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR"),
    ("public.cuentas_bancarias", "BANCO-A6791418"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR"),
    ("public.cuentas_bancarias", "BANCO-DF92A62D"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR"),
    ("public.cuentas_bancarias", "CTA-Z4QIC5"): ("CREDITO", "PASIVO", False, True, True, "EUR"),
    ("public.inversion", "INV-F28AEAD467"): ("AHORRO", "ACTIVO", True, True, False, "EUR"),
    ("public.gastos", "gasto-xg1mue"): ("PREPAGO", "ACTIVO", True, True, False, None),
}
CONFIG_CUENTAS_ESTADO = "PROPUESTA"
# Cuentas sin fila maestra V3 (Migration V3 §14/§29): origen, nombre, gestor V3.
CUENTAS_DERIVADAS = {
    ("public.inversion", "INV-F28AEAD467"): ("CUENTA AHORRO", "proveedor_id"),
    ("public.gastos", "gasto-xg1mue"): ("REVOLUT", None),
}
GESTOR_REVOLUT = "PROV-UH1DM1"

# Tablas cuya PK no es la columna id.
PK = {"tercero_personas": "tercero_id"}

# Reference data geografica versionada (DB Schema: geografia = reference data
# separada). Decision de ejecucion H-P5-01, PROVISIONAL hasta conformidad.
REF_GEO = "REF_GEO_ISO3166_V1"
REF_PAISES = {"ESPAÑA": ("ES", "ESP")}

# Reglas de ledger declaradas (visibles en el informe).
LEDGER_REGLAS = {
    "H-P5-01": "paises.iso2/iso3 NOT NULL; V3 codigo_iso=141 (ausencia). Se vincula por nombre "
               "exacto a " + REF_GEO + "; literal 141 conservado en origen. PROVISIONAL.",
    "H-P5-02": "regiones V3 mezclan niveles; tipo_region y parent_region_id quedan NULL "
               "(sin jerarquia inventada). PROVISIONAL.",
    "H-P5-03": "usuarios.timezone/locale NOT NULL sin dato V3; se deja actuar el DEFAULT de "
               "configuracion del contrato (no es hecho financiero). PROVISIONAL.",
    "H-P5-04": "terceros desde proveedores: naturaleza NULL y sin roles; ni EMPRESA ni COMERCIO "
               "se deducen del nombre o la rama. Los roles se asignan en el dominio que los demuestre.",
    "H-P5-05": "proveedores.persona_contacto (sin columna destino) se conserva en terceros.notas "
               "con etiqueta de origen. PROVISIONAL.",
    "H-P5-06": "terceros desde personas: enabled sin dato V3 (inactivatedon=141) -> DEFAULT del "
               "contrato. PROVISIONAL.",
    "D2-C": "persona V3 cuyo email coincide con el del tenant = el propio usuario: se VINCULA a "
            "usuarios y NO se crea tercero (C43/R-RV3-008). DNI/telefono/nacimiento no tienen "
            "destino en usuarios: perdida de detalle CANDIDATA R24, pendiente de aceptacion.",
    "D3-A": "configuracion de cuenta sin dato V3 (tipo, naturaleza, computa_*, permite_negativo, "
            "moneda Revolut) -> tabla CONFIG_CUENTAS en estado PROPUESTA; requiere confirmacion (S20).",
    "D3-B": "cuenta_participaciones.vigente_desde NOT NULL; V3 no da inicio real. Se usa "
            "FECHA_INICIO_LEDGER con semantica 'conocida desde el corte', sin afirmar el pasado. PROPUESTA.",
    "D3-C": "ahorro remunerado y Revolut sin saldo V3: saldo_apertura y fecha_inicio_ledger NULL "
            "(PENDIENTE_DATO_CORTE, Migration V3 §29). Ni 930/937,83 ni 250 se interpretan como saldo.",
    "D3-D": "cuenta_capacidades sin fuente V3: no se crean filas (RUN06 creo 21 sin origen).",
    "DV-10": "RUN06 cuentas contradice DB Schema §22: T. CREDITO como corriente/computa_liquidez; y "
             "permite_negativo=false con CASH en -30,00. Prevalece el contrato.",
    "DV-9": "RUN06 no materializo clasificaciones_tercero ni tercero_clasificaciones pese a que V3 "
            "tiene 22 ramas + 34 subsegmentos con jerarquia demostrada; RV3 las conserva (R26).",
}


class ErrorP5(Exception):
    """Fallo cerrado tipado."""

    def __init__(self, codigo: str, detalle: str):
        super().__init__(f"{codigo}: {detalle}")
        self.codigo = codigo


@dataclass
class Dataset:
    owner: str
    filas: dict = field(default_factory=lambda: {t: {} for t in ORDEN_TABLAS})
    naturales: dict = field(default_factory=dict)
    ledger: list = field(default_factory=list)
    pendientes: list = field(default_factory=list)

    def add(self, tabla: str, fila: dict, natural: tuple | None = None) -> str:
        fid = fila[PK.get(tabla, "id")]
        if fid in self.filas[tabla]:
            if self.filas[tabla][fid] != fila:
                raise ErrorP5("S7_COLISION_UUID", f"{tabla}/{fid}")
            return fid
        if natural is not None:
            k = (tabla,) + natural
            if k in self.naturales and self.naturales[k] != fid:
                raise ErrorP5("S7_COLISION_CLAVE_NATURAL", str(k))
            self.naturales[k] = fid
        self.filas[tabla][fid] = fila
        return fid

    def mapear(self, cont: str, clave: str, tabla: str, destino: str, rol: str,
               tipo: str = "CREADO", confianza: str = "ALTA", notas: str | None = None) -> None:
        origen = fu.uuid_origen(cont, clave)
        mid = fu.uuid_v3(cont, clave, "mapeos_importacion", f"{tabla}.{rol}")
        self.add("mapeos_importacion", {
            "id": mid, "registro_origen_id": origen, "tabla_destino": tabla,
            "registro_destino_id": destino, "tipo_mapping": tipo,
            "transformacion_codigo": f"{TRANSFORMACION}.{tabla}.{rol}",
            "transformacion_version": VERSION, "confianza": confianza, "notas": notas})

    def hash(self) -> str:
        cuerpo = {t: [self.filas[t][k] for k in sorted(self.filas[t])] for t in ORDEN_TABLAS}
        s = json.dumps(cuerpo, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=_j)
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    def recuentos(self) -> dict:
        return {t: len(self.filas[t]) for t in ORDEN_TABLAS}


def _j(o):
    if isinstance(o, Decimal):
        return str(o)
    raise TypeError(type(o))


def _celda(cont, col, fila, ctx):
    return fu.normalizar(cont, col, fila.get(col), fila, ctx)


def _texto(c) -> str | None:
    return None if c.valor is None else str(c.valor).strip() or None


# ------------------------------------------------------------ dominio 12 base
def dominio_12_trazabilidad(ds: Dataset, b0: dict, sha_run06: str) -> str:
    fid = fu.uuid_v3("RUN06", sha_run06, "fuentes_importacion", "fuente")
    ds.add("fuentes_importacion", {
        "id": fid, "owner_user_id": ds.owner, "tipo_fuente": "XLSX",
        "nombre_fuente": "RUN06 B0 snapshot origen (RV3-D002)",
        "version_fuente": "RUN06_v08", "pipeline_version": f"{TRANSFORMACION} {VERSION}",
        "sha256": sha_run06, "estado": "SIMULADA",
        "notas": f"datos_origen_texto = {fu.SEMANTICA_TEXTO}; sha256_registro = {fu.ALGORITMO_HASH_REGISTRO}"})
    for cont in sorted(b0):
        for clave in sorted(b0[cont]):
            r = b0[cont][clave]
            ds.add("registros_origen_importacion", {
                "id": fu.uuid_origen(cont, clave), "fuente_importacion_id": fid,
                "contenedor_origen": cont, "clave_origen": clave,
                "numero_fila_origen": r.numero_fila_origen, "datos_origen": r.datos,
                "datos_origen_texto": r.texto, "sha256_registro": r.sha256_registro},
                natural=(cont, clave))
    return fid


# ------------------------------------------------------------ dominio 1
def owner_de(clave_user: str) -> str:
    return fu.uuid_v3("public.users", clave_user, "usuarios", "tenant")


def dominio_1(ds: Dataset, fuente: dict, ctx: dict) -> None:
    users = fuente["public.users"]
    if len(users) != 1:
        raise ErrorP5("S20_TENANT", f"{len(users)} filas users; RV3 espera un unico tenant")
    (cu, u), = users.items()
    email = _texto(_celda("public.users", "email", u, ctx))
    nombre = _texto(_celda("public.users", "full_name", u, ctx))
    if not email or not nombre:
        raise ErrorP5("S6_TENANT_INCOMPLETO", "email/nombre ausente en users")
    ds.add("usuarios", {"id": ds.owner, "email": email, "nombre": nombre}, natural=(email,))
    ds.mapear("public.users", cu, "usuarios", ds.owner, "tenant")
    ds.ledger.append({"regla": "H-P5-03", "origen": f"public.users/{cu}"})
    # Actor self: obligatorio por contrato (exactamente uno, tercero_id NULL).
    self_id = fu.uuid_v3("public.users", cu, "actores_financieros", "self")
    ds.add("actores_financieros", {"id": self_id, "owner_user_id": ds.owner, "tercero_id": None},
           natural=(ds.owner, None))
    ds.mapear("public.users", cu, "actores_financieros", self_id, "self", tipo="CREADO",
              notas="actor self derivado del tenant (obligatorio por contrato)")

    pais_de = {}
    for cp, p in sorted(fuente.get("public.paises", {}).items()):
        nom = _texto(_celda("public.paises", "nombre", p, ctx))
        iso_c = _celda("public.paises", "codigo_iso", p, ctx)
        if nom not in REF_PAISES:
            raise ErrorP5("S4_PAIS_SIN_REFERENCIA", f"{cp}")
        iso2, iso3 = REF_PAISES[nom]
        if iso_c.estado == fu.CONOCIDO and str(iso_c.valor) not in (iso2, iso3):
            raise ErrorP5("S1_ISO_CONTRADICTORIO", f"{cp}")
        pid = fu.uuid_v3("public.paises", cp, "paises", "pais")
        ds.add("paises", {"id": pid, "iso2": iso2, "iso3": iso3, "nombre": nom}, natural=(iso2,))
        ds.mapear("public.paises", cp, "paises", pid, "pais", confianza="VALIDADA",
                  notas=f"iso desde {REF_GEO} por nombre exacto (H-P5-01)")
        ds.ledger.append({"regla": "H-P5-01", "origen": f"public.paises/{cp}"})
        pais_de[str(p["id"])] = pid

    region_de = {}
    for cr, r in sorted(fuente.get("public.regiones", {}).items()):
        pais = pais_de.get(str(r.get("pais_id")))
        if pais is None:
            raise ErrorP5("S8_HUERFANO", f"public.regiones/{cr} pais_id")
        rid = fu.uuid_v3("public.regiones", cr, "regiones", "region")
        ds.add("regiones", {"id": rid, "pais_id": pais, "parent_region_id": None,
                            "nombre": _texto(_celda("public.regiones", "nombre", r, ctx)),
                            "tipo_region": None, "codigo_oficial": None})
        ds.mapear("public.regiones", cr, "regiones", rid, "region")
        ds.ledger.append({"regla": "H-P5-02", "origen": f"public.regiones/{cr}"})
        region_de[str(r["id"])] = rid

    for cl, loc in sorted(fuente.get("public.localidades", {}).items()):
        reg = region_de.get(str(loc.get("region_id")))
        if reg is None:
            raise ErrorP5("S8_HUERFANO", f"public.localidades/{cl} region_id")
        cpost = _celda("public.localidades", "codigo_postal", loc, ctx)
        codigo = _texto(cpost) if cpost.estado == fu.CONOCIDO else None
        lid = fu.uuid_v3("public.localidades", cl, "localidades", "localidad")
        ds.add("localidades", {"id": lid, "region_id": reg,
                               "nombre": _texto(_celda("public.localidades", "nombre", loc, ctx)),
                               "codigo_oficial": codigo,
                               "codigo_oficial_tipo": "CODIGO_POSTAL" if codigo else None})
        ds.mapear("public.localidades", cl, "localidades", lid, "localidad")


# ------------------------------------------------------------ dominio 2
def _conocido(cont, col, fila, ctx):
    c = _celda(cont, col, fila, ctx)
    return _texto(c) if c.estado == fu.CONOCIDO else None


def dominio_2(ds: Dataset, fuente: dict, ctx: dict) -> None:
    email_tenant = ds.filas["usuarios"][ds.owner]["email"].casefold()
    # Clasificaciones de tercero: rama (raiz) -> subsegmento (hijo), jerarquia de V3.
    clas_de = {}
    for cr, r in sorted(fuente.get("public.tipo_ramas_proveedores", {}).items()):
        cid = fu.uuid_v3("public.tipo_ramas_proveedores", cr, "clasificaciones_tercero", "rama")
        ds.add("clasificaciones_tercero", {
            "id": cid, "owner_user_id": ds.owner, "parent_id": None, "codigo": None,
            "nombre": _conocido("public.tipo_ramas_proveedores", "nombre", r, ctx)},
            natural=(ds.owner, None, _conocido("public.tipo_ramas_proveedores", "nombre", r, ctx)))
        ds.mapear("public.tipo_ramas_proveedores", cr, "clasificaciones_tercero", cid, "rama")
        clas_de[("R", str(r["id"]))] = cid
    for cs, sg in sorted(fuente.get("public.tipo_subsegmentos_provee", {}).items()):
        padre = clas_de.get(("R", str(sg.get("rama_id"))))
        if padre is None:
            raise ErrorP5("S8_HUERFANO", f"public.tipo_subsegmentos_provee/{cs} rama_id")
        nom = _conocido("public.tipo_subsegmentos_provee", "nombre", sg, ctx)
        act = _celda("public.tipo_subsegmentos_provee", "activo", sg, ctx)
        cid = fu.uuid_v3("public.tipo_subsegmentos_provee", cs, "clasificaciones_tercero", "subsegmento")
        fila = {"id": cid, "owner_user_id": ds.owner, "parent_id": padre, "codigo": None, "nombre": nom}
        if act.estado == fu.CONOCIDO:
            fila["enabled"] = bool(act.valor)
        ds.add("clasificaciones_tercero", fila, natural=(ds.owner, padre, nom))
        ds.mapear("public.tipo_subsegmentos_provee", cs, "clasificaciones_tercero", cid, "subsegmento")
        clas_de[("S", str(sg["id"]))] = (cid, padre)
    ds.ledger.append({"regla": "DV-9", "origen": "public.tipo_ramas_proveedores+tipo_subsegmentos_provee"})

    for cp, pv in sorted(fuente.get("public.proveedores", {}).items()):
        cont = "public.proveedores"
        tid = fu.uuid_v3(cont, cp, "terceros", "tercero")
        contacto = _conocido(cont, "persona_contacto", pv, ctx)
        act = _celda(cont, "activo", pv, ctx)
        fila = {"id": tid, "owner_user_id": ds.owner, "nombre": _conocido(cont, "nombre", pv, ctx),
                "naturaleza": None, "identificador_fiscal": _conocido(cont, "cif", pv, ctx),
                "tipo_identificador_fiscal": None, "pais_fiscal_id": None,
                "email": _conocido(cont, "email", pv, ctx), "telefono": _conocido(cont, "telefono", pv, ctx),
                "notas": f"Persona de contacto (V3): {contacto}" if contacto else None}
        if act.estado == fu.CONOCIDO:
            fila["enabled"] = bool(act.valor)
        if not fila["nombre"]:
            raise ErrorP5("S4_TERCERO_SIN_NOMBRE", f"{cont}/{cp}")
        ds.add("terceros", fila)
        ds.mapear(cont, cp, "terceros", tid, "tercero")
        ds.ledger.append({"regla": "H-P5-04", "origen": f"{cont}/{cp}"})
        if contacto:
            ds.ledger.append({"regla": "H-P5-05", "origen": f"{cont}/{cp}"})
        sub = clas_de.get(("S", str(pv.get("subsegmento_id")))) if _celda(cont, "subsegmento_id", pv, ctx).estado == fu.CONOCIDO else None
        rama = clas_de.get(("R", str(pv.get("rama_id"))))
        if sub is not None and sub[1] != rama:
            raise ErrorP5("S1_RAMA_SUBSEGMENTO_INCOHERENTE", f"{cont}/{cp}")
        destino = sub[0] if sub is not None else rama
        if destino is None:
            raise ErrorP5("S8_HUERFANO", f"{cont}/{cp} rama_id")
        tcid = fu.uuid_v3(cont, cp, "tercero_clasificaciones", "clasificacion")
        ds.add("tercero_clasificaciones", {"id": tcid, "tercero_id": tid, "clasificacion_id": destino,
                                           "principal": True}, natural=(tid, destino))
        ds.mapear(cont, cp, "tercero_clasificaciones", tcid, "clasificacion")

    propias = [cp for cp, pe in fuente.get("public.personas", {}).items()
               if (_conocido("public.personas", "email", pe, ctx) or "").casefold() == email_tenant]
    if len(propias) > 1:
        raise ErrorP5("S20_PERSONA_PROPIA_AMBIGUA", str(sorted(propias)))
    for cp, pe in sorted(fuente.get("public.personas", {}).items()):
        cont = "public.personas"
        if cp in propias:
            ds.mapear(cont, cp, "usuarios", ds.owner, "persona_propia", tipo="VINCULADO",
                      notas="persona del propio tenant; no se crea tercero (C43)")
            ds.ledger.append({"regla": "D2-C", "origen": f"{cont}/{cp}"})
            continue
        tid = fu.uuid_v3(cont, cp, "terceros", "tercero")
        ds.add("terceros", {"id": tid, "owner_user_id": ds.owner,
                            "nombre": _conocido(cont, "nombre_completo", pe, ctx), "naturaleza": "PERSONA",
                            "identificador_fiscal": _conocido(cont, "dni", pe, ctx),
                            "tipo_identificador_fiscal": None, "pais_fiscal_id": None,
                            "email": _conocido(cont, "email", pe, ctx), "telefono": _conocido(cont, "telefono", pe, ctx),
                            "notas": _conocido(cont, "observaciones", pe, ctx)})
        ds.mapear(cont, cp, "terceros", tid, "tercero", tipo="DIVIDIDO")
        ds.add("tercero_personas", {"tercero_id": tid,
                                    "fecha_nacimiento": _conocido(cont, "fecha_nacimiento", pe, ctx)})
        ds.mapear(cont, cp, "tercero_personas", tid, "persona", tipo="DIVIDIDO")
        ds.ledger.append({"regla": "H-P5-06", "origen": f"{cont}/{cp}"})


# ------------------------------------------------------------ dominio 3
def dominio_3(ds: Dataset, fuente: dict, ctx: dict, modo_lab: bool) -> None:
    if CONFIG_CUENTAS_ESTADO != "CONFIRMADA":
        if not modo_lab:
            raise ErrorP5("S20_CONFIG_CUENTAS", "configuracion de cuentas sin dato V3 pendiente de confirmacion")
        ds.pendientes.append({"S20": "CONFIG_CUENTAS", "estado": "PROPUESTA_NO_CONFIRMADA"})
    self_id = next(iter(ds.filas["actores_financieros"]))

    def tercero(cont_prov_clave):
        tid = fu.uuid_v3("public.proveedores", cont_prov_clave, "terceros", "tercero")
        if tid not in ds.filas["terceros"]:
            raise ErrorP5("S8_HUERFANO", f"gestor {cont_prov_clave}")
        return tid

    def crear(cont, clave, nombre, gestor, saldo, activo):
        tipo, nat, liq, pat, neg, mon = CONFIG_CUENTAS[(cont, clave)]
        if mon is None:
            # moneda NOT NULL sin default y no demostrada: nunca se rellena.
            if not modo_lab:
                raise ErrorP5("S6_MONEDA_NO_DEMOSTRADA", f"{cont}/{clave}")
            ds.pendientes.append({"S20": "MONEDA_NO_DEMOSTRADA", "origen": f"{cont}/{clave}",
                                  "efecto": "cuenta NO creada en modo laboratorio"})
            return None
        cid = fu.uuid_v3(cont, clave, "cuentas", "cuenta")
        ds.add("cuentas", {"id": cid, "owner_user_id": ds.owner, "nombre": nombre, "tercero_gestor_id": gestor,
                           "tipo": tipo, "naturaleza": nat, "moneda": mon, "saldo_apertura": saldo,
                           "fecha_inicio_ledger": FECHA_INICIO_LEDGER if saldo is not None else None,
                           "limite_credito": None, "computa_liquidez": liq, "computa_patrimonio": pat,
                           "permite_negativo": neg, "enabled": activo, "fecha_cierre": None})
        ds.ledger.append({"regla": "D3-A", "origen": f"{cont}/{clave}"})
        return cid

    cont = "public.cuentas_bancarias"
    for cc, cb in sorted(fuente.get(cont, {}).items()):
        if (cont, cc) not in CONFIG_CUENTAS:
            raise ErrorP5("S4_CUENTA_SIN_CONFIG", f"{cont}/{cc}")
        liq = _celda(cont, "liquidez", cb, ctx)
        saldo = Decimal(str(liq.valor)) if liq.estado == fu.CONOCIDO else None
        act = _celda(cont, "activo", cb, ctx)
        cid = crear(cont, cc, _conocido(cont, "anagrama", cb, ctx),
                    tercero(_conocido(cont, "banco_id", cb, ctx)) if _conocido(cont, "banco_id", cb, ctx) else None,
                    saldo, bool(act.valor) if act.estado == fu.CONOCIDO else True)
        ds.mapear(cont, cc, "cuentas", cid, "cuenta")
        pct = _celda(cont, "participacion_pct", cb, ctx)
        if pct.estado == fu.CONOCIDO and Decimal(str(pct.valor)) != Decimal(100):
            # 0330 exige participacion = 100 en todo instante cubierto (fn_check_participacion_suma).
            # V3 solo conoce la cuota del tenant: el resto exige identificar al cotitular. Nunca se inventa.
            if not modo_lab:
                raise ErrorP5("S20_COTITULAR_NO_IDENTIFICADO", f"{cont}/{cc} participacion={pct.valor}")
            ds.pendientes.append({"S20": "COTITULAR_NO_IDENTIFICADO", "origen": f"{cont}/{cc}",
                                  "efecto": "participacion NO creada en modo laboratorio"})
        elif pct.estado == fu.CONOCIDO:
            pid = fu.uuid_v3(cont, cc, "cuenta_participaciones", "self")
            ds.add("cuenta_participaciones", {"id": pid, "cuenta_id": cid, "actor_id": self_id,
                                              "porcentaje": Decimal(str(pct.valor)),
                                              "vigente_desde": FECHA_INICIO_LEDGER, "vigente_hasta": None})
            ds.mapear(cont, cc, "cuenta_participaciones", pid, "self", tipo="DIVIDIDO")
            ds.ledger.append({"regla": "D3-B", "origen": f"{cont}/{cc}"})

    for (co, cl), (nombre, col_gestor) in sorted(CUENTAS_DERIVADAS.items()):
        fila = fuente.get(co, {}).get(cl)
        if fila is None:
            raise ErrorP5("S8_ORIGEN_AUSENTE", f"{co}/{cl}")
        gestor = tercero(fila[col_gestor]) if col_gestor else tercero(GESTOR_REVOLUT)
        cid = crear(co, cl, nombre, gestor, None, True)
        if cid is None:
            continue
        ds.mapear(co, cl, "cuentas", cid, "cuenta_derivada", tipo="DIVIDIDO", confianza="MEDIA",
                  notas="cuenta ausente del maestro V3 (Migration V3 §14/§29); saldo PENDIENTE_DATO_CORTE")
        ds.ledger.append({"regla": "D3-C", "origen": f"{co}/{cl}"})
    ds.ledger.append({"regla": "D3-D", "origen": "cuenta_capacidades"})
    ds.ledger.append({"regla": "DV-10", "origen": "RUN06.cuentas"})


# ------------------------------------------------------------ pipeline
def transformar(b0: dict, sha_run06: str, modo_lab: bool = False) -> Dataset:
    fuente = fu.fuente_b0(b0)
    ctx = fu.contexto_de(fuente)
    (cu,) = fuente["public.users"].keys()
    ds = Dataset(owner=owner_de(cu))
    dominio_12_trazabilidad(ds, b0, sha_run06)
    dominio_1(ds, fuente, ctx)
    dominio_2(ds, fuente, ctx)
    if "public.cuentas_bancarias" in fuente:
        dominio_3(ds, fuente, ctx, modo_lab)
    verificar_trazabilidad(ds)
    return ds


def verificar_trazabilidad(ds: Dataset) -> None:
    """R05 parcial: todo destino creado tiene mapeo; todo mapeo apunta a origen existente."""
    origenes = set(ds.filas["registros_origen_importacion"])
    destinos_mapeados = {(m["tabla_destino"], m["registro_destino_id"])
                         for m in ds.filas["mapeos_importacion"].values()}
    for m in ds.filas["mapeos_importacion"].values():
        if m["registro_origen_id"] not in origenes:
            raise ErrorP5("S8_MAPEO_SIN_ORIGEN", m["id"])
    exentas = {"fuentes_importacion", "registros_origen_importacion", "mapeos_importacion"}
    for t in ORDEN_TABLAS:
        if t in exentas:
            continue
        for fid in ds.filas[t]:
            if (t, fid) not in destinos_mapeados:
                raise ErrorP5("S8_DESTINO_SIN_ORIGEN", f"{t}/{fid}")


# ------------------------------------------------------------ validacion fisica
def orden_insercion(ds: Dataset, tabla: str) -> list:
    filas = ds.filas[tabla]
    col = AUTOREF.get(tabla)
    if col is None:
        return sorted(filas)

    def prof(fid, vistos=()):
        padre = filas[fid].get(col)
        if padre is None or padre not in filas:
            return 0
        if fid in vistos:
            raise ErrorP5("S1_CICLO_JERARQUIA", f"{tabla}/{fid}")
        return 1 + prof(padre, vistos + (fid,))
    return sorted(filas, key=lambda f: (prof(f), f))


def validar_fisico(ds: Dataset, dsn_import: str) -> dict:
    """Carga en una transaccion bajo RV3_IMPORT y SIEMPRE revierte."""
    import psycopg
    from psycopg.types.json import Jsonb
    res = {}
    with psycopg.connect(dsn_import) as c:
        with c.transaction(force_rollback=True):
            c.execute("SET ROLE gapto_migrator")
            c.execute("SET ROLE gapto_owner")
            c.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (ds.owner,))
            for t in ORDEN_TABLAS:
                for fid in orden_insercion(ds, t):
                    f = ds.filas[t][fid]
                    cols = sorted(f)
                    vals = [Jsonb(f[k]) if isinstance(f[k], (dict, list)) else f[k] for k in cols]
                    c.execute(f"INSERT INTO gapto.{t} ({', '.join(cols)}) VALUES "
                              f"({', '.join(['%s'] * len(cols))})", vals)
            c.execute("SET CONSTRAINTS ALL IMMEDIATE")
            for t in ORDEN_TABLAS:
                res[t] = c.execute(f"SELECT count(*) FROM gapto.{t}").fetchone()[0]
            res["_rol"] = c.execute("SELECT current_user, session_user").fetchone()
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run06", required=True, type=Path)
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--modo-lab", action="store_true",
                    help="permite PROPUESTAS no confirmadas; el informe queda marcado y NO vale para gate")
    ap.add_argument("--dsn-import", default=None, help="DSN del perfil RV3_IMPORT (laboratorio)")
    a = ap.parse_args()
    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] [1/3] Carga B0", flush=True)
    b0 = fu.cargar_b0(a.run06)
    sha = fu.p1.sha256_fichero(a.run06)
    print(f"[{time.strftime('%H:%M:%S')}] [2/3] Transformacion P5 v{VERSION}", flush=True)
    ds = transformar(b0, sha, modo_lab=a.modo_lab)
    h = ds.hash()
    fisico = None
    if a.dsn_import:
        print(f"[{time.strftime('%H:%M:%S')}] [3/3] Validacion fisica RV3_IMPORT (ROLLBACK)", flush=True)
        fisico = validar_fisico(ds, a.dsn_import)
    informe = {"version": VERSION, "hash_dataset": h, "recuentos": ds.recuentos(),
               "ledger_reglas": LEDGER_REGLAS, "ledger": ds.ledger, "pendientes": ds.pendientes,
               "fisico": fisico, "dominios": {"implementados": [1, "2-parcial", 3, "12-base"], "pendientes": ["2-resto"] + list(range(4, 12)), "modo_lab": a.modo_lab},
               "ts": datetime.now(timezone.utc).isoformat()}
    a.salida.mkdir(parents=True, exist_ok=True)
    p = a.salida / f"rv3_p5_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    p.write_text(json.dumps(informe, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"      hash_dataset={h}\n      recuentos={ds.recuentos()}\n      fisico={fisico}\n"
          f"      informe={p.name} ({time.time() - t0:.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
