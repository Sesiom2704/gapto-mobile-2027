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
#                4 entidades y subtipos (PARCIAL v0.4.0: PROPIEDAD; resto de subtipos
#                  en sus dominios 8/9/10; cotitulares pendientes -> S20)
#                8 financiaciones (PARCIAL v0.5.0: 4 prestamos formales con condiciones
#                  versionadas, calendario, financiador y garantia; 7 compras financiadas;
#                  derechos/obligaciones pendientes)
#               12 importacion: fuente + registros origen + mapeos (base)
#               5, 6, 7, 9, 10, 11 y resto de 2/4/8 pendientes.
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
# Versión: 0.5.0
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

VERSION = "0.5.0"
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
    "usuarios", "paises", "regiones", "localidades",
    "terceros", "tercero_personas", "clasificaciones_tercero", "tercero_clasificaciones",
    "tercero_roles", "actores_financieros",
    "cuentas", "cuenta_participaciones",
    "entidades", "propiedades", "entidad_participaciones",
    "financiaciones", "financiacion_condiciones_versiones", "financiacion_cuotas", "entidad_relaciones",
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
PK = {"tercero_personas": "tercero_id", "propiedades": "entidad_id", "financiaciones": "entidad_id"}

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
    "D4-A": "propiedades.direccion_id NULL: V3 da calle/numero/piso/puerta/localidad en texto; "
            "crear direcciones exige vincular localidad por nombre (misma decision que D2-F). Origen conservado.",
    "D4-B": "incluir_en_rentabilidad = patrimonio.disponible (Migration V3 §9: disponible=false "
            "significa excluir de rentabilidad).",
    "D4-C": "entidad_participaciones: 0 filas = propiedad no modelada (D-107). Solo se modela el "
            "reparto cuando esta completo; vigente_desde = fecha_adquisicion V3 demostrada.",
    "D4-D": "participaciones V3 != 100 (50 %; y Blasco 1 % = 0 % real segun Migration V3 §9): el "
            "resto exige identificar cotitulares/propietario. No se modelan hasta confirmacion (S20).",
    "DV-9": "RUN06 no materializo clasificaciones_tercero ni tercero_clasificaciones pese a que V3 "
            "tiene 22 ramas + 34 subsegmentos con jerarquia demostrada; RV3 las conserva (R26).",
    "D8-A": "tipo_financiacion demostrado solo si nombre V3 (HIP./PRESTAMO) y tipo_gasto del gasto de "
            "referencia coinciden; discrepancia -> PROPUESTA por nombre y fallo S20 fuera de laboratorio.",
    "D8-B": "HIPOTECA con referencia_vivienda V3 -> entidad_relaciones GARANTIZADA_POR a esa propiedad; "
            "vigencia NULL (inicio de la garantia no demostrado).",
    "D8-B2": "financiacion no HIPOTECA con referencia_vivienda: sin relacion (solo existe GARANTIZADA_POR); "
             "vinculo conservado en origen. Pendiente de conformidad.",
    "D8-C": "financiador = actor del tercero proveedor V3 del prestamo + tercero_roles FINANCIADOR (H-P5-04).",
    "D8-D": "moneda = moneda de la cuenta de cargo V3 (CONFIG_CUENTAS); sin cuenta configurada -> S6/S20.",
    "D8-E": "saldo_principal_apertura = capital_pendiente V3 con fecha_inicio_seguimiento = corte "
            "(Migration V3 §29, R11 173.215,92).",
    "D8-F": "sistema_amortizacion demostrado por calculo: FRANCES si el interes V3 se reproduce al centimo "
            "con la tasa de la version y cuota constante; SIN_INTERES con tasa 0 e interes 0; si no, OTRO "
            "(el calendario V3 es la fuente detallada). importe_cuota_referencia NULL (derivable).",
    "D8-G": "cuota V3 con total distinto de componentes: se conservan ambos sin correccion (Migration V3 §27).",
    "D8-H": "entidad_participaciones de la financiacion: 0 filas (no modelada, D-107); Migration V3 §29 "
            "prohibe inferirla desde propiedad o cuenta. Pendiente S20.",
    "D8-I": "pagada/fecha_pago/gasto_id de prestamo_cuota se disponen en dominio 6 (hechos); "
            "financiacion_cuotas no tiene flag de pagado (DB Schema §56).",
    "D8-J": "cuota con vencimiento anterior al corte y no pagada en V3: se conserva la fecha V3 sin "
            "desplazarla (Migration V3 §7: calendario desplazado). Clase C.",
    "D8-K": "compra financiada = gasto con tipo_gasto FINANCIACION y cuotas; capital = cuotas x importe_cuota "
            "= total; liquidada (restantes 0, pendiente 0) -> CERRADA/LIQUIDADA, apertura 0 al corte, "
            "fecha_cierre_real NULL; condicion SIN_INTERES; sin calendario (no existe en V3).",
    "D8-L": "financiador de compra financiada NULL: el proveedor V3 no demuestra ser el financiador; "
            "se conserva en origen (dominio 6: hecho_terceros).",
    "D8-N": "gasto con tipo_gasto FINANCIACION reclasificado por el propietario como gasto directo "
            "(Migration V3 §27/RUN01): no es financiacion; se dispone en dominio 6.",
    "D8-M": "total de compra sustituido por el validado por el propietario (Migration V3 §14/RUN01); "
            "literal V3 conservado en origen.",
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


