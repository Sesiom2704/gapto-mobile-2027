# capturas_g5_web_b11_v0.5.2.py — herramienta de capturas G5 (oscuro + Dynamic Type emulado)

GAPTO MOBILE 2027 · F06-M1 Tokens, V1 con anillo (F06-D003) · dictamen PT-06 y PT-07 del 2026-11-05 · rigor N1 (D-181). Versión 0.5.2 del 2026-11-06 (F06 MANT-TOKENS-RUTAS).

## 0. Cambio de 0.5.1 a 0.5.2
- **Motivo:** la 0.5.1 llevaba rutas absolutas de la máquina y rompía `tests/migration/test_rv3_000_repo_sin_datos_v3.py::test_sin_secretos_ni_rutas_locales_en_texto[ruta_absoluta_windows]` en `d12ea3b` (errata `ERRATA_F06-M1-TOKENS`).
- **0.5.1 (sustituida):** 64686 bytes, SHA-256 `fa5df9eb25374b0e8882d9d0bcc99cdd53a4a02c8fa835a5661846f49d7f87f9`. Es la versión con la que se tomaron las 182 capturas de Tokens; esa evidencia no cambia. Sale del árbol porque `test_rv3_000` recorre todo el repositorio, pero se recupera byte a byte con `git show d12ea3b:scripts/dev/capturas_g5_web_b11_v0.5.1.py` (y su LEEME con `git show d12ea3b:scripts/dev/capturas_g5_web_b11_v0.5.1_LEEME.md`).
- **Qué cambia:** la cabecera; `import os`; el import de `e2e_vs01` (de `scripts/dev/` o de `GAPTO_CAPTURAS_E2E_DIR`); y los valores por defecto de `--dist`, `--token-fichero`, `--pantallas` y `--salida`. `--token-fichero` pasa a ser obligatorio cuando no hay variable. Recetas, detector, variantes, estados, nombres de fichero y JSON no cambian.

| Parámetro | Variable de entorno | Valor por defecto |
|---|---|---|
| `--dist` | `GAPTO_CAPTURAS_DIST` | `<repo>/mobile/dist` |
| `--token-fichero` | `GAPTO_CAPTURAS_TOKEN_FICHERO` | ninguno (obligatorio; el token no vive en el repositorio) |
| `--pantallas` | `GAPTO_CAPTURAS_PANTALLAS` | `scripts/dev/capturas_g5_PANTALLAS_51.json` |
| `--salida` | `GAPTO_CAPTURAS_SALIDA` | `<padre del repo>/evidencia_capturas_g5/web` (fuera del repositorio) |
| import de `e2e_vs01` | `GAPTO_CAPTURAS_E2E_DIR` | el directorio del script (`scripts/dev/`) |

El resto de este LEEME es el de 0.5.1, con las rutas de origen ya sin la unidad de la máquina.

**EVIDENCIA WEB/VIEWPORT — NO EVIDENCIA iOS. El Dynamic Type es EMULADO y no acredita Dynamic Type nativo.**

## 1. Qué se incorpora y por qué así
| Fichero | Bytes | SHA-256 | Nota |
|---|---|---|---|
| `scripts/dev/capturas_g5_web_b11_v0.5.2.py` | 66021 | `8d93be60b02556fa7052463c02704d42000d1a1c263d4e9fd1e2e4e4643e9c0c` | herramienta congelada 0.5.2 (§0). No se edita: cualquier cambio exige versión nueva con su SHA |
| `scripts/dev/capturas_g5_PANTALLAS_51.json` | 5207 | `5918bc390369ab3aa5485962eeb418a3297e9b2c09dd739c3b46f36b43fe7640` | inventario congelado de las 51 pantallas G5 (origen `evidencia_f0507_g15/pre_final/PANTALLAS_51.json`, fuera del repositorio) |

En 0.5.1 la cabecera congelada conservaba las rutas de origen para no cambiar su SHA. En 0.5.2 la cabecera GAPTO ya da la ruta real en el repositorio.

## 2. Comparación con la versión de origen (PT-06.2 y PT-06.3)
- **Origen:** `capturas_g5_web.py` 0.5.0 de G5, SHA-256 `0346007b10c5f42f9f46c497a0a8438fb0b2db6c53def021c726f60ef8823e1f`.
- **Comparación:** el cuerpo funcional de 0.5.1 (desde la primera línea `# ====`) frente a 0.5.0 difiere en **3 líneas y nada más**, todas de la variante B11:
  1. `Ctx.cap`: `if self.variante == "dt"` pasa a `if self.variante in ("dt", "oscuro_dt")`. La emulación DT se reaplica antes de cada captura también en oscuro + DT.
  2. `main`: `color_scheme="dark" if variante == "oscuro"` pasa a `... in ("oscuro", "oscuro_dt")`.
  3. `main`: `if variante == "dt": ctx.add_init_script(DT_JS)` pasa a `if variante in ("dt", "oscuro_dt")`.
