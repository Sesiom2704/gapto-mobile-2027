# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_14p_f06_02_03_modelos_y_errores_puros.py
# Ruta: tests/backend/test_14p_f06_02_03_modelos_y_errores_puros.py
# Descripcion: F06-02/03 · piezas PURAS del bloque de contratos (contrato v1.1), SIN base de datos:
#     - familia de errores (§1.4): todos los codigos ★ con su HTTP y mensaje; los dos mensajes que ve Moisés
#       literales (RENTA_PENDIENTE_DE_F06_04 e INQUILINO_NO_PUEDE_SER_YO); motivo en el primer nivel;
#     - mapa fisico (§1.5, PC-CON-05): cada constraint del mapa EXISTE con ese nombre en las migrations (0010,
#       0050, 0070, 0080, 0100, 0351), el SQLSTATE y el codigo de cada fila, y la POLITICA DE EXCLUSION (una
#       constraint fuera del mapa no se traduce); C-31 cerrado (contrato v1.2): P0001 por la FIRMA de
#       gapto.fn_check_jerarquia_aciclica(), nunca por el texto localizable;
#     - validaciones de personas (D25, INQUILINO_NO_PUEDE_SER_YO, ROL_NO_ADMITIDO_PARA_YO, AGENCIA/ADMINISTRADOR
#       no cuentan para formalizar, principal solo en PROPIETARIO/GESTOR/INQUILINO);
#     - clausula (IPC con NULL, NINGUNA frente a «No lo sé», PORCENTAJE_FIJO exige %);
#     - tratamiento de servicios (M-9): INCLUIDO, REPERCUTIDO_FIJO (>0), POR_FACTURA (% NULL), NO_REPERCUTIDO;
#     - intervalos (inclusivos; fin abierto) y cobertura (INV-ALQ-07);
#     - derivaciones de lectura: situacion, `fin_previsto_vencido` y ocupacion con los oraculos O-1a y O-1b.
#   Es el unico fichero de este bloque que se puede ejecutar sin GAPTO_TEST_DATABASE_URL.
# Version: 0.1.0 (F06 T3-F06 Bloque 3, paso 3; escrito y ejecutable sin base)
# ============================================================

from __future__ import annotations

import datetime as dt
import pathlib
import sys
import uuid
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
if str(RAIZ / "backend") not in sys.path:
    sys.path.insert(0, str(RAIZ / "backend"))

from app.contratos import errores as e  # noqa: E402
from app.contratos import lecturas  # noqa: E402
from app.contratos import modelos as m  # noqa: E402

