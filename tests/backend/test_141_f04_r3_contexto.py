# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_141_f04_r3_contexto.py
# Ruta: tests/backend/test_141_f04_r3_contexto.py
# Descripcion: F04-D048 R3 (A18). Writers contextuales, ENRIQUECIMIENTO y
#   CORRECCION (OP-21) de `hecho_terceros`, `hecho_entidades`,
#   `hecho_magnitudes` y `hecho_etiquetas`: matriz R3-01, `principal`
#   obligatorio (R3-04), advisory D-080 antes de row locks (R3-02), tenant,
#   row_version, idempotencia, auditoria con snapshot y motivo.
# Version: 0.1.0
# ============================================================
from __future__ import annotations

import datetime as dt
import decimal
import threading
import time
import uuid

import psycopg
import pytest

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos_compuesto import (
    DatosContextoHecho,
    DatosEntidadHecho,
    DatosEtiquetaHecho,
    DatosMagnitudHecho,
    DatosTerceroHecho,
)
from app.core.modelos_posicion import TIPO_DERECHO, DatosAltaPosicion
from app.core.unidad_trabajo import UnidadDeTrabajo
from app.services.contexto_service import ContextoService
from app.services.correcciones_service import DatosCorreccion
from conftest import leer_fila
from f08_motor import efecto
from test_140_f04_r3_op22 import (
    como_owner,
    cuenta_filas,
    hecho,
    nueva_entidad,
    nueva_etiqueta,
    nueva_magnitud,
    nuevo_tercero,
    rechazo,
)

D = decimal.Decimal
FECHA = dt.date(2027, 6, 1)


@pytest.fixture()
def servicio_contexto(unidad: UnidadDeTrabajo) -> ContextoService:
    return ContextoService(unidad)


@pytest.fixture()
def gasto(servicio, servicio_efectos, contexto):
    """Hecho con un GASTO: (hecho_id, efecto_id, version)."""
    h = hecho()
    servicio.crear_hecho(contexto, h)
    e = efecto("GASTO", D("100.0000"))
    r = servicio_efectos.registrar_efectos(
        contexto, hecho_id=h.hecho_id, row_version_esperada=1, efectos=[e], presupuestable=True
    )
    return h.hecho_id, e.efecto_id, r.row_version


def version(admin, owner, hecho_id) -> int:
    return leer_fila(admin, owner, "SELECT row_version FROM gapto.hechos_financieros WHERE id=%s", (hecho_id,))[0]


# ==================================================================
# Matriz R3-01 (hecho_entidades)
# ==================================================================

MATRIZ = [
    # tipo, nivel_efecto, principal, relacion, esperado
    ("PROPIEDAD", False, True, "AFECTA_A", None),
    ("PROPIEDAD", True, False, "RELACIONADO_CON", None),
    ("CONTEXTO", True, True, "AFECTA_A", None),
    ("INVERSION", False, False, "RELACIONADO_CON", None),
    ("INVERSION", True, False, "RELACIONADO_CON", CodigoError.OWNERSHIP_F07),
    ("INVERSION", False, True, "AFECTA_A", CodigoError.OWNERSHIP_F07),
    ("FINANCIACION", False, True, "AFECTA_A", None),
    ("FINANCIACION", True, False, "AFECTA_A", CodigoError.OWNERSHIP_F07),
    ("PROPIEDAD", False, False, "GENERADO_POR", CodigoError.ENTRADA_INVALIDA),
    ("PROPIEDAD", False, False, "REPERCUTIBLE_A", CodigoError.ENTRADA_INVALIDA),
    ("PROPIEDAD", False, False, "INVENTADA", CodigoError.ENTRADA_INVALIDA),
]


@pytest.mark.parametrize("tipo, nivel_efecto, principal, relacion, esperado", MATRIZ,
                         ids=[f"{m[0]}-{'efecto' if m[1] else 'hecho'}-{m[2]}-{m[3]}" for m in MATRIZ])
