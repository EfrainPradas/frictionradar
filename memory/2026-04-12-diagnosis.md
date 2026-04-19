# DIAGNÓSTICO: Por qué 101 empresas fallaron (66%)

## Resumen del análisis

Analizé los datos de `needs_recollection.json` (101 empresas) y `ready_for_review.json` (48 empresas),
comparándolos con el código del pipeline de recolección (`collectors/` y `collection_orchestrator.py`).

## Hallazgos

### Hallazgo 1: Dominios rotos — ~15 empresas descartables

Algunos dominios en el input están **truncados o inválidos** (Wikipedia formatting issue):
- `eb.archive.org` (Dayna Communications — dominio parcial)
- `ahoo.com` (Wahoo Studios — falta la "W")
- `ildworks.com` (WildWorks — falta "W")
- `akeupnow.com` (WakeUpNow — falta "W")
- `ordperfect.com` (WordPerfect — falta "W")
- `inderfarms.com` (Winder Farms — falta "W")

**Impacto**: ~6% del total. Son empresas que nunca tuvieron chance.

### Hallazgo 2: Empresas muertas o sin careers — ~20 empresas

Algunas empresas en la lista de Wikipedia de Utah simplemente no existen más o no tienen web funcional:
- Omniture (adquirida por Adobe en 2012)
- Novell (adquirida por Attachmate en 2011)
- MonaVie (bankrupt en 2015)
- Degreed (headquarters en Pleasanton, CA — no Utah)
- Bluehost (headquarters en Jacksonville, FL)
- Motor Cargo / TForce Freight (no es Utah)

**Impacto**: ~13%. Nunca van a tener careers pages. Son ruido.

### Hallazgo 3: El problema real — Pipeline de recolección demasiado débil (~55 empresas)

Los 4 collectors activos (`CompanySiteCollector`, `CareersCollector`, `AtsPublicCollector`, `NewsroomCollector`)
tienen limitaciones severas:

1. **`CompanySiteCollector`**: solo busca en la homepage.
   - Busca `revops`, `growth`, y links a careers.
   - Si la homepage es SPA (React/Vue), `requests.get()` devuelve HTML vacío → 0 signals.
   - **`DynamicCareersCollector` NO está en `ACTIVE_COLLECTORS`** — está importado pero nunca ejecutado.

2. **`CareersCollector`**: solo intenta `/careers` con `requests.get()`.
   - Sin renderizar JS. Si la careers page usa Greenhouse/Lever/Workday → HTML vacío.
   - No intenta `/jobs`, `/work-here`, `/join-us`, subdominios careers.
   - **Cualquier página que requiera JS rendering produce 0 signals.**

3. **`AtsPublicCollector`**: es un stub que solo detecta `"ats"` en el dominio.
   - En la práctica, **nunca matchea ninguna empresa real**.

4. **`NewsroomCollector`**: solo intenta `/news` con `requests.get()`.
   - Mismo problema de JS rendering.

5. **El `BrowserCaptureService` (Playwright) sí se ejecuta** en el pipeline async,
   pero **falla silenciosamente** cuando:
   - Playwright no está instalado (`playwright install` nunca corrió)
   - El timeout de 10s es muy corto para páginas pesadas
   - Cloudflare/Akamai bloquean headless Chromium
   - La página redirige a un SSO o login

### Hallazgo 4: El problema de los 0 signals vs 1-3 signals

De las 101 needs_recollection:
- **~60 empresas** tienen `signals_count: 0` (falló completamente)
- **~41 empresas** tienen `signals_count: 1-4` pero `extraction_coverage: low`
  (capturaron algo mínimo, no suficiente para superar el umbral)

Las que tienen 1-4 signals son las que el Playwright capturó parcialmente:
- 1-2 signals de company_site (encontró un link "careers" o la palabra "growth")
- Pero el careers extraction completo no funcionó

### Hallazgo 5: Todas las 48 ready_for_review tienen `extraction_coverage: moderate`

Ninguna tiene `extraction_coverage: high`. Todas están en `broad_hiring_pattern_detected`.
Esto confirma que el pipeline captura **hiring breadth pero no depth** (sin descriptions, sin clustering funcional).

---

## Raíz del problema

El pipeline tiene **dos capas de recolección** con capacidades muy diferentes:

```
Capa 1 (Sync, requests): collectors básicos → solo HTML estático → débil
Capa 2 (Async, Playwright): browser_capture_service → JS rendering → fuerte pero frágil
```

La Capa 1 falla para ~66% de empresas porque la mayoría de careers pages requieren JS.
La Capa 2 (Playwright) debería compensar, pero:
- Se ejecuta en un thread fire-and-forget **después** de que el batch ya reportó "completed"
- No hay retry, no hay logging de fallas por empresa, no hay circuit breaker
- Si Playwright no está instalado o crashea, no hay forma de saberlo

---

## Solución propuesta

Ver `COLLECTION_PIPELINE_FIX.md` para la implementación detallada.
