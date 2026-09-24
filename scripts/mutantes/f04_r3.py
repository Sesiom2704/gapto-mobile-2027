#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: f04_r3.py
# Ruta: scripts/mutantes/f04_r3.py
# Descripcion: Arnes de mutacion de F04-D048 R3 (A17 + A18): OP-22,
#   writers contextuales, enriquecimiento y correccion OP-21 contextual.
#
#   Cada mutante aplica 1..N sustituciones (cada patron debe aparecer
#   EXACTAMENTE una vez en su fichero) y declara su DISCRIMINANTE: el test
#   concreto que debe caer. No se da por muerto si solo caen tests
#   colaterales.
#
#   Guardas D-181/D-192: E/S byte a byte; marcador DURABLE con el contenido
#   original de todos los ficheros tocados escrito ANTES del primer byte
#   mutado; al arrancar, si hay marcador, se restaura, se verifica y se
#   aborta no-PASS; restauracion verificada por SHA-256 tras cada mutante;
#   preflight verde de la suite antes del primer mutante; arbol limpio
#   exigido; un unico veredicto por mutante.
# Uso:
#   GAPTO_TEST_DATABASE_URL=... python scripts/mutantes/f04_r3.py [R3-M1 ...]
# Version: 0.1.0
# ============================================================
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
from dataclasses import dataclass

RAIZ = pathlib.Path(__file__).resolve().parents[2]
SUITE = (
    "tests/backend/test_140_f04_r3_op22.py",
    "tests/backend/test_141_f04_r3_contexto.py",
)
CMP = "backend/app/services/compuesto_service.py"
CTX = "backend/app/services/contexto_service.py"
COR = "backend/app/services/correcciones_service.py"
TES = "backend/app/services/tesoreria_service.py"
MARCADOR = RAIZ / ".mutante_f04_r3_en_curso"


@dataclass(frozen=True)
class Mutante:
    ident: str
    invariante: str
    cambios: tuple[tuple[str, str, str], ...]  # (fichero, viejo, nuevo)
    discriminante: str


INFERIR_POSICION = (
    "        movimientos: dict[uuid.UUID, int] = {}\n",
    "        if not datos.posiciones and datos.aportaciones and datos.efectos and datos.efectos[0].atribuciones:\n"
    "            from app.core.modelos_posicion import DatosAltaPosicion as _Alta\n"
    "            import decimal as _dec\n"
    "            _a = datos.efectos[0].atribuciones[0]\n"
    "            _r = PosicionesService(adscrita).crear_posicion(contexto, _Alta(\n"
    "                entidad_id=uuid.uuid4(), nombre='inferida', tipo='DERECHO_COBRO',\n"
    "                contraparte_actor_id=_a.actor_id, moneda='EUR', justificacion='DECISION_EXPLICITA',\n"
    "                fecha_inicio_seguimiento=datos.hecho.fecha_hecho, saldo_apertura=_dec.Decimal('0'),\n"
    "                hecho_id=raiz, hecho_row_version_esperada=version, fecha_hecho=datos.hecho.fecha_hecho,\n"
    "                concepto='inferida', efecto_id=uuid.uuid4(), vinculo_id=uuid.uuid4(),\n"
    "                importe_inicial=_a.importe_atribuido))\n"
    "            version = _r.hecho_row_version\n"
    "        movimientos: dict[uuid.UUID, int] = {}\n",
)

INFERIR_APORTACION = (
    "        if datos.aportaciones:\n            r = TesoreriaService(adscrita).registrar_aportaciones(\n",
    "        if not datos.aportaciones and datos.posiciones and datos.pagos:\n"
    "            from app.core.modelos_tesoreria import DatosAportacion as _Ap\n"
    "            _p = datos.pagos[0]\n"
    "            version = TesoreriaService(adscrita).registrar_aportaciones(\n"
    "                contexto, hecho_id=raiz, hecho_row_version_esperada=version,\n"
    "                aportaciones=[_Ap(aportacion_id=uuid.uuid4(), importe=abs(_p.movimiento.importe),\n"
    "                                  criterio_aportacion='MANUAL',\n"
    "                                  hecho_movimiento_tesoreria_id=_p.conciliacion.conciliacion_id)],\n"
    "            ).hecho_row_version\n"
    "        if datos.aportaciones:\n            r = TesoreriaService(adscrita).registrar_aportaciones(\n",
)

