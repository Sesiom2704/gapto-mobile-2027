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
#   v0.25.0: resto del dominio 12 (R05 completo): disposicion de todo origen. Gastos de referencia de
#           cuota (D5-T) VINCULADO a su financiacion; taxonomia V3 reemplazada (D-MIG-001) con codigo de
#           disposicion PROPUESTO (OBSOLETO) pendiente de decision; decision de clasificacion VINCULADA a
#           cada destino donde se aplico (con verificacion de coherencia). R05 estricto: origen sin
#           disposicion -> S8; mapeo a destino inexistente -> S8 (R-RV3-002).
#   v0.24.0: presupuesto de los 6 contenedores G-V3-03 (respuesta del propietario: importe_cuota = presupuesto
#           mensual, importe = restante): un presupuesto ACTIVO del mes del corte con 6 BOLSAS (D11-F/D11-H).
#   v0.23.0: dominio 11 (cierres): 13 cierres V3 -> snapshots IMPORTADO_LEGACY/CAJA/V3_SNAPSHOT; cabecera y
#           detalle como cierre_metricas con bundle LEGACY_V3_* deshabilitado (DB Schema §61/§65); sin snapshots
#           de saldos/posiciones/presupuesto que V3 no conserva. Presupuestos G-V3-03 pendientes (Migration V3 §4).
#   v0.22.0: dominio 7 (tesoreria legacy): 141 movimientos V3 -> 83 transferencias (hecho neutro + 166
#           movimientos OPERACION + transferencias + 166 conciliaciones, F04-D001) y 58 AJUSTE_SALDO (DV-7) = 224;
#           todos anteriores a fecha_inicio_ledger: no computan en el saldo de apertura (DB Schema §40, D7-D).
#   v0.21.0: respuestas 2026-09-21: ticket compartido con Ana (D6-Z: parte propia 27,33, sin actor ficticio);
#           compras ASICS, seguro Saavedra y vuelo Tailandia 100 % propias (PARTICIPACION_FIN_SELF); vuelo
#           vinculado al contexto Tailandia 2026; sin aportaciones de pago en el historico (D6-Q confirmada).
#   v0.20.0: respuestas del propietario (2026-09-21) al bloque 1 del dominio 6: Fuensanta 50 % por
#           participacion vigente (D6-V), Blasco Ibanez 100 % propio (D6-V), total 15,61 del cotidiano 1FRA14
#           (D6-W). Nutricionista: se mantiene como compra financiada cancelada, sin gasto (D8-K4 sin cambio).
#           Bloque 2 (OP-15): hecho COMPRA_FINANCIADA con GASTO total + DEUDA del principal vinculada a la
#           financiacion, atribuidos por su participacion vigente (D6-X); cuotas de prestamo y compra cancelada
#           sin hecho (D6-Y); compra sin participacion en el dominio 8 -> pendiente (no se presume 100 %).
#   v0.19.0: dominio 6 bloque 1 (hechos): 811 filas (810 HECHO_EXACTO + cobro parcial D5-S) -> hechos,
#           efectos, atribuciones, terceros, vinculos a entidades y relaciones; traspasos sin movimiento V3 como
#           TRANSFERENCIA neutra (opcion A del propietario, D6-T); devoluciones OP-13 (gafas con origen, gasolina
#           sin origen D6-D2); reembolsos F04-D015 con REEMBOLSO_DE; luz de Allende 100 % al inquilino
#           (respuesta 3); contextos decididos (Tailandia 2026, Finde Unai). Pendientes de fila: viviendas
#           compartidas sin decision, gasto adelantado parcialmente reembolsado, parte personal > total.
#           Compras financiadas -> bloque 2. Sin tesoreria (dominio 7).
#   v0.18.0: respuestas A-F del propietario 2026-09-21: Isa = REEMBOLSO (F04-D015); inicio = createon en 7
#           anuales (D5-B3); PARO PARCIAL 4/26 = cobro parcial -> dominio 6 (D5-S); cuotas de prestamo sin
#           regla (D5-T); nutricionista cancelada (D8-K4); 50/50 de compras de Fuensanta en la fuente
#           suplementaria v2 (S20-R5-F).
#   v0.17.0: respuestas del propietario 2026-09-21 al dominio 5: 15 gastos a plazos son compras
#           financiadas (D8-K2; abiertas al corte -> ACTIVA con saldo pendiente, D8-K3); fusiones N:1
#           IBI Saavedra, comunidad Saavedra y paro (D5-K3, solape -> D5-K2); inicio confirmado
#           (D5-B2); fin por fecha de modificacion (D5-C2); Mediolanum mantiene el UUID canonico.
#   v0.16.0: dominio 5 reglas financieras y versiones (RV3-D003, mandato de continuacion P5):
#           recurrencias V3 -> reglas_financieras + regla_versiones (D5-A..D5-P); renta N:1 contrato +
#           ingreso (corrige duplicado RUN06, DV-11); Mediolanum N:1 con versiones contiguas; ahorro
#           remunerado como TRANSFERENCIA a la cuenta de ahorro derivada; G-V3-02 RODANTE; contratos
#           .regla_renta_id completado; regla_excepciones 0 (D-MIG-015). Pendientes por fila: prestamo
#           coche Isa (STOP S1), cuotas de prestamo, gastos a plazos, inicio/fin no demostrados.
#   v0.15.0: respuestas del propietario 2026-09-21 (dominios 3 y 4): capacidades de
#           cuenta declaradas en la fuente suplementaria (D3-D revisada); direcciones
#           de propiedad con localidad vinculada por nombre exacto (D4-A revisada);
#           coordenadas MANUALES aportadas por el propietario (D4-G, D-184).
#   v0.14.0: clasificacion validada por el propietario (opcion 1, 2026-09-21): arbol
#           CONFIRMADO; tabla tipo V3 -> categoria (52) en codigo; clasificacion por
#           registro de los tipos heterogeneos en la fuente suplementaria (fichero
#           externo); resolucion completa de los registros operativos comprobada.
#   v0.13.0: D2-E resuelta por opcion A (arquitectura, 2026-09-21): arbol de categorias
#           canonico de Migration V3 v0.40 §15.2 como fuente suplementaria (un registro
#           origen por nodo); ambito y presupuestable_default PROPUESTOS hasta la
#           validacion del propietario (solo laboratorio).
#   v0.12.0: cuarta ronda S20 (2026-09-21): garaje con inicio validado, avalista
#           duplicada por captura fusionada en una sola vigencia, fianzas como
#           obligaciones de devolucion y luz de Allende como servicio repercutible 100 %.
#   v0.11.0: dominio 10 (parcial): contratos, participantes con vigencias, clausula de
#           revision de renta y valoraciones de propiedad desde patrimonio_compra.
#           Servicios y contextos sin fuente V3 estructurada: no se crean (D10-F/D10-G);
#           renta -> regla del dominio 5.
#   v0.10.0: tercera ronda S20 (2026-09-21): tipo_producto CONFIRMADO (6 FONDO + joint
#           venture como OTRO con nota), inversiones 100 % propietario desde su
#           fecha_inicio, contraparte de luz Allende = inquilino V3 validado contra el
#           contrato de la vivienda.
#   v0.9.0: dominio 9 inversiones (7 posiciones + objetivos versionados; la cuenta
#           de ahorro V3 sigue en dominio 3). tipo_producto sin dato V3 -> PROPUESTA S20.
#   v0.8.0: segunda ronda S20 (2026-09-21): fuente suplementaria APROBADA por
#           arquitectura; vigencias de participacion de financiacion CONFIRMADAS;
#           financiador y contrapartes decididos por la fuente suplementaria;
#           participaciones de derechos 100 % propietario; vigencia anterior al
#           inicio justificada por la decision; Universidad vinculada a sus pagos.
#   v0.7.0: dominio 8B derechos de cobro (11 posiciones: 7 transitorias liquidadas
#           = 330,11; SHEIN abierta 59,96; Universidad 0; dos de Isa indeterminadas).
#   v0.6.0: respuestas S20 del propietario (2026-09-21): configuracion de cuentas
#           CONFIRMADA, Revolut EUR, tipos de financiacion decididos, participaciones
#           de financiacion al 100 % propietario (vigencia PROPUESTA) y fuente
#           suplementaria DECISIONES_PROPIETARIO (fichero externo fuera del repo, con
#           PII) para cotitulares sin fila V3; esa fuente esta PENDIENTE de arquitectura:
#           fuera de laboratorio falla cerrada (S20_ARQ_FUENTE_DECISIONES).
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
# Versión: 0.25.0
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
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

VERSION = "0.25.0"
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
    "usuarios", "paises", "regiones", "localidades", "categorias_financieras",
    "terceros", "tercero_personas", "clasificaciones_tercero", "tercero_clasificaciones",
    "tercero_roles", "actores_financieros",
    "cuentas", "cuenta_capacidades", "cuenta_participaciones",
    "direcciones", "entidades", "propiedades", "entidad_participaciones",
    "financiaciones", "financiacion_condiciones_versiones", "financiacion_cuotas", "entidad_relaciones",
    "derechos_obligaciones_financieras", "inversiones", "inversion_objetivos_versiones",
    "reglas_financieras", "regla_versiones", "regla_excepciones",
    "contratos", "contrato_participantes", "contrato_revision_renta_versiones", "propiedad_valoraciones",
    "servicios", "contrato_servicios", "contextos",
    "hechos_financieros", "hecho_efectos", "efecto_atribuciones", "hecho_terceros", "hecho_entidades",
    "hecho_relaciones", "movimientos_tesoreria", "transferencias", "hecho_movimientos_tesoreria",
    "metricas_definicion", "cierres_mensuales", "cierre_metricas",
    "presupuestos", "presupuesto_lineas", "presupuesto_linea_alcances",
    "fuentes_importacion", "registros_origen_importacion", "mapeos_importacion",
]

# Autorreferencias: el padre se inserta antes que el hijo (orden por profundidad).
AUTOREF = {"regiones": "parent_region_id", "clasificaciones_tercero": "parent_id",
           "categorias_financieras": "parent_id"}

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
    # S20-2 (2026-09-21): EUR siempre salvo edicion explicita; incluye Revolut.
    ("public.gastos", "gasto-xg1mue"): ("PREPAGO", "ACTIVO", True, True, False, "EUR"),
}
# S20-1 (2026-09-21): configuracion confirmada por el propietario.
CONFIG_CUENTAS_ESTADO = "CONFIRMADA"
# Cuentas sin fila maestra V3 (Migration V3 §14/§29): origen, nombre, gestor V3.
CUENTAS_DERIVADAS = {
    ("public.inversion", "INV-F28AEAD467"): ("CUENTA AHORRO", "proveedor_id"),
    ("public.gastos", "gasto-xg1mue"): ("REVOLUT", None),
}
GESTOR_REVOLUT = "PROV-UH1DM1"