def test_matriz_r3_01(servicio_contexto, contexto, admin, gasto, tipo, nivel_efecto, principal, relacion, esperado) -> None:
    """R3-01. tipo_entidad x nivel x relacion x principal, validados juntos."""
    hecho_id, efecto_id, v = gasto
    d = DatosContextoHecho(entidades=[DatosEntidadHecho(
        uuid.uuid4(), nueva_entidad(admin, contexto.owner_user_id, tipo), relacion, principal=principal,
        efecto_id=efecto_id if nivel_efecto else None)])
    llamada = lambda: servicio_contexto.enriquecer(contexto, hecho_id=hecho_id, row_version_esperada=v, datos=d)  # noqa: E731
    if esperado is None:
        assert llamada().entidades_creadas == 1
    else:
        rechazo(llamada, esperado)
        assert cuenta_filas(admin, contexto.owner_user_id, "hecho_entidades", "hecho_id", hecho_id) == 0


def test_posicion_no_admite_vinculo_contextual(
    servicio_contexto, servicio_posiciones, contexto, admin, gasto, contraparte
) -> None:
    """R3-01. DERECHO_OBLIGACION: nunca contexto (entraria en su saldo)."""
    hecho_id, _, v = gasto
    alta = DatosAltaPosicion(
        entidad_id=uuid.uuid4(), nombre="posicion", tipo=TIPO_DERECHO, contraparte_actor_id=contraparte,
        moneda="EUR", justificacion="DECISION_EXPLICITA", fecha_inicio_seguimiento=FECHA,
        saldo_apertura=D("0"), hecho_id=uuid.uuid4(), fecha_hecho=FECHA, concepto="posicion",
        efecto_id=uuid.uuid4(), vinculo_id=uuid.uuid4(), importe_inicial=D("10.0000"))
    servicio_posiciones.crear_posicion(contexto, alta)
    d = DatosContextoHecho(entidades=[DatosEntidadHecho(uuid.uuid4(), alta.entidad_id, "RELACIONADO_CON", principal=False)])
    rechazo(lambda: servicio_contexto.enriquecer(contexto, hecho_id=hecho_id, row_version_esperada=v, datos=d),
            CodigoError.ENTRADA_INVALIDA)


def test_entidad_deshabilitada_no_recibe_vinculo_nuevo(servicio_contexto, contexto, admin, gasto) -> None:
    """R3-01. Estado de entidad."""
    hecho_id, _, v = gasto
    d = DatosContextoHecho(entidades=[DatosEntidadHecho(
        uuid.uuid4(), nueva_entidad(admin, contexto.owner_user_id, "PROPIEDAD", enabled=False), "AFECTA_A", principal=False)])
    rechazo(lambda: servicio_contexto.enriquecer(contexto, hecho_id=hecho_id, row_version_esperada=v, datos=d),
            CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO)


# ==================================================================
# R3-04 · principal obligatorio
# ==================================================================

def test_principal_ausente_no_construye_el_dto() -> None:
    """R3-04. Sin default: omitirlo es un error antes de cualquier INSERT."""
    with pytest.raises(TypeError):
        DatosTerceroHecho(uuid.uuid4(), uuid.uuid4(), "VENDEDOR")
    with pytest.raises(TypeError):
        DatosEntidadHecho(uuid.uuid4(), uuid.uuid4(), "AFECTA_A")


@pytest.mark.parametrize("dimension", ["tercero", "entidad"])
def test_principal_none_se_rechaza_y_no_se_convierte_en_false(
    servicio_contexto, contexto, admin, gasto, dimension
) -> None:
    """R3-04. principal=None -> ENTRADA_INVALIDA, sin filas."""
    hecho_id, _, v = gasto
    owner = contexto.owner_user_id
    if dimension == "tercero":
        d = DatosContextoHecho(terceros=[DatosTerceroHecho(uuid.uuid4(), nuevo_tercero(admin, owner), "VENDEDOR", principal=None)])
        tabla = "hecho_terceros"
    else:
        d = DatosContextoHecho(entidades=[DatosEntidadHecho(uuid.uuid4(), nueva_entidad(admin, owner), "AFECTA_A", principal=None)])
        tabla = "hecho_entidades"
    rechazo(lambda: servicio_contexto.enriquecer(contexto, hecho_id=hecho_id, row_version_esperada=v, datos=d),
            CodigoError.ENTRADA_INVALIDA)
    assert cuenta_filas(admin, owner, tabla, "hecho_id", hecho_id) == 0


