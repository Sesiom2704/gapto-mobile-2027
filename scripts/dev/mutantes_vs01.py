# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_vs01.py
# Ruta: scripts/dev/mutantes_vs01.py
# Descripcion: Arnes de mutacion de VS-01 (adaptador HTTP + cliente movil).
#   Demuestra que los tests de tests/api y mobile/__tests__ discriminan los
#   mecanismos que afirman (WM 12C.2). Cumple D-181/D-192:
#     - cada mutante declara transformacion (texto exacto, 1 ocurrencia) y
#       discriminante (suite que debe fallar);
#     - E/S byte a byte; journal durable ANTES de tocar el primer byte;
#     - al arrancar, si hay journal pendiente: restaura, verifica y aborta;
#     - preflight verde de ambas suites antes del primer mutante;
#     - tras cada mutante se restaura y verifica identidad byte-exacta;
#     - un veredicto unico por mutante: MUERTO | VIVO | NO_CLASIFICABLE.
#   Requiere GAPTO_TEST_DATABASE_URL (base local desechable) y node_modules
#   instalados en mobile/. No es evidencia de proveedor.
#   v0.2.0 (F05-D003): A02 apunta a la financiacion sellada; mutantes nuevos
#   A11..A20 (lock de cuenta, lectura fuera de la transaccion, recalculo en
#   reintento, revalidacion antes de identidad, agregado exacto, fecha,
#   vigencia en la fecha del pago, importe de la propuesta, propuesta de
#   cuentas-pago, fail-closed de identidad) y M09..M12 (cliente).
# Version: 0.2.0
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_vs01.journal.json"

PY = [sys.executable, "-m", "pytest", "tests/api", "-q", "-x", "-p", "no:cacheprovider", "--rootdir=tests/api"]
JS = ["npx", "jest", "--silent"]

