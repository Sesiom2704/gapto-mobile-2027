# Categorías sugeridas (onboarding F05-03, A8/R5) — versión 1 APROBADA

**Estado:** APROBADA por Moisés el 2026-10-09 sin cambios sobre la propuesta v0.1. Decisiones de la validación: «IRPF / Renta» = AMBOS; el seguro de hogar se mantiene en Seguros › Hogar y los nombres no se cambian (el fichero coincide con el árbol de Migration V3).

**Origen:** árbol baseline de Migration V3 §15.2 («Estado del árbol inicial»), sin cambios de nombres ni de jerarquía. 93 categorías: 23 grupos y 70 subcategorías.

**Qué se ha validado:**

- **Ámbito:** GASTO, INGRESO o AMBOS. Controla en qué registros se puede elegir la categoría; no cambia la naturaleza económica.
- **Presupuesto por defecto:** `presupuestable_default`. Es el valor por defecto de la categoría (C06). No es una propuesta del registro (E4 de F05-D026), que sigue preguntando «¿Cuenta para el presupuesto?».
- **Icono:** clave de la biblioteca v1 de F09 §12.97.9, solo claves publicadas. Si no hay un glifo propio, se usa el más cercano y se indica en la nota.

**Reglas que no hay que validar:**

- **Orden:** el de la tabla.
- **Clave estable:** `codigo` = `sug.` + nombre normalizado, único por owner; sirve para reconocer el reintento (idempotencia por estado de R5).
- **Versión del fichero:** 1. En B2, Claude Code convierte esta tabla, sin cambiar ningún valor, en el fichero versionado del repositorio y entrega su SHA-256; cualquier diferencia de contenido es STOP.

**Resumen de la propuesta:**

- **Ámbito:**
  - INGRESO: los 4 grupos de ingresos y sus hijos (9 nodos).
  - AMBOS: Alquileres e IRPF / Renta (decididos).
  - GASTO: el resto (82 nodos).
- **Presupuesto = No** en 12 nodos:
  - extraordinarios: Derramas, Mejoras y reforma, Multas;
  - IRPF / Renta;
  - costes financieros (2);
  - ingresos irregulares o no corrientes: Trabajos esporádicos, Prestaciones, Desempleo, Rendimientos (2), Venta de bienes.
- **Presupuesto = Sí** en el resto.

**Puntos a comprobar en B2 (no cambian el contenido aprobado):**

1. IRPF / Renta queda como AMBOS bajo un padre GASTO. Hay que confirmar en el selector de F05-01 cómo se navega a un hijo elegible para INGRESO bajo un padre que no lo es. Si da problemas: STOP y decisión de Moisés (no se corrige en silencio).
2. «Hogar» aparece dos veces en el árbol: en Seguros (seguro de hogar) y dentro de «Vivienda y hogar». Son padres distintos y no hay colisión de nombres. Se mantienen los nombres (decisión de Moisés): el selector muestra siempre la ruta completa.

