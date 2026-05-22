# Evaluación FrictionRadar — synth-2026-04-27-v3

Reporte agregado de las cuatro pasadas de evaluación contra el dataset
sintético v3 (218 empresas, 9 203 roles, 1 538 señales, semilla 42).

| Pasada                   | Métrica clave                  | Valor    |
|--------------------------|--------------------------------|----------|
| validate_dataset         | invariantes pasados            | 18 / 18  |
| evaluate_synthetic       | dom_friction match             | 71.1 %   |
| evaluate_synthetic       | score dentro de banda          | 99.5 %   |
| evaluate_synthetic       | diagnostic_state match         | 73.9 %   |
| evaluate_function_inference | accuracy in-scope           | 87.6 %   |
| evaluate_smart_match     | accuracy decisive (T/F)        | 78.0 %   |
| evaluate_smart_match     | recall                         | 100.0 %  |
| evaluate_smart_match     | precision                      | 73.3 %   |
| backend unit tests       | aprobados                      | 129 / 129|

## 1. Generación y validación

- 218 empresas (200 primarias + 18 contrafactuales).
- 18 invariantes (vocabularios cerrados, score bands, pareo CF, dominios sin colisión con seed real) → todos verdes.
- Hashes de vocabularios pinneados en `manifest.json` para detectar drift.

## 2. evaluate_synthetic.py

Engine real (CompanyEvaluationEngine + FrictionScoreEngine) corriendo sobre cada empresa.

- **Friction dominante**: 71.1 % match. Falla concentrada en `noise_floor`, `hiring_freeze`, `intermediary_trap` (volúmenes bajos donde el dominante deseado es `null`/ambiguo) y `data_quality_chaos` (65 %, lo cual es esperado por diseño).
- **Score band**: 99.5 % en banda. Las bandas 0–25 ya están alineadas con el rango alcanzable del engine de reglas.
- **Diagnostic state**: 73.9 % match. Los arquetipos de "señal alta" (`novawork_ideal` 95 %, `scaling_startup` 100 %, `ghost_jobs_giant` 86.7 %, `post_layoff_rehire` 85 %) clavan el estado. Los de "ruido bajo" (`hiring_freeze` 6.7 %, `noise_floor` 36.7 %) saturan a `broad_hiring_pattern_detected` cuando se esperaba `insufficient_evidence`, lo que refleja que el gate del engine es más laxo de lo que el groundtruth idealiza — gap conocido y aceptado para el diseño actual.

CFs: 18/18 con score 0, dom=null, ds=insufficient_evidence (banda [0,3]) — el roster vacío produce el baseline esperado.

## 3. evaluate_function_inference.py

`FunctionInferenceEngine.infer_functional_area` aplicado a los 9 203 role_titles.

- 8 515 in-scope (engine tiene reglas), 688 out-of-scope (`editorial`, `content`, `teaching`, `other` — generador los etiqueta pero el engine no tiene keywords).
- **Accuracy in-scope: 87.6 %**.

Per-clase:

| Clase            | n     | precision | recall |
|------------------|-------|-----------|--------|
| customer_success |   612 | 1.000     | 1.000  |
| data_analytics   |   577 | 1.000     | **0.489** |
| engineering      | 3 318 | 0.952     | 0.873  |
| finance          |   156 | 1.000     | 0.763  |
| marketing        |   452 | 1.000     | 1.000  |
| operations       | 1 158 | 1.000     | 0.741  |
| product          |   940 | 1.000     | 1.000  |
| sales            | 1 302 | 0.813     | 1.000  |

**Hallazgos accionables**:
- `data_analytics` recall 48.9 %: títulos como `Director of Data`, `Analytics Engineer`, `Data Scientist Lead` caen en `engineering` o `unknown`. El léxico de `data_analytics` está demasiado ceñido a "analyst/analytics specialist".
- `sales` precision 0.813: capta como sales algunos títulos `customer_success`/`operations` con palabras como "account" o "client".
- OOS (editorial/content/teaching/other) se mapean mayormente a `<none>` con baja confianza — comportamiento aceptable.