# Tablas cuya PK no es la columna id.
PK = {"tercero_personas": "tercero_id", "propiedades": "entidad_id", "financiaciones": "entidad_id",
      "derechos_obligaciones_financieras": "entidad_id", "inversiones": "entidad_id", "contratos": "entidad_id",
      "servicios": "entidad_id", "contextos": "entidad_id"}

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
    "D3-B": "cuenta_participaciones.vigente_desde = FECHA_INICIO_LEDGER con semantica 'conocida desde el "
            "corte', sin afirmar el pasado. CONFIRMADA por el propietario (S20-3, 2026-09-21).",
    "D3-C": "ahorro remunerado y Revolut sin saldo V3: saldo_apertura y fecha_inicio_ledger NULL "
            "(PENDIENTE_DATO_CORTE, Migration V3 §29). Ni 930/937,83 ni 250 se interpretan como saldo.",
    "D3-D": "cuenta_capacidades: V3 no tiene el dato (RUN06 creo 21 sin origen). v0.15.0: se crean SOLO las "
            "declaradas por el propietario en la fuente suplementaria (lista 'capacidades', matriz confirmada "
            "2026-09-21); cuenta sin declaracion -> 0 filas, nunca se deducen del tipo de cuenta.",
    "DV-10": "RUN06 cuentas contradice DB Schema §22: T. CREDITO como corriente/computa_liquidez; y "
             "permite_negativo=false con CASH en -30,00. Prevalece el contrato.",
    "D4-A": "v0.15.0 (propietario 2026-09-21): se crea direccion desde calle/numero/escalera/piso/puerta V3 "
            "(via_nombre/numero/escalera/planta/puerta; via_tipo y codigo_postal NULL: no se parsean ni se "
            "deducen). localidad V3 (texto) -> localidades por nombre normalizado exacto: 0 coincidencias -> "
            "S8, varias -> S7; nunca se elige una. Sin ningun dato de direccion -> direccion_id NULL.",
    "D4-G": "geolocalizacion de propiedad SOLO si el propietario la aporta (lista 'geolocalizaciones'); origen "
            "MANUAL; redondeo a 6 decimales (numeric(9,6), ROUND_HALF_UP, < 0,11 m); coordenadas ambas o ninguna. "
            "La migracion no geocodifica ni fabrica coordenadas (D-184).",
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
    "D8-K2": "compra financiada decidida por el propietario (respuesta 3, 2026-09-21) aunque el tipo V3 no sea "
             "FINANCIACION; mismas comprobaciones D8-K (cuotas x importe = total).",
    "D8-K3": "compra financiada abierta al corte: ACTIVA, saldo_principal_apertura = importe_pendiente V3 = cuotas "
             "restantes x cuota (comprobado), fecha_inicio_seguimiento = corte; sin calendario (no se fabrican fechas "
             "de cuotas futuras); financiador NULL (D8-L); participacion 0 filas (D8-H). Incoherencia -> pendiente S20.",
    "D8-K4": "compra financiada cancelada antes del corte (respuesta E): CERRADA/CANCELADA, saldo 0 al corte, "
             "fecha_cierre_real NULL (no declarada); el origen V3 se conserva, no se elimina.",
    "D8-N": "gasto con tipo_gasto FINANCIACION reclasificado por el propietario como gasto directo "
            "(Migration V3 §27/RUN01): no es financiacion; se dispone en dominio 6.",
    "D8-A2": "tipo de financiacion decidido por el propietario (S20-7/S20-8, 2026-09-21) cuando nombre y "
             "tipo_gasto V3 discrepan o no bastan: prevalece TIPO_FINANCIACION_DECIDIDO.",
    "D8-C2": "financiador NULL cuando el proveedor V3 del prestamo contradice el prestamista declarado por el "
             "propietario (S20-8: prestamo de familiares; V3 dice banco). Proveedor conservado en origen; "
             "no se crea actor ni rol FINANCIADOR por ese prestamo. PENDIENTE de conformidad.",
    "D8-C3": "financiador declarado por el propietario en la fuente suplementaria (S20 R2-2: prestamistas "
             "reales = padres; V3 solo admitia entidades financieras). Tercero sin naturaleza individual "
             "inventada + rol FINANCIADOR trazado a la decision.",
    "D8B-F": "participacion del derecho: 100 % propietario (S20 R2-7) salvo reparto decidido (derechos "
             "ligados a Fuensanta: 50 %); vigente_desde = fecha de la fila V3 generadora o, sin ella, del primer "
             "cobro V3 (mismo criterio aceptado en S20 R2-4). Fecha desconocida -> S6.",
    "D8B-G": "filas V3 relacionadas por el propietario con el derecho (S20 R2-8) se vinculan como evidencia "
             "(VINCULADO) sin alterar el canon de cobros; su naturaleza se dispone en dominio 6.",
    "D8-H2": "participacion de financiacion 100 % propietario decidida (S20-9); vigente_desde no fijada por "
             "el propietario: PROPUESTA = fecha_inicio de la financiacion. Fuera de laboratorio falla S20.",
    "D-S20-F": "fuente suplementaria DECISIONES_PROPIETARIO: personas y repartos declarados por el propietario "
               "sin fila V3 (S20-4..7, S20-11). Cada decision es un registro origen propio; fichero externo con "
               "SHA-256. PENDIENTE de decision de arquitectura: solo laboratorio.",
    "D-S20-V": "conflicto de vigencia: participacion de financiacion con vigente_desde anterior a su fecha_inicio "
               "(se aplica literal la decision del propietario y se eleva pregunta).",
    "D6-T1": "gasto S1 decidido como transferencia propia (S20-10): se dispone en dominios 6/7 (F04-D001), "
             "sin gasto ni ingreso; destino identificado por gestor V3 (candidata unica).",
    "D8B-A": "derecho de cobro = entidad DERECHO_OBLIGACION + subtipo; origen = fila V3 que lo genera "
              "(gasto adelantado) o, sin ella, las filas V3 que lo evidencian (cobros). Catalogo cerrado "
              "DERECHOS_V3 (Migration V3 §16/§28/§29); ninguna posicion se deduce por nombre.",
    "D8B-B": "posicion transitoria liquidada antes del corte: importe_original_documentado = cobro V3 de "
              "liquidacion; saldo_apertura 0 al corte; CERRADA/LIQUIDADA; fecha_cierre NULL (la fecha del "
              "cobro se dispone en dominio 6). Canon 330,11 / 7 posiciones.",
    "D8B-C": "contraparte sin fila V3 que la identifique -> NULL (desconocida), salvo decision del propietario "
              "en la fuente suplementaria (S20-11).",
    "D8B-D": "principal original desconocido -> importe_original_documentado NULL; saldo indeterminado -> "
              "saldo_apertura y fecha_inicio_seguimiento NULL, ACTIVA (Migration V3 §16; nunca 0).",
    "D8B-E": "moneda EUR (S20-2).",
    "D9-A": "inversion V3 -> entidad INVERSION + inversiones como POSICION sin padre (V3 no tiene jerarquia; "
             "CONTENEDOR no demostrado). La fila V3 que es cuenta (Migration V3 §29) no se duplica: dominio 3.",
    "D9-B": "tercero_gestor_id = proveedor V3 cuando proveedor_id y dealer_id coinciden; si discrepan -> S20.",
    "D9-C": "objetivos V3 (aporte/retorno esperado, roi, irr, moic, plazo, salida objetivo) -> una version de "
             "inversion_objetivos_versiones con vigencia NULL (inicio no demostrado; D-MIG-016). Nunca valoracion.",
    "D9-D": "capital_invertido_apertura NULL: aporte_estimado no es capital real (D-MIG-016).",
    "D9-E": "resultado final V3 (retorno_final_total, plazo_final) de una inversion cerrada: plazo_real_meses si "
             "conocido; el retorno realizado se dispone en dominio 6 (hecho), nunca como objetivo. fecha_fin_real "
             "y motivo_cierre desconocidos -> NULL (Migration V3 §27).",
    "D9-F": "tipo_producto NOT NULL sin dato V3: TIPO_PRODUCTO_PROPUESTO por inversion; fuera de laboratorio "
             "falla S20 hasta confirmacion del propietario.",
    "D9-G": "entidad_participaciones de inversiones: 100 % propietario desde fecha_inicio V3 (S20 R3-2).",
    "D9-H": "tipo de producto sin valor propio en el CHECK de 0330 (joint venture): OTRO + declaracion en "
             "notas; no es clase G (OTRO es representacion fiel) salvo que se requiera filtrar por el tipo.",
    "D8B-H": "contraparte = persona V3 declarada por el propietario (S20 R3-4), validada: debe figurar como "
              "inquilino en un contrato V3 de la vivienda referenciada por el gasto generador; si no -> S1.",
    "D10-A": "contrato V3 -> entidad CONTRATO + contratos; tipo por objeto_alquiler segun TIPO_CONTRATO_V3 "
              "(tabla cerrada; valor no mapeado -> S4); estado V3 'activo' -> FORMALIZADO.",
    "D10-B": "fecha_inicio = V3 salvo correccion validada por el propietario (Migration V3 §9/§27: contrato "
              "Francisco 2026-03-01); literal V3 conservado en origen. fecha_fin 141 -> NULL.",
    "D10-C": "renta_mensual -> regla financiera del dominio 5 (regla_renta_id se completa alli).",
    "D10-D": "participantes: rol V3 -> INQUILINO/AVALISTA/GESTOR; la persona propia (D2-C) -> actor self; "
              "vigente_desde = inicio del contrato. Fila inactivada: vigente_hasta = dia anterior a la "
              "inactivacion y la fila activa del mismo actor/rol empieza ese dia (Migration V3 §27: se migran "
              "ambas vigencias, sin deduplicar).",
    "D10-E": "incremento_ipc -> contrato_revision_renta_versiones IPC (true) / NINGUNA (false), vigente desde "
              "el inicio del contrato; periodicidad e indice no demostrados -> NULL.",
    "D10-F": "incluye_agua/luz/internet = false y suministros a cargo del inquilino: no se crean servicios ni "
              "contrato_servicios (seria fabricar entidades); flags conservados en origen.",
    "D10-G": "contextos: V3 no tiene entidad de contexto; se disponen en dominio 6 si un hecho lo demuestra.",
    "D10-H": "patrimonio_compra -> propiedad_valoraciones: COMPRA (valor_compra, fecha = fecha_adquisicion de "
              "la propiedad), MERCADO (valor_mercado, valor_mercado_fecha), FISCAL_REFERENCIA (valor_referencia, "
              "fecha NULL). total_inversion es control derivado (se comprueba, no se guarda); impuestos, "
              "notaria, agencia y reforma son costes -> dominio 6.",
    "D10-I": "fianza V3 > 0 -> OBLIGACION_PAGO abierta (S20 R4-3): importe y saldo al corte = fianza; "
              "contraparte = inquilino principal V3 del contrato; participacion 100 % propietario desde el inicio "
              "del contrato (criterio S20 R2-7); los desperfectos futuros se registraran como hechos.",
    "D10-J": "fila de participante duplicada por captura (S20 R4-2): no se crea; su origen se FUSIONA en la "
              "superviviente, que cubre desde el inicio del contrato. Corrige Migration V3 §27 (ambas vigencias).",
    "D10-K": "servicio repercutible decidido (S20 R4-4): entidad SERVICIO + contrato_servicios repercutible "
              "100 % al actor declarado, validado como inquilino del contrato; vigencia = inicio del contrato. "
              "propiedad_servicios no se crea (existencia del suministro previa no demostrada).",
    "D2-E": "categorias = arbol canonico de Migration V3 v0.40 §15.2 (opcion A, arquitectura 2026-09-21) como "
             "fuente suplementaria ARBOL_CATEGORIAS_MV3 con SHA-256 del bloque; nombre literal del documento; orden = "
             "posicion entre hermanos; codigo NULL; ambito INGRESO para las raices de ingreso del arbol y GASTO "
             "para el resto; presupuestable_default PROPUESTO (GASTO si, INGRESO no) hasta validacion (S20).",
    "D2-E2": "clasificacion de cada registro operativo: decision por registro de la fuente suplementaria "
              "(tipos heterogeneos; hoja REGISTROS aceptada en bloque) > tabla CATEGORIA_POR_TIPO_V3 (hoja TIPOS "
              "validada) ; FUERA = naturaleza distinta de categoria (transferencia, aportacion, cuota, derecho); "
              "desglose exacto solo cuando el origen canonico lo da (Migration V3 §15.2).",
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
    modo_lab: bool = False
    self_id: str | None = None
    categorias: dict = field(default_factory=dict)
    clasificacion: dict = field(default_factory=dict)
    decisiones: "Decisiones | None" = None
    preguntas: list = field(default_factory=list)
    reglas: dict = field(default_factory=dict)
    hechos: dict = field(default_factory=dict)
    tesoreria: dict = field(default_factory=dict)
    cierres: dict = field(default_factory=dict)
    trazabilidad: dict = field(default_factory=dict)

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
        etq = tabla or "sin_destino"  # OBSOLETO/IGNORADO sin destino (DB Schema §77)
        mid = fu.uuid_v3(cont, clave, "mapeos_importacion", f"{etq}.{rol}")
        self.add("mapeos_importacion", {
            "id": mid, "registro_origen_id": origen, "tabla_destino": tabla,
            "registro_destino_id": destino, "tipo_mapping": tipo,
            "transformacion_codigo": f"{TRANSFORMACION}.{etq}.{rol}",
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


# ------------------------------------------------------------ fuente suplementaria S20
# Decisiones del propietario que crean filas sin registro V3 (personas cotitulares y
# repartos). El fichero vive FUERA del repositorio (contiene PII) y se fija por SHA-256.
# Cada persona y cada reparto es un registro origen propio de una fuente distinta de RUN06.
CONT_DECISIONES = "rv3.decisiones_propietario"
# Aprobada por arquitectura (respuesta 1, 2026-09-21).
ARQ_FUENTE_DECISIONES_ESTADO = "APROBADA"


@dataclass
class Decisiones:
    sha256: str
    doc: dict


def cargar_decisiones(path: Path) -> Decisiones:
    raw = Path(path).read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    personas, reps = doc.get("personas"), doc.get("participaciones")
    if not doc.get("id") or not isinstance(personas, dict) or not isinstance(reps, list):
        raise ErrorP5("S4_DECISIONES_FORMATO", "id/personas/participaciones")
    vistos = set()
    for it in reps:
        if it.get("id") in vistos or not it.get("id") or not it.get("origen") or "/" not in it["origen"]:
            raise ErrorP5("S4_DECISIONES_FORMATO", f"participacion {it.get('id')}")
        vistos.add(it["id"])
        refs = [r for r, _ in it.get("repartos", [])]
        if len(refs) != len(set(refs)) or any(r != "SELF" and r not in personas for r in refs):
            raise ErrorP5("S8_DECISION_ACTOR_DESCONOCIDO", it["id"])
        if sum(Decimal(str(x)) for _, x in it["repartos"]) != Decimal(100) or \
                any(Decimal(str(x)) <= 0 for _, x in it["repartos"]):
            raise ErrorP5("S9_DECISION_REPARTO_NO_100", it["id"])
    for c in doc.get("contrapartes", []) + doc.get("financiadores", []):
        if c.get("id") in vistos or not c.get("id") or c.get("persona") not in personas or "/" not in c.get("origen", ""):
            raise ErrorP5("S4_DECISIONES_FORMATO", f"contraparte {c.get('id')}")
        vistos.add(c["id"])
    for k, pe in personas.items():
        if not k or k == "SELF" or not (pe.get("nombre") or "").strip():
            raise ErrorP5("S4_DECISIONES_FORMATO", f"persona {k}")
    origenes = set()
    for c in doc.get("capacidades", []):
        cods = c.get("codigos")
        if c.get("id") in vistos or not c.get("id") or "/" not in c.get("origen", "") or not isinstance(cods, list) \
                or not cods or len(cods) != len(set(cods)) or any(x not in CAPACIDADES_CATALOGO for x in cods):
            raise ErrorP5("S4_DECISIONES_FORMATO", f"capacidad {c.get('id')}")
        if ("cap", c["origen"]) in origenes:
            raise ErrorP5("S7_DECISION_DUPLICADA", c["origen"])
        vistos.add(c["id"]); origenes.add(("cap", c["origen"]))
    for g in doc.get("geolocalizaciones", []):
        try:
            la, lo = Decimal(str(g["latitud"])), Decimal(str(g["longitud"]))
        except Exception:
            raise ErrorP5("S4_DECISIONES_FORMATO", f"geolocalizacion {g.get('id')}")
        if g.get("id") in vistos or not g.get("id") or not str(g.get("origen", "")).startswith("public.patrimonio/") \
                or not (-90 <= la <= 90) or not (-180 <= lo <= 180):
            raise ErrorP5("S4_DECISIONES_FORMATO", f"geolocalizacion {g.get('id')}")
        if ("geo", g["origen"]) in origenes:
            raise ErrorP5("S7_DECISION_DUPLICADA", g["origen"])
        vistos.add(g["id"]); origenes.add(("geo", g["origen"]))
    return Decisiones(hashlib.sha256(raw).hexdigest(), doc)


def _gate_decisiones(ds: Dataset, motivo: str) -> None:
    if ARQ_FUENTE_DECISIONES_ESTADO == "APROBADA":
        return
    if not ds.modo_lab:
        raise ErrorP5("S20_ARQ_FUENTE_DECISIONES", motivo)
    if not any(p.get("S20") == "ARQ_FUENTE_DECISIONES" for p in ds.pendientes):
        ds.pendientes.append({"S20": "ARQ_FUENTE_DECISIONES", "estado": ARQ_FUENTE_DECISIONES_ESTADO,
                              "efecto": "filas de la fuente suplementaria creadas SOLO en laboratorio"})


def dominio_12_decisiones(ds: Dataset) -> None:
    dec = ds.decisiones
    if dec is None:
        return
    _gate_decisiones(ds, "fuente suplementaria")
    fid = fu.uuid_v3("DECISIONES", dec.sha256, "fuentes_importacion", "fuente")
    ds.add("fuentes_importacion", {
        "id": fid, "owner_user_id": ds.owner, "tipo_fuente": "OTRO",
        "nombre_fuente": f"Decisiones del propietario S20 ({dec.doc['id']})",
        "version_fuente": str(dec.doc.get("fecha") or ""), "pipeline_version": f"{TRANSFORMACION} {VERSION}",
        "sha256": dec.sha256, "estado": "SIMULADA",
        "notas": "fuente suplementaria sin fila V3 (D-S20-F); PENDIENTE de arquitectura"})
    items = [(f"persona/{k}", {"persona": k, **v}) for k, v in sorted(dec.doc["personas"].items())] + \
            [(f"participacion/{it['id']}", it) for it in sorted(dec.doc["participaciones"], key=lambda x: x["id"])] + \
            [(f"contraparte/{c['id']}", c) for c in sorted(dec.doc.get("contrapartes", []), key=lambda x: x["id"])] + \
            [(f"financiador/{c['id']}", c) for c in sorted(dec.doc.get("financiadores", []), key=lambda x: x["id"])] + \
            [(f"capacidad/{c['id']}", c) for c in sorted(dec.doc.get("capacidades", []), key=lambda x: x["id"])] + \
            [(f"geolocalizacion/{g['id']}", g) for g in sorted(dec.doc.get("geolocalizaciones", []), key=lambda x: x["id"])] + \
            [(f"contexto/{c['id']}", c) for c in sorted(dec.doc.get("contextos", []), key=lambda x: x["id"])] + \
            ([(f"clasificacion/{dec.doc['clasificacion']['id']}", dec.doc["clasificacion"])] if dec.doc.get("clasificacion") else [])
    for n, (clave, d) in enumerate(items, 1):
        t = json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        ds.add("registros_origen_importacion", {
            "id": fu.uuid_origen(CONT_DECISIONES, clave), "fuente_importacion_id": fid,
            "contenedor_origen": CONT_DECISIONES, "clave_origen": clave, "numero_fila_origen": n,
            "datos_origen": d, "datos_origen_texto": t,
            "sha256_registro": hashlib.sha256(t.encode("utf-8")).hexdigest()},
            natural=(CONT_DECISIONES, clave))
    ds.ledger.append({"regla": "D-S20-F", "origen": CONT_DECISIONES, "sha256": dec.sha256})
    for k, pe in sorted(dec.doc["personas"].items()):
        clave = f"persona/{k}"
        tid = fu.uuid_v3(CONT_DECISIONES, clave, "terceros", "tercero")
        nat = pe.get("naturaleza", "PERSONA")
        if nat not in ("PERSONA", None):
            raise ErrorP5("S4_DECISIONES_FORMATO", f"naturaleza de {k}")
        ds.add("terceros", {"id": tid, "owner_user_id": ds.owner, "nombre": pe["nombre"].strip(),
                            "naturaleza": nat, "identificador_fiscal": None,
                            "tipo_identificador_fiscal": None, "pais_fiscal_id": None, "email": None,
                            "telefono": None, "notas": None})
        ds.mapear(CONT_DECISIONES, clave, "terceros", tid, "tercero", confianza="VALIDADA")
        if nat == "PERSONA":
            ds.add("tercero_personas", {"tercero_id": tid, "fecha_nacimiento": None})
            ds.mapear(CONT_DECISIONES, clave, "tercero_personas", tid, "persona", tipo="DIVIDIDO", confianza="VALIDADA")
        aid = fu.uuid_v3(CONT_DECISIONES, clave, "actores_financieros", "actor")
        ds.add("actores_financieros", {"id": aid, "owner_user_id": ds.owner, "tercero_id": tid},
               natural=(ds.owner, tid))
        ds.mapear(CONT_DECISIONES, clave, "actores_financieros", aid, "actor", tipo="DIVIDIDO", confianza="VALIDADA")


def decision_de(ds: Dataset, origen: str) -> dict | None:
    if ds.decisiones is None:
        return None
    its = [it for it in ds.decisiones.doc["participaciones"] if it["origen"] == origen]
    if len(its) > 1:
        raise ErrorP5("S7_DECISION_DUPLICADA", origen)
    return its[0] if its else None


def _actor_decidido(ds: Dataset, ref: str) -> str:
    if ref == "SELF":
        return ds.self_id
    return fu.uuid_v3(CONT_DECISIONES, f"persona/{ref}", "actores_financieros", "actor")


def _desde_decidido(ds: Dataset, it: dict) -> str:
    d = it.get("desde")
    if isinstance(d, dict) and set(d) == {"fecha_adquisicion_de"}:
        co, cl = d["fecha_adquisicion_de"].split("/", 1)
        pid = fu.uuid_v3(co, cl, "entidades", "propiedad")
        prop = ds.filas["propiedades"].get(pid)
        if prop is None or not prop["fecha_adquisicion"]:
            raise ErrorP5("S8_DECISION_FECHA_SIN_ORIGEN", it["id"])
        return prop["fecha_adquisicion"]
    if isinstance(d, str) and len(d) == 10 and d[4] == d[7] == "-":
        return d
    raise ErrorP5("S4_DECISIONES_FORMATO", f"desde de {it['id']}")


def aplicar_reparto(ds: Dataset, it: dict, tabla: str, fk: str, destino: str, pct_v3) -> str:
    """Crea el reparto decidido (suma 100). Si V3 conoce la cuota propia y la decision la
    contradice, exige corrige_v3 explicito (Migration V3 §9: Blasco 1 % = 0 % real)."""
    _gate_decisiones(ds, it["id"])
    self_pct = sum((Decimal(str(x)) for r, x in it["repartos"] if r == "SELF"), Decimal(0))
    if pct_v3 is not None and Decimal(str(pct_v3)) != self_pct and not it.get("corrige_v3"):
        raise ErrorP5("S1_DECISION_CONTRADICE_V3", f"{it['id']} v3={pct_v3} decision={self_pct}")
    desde = _desde_decidido(ds, it)
    clave = f"participacion/{it['id']}"
    for ref, pct in it["repartos"]:
        rid = fu.uuid_v3(CONT_DECISIONES, clave, tabla, ref)
        ds.add(tabla, {"id": rid, fk: destino, "actor_id": _actor_decidido(ds, ref),
                       "porcentaje": Decimal(str(pct)), "vigente_desde": desde, "vigente_hasta": None})
        ds.mapear(CONT_DECISIONES, clave, tabla, rid, f"reparto.{ref}", confianza="VALIDADA")
    ds.ledger.append({"regla": "D-S20-F", "origen": it["origen"], "decision": it["id"], "tabla": tabla})
    return desde


# ------------------------------------------------------------ categorias (D2-E, opcion A)
CONT_ARBOL = "rv3.arbol_categorias_mv3"
ARBOL_VERSION = "Migration V3 v0.40 §15.2 (arbol baseline resumido)"
ARBOL_CATEGORIAS_MV3 = """SUPERMERCADOS
RESTAURANTES
VIVIENDA Y HOGAR
├── Suministros
│   ├── Electricidad
│   ├── Agua
│   └── Alarma y seguridad
├── Comunidad
│   ├── Cuota de comunidad
│   └── Derramas
├── Limpieza doméstica
├── Reparaciones y mantenimiento
├── Mejoras y reforma
└── Equipamiento del hogar
MOVILIDAD
├── Combustible
├── Peajes
├── Parking
├── Transporte
│   ├── Vuelos
│   ├── Tren
│   ├── Barco
│   ├── Autobús
│   ├── Metro
│   └── Coche compartido
├── Mantenimiento y cuidado del vehículo
└── Accesorios y equipamiento
ALOJAMIENTO
SALUD
├── Farmacia
├── Fisioterapia
├── Psicología
├── Nutrición
└── Dental
DEPORTE
├── Gimnasio
├── Natación
├── Buceo
├── Entrenamiento personal
├── Carreras y competiciones
├── Material y equipamiento deportivo
├── Suplementos
└── Cuotas y licencias deportivas
CUIDADO PERSONAL
├── Peluquería
└── Estética
ROPA Y COMPLEMENTOS
├── Ropa y calzado
└── Complementos personales
TECNOLOGÍA E INFORMÁTICA
└── Accesorios y periféricos
OCIO Y CULTURA
├── Actividades
├── Horticultura
├── Videojuegos
├── Cine y vídeo
├── Streaming
├── Libros y cómics
├── Juegos y ocio
├── Eventos y espectáculos
└── Lotería
REGALOS Y DETALLES
FORMACIÓN
├── Idiomas
└── Cursos y formación
COMUNICACIONES Y DIGITAL
├── Telefonía e internet
├── Software y servicios digitales
└── Plataformas digitales
SEGUROS
├── Hogar
├── Vida
├── Mascotas
└── Viaje
ADMINISTRACIÓN, IMPUESTOS Y TASAS
├── IBI
├── IRPF / Renta
├── Documentación y trámites
├── Licencias y tasas
└── Multas y sanciones
SERVICIOS PROFESIONALES
COSTES FINANCIEROS
└── Intereses y costes de financiación
INGRESOS LABORALES
├── Nómina
├── Dietas y complementos
└── Trabajos esporádicos
PRESTACIONES
└── Desempleo
ALQUILERES
RENDIMIENTOS FINANCIEROS
└── Intereses de cuentas e inversiones
VENTA DE BIENES"""
RAICES_INGRESO = {"INGRESOS LABORALES", "PRESTACIONES", "ALQUILERES", "RENDIMIENTOS FINANCIEROS", "VENTA DE BIENES"}
CATEGORIAS_ESTADO = "CONFIRMADA"  # hoja ARBOL_MV3 aceptada en bloque (opcion 1, 2026-09-21)
CATEGORIAS_ACTIVAS = True
# Hoja TIPOS validada (2026-09-21). Valor: ruta canonica normalizada | POR_REGISTRO | FUERA: <naturaleza> | SIN_USO.
CATEGORIA_POR_TIPO_V3 = {
    'ACT-TIPOGASTO-2X9H1Q': 'POR_REGISTRO',
    'AEA-TIPOGASTO-J06VRO': 'ADMINISTRACION, IMPUESTOS Y TASAS > IRPF / RENTA',
    'AHO-TIPOGASTO-470C59B8': 'FUERA: transferencia entre cuentas propias',
    'BIZ-TIPOINGRESO-6UJSD0': 'POR_REGISTRO',
    'CAP-TIPOGASTO-334BFEC7': 'POR_REGISTRO',
    'COM-TIPOGASTO-311A33BD': 'SUPERMERCADOS',
    'COM-TIPOGASTO-689645A0': 'VIVIENDA Y HOGAR > COMUNIDAD > CUOTA DE COMUNIDAD',
    'DER-TIPOGASTO-580F0N': 'VIVIENDA Y HOGAR > COMUNIDAD > DERRAMAS',
    'DES-TIPO_INGRESO-1JNN5I': 'PRESTACIONES > DESEMPLEO',
    'DEV-TIPO_INGRESO-9MD2NR': 'FUERA: devolucion de capital (reduce derecho)',
    'ELE-TIPOGASTO-47CC77E5': 'VIVIENDA Y HOGAR > SUMINISTROS > ELECTRICIDAD',
    'EXT-TIPO_INGRESO-BKKW27': 'SIN_USO',
    'FIN-TIPOGASTO-CC19E5D9': 'POR_REGISTRO',
    'FON-TIPOGASTO-F271A9D9': 'FUERA: aportacion a inversion',
    'HIP-TIPOGASTO-1D7B749B': 'FUERA: cuota de financiacion (interes -> COSTES FINANCIEROS > INTERESES Y COSTES DE FINANCIACION)',
    'HOS-TIPOGASTO-357FDG': 'ALOJAMIENTO',
    'HOT-TIPOGASTO-357FDG': 'ALOJAMIENTO',
    'LIQ-TIPOINGRESO-JVS25Q': 'RENDIMIENTOS FINANCIEROS > INTERESES DE CUENTAS E INVERSIONES',
    'MAN-TIPOGASTO-8FA20F09': 'VIVIENDA Y HOGAR > REPARACIONES Y MANTENIMIENTO',
    'MAV-TIPOGASTO-BVC356': 'MOVILIDAD > MANTENIMIENTO Y CUIDADO DEL VEHICULO',
    'MEJ-TIPOGASTO-52C6B7D9': 'POR_REGISTRO',
    'NOM-TIPO_INGRESO-N21P2F': 'INGRESOS LABORALES > NOMINA',
    'PAR-TIPOGASTO-5JKK5D': 'MOVILIDAD > PARKING',
    'PEA-TIPOGASTO-7HDY89': 'MOVILIDAD > PEAJES',
    'PRE-TIPOGASTO-DF858F12': 'FUERA: cuota de financiacion (interes -> COSTES FINANCIEROS)',
    'RES-TIPOGASTO-26ROES': 'RESTAURANTES',
    'ROP-TIPOGASTO-S227BB': 'ROPA Y COMPLEMENTOS > ROPA Y CALZADO',
    'SAL-TIPOGASTO-03B17403': 'POR_REGISTRO',
    'SEG-TIPOGASTO-C3MR9Y': 'POR_REGISTRO',
    'SUS-TIPOGASTO-FD321542': 'POR_REGISTRO',
    'TAR-TIPOGASTO-LC70SY': 'FUERA: amortizacion de tarjeta (transferencia)',
    'TAS-TIPOGASTO-UBBCAG': 'SERVICIOS PROFESIONALES',
    'TGAS-34HJV4': 'VIVIENDA Y HOGAR > SUMINISTROS > ELECTRICIDAD',
    'TGAS-71U318': 'POR_REGISTRO',
    'TGAS-8OS99A': 'ADMINISTRACION, IMPUESTOS Y TASAS > DOCUMENTACION Y TRAMITES',
    'TGAS-D0HQH4': 'FUERA: aportacion a inversion',
    'TGAS-TQMYN1': 'FUERA: cuenta de ahorro',
    'TGAS-XMKMUE': 'FUERA: aportacion a inversion (joint venture)',
    'TING-2059DN': 'FUERA: reembolso de suministros (reduce derecho)',
    'TING-2IB5N9': 'FUERA: reintegro de ahorro (transferencia)',
    'TING-9MCM5N': 'FUERA: devolucion de compra (reduce el gasto original)',
    'TING-FALQNB': 'INGRESOS LABORALES > DIETAS Y COMPLEMENTOS',
    'TING-YPN3X2': 'VENTA DE BIENES',
    'TIP-GASOLINA-SW1ZQO': 'MOVILIDAD > COMBUSTIBLE',
    'TIP-IBI-1BTR4W': 'ADMINISTRACION, IMPUESTOS Y TASAS > IBI',
    'TIP-INGLES-8CIIGN': 'FORMACION > IDIOMAS',
    'TIP-SEGURO HOGAR-SGQCAZ': 'SEGUROS > HOGAR',
    'TIP-SEGURO VIDA-7CHKTS': 'SEGUROS > VIDA',
    'TRA-TIPOGASTO-RB133Z': 'POR_REGISTRO',
    'TRA-TIPOINGRESO-S11CGL': 'INGRESOS LABORALES > TRABAJOS ESPORADICOS',
    'VIA-TIPOGASTO-6JPV7K': 'POR_REGISTRO',
    'VIV-TIPO_INGRESO-FKV95F': 'ALQUILERES',
}
CONTENEDORES_OPERATIVOS = ("public.gastos", "public.gastos_cotidianos", "public.ingresos")


def _norm(t: str) -> str:
    import unicodedata as _u
    return _u.normalize("NFKD", t).encode("ascii", "ignore").decode().upper().strip()


def _cat_por_ruta(ds: Dataset, ruta_norm: str) -> str:
    for ruta, cid in ds.categorias.items():
        if " > ".join(_norm(x) for x in ruta) == ruta_norm:
            return cid
    raise ErrorP5("S1_CATEGORIA_NO_CANONICA", ruta_norm)


def clasificar(ds: Dataset, co: str, cl: str, fila: dict) -> tuple:
    """-> ('CAT', id) | ('NULL', None) | ('FUERA', naturaleza) | ('DESGLOSE', [(id, Decimal)])."""
    regs = (ds.decisiones.doc.get("clasificacion") or {}).get("registros", {}) if ds.decisiones else {}
    clave = f"{co}/{cl}"
    tipo = CATEGORIA_POR_TIPO_V3.get(str(fila.get("tipo_id")))
    if tipo is None:
        raise ErrorP5("S4_TIPO_SIN_CLASIFICACION", f"{clave} tipo={fila.get('tipo_id')}")
    if clave in regs:
        v = regs[clave]
        if v is None:
            return ("NULL", None)
        if isinstance(v, dict) and "desglose" in v:
            return ("DESGLOSE", [(_cat_por_ruta(ds, r), Decimal(str(x))) for r, x in v["desglose"]])
        if isinstance(v, str):
            return ("CAT", _cat_por_ruta(ds, v))
        raise ErrorP5("S4_CLASIFICACION_FORMATO", clave)
    if tipo.startswith("FUERA"):
        return ("FUERA", tipo.split(":", 1)[1].strip())
    if tipo in ("POR_REGISTRO", "SIN_USO"):
        raise ErrorP5("S20_CLASIFICACION_REGISTRO", clave)
    return ("CAT", _cat_por_ruta(ds, tipo))


def verificar_clasificacion(ds: Dataset, fuente: dict) -> dict:
    """Resuelve todos los registros operativos V3 (control previo a los dominios 5/6)."""
    if not ds.categorias:
        return {}
    regs = (ds.decisiones.doc.get("clasificacion") or {}).get("registros", {}) if ds.decisiones else {}
    for clave in regs:
        co, cl = clave.split("/", 1)
        if cl not in fuente.get(co, {}):
            raise ErrorP5("S8_CLASIFICACION_SIN_ORIGEN", clave)
    cuenta = {}
    for co in CONTENEDORES_OPERATIVOS:
        for cl, fila in fuente.get(co, {}).items():
            r = clasificar(ds, co, cl, fila)
            if r[0] == "DESGLOSE":
                tot = fila.get("total") if fila.get("total") not in (None, "141") else fila.get("importe")
                if sum(x for _, x in r[1]) != Decimal(str(tot)):
                    raise ErrorP5("S9_DESGLOSE_NO_CUADRA", f"{co}/{cl}")
            cuenta[r[0]] = cuenta.get(r[0], 0) + 1
    ds.ledger.append({"regla": "D2-E2", "origen": "clasificacion", "resumen": cuenta})
    return cuenta  # ambito/presupuestable pendientes de validacion del propietario


def parsear_arbol(texto: str) -> list:
    """-> [(ruta_tupla, nombre, orden)] en orden de documento; falla ante sangria incoherente o duplicados."""
    import re as _re
    out, pila, hijos, vistos = [], [], {}, set()
    for linea in texto.split("\n"):
        if not linea.strip():
            continue
        pre = _re.match(r"^((?:│   |    )*)", linea).group(1)
        rama = _re.search(r"├── |└── ", linea) is not None
        nombre = _re.sub(r"^((?:│   |    )*)(├── |└── )?", "", linea).strip()
        prof = len(pre) // 4 + (1 if rama else 0)
        if prof > len(pila) or not nombre:
            raise ErrorP5("S4_ARBOL_MAL_FORMADO", linea)
        pila = pila[:prof] + [nombre]
        ruta = tuple(pila)
        if ruta in vistos:
            raise ErrorP5("S7_ARBOL_DUPLICADO", " > ".join(ruta))
        vistos.add(ruta)
        orden = hijos.get(ruta[:-1], 0)
        hijos[ruta[:-1]] = orden + 1
        out.append((ruta, nombre, orden))
    return out


def dominio_2_categorias(ds: Dataset) -> dict:
    """Crea el arbol canonico; devuelve ruta_tupla -> categoria_id."""
    if CATEGORIAS_ESTADO != "CONFIRMADA":
        if not ds.modo_lab:
            raise ErrorP5("S20_CATEGORIAS", "ambito/presupuestable_default pendientes de validacion")
        ds.pendientes.append({"S20": "CATEGORIAS", "estado": CATEGORIAS_ESTADO})
    sha = hashlib.sha256(ARBOL_CATEGORIAS_MV3.encode("utf-8")).hexdigest()
    fid = fu.uuid_v3("ARBOL", sha, "fuentes_importacion", "fuente")
    ds.add("fuentes_importacion", {
        "id": fid, "owner_user_id": ds.owner, "tipo_fuente": "OTRO", "nombre_fuente": "Arbol de categorias canonico (D2-E)",
        "version_fuente": ARBOL_VERSION, "pipeline_version": f"{TRANSFORMACION} {VERSION}", "sha256": sha,
        "estado": "SIMULADA", "notas": "fuente suplementaria: documento canonico, no fila V3"})
    ids = {}
    for n, (ruta, nombre, orden) in enumerate(parsear_arbol(ARBOL_CATEGORIAS_MV3), 1):
        clave = " > ".join(ruta)
        d = {"ruta": list(ruta), "nombre": nombre, "orden": orden}
        t = json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        ds.add("registros_origen_importacion", {
            "id": fu.uuid_origen(CONT_ARBOL, clave), "fuente_importacion_id": fid, "contenedor_origen": CONT_ARBOL,
            "clave_origen": clave, "numero_fila_origen": n, "datos_origen": d, "datos_origen_texto": t,
            "sha256_registro": hashlib.sha256(t.encode("utf-8")).hexdigest()}, natural=(CONT_ARBOL, clave))
        ambito = "INGRESO" if ruta[0] in RAICES_INGRESO else "GASTO"
        cid = fu.uuid_v3(CONT_ARBOL, clave, "categorias_financieras", "categoria")
        ds.add("categorias_financieras", {
            "id": cid, "owner_user_id": ds.owner, "parent_id": ids.get(ruta[:-1]), "nombre": nombre, "codigo": None,
            "ambito": ambito, "presupuestable_default": ambito == "GASTO", "orden": orden},
            natural=(ds.owner, ids.get(ruta[:-1]), nombre))
        ds.mapear(CONT_ARBOL, clave, "categorias_financieras", cid, "categoria")
        ids[ruta] = cid
    ds.ledger.append({"regla": "D2-E", "origen": CONT_ARBOL, "sha256": sha, "nodos": len(ids)})
    return ids


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
    ds.self_id = self_id
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
        dec = decision_de(ds, f"{cont}/{cc}")
        if dec is not None:
            aplicar_reparto(ds, dec, "cuenta_participaciones", "cuenta_id", cid,
                            pct.valor if pct.estado == fu.CONOCIDO else None)
        elif pct.estado == fu.CONOCIDO and Decimal(str(pct.valor)) != Decimal(100):
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
    for c in sorted((ds.decisiones.doc.get("capacidades", []) if ds.decisiones else []), key=lambda x: x["id"]):
        _gate_decisiones(ds, c["id"])
        co, cl = c["origen"].split("/", 1)
        cid = fu.uuid_v3(co, cl, "cuentas", "cuenta")
        if cid not in ds.filas["cuentas"]:
            raise ErrorP5("S8_DECISION_SIN_ORIGEN", f"capacidad {c['id']} -> {c['origen']}")
        clave = f"capacidad/{c['id']}"
        for cod in c["codigos"]:
            rid = fu.uuid_v3(CONT_DECISIONES, clave, "cuenta_capacidades", cod)
            ds.add("cuenta_capacidades", {"id": rid, "cuenta_id": cid, "capacidad_codigo": cod},
                   natural=(cid, cod))
            ds.mapear(CONT_DECISIONES, clave, "cuenta_capacidades", rid, f"capacidad.{cod}", confianza="VALIDADA")
    ds.ledger.append({"regla": "D3-D", "origen": "cuenta_capacidades"})
    ds.ledger.append({"regla": "DV-10", "origen": "RUN06.cuentas"})


# ------------------------------------------------------------ dominio 4
CAPACIDADES_CATALOGO = ("PAGAR_GASTO", "RECIBIR_INGRESO", "TRANSFERIR_SALIDA", "TRANSFERIR_ENTRADA",
                        "DOMICILIAR", "COMPRA_TARJETA")  # ck_cuenta_capacidades__capacidad_codigo (0330)
_DIR_V3 = (("calle", "via_nombre"), ("numero", "numero"), ("escalera", "escalera"), ("piso", "planta"),
           ("puerta", "puerta"))
_Q6 = Decimal("0.000001")


def _localidad_por_nombre(fuente: dict, ctx: dict, nombre: str, origen: str) -> str:
    cand = [cl for cl, loc in sorted(fuente.get("public.localidades", {}).items())
            if (t := _celda("public.localidades", "nombre", loc, ctx)).estado == fu.CONOCIDO
            and _norm(str(t.valor)) == _norm(nombre)]
    if not cand:
        raise ErrorP5("S8_LOCALIDAD_SIN_MAESTRO", origen)
    if len(cand) > 1:
        raise ErrorP5("S7_LOCALIDAD_AMBIGUA", origen)
    return fu.uuid_v3("public.localidades", cand[0], "localidades", "localidad")


def _direccion(ds: Dataset, fuente: dict, ctx: dict, cont: str, cp: str, g) -> str | None:
    campos = {dst: _texto(g(src)).strip() for src, dst in _DIR_V3
              if g(src).estado == fu.CONOCIDO and _texto(g(src)) and _texto(g(src)).strip()}
    loc = g("localidad")
    lid = None
    if loc.estado == fu.CONOCIDO and _texto(loc) and _texto(loc).strip():
        lid = _localidad_por_nombre(fuente, ctx, _texto(loc), f"{cont}/{cp}")
    if not campos and lid is None:
        return None
    did = fu.uuid_v3(cont, cp, "direcciones", "direccion")
    fila = {"id": did, "owner_user_id": ds.owner, "localidad_id": lid, "codigo_postal": None, "via_tipo": None,
            "via_nombre": None, "numero": None, "bloque": None, "escalera": None, "planta": None, "puerta": None,
            "observaciones": None}
    fila.update(campos)
    ds.add("direcciones", fila)
    ds.mapear(cont, cp, "direcciones", did, "direccion", tipo="DIVIDIDO")
    return did


def _geolocalizacion(ds: Dataset, origen: str):
    its = [x for x in (ds.decisiones.doc.get("geolocalizaciones", []) if ds.decisiones else []) if x["origen"] == origen]
    if not its:
        return None
    g = its[0]
    _gate_decisiones(ds, g["id"])
    q = lambda v: Decimal(str(v)).quantize(_Q6, rounding=ROUND_HALF_UP)
    return g, q(g["latitud"]), q(g["longitud"])


def _dec(c):
    return Decimal(str(c.valor)) if c.estado == fu.CONOCIDO else None


def _int(c):
    return int(Decimal(str(c.valor))) if c.estado == fu.CONOCIDO else None


def _bool(c):
    return bool(c.valor) if c.estado == fu.CONOCIDO else None


def dominio_4_propiedades(ds: Dataset, fuente: dict, ctx: dict, modo_lab: bool) -> None:
    cont = "public.patrimonio"
    for g in (ds.decisiones.doc.get("geolocalizaciones", []) if ds.decisiones else []):
        if g["origen"].split("/", 1)[1] not in fuente.get(cont, {}):
            raise ErrorP5("S8_DECISION_SIN_ORIGEN", f"geolocalizacion {g['id']} -> {g['origen']}")
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
        did = _direccion(ds, fuente, ctx, cont, cp, g)
        geo = _geolocalizacion(ds, f"{cont}/{cp}")
        ds.add("propiedades", {"entidad_id": eid, "direccion_id": did, "tipo_propiedad": tipo,
                               "referencia_catastral": None, "fecha_adquisicion": adq,
                               "fecha_salida_patrimonio": None, "motivo_salida": None,
                               "superficie_m2": _dec(g("superficie_m2")),
                               "superficie_construida_m2": _dec(g("superficie_construida")),
                               "habitaciones": _int(g("habitaciones")), "banos": _int(g("banos")),
                               "tiene_garaje": _bool(g("garaje")), "tiene_trastero": _bool(g("trastero")),
                               "incluir_en_rentabilidad": _bool(g("disponible")), "notas": None,
                               "latitud": geo[1] if geo else None, "longitud": geo[2] if geo else None,
                               "geolocalizacion_origen": "MANUAL" if geo else None})
        ds.mapear(cont, cp, "propiedades", eid, "propiedad", tipo="DIVIDIDO")
        if geo:
            ds.mapear(CONT_DECISIONES, f"geolocalizacion/{geo[0]['id']}", "propiedades", eid, "geolocalizacion",
                      tipo="DIVIDIDO", confianza="VALIDADA")
            ds.ledger.append({"regla": "D4-G", "origen": f"{cont}/{cp}", "decision": geo[0]["id"]})
        for r in ("D4-A", "D4-B"):  # D4-A revisada en v0.15.0
            ds.ledger.append({"regla": r, "origen": f"{cont}/{cp}"})
        pct = _dec(g("participacion_pct"))
        dec = decision_de(ds, f"{cont}/{cp}")
        if dec is not None:
            aplicar_reparto(ds, dec, "entidad_participaciones", "entidad_id", eid, pct)
        elif pct == Decimal(100) and adq:
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
TIPO_FINANCIACION_DECIDIDO: dict = {
    "prestamo-N622DI": "HIPOTECA",   # S20-7 (2026-09-21)
    "prestamo-wb8ysw": "PRESTAMO",   # S20-8 (2026-09-21): prestamo personal sin intereses
}
# S20-8: el proveedor V3 no es el prestamista declarado -> financiador NULL (D8-C2).
FINANCIADOR_NO_DEMOSTRADO = {"prestamo-wb8ysw"}
# S20-9: participacion 100 % propietario. vigente_desde NO fijada por el propietario:
# None = PROPUESTA fecha_inicio de la financiacion (D8-H2).
PARTICIPACION_FIN_SELF = {
    ("public.prestamo", "prestamo-0rmjg9"): None, ("public.prestamo", "prestamo-6d5rjp"): None,
    ("public.prestamo", "prestamo-wb8ysw"): None,
    ("public.gastos", "GASTO-4WG8DD"): None, ("public.gastos", "GASTO-B6RF5F"): None,
    ("public.gastos", "GASTO-DMNX6U"): None, ("public.gastos", "GASTO-T4I2U4"): None,
    ("public.gastos", "GASTO-Z0I8VL"): None, ("public.gastos", "gasto-6xec66"): None,
    ("public.gastos", "gasto-as0zyr"): None,
    # respuesta 2 del propietario (2026-09-21) a las compras decididas sin participacion
    ("public.gastos", "gasto-bsq0n8"): None, ("public.gastos", "gasto-ep2gra"): None,
    ("public.gastos", "gasto-x2t6dm"): None,
}
# Propuesta fecha_inicio ACEPTADA por el propietario (respuesta 4, 2026-09-21).
PARTICIPACION_FIN_VIGENCIA_ESTADO = "CONFIRMADA"
# S20-10: gasto S1 (no existe en B0) = transferencia propia hacia la cuenta Santander
# (candidata unica por gestor). Se dispone en dominios 6/7 (F04-D001); aqui solo se declara.
TRANSFERENCIA_PROPIA_DECIDIDA = {("public.gastos", "gasto-0e7jvy"): ("public.cuentas_bancarias", "CTA-H3PG1R")}
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
# Respuesta 3 del propietario (2026-09-21): los gastos a plazos sin tipo FINANCIACION son compras financiadas.
# Respuesta E (2026-09-21): cancelada antes del corte; el origen V3 NO se elimina (INV-RV3-01).
COMPRA_FINANCIADA_CANCELADA = {"gasto-pguksb"}
COMPRA_FINANCIADA_DECIDIDA = {"gasto-2t4xp3", "gasto-6p4sd2", "gasto-7sb205", "gasto-bsq0n8", "gasto-ep2gra",
                              "gasto-h45f25", "gasto-lqocej", "gasto-o678hf", "gasto-pguksb", "gasto-v56azl",
                              "gasto-w6xwkg", "gasto-x18xnq", "gasto-x2t6dm", "gasto-xpq796", "gasto-zz0qd0"}
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


def participaciones_financiacion(ds: Dataset, co: str, cl: str, eid: str, fecha_inicio) -> None:
    """S20-7 (reparto decidido con cotitular, fuente suplementaria) o S20-9 (100 % propietario,
    vigencia PROPUESTA = fecha_inicio). Sin decision: 0 filas (D8-H, nunca se infiere)."""
    origen = f"{co}/{cl}"
    dec = decision_de(ds, origen)
    if dec is not None:
        desde = aplicar_reparto(ds, dec, "entidad_participaciones", "entidad_id", eid, None)
        if fecha_inicio and str(desde) < str(fecha_inicio):
            ds.ledger.append({"regla": "D-S20-V", "origen": origen, "vigente_desde": desde,
                              "fecha_inicio": str(fecha_inicio), "justificacion": dec.get("justificacion")})
            if not dec.get("justificacion"):
                    ds.preguntas.append({"id": "Q-S20-7-VIGENCIA", "origen": origen, "vigente_desde": desde,
                                     "fecha_inicio": str(fecha_inicio)})
        return
    if (co, cl) not in PARTICIPACION_FIN_SELF:
        ds.ledger.append({"regla": "D8-H", "origen": origen})
        return
    desde = PARTICIPACION_FIN_SELF[(co, cl)]
    if desde is None:
        if PARTICIPACION_FIN_VIGENCIA_ESTADO != "CONFIRMADA" and not ds.modo_lab:
            raise ErrorP5("S20_VIGENCIA_PARTICIPACION_FIN", origen)
        if not fecha_inicio:
            raise ErrorP5("S6_VIGENCIA_SIN_FECHA_INICIO", origen)
        desde = str(fecha_inicio)
        if PARTICIPACION_FIN_VIGENCIA_ESTADO != "CONFIRMADA":
            ds.pendientes.append({"S20": "VIGENCIA_PARTICIPACION_FIN", "origen": origen, "propuesta": desde})
    pid = fu.uuid_v3(co, cl, "entidad_participaciones", "self")
    ds.add("entidad_participaciones", {"id": pid, "entidad_id": eid, "actor_id": ds.self_id,
                                       "porcentaje": Decimal(100), "vigente_desde": desde, "vigente_hasta": None})
    ds.mapear(co, cl, "entidad_participaciones", pid, "self", tipo="DIVIDIDO",
              notas="participacion decidida por el propietario (S20-9)")
    ds.ledger.append({"regla": "D8-H2", "origen": origen, "vigente_desde": desde})


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
        if cp in FINANCIADOR_NO_DEMOSTRADO:
            fin_actor = None
            ds.ledger.append({"regla": "D8-C2", "origen": origen})
            fdec = contraparte_decidida(ds, origen, "financiadores")
            if fdec is not None:
                fin_actor = _actor_decidido(ds, fdec["persona"])
                ftid = fu.uuid_v3(CONT_DECISIONES, f"persona/{fdec['persona']}", "terceros", "tercero")
                rid = fu.uuid_v3(CONT_DECISIONES, f"financiador/{fdec['id']}", "tercero_roles", "FINANCIADOR")
                ds.add("tercero_roles", {"id": rid, "tercero_id": ftid, "rol_codigo": "FINANCIADOR"},
                       natural=(ftid, "FINANCIADOR"))
                ds.mapear(CONT_DECISIONES, f"financiador/{fdec['id']}", "tercero_roles", rid, "rol.FINANCIADOR",
                          confianza="VALIDADA")
                ds.ledger.append({"regla": "D8-C3", "origen": origen, "decision": fdec["id"]})
            else:
                ds.preguntas.append({"id": "Q-S20-8-FINANCIADOR", "origen": origen,
                                     "nota": "proveedor V3 (banco) no es el prestamista declarado; financiador NULL"})
        else:
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
        for r in ("D8-A2" if estado_tipo == "DECIDIDO_S20" else "D8-A", "D8-C", "D8-D", "D8-E", "D8-I"):
            ds.ledger.append({"regla": r, "origen": origen})
        participaciones_financiacion(ds, cont, cp, eid, g("fecha_inicio"))

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
        decidida = kg in COMPRA_FINANCIADA_DECIDIDA
        if (str(gg.get("tipo_id")) not in tipos_fin and not decidida) or _val(cg, "prestamo_id", gg, ctx):
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
        abierta = None
        cancelada = kg in COMPRA_FINANCIADA_CANCELADA
        if cancelada and not (g("activo") is False and g("cuotas_restantes") not in (None, 0)):
            raise ErrorP5("S9_CANCELACION_INCOHERENTE", origen)
        if decidida and not cancelada and g("cuotas_restantes") not in (None, 0):
            rest = int(g("cuotas_restantes"))
            pend = Decimal(str(pend_c)) if pend_c is not None else None
            if pend is None or pend != Decimal(str(cuota)) * rest or rest + int(g("cuotas_pagadas") or 0) != int(n) \
                    or g("activo") is not True:
                ds.pendientes.append({"S20": "D8_COMPRA_FINANCIADA_ABIERTA_INCOHERENTE", "origen": origen, "bloquea_gate": True,
                                      "detalle": f"activo={g('activo')} restantes={rest} pendiente={pend_c}",
                                      "efecto": "financiacion NO creada; origen conservado"})
                continue
            abierta = pend
        elif not cancelada and not (g("cuotas_restantes") == 0 and pend_c is not None and Decimal(str(pend_c)) == 0):
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
            "saldo_principal_apertura": abierta if abierta is not None else Decimal("0"),
            "fecha_inicio_seguimiento": FECHA_INICIO_LEDGER,
            "fecha_inicio": g("fecha"), "fecha_vencimiento_final_prevista": None, "fecha_cierre_real": None,
            "estado": "ACTIVA" if abierta is not None else "CERRADA",
            "motivo_cierre": None if abierta is not None else ("CANCELADA" if cancelada else "LIQUIDADA"), "notas": None})
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
        for r in ("D8-K", "D8-L", "D8-D") + (("D8-K2",) if decidida else ()) + (("D8-K3",) if abierta is not None else ()) + (("D8-K4",) if cancelada else ()):
            ds.ledger.append({"regla": r, "origen": origen})
        participaciones_financiacion(ds, cg, kg, eid, g("fecha"))
        if kg in TOTAL_COMPRA_VALIDADO:
            ds.ledger.append({"regla": "D8-M", "origen": origen})