# ------------------------------------------------------------ dominio 4
def _dec(c):
    return Decimal(str(c.valor)) if c.estado == fu.CONOCIDO else None


def _int(c):
    return int(Decimal(str(c.valor))) if c.estado == fu.CONOCIDO else None


def _bool(c):
    return bool(c.valor) if c.estado == fu.CONOCIDO else None


def dominio_4_propiedades(ds: Dataset, fuente: dict, ctx: dict, modo_lab: bool) -> None:
    cont = "public.patrimonio"
    self_id = next(iter(ds.filas["actores_financieros"]))
    tipos = {"VIVIENDA", "LOCAL", "GARAJE", "TERRENO"}
    for cp, pa in sorted(fuente.get(cont, {}).items()):
        g = lambda col: _celda(cont, col, pa, ctx)
        eid = fu.uuid_v3(cont, cp, "entidades", "propiedad")
        tipo = _texto(g("tipo_inmueble")) if g("tipo_inmueble").estado == fu.CONOCIDO else None
        if tipo not in tipos:
            raise ErrorP5("S4_TIPO_PROPIEDAD", f"{cont}/{cp}")
        ds.add("entidades", {"id": eid, "owner_user_id": ds.owner, "tipo_entidad": "PROPIEDAD",
                             "nombre": _texto(g("referencia")), "enabled": _bool(g("activo"))})
        ds.mapear(cont, cp, "entidades", eid, "propiedad", tipo="DIVIDIDO")
        adq = _texto(g("fecha_adquisicion")) if g("fecha_adquisicion").estado == fu.CONOCIDO else None
        ds.add("propiedades", {"entidad_id": eid, "direccion_id": None, "tipo_propiedad": tipo,
                               "referencia_catastral": None, "fecha_adquisicion": adq,
                               "fecha_salida_patrimonio": None, "motivo_salida": None,
                               "superficie_m2": _dec(g("superficie_m2")),
                               "superficie_construida_m2": _dec(g("superficie_construida")),
                               "habitaciones": _int(g("habitaciones")), "banos": _int(g("banos")),
                               "tiene_garaje": _bool(g("garaje")), "tiene_trastero": _bool(g("trastero")),
                               "incluir_en_rentabilidad": _bool(g("disponible")), "notas": None,
                               "latitud": None, "longitud": None, "geolocalizacion_origen": None})
        ds.mapear(cont, cp, "propiedades", eid, "propiedad", tipo="DIVIDIDO")
        for r in ("D4-A", "D4-B"):
            ds.ledger.append({"regla": r, "origen": f"{cont}/{cp}"})
        pct = _dec(g("participacion_pct"))
        if pct == Decimal(100) and adq:
            pid = fu.uuid_v3(cont, cp, "entidad_participaciones", "self")
            ds.add("entidad_participaciones", {"id": pid, "entidad_id": eid, "actor_id": self_id,
                                               "porcentaje": pct, "vigente_desde": adq, "vigente_hasta": None})
            ds.mapear(cont, cp, "entidad_participaciones", pid, "self", tipo="DIVIDIDO")
            ds.ledger.append({"regla": "D4-C", "origen": f"{cont}/{cp}"})
        elif pct is not None:
            if not modo_lab:
                raise ErrorP5("S20_COTITULAR_NO_IDENTIFICADO", f"{cont}/{cp} participacion={pct}")
            ds.pendientes.append({"S20": "COTITULAR_NO_IDENTIFICADO", "origen": f"{cont}/{cp}",
                                  "efecto": "reparto NO modelado (0 filas, D-107) en modo laboratorio"})
            ds.ledger.append({"regla": "D4-D", "origen": f"{cont}/{cp}"})