OBLIGATORIA_COMO_INVARIANTE = (
    "            # 2. IDENTIDAD antes que cualquier validacion de estado (§14).\n",
    "            for _e in datos.efectos:\n"
    "                if _e.categoria_id is not None and not datos.contexto.magnitudes and sesion.uno(\n"
    "                    'SELECT 1 FROM gapto.categoria_magnitudes WHERE categoria_id=%s AND obligatoria',\n"
    "                    (_e.categoria_id,)):\n"
    "                    raise ErrorMotor(CodigoError.ENTRADA_INVALIDA, 'magnitud obligatoria ausente')\n"
    "            # 2. IDENTIDAD antes que cualquier validacion de estado (§14).\n",
)

VALIDAR_ANTES_DE_IDENTIDAD = (
    "            # 2. IDENTIDAD antes que cualquier validacion de estado (§14).\n",
    "            for _ent in datos.contexto.entidades:\n"
    "                if (repo_comp.leer(sesion, 'entidades', _ent.entidad_id) or {}).get('enabled') is False:\n"
    "                    raise ErrorMotor(CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO, 'deshabilitada')\n"
    "            # 2. IDENTIDAD antes que cualquier validacion de estado (§14).\n",
)

MUTANTES = (
    Mutante("R3-M1", "Ninguna posicion sin peticion explicita ni por diferencia (INV-04)",
            ((CMP,) + INFERIR_POSICION,), "test_posicion_no_se_infiere_por_diferencia"),
    Mutante("R3-M2", "La aportacion del adelanto nunca se infiere del movimiento (Q01)",
            ((CMP,) + INFERIR_APORTACION,), "test_i5_adelanto_puro"),
    Mutante("R3-M3", "Una aportacion sobre un cobro se rechaza (OP-06)",
            ((TES, "        if decimal.Decimal(importe_movimiento) > CERO:\n            raise ErrorMotor(\n                CodigoError.USO_EN_COBRO_NO_PERMITIDO,",
              "        if False:\n            raise ErrorMotor(\n                CodigoError.USO_EN_COBRO_NO_PERMITIDO,"),),
            "test_i2_aportacion_en_cobro_se_rechaza_y_no_deja_nada"),
    Mutante("R3-M4", "OP-18 se invoca adscrito, no ampliado ni esquivado (Q02)",
            ((CMP, "            version = SuplementosService(adscrita).registrar(\n                contexto, datos.suplemento\n",
              "            version = SuplementosService(adscrita).registrar(\n                contexto, dataclasses.replace(datos.suplemento, fecha_demostrada=True)\n"),),
            "test_i7_op22_conserva_el_contrato_de_op18"),
    Mutante("R3-M5", "REALIZADA solo por decision explicita",
            ((CMP, "                    marcar_realizada=p.marcar_realizada,\n", "                    marcar_realizada=True,\n"),),
            "test_i6_prevision_realidad_solo_por_decision_explicita"),
    Mutante("R3-M6", "Una sola transaccion: sin COMMIT parcial ante fallo tardio",
            ((CMP, "            resultado = self._componer(contexto, adscrita, datos)\n",
              "            try:\n                resultado = self._componer(contexto, adscrita, datos)\n"
              "            except Exception:\n                resultado = ResultadoHechoCompuesto(hecho_id=raiz, hecho_row_version=0)\n"),),
            "test_fallo_tardio_no_deja_nada"),
    Mutante("R3-M7", "Identidad antes de validacion mutable (§14)",
            ((CMP,) + VALIDAR_ANTES_DE_IDENTIDAD,), "test_identidad_antes_de_validacion_mutable"),
    Mutante("R3-M8", "Entidad (u objeto) deshabilitado no recibe vinculo nuevo",
            ((CTX, "    if not ficha[\"enabled\"]:\n", "    if False:\n"),),
            "test_entidad_deshabilitada_no_recibe_vinculo_nuevo"),
    Mutante("R3-M9", "Advisory D-080 antes de cualquier row lock (R3-02)",
            ((CTX, "    if escribe_entidades:\n        repo_corr.tomar_advisory_inversiones(sesion, owner)\n",
              "    if False:\n        repo_corr.tomar_advisory_inversiones(sesion, owner)\n"),),
            "test_advisory_d080_antes_del_root_lock"),
    Mutante("R3-M10", "Magnitud desconocida = ausencia, nunca cero",
            ((CTX, "        if m.valor is None:\n            raise ErrorMotor(", "        if m.valor is None and False:\n            raise ErrorMotor("),
             (CTX, "        try:\n            valor = decimal.Decimal(m.valor)\n",
              "        try:\n            valor = decimal.Decimal(m.valor if m.valor is not None else 0)\n"),
             (CTX, "                valor=decimal.Decimal(m.valor),\n",
              "                valor=decimal.Decimal(m.valor if m.valor is not None else 0),\n")),
            "test_magnitud_desconocida_es_ausencia_nunca_cero"),
    Mutante("R3-M11", "categoria_magnitudes.obligatoria no es invariante F04 (Q03)",
            ((CMP,) + OBLIGATORIA_COMO_INVARIANTE,), "test_q03_magnitud_obligatoria_ausente_no_rechaza"),
    Mutante("R3-M12", "Objeto de otro tenant: rechazo de dominio antes del INSERT",
            ((CTX, "    if ficha is None:\n        raise ErrorMotor(\n            CodigoError.AGREGADO_NO_ENCONTRADO,",
              "    if False:\n        raise ErrorMotor(\n            CodigoError.AGREGADO_NO_ENCONTRADO,"),),
            "test_objeto_de_otro_tenant_no_es_visible"),
    Mutante("R3-M13", "Correccion contextual exige motivo",
            ((COR, "        if not (datos.motivo or \"\").strip():\n", "        if False:\n"),),
            "test_correccion_exige_motivo"),
    Mutante("R3-M14", "Enriquecimiento no se disfraza de correccion",
            ((COR, "            if altas and not cambios:\n", "            if False:\n"),),
            "test_enriquecimiento_no_se_disfraza_de_correccion"),
    Mutante("R3-M15", "principal obligatorio: ausencia nunca se convierte en false (R3-04)",
            ((CTX, "    if not isinstance(valor, bool):\n", "    if valor is not None and not isinstance(valor, bool):\n"),
             (CTX, "                principal=t.principal,\n", "                principal=bool(t.principal),\n"),
             (CTX, "                principal=e.principal,\n", "                principal=bool(e.principal),\n")),
            "test_principal_none_se_rechaza_y_no_se_convierte_en_false"),
    Mutante("R3-M16", "Inversion a nivel de efecto o principal -> OWNERSHIP_F07",
            ((CTX, "        if e.efecto_id is not None or e.principal:\n", "        if False:\n"),),
            "test_matriz_r3_01"),
    Mutante("R3-M17", "Posicion (DERECHO_OBLIGACION) sin vinculo contextual",
            # Retirar SOLO la guarda explicita es un mutante equivalente (la
            # rama final `tipo not in TIPOS_ENTIDAD_CONTEXTO_LIBRE` rechaza con
            # el mismo codigo): se muta la regla completa, admitiendo la
            # posicion como contexto libre.
            ((CTX, "    if tipo == TIPO_ENTIDAD_POSICION:\n", "    if False:\n"),
             (CTX, "    elif tipo not in TIPOS_ENTIDAD_CONTEXTO_LIBRE:\n",
              "    elif tipo not in TIPOS_ENTIDAD_CONTEXTO_LIBRE | {TIPO_ENTIDAD_POSICION}:\n")),
            "test_posicion_no_admite_vinculo_contextual"),
    Mutante("R3-M18", "OP-21 contextual no alcanza GENERADO_POR",
            ((COR, "            if fila[\"tipo_relacion\"] not in RELACIONES_CONTEXTUALES:\n", "            if False:\n"),),
            "test_op21_no_toca_vinculos_generado_por"),
    Mutante("R3-M19", "Agregado parcial o distinto no se da por replay",
            ((CMP, "                if self._agregado_coincide(sesion, datos):\n", "                if True:\n"),),
            "test_agregado_parcial_preexistente_no_se_completa"),
    Mutante("R3-M20", "Financiacion a nivel de efecto -> OWNERSHIP_F07",
            ((CTX, "        if e.efecto_id is not None:\n            raise ErrorMotor(\n                CodigoError.OWNERSHIP_F07,\n                \"Un vinculo de financiacion",
              "        if False:\n            raise ErrorMotor(\n                CodigoError.OWNERSHIP_F07,\n                \"Un vinculo de financiacion"),),
            "test_matriz_r3_01"),
)


