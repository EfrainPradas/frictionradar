# Roadmap de Friction Radar

## Norte del proyecto

Construir un sistema que tome una empresa, lea su presencia publica y su area de careers, y responda tres cosas:

1. Que tipo de empresa es
2. Que tan fuerte es su presion de contratacion
3. Si ya podemos aislar un dolor real y atacar con un perfil especifico desde NovaWork

---

## Fases completadas

### Fase 0 — Definicion del problema
**Estado: Completada**

Entender que queriamos construir. No un job scraper, no otro buscador de vacantes.
Queríamos detectar empresas con demanda real, entender si el dolor se puede aislar, y saber si NovaWork ya puede posicionar un candidato.

### Fase 1 — Base tecnica del sistema
**Estado: Completada**

Backend (FastAPI), base de datos (Supabase/PostgreSQL), endpoints, creacion de companias, collection runs, senales, scoring, company type, dashboard inicial.

### Fase 2 — Primer motor de senales
**Estado: Completada**

Recoleccion de senales publicas basicas: careers page found, newsroom found, growth language, hiring areas visibles, open positions count, job cards visibles.

### Fase 3 — Correccion del modelo de interpretacion
**Estado: Completada**

Anti-hallucination rules, company_type, preliminary vs final verdict, gating para no mostrar dolores especificos sin evidencia suficiente.

### Fase 4 — Scorecard universal
**Estado: Completada**

6 KPIs: Extraction Coverage, Hiring Pressure, Function Concentration, Pain Clarity, Company Type Confidence, Positioning Readiness.

Estados de diagnostico: insufficient_evidence, broad_hiring_pattern_detected, specific_pain_emerging, specific_pain_identified, ready_for_positioning.

### Fase 5 — UI coherente con el scorecard
**Estado: Completada**

Si Pain Clarity es baja no se muestra dolor especifico. Si Positioning Readiness es baja no se muestra attack angle. El scorecard manda.

### Fase 6 — Dynamic careers extraction + Correcciones criticas
**Estado: Completada (2026-04-13)**

#### Problema resuelto
El pipeline tenia un fallo arquitectonico critico: los collectors sync producian senales falsas que bloqueaban a Playwright (el unico extractor capaz de leer sitios modernos con JS). Resultado: 71% de empresas quedaban con evidencia insuficiente.

#### Causa raiz
1. `dynamic_careers` matcheaba keywords genericos ("technology", "sales") en CUALQUIER pagina (incluso homepages), produciendo 3 senales falsas
2. El threshold de Playwright (`sync_signals < 3`) se activaba con senales de baja calidad, bloqueando la extraccion profunda
3. `newsroom` solo probaba paths hardcoded, sin descubrir links reales desde el homepage
4. El QA flag `deep_extraction_skipped_too_early` era demasiado agresivo

#### Correcciones aplicadas
1. **batch_processor.py**: Nuevo threshold basado en CALIDAD de evidencia, no conteo bruto. Playwright corre siempre que no haya careers page verificada o menos de 5 senales reales de careers.
2. **dynamic_careers.py**: Verifica que la URL sea realmente una careers page antes de emitir category signals. Si no es careers page verificada, solo emite position count.
3. **newsroom.py**: Agrega descubrimiento de links de news/blog/press desde el homepage antes de probar paths fijos.
4. **qa_engine.py**: Ajuste del flag `deep_extraction_skipped_too_early` para solo flagear cuando extraction_coverage es genuinamente low.

#### Resultado
Test con 5 empresas que antes eran `needs_recollection`:
- 5/5 pasaron a `ready_for_review`
- 3/5 alcanzaron pain_clarity: HIGH
- Signals promedio paso de 4 a 16

### Fase 8 — Batch analysis / CLI
**Estado: Completada**

CLI (`cli/analyze_companies.py`) que:
- Lee JSON de empresas
- Analiza una por una con pipeline completo
- Soporta resume (`--resume`)
- Soporta re-procesamiento por status (`--only-status needs_recollection`)
- QA cross-company checks
- Tiering automatico (tier_1 a tier_4)
- Output estructurado en archivos JSON separados por tier