# (id, fichero, texto_original, texto_mutado, suite_discriminante)
MUTANTES = [
    ("A01", "backend/app/api/traductor_gasto_pagado.py", "presupuestable=intencion.presupuestable", "presupuestable=True", "py"),
    ("A02", "backend/app/api/traductor_gasto_pagado.py", 'if intencion.financiacion.estado == "PROPUESTA_ACEPTADA":', "if True:", "py"),
    ("A03", "backend/app/api/traductor_gasto_pagado.py", 'if intencion.atribucion == "SOLO_MIO":', "if True:", "py"),
    ("A04", "backend/app/api/traductor_gasto_pagado.py", 'return uuid.uuid5(intencion, f"gapto.vs01.gasto_pagado.{rol}")', "return uuid.uuid4()", "py"),
    ("A05", "backend/app/api/lecturas_vs01.py", '"PARCIAL" if (sin_reparto or otra_moneda) else "CONFIRMADO"', '"CONFIRMADO"', "py"),
    ("A06", "backend/app/api/lecturas_vs01.py", "WHERE ef.moneda = 'EUR' AND ef.estado_atribucion = 'COMPLETA'", "WHERE ef.estado_atribucion = 'COMPLETA'", "py"),
    ("A07", "backend/app/api/app.py", "if not hmac.compare_digest(cabecera.encode(), esperado.encode()):", "if False:", "py"),
    ("A08", "backend/app/api/app.py", "    verificar_base_permitida(nombre, cfg)\n", "    pass\n", "py"),
    ("A09", "backend/app/api/dto_vs01.py", 'model_config = ConfigDict(extra="forbid", frozen=True)', 'model_config = ConfigDict(extra="ignore", frozen=True)', "py"),
    ("A10", "backend/app/api/errores_http.py", '"No se ha podido confirmar el registro. Puedes reintentar: no se duplicará.",\n        True,', '"No se ha podido confirmar el registro. Puedes reintentar: no se duplicará.",\n        False,', "py"),
    ('A11', 'backend/app/api/ejecucion_gasto_pagado.py', '"SELECT id FROM gapto.cuentas WHERE id = %s FOR NO KEY UPDATE"', '"SELECT id FROM gapto.cuentas WHERE id = %s"', 'py'),
    ('A12', 'backend/app/api/ejecucion_gasto_pagado.py', '        # 1. Lock contractual de la cuenta.\n        bloquear_cuenta(sesion, intencion.cuenta_id)\n        actor = leer_actor_self(sesion)\n\n        # 2. Identidad antes que cualquier revalidacion contextual.\n        ya_materializada = repo_hechos.leer_estado(sesion, intencion.intencion_id) is not None\n\n        if not ya_materializada:\n            # 3. Intencion nueva: relectura bajo el lock.\n            _validar_cuenta_nueva(sesion, intencion)\n            # 4. Revalidacion de la propuesta sellada, en la fecha del pago.\n            if intencion.financiacion.estado == "PROPUESTA_ACEPTADA" and not participacion_self_100(\n                sesion, intencion.cuenta_id, actor, intencion.fecha_hecho\n            ):\n                return RechazoIntegracion(CODIGO_PROPUESTA_OBSOLETA)\n', '        # 1. Lock contractual de la cuenta.\n        actor = leer_actor_self(sesion)\n        _previa = participacion_self_100(sesion, intencion.cuenta_id, actor, intencion.fecha_hecho)\n        bloquear_cuenta(sesion, intencion.cuenta_id)\n\n        # 2. Identidad antes que cualquier revalidacion contextual.\n        ya_materializada = repo_hechos.leer_estado(sesion, intencion.intencion_id) is not None\n\n        if not ya_materializada:\n            # 3. Intencion nueva: relectura bajo el lock.\n            _validar_cuenta_nueva(sesion, intencion)\n            # 4. Revalidacion de la propuesta sellada, en la fecha del pago.\n            if intencion.financiacion.estado == "PROPUESTA_ACEPTADA" and not _previa:\n                return RechazoIntegracion(CODIGO_PROPUESTA_OBSOLETA)\n', 'py'),
    ('A13', 'backend/app/api/ejecucion_gasto_pagado.py', '        datos = componer(intencion, actor)\n', "        _int = intencion\n        if not participacion_self_100(sesion, intencion.cuenta_id, actor, intencion.fecha_hecho):\n            _int = intencion.model_copy(update={'financiacion': __import__('app.api.dto_vs01', fromlist=['x']).FinanciacionNoDeterminada(estado='NO_DETERMINADA')})\n        datos = componer(_int, actor)\n", 'py'),
    ('A14', 'backend/app/api/ejecucion_gasto_pagado.py', '        if not ya_materializada:\n', '        if True:\n', 'py'),
    ('A15', 'backend/app/api/ejecucion_gasto_pagado.py', '        if ya_materializada and not _agregado_sin_extras(sesion, datos):\n', '        if False:\n', 'py'),
    ('A16', 'backend/app/api/dto_vs01.py', '        if valor > hoy_referencia():\n', '        if False:\n', 'py'),
    ('A17', 'backend/app/api/ejecucion_gasto_pagado.py', '                sesion, intencion.cuenta_id, actor, intencion.fecha_hecho\n            ):\n                return RechazoIntegracion', "                sesion, intencion.cuenta_id, actor, __import__('datetime').date.today()\n            ):\n                return RechazoIntegracion", 'py'),
    ('A18', 'backend/app/api/dto_vs01.py', '            and self.financiacion.importe != self.importe\n', '            and False\n', 'py'),
    ('A19', 'backend/app/api/lecturas_vs01.py', '"SELF_100" if participacion_self_100(sesion, f[0], actor, fecha) else "NO_DETERMINADA"', '"SELF_100"', 'py'),
    ('A20', 'backend/app/api/configuracion.py', '    if entorno != ENTORNO_UNICO_PERMITIDO:\n', '    if False:\n', 'py'),
    ("M01", "mobile/src/state/useEnvioGasto.ts", "if (enVuelo.current) return; // doble tap", "if (false) return; // doble tap", "js"),
    ("M02", "mobile/src/state/useEnvioGasto.ts", "      if (selladaRef.current) {\n        // Intención", "      if (false) {\n        // Intención", "js"),
    ("M03", "mobile/src/domain/intencion.ts", "presupuestable: null,\n    soloMio", "presupuestable: true,\n    soloMio", "js"),
    ("M04", "mobile/src/domain/intencion.ts", "soloMio: false,", "soloMio: true,", "js"),
    ("M05", "mobile/App.tsx", "if (registrado) setRefresco((n) => n + 1);", "if (false) setRefresco((n) => n + 1);", "js"),
    ("M06", "mobile/src/state/useEnvioGasto.ts", "} else if (r.tipo === 'RECHAZADO') {", "} else if (false) {", "js"),
    ("M07", "mobile/src/api/cliente.ts", "      return { tipo: 'INDETERMINADO', mensaje: esEscritura ? MSG_INDETERMINADO : MSG_SIN_CONEXION };\n    } catch {", "      return { tipo: 'RECHAZADO', codigo: 'X', mensaje: '' } as any;\n    } catch {", "js"),
    ("M08", "mobile/src/domain/importe.ts", "if (dec.length > 2) return { ok: false, motivo: 'DECIMALES' };", "", "js"),
    ('M09', 'mobile/src/domain/intencion.ts', "if (b.propuesta === 'SELF_100' && !b.propuestaRechazada) {", "if (b.propuesta === 'SELF_100') {", 'js'),
    ('M10', 'mobile/src/domain/intencion.ts', "  else if (b.fechaHecho > hoyIso) e.fecha = 'Solo gastos ya ocurridos: la fecha no puede ser futura.';\n", '', 'js'),
    ('M11', 'mobile/src/screens/RegistroGastoScreen.tsx', '  }, [b.fechaHecho]);', '  }, []);', 'js'),
    ('M12', 'mobile/src/screens/HomeScreen.tsx', '          <Columna etiqueta="Gastos">\n            <EstadoDato estado="NO_DISPONIBLE" />\n          </Columna>', '          <Columna etiqueta="Gastos">\n            <CeldaGastos lectura={gasto} onReintentar={cargar} />\n          </Columna>', 'js'),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(suite: str) -> int:
    if suite == "py":
        return subprocess.run(PY, cwd=RAIZ, capture_output=True).returncode
    return subprocess.run(JS, cwd=RAIZ / "mobile", capture_output=True).returncode


def recuperar_si_pendiente() -> bool:
    if not JOURNAL.exists():
        return False
    j = json.loads(JOURNAL.read_text(encoding="utf-8"))
    ruta = RAIZ / j["fichero"]
    original = bytes.fromhex(j["original_hex"])
    ruta.write_bytes(original)
    if sha(ruta.read_bytes()) != j["sha256"]:
        sys.exit("RECUPERACION FALLIDA: identidad no verificada")
    JOURNAL.unlink()
    return True


def main() -> None:
    if recuperar_si_pendiente():
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    for suite in ("py", "js"):
        if correr(suite) != 0:
            sys.exit(f"PREFLIGHT ROJO en suite {suite}: no se muta nada.")
    veredictos = []
    for mid, fichero, a, b, suite in MUTANTES:
        ruta = RAIZ / fichero
        original = ruta.read_bytes()
        texto = original.decode("utf-8")
        if texto.count(a) != 1:
            veredictos.append((mid, "NO_CLASIFICABLE", "transformacion no aplicable"))
            continue
        JOURNAL.write_text(json.dumps({"fichero": fichero, "original_hex": original.hex(), "sha256": sha(original)}), encoding="utf-8")
        os.sync() if hasattr(os, "sync") else None
        try:
            ruta.write_bytes(texto.replace(a, b).encode("utf-8"))
            rc = correr(suite)
            v = "MUERTO" if rc != 0 else "VIVO"
        finally:
            ruta.write_bytes(original)
            ok = sha(ruta.read_bytes()) == sha(original)
            JOURNAL.unlink(missing_ok=True)
        veredictos.append((mid, v if ok else "NO_CLASIFICABLE", suite))
    for v in veredictos:
        print(*v)
    print("RESUMEN", sum(1 for v in veredictos if v[1] == "MUERTO"), "/", len(veredictos), "muertos")
    sys.exit(0 if all(v[1] == "MUERTO" for v in veredictos) else 1)


if __name__ == "__main__":
    main()