# ------------------------------------------------------------ dominio 8 (financiaciones)
# Tipo de financiacion: demostrado solo cuando el nombre V3 del prestamo y el tipo_gasto de su
# gasto de referencia coinciden. Si discrepan o falta uno, decide el propietario (S20).
# clave prestamo -> tipo decidido (CONFIRMADO). Vacio: ninguna decision S20 registrada.
TIPO_FINANCIACION_DECIDIDO: dict = {}
# Condiciones versionadas decididas (arquitectura, continuacion RV3-E001-R2): Hip. Allende.
CONDICIONES_DECIDIDAS = {
    "prestamo-6d5rjp": [
        {"motivo": "ALTA", "desde": None, "hasta": "2026-03-27", "tasa": "2.5", "cuotas": (1, 20)},
        {"motivo": "CAMBIO_CONDICIONES", "desde": "2026-03-28", "hasta": None, "tasa": "2.6", "cuotas": (21, None)},
    ],
}
# Total validado por el propietario (Migration V3 §14 / RUN01): V3 total=134904 es error de separador.
TOTAL_COMPRA_VALIDADO = {"GASTO-T4I2U4": Decimal("1349.04")}
TIPO_GASTO_COMPRA_FINANCIADA = "FINANCIACION"
# Reclasificado por el propietario de financiado a gasto directo (Migration V3 §27, RUN01).
NO_COMPRA_FINANCIADA_CANON = {"gasto-7gl597"}
_PREF_NOMBRE = (("HIP.", "HIPOTECA"), ("HIPOTECA", "HIPOTECA"), ("PRÉSTAMO", "PRESTAMO"), ("PRESTAMO", "PRESTAMO"))
_TIPO_GASTO_FIN = {"HIPOTECA": "HIPOTECA", "PRESTAMO PERSONAL": "PRESTAMO"}
_AUSENTE = (fu.AUSENCIA_141, fu.AUSENCIA_NONE, fu.NULO)


def _val(cont, col, fila, ctx):
    c = _celda(cont, col, fila, ctx)
    return c.valor if c.estado in (fu.CONOCIDO, fu.REAL_141) else None


def _actor_tercero(ds: Dataset, clave_prov: str, rol: str | None) -> str:
    tid = fu.uuid_v3("public.proveedores", clave_prov, "terceros", "tercero")
    if tid not in ds.filas["terceros"]:
        raise ErrorP5("S8_HUERFANO", f"public.proveedores/{clave_prov}")
    aid = fu.uuid_v3("public.proveedores", clave_prov, "actores_financieros", "actor")
    ds.add("actores_financieros", {"id": aid, "owner_user_id": ds.owner, "tercero_id": tid},
           natural=(ds.owner, tid))
    ds.mapear("public.proveedores", clave_prov, "actores_financieros", aid, "actor", tipo="DIVIDIDO")
    if rol:
        rid = fu.uuid_v3("public.proveedores", clave_prov, "tercero_roles", rol)
        ds.add("tercero_roles", {"id": rid, "tercero_id": tid, "rol_codigo": rol}, natural=(tid, rol))
        ds.mapear("public.proveedores", clave_prov, "tercero_roles", rid, f"rol.{rol}", tipo="DIVIDIDO")
    return aid