### Fase 9 — Dataset de empresas objetivo
**Estado: Completada**

`tools/data/utah_companies.json`: 159 empresas de Utah con domain, industry, location, source (Wikipedia categories).

---

## Fase actual

### Fase 6.1 — Re-evaluacion completa del batch de Utah
**Estado: En progreso**

Re-corriendo las 159 empresas con las correcciones de Fase 6. Esperado: reduccion dramatica de `needs_recollection` (de 71% a <20%).

---

## Fases pendientes

### Fase 7 — Job Description Intelligence
**Estado: Proximo paso principal**

El gran cuello de botella actual. El sistema detecta demanda de hiring pero no aisla el dolor dominante en la mayoria de casos.

#### Que debe hacer:
1. **Extraer titulos reales** — Supply Chain Analyst, Finance Manager, Operations Coordinator
2. **Extraer job descriptions** — No cientos; solo suficientes para detectar patrones
3. **Clasificar funciones** — supply chain, operations, finance, analytics, retail, manufacturing, recruiting
4. **Detectar familias repetidas** — 6 roles de operations, 5 de supply chain planning, 4 de data/reporting
5. **Recalcular scorecard** — Mover empresas de `broad_hiring_pattern_detected` a `specific_pain_emerging` o `ready_for_positioning`

#### Implementacion sugerida:
- Playwright ya extrae `visible_role_cards` y los persiste en `company_job_roles`
- Falta: clasificador de functional_area mas robusto (puede ser rule-based o LLM-light)
- Falta: agregacion de hiring_patterns (top functional areas, capability themes)
- Falta: recalculo de Function Concentration y Pain Clarity basado en job roles

#### Sprint sugerido:
1. Mejorar `hybrid_careers_extractor` para extraer titulos + areas funcionales de las job cards
2. Crear `functional_area_classifier` (rule-based con fallback LLM)
3. Crear `hiring_pattern_aggregator` que calcule concentracion por area
4. Actualizar `company_evaluation` para usar hiring_patterns en Function Concentration y Pain Clarity
5. Re-correr batch y medir cuantas empresas suben a `specific_pain_emerging`

### Fase 10 — Positioning engine para NovaWork
**Estado: Posterior a Fase 7**

Solo debe activarse cuando:
- Hiring Pressure es real
- Pain Clarity es al menos moderate
- Function Concentration es suficiente
- Positioning Readiness no es low

El sistema responde: donde atacar, con que tipo de perfil, con que lenguaje posicionarlo.

### Fase 11 — Workflow comercial real
**Estado: Fase futura**

Usar Friction Radar como herramienta estrategica de NovaWork:
- Empresa priorizada
- Dolor detectado
- Tipo de perfil recomendado
- Angulo de ataque
- Posicionamiento sugerido
- Eventualmente outreach support

---

## Donde estamos hoy

### Ya resolvimos:
- Que es el producto
- Como debe pensar
- Como no alucinar
- Como evaluar empresas de forma generica
- Como separar hiring pressure de pain clarity
- Como leer correctamente cualquier empresa (no solo Nike o Maersk)
- Como hacer batch analysis a escala
- **Como recolectar evidencia suficiente de cualquier sitio web** (Fase 6 fix)

### Lo que falta para desbloquear valor real:
**Job Description Intelligence (Fase 7)** — La llave de todo.

Cuando eso este listo, el sistema podra decir con confianza:
- "Esta empresa tiene dolor en supply chain operations"
- "Necesita un perfil de Data Analyst con experiencia en reporting unificado"
- "El angulo de ataque es: fragmentacion de metricas entre marketing y producto"

---

## Resumen en una frase

Ya resolvimos como piensa Friction Radar y como recolecta evidencia de cualquier empresa.
Ahora toca alimentarlo con job description intelligence para que pueda aislar dolores reales y recomendar perfiles con confianza.