# ------------------------------------------------------------ dominio 8B (derechos/obligaciones)
# Catalogo cerrado (Migration V3 §16, §28, §29). genera: fila V3 que crea la posicion (o None);
# evidencia: cobros V3 que la reducen. modo: TRANSITORIA (liquidada antes del corte), ABIERTA
# (saldo = importe documentado sin cobro), LIQUIDADA_SIN_PRINCIPAL, INDETERMINADA.
_G, _GC, _I = "public.gastos", "public.gastos_cotidianos", "public.ingresos"
DERECHOS_V3 = [
    {"id": "DER-SHEIN", "genera": (_G, "gasto-g62il0"), "evidencia": [], "modo": "ABIERTA"},
    {"id": "DER-CANELA", "genera": (_G, "gasto-av2dby"), "evidencia": [(_I, "INGRESO-FZEQZV")], "modo": "TRANSITORIA"},
    {"id": "DER-ANA", "genera": (_GC, "GASTO_COTIDIANO-WL4DM4"), "evidencia": [(_I, "INGRESO-BI42IG")], "modo": "TRANSITORIA"},
    {"id": "DER-LUZ-03", "genera": (_G, "gasto-yh7fy4"), "evidencia": [(_I, "INGRESO-YC1PTU")], "modo": "TRANSITORIA"},
    {"id": "DER-LUZ-04", "genera": (_G, "gasto-uh4oum"), "evidencia": [(_I, "INGRESO-XC60RI")], "modo": "TRANSITORIA"},
    {"id": "DER-LUZ-05", "genera": (_G, "gasto-n5rj3l"), "evidencia": [(_I, "INGRESO-RLAOQR")], "modo": "TRANSITORIA"},
    {"id": "DER-LUZ-06", "genera": (_G, "gasto-302hrq"), "evidencia": [(_I, "INGRESO-8EACUL")], "modo": "TRANSITORIA"},
    {"id": "DER-LUZ-07", "genera": (_G, "gasto-yu6yhd"), "evidencia": [(_I, "INGRESO-K1KVM4")], "modo": "TRANSITORIA"},
    {"id": "DER-UNIV", "genera": None, "evidencia": [(_I, "INGRESO-MUJB1F"), (_I, "INGRESO-1THX4C"),
                                                      (_I, "INGRESO-TJ433N")], "modo": "LIQUIDADA_SIN_PRINCIPAL",
     "vinculados": [(_G, "gasto-x7jfb9"), (_G, "gasto-wzpazn")]},  # S20 R2-8
    {"id": "DER-ISA-COCHE", "genera": None, "evidencia": [(_I, "INGRESO-MX5Q04")], "modo": "INDETERMINADA"},
    {"id": "DER-ISA-ENTRADA", "genera": None, "evidencia": [(_I, "INGRESO-WPIL1Z")], "modo": "INDETERMINADA"},
]
CANON_TRANSITORIAS = (7, Decimal("330.11"))
# S20 R3-4: la luz de Allende la paga el inquilino Francisco (persona V3), validado contra el contrato.
CONTRAPARTE_V3_DECIDIDA = {f"DER-LUZ-0{n}": ("public.personas", "PER-8C62EC5126") for n in range(3, 8)}
PARTICIPACION_DERECHO_SELF = True  # S20 R2-7 (2026-09-21)
CANON_UNIVERSIDAD = Decimal("1352.00")


def _importe_v3(fuente, ctx, co, cl) -> Decimal:
    fila = fuente.get(co, {}).get(cl)
    if fila is None:
        raise ErrorP5("S8_ORIGEN_AUSENTE", f"{co}/{cl}")
    c = _celda(co, "importe", fila, ctx)
    if c.estado != fu.CONOCIDO:
        raise ErrorP5("S6_IMPORTE_DERECHO_DESCONOCIDO", f"{co}/{cl}")
    return Decimal(str(c.valor))


def _fecha_v3(fuente, ctx, co, cl):
    fila = fuente[co][cl]
    col = "fecha_inicio" if co == _I else "fecha"
    c = _celda(co, col, fila, ctx)
    return str(c.valor) if c.estado == fu.CONOCIDO else None


def contraparte_decidida(ds: Dataset, origen: str, lista: str = "contrapartes") -> dict | None:
    if ds.decisiones is None:
        return None
    its = [c for c in ds.decisiones.doc.get(lista, []) if c["origen"] == origen]
    if not its:
        return None
    if len(its) > 1:
        raise ErrorP5("S7_DECISION_DUPLICADA", origen)
    _gate_decisiones(ds, its[0]["id"])
    return its[0]


def _actor_persona_v3(ds: Dataset, co: str, ck: str) -> str:
    tid = fu.uuid_v3(co, ck, "terceros", "tercero")
    if tid not in ds.filas["terceros"]:
        raise ErrorP5("S8_HUERFANO", f"{co}/{ck}")
    aid = fu.uuid_v3(co, ck, "actores_financieros", "actor")
    ds.add("actores_financieros", {"id": aid, "owner_user_id": ds.owner, "tercero_id": tid}, natural=(ds.owner, tid))
    ds.mapear(co, ck, "actores_financieros", aid, "actor", tipo="DIVIDIDO")
    return aid


def _validar_inquilino(fuente, ctx, co, cl, persona, did) -> None:
    viv = fuente[co][cl].get("referencia_vivienda_id")
    contratos = {k for k, c in fuente.get("public.contratos", {}).items() if str(c.get("patrimonio_id")) == str(viv)}
    ok = any(str(p.get("persona_id")) == persona and str(p.get("contrato_id")) in contratos
             and str(p.get("rol")).lower() == "inquilino"
             for p in fuente.get("public.contratos_participantes", {}).values())
    if not ok:
        raise ErrorP5("S1_CONTRAPARTE_NO_INQUILINO", f"{did}: {persona} no es inquilino de {viv}")


def dominio_8b_derechos(ds: Dataset, fuente: dict, ctx: dict) -> None:
    trans_n, trans_total = 0, Decimal(0)
    for d in DERECHOS_V3:
        origenes = ([d["genera"]] if d["genera"] else []) + d["evidencia"]
        co, cl = origenes[0]
        if cl not in fuente.get(co, {}):
            raise ErrorP5("S8_ORIGEN_AUSENTE", f"{co}/{cl} ({d['id']})")
        eid = fu.uuid_v3(co, cl, "entidades", "derecho")
        fila_g = fuente[co][cl]
        nombre = _texto(_celda(co, "concepto" if co == _I else ("observaciones" if co == _GC else "nombre"), fila_g, ctx))
        cobros = [(_importe_v3(fuente, ctx, eo, ec), _fecha_v3(fuente, ctx, eo, ec)) for eo, ec in d["evidencia"]]
        modo = d["modo"]
        sub = {"entidad_id": eid, "tipo": "DERECHO_COBRO", "contraparte_actor_id": None, "moneda": "EUR",
               "importe_original_documentado": None, "saldo_apertura": None, "fecha_inicio_seguimiento": None,
               "fecha_vencimiento_final": None, "estado": "ACTIVA", "motivo_cierre": None, "fecha_cierre": None,
               "notas": None}
        if modo == "ABIERTA":
            if cobros:
                raise ErrorP5("S9_DERECHO_ABIERTO_CON_COBRO", d["id"])
            imp = _importe_v3(fuente, ctx, co, cl)
            sub.update(importe_original_documentado=imp, saldo_apertura=imp, fecha_inicio_seguimiento=FECHA_INICIO_LEDGER)
        elif modo == "TRANSITORIA":
            if len(cobros) != 1 or cobros[0][1] is None or cobros[0][1] >= FECHA_INICIO_LEDGER:
                raise ErrorP5("S9_TRANSITORIA_NO_LIQUIDADA_AL_CORTE", d["id"])
            if co != _GC and _importe_v3(fuente, ctx, co, cl) != cobros[0][0]:
                raise ErrorP5("S9_TRANSITORIA_IMPORTE_DISTINTO", d["id"])
            trans_n, trans_total = trans_n + 1, trans_total + cobros[0][0]
            sub.update(importe_original_documentado=cobros[0][0], saldo_apertura=Decimal("0"),
                       fecha_inicio_seguimiento=FECHA_INICIO_LEDGER, estado="CERRADA", motivo_cierre="LIQUIDADA")
        elif modo == "LIQUIDADA_SIN_PRINCIPAL":
            if sum(c[0] for c in cobros) != CANON_UNIVERSIDAD or any(c[1] is None or c[1] >= FECHA_INICIO_LEDGER for c in cobros):
                raise ErrorP5("S9_UNIVERSIDAD_NO_CUADRA", d["id"])
            sub.update(saldo_apertura=Decimal("0"), fecha_inicio_seguimiento=FECHA_INICIO_LEDGER,
                       estado="CERRADA", motivo_cierre="LIQUIDADA")
        elif modo != "INDETERMINADA":
            raise ErrorP5("S4_MODO_DERECHO", d["id"])
        dec = contraparte_decidida(ds, f"{co}/{cl}")
        if d["id"] in CONTRAPARTE_V3_DECIDIDA:
            po, pk = CONTRAPARTE_V3_DECIDIDA[d["id"]]
            _validar_inquilino(fuente, ctx, co, cl, pk, d["id"])
            sub["contraparte_actor_id"] = _actor_persona_v3(ds, po, pk)
            ds.ledger.append({"regla": "D8B-H", "origen": f"{co}/{cl}", "derecho": d["id"]})
        elif dec is not None:
            sub["contraparte_actor_id"] = _actor_decidido(ds, dec["persona"])
            ds.mapear(CONT_DECISIONES, f"contraparte/{dec['id']}", "derechos_obligaciones_financieras", eid,
                      "contraparte", tipo="VINCULADO", confianza="VALIDADA")
        else:
            # S20 R2-6: sin fila V3 que la identifique, la contraparte queda desconocida (NULL).
            ds.ledger.append({"regla": "D8B-C", "origen": f"{co}/{cl}", "derecho": d["id"]})
        ds.add("entidades", {"id": eid, "owner_user_id": ds.owner, "tipo_entidad": "DERECHO_OBLIGACION",
                             "nombre": nombre})
        ds.add("derechos_obligaciones_financieras", sub)
        tipo_map = "DIVIDIDO" if d["genera"] else "FUSIONADO"
        ds.mapear(co, cl, "entidades", eid, "derecho", tipo=tipo_map)
        ds.mapear(co, cl, "derechos_obligaciones_financieras", eid, "derecho", tipo=tipo_map)
        for eo, ec in origenes[1:]:
            ds.mapear(eo, ec, "derechos_obligaciones_financieras", eid, "derecho.evidencia",
                      tipo="VINCULADO" if d["genera"] else "FUSIONADO")
        for vo, vc in d.get("vinculados", []):
            if vc not in fuente.get(vo, {}):
                raise ErrorP5("S8_ORIGEN_AUSENTE", f"{vo}/{vc} ({d['id']})")
            ds.mapear(vo, vc, "derechos_obligaciones_financieras", eid, "derecho.vinculado", tipo="VINCULADO")
            ds.ledger.append({"regla": "D8B-G", "origen": f"{vo}/{vc}", "derecho": d["id"]})
        # participacion (S20 R2-7)
        rdec = decision_de(ds, f"{co}/{cl}")
        if rdec is not None:
            aplicar_reparto(ds, rdec, "entidad_participaciones", "entidad_id", eid, None)
        elif PARTICIPACION_DERECHO_SELF:
            fechas = [_fecha_v3(fuente, ctx, xo, xc) for xo, xc in origenes]
            desde = fechas[0] if d["genera"] else min((f for f in fechas if f), default=None)
            if not desde:
                raise ErrorP5("S6_VIGENCIA_DERECHO_SIN_FECHA", d["id"])
            pid = fu.uuid_v3(co, cl, "entidad_participaciones", "self")
            ds.add("entidad_participaciones", {"id": pid, "entidad_id": eid, "actor_id": ds.self_id,
                                               "porcentaje": Decimal(100), "vigente_desde": desde, "vigente_hasta": None})
            ds.mapear(co, cl, "entidad_participaciones", pid, "self", tipo="DIVIDIDO",
                      notas="participacion decidida por el propietario (S20 R2-7)")
            ds.ledger.append({"regla": "D8B-F", "origen": f"{co}/{cl}", "vigente_desde": desde})
        regla = {"ABIERTA": "D8B-A", "TRANSITORIA": "D8B-B", "LIQUIDADA_SIN_PRINCIPAL": "D8B-D",
                 "INDETERMINADA": "D8B-D"}[modo]
        for r in ("D8B-A", regla, "D8B-E") if regla != "D8B-A" else ("D8B-A", "D8B-E"):
            ds.ledger.append({"regla": r, "origen": f"{co}/{cl}", "derecho": d["id"]})
    if (trans_n, trans_total) != CANON_TRANSITORIAS:
        raise ErrorP5("S9_TRANSITORIAS_CANON", f"{trans_n} / {trans_total}")