- **Diferencias de comportamiento:** solo se añade la variante `oscuro_dt`, que combina el esquema oscuro con la emulación DT ×1,35. Las variantes `claro`, `oscuro` y `dt` se comportan igual que en 0.5.0.
- **Resto:** recetas, detector, criterios de estado, nombres de fichero y JSON no cambian.
- **Limitación conocida:** el JSON de salida sigue declarando `"version_script": "0.5.0"`, porque esa línea no se tocó al congelar. La versión real se identifica por el SHA del fichero.

## 3. Dependencias y parámetros fijados (PT-06.4)
| Elemento | Valor |
|---|---|
| Python | 3.13.4 |
| Playwright (pip) | 1.63.0, con Chromium 153.0.8010.12 (`pw.chromium.launch()`, sin cabeza) |
| `e2e_vs01.py` | `LAYOUT_JS`, `fallos_layout`, `ELIPSIS_AUTORIZADA` y `servidor_web`. En 0.5.1 el import fijo apuntaba al worktree `wt_v25_mpg` (d11bc78); en 0.5.2 se importa de `scripts/dev/` del propio repositorio. Ese fichero es idéntico al de `scripts/dev/e2e_vs01.py` de este repositorio (SHA-256 `b131adbb0d6b3ebf2d71a2d299c8feb2d30d4db6a203e91fcebb394a25ed3c25`) |
| Viewport | 393 × 852 CSS px, `device_scale_factor=3`, `locale="es-ES"`, `timezone_id="Europe/Madrid"` |
| Variantes | `claro` (light), `oscuro` (dark), `dt` (light + DT ×1,35) y `oscuro_dt` (dark + DT ×1,35), con `FACTOR_DT = 1.35` |
| Tiempos | timeout por defecto de 10 s; 30 s para esperar Inicio |
| Puertos por defecto | API 5468, web 5469 |
| Argumentos que se pasan siempre en el gate | `--dist`, `--token-fichero`, `--pantallas`, `--salida`, `--variantes claro,oscuro,dt,oscuro_dt` y `--json` (en 0.5.1 los valores por defecto apuntaban a rutas de G5 fuera del repositorio; en 0.5.2, ver §0) |

## 4. Un fallo nunca es PASS (PT-06.5)
La herramienta no tiene ningún estado PASS. Estados posibles por fila y variante:
- **CAPTURADA:** hay al menos una captura y todas tienen `detector_ok` y la acreditación por testID visible. Los fallos de layout del detector se registran en el JSON y se valoran aparte; no cambian el estado.
- **PENDIENTE:** sin capturas; alguna captura sin acreditar o con el detector fallido; `NoCapturada` (ruta no alcanzada); o cualquier excepción de la receta.
- **NO APLICA:** solo G5-07 y G5-51, fijas en `NO_APLICA` (decisiones D3 y D4).

Pruebas en negativo, guardadas en la evidencia del gate (`PT06/negativo/`):
1. **Export sin la app** (un `index.html` sin la aplicación), con G5-01, G5-02 y G5-07 en claro y en oscuro + DT. Resultado:
   - G5-01 y G5-02 quedan PENDIENTE en las dos variantes («fallo: TimeoutError»), con 0 capturas acreditadas y la captura `*_estado_al_fallar.png`;
   - G5-07 queda NO APLICA;
   - ninguna fila queda CAPTURADA.
2. **Export vacío** (sin `index.html`): la herramienta aborta antes de capturar («el servidor web del E2E no responde») y no escribe resultados.

El código de salida es 0 aunque haya PENDIENTES. El resultado se lee siempre del JSON, nunca del código de salida.

## 5. Limitaciones (PT-06.6)
- **WEB/VIEWPORT:** Chromium sobre el export web de Expo, no iOS.
- **Dynamic Type emulado:** escala `font-size` y `line-height` ×1,35 por script inyectado (`DT_JS`). No acredita el Dynamic Type nativo de iOS.
- **Condiciones de datos (PT-07):** G5-05, G5-22, G5-41 y G5-48 (DT) quedan PENDIENTE por causas de datos o del detector. Se registran una a una en el informe del gate y nunca pasan a PASS ni a NO APLICA.

## 6. Credenciales (PT-06.7)
- **Token:** se lee de `--token-fichero` y solo viaja en la cabecera `Authorization` de las llamadas a la API. No se imprime ni se escribe en el JSON ni en los registros.
- **Export web:** `EXPO_PUBLIC_*` lleva incrustado el token de desarrollo sintético. Por eso el export y los PNG se quedan en la evidencia local y no van a Drive.
- **Comprobación del gate:** se busca el token en todos los artefactos de salida (JSON, registros e índice) y debe dar 0 apariciones.