FECHA = dt.date


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# ================================================================== §1.4 familia de errores
CODIGOS_NUEVOS = (
    "HABITACION_REQUERIDA", "HABITACION_NO_ADMITIDA", "HABITACION_FUERA_DE_FICHA", "HABITACIONES_NO_INDICADAS",
    "SOLAPE_CON_CONTRATO_FIRMADO", "PROPIEDAD_FUERA_DE_PATRIMONIO", "FALTAN_PARTES_PARA_FORMALIZAR",
    "PRINCIPAL_REQUERIDO", "INQUILINO_NO_PUEDE_SER_YO", "ROL_NO_ADMITIDO_PARA_YO", "CONTRATO_SIN_INQUILINO",
    "CONTRATO_SIN_ARRENDADOR", "PRINCIPAL_DUPLICADO", "TRATAMIENTO_SOLAPADO", "SERVICIO_YA_VINCULADO",
    "CLAUSULA_SOLAPADA", "DESDE_IGUAL_A_VERSION_ABIERTA", "FECHA_FIN_ANTERIOR_A_VIGENCIA", "CONTRATO_NO_VIGENTE",
    "SUCESOR_SOLAPADO", "FECHA_INICIO_REQUERIDA", "CLAUSULA_INCOMPLETA", "SERVICIO_NO_VINCULADO_A_PROPIEDAD",
    "ACTOR_NO_ES_INQUILINO", "TRATAMIENTO_INCOMPATIBLE", "SERVICIO_DADO_DE_BAJA", "ROL_DESCONOCIDO",
    "CLASIFICACION_CICLO", "CLASIFICACION_NOMBRE_REPETIDO", "RETIRADA_NO_ADMITIDA", "RENTA_NO_DISPONIBLE",
)
HTTP_NUEVOS = {
    "HABITACION_REQUERIDA": 422, "HABITACION_NO_ADMITIDA": 422, "HABITACION_FUERA_DE_FICHA": 422,
    "HABITACIONES_NO_INDICADAS": 422, "SOLAPE_CON_CONTRATO_FIRMADO": 409, "PROPIEDAD_FUERA_DE_PATRIMONIO": 422,
    "FALTAN_PARTES_PARA_FORMALIZAR": 422, "PRINCIPAL_REQUERIDO": 422, "INQUILINO_NO_PUEDE_SER_YO": 422,
    "ROL_NO_ADMITIDO_PARA_YO": 422, "CONTRATO_SIN_INQUILINO": 409, "CONTRATO_SIN_ARRENDADOR": 409,
    "PRINCIPAL_DUPLICADO": 422, "TRATAMIENTO_SOLAPADO": 409, "SERVICIO_YA_VINCULADO": 409, "CLAUSULA_SOLAPADA": 409,
    "DESDE_IGUAL_A_VERSION_ABIERTA": 422, "FECHA_FIN_ANTERIOR_A_VIGENCIA": 422, "CONTRATO_NO_VIGENTE": 409,
    "SUCESOR_SOLAPADO": 422, "FECHA_INICIO_REQUERIDA": 422, "CLAUSULA_INCOMPLETA": 422,
    "SERVICIO_NO_VINCULADO_A_PROPIEDAD": 422, "ACTOR_NO_ES_INQUILINO": 422, "TRATAMIENTO_INCOMPATIBLE": 422,
    "SERVICIO_DADO_DE_BAJA": 409, "ROL_DESCONOCIDO": 422, "CLASIFICACION_CICLO": 422,
    "CLASIFICACION_NOMBRE_REPETIDO": 409, "RETIRADA_NO_ADMITIDA": 409, "RENTA_NO_DISPONIBLE": 422,
}


def test_los_31_codigos_nuevos_tienen_http_y_mensaje_propios():
    assert set(CODIGOS_NUEVOS) == set(HTTP_NUEVOS) and len(CODIGOS_NUEVOS) == 31
    for codigo in CODIGOS_NUEVOS:
        status, cuerpo = e.rechazo_http(codigo)
        assert status == HTTP_NUEVOS[codigo], codigo
        assert cuerpo["codigo"] == codigo and cuerpo["mensaje"].strip() and cuerpo["reintentable"] is False


def test_codigos_reutilizados_con_mensaje_propio_y_status_del_contrato():
    esperados = {"AGREGADO_NO_ENCONTRADO": 404, "VERSION_DESFASADA": 409,
                 "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION": 409, "TERCERO_NO_DISPONIBLE": 409,
                 "PARTICIPANTE_DUPLICADO": 422, "FECHA_ANTERIOR_INICIO": 422, "MOTIVO_AUSENTE": 422,
                 "CAMPO_INMUTABLE": 422, "OPERACION_NO_PERMITIDA_EN_ESTADO": 409, "HABITACIONES_EN_USO": 409}
    for codigo, status in esperados.items():
        assert e.rechazo_http(codigo)[0] == status, codigo
    # ningun mensaje habla de titularidad, reparto o prevision (los de las familias anteriores)
    for codigo in esperados:
        mensaje = e.rechazo_http(codigo)[1]["mensaje"].lower()
        assert not any(t in mensaje for t in ("titular", "reparto", "previs")), (codigo, mensaje)