# ------------------------------------------------------------ dominio 9 (inversiones)
# tipo_producto sin dato V3 (PROPUESTA pendiente del propietario, D9-F).
# S20 R3-1 (2026-09-21): todas FONDO salvo el edificio, que es un joint venture (sin valor
# propio en el CHECK de 0330 -> OTRO, con la declaracion del propietario en notas; D9-H).
TIPO_PRODUCTO_PROPUESTO = {
    "INV-26577BEDE3": "FONDO", "INV-2F7A749023": "OTRO", "INV-35B5375831": "FONDO",
    "INV-59D23434E8": "FONDO", "INV-DE397BD29C": "FONDO", "INV-E30D554524": "FONDO", "INV-E674104368": "FONDO",
}
TIPO_PRODUCTO_ESTADO = "CONFIRMADA"
NOTA_TIPO_PRODUCTO = {"INV-2F7A749023": "Tipo declarado por el propietario: JOINT VENTURE (S20 R3-1)."}
PARTICIPACION_INVERSION_SELF = True  # S20 R3-2: 100 % propietario desde fecha_inicio V3
_OBJ = {"aporte_estimado": "aporte_objetivo_total", "retorno_esperado_total": "valor_objetivo_total",
        "roi_esperado_pct": "roi_objetivo_pct", "irr_esperada_pct": "irr_objetivo_pct",
        "moic_esperado": "moic_objetivo", "plazo_esperado_meses": "plazo_objetivo_meses",
        "fecha_objetivo_salida": "fecha_objetivo_salida"}


def dominio_9_inversiones(ds: Dataset, fuente: dict, ctx: dict) -> None:
    cont = "public.inversion"
    for ci, iv in sorted(fuente.get(cont, {}).items()):
        origen = f"{cont}/{ci}"
        if (cont, ci) in CUENTAS_DERIVADAS:
            ds.ledger.append({"regla": "D9-A", "origen": origen, "destino": "cuentas (dominio 3)"})
            continue
        g = lambda col: _celda(cont, col, iv, ctx)
        v = lambda col: g(col).valor if g(col).estado == fu.CONOCIDO else None
        if ci not in TIPO_PRODUCTO_PROPUESTO:
            raise ErrorP5("S4_INVERSION_SIN_TIPO", origen)
        if TIPO_PRODUCTO_ESTADO != "CONFIRMADA":
            if not ds.modo_lab:
                raise ErrorP5("S20_TIPO_PRODUCTO", origen)
            ds.pendientes.append({"S20": "TIPO_PRODUCTO", "origen": origen, "propuesta": TIPO_PRODUCTO_PROPUESTO[ci]})
        prov, dealer = v("proveedor_id"), v("dealer_id")
        if prov and dealer and prov != dealer:
            raise ErrorP5("S20_GESTOR_INVERSION", f"{origen} proveedor != dealer")
        gestor = prov or dealer
        tgid = fu.uuid_v3("public.proveedores", str(gestor), "terceros", "tercero") if gestor else None
        if tgid and tgid not in ds.filas["terceros"]:
            raise ErrorP5("S8_HUERFANO", f"{origen} proveedor_id")
        estado = v("estado")
        if estado not in ("ACTIVA", "CERRADA"):
            raise ErrorP5("S4_ESTADO_INVERSION", f"{origen} estado={estado}")
        mon = v("moneda")
        if not mon:
            raise ErrorP5("S6_MONEDA_NO_DEMOSTRADA", origen)
        eid = fu.uuid_v3(cont, ci, "entidades", "inversion")
        ds.add("entidades", {"id": eid, "owner_user_id": ds.owner, "tipo_entidad": "INVERSION",
                             "nombre": _texto(g("nombre"))})
        ds.mapear(cont, ci, "entidades", eid, "inversion", tipo="DIVIDIDO")
        plazo = v("plazo_final_meses") if estado == "CERRADA" else None
        ds.add("inversiones", {
            "entidad_id": eid, "inversion_padre_entidad_id": None, "rol_estructura": "POSICION",
            "tipo_producto": TIPO_PRODUCTO_PROPUESTO[ci], "tercero_gestor_id": tgid, "moneda": mon,
            "fecha_inicio": v("fecha_inicio"), "fecha_fin_real": v("fecha_cierre_real"),
            "plazo_real_meses": int(Decimal(str(plazo))) if plazo is not None else None,
            "capital_invertido_apertura": None, "fecha_capital_invertido_apertura": None,
            "estado": estado, "motivo_cierre": None,
            "notas": " ".join(x for x in (_texto(g("descripcion")) if g("descripcion").estado == fu.CONOCIDO else None,
                                          NOTA_TIPO_PRODUCTO.get(ci)) if x) or None})
        ds.mapear(cont, ci, "inversiones", eid, "inversion", tipo="DIVIDIDO")
        if PARTICIPACION_INVERSION_SELF:
            if not v("fecha_inicio"):
                raise ErrorP5("S6_VIGENCIA_INVERSION_SIN_FECHA", origen)
            pid = fu.uuid_v3(cont, ci, "entidad_participaciones", "self")
            ds.add("entidad_participaciones", {"id": pid, "entidad_id": eid, "actor_id": ds.self_id,
                                               "porcentaje": Decimal(100), "vigente_desde": str(v("fecha_inicio")),
                                               "vigente_hasta": None})
            ds.mapear(cont, ci, "entidad_participaciones", pid, "self", tipo="DIVIDIDO",
                      notas="participacion decidida por el propietario (S20 R3-2)")
        obj = {}
        for col, dest in _OBJ.items():
            x = v(col)
            if x is not None:
                obj[dest] = str(x) if dest == "fecha_objetivo_salida" else (
                    int(Decimal(str(x))) if dest == "plazo_objetivo_meses" else Decimal(str(x)))
        if obj:
            oid = fu.uuid_v3(cont, ci, "inversion_objetivos_versiones", "v1")
            fila = {"id": oid, "inversion_entidad_id": eid, "vigente_desde": None, "vigente_hasta": None,
                    "aporte_objetivo_total": None, "valor_objetivo_total": None, "roi_objetivo_pct": None,
                    "moic_objetivo": None, "irr_objetivo_pct": None, "plazo_objetivo_meses": None,
                    "fecha_objetivo_salida": None, "notas": None}
            fila.update(obj)
            ds.add("inversion_objetivos_versiones", fila)
            ds.mapear(cont, ci, "inversion_objetivos_versiones", oid, "objetivo_v1", tipo="DIVIDIDO")
            a, r, roi = obj.get("aporte_objetivo_total"), obj.get("valor_objetivo_total"), obj.get("roi_objetivo_pct")
            if a and r is not None and roi is not None and \
                    abs(((r / a - 1) * 100).quantize(Decimal("0.01")) - roi) > Decimal("0.01"):
                raise ErrorP5("S9_ROI_OBJETIVO_INCOHERENTE", origen)
        reglas = ["D9-A", "D9-B", "D9-C", "D9-D", "D9-F", "D9-G"] + (["D9-E"] if estado == "CERRADA" else [])
        for r_ in reglas:
            ds.ledger.append({"regla": r_, "origen": origen})


# ------------------------------------------------------------ dominio 10 (contratos y valoraciones)
TIPO_CONTRATO_V3 = {"completa": "ALQUILER_VIVIENDA", "vivienda_trastero": "ALQUILER_VIVIENDA", "garaje": "OTRO"}
ESTADO_CONTRATO_V3 = {"activo": "FORMALIZADO"}
FECHA_INICIO_CONTRATO_VALIDADA = {
    "CON-FRANCISCO-20250301": "2026-03-01",  # Migration V3 §9/§27
    "CON-9F3136AA14": "2026-03-01",          # S20 R4-1: vivienda y garaje alquilados por separado
}
# S20 R4-2: fila de participante creada e inactivada por error de captura (misma persona y rol):
# una sola vigencia; su origen se FUSIONA en la fila superviviente.
PARTICIPANTE_DUPLICADO_CAPTURA = {"CPR-MARIA-AVA": "CPR-312ACF7718"}
# S20 R4-3: la fianza la conserva el propietario y es obligacion de devolver (salvo desperfectos).
FIANZA_COMO_OBLIGACION = True
# S20 R4-4 / R3-4: luz de la vivienda del contrato, repercutible 100 % al inquilino que la paga.
SERVICIOS_REPERCUTIDOS = {
    "CON-MARINA-240901": [{"clave": "luz", "tipo_servicio": "SUMINISTRO_ELECTRICO",
                           "actor": ("public.personas", "PER-8C62EC5126"), "porcentaje": Decimal(100)}],
}
ROL_PARTICIPANTE_V3 = {"inquilino": "INQUILINO", "avalista": "AVALISTA", "gestor": "GESTOR"}


def _dia(ts: str, delta: int = 0) -> str:
    from datetime import date, timedelta
    return (date.fromisoformat(str(ts)[:10]) + timedelta(days=delta)).isoformat()


def dominio_10_contratos(ds: Dataset, fuente: dict, ctx: dict) -> None:
    cc, cpt = "public.contratos", "public.contratos_participantes"
    persona_propia = {m["registro_origen_id"] for m in ds.filas["mapeos_importacion"].values()
                      if m["tabla_destino"] == "usuarios" and m["tipo_mapping"] == "VINCULADO"}
    for ck, c in sorted(fuente.get(cc, {}).items()):
        g = lambda col: _celda(cc, col, c, ctx)
        v = lambda col: g(col).valor if g(col).estado == fu.CONOCIDO else None
        origen = f"{cc}/{ck}"
        pid = fu.uuid_v3("public.patrimonio", str(v("patrimonio_id")), "entidades", "propiedad")
        if pid not in ds.filas["propiedades"]:
            raise ErrorP5("S8_HUERFANO", f"{origen} patrimonio_id")
        tipo = TIPO_CONTRATO_V3.get(str(v("objeto_alquiler")))
        est = ESTADO_CONTRATO_V3.get(str(v("estado")))
        if tipo is None or est is None:
            raise ErrorP5("S4_CONTRATO_SIN_MAPPING", f"{origen} objeto={v('objeto_alquiler')} estado={v('estado')}")
        inicio = FECHA_INICIO_CONTRATO_VALIDADA.get(ck, v("fecha_inicio"))
        eid = fu.uuid_v3(cc, ck, "entidades", "contrato")
        ds.add("entidades", {"id": eid, "owner_user_id": ds.owner, "tipo_entidad": "CONTRATO", "nombre": ck})
        ds.mapear(cc, ck, "entidades", eid, "contrato", tipo="DIVIDIDO")
        ds.add("contratos", {"entidad_id": eid, "propiedad_entidad_id": pid, "tipo_contrato": tipo,
                             "fecha_inicio": inicio, "fecha_fin_prevista": v("fecha_fin"), "fecha_fin_real": None,
                             "estado_documental": est, "regla_renta_id": None,
                             "notas": _texto(g("observaciones")) if g("observaciones").estado == fu.CONOCIDO else None})
        ds.mapear(cc, ck, "contratos", eid, "contrato", tipo="DIVIDIDO",
                  notas="fecha_inicio corregida y validada (D10-B)" if ck in FECHA_INICIO_CONTRATO_VALIDADA else None)
        for r in ("D10-A", "D10-C", "D10-F", "D10-I") + (("D10-B",) if ck in FECHA_INICIO_CONTRATO_VALIDADA else ()):
            ds.ledger.append({"regla": r, "origen": origen})
        ipc = v("incremento_ipc")
        if ipc is not None:
            rid = fu.uuid_v3(cc, ck, "contrato_revision_renta_versiones", "v1")
            ds.add("contrato_revision_renta_versiones", {
                "id": rid, "contrato_entidad_id": eid, "vigente_desde": inicio, "vigente_hasta": None,
                "tipo_revision": "IPC" if ipc else "NINGUNA", "indice_referencia": None, "periodicidad_meses": None,
                "fecha_primera_revision": None, "porcentaje_fijo": None, "notas": None})
            ds.mapear(cc, ck, "contrato_revision_renta_versiones", rid, "revision_v1", tipo="DIVIDIDO")
            ds.ledger.append({"regla": "D10-E", "origen": origen})
        parts = {k: p for k, p in fuente.get(cpt, {}).items() if str(p.get("contrato_id")) == ck}
        for dup, sup in PARTICIPANTE_DUPLICADO_CAPTURA.items():
            if dup in parts:
                if sup not in parts or (str(parts[sup].get("persona_id")), str(parts[sup].get("rol"))) != \
                        (str(parts[dup].get("persona_id")), str(parts[dup].get("rol"))):
                    raise ErrorP5("S1_DUPLICADO_CAPTURA_INCOHERENTE", f"{cpt}/{dup}")
                parts = {k: p for k, p in parts.items() if k != dup}
                ds.mapear(cpt, dup, "contrato_participantes", fu.uuid_v3(cpt, sup, "contrato_participantes", "participante"),
                          "participante", tipo="FUSIONADO", confianza="VALIDADA",
                          notas="fila duplicada por error de captura (S20 R4-2)")
                ds.ledger.append({"regla": "D10-J", "origen": f"{cpt}/{dup}", "superviviente": sup})
        inact = {}
        for k, p in parts.items():
            ic = _celda(cpt, "inactivatedon", p, ctx)
            if ic.estado == fu.CONOCIDO:
                inact[(str(p.get("persona_id")), str(p.get("rol")))] = str(ic.valor)
        for k, p in sorted(parts.items()):
            per, rolv = str(p.get("persona_id")), str(p.get("rol"))
            rol = ROL_PARTICIPANTE_V3.get(rolv.lower())
            if rol is None:
                raise ErrorP5("S4_ROL_PARTICIPANTE", f"{cpt}/{k} rol={rolv}")
            if fu.uuid_origen("public.personas", per) in persona_propia:
                actor = ds.self_id
            else:
                actor = _actor_persona_v3(ds, "public.personas", per)
            ic = _celda(cpt, "inactivatedon", p, ctx)
            desde, hasta = inicio, None
            if ic.estado == fu.CONOCIDO:
                hasta = _dia(ic.valor, -1)
            elif (per, rolv) in inact:
                desde = max(inicio, _dia(inact[(per, rolv)]))
            if hasta is not None and hasta < desde:
                raise ErrorP5("S9_VIGENCIA_PARTICIPANTE", f"{cpt}/{k}")
            prid = fu.uuid_v3(cpt, k, "contrato_participantes", "participante")
            es_p = _celda(cpt, "es_principal", p, ctx)
            ds.add("contrato_participantes", {"id": prid, "contrato_entidad_id": eid, "actor_id": actor, "rol": rol,
                                              "principal": bool(es_p.valor) if es_p.estado == fu.CONOCIDO else False,
                                              "vigente_desde": desde, "vigente_hasta": hasta})
            ds.mapear(cpt, k, "contrato_participantes", prid, "participante")
            ds.ledger.append({"regla": "D10-D", "origen": f"{cpt}/{k}"})
        principales = [(str(p.get("persona_id"))) for p in parts.values()
                       if str(p.get("rol")).lower() == "inquilino" and _celda(cpt, "es_principal", p, ctx).valor is True]
        fz = v("fianza")
        if FIANZA_COMO_OBLIGACION and fz is not None and Decimal(str(fz)) > 0:
            if len(principales) != 1:
                raise ErrorP5("S20_CONTRAPARTE_FIANZA", f"{origen} inquilinos principales={len(principales)}")
            oid = fu.uuid_v3(cc, ck, "entidades", "fianza")
            ds.add("entidades", {"id": oid, "owner_user_id": ds.owner, "tipo_entidad": "DERECHO_OBLIGACION",
                                 "nombre": f"FIANZA {ck}"})
            ds.add("derechos_obligaciones_financieras", {
                "entidad_id": oid, "tipo": "OBLIGACION_PAGO",
                "contraparte_actor_id": _actor_persona_v3(ds, "public.personas", principales[0]), "moneda": "EUR",
                "importe_original_documentado": Decimal(str(fz)), "saldo_apertura": Decimal(str(fz)),
                "fecha_inicio_seguimiento": FECHA_INICIO_LEDGER, "fecha_vencimiento_final": None, "estado": "ACTIVA",
                "motivo_cierre": None, "fecha_cierre": None, "notas": None})
            ds.mapear(cc, ck, "entidades", oid, "fianza", tipo="DIVIDIDO")
            ds.mapear(cc, ck, "derechos_obligaciones_financieras", oid, "fianza", tipo="DIVIDIDO")
            fpid = fu.uuid_v3(cc, ck, "entidad_participaciones", "fianza.self")
            ds.add("entidad_participaciones", {"id": fpid, "entidad_id": oid, "actor_id": ds.self_id,
                                               "porcentaje": Decimal(100), "vigente_desde": inicio, "vigente_hasta": None})
            ds.mapear(cc, ck, "entidad_participaciones", fpid, "fianza.self", tipo="DIVIDIDO")
        for srv in SERVICIOS_REPERCUTIDOS.get(ck, []):
            ao, ak = srv["actor"]
            if not any(str(p.get("persona_id")) == ak and str(p.get("rol")).lower() == "inquilino" for p in parts.values()):
                raise ErrorP5("S1_REPERCUSION_NO_INQUILINO", f"{origen} {ak}")
            sid = fu.uuid_v3(cc, ck, "entidades", f"servicio.{srv['clave']}")
            ds.add("entidades", {"id": sid, "owner_user_id": ds.owner, "tipo_entidad": "SERVICIO",
                                 "nombre": f"{srv['tipo_servicio']} {ck}"})
            ds.add("servicios", {"entidad_id": sid, "tipo_servicio": srv["tipo_servicio"], "categoria_default_id": None,
                                 "fecha_inicio": None, "fecha_fin_real": None, "notas": None})
            csid = fu.uuid_v3(cc, ck, "contrato_servicios", srv["clave"])
            ds.add("contrato_servicios", {"id": csid, "contrato_entidad_id": eid, "servicio_entidad_id": sid,
                                          "incluido_en_renta": False, "repercutible": True,
                                          "actor_repercusion_id": _actor_persona_v3(ds, ao, ak),
                                          "porcentaje_repercutible": srv["porcentaje"],
                                          "vigente_desde": inicio, "vigente_hasta": None})
            for t_, i_ in (("entidades", sid), ("servicios", sid), ("contrato_servicios", csid)):
                ds.mapear(cc, ck, t_, i_, f"servicio.{srv['clave']}", tipo="DIVIDIDO", confianza="VALIDADA",
                          notas="servicio repercutible decidido por el propietario (S20 R4-4)")
            ds.ledger.append({"regla": "D10-K", "origen": origen})
    ds.ledger.append({"regla": "D10-G", "origen": "contextos"})

    cv = "public.patrimonio_compra"
    for vk, pc in sorted(fuente.get(cv, {}).items()):
        g = lambda col: _celda(cv, col, pc, ctx)
        dv = lambda col: Decimal(str(g(col).valor)) if g(col).estado == fu.CONOCIDO else None
        origen = f"{cv}/{vk}"
        pid = fu.uuid_v3("public.patrimonio", str(pc.get("patrimonio_id")), "entidades", "propiedad")
        prop = ds.filas["propiedades"].get(pid)
        if prop is None:
            raise ErrorP5("S8_HUERFANO", f"{origen} patrimonio_id")
        comps = [dv(x) for x in ("valor_compra", "impuestos_eur", "notaria", "agencia", "reforma_adecuamiento")]
        if dv("total_inversion") is not None and sum(x for x in comps if x is not None) != dv("total_inversion"):
            raise ErrorP5("S9_TOTAL_INVERSION_NO_CUADRA", origen)
        fcomp = _celda(cv, "fecha_compra", pc, ctx)
        for col, metodo, fecha in (
                ("valor_compra", "COMPRA", str(fcomp.valor) if fcomp.estado == fu.CONOCIDO else prop["fecha_adquisicion"]),
                ("valor_mercado", "MERCADO", str(g("valor_mercado_fecha").valor) if g("valor_mercado_fecha").estado == fu.CONOCIDO else None),
                ("valor_referencia", "FISCAL_REFERENCIA", None)):
            val = dv(col)
            if val is None:
                continue
            if val <= 0:
                raise ErrorP5("S5_VALORACION_NO_POSITIVA", f"{origen} {col}")
            vid = fu.uuid_v3(cv, vk, "propiedad_valoraciones", metodo)
            ds.add("propiedad_valoraciones", {"id": vid, "propiedad_entidad_id": pid, "fecha_valoracion": fecha,
                                              "valor_total": val, "moneda": "EUR", "metodo": metodo,
                                              "fuente": f"V3 {cv}.{col}", "notas": None})
            ds.mapear(cv, vk, "propiedad_valoraciones", vid, f"valoracion.{metodo}", tipo="DIVIDIDO")
        ds.ledger.append({"regla": "D10-H", "origen": origen})



# ------------------------------------------------------------ dominio 5 reglas financieras
# Contrato fisico 0330: 0030 (tablas), 0080 (UNIQUE excepciones), 0090 (FK inmediatas), 0100 (EXCLUDE
# vigencias []), 0265 (anclaje D-126), 0270 (A8 VENTANA). Semantica: DB Schema §29-§31, Migration V3
# §4/§14/§16/F03-02 D-126, F04-D015/D016/D020. Mandato RV3-E001-R2 continuacion P5 dominio 5.
TIPOS_HECHO_SEED = {  # 0150_f03_01_seed_tipos_hecho.sql (UUID fijos; codigo = identidad semantica)
    "GASTO": "b9c7573f-fa72-54a1-8b2d-b1c189f32533",
    "INGRESO": "bfdad2e0-2d2e-5850-b73a-1d2ecd8eb4c4",
    "TRANSFERENCIA": "7ba5c0c4-ccd9-557c-838a-9122e96634d6",
    "COMPRA_FINANCIADA": "7c20e19e-8c62-5df7-b11b-17d15eb4c76c",
    "REEMBOLSO": "a4153b30-58b5-50d4-9073-471ea1d6c294",
    "APORTACION_INVERSION": "cf006530-280c-587b-994f-e621e680e3ef",
    "GENERACION_DERECHO_OBLIGACION": "26ee751e-aa9c-5c3b-a81c-7a28e5a5be34",
}
FLUJO_POR_TIPO = {"GASTO": "SALIDA", "INGRESO": "ENTRADA", "TRANSFERENCIA": "TRANSFERENCIA",
                  "APORTACION_INVERSION": "SALIDA", "REEMBOLSO": "ENTRADA", "GENERACION_DERECHO_OBLIGACION": "ENTRADA"}