| # | Categoría | Ámbito | Presupuesto por defecto | Icono (clave v1) | Nota |
|---|---|---|---|---|---|
| 1 | **Supermercados** | GASTO | Sí | `compras.carrito` |  |
| 2 | **Restaurantes** | GASTO | Sí | `comida.restaurante` | Restaurantes, bares, pubs (Migration V3) |
| 3 | **Vivienda y hogar** | GASTO | Sí | `hogar.casa` |  |
| 4 | — Suministros | GASTO | Sí | `hogar.luz` |  |
| 5 | — — Electricidad | GASTO | Sí | `hogar.luz` |  |
| 6 | — — Agua | GASTO | Sí | `hogar.agua` |  |
| 7 | — — Alarma y seguridad | GASTO | Sí | `finanzas.seguro` |  |
| 8 | — Comunidad | GASTO | Sí | `hogar.casa` |  |
| 9 | — — Cuota de comunidad | GASTO | Sí | `hogar.casa` |  |
| 10 | — — Derramas | GASTO | No | `hogar.casa` | Extraordinario |
| 11 | — Limpieza doméstica | GASTO | Sí | `hogar.casa` | Sin glifo propio en la biblioteca v1 |
| 12 | — Reparaciones y mantenimiento | GASTO | Sí | `hogar.reparaciones` |  |
| 13 | — Mejoras y reforma | GASTO | No | `hogar.reparaciones` | Extraordinario; mejor con contexto |
| 14 | — Equipamiento del hogar | GASTO | Sí | `hogar.casa` |  |
| 15 | **Movilidad** | GASTO | Sí | `transporte.coche` |  |
| 16 | — Combustible | GASTO | Sí | `transporte.coche` | Sin surtidor en la biblioteca v1 |
| 17 | — Peajes | GASTO | Sí | `transporte.coche` |  |
| 18 | — Parking | GASTO | Sí | `transporte.coche` |  |
| 19 | — Transporte | GASTO | Sí | `transporte.bus` |  |
| 20 | — — Vuelos | GASTO | Sí | `transporte.avion` |  |
| 21 | — — Tren | GASTO | Sí | `transporte.bus` | Sin tren en la biblioteca v1 |
| 22 | — — Barco | GASTO | Sí | `transporte.viaje` | Sin barco en la biblioteca v1 |
| 23 | — — Autobús | GASTO | Sí | `transporte.bus` |  |
| 24 | — — Metro | GASTO | Sí | `transporte.bus` | Sin metro en la biblioteca v1 |
| 25 | — — Coche compartido | GASTO | Sí | `transporte.coche` |  |
| 26 | — Mantenimiento y cuidado del vehículo | GASTO | Sí | `hogar.reparaciones` |  |
| 27 | — Accesorios y equipamiento | GASTO | Sí | `transporte.coche` |  |
| 28 | **Alojamiento** | GASTO | Sí | `transporte.viaje` |  |
| 29 | **Salud** | GASTO | Sí | `salud.corazon` |  |
| 30 | — Farmacia | GASTO | Sí | `salud.farmacia` |  |
| 31 | — Fisioterapia | GASTO | Sí | `salud.corazon` |  |
| 32 | — Psicología | GASTO | Sí | `salud.corazon` |  |
| 33 | — Nutrición | GASTO | Sí | `salud.corazon` |  |
| 34 | — Dental | GASTO | Sí | `salud.corazon` |  |
| 35 | **Deporte** | GASTO | Sí | `salud.deporte` |  |
| 36 | — Gimnasio | GASTO | Sí | `salud.deporte` |  |
| 37 | — Natación | GASTO | Sí | `salud.deporte` |  |
| 38 | — Buceo | GASTO | Sí | `salud.deporte` |  |
| 39 | — Entrenamiento personal | GASTO | Sí | `salud.deporte` |  |
| 40 | — Carreras y competiciones | GASTO | Sí | `salud.deporte` |  |
| 41 | — Material y equipamiento deportivo | GASTO | Sí | `salud.deporte` |  |
| 42 | — Suplementos | GASTO | Sí | `salud.deporte` |  |
| 43 | — Cuotas y licencias deportivas | GASTO | Sí | `salud.deporte` |  |
| 44 | **Cuidado personal** | GASTO | Sí | `personal.peluqueria` |  |
| 45 | — Peluquería | GASTO | Sí | `personal.peluqueria` |  |
| 46 | — Estética | GASTO | Sí | `personal.peluqueria` |  |
| 47 | **Ropa y complementos** | GASTO | Sí | `compras.ropa` |  |
| 48 | — Ropa y calzado | GASTO | Sí | `compras.ropa` |  |
| 49 | — Complementos personales | GASTO | Sí | `compras.ropa` |  |
| 50 | **Tecnología e informática** | GASTO | Sí | `personal.movil` |  |
| 51 | — Accesorios y periféricos | GASTO | Sí | `personal.movil` |  |
| 52 | **Ocio y cultura** | GASTO | Sí | `ocio.musica` |  |
| 53 | — Actividades | GASTO | Sí | `ocio.musica` |  |
| 54 | — Horticultura | GASTO | Sí | `hogar.casa` | Candidato en Migration V3 §15 |
| 55 | — Videojuegos | GASTO | Sí | `personal.movil` | Sin mando en la biblioteca v1 |
| 56 | — Cine y vídeo | GASTO | Sí | `ocio.cine` |  |
| 57 | — Streaming | GASTO | Sí | `ocio.cine` |  |
| 58 | — Libros y cómics | GASTO | Sí | `ocio.libro` |  |
| 59 | — Juegos y ocio | GASTO | Sí | `ocio.musica` |  |
| 60 | — Eventos y espectáculos | GASTO | Sí | `ocio.musica` |  |
| 61 | — Lotería | GASTO | Sí | `finanzas.dinero` |  |
| 62 | **Regalos y detalles** | GASTO | Sí | `ocio.regalo` |  |
| 63 | **Formación** | GASTO | Sí | `personal.educacion` |  |
| 64 | — Idiomas | GASTO | Sí | `personal.educacion` |  |
| 65 | — Cursos y formación | GASTO | Sí | `personal.educacion` |  |
| 66 | **Comunicaciones y digital** | GASTO | Sí | `hogar.internet` |  |
| 67 | — Telefonía e internet | GASTO | Sí | `hogar.internet` |  |
| 68 | — Software y servicios digitales | GASTO | Sí | `finanzas.suscripcion` |  |
| 69 | — Plataformas digitales | GASTO | Sí | `finanzas.suscripcion` |  |
| 70 | **Seguros** | GASTO | Sí | `finanzas.seguro` |  |
| 71 | — Hogar | GASTO | Sí | `finanzas.seguro` | Seguro de hogar (no confundir con Vivienda y hogar) |
| 72 | — Vida | GASTO | Sí | `finanzas.seguro` |  |
| 73 | — Mascotas | GASTO | Sí | `personal.mascota` |  |
| 74 | — Viaje | GASTO | Sí | `finanzas.seguro` |  |
| 75 | **Administración, impuestos y tasas** | GASTO | Sí | `finanzas.impuestos` |  |
| 76 | — IBI | GASTO | Sí | `finanzas.impuestos` |  |
| 77 | — IRPF / Renta | AMBOS | No | `finanzas.impuestos` | AMBOS (decidido): la declaración puede salir a pagar o a devolver |
| 78 | — Documentación y trámites | GASTO | Sí | `finanzas.impuestos` |  |
| 79 | — Licencias y tasas | GASTO | Sí | `finanzas.impuestos` |  |
| 80 | — Multas y sanciones | GASTO | No | `finanzas.impuestos` | Imprevisible |
| 81 | **Servicios profesionales** | GASTO | Sí | `finanzas.impuestos` |  |
| 82 | **Costes financieros** | GASTO | No | `finanzas.dinero` |  |
| 83 | — Intereses y costes de financiación | GASTO | No | `finanzas.dinero` | Coste de deuda; F07 |
| 84 | **Ingresos laborales** | INGRESO | Sí | `finanzas.dinero` |  |
| 85 | — Nómina | INGRESO | Sí | `finanzas.dinero` |  |
| 86 | — Dietas y complementos | INGRESO | Sí | `finanzas.dinero` |  |
| 87 | — Trabajos esporádicos | INGRESO | No | `finanzas.dinero` | Irregular |
| 88 | **Prestaciones** | INGRESO | No | `finanzas.dinero` |  |
| 89 | — Desempleo | INGRESO | No | `finanzas.dinero` |  |
| 90 | **Alquileres** | AMBOS | Sí | `hogar.casa` | AMBOS: decidido por Moisés |
| 91 | **Rendimientos financieros** | INGRESO | No | `finanzas.dinero` |  |
| 92 | — Intereses de cuentas e inversiones | INGRESO | No | `finanzas.dinero` |  |
| 93 | **Venta de bienes** | INGRESO | No | `finanzas.dinero` | Irregular |