def test_mensajes_literales_que_ve_moises():
    assert e.MENSAJE_RENTA_PENDIENTE == (
        "Este contrato tiene una renta registrada. Para terminarlo hay que cerrar también su renta, y eso llegará "
        "con la parte de cobros. De momento no se puede terminar.")
    assert e.rechazo_http("INQUILINO_NO_PUEDE_SER_YO")[1]["mensaje"] == "Tú no puedes ser inquilino de tu propio contrato."
    assert e.MENSAJE_REGLA_SERVICIO == (
        "Este servicio tiene un pago previsto registrado. Para darlo de baja hay que cerrar ese pago previsto, y eso "
        "llegará con la parte de cobros.")


def test_motivo_sube_al_primer_nivel_y_cada_motivo_tiene_su_mensaje():
    status, cuerpo = e.rechazo_http("OPERACION_NO_PERMITIDA_EN_ESTADO", {"motivo": "RENTA_PENDIENTE_DE_F06_04"})
    assert status == 409 and cuerpo["motivo"] == "RENTA_PENDIENTE_DE_F06_04"
    assert cuerpo["mensaje"] == e.MENSAJE_RENTA_PENDIENTE and cuerpo["detalle"] == {"motivo": "RENTA_PENDIENTE_DE_F06_04"}
    status, cuerpo = e.rechazo_http("OPERACION_NO_PERMITIDA_EN_ESTADO", {"motivo": "REGLA_SERVICIO_PENDIENTE_DE_F06_04"})
    assert status == 409 and cuerpo["mensaje"] == e.MENSAJE_REGLA_SERVICIO
    # O-31: la baja de servicio NUNCA lleva el motivo de renta
    assert "RENTA_PENDIENTE" not in cuerpo["motivo"] and cuerpo["motivo"] != e.RENTA_PENDIENTE
    # sin motivo: mensaje generico, sin clave `motivo`
    assert "motivo" not in e.rechazo_http("OPERACION_NO_PERMITIDA_EN_ESTADO")[1]


def test_detalle_de_solape_se_conserva_con_la_lista_de_contratos():
    detalle = {"contratos": [{"id": "x", "nombre": "26-HAB2-AG"}]}
    cuerpo = e.rechazo_http("SOLAPE_CON_CONTRATO_FIRMADO", detalle)[1]
    assert cuerpo["detalle"] == detalle


# ================================================================== §1.5 mapa fisico
MIGRATIONS = RAIZ / "migrations"


def _migrations_texto() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(MIGRATIONS.glob("*.sql")))


def test_cada_constraint_del_mapa_existe_con_ese_nombre_exacto_en_las_migrations():
    texto = _migrations_texto()
    for nombre in e.MAPA_FISICO:
        assert nombre in texto, f"{nombre}: no existe en migrations/ (cita del contrato desactualizada)"


def test_el_mapa_cubre_las_filas_de_1_5_con_su_sqlstate_y_codigo():
    esperado = {
        "ex_contrato_participantes__contrato_actor_rol": ("23P01", "PARTICIPANTE_DUPLICADO"),
        "ex_contrato_participantes__principal_por_rol": ("23P01", "PRINCIPAL_DUPLICADO"),
        "ex_contrato_servicios__contrato_servicio": ("23P01", "TRATAMIENTO_SOLAPADO"),
        "ex_propiedad_servicios__propiedad_servicio": ("23P01", "SERVICIO_YA_VINCULADO"),
        "ex_contrato_revision_renta_versiones__contrato": ("23P01", "CLAUSULA_SOLAPADA"),
        "ck_contratos__habitacion": ("23514", "HABITACION_NO_ADMITIDA"),
        "ck_contrato_servicios__repercusion_coherente": ("23514", "TRATAMIENTO_INCOMPATIBLE"),
        "ck_contrato_participantes__rol": ("23514", "ROL_DESCONOCIDO"),
        "ck_tercero_roles__rol_codigo": ("23514", "ROL_DESCONOCIDO"),
        "ck_contrato_servicios__renta_repercutible_excl": ("23514", "TRATAMIENTO_INCOMPATIBLE"),
        "ck_contrato_servicios__porcentaje": ("23514", "TRATAMIENTO_INCOMPATIBLE"),
        "ck_contrato_revision_renta_versiones__porcentaje_fijo_exigido": ("23514", "CLAUSULA_INCOMPLETA"),
        "ck_contrato_revision_renta_versiones__ninguna_sin_parametros": ("23514", "CLAUSULA_INCOMPLETA"),
        "ck_contratos__fin_prevista_no_anterior": ("23514", "FECHA_ANTERIOR_INICIO"),
        "ck_contratos__fin_real_no_anterior": ("23514", "FECHA_ANTERIOR_INICIO"),
        "uq_clasificaciones_tercero__owner_parent_nombre": ("23505", "CLASIFICACION_NOMBRE_REPETIDO"),
    }
    assert e.MAPA_FISICO == esperado