PERIODICIDAD_V3 = {"MENSUAL": ("MENSUAL", 1), "ANUAL": ("ANUAL", 1), "SEMESTRAL": ("MENSUAL", 6)}
CAMPO_INICIO = {"public.gastos": "fecha", "public.ingresos": "fecha_inicio"}
CAMPO_RANGO = {"public.gastos": "rango_pago", "public.ingresos": "rango_cobro"}
CAMPO_NOMBRE = {"public.gastos": "nombre", "public.ingresos": "concepto"}
CAMPO_ULTIMO = {"public.gastos": "ultimo_pago_on", "public.ingresos": "ultimo_ingreso_on"}
# G-V3-03 contenedores presupuestarios (Migration V3 §4) -> dominio 11, nunca regla.
CONTENEDORES_PRESUPUESTARIOS = {"GASTO-39E0DA", "GASTO-COGUQZ", "GASTO-THXCP3", "GASTO-THXCPY", "GASTO-XV7KBS",
                                "GASTO-YSA5YN"}
# G-V3-02 gimnasio validado como RODANTE (Migration V3 D-126); no se generaliza por nombre.
RODANTES_VALIDADOS = {("public.gastos", "GASTO-MWH8PN"), ("public.gastos", "gasto-wsd3tv")}
# Ahorro remunerado P1/P2/P3/EXTRA (Migration V3 §14): transferencia a la cuenta de ahorro derivada de
# INV-F28AEAD467 (AHORRO ACCESIBLE, propietario 2026-09-21). No se crea otra cuenta.
CUENTA_AHORRO = ("public.inversion", "INV-F28AEAD467")
TRANSFERENCIAS_AHORRO = {"GASTO-ZL0ZP3", "GASTO-ZL0ZP4", "gasto-qv6ysw", "gasto-0mvwgh", "gasto-z94414"}
# Aportacion Mediolanum N:1 (Migration V3 §16): dos filas V3 -> una regla, versiones por fila, en orden.
FUSION_MEDIOLANUM = {"regla_id": "e6f9b86e-a62e-523b-8490-99a4804df761",  # UUID canonico Migration V3 §16
                     "inversion": "INV-E30D554524", "filas": ["GASTO-UVUY73", "gasto-kdaeki"],
                     "co": "public.gastos", "tipo": "APORTACION_INVERSION"}
# Fusiones N:1 decididas por el propietario (2026-09-21, respuesta 8): mismo comportamiento esperado con
# condiciones cambiadas (G-V3-02/G-V3-04). Telefonos NO. PARO PARCIAL - 4/26 no se fusiona: se solapa.
FUSIONES_PROPIETARIO = [
    {"co": "public.gastos", "filas": ["GASTO-UX2T9J", "gasto-rhutck"]},       # IBI Saavedra 2025 -> 2026
    {"co": "public.gastos", "filas": ["GASTO-F064Y6", "gasto-knrcb0"]},       # comunidad Saavedra
    {"co": "public.ingresos", "filas": ["INGRESO-1U01KS", "INGRESO-WIU44G"]},  # paro -> paro parcial
]
# Respuesta 4 (2026-09-21): inicio confirmado por el propietario aunque fecha > createon.
INICIO_CONFIRMADO = {("public.gastos", "gasto-3qw646")}
# Respuesta 5 (2026-09-21): fin = fecha de modificacion V3 (coincide con el ultimo pago confirmado).
# Respuesta B (2026-09-21): inicio = fecha de creacion V3 en los anuales cuya `fecha` avanzo al vencimiento.
INICIO_POR_CREACION = {("public.gastos", k) for k in ("GASTO-E97DIW", "GASTO-OKZ0M0", "GASTO-RZG9Y3", "GASTO-UX2T9J",
                                                      "GASTO-VTKC38", "GASTO-WR2WFJ", "gasto-ugzxrm")}
# Respuesta C (2026-09-21): cobro parcial de un mes del paro parcial; no es regla, se dispone en dominio 6.
COBRO_PARCIAL_NO_REGLA = {("public.ingresos", "INGRESO-TXJ5II")}
FIN_POR_MODIFICACION = {("public.gastos", "GASTO-WIPJQR"), ("public.gastos", "gasto-0upxg2"),
                        ("public.gastos", "gasto-t2ndhm")}
# Prestamo coche Isa: el cobro mensual reduce DER-ISA-COCHE. Tipo de hecho en STOP S1 (mandato:
# GENERACION_DERECHO_OBLIGACION; canon F04-D015/D016 + vocabulario F04: REEMBOLSO). None = pendiente.
REGLA_DERECHO_ISA = {("public.ingresos", "INGRESO-MX5Q04"): ("public.ingresos", "INGRESO-MX5Q04")}
ISA_TIPO_HECHO_DECIDIDO: str | None = "REEMBOLSO"  # respuesta A del propietario 2026-09-21 (F04-D015)
DOMINIO_5_ACTIVO = True
# Respuesta D (2026-09-21): la cuota de prestamo no tiene regla propia; su expectativa es el calendario de la
# financiacion (financiacion_cuotas), igual que en las compras financiadas. Evita duplicar la expectativa.
CUOTA_PRESTAMO_SIN_REGLA = True  # los tests historicos lo aislan (conftest 0.3.0) para verificar su baseline
ISA_TIPOS_ADMITIDOS = {"REEMBOLSO", "GENERACION_DERECHO_OBLIGACION"}

LEDGER_REGLAS.update({
    "D5-A": "identidad: 1 fila V3 recurrente -> 1 regla (uuid v3|fila|reglas_financieras|regla) + 1 version; fusiones N:1 "
            "solo con evidencia canonica (Mediolanum §16; renta = ingreso con contrato_alquiler + renta_mensual del contrato).",
    "D5-B": "vigente_desde = fecha (gastos) / fecha_inicio (ingresos) solo si se demuestra inicio: no posterior a createon ni "
            "a ultimo_pago_on/ultimo_ingreso_on. Si no -> pendiente S6 (sin sustituto createon/primer pago). Rentas: inicio "
            "del contrato validado (D10-B).",
    "D5-C": "vigente_hasta: activo=true -> NULL; activo=false con inactivatedon -> dia anterior (criterio D10-D: el "
            "gestionable V3 deja de estar vivo, Migration V3 §4); activo=false sin inactivatedon -> pendiente S6.",
    "D5-B2": "inicio confirmado por el propietario (respuesta 4, 2026-09-21) aunque fecha > createon.",
    "D5-C2": "fin decidido por el propietario (respuesta 5, 2026-09-21): vigente_hasta = fecha de modifiedon V3 "
             "(inclusiva; coincide con el ultimo pago confirmado, no se resta dia para no excluir esa ocurrencia).",
    "D5-K2": "fusion con solape de evidencia (el sucesor empieza antes de inactivar el predecesor): hasta del "
             "predecesor = inicio del sucesor - 1 dia; literal de inactivatedon en origen. Hueco -> S9.",
    "D5-K3": "fusion N:1 decidida por el propietario (respuesta 8, 2026-09-21): IBI Saavedra 2025->2026, comunidad "
             "Saavedra, paro -> paro parcial; firma (cuentas, tercero, cadencia, moneda, categoria, entidad) identica.",
    "D5-B3": "inicio = createon V3 decidido por el propietario (respuesta B, 2026-09-21) en anuales cuya fecha V3 avanzo "
             "al siguiente vencimiento; createon no puede ser posterior al ultimo pago (S9).",
    "D5-S": "cobro parcial de un mes de otra recurrencia (respuesta C): no es regla; se dispone en dominio 6.",
    "D5-T": "cuota de prestamo sin regla propia (respuesta D): la expectativa es el calendario de la financiacion.",
    "D5-C1": "activo=true con inactivatedon conocido: dato contradictorio (clase C); prevalece activo, literal en origen.",
    "D5-D": "rango V3 'a-b' -> VENTANA dia_desde=a, dia_hasta=b (1<=a<=b<=31); RODANTE -> ANCLA y el rango queda solo en "
            "origen (D-126). Anclaje CALENDARIO salvo G-V3-02 gimnasio validado.",
    "D5-E": "periodicidad MENSUAL/ANUAL -> intervalo 1; SEMESTRAL -> MENSUAL intervalo 6 (literal de la fila).",
    "D5-F": "importe FIJO = importe V3 > 0 (con importe_cuota igual cuando existe); nunca MANUAL como sustituto.",
    "D5-G": "presupuestable: GASTO/INGRESO -> presupuestable_default de la categoria o, sin categoria, politica de ambito "
            "confirmada (GASTO si, INGRESO no); TRANSFERENCIA/APORTACION/REEMBOLSO -> false (DB Schema: solo efectos "
            "gasto/ingreso consumen presupuesto).",
    "D5-H": "tercero_id = proveedor V3 en gastos y aportacion; NULL en transferencias propias, rentas (derivable de "
            "contrato_participantes) e ingresos sin contraparte V3. entidad_origen = propiedad por referencia_vivienda_id.",
    "D5-I": "cuentas: gastos -> salida; ingresos -> entrada; moneda = moneda de la cuenta (S20-2 EUR sin cuenta).",
    "D5-J": "ahorro remunerado -> TRANSFERENCIA origen V3 -> cuenta de ahorro derivada; gasto 0; importe_referencia_lado "
            "NULL (misma moneda, DB Schema §30).",
    "D5-K": "Mediolanum N:1 -> APORTACION_INVERSION SALIDA, entidad_origen = INV-E30D554524; versiones contiguas "
            "comprobadas (hasta v1 + 1 dia = desde v2). UUID literal canonico de Migration V3 §16 (no derivable RV3).",
    "D5-L": "renta: una regla por contrato (entidad_origen = contrato, DB Schema §49) fusionando la fila ingreso V3 "
            "vinculada; importe FIJO (no hay calendario de entidad para contratos); contratos.regla_renta_id completado. "
            "RUN06 duplicaba las 3 rentas (6 reglas): divergencia DV-11.",
    "D5-M": "regla_excepciones = 0: omitido_* V3 no conserva fecha_objetivo de la ocurrencia omitida (D-MIG-015).",
    "D5-N": "excluidas: G-V3-03 -> dominio 11; compras financiadas -> dominio 8 (financiacion ya creada).",
    "D5-P": "pendientes S20 del dominio 5 bloquean solo su fila (sin destino, origen conservado) y el informe no vale "
            "para gate mientras existan.",
})


def _d(c) -> str | None:
    return str(c.valor)[:10] if c.estado == fu.CONOCIDO and c.valor is not None else None


def _rango(texto) -> tuple[int, int] | None:
    import re as _re
    m = _re.fullmatch(r"\s*(\d{1,2})\s*-\s*(\d{1,2})\s*", str(texto or ""))
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    return (a, b) if 1 <= a <= b <= 31 else None


class PendienteD5(Exception):
    def __init__(self, stop: str, codigo: str, detalle: str = ""):
        super().__init__(f"{stop} {codigo} {detalle}")
        self.stop, self.codigo, self.detalle = stop, codigo, detalle


def _pend(ds: Dataset, co: str, cl: str, p: PendienteD5) -> None:
    ds.pendientes.append({p.stop: p.codigo, "origen": f"{co}/{cl}", "detalle": p.detalle, "dominio": 5,
                          "efecto": "regla NO creada; origen conservado", "bloquea_gate": True})


def _vigencia(co: str, fila: dict, ctx: dict, desde_forzado: str | None = None) -> tuple[str, str | None, list]:
    notas = []
    g = lambda col: _celda(co, col, fila, ctx)
    clave = (co, str(fila.get("id")))
    desde = desde_forzado
    if desde is None:
        ini, cre, ult = _d(g(CAMPO_INICIO[co])), _d(g("createon")), _d(g(CAMPO_ULTIMO[co]))
        if ini is None:
            raise PendienteD5("S6", "D5_INICIO_DESCONOCIDO")
        if clave in INICIO_CONFIRMADO:
            notas.append("D5-B2")
        elif clave in INICIO_POR_CREACION:
            if cre is None or (ult is not None and cre > ult):
                raise PendienteD5("S9", "D5_INICIO_CREACION_INVALIDO", f"createon={cre} ultimo={ult}")
            ini = cre
            notas.append("D5-B3")
        elif (cre is not None and ini > cre) or (ult is not None and ini > ult):
            raise PendienteD5("S6", "D5_INICIO_NO_DEMOSTRADO", f"{CAMPO_INICIO[co]}={ini} createon={cre} ultimo={ult}")
        desde = ini
    act, ina = g("activo"), _d(g("inactivatedon"))
    if act.estado != fu.CONOCIDO:
        raise PendienteD5("S6", "D5_ACTIVO_DESCONOCIDO")
    if act.valor is True:
        if ina is not None:
            notas.append("D5-C1")
        return desde, None, notas
    if ina is None and clave in FIN_POR_MODIFICACION:
        mod = _d(g("modifiedon"))
        if mod is None or mod < desde:
            raise PendienteD5("S9", "D5_FIN_MODIFICACION_INVALIDO", f"desde={desde} modifiedon={mod}")
        notas.append("D5-C2")
        return desde, mod, notas
    if ina is None:
        raise PendienteD5("S6", "D5_FIN_NO_DEMOSTRADO", "activo=false sin inactivatedon")
    hasta = _dia(ina, -1)
    if hasta < desde:
        raise PendienteD5("S9", "D5_FIN_ANTERIOR_A_INICIO", f"desde={desde} inactivatedon={ina}")
    return desde, hasta, notas


def _base_version(ds: Dataset, co: str, cl: str, fila: dict, ctx: dict, tipo: str, rodante: bool) -> dict:
    g = lambda col: _celda(co, col, fila, ctx)
    per = PERIODICIDAD_V3.get(str(g("periodicidad").valor)) if g("periodicidad").estado == fu.CONOCIDO else None
    if per is None:
        raise PendienteD5("S4", "D5_PERIODICIDAD_SIN_MAPPING", str(g("periodicidad").valor))
    imp = g("importe")
    if imp.estado != fu.CONOCIDO or imp.valor is None or Decimal(str(imp.valor)) <= 0:
        raise PendienteD5("S6", "D5_IMPORTE_NO_POSITIVO")
    importe = Decimal(str(imp.valor))
    if co == "public.gastos":
        ic = g("importe_cuota")
        if ic.estado == fu.CONOCIDO and ic.valor is not None and Decimal(str(ic.valor)) != importe:
            raise PendienteD5("S9", "D5_IMPORTE_CUOTA_DISTINTO")
    if rodante:
        fecha_modo, dd, dh = "ANCLA", None, None
    else:
        r = _rango(g(CAMPO_RANGO[co]).valor) if g(CAMPO_RANGO[co]).estado == fu.CONOCIDO else None
        if r is None:
            raise PendienteD5("S4", "D5_RANGO_NO_REPRESENTABLE", str(g(CAMPO_RANGO[co]).valor))
        fecha_modo, (dd, dh) = "VENTANA", r
    cta = _texto(g("cuenta_id")) if g("cuenta_id").estado == fu.CONOCIDO else None
    cid = None
    if cta:
        cid = fu.uuid_v3("public.cuentas_bancarias", cta, "cuentas", "cuenta")
        if cid not in ds.filas["cuentas"]:
            raise ErrorP5("S8_HUERFANO", f"{co}/{cl} cuenta_id={cta}")
    moneda = ds.filas["cuentas"][cid]["moneda"] if cid else "EUR"
    flujo = FLUJO_POR_TIPO[tipo]
    return {"tipo_hecho_id": TIPOS_HECHO_SEED[tipo], "flujo_tesoreria_esperado": flujo,
            "cuenta_salida_esperada_id": cid if flujo in ("SALIDA", "TRANSFERENCIA") else None,
            "cuenta_entrada_esperada_id": cid if flujo == "ENTRADA" else None,
            "moneda": moneda, "importe_referencia_lado": None, "periodicidad": per[0], "intervalo": per[1],
            "anclaje_recurrencia": "RODANTE" if rodante else "CALENDARIO", "fecha_modo": fecha_modo,
            "dia_desde": dd, "dia_hasta": dh, "importe_modo": "FIJO", "importe_fijo": importe,
            "cuenta_calculo_id": None, "saldo_objetivo": None, "meses_historico": None}


def _categoria_regla(ds: Dataset, co: str, cl: str, fila: dict, tipo: str) -> tuple[str | None, bool]:
    r = clasificar(ds, co, cl, fila) if ds.categorias else ("NULL", None)
    if tipo not in ("GASTO", "INGRESO"):
        if r[0] == "CAT":
            raise PendienteD5("S1", "D5_CATEGORIA_EN_NATURALEZA_FUERA", tipo)
        return None, False
    if r[0] == "FUERA":
        raise ErrorP5("S4_NATURALEZA_FUERA_SIN_GRUPO", f"{co}/{cl} {r[1]}")
    if r[0] == "DESGLOSE":
        raise PendienteD5("S20", "D5_DESGLOSE_EN_REGLA")
    if r[0] == "CAT":
        return r[1], bool(ds.filas["categorias_financieras"][r[1]]["presupuestable_default"])
    return None, tipo == "GASTO"


def _tercero_prov(ds: Dataset, co: str, cl: str, fila: dict, ctx: dict) -> str | None:
    if co != "public.gastos":
        return None
    c = _celda(co, "proveedor_id", fila, ctx)
    if c.estado != fu.CONOCIDO or not _texto(c):
        return None
    tid = fu.uuid_v3("public.proveedores", _texto(c), "terceros", "tercero")
    if tid not in ds.filas["terceros"]:
        raise ErrorP5("S8_HUERFANO", f"{co}/{cl} proveedor_id")
    return tid


def _entidad_vivienda(ds: Dataset, co: str, cl: str, fila: dict, ctx: dict) -> str | None:
    c = _celda(co, "referencia_vivienda_id", fila, ctx)
    if c.estado != fu.CONOCIDO or not _texto(c):
        return None
    pid = fu.uuid_v3("public.patrimonio", _texto(c), "entidades", "propiedad")
    if pid not in ds.filas["propiedades"]:
        raise ErrorP5("S8_HUERFANO", f"{co}/{cl} referencia_vivienda_id")
    return pid


def _alta_regla(ds: Dataset, rid: str, nombre: str, entidad: str | None, origenes: list, versiones: list,
                ledger: list) -> str:
    nombre = (nombre or "").strip()[:160]
    if not nombre:
        raise ErrorP5("S4_REGLA_SIN_NOMBRE", str(origenes))
    ds.add("reglas_financieras", {"id": rid, "owner_user_id": ds.owner, "nombre": nombre, "entidad_origen_id": entidad})
    tm = "FUSIONADO" if len(origenes) > 1 else "CREADO"
    for co, cl in origenes:
        ds.mapear(co, cl, "reglas_financieras", rid, "regla", tipo=tm)
    orden = sorted(versiones, key=lambda v: v[2]["vigente_desde"])
    for (a, b) in zip(orden, orden[1:]):
        if a[2]["vigente_hasta"] is None or _dia(a[2]["vigente_hasta"], 1) != b[2]["vigente_desde"]:
            raise ErrorP5("S9_VERSIONES_NO_CONTIGUAS", f"{rid} {a[2]['vigente_hasta']} -> {b[2]['vigente_desde']}")
    for vorig, rol, v in orden:
        vid = fu.uuid_v3(vorig[0][0], vorig[0][1], "regla_versiones", rol)
        ds.add("regla_versiones", {"id": vid, "regla_id": rid, **v})
        for co, cl in vorig:
            ds.mapear(co, cl, "regla_versiones", vid, rol, tipo="FUSIONADO" if len(vorig) > 1 else "DIVIDIDO")
    for r in ledger:
        ds.ledger.append({"regla": r, "destino": rid, "origenes": [f"{a}/{b}" for a, b in origenes]})
    return rid


def _version(ds, co, cl, fila, ctx, tipo, rodante=False, desde=None) -> tuple[dict, list]:
    v = _base_version(ds, co, cl, fila, ctx, tipo, rodante)
    d, h, notas = _vigencia(co, fila, ctx, desde)
    cat, pres = _categoria_regla(ds, co, cl, fila, tipo)
    v.update({"vigente_desde": d, "vigente_hasta": h, "categoria_id": cat, "presupuestable": pres,
              "tercero_id": None})
    return v, notas


