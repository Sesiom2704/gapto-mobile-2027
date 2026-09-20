# ============================================================
# GAPTO MOBILE 2027
# Fichero: f0406.py
# Ruta: scripts/mutantes/f0406.py
# Descripcion: Arnes de mutacion de F04-06. Aplica una a una las mutaciones
#   contractuales del mandato MANDATO-F04-06-01, ejecuta la suite
#   discriminante y restaura.
#
#   DOS CLASES DE MUTANTE, y la segunda es nueva respecto de F04-05:
#
#   - CODIGO: se reemplaza un fragmento de un fichero .py, se verifica que el
#     SHA-256 cambia, se ejecuta la suite y se restaura el fichero.
#   - FISICO: se inutiliza temporalmente una garantia de PostgreSQL sobre la
#     base LOCAL DESECHABLE. Existe porque N14 exige demostrar que la
#     revalidacion parent-side de 0270 es realmente necesaria, y esa garantia
#     no vive en el codigo. Las migrations son INTOCABLES: el mutante no las
#     edita, solo deshabilita el trigger en la copia local y lo vuelve a
#     habilitar despues. Nunca se ejecuta contra Neon ni contra Supabase, y el
#     arnes aborta si la base destino no es la local de pruebas.
#
#   GUARDAS, todas heredadas de incidentes reales de F04-05 (D-181):
#   - arbol limpio antes de empezar y despues de terminar;
#   - SHA-256 antes/despues: una mutacion que no cambia el fichero es INERTE y
#     se marca DUDOSA, no superviviente;
#   - la salida de pytest debe tener forma de resumen: un argumento invalido
#     hace que la suite no llegue a ejecutarse y "cero fallos" pasaria por
#     superviviente;
#   - el DISCRIMINANTE declarado debe estar entre los fallos: si solo caen
#     tests colaterales, el mutante no esta demostrado;
#   - el discriminante debe ser DETERMINISTA cuando exista alternativa; una
#     carrera no sirve de oraculo unico;
#   - restauracion verificada, tambien para los mutantes fisicos.
#
#   Cualquier guarda incumplida deja el resultado DUDOSO y el codigo de salida
#   deja de ser 0.
#
# Uso:
#   python scripts/mutantes/f0406.py            # todos
#   python scripts/mutantes/f0406.py N14         # un lote
#
# Version: 0.1.3
#   0.1.3 (iteracion correctiva): N8 discrimina por OPERACION y no por fechas;
#   E-B4-04 deja de apoyarse en la regla retirada; N11 queda clasificado con
#   su prueba estatica.
# Version: 0.1.2
#   0.1.2 (B5): se corrige la justificacion de N11. La prediccion de que OP-21
#   haria alcanzable la terna no se cumplio.
# Version: 0.1.1
#   0.1.1 (B1): soporte de mutante EQUIVALENTE con justificacion obligatoria.
#   Un equivalente no se cuenta como superviviente, pero tampoco se ignora en
#   silencio: el mandato exige demostrar por que lo es.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess
import sys
from dataclasses import dataclass, field

RAIZ = pathlib.Path(__file__).resolve().parents[2]

SRV_TRANSF = "backend/app/services/transferencias_service.py"
REP_TRANSF = "backend/app/repositories/transferencias_repository.py"

SUITE_B1 = "tests/backend/test_115_op10_transferencia.py"
SUITE_B2 = "tests/backend/test_116_op11_reversion.py"
SUITE_B3 = "tests/backend/test_117_op13_devolucion.py"
SUITE_B4 = "tests/backend/test_118_op18_suplemento.py"
SUITE_B5 = "tests/backend/test_119_op21_correccion.py"

SRV_COR = "backend/app/services/correcciones_service.py"
REP_COR = "backend/app/repositories/correcciones_repository.py"

SRV_SUP = "backend/app/services/suplementos_service.py"

SRV_DEV = "backend/app/services/devoluciones_service.py"
REP_REL = "backend/app/repositories/relaciones_repository.py"

SRV_TES = "backend/app/services/tesoreria_service.py"
REP_TES = "backend/app/repositories/tesoreria_repository.py"