def _exc(sqlstate: str, constraint: str | None = None, contexto: str | None = None):
    return SimpleNamespace(sqlstate=sqlstate, diag=SimpleNamespace(constraint_name=constraint, context=contexto))


@pytest.mark.parametrize("constraint,sqlstate_codigo", sorted(e.MAPA_FISICO.items()))
def test_traduccion_por_identidad_de_la_constraint(constraint, sqlstate_codigo):
    sqlstate, codigo = sqlstate_codigo
    assert e.traducir_fisico(_exc(sqlstate, constraint)) == codigo
    # el mismo nombre con OTRO sqlstate no se disfraza
    otro = "23514" if sqlstate != "23514" else "23P01"
    assert e.traducir_fisico(_exc(otro, constraint)) is None


def test_politica_de_exclusion_una_constraint_fuera_del_mapa_no_se_traduce():
    for fuera in ("ck_contrato_servicios__modo_reparto_dominio", "ck_contratos__formalizado_exige_inicio",
                  "ck_contrato_participantes__vigencia", "uq_tercero_roles__tercero_rol", "pk_contratos",
                  "constraint_inventada", None):
        assert e.traducir_fisico(_exc("23514", fuera)) is None
        assert e.traducir_fisico(_exc("23505", fuera)) is None
    # un P0001 de OTRO trigger tampoco
    assert e.traducir_fisico(_exc("P0001", None, "PL/pgSQL function gapto.fn_check_otra()")) is None


def test_c31_provisional_ciclo_de_clasificacion_por_firma_de_funcion_no_por_texto():
    contexto = "PL/pgSQL function gapto.fn_check_jerarquia_aciclica() line 12 at RAISE"
    assert e.traducir_fisico(_exc("P0001", None, contexto)) == "CLASIFICACION_CICLO"
    # en otra localizacion el prefijo del contexto cambia; la firma no
    assert e.traducir_fisico(_exc("P0001", None, "funcion PL/pgSQL gapto.fn_check_jerarquia_aciclica() linea 12")) \
        == "CLASIFICACION_CICLO"
    # la firma como parte de otra (fn_check_jerarquia_aciclica_extra()) no coincide
    assert e.traducir_fisico(_exc("P0001", None, "gapto.fn_check_jerarquia_aciclica_extra()")) is None
    # el texto del mensaje, solo, no basta
    assert e.traducir_fisico(_exc("P0001", None, "ciclo de jerarquia")) is None
    # con otro SQLSTATE la firma no se mira
    assert e.traducir_fisico(_exc("23514", None, contexto)) is None


# ================================================================== D25 y personas
def P(rol, *, principal=False, yo=False, tercero=None):
    return m.Persona(rol=rol, principal=principal, yo=yo, tercero_id=tercero if not yo else None)


def T():
    return _uuid()