def dominio_5_reglas(ds: Dataset, fuente: dict, ctx: dict) -> dict:
    """Reglas financieras y versiones desde las recurrencias V3 y la renta de contratos."""
    G, I, C = "public.gastos", "public.ingresos", "public.contratos"
    disp = {"CREADA": [], "FUSIONADA": [], "EXCLUIDA_D11": [], "EXCLUIDA_D8": [], "EXCLUIDA_D6": [], "PENDIENTE": []}
    FUSIONES = ([FUSION_MEDIOLANUM] if FUSION_MEDIOLANUM else []) + list(FUSIONES_PROPIETARIO)
    faltan = [k for k in CONTENEDORES_PRESUPUESTARIOS | TRANSFERENCIAS_AHORRO if k not in fuente.get(G, {})] + \
        [k for fz in FUSIONES for k in fz["filas"] if k not in fuente.get(fz["co"], {})]
    faltan += [k for (_, k) in REGLA_DERECHO_ISA if k not in fuente.get(I, {})]
    if faltan:
        raise ErrorP5("S8_ORIGEN_AUSENTE", f"catalogo dominio 5: {sorted(faltan)}")
    recurrentes = [(co, cl, f) for co in (G, I) for cl, f in sorted(fuente.get(co, {}).items())
                   if _celda(co, "periodicidad", f, ctx).valor != "PAGO UNICO"]
    hechos = set()

    def pendiente(co, cl, p):
        _pend(ds, co, cl, p)
        disp["PENDIENTE"].append((f"{co}/{cl}", p.codigo))
        hechos.add((co, cl))

    # renta de contratos (N:1 contrato + ingreso vinculado)
    rentas = {}
    for co, cl, f in recurrentes:
        if co == I:
            c = _celda(I, "contrato_alquiler", f, ctx)
            if c.estado == fu.CONOCIDO and _texto(c):
                rentas.setdefault(_texto(c), []).append((cl, f))
    for ck, ct in sorted(fuente.get(C, {}).items()):
        ren = _celda(C, "renta_mensual", ct, ctx)
        if ren.estado != fu.CONOCIDO or ren.valor is None:
            continue
        filas = rentas.pop(ck, [])
        if len(filas) != 1:
            raise ErrorP5("S20_RENTA_SIN_FILA_INGRESO_UNICA", f"{C}/{ck} filas={len(filas)}")
        kl, fi = filas[0]
        eid = fu.uuid_v3(C, ck, "entidades", "contrato")
        con = ds.filas["contratos"].get(eid)
        if con is None:
            raise ErrorP5("S8_HUERFANO", f"{C}/{ck}")
        try:
            v, notas = _version(ds, I, kl, fi, ctx, "INGRESO", desde=con["fecha_inicio"])
        except PendienteD5 as p:
            pendiente(I, kl, p)
            continue
        if v["importe_fijo"] != Decimal(str(ren.valor)) or v["periodicidad"] != "MENSUAL" or v["intervalo"] != 1:
            raise ErrorP5("S9_RENTA_INCOMPATIBLE", f"{C}/{ck} ingreso={v['importe_fijo']} renta={ren.valor}")
        rid = fu.uuid_v3(C, ck, "reglas_financieras", "renta")
        ini_i = _d(_celda(I, "fecha_inicio", fi, ctx))
        led = ["D5-A", "D5-L", "D5-D", "D5-G"] + notas + (["D10-B"] if ini_i != con["fecha_inicio"] else [])
        _alta_regla(ds, rid, _texto(_celda(I, "concepto", fi, ctx)), eid, [(C, ck), (I, kl)],
                    [([(I, kl), (C, ck)], "renta.v1", v)], led)
        con["regla_renta_id"] = rid
        disp["FUSIONADA"].append((f"{I}/{kl}+{C}/{ck}", rid))
        hechos.add((I, kl))
    if rentas:
        raise ErrorP5("S8_CONTRATO_AUSENTE", str(sorted(rentas)))

    # fusiones N:1 (Mediolanum canonica §16 + fusiones decididas por el propietario 2026-09-21)
    for fz in FUSIONES:
        co = fz["co"]
        tipo = fz.get("tipo") or ("GASTO" if co == G else "INGRESO")
        vers, origenes, firmas = [], [], set()
        try:
            for n, kg in enumerate(fz["filas"], 1):
                f = fuente[co][kg]
                v, notas = _version(ds, co, kg, f, ctx, tipo, desde=None)
                v["tercero_id"] = _tercero_prov(ds, co, kg, f, ctx)
                ent_v = _entidad_vivienda(ds, co, kg, f, ctx) if not fz.get("inversion") else None
                firmas.add((v["cuenta_salida_esperada_id"], v["cuenta_entrada_esperada_id"], v["tercero_id"],
                            v["periodicidad"], v["intervalo"], v["moneda"], v["categoria_id"], ent_v,
                            clasificar(ds, co, kg, f)[0] if ds.categorias else "NULL"))
                vers.append(([(co, kg)], f"v{n}", v))
                origenes.append((co, kg))
        except PendienteD5 as p:
            for kg in fz["filas"]:
                pendiente(co, kg, PendienteD5(p.stop, p.codigo, f"fusion {fz['filas']}: {p.detalle}"))
            continue
        if len(firmas) != 1:
            raise ErrorP5("S9_FUSION_INCOMPATIBLE", f"{fz['filas']} {firmas}")
        vers.sort(key=lambda x: x[2]["vigente_desde"])
        led = ["D5-A", "D5-K" if fz.get("inversion") else "D5-K3", "D5-D", "D5-G"]
        for prev, nxt in zip(vers, vers[1:]):
            fin = _dia(nxt[2]["vigente_desde"], -1)
            h = prev[2]["vigente_hasta"]
            if h is not None and h > fin and fin >= prev[2]["vigente_desde"]:
                ds.ledger.append({"regla": "D5-K2", "origen": f"{co}/{prev[0][0][1]}", "hasta_evidencia": h, "hasta": fin})
                prev[2]["vigente_hasta"] = fin
        if fz.get("inversion"):
            ent = fu.uuid_v3("public.inversion", fz["inversion"], "entidades", "inversion")
            if ent not in ds.filas["inversiones"]:
                raise ErrorP5("S8_HUERFANO", fz["inversion"])
        else:
            ent = next(iter(firmas))[7]
        rid = fz.get("regla_id") or fu.uuid_v3(co, fz["filas"][0], "reglas_financieras", "regla")
        ultima = vers[-1][0][0][1]
        _alta_regla(ds, rid, _texto(_celda(co, CAMPO_NOMBRE[co], fuente[co][ultima], ctx)), ent, origenes, vers, led)
        disp["FUSIONADA"].append(("+".join(f"{a}/{b}" for a, b in origenes), rid))
        hechos.update(origenes)

    ahorro = fu.uuid_v3(CUENTA_AHORRO[0], CUENTA_AHORRO[1], "cuentas", "cuenta")
    for co, cl, f in recurrentes:
        if (co, cl) in hechos:
            continue
        hechos.add((co, cl))
        if co == G and cl in CONTENEDORES_PRESUPUESTARIOS:
            disp["EXCLUIDA_D11"].append(f"{co}/{cl}")
            continue
        if co == G and fu.uuid_v3(co, cl, "entidades", "financiacion") in ds.filas["financiaciones"]:
            disp["EXCLUIDA_D8"].append(f"{co}/{cl}")
            continue
        if (co, cl) in COBRO_PARCIAL_NO_REGLA:
            disp["EXCLUIDA_D6"].append(f"{co}/{cl}")
            ds.ledger.append({"regla": "D5-S", "origen": f"{co}/{cl}"})
            continue
        pr = _celda(co, "prestamo_id", f, ctx) if co == G else None
        if pr is not None and pr.estado == fu.CONOCIDO and _texto(pr) and CUOTA_PRESTAMO_SIN_REGLA:
            if fu.uuid_v3("public.prestamo", _texto(pr), "entidades", "financiacion") not in ds.filas["financiaciones"]:
                raise ErrorP5("S8_HUERFANO", f"{co}/{cl} prestamo_id={_texto(pr)}")
            disp["EXCLUIDA_D8"].append(f"{co}/{cl}")
            ds.ledger.append({"regla": "D5-T", "origen": f"{co}/{cl}"})
            continue
        try:
            g = lambda col: _celda(co, col, f, ctx)
            if co == G and g("prestamo_id").estado == fu.CONOCIDO and _texto(g("prestamo_id")):
                raise PendienteD5("S20", "D5_CUOTA_PRESTAMO_TIPO_HECHO", _texto(g("prestamo_id")))
            if co == G and g("cuotas").estado == fu.CONOCIDO and g("cuotas").valor not in (None, 1):
                raise PendienteD5("S20", "D5_GASTO_A_PLAZOS_NATURALEZA", f"cuotas={g('cuotas').valor}")
            ent, led = None, ["D5-A", "D5-B", "D5-C", "D5-D", "D5-E", "D5-F", "D5-G", "D5-H", "D5-I"]
            if (co, cl) in REGLA_DERECHO_ISA:
                dco, dcl = REGLA_DERECHO_ISA[(co, cl)]
                ent = fu.uuid_v3(dco, dcl, "entidades", "derecho")
                if ent not in ds.filas["derechos_obligaciones_financieras"]:
                    raise ErrorP5("S8_HUERFANO", f"derecho de {co}/{cl}")
                if ISA_TIPO_HECHO_DECIDIDO is None:
                    raise PendienteD5("S1", "D5_ISA_TIPO_HECHO", "mandato GENERACION vs F04-D015/D016 REEMBOLSO")
                if ISA_TIPO_HECHO_DECIDIDO not in ISA_TIPOS_ADMITIDOS:
                    raise ErrorP5("S4_ISA_TIPO_HECHO", ISA_TIPO_HECHO_DECIDIDO)
                v, notas = _version(ds, co, cl, f, ctx, ISA_TIPO_HECHO_DECIDIDO)
            elif co == G and cl in TRANSFERENCIAS_AHORRO:
                if ahorro not in ds.filas["cuentas"]:
                    raise ErrorP5("S8_HUERFANO", "cuenta de ahorro derivada")
                v, notas = _version(ds, co, cl, f, ctx, "TRANSFERENCIA")
                if v["cuenta_salida_esperada_id"] == ahorro:
                    raise ErrorP5("S9_AUTOTRANSFERENCIA", f"{co}/{cl}")
                v["cuenta_entrada_esperada_id"] = ahorro
                led.append("D5-J")
            else:
                tipo = "GASTO" if co == G else "INGRESO"
                v, notas = _version(ds, co, cl, f, ctx, tipo, rodante=(co, cl) in RODANTES_VALIDADOS)
                v["tercero_id"] = _tercero_prov(ds, co, cl, f, ctx)
                ent = _entidad_vivienda(ds, co, cl, f, ctx)
        except PendienteD5 as p:
            pendiente(co, cl, p)
            continue
        rid = fu.uuid_v3(co, cl, "reglas_financieras", "regla")
        _alta_regla(ds, rid, _texto(_celda(co, CAMPO_NOMBRE[co], f, ctx)), ent, [(co, cl)],
                    [([(co, cl)], "v1", v)], led + notas)
        disp["CREADA"].append((f"{co}/{cl}", rid))
    ds.ledger.append({"regla": "D5-M", "regla_excepciones": 0})
    # disposicion exclusiva y exhaustiva de cada fila recurrente V3 (R05 del dominio)
    vistos = [o for k in ("EXCLUIDA_D11", "EXCLUIDA_D8", "EXCLUIDA_D6") for o in disp[k]] + [o for o, _ in disp["PENDIENTE"]] + \
        [o for o, _ in disp["CREADA"]] + [x for o, _ in disp["FUSIONADA"] for x in o.split("+") if not x.startswith(C)]
    esperados = [f"{co}/{cl}" for co, cl, _ in recurrentes]
    if sorted(vistos) != sorted(esperados):
        raise ErrorP5("S9_DISPOSICION_D5", f"filas={len(esperados)} disposiciones={len(vistos)}")
    resumen = {k: len(x) for k, x in disp.items()}
    resumen["recurrentes_v3"] = len(recurrentes)
    resumen["rentas_contrato"] = sum(1 for _, ct in fuente.get(C, {}).items()
                                     if _celda(C, "renta_mensual", ct, ctx).valor is not None)
    resumen["reglas"] = len(ds.filas["reglas_financieras"])
    resumen["versiones"] = len(ds.filas["regla_versiones"])
    ds.ledger.append({"regla": "D5-R", "resumen": resumen})
    return {"resumen": resumen, "disposicion": disp}


# ------------------------------------------------------------ pipeline
# ------------------------------------------------------------ dominio 6 (hechos) - bloque 1
# Plan R2 dominio 6: hechos, efectos, atribuciones, terceros y vinculos a entidades de las 810 filas
# operativas sin regla ni financiacion (RUN02: HECHO_EXACTO) + el cobro parcial derivado por D5-S.
# Sin tesoreria (dominio 7; D-MIG-015 y Migration V3 §18: cuenta_id V3 no prueba movimiento bancario).
DOMINIO_6_ACTIVO = True
MONEDA_V3 = "EUR"  # D6-M: V3 es monodivisa EUR (Revolut EUR confirmado S20); sin campo de moneda por fila
NATURALEZA_TRANSFERENCIA = {"transferencia entre cuentas propias", "amortizacion de tarjeta (transferencia)",
                            "reintegro de ahorro (transferencia)"}
NATURALEZA_REEMBOLSO = {"devolucion de capital (reduce derecho)", "reembolso de suministros (reduce derecho)"}
PREFIJO_INTERES = "cuota de financiacion (interes -> "
# Opcion A del propietario (2026-09-21): traspaso real sin movimiento V3 -> hecho TRANSFERENCIA neutro sin
# movimientos (excepcion legacy D6-T). CARGA REVOLUT: Migration V3 §14 (traspaso entre cuentas propias).
TRANSFERENCIA_LEGACY_DECIDIDA = {("public.gastos", "gasto-xg1mue")}
# OP-13 (F04-06): devolucion = GASTO negativo de la misma naturaleza. Gafas: origen conocido (DEVOLUCION_DE).
# PAPA (GASOLINA): devolucion de gasolina declarada por el propietario (2026-09-21); origen no identificado ->
# sin relacion inventada (D6-D2).
DEVOLUCION_DECIDIDA = {("public.ingresos", "INGRESO-5SRKF6"): ("public.gastos", "gasto-i3yngl"),
                       ("public.ingresos", "INGRESO-6AMJ79"): None}
GASTO_CORREGIDO_V3 = {("public.ingresos", "INGRESO-SIJREF")}  # Migration V3 §23: ventiladores = gasto de 85 EUR
# Respuesta 3 (2026-09-21): la luz de Allende la soporta 100 % el inquilino (contraparte del derecho).
ATRIBUCION_CONTRAPARTE_100 = {f"DER-LUZ-0{n}" for n in range(3, 8)}
# Sin decision: gasto adelantado parcialmente reembolsado (Canela, tarta Ana) -> pendiente de fila.
ATRIBUCION_DERECHO_PENDIENTE = {"DER-CANELA"}
# Respuesta 1 (2026-09-21): ticket pagado entero y compartido; la parte del otro participante es el importe del
# derecho. Contraparte sin actor -> atribucion PARCIAL (no se crea actor ficticio); con actor -> COMPLETA.
ATRIBUCION_COMPARTIDA = {"DER-ANA"}
# Respuestas del propietario 2026-09-21 (P5 v0.20.0), por vivienda V3:
#   Fuensanta: todo lo relacionado se reparte 50 % (participacion vigente de la propiedad) -> PARTICIPACION;
#   Blasco Ibanez: gasto 100 % propio (contribucion a la vivienda habitual sin participacion) -> SELF_100.
VIVIENDA_ATRIBUCION_DECIDIDA = {"VIVIENDA-42E8QW": "PARTICIPACION", "VIVIENDA-0B1D7T": "SELF_100"}
# Respuesta 4: el total real del ticket es 15,61 (V3 guardo 15,605); el literal V3 se conserva en origen.
IMPORTE_TOTAL_CORREGIDO = {("public.gastos_cotidianos", "GASTO_COTIDIANO-1FRA14"): Decimal("15.61")}
COMPRAS_FINANCIADAS_D6 = True
# Respuesta 2 (2026-09-21): el vuelo de Tailandia tambien pertenece al contexto Tailandia 2026.
CONTEXTO_ADICIONAL = {("public.gastos", "gasto-x2t6dm"): "CTX-TAILANDIA-2026"}  # bloque 2 del dominio 6 (OP-15)
# Prestamo/adelanto puro sin gasto propio (Migration V3, F03-01 punto 2: Tania-SHEIN).
GENERACION_PURA = {"DER-SHEIN"}

LEDGER_REGLAS.update({
    "D6-A": "1 fila operativa -> 1 hecho (uuid v3|fila|hechos_financieros|hecho); fecha_hecho = fecha / fecha_inicio V3; "
            "estado ACTIVO; localizacion DESCONOCIDA (V3 no la registra; NO_APLICA nunca es default).",
    "D6-B": "GASTO: efecto GASTO por el total del hecho (total/importe_total); atribucion self = parte personal V3 "
            "(importe); COMPLETA si coincide, PARCIAL si falta el resto (Migration V3 §18/§23, sin actores ficticios).",
    "D6-C": "INGRESO real: efecto INGRESO por importe, atribucion self 100 %.",
    "D6-D": "devolucion (OP-13): hecho GASTO con efecto GASTO negativo y DEVOLUCION_DE si el origen es conocido; "
            "nunca INGRESO.",
    "D6-D2": "devolucion con origen no identificado: sin relacion inventada; capacidad reversible no demostrable en "
             "legacy (declarada).",
    "D6-E": "derecho de cobro: la generacion y el cobro se vinculan con hecho_entidades al efecto DERECHO_COBRO. El "
            "saldo de la posicion solo suma deltas posteriores a fecha_inicio_seguimiento (DB Schema §46): los hechos "
            "anteriores al corte son detalle reconstruido y no alteran la apertura del dominio 8B (D-MIG-015).",
    "D6-F": "reembolso (F04-D015): REEMBOLSO con DERECHO_COBRO negativo; REEMBOLSO_DE solo si el hecho generador existe.",
    "D6-G": "prestamo/adelanto puro a tercero sin gasto propio -> GENERACION_DERECHO_OBLIGACION (Migration V3, "
            "F03-01 punto 2).",
    "D6-M": "moneda EUR (V3 monodivisa).",
    "D6-P": "presupuestable = presupuestable_default de la categoria; sin categoria GASTO si / INGRESO no; "
            "transferencias, reembolsos y generaciones de derecho false.",
    "D6-Q": "sin aportaciones de pago ni efecto_cuentas en el historico (decidido por el propietario 2026-09-21): el "
            "cuenta_id V3 no prueba el cargo bancario (Migration V3 §18) y queda en origen; los saldos abren en el corte.",
    "D6-R": "tercero: proveedor V3 -> hecho_terceros VENDEDOR principal.",
    "D6-S": "vivienda V3 -> hecho_entidades AFECTA_A (nivel hecho); contexto decidido -> RELACIONADO_CON.",
    "D6-T": "traspaso real sin movimiento V3 (opcion A del propietario): hecho TRANSFERENCIA sin efectos ni "
            "movimientos; excepcion legacy a la literalidad de F04-D001 (no se fabrica tesoreria).",
    "D6-U": "cotidianos: numero_participantes_total = cantidad; observaciones/comentarios -> notas.",
    "D6-V": "vivienda con atribucion decidida por el propietario: PARTICIPACION -> reparto del total por las "
            "entidad_participaciones vigentes en fecha_hecho (criterio PARTICIPACION_ENTIDAD, suma exacta); SELF_100 -> "
            "100 % propietario aunque no participe en la vivienda. Sin decision -> pendiente de fila.",
    "D6-W": "total corregido por el propietario (clase C): se usa el importe declarado; el literal V3 queda en origen.",
    "D6-Z": "ticket compartido decidido por el propietario: GASTO por el total; parte propia = total - derecho; la "
            "parte del otro participante solo se atribuye si tiene actor (si no, PARCIAL); DERECHO_COBRO por esa parte "
            "y su cobro como REEMBOLSO. El importe personal V3 (que no descontaba el Bizum) queda en origen.",
    "D6-X": "compra financiada (OP-15): hecho COMPRA_FINANCIADA con GASTO por el total (nace con la compra) y DEUDA por "
            "el principal que desembolsa el financiador (= capital_original_contratado, comprobado contra cuota x numero "
            "de cuotas), ambos atribuidos por la participacion vigente de la financiacion y la DEUDA vinculada a ella. "
            "La compra es anterior a fecha_inicio_seguimiento: su DEUDA no altera el saldo de apertura (D6-E); si no lo "
            "fuese -> S9 (doble conteo). Las cuotas no crean gasto.",
    "D6-Y": "sin hecho: compra financiada cancelada (NUTRICIONISTA, respuesta del propietario) y cuotas de prestamo "
            "(D5-T; su expectativa es el calendario de la financiacion, D-MIG-015).",
})


class PendienteD6(Exception):
    def __init__(self, clase: str, codigo: str, detalle: str | None = None):
        super().__init__(codigo)
        self.clase, self.codigo, self.detalle = clase, codigo, detalle


def _presup(ds: Dataset, cat: str | None, tipo: str) -> bool:
    if tipo not in ("GASTO", "INGRESO"):
        return False
    if cat is not None:
        return bool(ds.filas["categorias_financieras"][cat]["presupuestable_default"])
    return tipo == "GASTO"


def _dec_c(co, col, fila, ctx):
    c = _celda(co, col, fila, ctx)
    return Decimal(str(c.valor)) if c.estado == fu.CONOCIDO and c.valor is not None else None


def _tercero_hecho(ds, co, cl, fila, ctx):
    if co not in ("public.gastos", "public.gastos_cotidianos"):
        return None
    c = _celda(co, "proveedor_id", fila, ctx)
    if c.estado != fu.CONOCIDO or not _texto(c):
        return None
    tid = fu.uuid_v3("public.proveedores", _texto(c), "terceros", "tercero")
    if tid not in ds.filas["terceros"]:
        raise ErrorP5("S8_HUERFANO", f"{co}/{cl} proveedor_id")
    return tid


def _participacion_entidad_self_100(ds, eid) -> bool:
    ps = [p for p in ds.filas["entidad_participaciones"].values() if p["entidad_id"] == eid]
    return bool(ps) and all(p["actor_id"] == ds.self_id and Decimal(p["porcentaje"]) == 100 for p in ps)


class _H:
    """Constructor de un hecho y sus hijos, todos mapeados al registro origen."""

    def __init__(self, ds, co, cl, tipo, fecha, concepto, importe_total, presupuestable, notas=None, participantes=None):
        self.ds, self.co, self.cl = ds, co, cl
        self.id = fu.uuid_v3(co, cl, "hechos_financieros", "hecho")
        self.efectos, self.hijos = [], []
        self.fila = {"id": self.id, "owner_user_id": ds.owner, "tipo_hecho_id": TIPOS_HECHO_SEED[tipo],
                     "fecha_hecho": fecha, "concepto": concepto, "importe_total": importe_total,
                     "numero_participantes_total": participantes, "moneda": MONEDA_V3, "localidad_id": None,
                     "estado_localizacion": "DESCONOCIDA", "estado": "ACTIVO", "anulado_at": None,
                     "motivo_anulacion": None, "presupuestable": presupuestable, "notas": notas}

    def efecto(self, rol, tipo_efecto, delta, categoria, atribs, estado):
        if delta == 0:
            raise PendienteD6("S6", "D6_EFECTO_CERO", rol)
        eid = fu.uuid_v3(self.co, self.cl, "hecho_efectos", rol)
        self.efectos.append(("hecho_efectos", {"id": eid, "hecho_id": self.id, "tipo_efecto": tipo_efecto,
                                               "importe_delta": delta, "categoria_id": categoria,
                                               "estado_atribucion": estado, "descripcion": None}, rol))
        for actor, imp, crit, *pct in atribs:
            self.hijos.append(("efecto_atribuciones", {
                "id": fu.uuid_v3(self.co, self.cl, "efecto_atribuciones", f"{rol}.{actor}"), "efecto_id": eid,
                "actor_id": actor, "importe_atribuido": imp, "porcentaje_aplicado": pct[0] if pct else None,
                "criterio_atribucion": crit}, f"{rol}.atribucion.{actor}"))
        return eid

    def entidad(self, entidad_id, tipo_rel, efecto_id=None, rol="entidad"):
        self.hijos.append(("hecho_entidades", {
            "id": fu.uuid_v3(self.co, self.cl, "hecho_entidades", f"{rol}.{entidad_id}"), "hecho_id": self.id,
            "efecto_id": efecto_id, "entidad_id": entidad_id, "tipo_relacion": tipo_rel, "principal": True,
            "owner_user_id": self.ds.owner}, rol))

    def tercero(self, tid, rol_en_hecho="VENDEDOR"):
        self.hijos.append(("hecho_terceros", {
            "id": fu.uuid_v3(self.co, self.cl, "hecho_terceros", rol_en_hecho), "hecho_id": self.id,
            "tercero_id": tid, "rol_en_hecho": rol_en_hecho, "principal": True}, "tercero"))

    def relacion(self, destino_id, tipo_rel, importe):
        self.hijos.append(("hecho_relaciones", {
            "id": fu.uuid_v3(self.co, self.cl, "hecho_relaciones", tipo_rel), "hecho_origen_id": self.id,
            "hecho_destino_id": destino_id, "tipo_relacion": tipo_rel, "importe_relacionado": importe,
            "notas": None}, tipo_rel.lower()))

    def confirmar(self):
        ds = self.ds
        ds.add("hechos_financieros", self.fila)
        ds.mapear(self.co, self.cl, "hechos_financieros", self.id, "hecho")
        for tabla, fila, rol in self.efectos + self.hijos:
            ds.add(tabla, fila)
            ds.mapear(self.co, self.cl, tabla, fila["id"], rol, tipo="DIVIDIDO")
        return self.id


def _filas_dominio_6(ds: Dataset, fuente: dict) -> list:
    disp = (ds.reglas or {}).get("disposicion", {})
    fuera = set()
    for k in ("CREADA", "FUSIONADA"):
        for o, _ in disp.get(k, []):
            fuera.update(tuple(x.split("/", 1)) for x in o.split("+"))
    for k in ("EXCLUIDA_D11", "EXCLUIDA_D8"):
        fuera.update(tuple(o.split("/", 1)) for o in disp.get(k, []))
    return [(co, cl) for co in CONTENEDORES_OPERATIVOS for cl in sorted(fuente.get(co, {})) if (co, cl) not in fuera]


def dominio_6_hechos(ds: Dataset, fuente: dict, ctx: dict) -> dict:
    filas = _filas_dominio_6(ds, fuente)
    derecho_de = {}  # (co, cl) -> (id derecho, rol 'genera'|'cobro')
    for d in DERECHOS_V3:
        origenes = ([d["genera"]] if d["genera"] else []) + d["evidencia"]
        eid = fu.uuid_v3(origenes[0][0], origenes[0][1], "entidades", "derecho")
        if eid not in ds.filas["derechos_obligaciones_financieras"]:
            raise ErrorP5("S8_DERECHO_AUSENTE", d["id"])
        if d["genera"]:
            derecho_de[tuple(d["genera"])] = (d, eid, "genera")
        for e in d["evidencia"]:
            derecho_de[tuple(e)] = (d, eid, "cobro")
    contexto_de = {}
    if ds.decisiones is not None:
        for c in sorted(ds.decisiones.doc.get("contextos", []), key=lambda x: x["id"]):
            clave = f"contexto/{c['id']}"
            cid = fu.uuid_v3(CONT_DECISIONES, clave, "entidades", "contexto")
            ds.add("entidades", {"id": cid, "owner_user_id": ds.owner, "tipo_entidad": "CONTEXTO",
                                 "nombre": c["nombre"].strip()})
            ds.add("contextos", {"entidad_id": cid, "tipo_contexto": c["tipo"], "fecha_inicio": None,
                                 "fecha_fin": None, "notas": None})
            ds.mapear(CONT_DECISIONES, clave, "entidades", cid, "contexto", confianza="VALIDADA")
            ds.mapear(CONT_DECISIONES, clave, "contextos", cid, "contexto", tipo="DIVIDIDO", confianza="VALIDADA")
            extra = [f"{k[0]}/{k[1]}" for k, v in sorted(CONTEXTO_ADICIONAL.items()) if v == c["id"]]
            for r in list(c["registros"]) + extra:
                o = tuple(r.split("/", 1))
                if o[1] not in fuente.get(o[0], {}):
                    raise ErrorP5("S8_CONTEXTO_SIN_ORIGEN", r)
                contexto_de.setdefault(o, []).append(cid)
    creados, ids, pend = {}, {}, []
    # los origenes de relaciones (generador, gasto original) se construyen antes que sus dependientes
    orden = sorted(filas, key=lambda o: (o in derecho_de and derecho_de[o][2] == "cobro") or o in DEVOLUCION_DECIDIDA)
    for co, cl in orden:
        try:
            tipo, h = _hecho_v3(ds, fuente, ctx, co, cl, derecho_de, contexto_de, ids, set(filas),
                                {tuple(x.split("/", 1)) for x in pend})
        except PendienteD6 as p:
            ds.pendientes.append({"dominio": 6, "origen": f"{co}/{cl}", "clase": p.clase, "codigo": p.codigo,
                                  "detalle": p.detalle})
            pend.append(f"{co}/{cl}")
            continue
        ids[(co, cl)] = h.confirmar()
        creados[tipo] = creados.get(tipo, 0) + 1
    for o in sorted(o for o in DEVOLUCION_DECIDIDA if o in dict.fromkeys(filas) and DEVOLUCION_DECIDIDA[o] is None):
        ds.ledger.append({"regla": "D6-D2", "origen": f"{o[0]}/{o[1]}"})
    for co, cl in filas:
        if (co, cl) in TRANSFERENCIA_LEGACY_DECIDIDA or ((co, cl) in ids and
                ds.filas["hechos_financieros"][ids[(co, cl)]]["tipo_hecho_id"] == TIPOS_HECHO_SEED["TRANSFERENCIA"]):
            ds.ledger.append({"regla": "D6-T", "origen": f"{co}/{cl}"})
    if COMPRAS_FINANCIADAS_D6:
        for co, cl in _filas_d8(ds, fuente):
            fid = _financiacion_de(ds, co, cl)
            fin = ds.filas["financiaciones"].get(fid) if fid else None
            if fin is None or fin["tipo_financiacion"] != "COMPRA_FINANCIADA" or fin["motivo_cierre"] == "CANCELADA":
                ds.ledger.append({"regla": "D6-Y", "origen": f"{co}/{cl}"})
                continue
            try:
                h = _compra_financiada(ds, fuente, ctx, co, cl, fid, fin)
                for cid in contexto_de.get((co, cl), []):
                    h.entidad(cid, "RELACIONADO_CON", rol="contexto")
            except PendienteD6 as p:
                ds.pendientes.append({"dominio": 6, "origen": f"{co}/{cl}", "clase": p.clase, "codigo": p.codigo,
                                      "detalle": p.detalle})
                pend.append(f"{co}/{cl}")
                continue
            ids[(co, cl)] = h.confirmar()
            creados["COMPRA_FINANCIADA"] = creados.get("COMPRA_FINANCIADA", 0) + 1
            ds.ledger.append({"regla": "D6-X", "origen": f"{co}/{cl}"})
    return {"filas": len(filas), "creados": creados, "pendientes": pend}


