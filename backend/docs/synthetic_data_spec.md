# Synthetic Data Spec — FrictionRadar v1

> Contrato de diseño para generar el dataset sintético a partir del export real
> de companies/domains/roles. Este documento alinea **arquetipos** y
> **ground-truth schema** ANTES de escribir código generador.
>
> Estado: borrador para aprobación de Efrain.
> Versión: `synthetic-spec-v1` (bump al cambiar invariantes).

---

## 0. Vocabularios invariantes (NO inventar valores)

Todos los campos siguientes son enums cerrados verificados en el código actual.
Cualquier dato sintético DEBE usar exactamente estos valores — el motor real
hace `in_(...)` exact-match contra la mayoría.

### 0.1 `companies.inferred_sector`
`smart_match_engine._prefilter_candidates` filtra exact-match.
Fuente canónica: `app/services/sector_inference.py:22-40` (17 sectores).
Verificado contra DB real el 2026-04-27 — todos están presentes.
```
Software & SaaS
AI & Machine Learning
Semiconductors & Hardware
Fintech & Financial Services
Ecommerce & Consumer
Healthcare & Biotech
Media & Entertainment
Gaming
Retail & Hospitality
Manufacturing & Industrial
Logistics & Transportation
Telco & Internet Infra
Education
Real Estate & Construction
Energy & Utilities
Professional Services
Other
```

### 0.2 `diagnostic_state`
De `company_evaluation.py:17-23`:
```
insufficient_evidence
broad_hiring_pattern_detected
specific_pain_emerging
specific_pain_identified
ready_for_positioning
```

### 0.3 `friction_categories` (= posibles `dominant_friction_type`)
De `app/core/friction_categories.py`:
```
reporting_fragmentation
process_inefficiency
tooling_inconsistency
scaling_strain
customer_experience_friction
```

### 0.4 `eligibility_gate`
Smart-Match acepta para match: `full`, `conditional`. Otros valores en uso:
`blocked`, `none` (= no elegible).

### 0.5 `confidence` (banda)
Valores típicos: `high`, `moderate`, `low`.

---

## 1. Arquetipos de empresa (10)

Cada arquetipo es un set de parámetros de generación. La distribución del
dataset (cuántas empresas de cada tipo) está en §3.

| # | id                       | tagline                                                         | sectors esperados                          | size band  | geo bias        |
|---|--------------------------|-----------------------------------------------------------------|--------------------------------------------|------------|------------------|
| 1 | `scaling_startup`        | Crecimiento sano, alta presión, sin freeze                      | Software & SaaS, AI & Machine Learning     | 50-500     | US-CA, US-NY, EU |
| 2 | `ghost_jobs_giant`       | Reqs evergreen reposteados sin contratar                        | Retail & Hospitality, Professional Services | 5k+        | US-multi        |
| 3 | `post_layoff_rehire`     | Cierre Q4, reapertura Q1 con titles junior-er                   | Software & SaaS, Media & Entertainment     | 1k-5k      | US-multi        |
| 4 | `hiring_freeze`          | 0 nuevos roles en 6 meses, solo "critical"                      | Manufacturing & Industrial, Other          | 1k-10k     | US, LATAM       |
| 5 | `aggressive_replacer`    | Turnover alto: cada rol cierra en 14d y vuelve en 30d            | Fintech & Financial Services               | 200-2k     | US-NY, UK       |
| 6 | `lit_edu_cluster`        | VIP-daughter cohort: editorial, EdTech, libros                  | Education, Media & Entertainment           | 10-200     | US, ES, MX      |
| 7 | `novawork_ideal`         | Perfil con `ready_for_positioning`, full eligibility            | Software & SaaS                            | 100-1k     | US-CA, US-NY    |
| 8 | `noise_floor`            | Empresa sin fricción real, bajo `friction_score`                | Other, Professional Services               | 10-500     | global          |
| 9 | `intermediary_trap`      | Job board / staffing — debe ser detectado como NO operating     | Other, Professional Services               | 50-2k      | US, IN          |
| 10| `data_quality_chaos`     | Mismo arquetipo (cualquiera) + ruido adversarial intenso         | hereda del padre                           | hereda     | hereda          |