def test_yo_nunca_es_inquilino_agencia_ni_administrador_pero_si_propietario_o_gestor():
    assert m.validar_yo([P("INQUILINO", yo=True)]).codigo == "INQUILINO_NO_PUEDE_SER_YO"
    assert m.validar_yo([P("AGENCIA", yo=True)]).codigo == "ROL_NO_ADMITIDO_PARA_YO"
    assert m.validar_yo([P("ADMINISTRADOR", yo=True)]).codigo == "ROL_NO_ADMITIDO_PARA_YO"
    assert m.validar_yo([P("PROPIETARIO", yo=True, principal=True), P("GESTOR", yo=True)]) is None
    # un tercero (p. ej. un socio) tambien puede ser GESTOR
    assert m.validar_yo([P("GESTOR", tercero=T())]) is None


def test_actor_repetido_en_el_mismo_rol():
    t = T()
    assert m.validar_personas_alta([P("INQUILINO", tercero=t), P("INQUILINO", tercero=t)],
                                   formalizado=False).codigo == "PARTICIPANTE_DUPLICADO"
    # el mismo tercero en roles distintos es legitimo
    assert m.validar_personas_alta([P("INQUILINO", tercero=t), P("AVALISTA", tercero=t)], formalizado=False) is None
    assert m.validar_personas_alta([P("FIADOR", tercero=t)], formalizado=False).codigo == "ROL_DESCONOCIDO"


def test_principal_solo_obligatorio_en_propietario_gestor_e_inquilino():
    a, i, ag = T(), T(), T()
    # AVALISTA, AGENCIA y ADMINISTRADOR sin principal: OK (O-24)
    base = [P("PROPIETARIO", yo=True, principal=True), P("INQUILINO", tercero=i, principal=True)]
    for rol in ("AVALISTA", "AGENCIA", "ADMINISTRADOR"):
        assert m.validar_principales(base + [P(rol, tercero=ag)], formalizado=True) is None, rol
    # INQUILINO sin principal -> PRINCIPAL_REQUERIDO
    assert m.validar_principales([P("PROPIETARIO", yo=True, principal=True), P("INQUILINO", tercero=i)],
                                 formalizado=True).codigo == "PRINCIPAL_REQUERIDO"
    # PROPIETARIO y GESTOR tambien
    assert m.validar_principales([P("PROPIETARIO", yo=True), P("INQUILINO", tercero=i, principal=True)],
                                 formalizado=True).codigo == "PRINCIPAL_REQUERIDO"
    assert m.validar_principales([P("GESTOR", tercero=a), P("INQUILINO", tercero=i, principal=True)],
                                 formalizado=True).codigo == "PRINCIPAL_REQUERIDO"
    # dos principales en AGENCIA -> rechazo (validacion previa; ademas la EXCLUDE)
    dos = base + [P("AGENCIA", tercero=T(), principal=True), P("AGENCIA", tercero=T(), principal=True)]
    assert m.validar_principales(dos, formalizado=True).codigo == "PRINCIPAL_DUPLICADO"


def test_agencia_y_administrador_nunca_cuentan_para_formalizar():
    i, ag, ad = T(), T(), T()
    solo_intermediarios = [P("AGENCIA", tercero=ag), P("ADMINISTRADOR", tercero=ad),
                           P("INQUILINO", tercero=i, principal=True)]
    assert m.validar_principales(solo_intermediarios, formalizado=True).codigo == "FALTAN_PARTES_PARA_FORMALIZAR"
    completo = solo_intermediarios + [P("PROPIETARIO", yo=True, principal=True)]
    assert m.validar_principales(completo, formalizado=True) is None
    # (PROPIETARIO o GESTOR) e INQUILINO principal; sin personas -> faltan partes
    assert m.validar_principales([], formalizado=True).codigo == "FALTAN_PARTES_PARA_FORMALIZAR"
    assert m.validar_principales([P("GESTOR", tercero=T(), principal=True), P("INQUILINO", tercero=i, principal=True)],
                                 formalizado=True) is None
    # un borrador no exige partes
    assert m.validar_principales([], formalizado=False) is None