def _moneda_cuenta(ds: Dataset, clave_cuenta, origen: str, modo_lab: bool):
    cid = fu.uuid_v3("public.cuentas_bancarias", str(clave_cuenta), "cuentas", "cuenta") if clave_cuenta else None
    cta = ds.filas["cuentas"].get(cid) if cid else None
    if cta is None:
        if not modo_lab:
            raise ErrorP5("S6_MONEDA_NO_DEMOSTRADA", f"{origen}: cuenta de cargo sin configurar")
        ds.pendientes.append({"S20": "MONEDA_NO_DEMOSTRADA", "origen": origen,
                              "efecto": "financiacion NO creada en modo laboratorio"})
        return None
    return cta["moneda"]


def _tipo_prestamo(fuente, cont, cp, pr, ctx):
    nombre = (_texto(_celda(cont, "nombre", pr, ctx)) or "").upper()
    por_nombre = next((t for p, t in _PREF_NOMBRE if nombre.startswith(p)), None)
    por_gasto = None
    rg = _val(cont, "referencia_gasto", pr, ctx)
    g = fuente.get("public.gastos", {}).get(str(rg)) if rg else None
    if g is not None:
        tg = fuente.get("public.tipo_gasto", {}).get(str(g.get("tipo_id")))
        if tg is not None:
            por_gasto = _TIPO_GASTO_FIN.get((_texto(_celda("public.tipo_gasto", "nombre", tg, ctx)) or "").upper())
    if cp in TIPO_FINANCIACION_DECIDIDO:
        return TIPO_FINANCIACION_DECIDIDO[cp], "DECIDIDO_S20", por_nombre, por_gasto
    if por_nombre and por_nombre == por_gasto:
        return por_nombre, "DEMOSTRADO", por_nombre, por_gasto
    return por_nombre, "PROPUESTA", por_nombre, por_gasto


def _sistema(cuotas: list, tasa: Decimal, ultima: int) -> str:
    """FRANCES solo si el interes V3 se reproduce al centimo con la tasa y la cuota es constante
    (salvo la ultima del prestamo); SIN_INTERES si tasa 0 e interes 0; en otro caso OTRO."""
    from decimal import ROUND_HALF_UP
    if tasa == 0:
        return "SIN_INTERES" if all(c["interes"] == 0 for c in cuotas) else "OTRO"
    imp = {c["importe"] for c in cuotas if c["num"] != ultima}
    ok = all(abs((c["saldo_prev"] * tasa / Decimal(1200)).quantize(Decimal("0.01"), ROUND_HALF_UP)
                 - c["interes"]) <= Decimal("0.01") for c in cuotas)
    return "FRANCES" if ok and len(imp) <= 1 else "OTRO"