@pytest.mark.parametrize("valor", [True, False])
def test_principal_explicito_se_conserva(servicio_contexto, contexto, admin, gasto, valor) -> None:
    """R3-04. true/false explicitos se persisten tal cual (sin degradar)."""
    hecho_id, _, v = gasto
    t = DatosTerceroHecho(uuid.uuid4(), nuevo_tercero(admin, contexto.owner_user_id), "OTRO", principal=valor)
    servicio_contexto.enriquecer(contexto, hecho_id=hecho_id, row_version_esperada=v, datos=DatosContextoHecho(terceros=[t]))
    assert leer_fila(admin, contexto.owner_user_id, "SELECT principal FROM gapto.hecho_terceros WHERE id=%s",
                     (t.registro_id,)) == (valor,)


# ==================================================================
# Enriquecimiento (§11)
# ==================================================================

def _una_de_cada(admin, owner) -> DatosContextoHecho:
    return DatosContextoHecho(
        terceros=[DatosTerceroHecho(uuid.uuid4(), nuevo_tercero(admin, owner), "VENDEDOR", principal=True)],
        entidades=[DatosEntidadHecho(uuid.uuid4(), nueva_entidad(admin, owner), "AFECTA_A", principal=False)],
        magnitudes=[DatosMagnitudHecho(uuid.uuid4(), nueva_magnitud(admin, owner), D("7.25"), unidad="l")],
        etiquetas=[DatosEtiquetaHecho(uuid.uuid4(), nueva_etiqueta(admin, owner))],
    )


def test_enriquecimiento_de_cada_dimension(servicio_contexto, contexto, admin, gasto) -> None:
    """§11. Añade lo que faltaba: una version mas, auditoria CREAR por fila,
    sin motivo (no es correccion)."""
    hecho_id, _, v = gasto
    owner = contexto.owner_user_id
    d = _una_de_cada(admin, owner)
    r = servicio_contexto.enriquecer(contexto, hecho_id=hecho_id, row_version_esperada=v, datos=d)
    assert r.hecho_row_version == v + 1 == version(admin, owner, hecho_id)
    assert (r.terceros_creados, r.entidades_creadas, r.magnitudes_creadas, r.etiquetas_creadas) == (1, 1, 1, 1)
    for registro_id in d.identidades():
        assert leer_fila(admin, owner, "SELECT accion, motivo FROM gapto.auditoria WHERE registro_id=%s",
                         (registro_id,)) == ("CREAR", None)


def test_enriquecimiento_replay_idempotente_y_subconjunto_conflicto(servicio_contexto, contexto, admin, gasto) -> None:
    """§11/§13. Reintento exacto -> idempotente sin version nueva; mismo UUID
    con otro contenido o lote parcial -> conflicto."""
    hecho_id, _, v = gasto
    owner = contexto.owner_user_id
    d = _una_de_cada(admin, owner)
    servicio_contexto.enriquecer(contexto, hecho_id=hecho_id, row_version_esperada=v, datos=d)
    r = servicio_contexto.enriquecer(contexto, hecho_id=hecho_id, row_version_esperada=v, datos=d)
    assert r.idempotente and r.hecho_row_version == v + 1
    parcial = DatosContextoHecho(
        etiquetas=list(d.etiquetas) + [DatosEtiquetaHecho(uuid.uuid4(), nueva_etiqueta(admin, owner))])
    rechazo(lambda: servicio_contexto.enriquecer(contexto, hecho_id=hecho_id, row_version_esperada=v + 1, datos=parcial),
            CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION)


def test_enriquecimiento_version_desfasada(servicio_contexto, contexto, admin, gasto) -> None:
    """§16. row_version obligatorio: stale -> VERSION_DESFASADA, nada escrito."""
    hecho_id, _, v = gasto
    d = DatosContextoHecho(etiquetas=[DatosEtiquetaHecho(uuid.uuid4(), nueva_etiqueta(admin, contexto.owner_user_id))])
    rechazo(lambda: servicio_contexto.enriquecer(contexto, hecho_id=hecho_id, row_version_esperada=v - 1, datos=d),
            CodigoError.VERSION_DESFASADA)
    assert cuenta_filas(admin, contexto.owner_user_id, "hecho_etiquetas", "hecho_id", hecho_id) == 0


# ==================================================================
# Correccion OP-21 (§12)
# ==================================================================