# Solo se acepta mutar fisicamente esta base. Es la local desechable que se
# recrea desde plantilla; cualquier otra cosa se aborta.
BASE_PERMITIDA = "gapto2027_test"


@dataclass(frozen=True)
class Mutante:
    """Una mutacion contractual.

    `discriminante` es el fragmento del identificador de test que DEBE caer.
    Sin el, un mutante podria darse por muerto por un fallo colateral que no
    tiene nada que ver con la invariante vigilada.
    """

    ident: str
    invariante: str
    descripcion: str
    discriminante: str
    suite: str
    fichero: str = ""
    viejo: str = ""
    nuevo: str = ""
    sql_mutar: tuple[str, ...] = field(default_factory=tuple)
    sql_restaurar: tuple[str, ...] = field(default_factory=tuple)
    # Un mutante declarado EQUIVALENTE no se cuenta como superviviente, pero
    # exige justificacion escrita: el mandato prohibe inventar una propiedad
    # para matarlo, y prohibe igualmente ignorarlo en silencio.
    equivalente: str = ""

    @property
    def es_fisico(self) -> bool:
        return bool(self.sql_mutar)


MUTANTES: list[Mutante] = [
    Mutante(
        ident="N9",
        invariante="No existe FX implicito: en monedas distintas no se compara nominalmente",
        descripcion="compara importes aunque las monedas difieran",
        fichero=SRV_TRANSF,
        viejo='        if salida["moneda"] == entrada["moneda"] and abs(\n            salida["importe"]\n        ) != entrada["importe"]:',
        nuevo='        if abs(salida["importe"]) != entrada["importe"]:',
        discriminante="test_multidivisa_sin_igualdad_nominal",
        suite=SUITE_B1,
    ),
    Mutante(
        ident="N10",
        invariante="Retry todo-o-nada: un lote parcialmente ocupado es conflicto",
        descripcion="completa las identidades que falten en vez de rechazar",
        fichero=SRV_TRANSF,
        viejo="        if set(datos.identidades) != existentes:\n            raise self._conflicto_identidad()",
        nuevo="        if False:\n            raise self._conflicto_identidad()",
        # El caso "parcialmente ocupado" lo atrapa tambien la guarda de
        # identidad economica. El unico que aisla ESTA guarda es el lote
        # casi completo, donde el par coincide y solo faltan hijos.
        discriminante="test_lote_casi_completo_no_es_reintento",
        suite=SUITE_B1,
    ),
    Mutante(
        ident="N14",
        invariante="La revalidacion parent-side de 0270 rechaza dejar una transferencia invalida",
        descripcion="deshabilita trg_movimientos_tesoreria__padre_dependencias",
        sql_mutar=(
            "ALTER TABLE gapto.movimientos_tesoreria "
            "DISABLE TRIGGER trg_movimientos_tesoreria__padre_dependencias",
        ),
        sql_restaurar=(
            "ALTER TABLE gapto.movimientos_tesoreria "
            "ENABLE TRIGGER trg_movimientos_tesoreria__padre_dependencias",
        ),
        discriminante="test_tocar_una_sola_pata_deja_estado_invalido_y_se_rechaza",
        suite=SUITE_B1,
    ),
    Mutante(
        ident="E-B1-01",
        invariante="F04-D001: la comision no se embebe en la transferencia",
        descripcion="acepta una comision dentro de la transferencia",
        fichero=SRV_TRANSF,
        viejo="        if datos.comision is not None:",
        nuevo="        if False:",
        discriminante="test_comision_embebida_rechazada",
        suite=SUITE_B1,
    ),
    Mutante(
        ident="E-B1-02",
        invariante="Origen y destino deben ser cuentas distintas",
        descripcion="admite transferir a la misma cuenta",
        fichero=SRV_TRANSF,
        viejo="        if datos.cuenta_origen_id == datos.cuenta_destino_id:",
        nuevo="        if False:",
        discriminante="test_misma_cuenta",
        suite=SUITE_B1,
        equivalente=(
            "La regla cuentas-distintas tiene DOS guardas: esta, temprana y "
            "sin tocar la base, y la de _prevalidar_estructura, que lee los "
            "movimientos ya escritos. Quitar la primera no cambia nada "
            "observable: la segunda devuelve el mismo MISMA_CUENTA y la "
            "transaccion revierte igual. Es defensa en profundidad, no una "
            "regla distinta. Matarlo exigiria inventar una propiedad sobre el "
            "ORDEN de los errores que ningun contrato fija."
        ),
    ),
    Mutante(
        ident="E-B1-03",
        invariante="El signo lo pone el motor: salida negativa, entrada positiva",
        descripcion="no invierte el signo de la pata de salida",
        fichero=SRV_TRANSF,
        viejo="                    (datos.movimiento_salida_id, datos.cuenta_origen_id,\n                     -decimal.Decimal(datos.importe_salida),",
        nuevo="                    (datos.movimiento_salida_id, datos.cuenta_origen_id,\n                     decimal.Decimal(datos.importe_salida),",
        discriminante="test_los_signos_los_pone_el_motor",
        suite=SUITE_B1,
    ),
    Mutante(
        ident="E-B1-04",
        invariante="La identidad economica de una transferencia es su par de movimientos",
        descripcion="acepta cualquier par al reintentar con el mismo UUID",
        fichero=SRV_TRANSF,
        viejo="        if not repo_transf.creacion_previa_coincide(",
        nuevo="        if False and repo_transf.creacion_previa_coincide(",
        # Con otro par, la guarda de lote completo ya rechaza. Lo que aisla
        # ESTA guarda son las seis identidades correctas con las patas
        # invertidas: el lote cuadra y lo que cambia es el sentido.
        discriminante="test_las_mismas_seis_identidades_con_las_patas_invertidas",
        suite=SUITE_B1,
    ),
    Mutante(
        ident="E-B1-05",
        invariante="Una conciliacion conserva el signo de su movimiento",
        descripcion="asigna la salida en positivo",
        fichero=SRV_TRANSF,
        viejo="                (datos.conciliacion_salida_id, datos.movimiento_salida_id,\n                 -decimal.Decimal(datos.importe_salida)),",
        nuevo="                (datos.conciliacion_salida_id, datos.movimiento_salida_id,\n                 decimal.Decimal(datos.importe_salida)),",
        discriminante="test_las_conciliaciones_conservan_el_signo_de_su_movimiento",
        suite=SUITE_B1,
    ),
    Mutante(
        ident='N3',
        invariante='Una reversion de tesoreria no es una devolucion economica',
        descripcion='enlaza la reversion consigo misma en vez de con el original',
        fichero=SRV_TES,
        viejo='                reversion_de_movimiento_id=datos.movimiento_original_id,',
        nuevo='                reversion_de_movimiento_id=datos.reversion_id,',
        discriminante='test_reversion_total',
        suite=SUITE_B2,
    ),
    Mutante(
        ident='N7',
        invariante='La suma de reversiones ACTIVAS no supera el original',
        descripcion='ignora lo ya revertido al calcular el disponible',
        fichero=SRV_TES,
        viejo='            disponible = abs(decimal.Decimal(original["importe"])) - revertido',
        nuevo='            disponible = abs(decimal.Decimal(original["importe"]))',
        discriminante='test_excede_el_importe_original',
        suite=SUITE_B2,
    ),
    Mutante(
        ident='N13',
        invariante='La reversion vive en la misma cuenta que el original (D-099)',
        descripcion='admite revertir en otra cuenta del mismo owner',
        fichero=SRV_TES,
        viejo='            if original["cuenta_id"] != datos.cuenta_id:',
        nuevo='            if False:',
        discriminante='test_cuenta_distinta',
        suite=SUITE_B2,
    ),
    Mutante(
        ident='E-B2-01',
        invariante='Profundidad maxima 1: no se encadenan reversiones (D-133)',
        descripcion='admite revertir una reversion',
        fichero=SRV_TES,
        viejo='            if original["es_reversion"]:',
        nuevo='            if False:',
        discriminante='test_reversion_de_reversion',
        suite=SUITE_B2,
    ),
    Mutante(
        ident='E-B2-02',
        invariante='No se revierte un movimiento ANULADO (D-119/T6)',
        descripcion='admite revertir un original anulado',
        fichero=SRV_TES,
        viejo='            if original["estado"] != "ACTIVO":',
        nuevo='            if False:',
        discriminante='test_original_anulado',
        suite=SUITE_B2,
    ),
    Mutante(
        ident='E-B2-03',
        invariante='El signo contrario lo pone el motor desde el original',
        descripcion='copia el signo del original en vez de invertirlo',
        fichero=SRV_TES,
        viejo='            signo = -1 if decimal.Decimal(original["importe"]) > 0 else 1',
        nuevo='            signo = 1 if decimal.Decimal(original["importe"]) > 0 else -1',
        discriminante='test_el_signo_lo_pone_el_motor_desde_el_original',
        suite=SUITE_B2,
    ),
    Mutante(
        ident='E-B2-04',
        invariante='La reversion conserva la clase del movimiento original',
        descripcion='fuerza OPERACION en toda reversion',
        fichero=SRV_TES,
        viejo='                clase_movimiento=original["clase_movimiento"],',
        nuevo='                clase_movimiento="OPERACION",',
        discriminante='test_la_reversion_conserva_la_clase_del_original',
        suite=SUITE_B2,
    ),
    Mutante(
        ident='E-B2-05',
        invariante='El lock del original precede a la lectura de lo revertido',
        descripcion='lee el acumulado sin bloquear el original',
        fichero=REP_TES,
        viejo='    sesion.uno(\n        "SELECT 1 FROM gapto.movimientos_tesoreria WHERE id = %s::uuid "\n        "FOR NO KEY UPDATE",\n        (original_id,),\n    )',
        nuevo='    sesion.uno(\n        "SELECT 1 FROM gapto.movimientos_tesoreria WHERE id = %s::uuid",\n        (original_id,),\n    )',
        discriminante='test_dos_reversiones_concurrentes_no_superan_el_original',
        suite=SUITE_B2,
    ),
    Mutante(
        ident='N1',
        invariante='El lock del hecho origen es la UNICA defensa del acumulado devuelto',
        descripcion='lee la capacidad sin bloquear el hecho original',
        fichero=REP_REL,
        viejo='    visibles = 0\n    for hecho_id in sorted(set(ids), key=str):\n        fila = sesion.uno(\n            "SELECT 1 FROM gapto.hechos_financieros WHERE id = %s::uuid "\n            "FOR NO KEY UPDATE",\n            (hecho_id,),\n        )',
        nuevo='    visibles = 0\n    for hecho_id in sorted(set(ids), key=str):\n        fila = sesion.uno(\n            "SELECT 1 FROM gapto.hechos_financieros WHERE id = %s::uuid",\n            (hecho_id,),\n        )',
        discriminante='test_i1_dos_devoluciones_concurrentes_no_superan_la_capacidad',
        suite=SUITE_B3,
    ),
    Mutante(
        ident='N2',
        invariante='INV-05: una devolucion conserva la naturaleza del original',
        descripcion='registra la devolucion como INGRESO',
        fichero=SRV_DEV,
        viejo='            if datos.tipo_efecto_devolucion == "INGRESO":',
        nuevo='            if False:',
        discriminante='test_intento_de_registrar_la_devolucion_como_ingreso',
        suite=SUITE_B3,
    ),
    Mutante(
        ident='N11',
        invariante='Una sola relacion logica por terna (F04-D028)',
        descripcion='inserta una segunda fila con la misma terna',
        fichero=SRV_DEV,
        viejo='        if existente is not None:',
        nuevo='        if False:',
        discriminante='test_retry_idempotente',
        suite=SUITE_B3,
        equivalente=(
            'EQUIVALENTE / NO DISCRIMINABLE EN LA SUPERFICIE F04-06 ACTUAL. '
            'PRUEBA ESTATICA: solo dos writers crean hecho_relaciones -- '
            'devoluciones_service (OP-13) y suplementos_service (OP-18) -- y '
            'ambos crean su hecho ORIGEN dentro de la misma transaccion, de '
            'modo que la terna (origen, destino, tipo) no puede preexistir. '
            'correcciones_service (OP-21) solo ELIMINA relaciones. Ningun '
            'writer activo puede construir el estado previo necesario. '
            'F04-D028 se mantiene como protocolo defensivo para writers '
            'futuros; el error funcional externo se retiro por acuerdo de '
            'arquitectura al no tener camino alcanzable.'
        ),
    ),
    Mutante(
        ident='N12',
        invariante='Con signos mezclados la capacidad no es demostrable (F04-D030)',
        descripcion='agrega los signos mixtos en vez de fallar cerrado',
        fichero=SRV_DEV,
        viejo='        if resumen["signos_distintos"] > 1:',
        nuevo='        if False:',
        discriminante='test_signos_mezclados_falla_cerrado',
        suite=SUITE_B3,
    ),
    Mutante(
        ident='E-B3-01',
        invariante='El acumulado se calcula sobre devoluciones ACTIVAS',
        descripcion='ignora lo ya devuelto al comprobar el limite',
        fichero=SRV_DEV,
        viejo='            if devuelto + magnitud > capacidad:',
        nuevo='            if magnitud > capacidad:',
        discriminante='test_excede_la_capacidad',
        suite=SUITE_B3,
    ),
    Mutante(
        ident='E-B3-02',
        invariante='El signo del efecto lo deriva el motor del neto del original',
        descripcion='copia el signo del original en vez de invertirlo',
        fichero=SRV_DEV,
        viejo='            signo = -1 if neto > CERO else 1',
        nuevo='            signo = 1 if neto > CERO else -1',
        discriminante='test_devolucion_parcial_conserva_la_naturaleza',
        suite=SUITE_B3,
    ),
    Mutante(
        ident='E-B3-03',
        invariante='El movimiento de la devolucion lleva signo contrario al efecto',
        descripcion='hace coincidir el signo del movimiento con el del efecto',
        fichero=SRV_DEV,
        viejo='        importe_movimiento = -importe_delta',
        nuevo='        importe_movimiento = importe_delta',
        discriminante='test_devolucion_con_caja',
        suite=SUITE_B3,
    ),
    Mutante(
        ident='E-B3-04',
        invariante='Sin equivalencia declarada no se compara nominalmente',
        descripcion='acepta multidivisa sin declaracion',
        fichero=SRV_DEV,
        viejo='        if moneda_original != datos.moneda and not datos.equivalencia_declarada:',
        nuevo='        if False:',
        discriminante='test_multidivisa_sin_equivalencia',
        suite=SUITE_B3,
    ),
    Mutante(
        ident='E-B3-05',
        invariante='La direccion es devolucion -> original (F04-D030)',
        descripcion='invierte origen y destino de la relacion',
        fichero=SRV_DEV,
        viejo='            hecho_origen_id=datos.hecho_id,\n            hecho_destino_id=datos.hecho_original_id,\n            tipo_relacion=TIPO_RELACION_DEVOLUCION,\n            importe_relacionado=magnitud,',
        nuevo='            hecho_origen_id=datos.hecho_original_id,\n            hecho_destino_id=datos.hecho_id,\n            tipo_relacion=TIPO_RELACION_DEVOLUCION,\n            importe_relacionado=magnitud,',
        discriminante='test_la_relacion_va_de_la_devolucion_al_original',
        suite=SUITE_B3,
    ),
    Mutante(
        ident='N8',
        invariante='OP-18 crea realidad NUEVA y no edita el hecho relacionado',
        descripcion='OP-18 reutiliza la identidad del hecho ajustado en vez de crear una nueva',
        fichero=SRV_SUP,
        viejo='                    hecho_id=datos.hecho_id,\n                    fecha_hecho=datos.fecha_hecho,',
        nuevo='                    hecho_id=datos.hecho_ajustado_id or datos.hecho_id,\n                    fecha_hecho=datos.fecha_hecho,',
        discriminante='test_op18_crea_realidad_nueva_y_no_edita_el_original',
        suite=SUITE_B4,
    ),
    Mutante(
        ident='E-B4-01',
        invariante='Sin fecha economica demostrada no se retrodata nada',
        descripcion='acepta realidad suplementaria sin fecha demostrada',
        fichero=SRV_SUP,
        viejo='        if not datos.fecha_demostrada:',
        nuevo='        if False:',
        discriminante='test_fecha_economica_no_demostrada',
        suite=SUITE_B4,
    ),
    Mutante(
        ident='E-B4-02',
        invariante='OP-18 no edita una realidad anterior',
        descripcion='acepta la peticion de editar el original',
        fichero=SRV_SUP,
        viejo='        if datos.editar_original:',
        nuevo='        if False:',
        discriminante='test_intento_de_editar_el_original',
        suite=SUITE_B4,
    ),
    Mutante(
        ident='E-B4-03',
        invariante='F04-06 no inventa politica de periodos cerrados',
        descripcion='procede sobre un periodo cerrado sin politica',
        fichero=SRV_SUP,
        viejo='        if datos.periodo_cerrado and not datos.politica_periodo_cerrado:',
        nuevo='        if False:',
        discriminante='test_periodo_cerrado_sin_politica',
        suite=SUITE_B4,
    ),
    Mutante(
        ident='E-B4-04',
        invariante='CORRIGE_A va del ajuste al hecho ajustado',
        descripcion='invierte origen y destino de la relacion',
        fichero=SRV_SUP,
        # El patron incluye `importe_relacionado` para ser UNIVOCO: la
        # llamada de lectura comparte las dos primeras lineas y mutarla
        # seria inerte.
        viejo='            hecho_origen_id=datos.hecho_id,\n            hecho_destino_id=datos.hecho_ajustado_id,\n            tipo_relacion=TIPO_RELACION_CORRIGE,\n            importe_relacionado=',
        nuevo='            hecho_origen_id=datos.hecho_ajustado_id,\n            hecho_destino_id=datos.hecho_id,\n            tipo_relacion=TIPO_RELACION_CORRIGE,\n            importe_relacionado=',
        discriminante='test_corrige_a_va_del_ajuste_al_hecho_ajustado',
        suite=SUITE_B4,
    ),
    Mutante(
        ident='N4',
        invariante='D-187: un hecho ACTIVO no TRANSFERENCIA no queda sin efectos',
        descripcion='deja el hecho sin ningun efecto',
        fichero=SRV_COR,
        viejo='            if finales == 0:',
        nuevo='            if False:',
        discriminante='test_correccion_que_dejaria_el_hecho_sin_efectos',
        suite=SUITE_B5,
    ),
    Mutante(
        ident='N5',
        invariante='Las raices financieras no se borran nunca (0320 / D-186)',
        descripcion='acepta el hard-delete de la raiz',
        fichero=SRV_COR,
        viejo='        if datos.eliminar_hecho:',
        nuevo='        if False:',
        discriminante='test_hard_delete_de_hecho_rechazado',
        suite=SUITE_B5,
    ),
    Mutante(
        ident='N6',
        invariante='Todo DELETE deja snapshot completo en auditoria',
        descripcion='elimina el efecto sin registrar su snapshot',
        fichero=SRV_COR,
        viejo='            auditoria.registrar(\n                sesion,\n                tabla=repo_corr.TABLA_EFECTOS,\n                registro_id=efecto_id,\n                accion=auditoria.ACCION_ANULAR,\n                datos_antes_json=snapshot,\n                motivo=datos.motivo,\n            )',
        nuevo='            auditoria.registrar(\n                sesion,\n                tabla=repo_corr.TABLA_EFECTOS,\n                registro_id=efecto_id,\n                accion=auditoria.ACCION_ANULAR,\n                motivo=datos.motivo,\n            )',
        discriminante='test_el_delete_deja_snapshot_completo',
        suite=SUITE_B5,
    ),
    Mutante(
        ident='E-B5-01',
        invariante='El control optimista serializa dos correcciones sobre la raiz',
        descripcion='ignora la version esperada',
        fichero=SRV_COR,
        viejo='            if nueva_version is None:',
        nuevo='            if False:',
        discriminante='test_version_desfasada',
        suite=SUITE_B5,
    ),
    Mutante(
        ident='E-B5-02',
        invariante='Toda correccion agregada exige motivo (D-186)',
        descripcion='acepta una correccion sin motivo',
        fichero=SRV_COR,
        viejo='        if not (datos.motivo or "").strip():',
        nuevo='        if False:',
        discriminante='test_motivo_ausente',
        suite=SUITE_B5,
    ),
    Mutante(
        ident='E-B5-03',
        invariante='Un movimiento tampoco se borra: se anula por su lifecycle',
        descripcion='acepta el hard-delete de un movimiento',
        fichero=SRV_COR,
        viejo='        if datos.eliminar_movimiento is not None:',
        nuevo='        if False:',
        discriminante='test_hard_delete_de_movimiento_rechazado',
        suite=SUITE_B5,
    ),
    Mutante(
        ident='E-B5-04',
        invariante='Solo se actualizan campos enumerados del efecto',
        descripcion='admite reescribir cualquier columna del efecto',
        fichero=SRV_COR,
        viejo='            desconocidos = set(cambios) - CAMPOS_EFECTO_CORREGIBLES',
        nuevo='            desconocidos = set()',
        discriminante='test_campo_no_corregible_rechazado',
        suite=SUITE_B5,
    ),
]