def dominio_8_financiaciones(ds: Dataset, fuente: dict, ctx: dict, modo_lab: bool) -> None:
    cont, cq = "public.prestamo", "public.prestamo_cuota"
    cuotas_de: dict = {}
    for kq, q in fuente.get(cq, {}).items():
        cuotas_de.setdefault(str(q.get("prestamo_id")), []).append((kq, q))
    for cp, pr in sorted(fuente.get(cont, {}).items()):
        g = lambda col: _val(cont, col, pr, ctx)
        origen = f"{cont}/{cp}"
        tipo, estado_tipo, por_nombre, por_gasto = _tipo_prestamo(fuente, cont, cp, pr, ctx)
        if tipo is None or estado_tipo == "PROPUESTA":
            if not modo_lab or tipo is None:
                raise ErrorP5("S20_TIPO_FINANCIACION", f"{origen} nombre={por_nombre} tipo_gasto={por_gasto}")
            ds.pendientes.append({"S20": "TIPO_FINANCIACION", "origen": origen, "propuesta": tipo,
                                  "evidencia": {"nombre": por_nombre, "tipo_gasto": por_gasto}})
        moneda = _moneda_cuenta(ds, g("cuenta_id"), origen, modo_lab)
        if moneda is None:
            continue
        eid = fu.uuid_v3(cont, cp, "entidades", "financiacion")
        ds.add("entidades", {"id": eid, "owner_user_id": ds.owner, "tipo_entidad": "FINANCIACION",
                             "nombre": _texto(_celda(cont, "nombre", pr, ctx)), "enabled": bool(g("activo"))})
        ds.mapear(cont, cp, "entidades", eid, "financiacion", tipo="DIVIDIDO")
        prov = g("proveedor_id")
        fin_actor = _actor_tercero(ds, str(prov), "FINANCIADOR") if prov else None
        pend = g("capital_pendiente")
        ds.add("financiaciones", {
            "entidad_id": eid, "tipo_financiacion": tipo, "financiador_actor_id": fin_actor, "moneda": moneda,
            "capital_original_contratado": Decimal(str(g("importe_principal"))) if g("importe_principal") is not None else None,
            "saldo_principal_apertura": Decimal(str(pend)) if pend is not None else None,
            "fecha_inicio_seguimiento": FECHA_INICIO_LEDGER if pend is not None else None,
            "fecha_inicio": g("fecha_inicio"), "fecha_vencimiento_final_prevista": g("fecha_vencimiento"),
            "fecha_cierre_real": None, "estado": "ACTIVA" if g("estado") == "ACTIVO" else None,
            "motivo_cierre": None, "notas": None})
        if ds.filas["financiaciones"][eid]["estado"] is None:
            raise ErrorP5("S20_ESTADO_FINANCIACION", f"{origen} estado={g('estado')}")
        ds.mapear(cont, cp, "financiaciones", eid, "financiacion", tipo="DIVIDIDO")
        for r in ("D8-A", "D8-C", "D8-D", "D8-E", "D8-H", "D8-I"):
            ds.ledger.append({"regla": r, "origen": origen})

        # calendario (orden contractual) y saldo encadenado
        filas = sorted(cuotas_de.get(cp, []), key=lambda x: int(_val(cq, "num_cuota", x[1], ctx)))
        principal = Decimal(str(g("importe_principal")))
        saldo, cal = principal, []
        for kq, q in filas:
            gq = lambda col: _val(cq, col, q, ctx)
            if Decimal(str(gq("seguros") or 0)) != 0:
                raise ErrorP5("S4_SEGUROS_SIN_DESTINO", f"{cq}/{kq}")
            c = {"clave": kq, "num": int(gq("num_cuota")), "venc": gq("fecha_vencimiento"),
                 "capital": Decimal(str(gq("capital"))), "interes": Decimal(str(gq("interes"))),
                 "comis": Decimal(str(gq("comisiones"))) if gq("comisiones") is not None else None,
                 "importe": Decimal(str(gq("importe_cuota"))), "pagada": gq("pagada"), "saldo_prev": saldo}
            saldo -= c["capital"]
            cal.append(c)
        if [c["num"] for c in cal] != list(range(1, len(cal) + 1)):
            raise ErrorP5("S4_SECUENCIA_CUOTAS", origen)
        if cal and sum(c["capital"] for c in cal) != principal:
            raise ErrorP5("S9_CALENDARIO_NO_CUADRA", f"{origen} suma capital != principal")
        if cal and pend is not None and principal - sum(c["capital"] for c in cal if c["pagada"] is True) != Decimal(str(pend)):
            raise ErrorP5("S9_APERTURA_NO_CUADRA", f"{origen} capital_pendiente != principal - capital pagado")
        ultima = len(cal)
        versiones = CONDICIONES_DECIDIDAS.get(cp) or [
            {"motivo": "ALTA", "desde": None, "hasta": None, "tasa": g("tin_pct"), "cuotas": (1, None)}]
        vmap = {}
        for i, vd in enumerate(versiones, 1):
            vid = fu.uuid_v3(cont, cp, "financiacion_condiciones_versiones", f"v{i}")
            lo, hi = vd["cuotas"]
            tramo = [c for c in cal if c["num"] >= lo and (hi is None or c["num"] <= hi)]
            tasa = Decimal(str(vd["tasa"])) if vd["tasa"] is not None else None
            ti = g("tipo_interes")
            if ti not in ("FIJO", "VARIABLE", "SIN_INTERES"):
                raise ErrorP5("S4_TIPO_INTERES", f"{origen} tipo_interes={ti}")
            if g("periodicidad") != "MENSUAL":
                raise ErrorP5("S4_PERIODICIDAD", f"{origen} periodicidad={g('periodicidad')}")
            sistema = _sistema(tramo, tasa, ultima) if (tasa is not None and tramo) else "OTRO"
            ds.add("financiacion_condiciones_versiones", {
                "id": vid, "financiacion_entidad_id": eid, "vigente_desde": vd["desde"] or g("fecha_inicio"),
                "vigente_hasta": vd["hasta"], "motivo_version": vd["motivo"], "hecho_causa_id": None,
                "modo_recalculo_amortizacion": None, "tipo_interes": ti, "tasa_anual_pct": tasa,
                "indice_referencia": _texto(_celda(cont, "indice", pr, ctx)) if g("indice") else None,
                "diferencial_pct": Decimal(str(g("diferencial_pct"))) if g("diferencial_pct") is not None else None,
                "sistema_amortizacion": sistema, "periodicidad": "MENSUAL", "intervalo": 1,
                "importe_cuota_referencia": None, "numero_cuotas_referencia": g("cuotas_totales"),
                "comisiones_periodicas": None})
            ds.mapear(cont, cp, "financiacion_condiciones_versiones", vid, f"v{i}", tipo="DIVIDIDO")
            ds.ledger.append({"regla": "D8-F", "origen": origen, "version": i, "sistema": sistema})
            for c in tramo:
                vmap[c["num"]] = vid
        for c in cal:
            qid = fu.uuid_v3(cq, c["clave"], "financiacion_cuotas", "cuota")
            ds.add("financiacion_cuotas", {
                "id": qid, "financiacion_entidad_id": eid, "condicion_version_id": vmap.get(c["num"]),
                "numero_cuota": c["num"], "fecha_vencimiento": c["venc"], "capital_previsto": c["capital"],
                "interes_previsto": c["interes"], "comisiones_previstas": c["comis"],
                "importe_total_previsto": c["importe"], "prevision_id": None},
                natural=(eid, c["num"]))
            ds.mapear(cq, c["clave"], "financiacion_cuotas", qid, "cuota")
            if c["capital"] + c["interes"] + (c["comis"] or 0) != c["importe"]:
                ds.ledger.append({"regla": "D8-G", "origen": f"{cq}/{c['clave']}",
                                  "diferencia": str(c["importe"] - c["capital"] - c["interes"] - (c["comis"] or 0))})
            if c["pagada"] is not True and str(c["venc"]) < FECHA_INICIO_LEDGER:
                ds.ledger.append({"regla": "D8-J", "origen": f"{cq}/{c['clave']}"})
        # garantia: solo HIPOTECA con vivienda V3 que exista como propiedad
        viv = g("referencia_vivienda_id")
        if tipo == "HIPOTECA" and viv:
            pid = fu.uuid_v3("public.patrimonio", str(viv), "entidades", "propiedad")
            if pid not in ds.filas["propiedades"]:
                raise ErrorP5("S8_HUERFANO", f"{origen} referencia_vivienda_id")
            rid = fu.uuid_v3(cont, cp, "entidad_relaciones", "garantia")
            ds.add("entidad_relaciones", {"id": rid, "entidad_origen_id": eid, "entidad_destino_id": pid,
                                          "tipo_relacion": "GARANTIZADA_POR", "vigente_desde": None,
                                          "vigente_hasta": None})
            ds.mapear(cont, cp, "entidad_relaciones", rid, "garantia", tipo="DIVIDIDO")
            ds.ledger.append({"regla": "D8-B", "origen": origen})
        elif viv:
            ds.ledger.append({"regla": "D8-B2", "origen": origen})

    # compras financiadas de consumo (Migration V3 §14/§28: 7; 2.623,76 EUR)
    cg = "public.gastos"
    tipos_fin = {k for k, t in fuente.get("public.tipo_gasto", {}).items()
                 if (_texto(_celda("public.tipo_gasto", "nombre", t, ctx)) or "").upper() == TIPO_GASTO_COMPRA_FINANCIADA}
    for kg, gg in sorted(fuente.get(cg, {}).items()):
        if str(gg.get("tipo_id")) not in tipos_fin or _val(cg, "prestamo_id", gg, ctx):
            continue
        g = lambda col: _val(cg, col, gg, ctx)
        origen = f"{cg}/{kg}"
        if kg in NO_COMPRA_FINANCIADA_CANON:
            ds.ledger.append({"regla": "D8-N", "origen": origen})
            continue
        n, cuota = g("cuotas"), g("importe_cuota")
        if n is None or cuota is None or int(n) < 2:
            raise ErrorP5("S4_COMPRA_FINANCIADA_SIN_CUOTAS", origen)
        capital = Decimal(str(cuota)) * int(n)
        total = TOTAL_COMPRA_VALIDADO.get(kg, Decimal(str(g("total"))) if g("total") is not None else None)
        if total != capital:
            raise ErrorP5("S9_COMPRA_FINANCIADA_TOTAL", f"{origen} total={total} cuotas={capital}")
        pend_c = g("importe_pendiente")
        if not (g("cuotas_restantes") == 0 and pend_c is not None and Decimal(str(pend_c)) == 0):
            if not modo_lab:
                raise ErrorP5("S20_COMPRA_FINANCIADA_PENDIENTE", origen)
            ds.pendientes.append({"S20": "COMPRA_FINANCIADA_PENDIENTE", "origen": origen})
            continue
        if g("periodicidad") != "MENSUAL":
            raise ErrorP5("S4_PERIODICIDAD", origen)
        moneda = _moneda_cuenta(ds, g("cuenta_id"), origen, modo_lab)
        if moneda is None:
            continue
        eid = fu.uuid_v3(cg, kg, "entidades", "financiacion")
        ds.add("entidades", {"id": eid, "owner_user_id": ds.owner, "tipo_entidad": "FINANCIACION",
                             "nombre": _texto(_celda(cg, "nombre", gg, ctx)), "enabled": bool(g("activo"))})
        ds.mapear(cg, kg, "entidades", eid, "financiacion", tipo="DIVIDIDO")
        ds.add("financiaciones", {
            "entidad_id": eid, "tipo_financiacion": "COMPRA_FINANCIADA", "financiador_actor_id": None,
            "moneda": moneda, "capital_original_contratado": capital,
            "saldo_principal_apertura": Decimal("0"), "fecha_inicio_seguimiento": FECHA_INICIO_LEDGER,
            "fecha_inicio": g("fecha"), "fecha_vencimiento_final_prevista": None, "fecha_cierre_real": None,
            "estado": "CERRADA", "motivo_cierre": "LIQUIDADA", "notas": None})
        ds.mapear(cg, kg, "financiaciones", eid, "financiacion", tipo="DIVIDIDO")
        vid = fu.uuid_v3(cg, kg, "financiacion_condiciones_versiones", "v1")
        ds.add("financiacion_condiciones_versiones", {
            "id": vid, "financiacion_entidad_id": eid, "vigente_desde": g("fecha"), "vigente_hasta": None,
            "motivo_version": "ALTA", "hecho_causa_id": None, "modo_recalculo_amortizacion": None,
            "tipo_interes": "SIN_INTERES", "tasa_anual_pct": None, "indice_referencia": None,
            "diferencial_pct": None, "sistema_amortizacion": "SIN_INTERES", "periodicidad": "MENSUAL",
            "intervalo": 1, "importe_cuota_referencia": Decimal(str(cuota)), "numero_cuotas_referencia": int(n),
            "comisiones_periodicas": None})
        ds.mapear(cg, kg, "financiacion_condiciones_versiones", vid, "v1", tipo="DIVIDIDO")
        for r in ("D8-K", "D8-L", "D8-D", "D8-H"):
            ds.ledger.append({"regla": r, "origen": origen})
        if kg in TOTAL_COMPRA_VALIDADO:
            ds.ledger.append({"regla": "D8-M", "origen": origen})


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
    dominio_4_propiedades(ds, fuente, ctx, modo_lab)
    dominio_8_financiaciones(ds, fuente, ctx, modo_lab)
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
               "fisico": fisico, "dominios": {"implementados": [1, "2-parcial", 3, "4-propiedad", "8-financiaciones", "12-base"], "pendientes": ["2-resto", "4-resto", 5, 6, 7, "8-derechos", 9, 10, 11], "modo_lab": a.modo_lab},
               "ts": datetime.now(timezone.utc).isoformat()}
    a.salida.mkdir(parents=True, exist_ok=True)
    p = a.salida / f"rv3_p5_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    p.write_text(json.dumps(informe, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"      hash_dataset={h}\n      recuentos={ds.recuentos()}\n      fisico={fisico}\n"
          f"      informe={p.name} ({time.time() - t0:.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