# ================================================================== clausula (C-REV-01)
def test_clausula_ipc_con_parametros_desconocidos_queda_en_null():
    cols = m.validar_clausula(m.Clausula(tipo="IPC"))
    assert isinstance(cols, dict)
    assert cols["tipo_revision"] == "IPC" and cols["indice_referencia"] == "IPC INE"
    assert cols["periodicidad_meses"] is None and cols["fecha_primera_revision"] is None
    assert m.validar_clausula(m.Clausula(tipo="IPC", periodicidad_meses=12))["periodicidad_meses"] == 12


def test_clausula_ninguna_frente_a_no_lo_se_y_porcentaje_fijo():
    ninguna = m.validar_clausula(m.Clausula(tipo="NINGUNA"))
    assert ninguna["tipo_revision"] == "NINGUNA" and ninguna["indice_referencia"] is None  # fila NINGUNA, no «No lo sé»
    for con in (dict(periodicidad_meses=12), dict(indice_referencia="IPC INE"), dict(porcentaje_fijo=D("2")),
                dict(fecha_primera_revision=FECHA(2027, 1, 1))):
        assert m.validar_clausula(m.Clausula(tipo="NINGUNA", **con)).codigo == "CLAUSULA_INCOMPLETA", con
    assert m.validar_clausula(m.Clausula(tipo="PORCENTAJE_FIJO")).codigo == "CLAUSULA_INCOMPLETA"
    assert m.validar_clausula(m.Clausula(tipo="PORCENTAJE_FIJO", porcentaje_fijo=D("3.5")))["porcentaje_fijo"] == D("3.5")
    assert m.validar_clausula(m.Clausula(tipo="IPC", periodicidad_meses=0)).codigo == "ENTRADA_INVALIDA"
    assert m.validar_clausula(m.Clausula(tipo="LIBRE")).codigo == "ENTRADA_INVALIDA"
    for tipo in ("INDICE", "MANUAL", "OTRO"):      # otro indice o manual: parametros opcionales
        assert isinstance(m.validar_clausula(m.Clausula(tipo=tipo)), dict)


# ================================================================== tratamiento de servicios (M-9)
def test_tratamiento_modos_y_su_fila():
    actor = _uuid()
    inc = m.columnas_tratamiento("INCLUIDO", None, None)
    assert inc == {"incluido_en_renta": True, "repercutible": False, "modo_reparto": None,
                   "actor_repercusion_id": None, "porcentaje_repercutible": None}
    no = m.columnas_tratamiento("NO_REPERCUTIDO", None, None)
    assert no["incluido_en_renta"] is False and no["repercutible"] is False and no["modo_reparto"] is None
    fijo = m.columnas_tratamiento("REPERCUTIDO_FIJO", actor, D("50"))
    assert fijo["modo_reparto"] == "FIJO" and fijo["porcentaje_repercutible"] == D("50") and fijo["repercutible"]
    factura = m.columnas_tratamiento("POR_FACTURA", actor, None)
    assert factura["modo_reparto"] == "POR_FACTURA" and factura["porcentaje_repercutible"] is None


def test_tratamiento_incoherente_es_tratamiento_incompatible():
    actor = _uuid()
    for args in (("POR_FACTURA", actor, D("50")),            # POR_FACTURA con %
                 ("REPERCUTIDO_FIJO", actor, D("0")),        # el writer exige > 0 aunque el CHECK admita 0
                 ("REPERCUTIDO_FIJO", actor, None), ("REPERCUTIDO_FIJO", actor, D("100.0001")),
                 ("INCLUIDO", actor, None), ("INCLUIDO", None, D("10")), ("NO_REPERCUTIDO", actor, None)):
        assert m.columnas_tratamiento(*args).codigo == "TRATAMIENTO_INCOMPATIBLE", args
    assert m.columnas_tratamiento("REPERCUTIDO_FIJO", actor, D("100"))["porcentaje_repercutible"] == D("100")
    assert m.columnas_tratamiento("SIN_INDICAR", None, None).codigo == "ENTRADA_INVALIDA"   # no es una fila