### 1.1 Parámetros por arquetipo

Cada arquetipo se describe con este shape (todos los λ son por trimestre simulado):

```yaml
archetype_id: scaling_startup
demographics:
  size_band: [50, 500]
  geography_weights: { "US-CA": 0.4, "US-NY": 0.2, "EU": 0.3, "Other": 0.1 }
  sectors: ["Software & SaaS", "AI & Machine Learning"]
roles_generation:
  poisson_lambda_quarter: 18          # roles abiertos por trimestre
  functional_area_mix:
    engineering: 0.55
    product: 0.15
    sales: 0.10
    marketing: 0.07
    operations: 0.08
    other: 0.05
  ttl_open_days: { p50: 28, p95: 75 }
  repost_probability: 0.05            # rara vez
  title_drift_probability: 0.0
  evergreen_probability: 0.0
behavioral_pattern:
  cohort: "monotone_growth"           # roles aumentan trimestre a trimestre
  signal_density: "high"
  noise_signals: "low"
expected_outputs:                     # ground truth
  diagnostic_state: ready_for_positioning
  dominant_friction_type: scaling_strain
  friction_score_band: [55, 80]
  eligibility_gate: full
  confidence: high
  smart_match_hit: true
```

Los 10 arquetipos completos viven en `backend/scripts/synthetic/archetypes.yaml`
(a generar en la fase de implementación). Los **expected_outputs** son la
ground truth.

### 1.2 Resumen de outputs esperados por arquetipo

| arquetipo               | diagnostic_state                   | dominant_friction        | score band | eligibility | sm_hit |
|-------------------------|------------------------------------|--------------------------|------------|-------------|--------|
| scaling_startup         | ready_for_positioning              | scaling_strain           | 55–80      | full        | ✅     |
| ghost_jobs_giant        | broad_hiring_pattern_detected      | process_inefficiency     | 35–55      | conditional | ⚠️ borderline |
| post_layoff_rehire      | specific_pain_emerging             | scaling_strain           | 40–60      | conditional | ✅     |
| hiring_freeze           | insufficient_evidence              | (any, low score)         | 0–15       | blocked     | ❌     |
| aggressive_replacer     | specific_pain_identified           | tooling_inconsistency    | 50–70      | full        | ✅     |
| lit_edu_cluster         | specific_pain_emerging             | reporting_fragmentation  | 30–55      | conditional | ✅ (Isabella) |
| novawork_ideal          | ready_for_positioning              | scaling_strain           | 65–85      | full        | ✅     |
| noise_floor             | insufficient_evidence              | (low score, any)         | 0–20       | blocked     | ❌     |
| intermediary_trap       | insufficient_evidence              | (n/a — not operating)    | 0–10       | blocked     | ❌     |
| data_quality_chaos      | hereda                             | hereda                   | hereda ±15 | hereda      | hereda |

---

## 2. Ground-truth schema

Toda fila sintética lleva metadata fuera del modelo de producción. **No
contamina las tablas reales**: vive en un campo paralelo `synthetic_meta`
que el generador escribe a un side-table o a un JSON sidecar.

### 2.1 `synthetic_meta` por empresa