@pytest.fixture()
def enriquecido(servicio_contexto, contexto, admin, gasto):
    hecho_id, _, v = gasto
    d = _una_de_cada(admin, contexto.owner_user_id)
    r = servicio_contexto.enriquecer(contexto, hecho_id=hecho_id, row_version_esperada=v, datos=d)
    return hecho_id, d, r.hecho_row_version


def test_correccion_de_cada_dimension(servicio_correcciones, contexto, admin, enriquecido) -> None:
    """§12. Tercero reemplazado, entidad retirada, magnitud corregida,
    etiqueta reemplazada. Snapshot completo de lo retirado y motivo."""
    hecho_id, d, v = enriquecido
    owner = contexto.owner_user_id
    nuevo_t = DatosTerceroHecho(uuid.uuid4(), d.terceros[0].tercero_id, "OTRO", principal=True)
    nueva_g = DatosEtiquetaHecho(uuid.uuid4(), nueva_etiqueta(admin, owner))
    motivo = "el vendedor y la etiqueta eran otros"
    servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=hecho_id, row_version_esperada=v, motivo=motivo,
        terceros_a_eliminar=(d.terceros[0].registro_id,), terceros_a_crear=(nuevo_t,),
        entidades_a_eliminar=(d.entidades[0].registro_id,),
        magnitudes_a_actualizar={d.magnitudes[0].registro_id: {"valor": D("8.5")}},
        etiquetas_a_eliminar=(d.etiquetas[0].registro_id,), etiquetas_a_crear=(nueva_g,),
    ))
    assert leer_fila(admin, owner, "SELECT rol_en_hecho FROM gapto.hecho_terceros WHERE hecho_id=%s", (hecho_id,)) == ("OTRO",)
    assert cuenta_filas(admin, owner, "hecho_entidades", "hecho_id", hecho_id) == 0
    assert leer_fila(admin, owner, "SELECT valor, unidad FROM gapto.hecho_magnitudes WHERE hecho_id=%s",
                     (hecho_id,)) == (D("8.500000"), "l")
    for retirado in (d.terceros[0].registro_id, d.entidades[0].registro_id, d.etiquetas[0].registro_id):
        fila = leer_fila(admin, owner, "SELECT accion, motivo, datos_antes->>'id' FROM gapto.auditoria "
                         "WHERE registro_id=%s AND accion='ANULAR'", (retirado,))
        assert fila == ("ANULAR", motivo, str(retirado))
    assert leer_fila(admin, owner, "SELECT datos_antes->>'valor', datos_despues->>'valor', motivo FROM gapto.auditoria "
                     "WHERE registro_id=%s AND accion='ACTUALIZAR'", (d.magnitudes[0].registro_id,))[2] == motivo


def test_correccion_elimina_magnitud_que_era_desconocida(servicio_correcciones, contexto, admin, enriquecido) -> None:
    """§9/§12. Una magnitud que nunca se conocio se ELIMINA (ausencia), no se
    pone a cero; poner valor None se rechaza."""
    hecho_id, d, v = enriquecido
    registro = d.magnitudes[0].registro_id
    rechazo(lambda: servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=hecho_id, row_version_esperada=v, motivo="x",
        magnitudes_a_actualizar={registro: {"valor": None}})), CodigoError.ENTRADA_INVALIDA)
    servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=hecho_id, row_version_esperada=v, motivo="no se conocia", magnitudes_a_eliminar=(registro,)))
    assert cuenta_filas(admin, contexto.owner_user_id, "hecho_magnitudes", "hecho_id", hecho_id) == 0


def test_correccion_exige_motivo(servicio_correcciones, contexto, enriquecido) -> None:
    """§12. Corregir sin motivo -> MOTIVO_AUSENTE."""
    hecho_id, d, v = enriquecido
    rechazo(lambda: servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=hecho_id, row_version_esperada=v, motivo=None,
        etiquetas_a_eliminar=(d.etiquetas[0].registro_id,))), CodigoError.MOTIVO_AUSENTE)


