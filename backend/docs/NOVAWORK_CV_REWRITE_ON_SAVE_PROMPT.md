# Prompt para NovaWork — Auto-rewrite CV contra positioning_angle al "Save"

Copia este prompt completo en tu sesión de Claude Code dentro del repo de NovaWork (`/c/Ubuntu/home/efraiprada/novaworkglobal/active`).

---

## Contexto

Soy Efrain, founder de NovaWork + FrictionRadar. Piloto Smart Matches ya funciona para mi email `efrain.pradas@gmail.com`. El flujo actual:

1. FrictionRadar detecta empresas con "hiring pain"
2. NovaWork hace POST a `/internal/v1/match` del motor FR y guarda resultados en `smart_match_briefs` con status=`proposed`
3. UI en `SmartMatches.tsx` muestra tarjetas con `match_insight`, `relevant_area`, `what_they_seek`, `positioning_angle`, `open_roles`
4. Usuario puede marcar una tarjeta como `saved` o `dismissed` via `PATCH /api/smart-matches/:id`

Lo que FALTA y es lo que tengo que construir ahora: cuando el usuario le da "Save" a un match brief, disparar automáticamente una reescritura de su CV master personalizada contra el `positioning_angle` + `what_they_seek` + `open_roles` de esa empresa específica. El CV reescrito queda guardado y asociado al brief, listo para exportar/descargar.

## Objetivo

Añadir un flujo "auto-personalizar CV" que se ejecuta al marcar un brief como `saved`. Debe:

1. Tomar el master resume del usuario (profile_summary + bullets + work_experience)
2. Tomar el brief guardado (positioning_angle + what_they_seek + open_roles[0].title típicamente)
3. Llamar a OpenAI (gpt-4o-mini o similar) para reescribir:
   - `profile_summary` tailored al positioning_angle
   - Top 8 bullets reordenados/reescritos para resaltar las competencias que ataca ese dolor
4. Guardar el resultado en una tabla nueva `smart_match_cv_versions` ligada al brief
5. Mostrar en la UI un botón "View tailored resume" en la tarjeta cuando el brief ya tiene una versión generada

## Archivos existentes que importan (NO tocar si no hace falta)

- `backend/routes/smartMatches.js` — ya tiene PATCH `/:id` para cambiar status
- `backend/services/frictionradar.js` — cliente HTTP a FR, no tocar
- `backend/services/smartMatchTranslator.js` — traduce vocabulario FR a neutro, respeta esta barrera
- `backend/services/openai.js` — exporta `openai` instancia. Usar esta.
- `frontend/src/pages/dashboard/SmartMatches.tsx` — UI actual de tarjetas
- `supabase/migrations/20260419000001_smart_match_briefs.sql` — tabla brief existente

## Entregables

### 1. Migration nueva — `supabase/migrations/20260419000002_smart_match_cv_versions.sql`

```sql
CREATE TABLE IF NOT EXISTS smart_match_cv_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brief_id UUID NOT NULL REFERENCES smart_match_briefs(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  master_resume_id UUID REFERENCES user_resumes(id) ON DELETE SET NULL,
  profile_summary_tailored TEXT,
  bullets_tailored JSONB NOT NULL DEFAULT '[]'::jsonb,
  positioning_angle_used TEXT,
  what_they_seek_used TEXT,
  top_role_title_used TEXT,
  generation_prompt TEXT,
  generation_model TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT smart_match_cv_versions_brief_unique UNIQUE (brief_id)
);

CREATE INDEX IF NOT EXISTS idx_smart_match_cv_versions_user
  ON smart_match_cv_versions(user_id);

ALTER TABLE smart_match_cv_versions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own cv versions" ON smart_match_cv_versions;
DROP POLICY IF EXISTS "Users can insert own cv versions" ON smart_match_cv_versions;

CREATE POLICY "Users can view own cv versions"
  ON smart_match_cv_versions FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own cv versions"
  ON smart_match_cv_versions FOR INSERT WITH CHECK (auth.uid() = user_id);
```

### 2. Service nuevo — `backend/services/cvPersonalization.js`

Función `generateTailoredCv({ userId, briefId, supabase, openai })` que:

1. Lee el `smart_match_briefs` por id + user_id (valida ownership)
2. Lee el master resume del user (`user_resumes` donde `is_master=true`, más reciente)
3. Lee hasta 40 bullets del `accomplishment_bank` del user
4. Construye el prompt:

```
Eres un experto en CVs ejecutivos. Reescribe el profile summary y elige los 8 bullets más relevantes para atacar este dolor corporativo específico.

EMPRESA: {domain}
POSITIONING ANGLE (cómo debe posicionarse el candidato): {positioning_angle}
WHAT THEY SEEK (lo que la empresa necesita): {what_they_seek}
TOP ROLE TITLE: {top_role_title}

PERFIL ACTUAL DEL CANDIDATO:
{profile_summary}

BANCO DE BULLETS (elige y reescribe los 8 más relevantes):
{bullets_enumerated}

Responde JSON estricto:
{
  "profile_summary_tailored": "...",  // 2-3 oraciones, max 80 palabras, conectando explícitamente con el positioning_angle
  "bullets_tailored": [
    {"original_index": 3, "tailored_text": "..."},
    ...
  ]  // exactamente 8 items, reordenados por relevancia
}
```