```json
{
  "synthetic_meta": {
    "is_synthetic": true,
    "dataset_version": "synth-2026-04-27-v1",
    "generator_version": "0.1.0",
    "seed": 42,
    "archetype_id": "scaling_startup",
    "archetype_persona_index": 7,
    "generated_at": "2026-04-27T10:00:00Z",
    "simulated_t0": "2025-10-01",
    "simulated_t1": "2026-04-01",

    "expected_diagnostic_state": "ready_for_positioning",
    "expected_dominant_friction_type": "scaling_strain",
    "expected_friction_score_band": [55, 80],
    "expected_eligibility_gate": "full",
    "expected_confidence": "high",
    "expected_smart_match_hit": true,
    "expected_smart_match_reason": "high pain clarity in eng + ready state",

    "friction_signatures": [
      "high_eng_concentration",
      "monotone_role_growth",
      "low_noise_signals"
    ],
    "noise_injected": [],
    "counterfactual_pair_id": null,
    "ground_truth_immutable": true
  }
}
```

### 2.2 `synthetic_meta` por rol (subset)

```json
{
  "synthetic_meta": {
    "is_synthetic": true,
    "parent_company_synth_id": "synth-co-00042",
    "role_template_id": "tpl-eng-be-senior",
    "lifecycle": {
      "first_posted": "2026-02-14",
      "last_seen": "2026-04-22",
      "is_repost_of": null,
      "repost_count": 0,
      "is_evergreen": false,
      "title_drift_history": []
    },
    "is_friction_signal": false,
    "friction_signal_kind": null,
    "noise_injected": []
  }
}
```

### 2.3 Dataset manifest (sidecar global)

Un solo archivo `synthetic_dataset_manifest.json` por dataset:

```json
{
  "dataset_version": "synth-2026-04-27-v1",
  "generator_version": "0.1.0",
  "seed": 42,
  "generated_at": "2026-04-27T10:00:00Z",
  "simulated_window": { "t0": "2025-10-01", "t1": "2026-04-01" },
  "source_real_export": "exports/companies_2026-04-27.json",
  "totals": {
    "companies": 200,
    "roles": 4180,
    "signals": 12500
  },
  "archetype_distribution": {
    "scaling_startup":     30,
    "ghost_jobs_giant":    15,
    "post_layoff_rehire":  20,
    "hiring_freeze":       15,
    "aggressive_replacer": 15,
    "lit_edu_cluster":     25,
    "novawork_ideal":      20,
    "noise_floor":         30,
    "intermediary_trap":   10,
    "data_quality_chaos":  20
  },
  "counterfactual_pairs": 18,
  "vocabularies_pinned": {
    "sectors": "...sha256...",
    "diagnostic_states": "...sha256...",
    "friction_categories": "...sha256..."
  }
}
```

`vocabularies_pinned` ata el dataset a los enums vigentes el día de
generación. Si alguien cambia un sector después, sabremos si el dataset
sigue siendo válido.

---

## 3. Mezcla del dataset

Total objetivo: **200 empresas / ~4k roles / ~12k signals**.

Distribución diseñada para que cada arquetipo tenga muestra suficiente y
que `noise_floor` + `intermediary_trap` (los hard negatives) sean ~20% del
total — proporción defendible para evaluar precisión.

| arquetipo               | n  | ratio |
|-------------------------|----|-------|
| scaling_startup         | 30 | 15%   |
| ghost_jobs_giant        | 15 | 7.5%  |
| post_layoff_rehire      | 20 | 10%   |
| hiring_freeze           | 15 | 7.5%  |
| aggressive_replacer     | 15 | 7.5%  |
| lit_edu_cluster         | 25 | 12.5% |
| novawork_ideal          | 20 | 10%   |
| noise_floor             | 30 | 15%   |
| intermediary_trap       | 10 | 5%    |
| data_quality_chaos      | 20 | 10%   |

---

## 4. Counterfactual pairs

Para medir lift del scoring, **18 pares** de empresas que comparten todo
salvo la firma de fricción:

- Misma persona demográfica (sector, size, geo).
- Mismo template base de roles.
- Una con `friction_signatures` activadas, la otra con baseline.

Ejemplo:
```
synth-co-00100  archetype=scaling_startup    friction_signatures=[…]   expected_score_band=[55,80]
synth-co-00100c archetype=scaling_startup_cf friction_signatures=[]    expected_score_band=[10,25]
counterfactual_pair_id = "pair-00100"
```