@pytest.mark.parametrize("dimension", ["terceros", "entidades", "magnitudes", "etiquetas"])
def test_enriquecimiento_no_se_disfraza_de_correccion(
    servicio_correcciones, contexto, admin, enriquecido, dimension
) -> None:
    """§12. Un alta pura en OP-21 es enriquecimiento: se rechaza."""
    hecho_id, _, v = enriquecido
    owner = contexto.owner_user_id
    alta = {
        "terceros": ("terceros_a_crear", DatosTerceroHecho(uuid.uuid4(), nuevo_tercero(admin, owner), "OTRO", principal=False)),
        "entidades": ("entidades_a_crear", DatosEntidadHecho(uuid.uuid4(), nueva_entidad(admin, owner), "AFECTA_A", principal=False)),
        "magnitudes": ("magnitudes_a_crear", DatosMagnitudHecho(uuid.uuid4(), nueva_magnitud(admin, owner), D("1"))),
        "etiquetas": ("etiquetas_a_crear", DatosEtiquetaHecho(uuid.uuid4(), nueva_etiqueta(admin, owner))),
    }[dimension]
    rechazo(lambda: servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=hecho_id, row_version_esperada=v, motivo="faltaba", **{alta[0]: (alta[1],)})),
        CodigoError.ENTRADA_INVALIDA)


def test_op21_no_toca_vinculos_generado_por(
    servicio_correcciones, servicio_posiciones, contexto, admin, contraparte
) -> None:
    """R3-01. OP-21 contextual no alcanza el vinculo GENERADO_POR de OP-12."""
    alta = DatosAltaPosicion(
        entidad_id=uuid.uuid4(), nombre="posicion", tipo=TIPO_DERECHO, contraparte_actor_id=contraparte,
        moneda="EUR", justificacion="DECISION_EXPLICITA", fecha_inicio_seguimiento=FECHA,
        saldo_apertura=D("0"), hecho_id=uuid.uuid4(), fecha_hecho=FECHA, concepto="posicion",
        efecto_id=uuid.uuid4(), vinculo_id=uuid.uuid4(), importe_inicial=D("10.0000"))
    servicio_posiciones.crear_posicion(contexto, alta)
    v = version(admin, contexto.owner_user_id, alta.hecho_id)
    rechazo(lambda: servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=alta.hecho_id, row_version_esperada=v, motivo="x", entidades_a_eliminar=(alta.vinculo_id,))),
        CodigoError.ENTRADA_INVALIDA)


# ==================================================================
# §20 · Tenant
# ==================================================================

@pytest.mark.parametrize("dimension", ["tercero", "entidad", "magnitud", "etiqueta"])
def test_objeto_de_otro_tenant_no_es_visible(servicio_contexto, contexto, admin, gasto, otro_owner, dimension) -> None:
    """§20. Referenciar un objeto de otro tenant -> AGREGADO_NO_ENCONTRADO."""
    hecho_id, _, v = gasto
    d = {
        "tercero": DatosContextoHecho(terceros=[DatosTerceroHecho(uuid.uuid4(), nuevo_tercero(admin, otro_owner), "OTRO", principal=False)]),
        "entidad": DatosContextoHecho(entidades=[DatosEntidadHecho(uuid.uuid4(), nueva_entidad(admin, otro_owner), "AFECTA_A", principal=False)]),
        "magnitud": DatosContextoHecho(magnitudes=[DatosMagnitudHecho(uuid.uuid4(), nueva_magnitud(admin, otro_owner), D("1"))]),
        "etiqueta": DatosContextoHecho(etiquetas=[DatosEtiquetaHecho(uuid.uuid4(), nueva_etiqueta(admin, otro_owner))]),
    }[dimension]
    rechazo(lambda: servicio_contexto.enriquecer(contexto, hecho_id=hecho_id, row_version_esperada=v, datos=d),
            CodigoError.AGREGADO_NO_ENCONTRADO)


def test_otro_tenant_no_ve_ni_corrige_ni_enriquece(
    servicio_contexto, servicio_correcciones, contexto, admin, enriquecido, otro_owner
) -> None:
    """§20. El hecho de un tenant es invisible para otro: ni enriquecer ni
    corregir (DELETE/UPDATE) sus filas contextuales."""
    hecho_id, d, v = enriquecido
    ajeno = ContextoOperacion(owner_user_id=otro_owner, actor_tipo="SISTEMA", request_id=uuid.uuid4())
    rechazo(lambda: servicio_contexto.enriquecer(ajeno, hecho_id=hecho_id, row_version_esperada=v, datos=DatosContextoHecho(
        etiquetas=[DatosEtiquetaHecho(uuid.uuid4(), nueva_etiqueta(admin, otro_owner))])), CodigoError.AGREGADO_NO_ENCONTRADO)
    rechazo(lambda: servicio_correcciones.corregir(ajeno, DatosCorreccion(
        hecho_id=hecho_id, row_version_esperada=v, motivo="x", etiquetas_a_eliminar=(d.etiquetas[0].registro_id,),
        magnitudes_a_actualizar={d.magnitudes[0].registro_id: {"valor": D("0")}})), CodigoError.AGREGADO_NO_ENCONTRADO)
    for tabla in ("hecho_terceros", "hecho_entidades", "hecho_magnitudes", "hecho_etiquetas"):
        assert cuenta_filas(admin, contexto.owner_user_id, tabla, "hecho_id", hecho_id) == 1