def sha256(ruta: pathlib.Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def arbol_limpio() -> bool:
    salida = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=RAIZ, capture_output=True, text=True, check=False,
    )
    return not salida.stdout.strip()


def dsn_pruebas() -> str:
    dsn = os.environ.get("GAPTO_TEST_DATABASE_URL", "")
    if not dsn:
        raise SystemExit("ABORTADO: falta GAPTO_TEST_DATABASE_URL")
    base = dsn.rsplit("/", 1)[-1].split("?")[0]
    if base != BASE_PERMITIDA:
        raise SystemExit(
            f"ABORTADO: los mutantes fisicos solo se aplican sobre "
            f"{BASE_PERMITIDA}; la base destino es '{base}'."
        )
    return dsn


def ejecutar_sql(sentencias: tuple[str, ...]) -> None:
    import psycopg  # import local: los mutantes de codigo no lo necesitan

    with psycopg.connect(dsn_pruebas(), autocommit=True) as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("SET ROLE gapto_owner")
            for sentencia in sentencias:
                cursor.execute(sentencia)


def trigger_habilitado() -> str:
    import psycopg

    with psycopg.connect(dsn_pruebas(), autocommit=True) as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT tgenabled FROM pg_trigger t JOIN pg_class c "
                "ON c.oid = t.tgrelid WHERE c.relnamespace = 'gapto'::regnamespace "
                "AND t.tgname = 'trg_movimientos_tesoreria__padre_dependencias'"
            )
            fila = cursor.fetchone()
    return "" if fila is None else fila[0]