# ================================================================== intervalos y cobertura
def test_intervalos_inclusivos_con_fin_abierto():
    d = FECHA
    assert m.intervalo_solapa(d(2026, 1, 1), d(2026, 1, 31), d(2026, 1, 31), None)          # mismo dia: solapa
    assert not m.intervalo_solapa(d(2026, 1, 1), d(2026, 1, 30), d(2026, 1, 31), None)
    assert m.intervalo_solapa(d(2026, 1, 1), None, d(2030, 1, 1), d(2030, 1, 2))            # sin fin
    assert not m.intervalo_solapa(d(2026, 1, 1), d(2026, 2, 1), d(2026, 2, 2), d(2026, 3, 1))


def test_cobertura_sin_huecos_inv_alq_07():
    d = FECHA
    assert m.cubre([(d(2026, 1, 1), None)], d(2026, 1, 1), None)
    assert not m.cubre([], d(2026, 1, 1), None)
    assert not m.cubre([(d(2026, 1, 1), d(2026, 3, 31))], d(2026, 1, 1), None)             # termina antes: hueco al final
    assert m.cubre([(d(2026, 1, 1), d(2026, 3, 31)), (d(2026, 4, 1), None)], d(2026, 1, 1), None)   # relevo contiguo
    assert not m.cubre([(d(2026, 1, 1), d(2026, 3, 30)), (d(2026, 4, 1), None)], d(2026, 1, 1), None)  # un dia sin nadie
    assert not m.cubre([(d(2026, 2, 1), None)], d(2026, 1, 1), None)                       # empieza tarde
    assert m.cubre([(d(2026, 1, 1), d(2026, 6, 30))], d(2026, 1, 1), d(2026, 6, 30))       # contrato ya terminado


# ================================================================== lecturas derivadas (sin columna)
def C(id_, tipo, hab, estado, inicio, fin_prevista=None, fin_real=None, regla=None, nombre="x"):
    return {"id": id_, "nombre": nombre, "tipo_contrato": tipo, "habitacion": hab, "estado_documental": estado,
            "fecha_inicio": inicio, "fecha_fin_prevista": fin_prevista, "fecha_fin_real": fin_real,
            "regla_renta_id": regla, "row_version": 1}


HOY = FECHA(2026, 11, 18)


def test_o_1a_fixture_independiente_de_ocupacion():
    """Piso de 4 habitaciones; hoy 2026-11-18: H1 y H2 ocupadas, H3 proxima, H4 (borrador) libre."""
    d = FECHA
    contratos = [
        C("1", "HABITACION", 1, "FORMALIZADO", d(2026, 9, 1)),
        C("2", "HABITACION", 2, "FORMALIZADO", d(2026, 3, 1), fin_prevista=d(2027, 8, 31)),
        C("3", "HABITACION", 3, "FORMALIZADO", d(2026, 12, 1)),
        C("4", "HABITACION", 4, "BORRADOR", d(2026, 11, 1)),
    ]
    por_hab = {o["habitacion"]: o["estado"] for o in lecturas.ocupacion(contratos, 4, HOY)}
    assert por_hab == {1: "OCUPADA", 2: "OCUPADA", 3: "PROXIMA", 4: "LIBRE"}
    assert sum(v == "OCUPADA" for v in por_hab.values()) == 2          # el borrador no ocupa