## 4. evaluate_smart_match.py

Pipeline real: CompanyEvaluationEngine → `check_eligibility` (positioning_engine). Predicted hit ≡ `gate_passed ∈ {full, conditional}`.

- 200 decisive (T/F), 18 borderline (todos resultaron `hit` por el engine — 100 % permisivo en zona gris).
- **Accuracy decisive: 78.0 %** · **Precision: 73.3 %** · **Recall: 100.0 %**.
- TP=121, FP=44, FN=0, TN=35.

Per-arquetipo (decisive):

| Arquetipo            | n  | dec | acc%   | pred_hit% | exp_hit% |
|----------------------|----|-----|--------|-----------|----------|
| novawork_ideal       | 20 | 20  | 100.0  | 100.0     | 100.0    |
| scaling_startup      | 30 | 30  | 100.0  | 100.0     | 100.0    |
| post_layoff_rehire   | 20 | 20  | 100.0  | 100.0     | 100.0    |
| aggressive_replacer  | 15 | 15  | 100.0  | 100.0     | 100.0    |
| lit_edu_cluster      | 25 | 25  | 100.0  | 100.0     | 100.0    |
| data_quality_chaos   | 20 | 17  |  94.1  |  75.0     |  55.0    |
| noise_floor          | 30 | 30  |  36.7  |  63.3     |   0.0    |
| hiring_freeze        | 15 | 15  |   6.7  |  93.3     |   0.0    |
| intermediary_trap    | 10 | 10  |   0.0  | 100.0     |   0.0    |
| ghost_jobs_giant     | 15 |  0  |  n/a   | 100.0     |   0.0    |
| todos los CF (×18)   | 18 | 18  | 100.0  |   0.0     |   0.0    |

**Lectura**:
- Los positivos de NovaWork (todos los arquetipos "ricos") se capturan al 100 % — recall perfecto.
- Los CF se rechazan al 100 % — el corte por roster vacío funciona.
- Los falsos positivos se concentran en arquetipos de **señal débil con muchos roles** (`hiring_freeze` 14/15 FP, `noise_floor` 19/30 FP, `intermediary_trap` 10/10 FP). El gate `conditional` se dispara porque `broad_hiring_pattern_detected + classified_roles ≥ 5 + concentration ≠ low` se cumple incluso con poco contexto.
- `ghost_jobs_giant` está marcado como `expected_smart_match_hit="borderline"` en groundtruth — el engine los acepta a todos (15/15 hit), lo cual es coherente con la naturaleza zona gris.

## 5. Trade-offs aceptados

1. **Recall = 100 %, precision = 73 %**: en producto, sobre-llamar a un Smart-Match candidato es más barato que perderlo. NovaWork puede aplicar un segundo filtro humano sobre los borderline.
2. **noise_floor / hiring_freeze como FP**: el engine no tiene aún heurísticas de "low-volume noise" — para subir precision habría que endurecer `check_eligibility` (p.ej. requerir `function_concentration ≥ moderate` cuando ds=`broad_hiring_pattern_detected`). Pendiente de decisión de producto.
3. **data_analytics recall 48.9 %**: ampliar diccionario de `function_inference_engine` con `director of data`, `head of analytics`, `analytics engineer`, `data platform`, `bi developer`. Patch contenido.

## 6. Próximos pasos sugeridos

- **Quick win** (sin código): regenerar v3 con seed 7 y semilla 13 para confirmar que las métricas son estables (no overfit a la seed 42).
- **Patch low-risk**: ampliar `FUNCTION_KEYWORDS["data_analytics"]` para subir recall al ~85 %.
- **Decisión de producto**: ¿endurecer `check_eligibility` para reducir FP en arquetipos de bajo volumen, o mantener el gate laxo y depender del filtro NovaWork? Recomendación: mantener laxo dado el recall=100 %.