def ejecutar_suite(suite: str) -> tuple[str, list[str]]:
    res = subprocess.run(
        [sys.executable, "-m", "pytest", suite, "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=RAIZ, capture_output=True, text=True, check=False, timeout=3600,
    )
    lineas = [l for l in res.stdout.strip().splitlines() if l.strip()]
    resumen = lineas[-1] if lineas else "(sin salida)"
    fallidos = [
        l.split(" ")[1] for l in lineas
        if l.startswith("FAILED ") and len(l.split(" ")) > 1
    ]
    return resumen, fallidos


def correr(lote: list[Mutante]) -> list[tuple[Mutante, str, int]]:
    filas: list[tuple[Mutante, str, int]] = []
    for mut in lote:
        if mut.es_fisico:
            estado_previo = trigger_habilitado()
            if estado_previo != "O":
                filas.append((mut, "DUDOSO: la garantia no estaba activa", 0))
                print(f"  {mut.ident:8} DUDOSO    la garantia no estaba activa",
                      flush=True)
                continue
            ejecutar_sql(mut.sql_mutar)
            if trigger_habilitado() == "O":
                ejecutar_sql(mut.sql_restaurar)
                filas.append((mut, "MUTACION INERTE", 0))
                print(f"  {mut.ident:8} DUDOSO    la garantia sigue activa",
                      flush=True)
                continue
            try:
                resumen, fallidos = ejecutar_suite(mut.suite)
            finally:
                ejecutar_sql(mut.sql_restaurar)
            if trigger_habilitado() != "O":  # pragma: no cover
                raise SystemExit(f"{mut.ident}: la garantia NO quedo restaurada")
        else:
            ruta = RAIZ / mut.fichero
            original = ruta.read_text()
            antes = sha256(ruta)
            if mut.viejo not in original:
                filas.append((mut, "PATRON NO ENCONTRADO", 0))
                print(f"  {mut.ident:8} DUDOSO    patron no encontrado", flush=True)
                continue
            ruta.write_text(original.replace(mut.viejo, mut.nuevo, 1))
            if sha256(ruta) == antes:
                ruta.write_text(original)
                filas.append((mut, "MUTACION INERTE", 0))
                print(f"  {mut.ident:8} DUDOSO    el fichero no cambio", flush=True)
                continue
            try:
                resumen, fallidos = ejecutar_suite(mut.suite)
            finally:
                ruta.write_text(original)
            if sha256(ruta) != antes:  # pragma: no cover
                raise SystemExit(f"{mut.ident}: la restauracion no devolvio el SHA")

        if "passed" not in resumen and "failed" not in resumen:
            filas.append((mut, f"SUITE NO EJECUTADA: {resumen[:40]}", 0))
            print(f"  {mut.ident:8} DUDOSO    la suite no llego a ejecutarse",
                  flush=True)
            continue
        n = int(resumen.split(" failed")[0].split()[-1]) if " failed" in resumen else 0
        if n == 0:
            estado = "EQUIVALENTE" if mut.equivalente else "SOBREVIVE"
        elif not any(mut.discriminante in f for f in fallidos):
            estado = "DUDOSO: cayeron colaterales, no el discriminante"
        else:
            estado = "MUERTO"
        filas.append((mut, estado, n))
        marca = "fisico" if mut.es_fisico else "codigo"
        print(f"  {mut.ident:8} {estado.split(':')[0]:9} fallos={n:<3} "
              f"[{marca}] {mut.descripcion}", flush=True)
    return filas


def main() -> int:
    filtro = set(sys.argv[1:])
    lote = [m for m in MUTANTES if not filtro or m.ident in filtro]

    if not arbol_limpio():
        print("ABORTADO: el arbol de trabajo no esta limpio antes de empezar.")
        subprocess.run(["git", "status", "--short"], cwd=RAIZ, check=False)
        return 2

    print(f"raiz={RAIZ}")
    print("=== F04-06 · MUTANTES ===", flush=True)
    resultados = correr(lote)

    if not arbol_limpio():
        print("!!! EL ARBOL NO QUEDO LIMPIO TRAS LA RESTAURACION")
        subprocess.run(["git", "status", "--short"], cwd=RAIZ, check=False)
        return 3

    muertos = sum(1 for _, e, _ in resultados if e == "MUERTO")
    equivalentes = [m for m, e, _ in resultados if e == "EQUIVALENTE"]
    print(f"\nRESULTADO: {muertos}/{len(resultados) - len(equivalentes)} muertos"
          f" + {len(equivalentes)} equivalentes declarados")
    for mut in equivalentes:
        print(f"  {mut.ident}: {mut.equivalente}")
    print("Arbol limpio tras la restauracion: OK")

    dudosos = [
        m.ident for m, e, _ in resultados
        if e not in ("MUERTO", "SOBREVIVE", "EQUIVALENTE")
    ]
    if dudosos:
        print(f"DUDOSOS (el arnes no puede demostrar su resultado): {dudosos}")
        return 4
    return 0 if muertos == len(resultados) - len(equivalentes) else 1


if __name__ == "__main__":
    sys.exit(main())