def test_o_1b_escenario_a1_validado_de_la_lamina_v08():
    d = FECHA
    contratos = [
        C("hab1", "HABITACION", 1, "FORMALIZADO", d(2026, 9, 1), nombre="26-HAB1-CR"),
        C("hab2", "HABITACION", 2, "FORMALIZADO", d(2026, 1, 1), fin_prevista=d(2027, 8, 31), nombre="26-HAB2-AG"),
        # 25-HAB5-LM: fin previsto 2026-10-31 y SIN fin real -> sigue ocupada y con la marca derivada
        C("hab5", "HABITACION", 5, "FORMALIZADO", d(2025, 11, 1), fin_prevista=d(2026, 10, 31), nombre="25-HAB5-LM"),
        C("hab3", "HABITACION", 3, "FORMALIZADO", d(2026, 12, 1), nombre="26-HAB3-PR"),
        C("hab4", "HABITACION", 4, "BORRADOR", d(2026, 11, 1), nombre="26-HAB4-ES"),
        C("fin1", "HABITACION", 3, "FORMALIZADO", d(2025, 1, 1), fin_real=d(2025, 12, 31), nombre="25-HAB3-X"),
        C("fin2", "HABITACION", 4, "FORMALIZADO", d(2025, 1, 1), fin_real=d(2026, 6, 30), nombre="25-HAB4-Y"),
    ]
    ocupacion = {o["habitacion"]: o["estado"] for o in lecturas.ocupacion(contratos, 5, HOY)}
    assert ocupacion == {1: "OCUPADA", 2: "OCUPADA", 5: "OCUPADA", 3: "PROXIMA", 4: "LIBRE"}
    situaciones = {c["id"]: lecturas.situacion(c, HOY) for c in contratos}
    assert situaciones == {"hab1": "VIGENTE", "hab2": "VIGENTE", "hab5": "VIGENTE", "hab3": "PROXIMO",
                           "hab4": "BORRADOR", "fin1": "FINALIZADO", "fin2": "FINALIZADO"}
    vencidos = [c["id"] for c in contratos if lecturas.fin_previsto_vencido(c, HOY)]
    assert vencidos == ["hab5"]                     # fin_previsto_vencido = true solo en 25-HAB5-LM


def test_el_fin_previsto_no_libera_y_finalizado_exige_fin_real_anterior_a_hoy():
    d = FECHA
    c = C("a", "HABITACION", 1, "FORMALIZADO", d(2026, 1, 1), fin_prevista=d(2026, 6, 30))
    assert lecturas.situacion(c, HOY) == "VIGENTE" and lecturas.fin_previsto_vencido(c, HOY)
    assert lecturas.ocupacion([c], 1, HOY)[0]["estado"] == "OCUPADA"
    c["fecha_fin_real"] = HOY                       # fin real == hoy: todavia vigente (FINALIZADO solo < hoy)
    assert lecturas.situacion(c, HOY) == "VIGENTE" and not lecturas.fin_previsto_vencido(c, HOY)
    c["fecha_fin_real"] = HOY - dt.timedelta(days=1)
    assert lecturas.situacion(c, HOY) == "FINALIZADO"
    assert lecturas.ocupacion([c], 1, HOY)[0]["estado"] == "LIBRE"
    assert lecturas.situacion({**c, "estado_documental": "CANCELADO"}, HOY) == "CANCELADO"


def test_vivienda_completa_vigente_ocupa_todas_las_habitaciones():
    v = C("v", "ALQUILER_VIVIENDA", None, "FORMALIZADO", FECHA(2026, 1, 1))
    assert {o["estado"] for o in lecturas.ocupacion([v], 3, HOY)} == {"OCUPADA"}
    assert lecturas.ocupacion([], None, HOY) == [] and lecturas.ocupacion([], 0, HOY) == []


def test_iniciales_del_nombre_propuesto():
    assert lecturas._iniciales("Carmen Ruiz") == "CR"
    assert lecturas._iniciales("Ana María López") == "AL"
    assert lecturas._iniciales("Empresa") == "E"
    assert lecturas._iniciales(None) == ""


def test_texto_canonico_de_importes_y_fechas_para_el_sellado():
    assert m.texto(D("50")) == "50.0000" and m.texto(FECHA(2026, 1, 2)) == "2026-01-02" and m.texto(None) is None
    p1 = m.Persona(rol="INQUILINO", tercero_id=uuid.UUID(int=1))
    p2 = m.Persona(rol="AVALISTA", yo=True)
    # el orden de las personas no cambia el contenido sellado
    assert m.personas_canonicas([p1, p2]) == m.personas_canonicas([p2, p1])