---

## 7. Patch aplicado (2026-04-29) — `data_analytics` keywords

**Diagnóstico exacto** (sample de 295 misses):
- `Director of Data` (×150) → `unknown` (ningún keyword `data` standalone).
- `Staff Data Engineer` (×145) → `engineering` (porque `engineering` listaba `data engineer` y `engineer`, ganando 2-vs-1 en score).

**Cambios en `backend/app/services/function_inference_engine.py`**:
1. `data_analytics`: añadidos `director of data`, `head of data`, `vp of data`, `chief data officer`, `data platform`, `data infrastructure`, `analytics engineer`, `data warehouse`.
2. `engineering`: removidos `data engineer` y `ml engineer` (duplicados con `data_analytics`; el tiebreaker por specificity hace que el match más largo gane cuando los scores empatan).

**Resultado** (re-ejecución sobre el mismo v3):
| Métrica                  | antes   | después  |
|--------------------------|---------|----------|
| accuracy in-scope global | 87.6 %  | **91.1 %** |
| `data_analytics` recall  | 48.9 %  | **100.0 %** |
| `engineering` precision  | 95.2 %  | **100.0 %** |

Suite backend: 391 / 398 tests pasando — los 7 fallos restantes son pre-existentes (master_index dedup, florida import, ashby/playwright extraction) y no tocan `function_inference`.

## 8. Estabilidad multi-seed

Datasets adicionales generados (mismo `archetypes.yaml` v3, distintas semillas):

| Dataset                       | seed | total | dom %  | band % | ds %   | fn %   | SM acc | SM prec | SM rec |
|-------------------------------|------|-------|--------|--------|--------|--------|--------|---------|--------|
| `synth-2026-04-27-v3`         | 42   | 218   | 71.1   | 99.5   | 73.9   | 91.1   | 78.0   | 73.3    | 100.0  |
| `synth-2026-04-29-seed7`      |  7   | 218   | 71.6   | 98.2   | 78.4   | 91.3   | 84.4   | 80.0    | 100.0  |
| `synth-2026-04-29-seed13`     | 13   | 218   | 71.1   | 99.5   | 69.7   | 91.4   | 80.0   | 75.3    | 100.0  |
| **rango**                     | —    | —     | ±0.5pp | ±1.3pp | ±8.7pp | ±0.3pp | ±6.4pp | ±6.7pp  | 0      |

**Lecturas**:
- `dom`, `band`, `fn` y `recall` son altamente estables (rango ≤ 1.5pp, recall=100% en las tres seeds). Los pipelines de scoring y de inferencia funcional no dependen de la realización aleatoria.
- `ds` y `SM precision` varían más (~7-9pp) — sensibilidad al ruido residual en los arquetipos de bajo volumen (`hiring_freeze`, `noise_floor`, `intermediary_trap`), donde un par de roles extra disparan el gate `conditional`. Esto es consistente con el diagnóstico de la sección 4: el gate es laxo en señal débil.
- Conclusión: las métricas v3 no están sobreajustadas a seed 42. La banda de confianza típica para una corrida individual es ±5pp en `ds` y `SM precision`, ±1pp en lo demás.

## 9. Estado de los próximos pasos

- ✅ Quick win — multi-seed (seeds 7 y 13).
- ✅ Patch — `FUNCTION_KEYWORDS["data_analytics"]`.
- ⏳ Decisión de producto — endurecer o mantener el gate laxo. Recomendación: **mantener laxo** dado que recall=100% es invariante a la seed.

---

Reportes JSON completos en este directorio:
- `evaluation_report.json` — métricas por archetipo del engine de scoring
- `function_inference_eval.json` — confusion matrix completa por functional_area
- `smart_match_eval.json` — per-company predicted vs expected hit
- `manifest.json` — versión, seed, hashes de vocabularios