def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _recuperar_si_aborto_previo() -> None:
    if MARCADOR.exists():
        guardado = json.loads(MARCADOR.read_text("ascii"))
        for ruta_rel, (hexa, sha) in guardado.items():
            (RAIZ / ruta_rel).write_bytes(bytes.fromhex(hexa))
            if _sha((RAIZ / ruta_rel).read_bytes()) != sha:
                raise SystemExit(f"ABORTADO: restauracion no verificada en {ruta_rel}")
        MARCADOR.unlink()
        raise SystemExit("ABORTADO: habia una mutacion a medias; restaurada y verificada. Vuelve a ejecutar.")


def _arbol_limpio() -> None:
    salida = subprocess.run(["git", "status", "--porcelain"], cwd=RAIZ, capture_output=True, text=True).stdout.strip()
    if salida:
        raise SystemExit("ABORTADO: el arbol de trabajo no esta limpio.")


def _pytest() -> tuple[int, str]:
    p = subprocess.run([sys.executable, "-m", "pytest", *SUITE, "-q", "-p", "no:cacheprovider", "-rf", "--timeout", "90"],
                       cwd=RAIZ, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def ejecutar(m: Mutante) -> str:
    originales: dict[str, bytes] = {}
    for fichero, viejo, _ in m.cambios:
        if fichero not in originales:
            originales[fichero] = (RAIZ / fichero).read_bytes()
    textos = {f: b.decode("utf-8") for f, b in originales.items()}
    for fichero, viejo, nuevo in m.cambios:
        n = textos[fichero].count(viejo)
        if n != 1:
            return f"DUDOSO    patron encontrado {n} veces en {fichero} (se exige 1)"
        textos[fichero] = textos[fichero].replace(viejo, nuevo, 1)
    MARCADOR.write_text(json.dumps({f: (b.hex(), _sha(b)) for f, b in originales.items()}), "ascii")
    try:
        for fichero, texto in textos.items():
            (RAIZ / fichero).write_bytes(texto.encode("utf-8"))
        codigo, salida = _pytest()
    finally:
        for fichero, original in originales.items():
            (RAIZ / fichero).write_bytes(original)
            if _sha((RAIZ / fichero).read_bytes()) != _sha(original):
                raise SystemExit(f"ABORTADO: restauracion fallida en {fichero}")
        MARCADOR.unlink()
    if "passed" not in salida and "failed" not in salida and "error" not in salida:
        return "DUDOSO    pytest no llego a ejecutarse"
    fallos = [l for l in salida.splitlines() if l.startswith(("FAILED", "ERROR"))]
    if codigo == 0:
        return "VIVO      ningun test cae"
    if not any(m.discriminante in l for l in fallos):
        return f"DUDOSO    caen {len(fallos)} tests pero no el discriminante"
    return f"MUERTO    fallos={len(fallos)}"


def main(argv: list[str]) -> int:
    _recuperar_si_aborto_previo()
    _arbol_limpio()
    codigo, _ = _pytest()
    if codigo != 0:
        raise SystemExit("ABORTADO: la suite R3 no esta verde antes de mutar.")
    seleccion = [m for m in MUTANTES if not argv or m.ident in argv]
    print("=== F04-D048 R3 · MUTANTES ===")
    muertos = 0
    for m in seleccion:
        veredicto = ejecutar(m)
        muertos += veredicto.startswith("MUERTO")
        print(f"  {m.ident:7}  {veredicto}   [{m.invariante}] -> {m.discriminante}")
    _arbol_limpio()
    print(f"RESULTADO: {muertos}/{len(seleccion)} muertos")
    return 0 if muertos == len(seleccion) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