@pytest.mark.parametrize("tabla", ["hecho_terceros", "hecho_entidades", "hecho_magnitudes", "hecho_etiquetas"])
def test_sin_contexto_de_tenant_falla_cerrado(dsn, admin, contexto, enriquecido, tabla) -> None:
    """§20. gapto_runtime sin GUC de tenant: o no ve nada o la consulta falla;
    en ningun caso lee ni borra filas del tenant (fail-closed)."""
    hecho_id, _, _ = enriquecido
    for sentencia in (f"SELECT count(*) FROM gapto.{tabla} WHERE hecho_id=%s",
                      f"DELETE FROM gapto.{tabla} WHERE hecho_id=%s"):
        with psycopg.connect(dsn) as conexion:
            conexion.execute("SET ROLE gapto_runtime")
            try:
                cursor = conexion.execute(sentencia, (hecho_id,))
                if sentencia.startswith("SELECT"):
                    assert cursor.fetchone() == (0,)
                else:
                    assert cursor.rowcount == 0
            except psycopg.Error:
                conexion.rollback()
    assert cuenta_filas(admin, contexto.owner_user_id, tabla, "hecho_id", hecho_id) == 1


def test_servicio_sin_contexto_de_tenant() -> None:
    """§20. Sin tenant no hay operacion: TENANT_AUSENTE antes de tocar la base."""
    with pytest.raises(ErrorMotor) as excinfo:
        ContextoOperacion(owner_user_id=None, actor_tipo="SISTEMA", request_id=uuid.uuid4())
    assert excinfo.value.codigo is CodigoError.TENANT_AUSENTE


# ==================================================================
# R3-02 · advisory D-080 ANTES del root lock
# ==================================================================

def test_advisory_d080_antes_del_root_lock(dsn, unidad, contexto, admin, gasto) -> None:
    """R3-02. Con el advisory INVERSIONES tomado por otra transaccion, un
    enriquecimiento que escribe hecho_entidades queda esperando SIN haber
    bloqueado aun la raiz: otra sesion puede bloquear el hecho con NOWAIT.
    (Si el advisory se tomase despues del root lock, el NOWAIT fallaria.)"""
    hecho_id, _, v = gasto
    owner = contexto.owner_user_id
    d = DatosContextoHecho(entidades=[DatosEntidadHecho(uuid.uuid4(), nueva_entidad(admin, owner), "AFECTA_A", principal=False)])
    bloqueador = psycopg.connect(dsn)
    bloqueador.execute("BEGIN")
    bloqueador.execute("SELECT pg_advisory_xact_lock(hashtext('gapto:INVERSIONES'), hashtext(%s))", (str(owner),))
    resultado: dict = {}

    def enriquecer() -> None:
        try:
            resultado["r"] = ContextoService(unidad).enriquecer(
                contexto, hecho_id=hecho_id, row_version_esperada=v, datos=d)
        except Exception as exc:  # pragma: no cover - diagnostico
            resultado["e"] = exc

    hilo = threading.Thread(target=enriquecer)
    hilo.start()
    time.sleep(1.0)
    sonda = psycopg.connect(dsn)
    try:
        sonda.execute("BEGIN")
        sonda.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
        sonda.execute("SELECT 1 FROM gapto.hechos_financieros WHERE id=%s FOR UPDATE NOWAIT", (hecho_id,))
        sonda.execute("ROLLBACK")
    finally:
        sonda.close()
        bloqueador.execute("ROLLBACK")
        bloqueador.close()
        hilo.join(10)
    assert "e" not in resultado, resultado.get("e")
    assert resultado["r"].entidades_creadas == 1