def _filas_d8(ds: Dataset, fuente: dict) -> list:
    disp = (ds.reglas or {}).get("disposicion", {})
    return sorted(tuple(o.split("/", 1)) for o in disp.get("EXCLUIDA_D8", []))


def _financiacion_de(ds: Dataset, co: str, cl: str) -> str | None:
    org = fu.uuid_origen(co, cl)
    fs = {m["registro_destino_id"] for m in ds.filas["mapeos_importacion"].values()
          if m["tabla_destino"] == "financiaciones" and m["registro_origen_id"] == org}
    if len(fs) > 1:
        raise ErrorP5("S7_FINANCIACION_AMBIGUA", f"{co}/{cl}")
    return next(iter(fs), None)


def _compra_financiada(ds, fuente, ctx, co, cl, fid, fin):
    f = fuente[co][cl]
    fc = _celda(co, "fecha", f, ctx)
    if fc.estado != fu.CONOCIDO:
        raise PendienteD6("S6", "D6_FECHA_DESCONOCIDA")
    fecha = str(fc.valor)[:10]
    if fecha != fin["fecha_inicio"]:
        raise ErrorP5("S9_COMPRA_FECHA_DISTINTA_DE_FINANCIACION", f"{co}/{cl}")
    if fin["fecha_inicio_seguimiento"] is not None and fecha >= fin["fecha_inicio_seguimiento"]:
        raise ErrorP5("S9_COMPRA_DENTRO_DEL_SEGUIMIENTO", f"{co}/{cl}")  # su DEUDA se contaria dos veces
    total = Decimal(fin["capital_original_contratado"])
    cvs = [v for v in ds.filas["financiacion_condiciones_versiones"].values() if v["financiacion_entidad_id"] == fid]
    if len(cvs) != 1 or Decimal(cvs[0]["importe_cuota_referencia"]) * cvs[0]["numero_cuotas_referencia"] != total:
        raise PendienteD6("S20", "D6_PRINCIPAL_NO_DEMOSTRADO", f"{co}/{cl}")
    clasif = clasificar(ds, co, cl, f)
    if clasif[0] not in ("CAT", "NULL"):
        raise ErrorP5("S4_COMPRA_SIN_CATEGORIA_ECONOMICA", f"{co}/{cl} {clasif}")
    cat = clasif[1] if clasif[0] == "CAT" else None
    ps = [p for p in ds.filas["entidad_participaciones"].values() if p["entidad_id"] == fid
          and p["vigente_desde"] <= fecha and (p["vigente_hasta"] is None or p["vigente_hasta"] >= fecha)]
    if not ps:  # el dominio 8 no fijo participacion para esta financiacion: no se presume 100 % propio
        raise PendienteD6("S20", "D6_COMPRA_SIN_PARTICIPACION", f"{co}/{cl}")
    if sum(Decimal(p["porcentaje"]) for p in ps) != 100:
        raise ErrorP5("S9_PARTICIPACION_COMPRA_NO_CUADRA", f"{co}/{cl}")
    ps = sorted(ps, key=lambda x: x["actor_id"])

    def rep(importe):
        return [(p["actor_id"], importe * Decimal(p["porcentaje"]) / 100, "PARTICIPACION_ENTIDAD",
                 Decimal(p["porcentaje"])) for p in ps]
    nombre = _texto(_celda(co, "nombre", f, ctx))
    notas = _texto(_celda(co, "comentarios", f, ctx))
    h = _H(ds, co, cl, "COMPRA_FINANCIADA", fecha, nombre, total, _presup(ds, cat, "GASTO"), notas)
    h.efecto("gasto", "GASTO", total, cat, rep(total), "COMPLETA")
    ed = h.efecto("deuda", "DEUDA", total, None, rep(total), "COMPLETA")
    h.entidad(fid, "AFECTA_A", ed, rol="financiacion")
    tid = _tercero_hecho(ds, co, cl, f, ctx)
    if tid:
        h.tercero(tid)
    fa = fin.get("financiador_actor_id")
    ft = ds.filas["actores_financieros"].get(fa, {}).get("tercero_id") if fa else None
    if ft and ft != tid:
        h.tercero(ft, "FINANCIADOR")
    viv = _entidad_vivienda(ds, co, cl, f, ctx)
    if viv:
        h.entidad(viv, "AFECTA_A", rol="vivienda")
    return h


def _hecho_v3(ds, fuente, ctx, co, cl, derecho_de, contexto_de, ids, filas_d6=frozenset(), pendientes_d6=frozenset()):
    f = fuente[co][cl]
    fc = _celda(co, "fecha_inicio" if co == "public.ingresos" else "fecha", f, ctx)
    if fc.estado != fu.CONOCIDO:
        raise PendienteD6("S6", "D6_FECHA_DESCONOCIDA")
    fecha = str(fc.valor)[:10]
    nombre = _texto(_celda(co, {"public.gastos": "nombre", "public.ingresos": "concepto"}[co], f, ctx)) \
        if co != "public.gastos_cotidianos" else None
    col_nota = {"public.gastos": "comentarios", "public.gastos_cotidianos": "observaciones"}.get(co)
    notas = _texto(_celda(co, col_nota, f, ctx)) if col_nota else None
    imp = _dec_c(co, "importe", f, ctx)
    tot = _dec_c(co, "importe_total" if co == "public.gastos_cotidianos" else "total", f, ctx) \
        if co != "public.ingresos" else imp
    if tot is None:
        tot = imp
    if (co, cl) in IMPORTE_TOTAL_CORREGIDO:
        tot = IMPORTE_TOTAL_CORREGIDO[(co, cl)]
        ds.ledger.append({"regla": "D6-W", "origen": f"{co}/{cl}", "importe_total": str(tot)})
    if imp is None or tot is None:
        raise PendienteD6("S6", "D6_IMPORTE_DESCONOCIDO")
    if imp < 0 or tot < 0:
        raise ErrorP5("S9_IMPORTE_INCOHERENTE", f"{co}/{cl}")
    if imp > tot:  # dato V3 incoherente (clase C): no se redondea ni se corrige
        raise PendienteD6("C", "D6_PARTE_PERSONAL_SUPERA_TOTAL", f"{imp} > {tot}")
    clasif = clasificar(ds, co, cl, f)
    if clasif[0] == "DESGLOSE":
        raise PendienteD6("S20", "D6_DESGLOSE")
    cat = clasif[1] if clasif[0] == "CAT" else None
    naturaleza = clasif[1] if clasif[0] == "FUERA" else None
    tid = _tercero_hecho(ds, co, cl, f, ctx)
    viv = _entidad_vivienda(ds, co, cl, f, ctx)
    S = ds.self_id
    o = (co, cl)
    viv_v3 = _texto(_celda(co, "referencia_vivienda_id", f, ctx)) if viv else None
    modo_viv = VIVIENDA_ATRIBUCION_DECIDIDA.get(viv_v3) if viv else None

    def _reparto(total):
        """Atribucion del total segun la decision de vivienda (D6-V); None = regla general."""
        if modo_viv == "SELF_100":
            return [(S, total, "MANUAL")]
        if modo_viv != "PARTICIPACION":
            return None
        ps = [p for p in ds.filas["entidad_participaciones"].values() if p["entidad_id"] == viv
              and p["vigente_desde"] <= fecha and (p["vigente_hasta"] is None or p["vigente_hasta"] >= fecha)]
        if not ps or sum(Decimal(p["porcentaje"]) for p in ps) != 100:
            raise ErrorP5("S9_PARTICIPACION_VIVIENDA_NO_CUADRA", f"{co}/{cl}")
        return [(p["actor_id"], total * Decimal(p["porcentaje"]) / 100, "PARTICIPACION_ENTIDAD", Decimal(p["porcentaje"]))
                for p in sorted(ps, key=lambda x: x["actor_id"])]

    def _base(h):
        if tid:
            h.tercero(tid)
        if viv:
            h.entidad(viv, "AFECTA_A", rol="vivienda")
        for cid in contexto_de.get(o, []):
            h.entidad(cid, "RELACIONADO_CON", rol="contexto")
        return h

    # 1) traspasos propios (opcion A)
    if o in TRANSFERENCIA_LEGACY_DECIDIDA or naturaleza in NATURALEZA_TRANSFERENCIA:
        if cat is not None:
            raise ErrorP5("S1_CATEGORIA_EN_TRANSFERENCIA", f"{co}/{cl}")
        h = _H(ds, co, cl, "TRANSFERENCIA", fecha, nombre, tot, False, notas)
        return "TRANSFERENCIA", h
    # 2) derechos de cobro
    if o in derecho_de:
        d, did, rol = derecho_de[o]
        if rol == "genera" and d["id"] in ATRIBUCION_DERECHO_PENDIENTE:
            raise PendienteD6("S20", "D6_ATRIBUCION_GASTO_REEMBOLSADO", d["id"])
        if rol == "cobro":
            if co != "public.ingresos" or (naturaleza is not None and naturaleza not in NATURALEZA_REEMBOLSO):
                raise ErrorP5("S1_COBRO_DE_DERECHO_NO_REEMBOLSO", f"{co}/{cl}")
            h = _H(ds, co, cl, "REEMBOLSO", fecha, nombre, imp, False, notas)
            ef = h.efecto("derecho_cobro", "DERECHO_COBRO", -imp, None, [(S, -imp, "MANUAL")], "COMPLETA")
            h.entidad(did, "AFECTA_A", ef, rol="derecho")
            gen = tuple(d["genera"]) if d["genera"] else None
            if gen is not None and gen in ids:
                h.relacion(ids[gen], "REEMBOLSO_DE", imp)
            elif gen is not None and gen in pendientes_d6:
                raise PendienteD6("S20", "D6_GENERADOR_PENDIENTE", f"{gen[0]}/{gen[1]}")
            elif gen is not None and gen in filas_d6:
                raise ErrorP5("S8_GENERADOR_NO_CREADO", f"{co}/{cl}")
            return "REEMBOLSO", _base(h)
        sub = ds.filas["derechos_obligaciones_financieras"][did]
        contraparte = sub["contraparte_actor_id"]
        if d["id"] in GENERACION_PURA:  # adelanto puro sin gasto propio
            h = _H(ds, co, cl, "GENERACION_DERECHO_OBLIGACION", fecha, nombre, tot, False, notas)
            ef = h.efecto("derecho_cobro", "DERECHO_COBRO", tot, None, [(S, tot, "MANUAL")], "COMPLETA")
            h.entidad(did, "AFECTA_A", ef, rol="derecho")
            return "GENERACION_DERECHO_OBLIGACION", _base(h)
        importe_derecho = Decimal(str(sub["importe_original_documentado"]))
        if d["id"] in ATRIBUCION_COMPARTIDA:
            if not 0 < importe_derecho < tot:
                raise ErrorP5("S9_PARTE_COMPARTIDA_INCOHERENTE", d["id"])
            atr = [(S, tot - importe_derecho, "MANUAL")] + ([(contraparte, importe_derecho, "MANUAL")] if contraparte else [])
            estado = "COMPLETA" if contraparte else "PARCIAL"
            ds.ledger.append({"regla": "D6-Z", "origen": f"{co}/{cl}", "derecho": d["id"]})
        else:
            if d["id"] not in ATRIBUCION_CONTRAPARTE_100 or contraparte is None:
                raise PendienteD6("S20", "D6_ATRIBUCION_GASTO_REEMBOLSADO", d["id"])
            if importe_derecho != tot:
                raise ErrorP5("S9_REPERCUSION_NO_TOTAL", d["id"])
            atr, estado = [(contraparte, tot, "MANUAL")], "COMPLETA"
        h = _H(ds, co, cl, "GASTO", fecha, nombre, tot, _presup(ds, cat, "GASTO"), notas)
        h.efecto("gasto", "GASTO", tot, cat, atr, estado)
        ef = h.efecto("derecho_cobro", "DERECHO_COBRO", importe_derecho, None,
                      [(S, importe_derecho, "MANUAL")], "COMPLETA")
        h.entidad(did, "AFECTA_A", ef, rol="derecho")
        return "GASTO", _base(h)
    # 3) devoluciones (OP-13)
    if o in DEVOLUCION_DECIDIDA:
        orig = DEVOLUCION_DECIDIDA[o]
        cat_d = cat
        h = _H(ds, co, cl, "GASTO", fecha, nombre, imp, False, notas)
        if orig is not None:
            if orig not in ids:
                raise ErrorP5("S8_ORIGEN_DEVOLUCION_NO_CREADO", f"{co}/{cl}")
            fo = fuente[orig[0]][orig[1]]
            r = clasificar(ds, orig[0], orig[1], fo)
            cat_d = r[1] if r[0] == "CAT" else None
            cap = sum(-Decimal(e["importe_delta"]) for e in ds.filas["hecho_efectos"].values()
                      if e["hecho_id"] == ids[orig] and e["tipo_efecto"] == "GASTO")
            if imp > -cap:
                raise ErrorP5("S9_DEVOLUCION_EXCEDE_ORIGEN", f"{co}/{cl}")
            h.relacion(ids[orig], "DEVOLUCION_DE", imp)
        h.fila["presupuestable"] = _presup(ds, cat_d, "GASTO")
        h.efecto("gasto", "GASTO", -imp, cat_d, [(S, -imp, "MANUAL")], "COMPLETA")
        return "GASTO", _base(h)
    # 4) viviendas sin participacion 100 % self: atribucion pendiente de decision
    if viv and modo_viv is None and not _participacion_entidad_self_100(ds, viv):
        raise PendienteD6("S20", "D6_ATRIBUCION_ENTIDAD_COMPARTIDA", viv)
    # 5) ingresos
    if co == "public.ingresos" and o not in GASTO_CORREGIDO_V3:
        if naturaleza is not None or cat is None:
            raise ErrorP5("S4_INGRESO_SIN_DISPOSICION", f"{co}/{cl} {naturaleza}")
        h = _H(ds, co, cl, "INGRESO", fecha, nombre, imp, _presup(ds, cat, "INGRESO"), notas)
        h.efecto("ingreso", "INGRESO", imp, cat, [(S, imp, "MANUAL")], "COMPLETA")
        return "INGRESO", _base(h)
    # 6) gastos
    if naturaleza is not None:
        if not naturaleza.startswith(PREFIJO_INTERES):
            raise ErrorP5("S4_GASTO_FUERA_SIN_DISPOSICION", f"{co}/{cl} {naturaleza}")
        cat = _cat_por_ruta(ds, _norm(naturaleza[len(PREFIJO_INTERES):].rstrip(")")))
    part = _dec_c(co, "cantidad", f, ctx) if co == "public.gastos_cotidianos" else None
    h = _H(ds, co, cl, "GASTO", fecha, nombre, tot, _presup(ds, cat, "GASTO"), notas,
           int(part) if part is not None else None)
    rep = _reparto(tot)
    if rep is not None and imp != tot:
        raise PendienteD6("S20", "D6_REPARTO_VIVIENDA_CON_PARTE_PERSONAL", f"{imp} / {tot}")
    if rep is not None:
        h.efecto("gasto", "GASTO", tot, cat, rep, "COMPLETA")
        ds.ledger.append({"regla": "D6-V", "origen": f"{co}/{cl}", "modo": modo_viv})
        return "GASTO", _base(h)
    h.efecto("gasto", "GASTO", tot, cat, [(S, imp, "MANUAL")], "COMPLETA" if imp == tot else "PARCIAL")
    return "GASTO", _base(h)


# ------------------------------------------------------------ dominio 7 (tesoreria)
# public.movimientos_cuenta V3 -> ledger legacy anterior al corte (DB Schema §40: se conserva y NO computa en el
# saldo, que abre en fecha_inicio_ledger con saldo_apertura del dominio 3). DV-7: misma cuenta = ajuste manual.
DOMINIO_7_ACTIVO = True
MOVIMIENTOS_V3 = "public.movimientos_cuenta"

LEDGER_REGLAS.update({
    "D7-A": "transferencia V3 entre cuentas distintas -> hecho TRANSFERENCIA neutro (sin efectos) + movimiento de salida "
            "(-importe) y de entrada (+importe) OPERACION + transferencias + dos conciliaciones por el importe firmado "
            "de cada pata (F04-D001).",
    "D7-B": "movimiento V3 con origen = destino -> un unico movimiento AJUSTE_SALDO, sin hecho ni transferencia "
            "(DV-7, INV-RV3-10); importe = saldo_despues - saldo_antes (RUN01), comprobado contra el importe V3.",
    "D7-C": "fecha_movimiento = fecha V3; confirmado_at = createdon V3 (registro/confirmacion del usuario en V3; sin "
            "hora fabricada); descripcion = comentarios.",
    "D7-D": "todo movimiento V3 es anterior a fecha_inicio_ledger de su cuenta: legacy que no computa en el saldo de "
            "apertura (DB Schema §40). Un movimiento en o tras el inicio del ledger se contaria dos veces -> S9.",
})


def _cuenta_v3(ds: Dataset, clave: str, origen: str) -> dict:
    cid = fu.uuid_v3("public.cuentas_bancarias", clave, "cuentas", "cuenta")
    c = ds.filas["cuentas"].get(cid)
    if c is None:
        raise ErrorP5("S8_HUERFANO", f"{origen} cuenta {clave}")
    return c


def dominio_7_tesoreria(ds: Dataset, fuente: dict, ctx: dict) -> dict:
    co = MOVIMIENTOS_V3
    n_tr = n_aj = 0
    for cl in sorted(fuente.get(co, {})):
        f = fuente[co][cl]
        g = lambda col: _celda(co, col, f, ctx)
        org, dst = _texto(g("cuenta_origen_id")), _texto(g("cuenta_destino_id"))
        fecha, creado, imp = g("fecha"), g("createdon"), _dec_c(co, "importe", f, ctx)
        if fecha.estado != fu.CONOCIDO or creado.estado != fu.CONOCIDO or imp is None or not org or not dst:
            raise ErrorP5("S6_MOVIMIENTO_INCOMPLETO", f"{co}/{cl}")
        fecha = str(fecha.valor)[:10]
        confirmado = str(creado.valor)
        desc = _texto(g("comentarios"))
        corig = _cuenta_v3(ds, org, f"{co}/{cl}")
        for c in (corig, _cuenta_v3(ds, dst, f"{co}/{cl}")):
            if c["fecha_inicio_ledger"] is None or fecha >= c["fecha_inicio_ledger"]:
                raise ErrorP5("S9_MOVIMIENTO_DENTRO_DEL_LEDGER", f"{co}/{cl}")  # computaria dos veces

        def mov(rol, cuenta, importe, clase):
            mid = fu.uuid_v3(co, cl, "movimientos_tesoreria", rol)
            ds.add("movimientos_tesoreria", {
                "id": mid, "cuenta_id": cuenta["id"], "fecha_movimiento": fecha, "importe": importe,
                "descripcion": desc, "confirmado_at": confirmado, "clase_movimiento": clase, "estado": "ACTIVO",
                "anulado_at": None, "motivo_anulacion": None, "reversion_de_movimiento_id": None})
            ds.mapear(co, cl, "movimientos_tesoreria", mid, rol, tipo="DIVIDIDO" if clase == "OPERACION" else "CREADO")
            return mid
        if org == dst:  # DV-7: ajuste manual de liquidez
            antes, despues = _dec_c(co, "saldo_origen_antes", f, ctx), _dec_c(co, "saldo_origen_despues", f, ctx)
            if antes is None or despues is None:
                raise ErrorP5("S6_AJUSTE_SIN_SALDOS", f"{co}/{cl}")
            delta = despues - antes
            if delta == 0 or abs(delta) != imp:
                raise ErrorP5("S9_AJUSTE_INCOHERENTE", f"{co}/{cl}")
            mov("ajuste", corig, delta, "AJUSTE_SALDO")
            n_aj += 1
            continue
        if imp <= 0:
            raise ErrorP5("S9_TRANSFERENCIA_IMPORTE", f"{co}/{cl}")
        cdst = _cuenta_v3(ds, dst, f"{co}/{cl}")
        if corig["moneda"] != cdst["moneda"]:
            raise ErrorP5("S20_TRANSFERENCIA_MULTIDIVISA", f"{co}/{cl}")
        ms, me = mov("salida", corig, -imp, "OPERACION"), mov("entrada", cdst, imp, "OPERACION")
        tid = fu.uuid_v3(co, cl, "transferencias", "transferencia")
        ds.add("transferencias", {"id": tid, "movimiento_salida_id": ms, "movimiento_entrada_id": me, "notas": None})
        ds.mapear(co, cl, "transferencias", tid, "transferencia", tipo="DIVIDIDO")
        h = _H(ds, co, cl, "TRANSFERENCIA", fecha, None, imp, False, desc)
        h.fila["moneda"] = corig["moneda"]
        for rol, mid, x in (("conciliacion.salida", ms, -imp), ("conciliacion.entrada", me, imp)):
            h.hijos.append(("hecho_movimientos_tesoreria", {
                "id": fu.uuid_v3(co, cl, "hecho_movimientos_tesoreria", rol), "hecho_id": h.id,
                "movimiento_tesoreria_id": mid, "importe_asignado": x}, rol))
        h.confirmar()
        n_tr += 1
    ds.ledger.append({"regla": "D7-A", "origen": co, "transferencias": n_tr})
    ds.ledger.append({"regla": "D7-B", "origen": co, "ajustes": n_aj})
    return {"transferencias": n_tr, "ajustes": n_aj, "movimientos": 2 * n_tr + n_aj}


# ------------------------------------------------------------ dominio 11 (cierres legacy y presupuestos)
# 13 cierres V3 -> snapshots IMPORTADO_LEGACY / CAJA / V3_SNAPSHOT sin recalcular (INV-RV3-08, D-MIG-015, DB Schema
# §61). Cabecera y detalle se conservan como cierre_metricas con un bundle LEGACY_V3_* de metricas_definicion
# (DB Schema: "Legacy V3 puede aportar bundles especificos LEGACY_V3_*"), deshabilitado para cierres nuevos.
DOMINIO_11_ACTIVO = True
CIERRES_V3, DETALLE_V3 = "public.cierre_mensual", "public.cierre_mensual_detalle"
CONT_LEGACY_METRICAS = "LEGACY_V3"
CABECERA_NO_METRICA = {"anio", "mes", "id", "user_id", "fecha_cierre", "criterio"}
DETALLE_METRICAS = {"esperado": "MONEDA", "real": "MONEDA", "desviacion": "MONEDA", "cumplimiento_pct": "NUMERO",
                    "incluye_kpi": "TEXTO"}
# Migration V3 §11: el rediseno de diciembre 2025 introduce liquidez, contadores y desglose; antes esos campos
# valen 0 por inexistencia del modulo, no por valor real (INV-RV3-04).
REDISENO_CIERRES = (2025, 12)
CAMPOS_REDISENO = {"liquidez_total", "n_cotidianos", "n_recurrentes_gas", "n_recurrentes_ing", "n_unicos_gas",
                   "n_unicos_ing", "gastos_cotidianos_esperados", "gastos_cotidianos_reales",
                   "gastos_gestionables_esperados", "gastos_gestionables_reales", "desv_cotidianos",
                   "desv_gestionables"}
# G-V3-03 (respuesta del propietario 2026-09-21): importe_cuota = presupuesto mensual; importe = restante que V3
# iba restando y reescribia al reiniciar el mes (V3 no conserva presupuestos anteriores). Se crea un unico
# presupuesto ACTIVO para el mes del corte; no se inventan meses anteriores.
PRESUPUESTO_CONTENEDORES_DECIDIDO = True