5. Llama `openai.chat.completions.create({ model: 'gpt-4o-mini', response_format: { type: 'json_object' }, temperature: 0.3 })`
6. Parsea, valida shape (ver test abajo)
7. UPSERT en `smart_match_cv_versions` (ON CONFLICT brief_id → overwrite — regenerar reemplaza la versión previa)
8. Devuelve la fila insertada

Manejo de errores:
- Si no hay master resume → throw `{ code: 'NO_MASTER_RESUME' }`
- Si OpenAI falla → log + rethrow con status 502
- Si JSON no parsea o no tiene 8 bullets → throw `{ code: 'LLM_BAD_OUTPUT' }`

### 3. Modificar — `backend/routes/smartMatches.js`

En el PATCH `/:id` existente, cuando el status que se está seteando es `saved`, disparar la generación del CV **de forma síncrona** (esperar resultado y devolverlo). Si ya existe una cv_version para ese brief, NO regenerar — devolver la existente.

```js
// dentro del handler PATCH, después del update exitoso:
if (status === 'saved') {
  const { data: existing } = await supabaseAdmin
    .from('smart_match_cv_versions')
    .select('*')
    .eq('brief_id', id)
    .maybeSingle()

  let cvVersion = existing
  if (!existing) {
    try {
      cvVersion = await generateTailoredCv({
        userId,
        briefId: id,
        supabase: supabaseAdmin,
        openai,
      })
    } catch (err) {
      console.error('[smart-matches] cv generation failed:', err)
      // No bloquear el save, solo loguear
    }
  }
  return res.json({ brief: data, cv_version: cvVersion })
}
```

Añadir también endpoint nuevo **POST `/:id/regenerate-cv`** para re-disparar generación manualmente (borrar row existente + generar de nuevo). Útil si el resume master cambia.

Y un **GET `/:id/cv`** para recuperar la cv_version asociada sin volver a generarla.

### 4. Modificar — `frontend/src/pages/dashboard/SmartMatches.tsx`

En cada tarjeta:

- El botón "Save" ya existe. Tras el PATCH exitoso, si la respuesta trae `cv_version`, guardar en estado local y mostrar un badge verde "Resume tailored ✓" dentro de la tarjeta.
- Añadir botón "View tailored resume" que abre un Drawer/Modal mostrando `profile_summary_tailored` y los 8 bullets.
- En el Drawer, botón "Regenerate" que hace POST a `/api/smart-matches/:id/regenerate-cv`.
- Si el brief ya estaba `saved` al cargar la página (cv_version existente), mostrar directamente el botón "View tailored resume".

Para el "View tailored resume" usa el mismo look & feel que el resume builder existente (layout neutro, sin vocabulario FR). No toques el resume master del usuario — esto es una versión derivada, no reemplaza nada.

### 5. Test — `backend/services/__tests__/cvPersonalization.test.js`

- Mock `openai.chat.completions.create` → devolver JSON valido con 8 bullets
- Mock supabase: `user_resumes` devuelve master, `accomplishment_bank` devuelve 20 bullets, `smart_match_briefs` devuelve brief
- Verificar: `smart_match_cv_versions` upsert llamado con 8 items y profile_summary_tailored truthy
- Verificar: respuesta LLM con 5 bullets (mal shape) → throw `LLM_BAD_OUTPUT`
- Verificar: sin master resume → throw `NO_MASTER_RESUME`

### 6. Orden de implementación

1. Migration (aplicar a Supabase local o branch)
2. Service `cvPersonalization.js` con tests
3. Extender `routes/smartMatches.js` (PATCH, POST regenerate, GET cv)
4. Frontend: badge + drawer + botón regenerate
5. Smoke test end-to-end: Save un brief → ver badge → abrir drawer → confirmar bullets

### 7. Reglas importantes

- **Vocabulario**: NADA de `main_pain`, `best_attack_angle`, `friction_score` en columnas/UI. Usar `positioning_angle_used`, `what_they_seek_used`, etc. (vocabulario neutro ya establecido).
- **Pilot gate**: mantener el `requirePilotUser` middleware. Todo este flujo está gated al email `efrain.pradas@gmail.com` por ahora.
- **Costo OpenAI**: `gpt-4o-mini` es barato (~$0.0005 por generación). No usar gpt-4 para esto.
- **No backfill**: no regenerar CVs para briefs ya guardados antes de este cambio. Solo se genera on-click.
- **Idempotencia**: llamar `/regenerate-cv` dos veces seguidas debe producir dos CVs distintos (temperature=0.3). Llamar Save dos veces al mismo brief debe devolver el mismo cv_version (no regenerar).
- **No bloquear el PATCH**: si la generación falla, el Save sigue siendo éxito; devolver `cv_version: null` y loguear error.

### 8. Verificación manual después de implementar

```bash
# En NovaWork backend:
npm run migrate  # aplica migration nueva
npm run test services/__tests__/cvPersonalization.test.js
npm run dev

# En el navegador (logueado como efrain.pradas@gmail.com):
# 1. Ir a /smart-matches
# 2. Click "Save" en una tarjeta
# 3. Ver badge "Resume tailored ✓"
# 4. Click "View tailored resume" → ver profile_summary y 8 bullets
# 5. Click "Regenerate" → nueva versión con bullets potencialmente distintos
# 6. Refrescar página → el brief guardado aún muestra el badge
```

---

Empieza por la migration, luego el service con tests, luego las rutas, luego UI. Si encuentras algo ambiguo sobre vocabulario o shape, avísame antes de asumir.