Métrica derivable: `score(real) − score(counterfactual) ≥ Δ_min` por arquetipo.

---

## 5. Ruido adversarial (`data_quality_chaos`)

Catálogo de transformaciones posibles. El generador elige 1-3 por empresa:

| código              | transformación                                                |
|---------------------|---------------------------------------------------------------|
| `html_residual`     | inserta `&amp;`, `<p>`, `&nbsp;` en `role_description`        |
| `case_chaos`        | `role_title` en MAYÚSCULAS o tÍtUlO mixto                     |
| `lang_mix`          | mezcla EN+ES en descripciones                                 |
| `mojibake`          | UTF-8 mal decodificado en algunos campos                      |
| `null_injection`    | `role_department` null en 30%, `role_description` null en 5%  |
| `dup_partial`       | mismo rol con dos source_url ligeramente distintas            |
| `location_garbage`  | `role_location = "Remote – EMEA preferred (occasional travel)"` |
| `title_with_emoji`  | "Senior Backend Engineer 🚀"                                  |
| `empty_signals`     | empresa con 0 signals y >5 roles (ruptura de invariante real) |

Cada noise se loggea en `synthetic_meta.noise_injected`.

---

## 6. Reglas duras (invariantes que el generador NO puede romper)

1. `inferred_sector` ∈ vocabulario §0.1 exacto.
2. `diagnostic_state` ∈ vocabulario §0.2 exacto.
3. `dominant_friction_type` ∈ vocabulario §0.3 exacto.
4. `eligibility_gate` ∈ {`full`, `conditional`, `blocked`, `none`}.
5. `domain` único; sintéticos prefijo `synth-` para grep fácil
   (ej. `synth-acme-corp.test`).
6. `name` no debe colisionar con empresas reales del export. Si colisiona,
   sufijar ` (synthetic)`.
7. Toda persona/email en `role_description` debe ser fake (faker locale
   `en_US`/`es_ES`); JAMÁS reusar de datos reales.
8. `synthetic_meta.is_synthetic = true` SIEMPRE.
9. `seed` reproducible: misma seed + mismo manifest = mismo dataset bit-a-bit.

---

## 7. Decisiones abiertas (necesito tu confirmación)

- ~~**D1 — Almacenamiento**~~ → **DECIDIDO: (c) JSON sidecar**.
  El dataset vive en `backend/data/synthetic/<dataset_version>/` como
  archivos JSON (companies.json, roles.json, signals.json, manifest.json).
  Un loader (`backend/scripts/synthetic/load_into_test_db.py`) podrá
  hidratar una sqlite/postgres de test cuando queramos correr el motor
  real contra el dataset. NO se toca la DB de producción.

- ~~**D2 — Distribución 200**~~ → **DECIDIDO**: pesos de §3 conservados.
- ~~**D3 — Dominant friction null**~~ → **DECIDIDO**: cuando
  `expected_friction_score < 15`, `expected_dominant_friction_type` puede
  ser `null` en `synthetic_meta`. En el JSON sintético tomamos la
  decisión al generar (no en DB), así que no toca esquemas reales.
- ~~**D4 — Ventana temporal**~~ → **DECIDIDO**: T0=2025-04-01,
  T1=2026-04-01 (12 meses).
- ~~**D5 — LLM en generación**~~ → **DECIDIDO**: templates puros en v1.
  LLM queda fuera de scope hasta v2.

---

## 8. Lo que viene después (post-aprobación)

1. Script `backend/scripts/synthetic/export_real_seed.py` — JSON real.
2. `backend/scripts/synthetic/archetypes.yaml` — arquetipos en YAML.
3. `backend/scripts/synthetic/generate_dataset.py` — generador.
4. `backend/scripts/synthetic/validate_dataset.py` — checa invariantes §6.
5. `backend/tests/test_synthetic_generator.py` — golden tests con seed fija.