LEDGER_REGLAS.update({
    "D11-A": "cierre V3 -> cierres_mensuales: periodo = mes natural (anio, mes); cerrado_at = fecha_cierre V3 (timestamp "
             "sin zona de la BD V3, interpretado en UTC como la baseline); criterio V3 literal; IMPORTADO_LEGACY; "
             "metodologia V3_SNAPSHOT; CERRADO version 1.",
    "D11-B": "cada campo numerico de la cabecera V3 -> cierre_metricas con metrica LEGACY_V3_<CAMPO> (valor V3 tal cual, sin "
             "recalculo; las discrepancias cabecera/detalle se conservan). Desconocido -> sin fila, nunca cero.",
    "D11-G": "cierres anteriores al rediseno de diciembre 2025: los campos que aun no existian (liquidez, contadores y "
             "desglose cotidianos/gestionables) valen 0 por ausencia del modulo -> sin metrica (desconocido, INV-RV3-04); "
             "literal en origen. Un valor no nulo en esos campos antes del rediseno contradice el canon -> S9.",
    "D11-C": "detalle V3 -> cierre_metricas del cierre padre con metricas LEGACY_V3_DETALLE_* y clave_desglose = "
             "tipo_detalle/segmento_id; incluye_kpi como texto.",
    "D11-D": "metricas LEGACY_V3_* se crean deshabilitadas (enabled=false: no disponibles para cierres 2027) y se trazan a "
             "cada cierre V3 que las usa.",
    "D11-E": "sin cierre_saldos_cuenta / cierre_presupuesto_lineas / cierre_posiciones_entidad: V3 no conserva esos "
             "snapshots y no se reconstruyen desde el estado posterior (INV-RV3-08).",
    "D11-F": "contenedores G-V3-03 -> un presupuesto ACTIVO del mes del corte (version 1, moneda EUR, perspectiva "
             "ATRIBUIBLE: V3 consumia la parte personal, Migration V3 §18) con una BOLSA de GASTO por contenedor; "
             "importe_objetivo = importe_cuota V3 (presupuesto mensual, metodo MANUAL); alcance = categoria del "
             "contenedor con descendientes. El restante V3 (importe) no se persiste: se deriva de los hechos. Meses "
             "anteriores no existen en V3 y no se inventan.",
    "D11-I": "carga fisica del presupuesto: INSERT en BORRADOR, lineas y alcances, y transicion a ACTIVO en la misma "
             "transaccion (guarda de congelacion de 0330); el dataset refleja el estado final.",
    "D11-H": "contenedor sin categoria unica (clasificacion NULL decidida): linea sin alcance; conserva el objetivo pero no "
             "captura efectos hasta que se le asigne alcance.",
})


def _metrica_legacy(ds: Dataset, codigo: str, unidad: str) -> str:
    mid = fu.uuid_v3(CONT_LEGACY_METRICAS, codigo, "metricas_definicion", "metrica")
    ds.add("metricas_definicion", {"id": mid, "codigo": codigo, "nombre": f"Legacy V3: {codigo[10:].lower()}",
                                   "tipo_valor": "TEXT" if unidad == "TEXTO" else "NUMERIC", "unidad": unidad,
                                   "enabled": False}, natural=(codigo,))
    return mid


def _valor_metrica(c, unidad):
    if c.estado != fu.CONOCIDO or c.valor is None:
        return None
    if unidad == "TEXTO":
        return {"valor_numeric": None, "valor_text": str(c.valor).lower() if isinstance(c.valor, bool) else str(c.valor)}
    return {"valor_numeric": Decimal(str(c.valor)), "valor_text": None}


def dominio_11_cierres(ds: Dataset, fuente: dict, ctx: dict) -> dict:
    import calendar
    ids, n_met = {}, 0
    for cl in sorted(fuente.get(CIERRES_V3, {})):
        co, f = CIERRES_V3, fuente[CIERRES_V3][cl]
        anio, mes = _int(_celda(co, "anio", f, ctx)), _int(_celda(co, "mes", f, ctx))
        fc, crit = _celda(co, "fecha_cierre", f, ctx), _texto(_celda(co, "criterio", f, ctx))
        if anio is None or mes is None or fc.estado != fu.CONOCIDO or crit is None:
            raise ErrorP5("S6_CIERRE_INCOMPLETO", f"{co}/{cl}")
        cid = fu.uuid_v3(co, cl, "cierres_mensuales", "cierre")
        ds.add("cierres_mensuales", {
            "id": cid, "owner_user_id": ds.owner, "periodo_desde": f"{anio:04d}-{mes:02d}-01",
            "periodo_hasta": f"{anio:04d}-{mes:02d}-{calendar.monthrange(anio, mes)[1]:02d}",
            "cerrado_at": str(fc.valor) if "+" in str(fc.valor)[10:] else f"{fc.valor}+00:00",
            "criterio": crit, "origen_cierre": "IMPORTADO_LEGACY", "metodologia_version": "V3_SNAPSHOT",
            "estado": "CERRADO", "version_cierre": 1, "reemplaza_cierre_id": None, "reabierto_at": None,
            "motivo_reapertura": None, "notas": None}, natural=(ds.owner, anio, mes))
        ds.mapear(co, cl, "cierres_mensuales", cid, "cierre")
        ids[cl] = (cid, anio, mes)
        for campo in sorted(k for k in f if k not in CABECERA_NO_METRICA):
            unidad = "NUMERO" if campo.startswith("n_") else "MONEDA"
            v = _valor_metrica(_celda(co, campo, f, ctx), unidad)
            if v is None:
                continue
            if (anio, mes) < REDISENO_CIERRES and campo in CAMPOS_REDISENO:
                if v["valor_numeric"] != 0:
                    raise ErrorP5("S9_CAMPO_PREVIO_AL_REDISENO", f"{co}/{cl} {campo}")
                ds.ledger.append({"regla": "D11-G", "origen": f"{co}/{cl}", "campo": campo})
                continue
            codigo = f"LEGACY_V3_{campo.upper()}"
            met = _metrica_legacy(ds, codigo, unidad)
            ds.mapear(co, cl, "metricas_definicion", met, f"metrica.{codigo}", tipo="VINCULADO")
            rid = fu.uuid_v3(co, cl, "cierre_metricas", codigo)
            ds.add("cierre_metricas", {"id": rid, "cierre_id": cid, "metrica_id": met, "clave_desglose": None,
                                       "dimensiones_snapshot": None, **v})
            ds.mapear(co, cl, "cierre_metricas", rid, codigo, tipo="DIVIDIDO")
            n_met += 1
    n_det = 0
    for cl in sorted(fuente.get(DETALLE_V3, {})):
        co, f = DETALLE_V3, fuente[DETALLE_V3][cl]
        padre = _texto(_celda(co, "cierre_id", f, ctx))
        if padre not in ids:
            raise ErrorP5("S8_DETALLE_SIN_CIERRE", f"{co}/{cl}")
        cid, anio, mes = ids[padre]
        if (_int(_celda(co, "anio", f, ctx)), _int(_celda(co, "mes", f, ctx))) != (anio, mes):
            raise ErrorP5("S9_DETALLE_PERIODO_DISTINTO", f"{co}/{cl}")
        tipo, seg = _texto(_celda(co, "tipo_detalle", f, ctx)), _texto(_celda(co, "segmento_id", f, ctx))
        if not tipo or not seg:
            raise ErrorP5("S6_DETALLE_SIN_CLAVE", f"{co}/{cl}")
        for campo, unidad in sorted(DETALLE_METRICAS.items()):
            v = _valor_metrica(_celda(co, campo, f, ctx), unidad)
            if v is None:
                continue
            codigo = f"LEGACY_V3_DETALLE_{campo.upper()}"
            met = _metrica_legacy(ds, codigo, unidad)
            ds.mapear(co, cl, "metricas_definicion", met, f"metrica.{codigo}", tipo="VINCULADO")
            rid = fu.uuid_v3(co, cl, "cierre_metricas", codigo)
            ds.add("cierre_metricas", {"id": rid, "cierre_id": cid, "metrica_id": met,
                                       "clave_desglose": f"{tipo}/{seg}", "dimensiones_snapshot": None, **v})
            ds.mapear(co, cl, "cierre_metricas", rid, codigo, tipo="DIVIDIDO")
            n_det += 1
    pres = _presupuesto_contenedores(ds, fuente, ctx) if PRESUPUESTO_CONTENEDORES_DECIDIDO else {}
    pend = []
    if not PRESUPUESTO_CONTENEDORES_DECIDIDO:
        for k in sorted(CONTENEDORES_PRESUPUESTARIOS):
            if k in fuente.get("public.gastos", {}):
                ds.pendientes.append({"dominio": 11, "origen": f"public.gastos/{k}", "clase": "S20",
                                      "codigo": "D11_PRESUPUESTO_SEMANTICA_NO_FIABLE", "detalle": "Migration V3 §4"})
                pend.append(k)
    return {"cierres": len(ids), "metricas_cabecera": n_met, "metricas_detalle": n_det,
            "definiciones_legacy": sum(1 for m in ds.filas["metricas_definicion"].values()
                                       if m["codigo"].startswith("LEGACY_V3_")),
            "presupuestos_pendientes": pend, "presupuesto": pres}


def _presupuesto_contenedores(ds: Dataset, fuente: dict, ctx: dict) -> dict:
    import calendar
    co = "public.gastos"
    claves = sorted(k for k in CONTENEDORES_PRESUPUESTARIOS if k in fuente.get(co, {}))
    if not claves:
        return {}
    anio, mes = int(FECHA_INICIO_LEDGER[:4]), int(FECHA_INICIO_LEDGER[5:7])
    desde = f"{anio:04d}-{mes:02d}-01"
    hasta = f"{anio:04d}-{mes:02d}-{calendar.monthrange(anio, mes)[1]:02d}"
    pid = fu.uuid_v3("RV3_PRESUPUESTO", desde, "presupuestos", "presupuesto")
    ds.add("presupuestos", {"id": pid, "owner_user_id": ds.owner, "periodo_desde": desde, "periodo_hasta": hasta,
                            "moneda": MONEDA_V3, "perspectiva": "ATRIBUIBLE", "version_presupuesto": 1,
                            "reemplaza_presupuesto_id": None, "estado": "ACTIVO", "generado_desde_cierre_id": None},
           natural=(ds.owner, desde, hasta))
    lineas, sin_alcance = 0, []
    for cl in claves:
        f = fuente[co][cl]
        obj = _dec_c(co, "importe_cuota", f, ctx)
        if obj is None or obj < 0:
            raise ErrorP5("S6_PRESUPUESTO_SIN_OBJETIVO", f"{co}/{cl}")
        ds.mapear(co, cl, "presupuestos", pid, "presupuesto", tipo="FUSIONADO")
        lid = fu.uuid_v3(co, cl, "presupuesto_lineas", "linea")
        ds.add("presupuesto_lineas", {"id": lid, "presupuesto_id": pid, "nombre": _texto(_celda(co, "nombre", f, ctx)),
                                      "tipo_linea": "BOLSA", "naturaleza_economica": "GASTO", "prioridad_consumo": None,
                                      "importe_base_calculado": None, "importe_objetivo": obj,
                                      "metodo_estimacion": "MANUAL", "meses_historico": None, "notas": None})
        ds.mapear(co, cl, "presupuesto_lineas", lid, "linea", tipo="DIVIDIDO")
        lineas += 1
        r = clasificar(ds, co, cl, f)
        if r[0] == "CAT":
            aid = fu.uuid_v3(co, cl, "presupuesto_linea_alcances", "alcance")
            ds.add("presupuesto_linea_alcances", {"id": aid, "presupuesto_linea_id": lid, "categoria_id": r[1],
                                                  "entidad_id": None, "incluir_descendientes": True})
            ds.mapear(co, cl, "presupuesto_linea_alcances", aid, "alcance", tipo="DIVIDIDO")
        elif r[0] == "NULL":
            sin_alcance.append(cl)
            ds.ledger.append({"regla": "D11-H", "origen": f"{co}/{cl}"})
        else:
            raise ErrorP5("S4_CONTENEDOR_NO_ES_GASTO", f"{co}/{cl} {r}")
        ds.ledger.append({"regla": "D11-F", "origen": f"{co}/{cl}"})
    return {"periodo": [desde, hasta], "lineas": lineas, "sin_alcance": sin_alcance}


# ------------------------------------------------------------ dominio 12: disposicion (R05)
DOMINIO_12_DISPOSICION_ACTIVO = True
# D-MIG-001: rama/segmento/tipo V3 se eliminan conceptualmente; los maestros 2027 usan ruta semantica propia
# (MV3 §24) y el tipo no se proyecta a categoria (MV3 §14): el registro no tiene destino. El canon no define
# la diferencia OBSOLETO/IGNORADO (DB Schema §77); RUN06 uso IGNORADO. Propuesta OBSOLETO pendiente (S20).
TAXONOMIA_V3_REEMPLAZADA = ("public.tipo_gasto", "public.tipo_ingreso", "public.tipo_ramas_gasto",
                            "public.tipo_ramas_ingreso", "public.tipo_segmentos_gasto")
DISPOSICION_TAXONOMIA_V3 = "OBSOLETO"
DISPOSICION_TAXONOMIA_ESTADO = "PROPUESTA"
# Respuesta D (2026-09-21): la cuota de prestamo no tiene regla; su expectativa es el calendario de la
# financiacion. El gasto V3 de referencia queda VINCULADO a esa financiacion (D5-T).
GASTO_REFERENCIA_CUOTA_VINCULADO = True
# Solo los efectos economicos llevan categoria (dominio 6); DEUDA/DERECHO_COBRO/... no la reciben.
EFECTOS_CATEGORIZABLES = ("GASTO", "INGRESO")


def dominio_12_disposicion(ds: Dataset, fuente: dict) -> None:
    """Disposicion explicita de los origenes que ningun dominio transforma (R05 / INV-RV3-02)."""
    tz = ds.trazabilidad
    tz.setdefault("contenedores_pendientes", [])
    # 1) gastos V3 de referencia de cuota de prestamo (D5-T)
    n_ref = 0
    if GASTO_REFERENCIA_CUOTA_VINCULADO:
        for e in ds.ledger:
            if e.get("regla") != "D5-T":
                continue
            co, cl = e["origen"].split("/", 1)
            pr = _texto(_val_d12(fuente, co, cl, "prestamo_id"))
            eid = fu.uuid_v3("public.prestamo", pr, "entidades", "financiacion")
            if eid not in ds.filas["financiaciones"]:
                raise ErrorP5("S8_HUERFANO", f"{co}/{cl} prestamo_id={pr}")
            ds.mapear(co, cl, "financiaciones", eid, "expectativa_cuota", tipo="VINCULADO",
                      notas="D5-T: expectativa de la cuota = calendario de la financiacion; sin regla propia")
            n_ref += 1
    tz["gastos_referencia_cuota_vinculados"] = n_ref
    # 2) taxonomia V3 reemplazada por el arbol 2027
    presentes = [c for c in TAXONOMIA_V3_REEMPLAZADA if c in fuente]
    filas = sum(len(fuente[c]) for c in presentes)
    ya = {m["registro_origen_id"] for m in ds.filas["mapeos_importacion"].values()}
    for c in presentes:
        for cl in fuente[c]:
            if fu.uuid_origen(c, cl) in ya:
                raise ErrorP5("S1_TAXONOMIA_V3_CON_DESTINO", f"{c}/{cl}")
    materializar = DISPOSICION_TAXONOMIA_ESTADO == "CONFIRMADA" or ds.modo_lab
    if filas and DISPOSICION_TAXONOMIA_ESTADO != "CONFIRMADA":
        ds.pendientes.append({"S20": "DISPOSICION_TAXONOMIA_V3", "estado": DISPOSICION_TAXONOMIA_ESTADO,
                              "propuesta": DISPOSICION_TAXONOMIA_V3, "alternativa": "IGNORADO (RUN06)",
                              "filas": filas, "bloquea_gate": True,
                              "efecto": "materializada solo en laboratorio" if ds.modo_lab
                              else "origenes sin disposicion hasta la decision"})
    if filas and materializar:
        for c in presentes:
            for cl in sorted(fuente[c]):
                ds.mapear(c, cl, None, None, "disposicion", tipo=DISPOSICION_TAXONOMIA_V3,
                          notas="D-MIG-001: taxonomia V3 reemplazada por el arbol de categorias 2027 (sin destino)")
    elif filas:
        tz["contenedores_pendientes"] = presentes
    tz["taxonomia_v3"] = {"filas": filas, "disposicion": DISPOSICION_TAXONOMIA_V3 if materializar else None,
                          "estado": DISPOSICION_TAXONOMIA_ESTADO}
    # 3) decision de clasificacion: VINCULADA a cada destino donde se aplico, verificando que se aplico
    tz["clasificacion_vinculos"] = _vincular_clasificacion(ds) if ds.categorias else 0


def _val_d12(fuente, co, cl, col):
    return fu.normalizar(co, col, fuente[co][cl].get(col), fuente[co][cl], fu.contexto_de(fuente))


def _vincular_clasificacion(ds: Dataset) -> int:
    dec = ds.decisiones
    if dec is None or not dec.doc.get("clasificacion"):
        return 0
    clave_dec = f"clasificacion/{dec.doc['clasificacion']['id']}"
    por_origen = {}
    for m in ds.filas["mapeos_importacion"].values():
        por_origen.setdefault(m["registro_origen_id"], []).append(m)
    n = 0
    for clave, v in sorted(dec.doc["clasificacion"]["registros"].items()):
        co, cl = clave.split("/", 1)
        if v is None:
            esperadas = {None}
        elif isinstance(v, dict) and "desglose" in v:
            esperadas = {_cat_por_ruta(ds, r) for r, _x in v["desglose"]}
        else:
            esperadas = {_cat_por_ruta(ds, v)}
        for m in sorted(por_origen.get(fu.uuid_origen(co, cl), []), key=lambda x: x["id"]):
            t, did = m["tabla_destino"], m["registro_destino_id"]
            if t == "hecho_efectos":
                f = ds.filas[t][did]
                if f["tipo_efecto"] not in EFECTOS_CATEGORIZABLES:
                    continue
            elif t != "regla_versiones":
                continue
            f = ds.filas[t][did]
            if f["categoria_id"] not in esperadas:
                raise ErrorP5("S9_CLASIFICACION_NO_APLICADA", f"{clave} -> {t}/{did}")
            ds.mapear(CONT_DECISIONES, clave_dec, t, did, f"clasificacion.{did}", tipo="VINCULADO",
                      confianza="VALIDADA", notas=f"categoria decidida para {clave}")
            n += 1
    return n


def transformar(b0: dict, sha_run06: str, modo_lab: bool = False,
                decisiones: "Decisiones | None" = None) -> Dataset:
    fuente = fu.fuente_b0(b0)
    ctx = fu.contexto_de(fuente)
    (cu,) = fuente["public.users"].keys()
    ds = Dataset(owner=owner_de(cu), modo_lab=modo_lab, decisiones=decisiones)
    dominio_12_trazabilidad(ds, b0, sha_run06)
    dominio_1(ds, fuente, ctx)
    dominio_2(ds, fuente, ctx)
    if CATEGORIAS_ACTIVAS:
        ds.categorias = dominio_2_categorias(ds)
    dominio_12_decisiones(ds)
    if "public.cuentas_bancarias" in fuente:
        dominio_3(ds, fuente, ctx, modo_lab)
    dominio_4_propiedades(ds, fuente, ctx, modo_lab)
    dominio_8_financiaciones(ds, fuente, ctx, modo_lab)
    if DERECHOS_V3:
        dominio_8b_derechos(ds, fuente, ctx)
    dominio_9_inversiones(ds, fuente, ctx)
    dominio_10_contratos(ds, fuente, ctx)
    ds.clasificacion = verificar_clasificacion(ds, fuente)
    if DOMINIO_5_ACTIVO:
        ds.reglas = dominio_5_reglas(ds, fuente, ctx)
        if DOMINIO_6_ACTIVO:
            ds.hechos = dominio_6_hechos(ds, fuente, ctx)
            if DOMINIO_7_ACTIVO and MOVIMIENTOS_V3 in fuente:
                ds.tesoreria = dominio_7_tesoreria(ds, fuente, ctx)
    if DOMINIO_11_ACTIVO and CIERRES_V3 in fuente:
        ds.cierres = dominio_11_cierres(ds, fuente, ctx)
    if DOMINIO_12_DISPOSICION_ACTIVO:
        dominio_12_disposicion(ds, fuente)
    verificar_trazabilidad(ds)
    return ds


def verificar_trazabilidad(ds: Dataset) -> None:
    """R05: todo destino creado tiene mapeo; todo mapeo apunta a origen y destino existentes (R-RV3-002:
    referencia polimorfica sin FK, validada aqui); con el dominio 12 completo, todo origen tiene disposicion."""
    origenes = set(ds.filas["registros_origen_importacion"])
    destinos_mapeados = {(m["tabla_destino"], m["registro_destino_id"])
                         for m in ds.filas["mapeos_importacion"].values()}
    for m in ds.filas["mapeos_importacion"].values():
        if m["registro_origen_id"] not in origenes:
            raise ErrorP5("S8_MAPEO_SIN_ORIGEN", m["id"])
        t = m["tabla_destino"]
        if t is not None and (t not in ds.filas or m["registro_destino_id"] not in ds.filas[t]):
            raise ErrorP5("S8_MAPEO_DESTINO_INEXISTENTE", f"{m['id']} -> {t}/{m['registro_destino_id']}")
    exentas = {"fuentes_importacion", "registros_origen_importacion", "mapeos_importacion"}
    for t in ORDEN_TABLAS:
        if t in exentas:
            continue
        for fid in ds.filas[t]:
            if (t, fid) not in destinos_mapeados:
                raise ErrorP5("S8_DESTINO_SIN_ORIGEN", f"{t}/{fid}")
    if not DOMINIO_12_DISPOSICION_ACTIVO:
        return
    con = {m["registro_origen_id"] for m in ds.filas["mapeos_importacion"].values()}
    ro = ds.filas["registros_origen_importacion"]
    sin = sorted(f"{ro[o]['contenedor_origen']}/{ro[o]['clave_origen']}" for o in origenes - con)
    en_decision = [k for k in sin if k.split("/", 1)[0] in ds.trazabilidad.get("contenedores_pendientes", ())]
    resto = [k for k in sin if k not in set(en_decision)]
    if resto:
        raise ErrorP5("S8_ORIGEN_SIN_DISPOSICION", f"{len(resto)}: {', '.join(resto[:5])}")
    ds.trazabilidad.update({"R05_origenes": len(origenes), "R05_con_disposicion": len(origenes) - len(sin),
                            "R05_sin_disposicion_pendiente_decision": len(en_decision),
                            "R05_destinos_sin_origen": 0, "R05_mapeos_destino_inexistente": 0})


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


# Ciclo de vida exigido por 0330 al cargar (no cambia el dataset): la fila se inserta en el estado inicial y,
# tras sus hijos, se transiciona al estado final (fn_guard_presupuesto_congelado: solo BORRADOR admite lineas).
TRANSICIONES_CARGA = {"presupuestos": ("estado", "BORRADOR")}


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
                    if t in TRANSICIONES_CARGA:
                        f = {**f, TRANSICIONES_CARGA[t][0]: TRANSICIONES_CARGA[t][1]}
                    cols = sorted(f)
                    vals = [Jsonb(f[k]) if isinstance(f[k], (dict, list)) else f[k] for k in cols]
                    c.execute(f"INSERT INTO gapto.{t} ({', '.join(cols)}) VALUES "
                              f"({', '.join(['%s'] * len(cols))})", vals)
            for t, (col, _ini) in TRANSICIONES_CARGA.items():
                for fid in orden_insercion(ds, t):
                    c.execute(f"UPDATE gapto.{t} SET {col} = %s WHERE id = %s", (ds.filas[t][fid][col], fid))
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
    ap.add_argument("--decisiones-propietario", default=None, type=Path,
                    help="JSON EXTERNO al repositorio (contiene PII) con decisiones S20 sin fila V3")
    a = ap.parse_args()
    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] [1/3] Carga B0", flush=True)
    b0 = fu.cargar_b0(a.run06)
    sha = fu.p1.sha256_fichero(a.run06)
    print(f"[{time.strftime('%H:%M:%S')}] [2/3] Transformacion P5 v{VERSION}", flush=True)
    dec = cargar_decisiones(a.decisiones_propietario) if a.decisiones_propietario else None
    ds = transformar(b0, sha, modo_lab=a.modo_lab, decisiones=dec)
    h = ds.hash()
    fisico = None
    if a.dsn_import:
        print(f"[{time.strftime('%H:%M:%S')}] [3/3] Validacion fisica RV3_IMPORT (ROLLBACK)", flush=True)
        fisico = validar_fisico(ds, a.dsn_import)
    informe = {"version": VERSION, "hash_dataset": h, "recuentos": ds.recuentos(),
               "ledger_reglas": LEDGER_REGLAS, "ledger": ds.ledger, "pendientes": ds.pendientes,
               "preguntas": ds.preguntas, "clasificacion": ds.clasificacion, "decisiones_sha256": dec.sha256 if dec else None,
               "fisico": fisico, "reglas": ds.reglas, "hechos": ds.hechos, "tesoreria": ds.tesoreria, "cierres": ds.cierres, "trazabilidad": ds.trazabilidad, "dominios": {"implementados": [1, "2-parcial", 3, "4-propiedad", 5, "6", 7, "11", "8-financiaciones", "8B-derechos", "9-inversiones", "10-contratos-valoraciones", "12-disposicion-R05"], "pendientes": ["12-reconciliacion-R01..R26", "P5b"], "modo_lab": a.modo_lab},
               "ts": datetime.now(timezone.utc).isoformat()}
    a.salida.mkdir(parents=True, exist_ok=True)
    p = a.salida / f"rv3_p5_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    p.write_text(json.dumps(informe, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"      hash_dataset={h}\n      recuentos={ds.recuentos()}\n      fisico={fisico}\n"
          f"      informe={p.name} ({time.time() - t0:.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
