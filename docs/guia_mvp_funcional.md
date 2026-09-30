# Librería Inglés — MVP funcional (rama `fix/mvp-funcional`)

**Objetivo:** que la app se pueda usar de punta a punta con una cuenta personal:
login → nivel → conexión de IA → clase → corrección → progreso.

---

# 1. Qué incluye

| Pieza | Estado |
|---|---|
| Login con Google (cuenta personal) | ✅ requiere `GOOGLE_CLIENT_ID` |
| Login de desarrollo sin Google | ✅ solo local (`DEV_LOGIN_ENABLED=true`) |
| Elección de nivel (nivel seleccionado = nivel operativo inicial) | ✅ A1 disponible |
| Currícula A1 como datos (`backend/app/curriculum/data/a1.json`) | ✅ 20 skills, 4 áreas |
| Conexiones de IA BYOK: OpenAI, Gemini, Anthropic | ✅ keys cifradas, prueba inmediata |
| Proveedor simulado para probar sin keys | ✅ solo local (`MOCK_AI_ENABLED=true`) |
| Router de IA: prioridad, failover, backoff, estados | ✅ |
| Conexiones de plataforma (PLATFORM_OWNER) | ✅ vía `PLATFORM_OWNER_EMAILS` |
| Generación de clase (solicitud persistida antes de llamar a la IA) | ✅ `GENERATING` / `GENERATION_FAILED` + reintento |
| Autoguardado por ejercicio | ✅ |
| Evaluación híbrida (reglas → errores comunes → caché → IA) | ✅ |
| Persistir respuestas antes de corregir; pendientes si no hay IA | ✅ `AWAITING_EVALUATION` + reintento automático al entrar |
| Apelación "Creo que mi respuesta es correcta" | ✅ agrega la variante a la answer key |
| Rehacer clase y comparar intentos | ✅ |
| Progreso por skill (score, intentos, confianza, estado, tendencia) | ✅ |
| Dashboard e historial | ✅ |
| Selección adaptativa de skills (prioriza débiles y no practicadas) | ✅ básica |

**Fuera de esta entrega:** diagnóstico adaptativo, promoción/descenso automático de nivel,
currícula A2–C2, listening/speaking/pronunciación, portal de organizaciones y ADMIN,
invitaciones, pagos, vinculación de perfiles entre cuentas.

---

# 2. Configuración del backend

Copiar `backend/.env.example` a `backend/.env` y revisar:

```text
JWT_SECRET=<secreto de 32+ caracteres>
DEV_LOGIN_ENABLED=true          # login sin Google (solo local)
MOCK_AI_ENABLED=true            # proveedor simulado (solo local)
GOOGLE_CLIENT_ID=               # ver punto 3
PLATFORM_OWNER_EMAILS=tu@email  # recibe el rol PLATFORM_OWNER al ingresar
ENCRYPTION_KEY=                 # opcional en local; obligatoria en production
```

Aplicar migraciones (hay una nueva, `0002_learning_flow`):

```powershell
cd backend
pip install -e ".[dev]"
alembic upgrade head
```

> Si `JWT_SECRET` cambia y `ENCRYPTION_KEY` está vacía, las API keys guardadas dejan de
> poder descifrarse (hay que volver a cargarlas). Para evitarlo, fijá `ENCRYPTION_KEY`:
>
> ```powershell
> python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
> ```

---

# 3. Login con Google

1. Google Cloud Console → **APIs y servicios → Credenciales → Crear credenciales → ID de cliente de OAuth**.
2. Tipo: **Aplicación web**.
3. **Orígenes de JavaScript autorizados:** `http://localhost:4200`.
4. Copiar el *Client ID* en `GOOGLE_CLIENT_ID` del `.env` y reiniciar el backend.

El frontend obtiene el Client ID desde `/api/v1/auth/config`; no hay que configurarlo en Angular.

---

# 4. Probar sin API keys (modo simulado)

1. Levantar backend y frontend.
2. `http://localhost:4200` → **Crear cuenta personal** → ingresar en modo desarrollo.
3. Elegir **A1**.
4. **IA** → proveedor **Simulado** → Guardar y probar.
5. **Inicio → Nueva clase**, responder, **Finalizar y comprobar**.

Modelos especiales del simulado para probar resiliencia:

| Modelo | Simula |
|---|---|
| `mock` | funciona |
| `mock-fail-quota` | cuota agotada |
| `mock-fail-down` | proveedor caído |
| `mock-fail-auth` | credencial inválida |

Ejemplo: una conexión `mock-fail-quota` con prioridad 1 y otra `mock` con prioridad 2 muestra
el failover; dejar solo la que falla muestra la clase en *Esperando corrección*.

---

# 5. Proveedores reales

En **IA → Agregar conexión**: proveedor, nombre, modelo (opcional) y API key.
Al guardar se prueba de inmediato. Modelos por defecto (editables):

| Proveedor | Modelo por defecto |
|---|---|
| OpenAI | `gpt-4o-mini` |
| Google Gemini | `gemini-2.5-flash` |
| Anthropic | `claude-sonnet-4-5` |

Si el proveedor responde 404, el nombre del modelo no existe: editarlo por uno vigente.

---

# 6. Flujo técnico

```text
POST /classes
  ├─ motor elige 6 skills (débiles / sin practicar tienen más peso)
  ├─ persiste CLASS_SESSION en GENERATING con la solicitud
  ├─ router de IA (prioridad → failover → backoff)
  ├─ valida el JSON (skills pedidas, tipos, opciones, huecos)
  └─ READY  |  GENERATION_FAILED (reintentable)

PUT /classes/{id}/answers/{exercise}   autoguardado → IN_PROGRESS

POST /classes/{id}/submit
  ├─ 1) persiste todos los ATTEMPT → AWAITING_EVALUATION
  └─ 2) evalúa cada intento:
        acceptedAnswers → RULE_MATCH
        commonErrors    → COMMON_ERROR_MATCH
        opción múltiple → incorrecto por regla
        caché IA        → AI
        IA              → AI   (sin IA: queda pendiente)
     todos evaluados → COMPLETED + recalcula STUDY_SKILL_PROGRESS
```

El score lo calcula el backend a partir de los conceptos (correct = 100, partial = 50,
incorrect = 0); las sugerencias de estilo no descuentan.

---

# 7. Endpoints nuevos

```text
GET  /api/v1/auth/config
POST /api/v1/auth/google
POST /api/v1/auth/dev-login
GET  /api/v1/me
PUT  /api/v1/me/level

GET    /api/v1/ai/providers
GET    /api/v1/ai/connections?scope=account|platform
POST   /api/v1/ai/connections
PATCH  /api/v1/ai/connections/{id}
DELETE /api/v1/ai/connections/{id}
POST   /api/v1/ai/connections/{id}/test

GET  /api/v1/classes
POST /api/v1/classes
POST /api/v1/classes/process-pending
GET  /api/v1/classes/{id}
PUT  /api/v1/classes/{id}/answers/{exercise_id}
POST /api/v1/classes/{id}/submit
POST /api/v1/classes/{id}/retry-generation
POST /api/v1/classes/{id}/retake
POST /api/v1/classes/{id}/exercises/{exercise_id}/appeal

GET  /api/v1/progress
```

---

# 8. Cambios de modelo (migración `0002_learning_flow`)

- `study_profiles`: `selected_level`, `estimated_level`, `operational_level`.
- `accounts`: `display_name`.
- `ai_connections`: `model`, `credential_hint`, `last_check_at`, `last_used_at`,
  `last_error_code`, `last_error_at`; CHECK de `owner_type`/`owner_id`; índice por dueño.
- `class_sessions`: `account_id`, `target_level`, `title`, `current_attempt`, `score`,
  `generated_by_connection_id`, `submitted_at`, `evaluated_at`; estados unificados
  (`SUBMITTED`/`EVALUATION_PENDING` → `AWAITING_EVALUATION`).
- `exercises`: `position`, `level`, `area`, `skill_key`, `instruction`, `content`, `expected_concepts`.
- `attempts`: `account_id`, `attempt_number` (único por ejercicio), `appealed_at`, `evaluated_at`.
- `draft_answers` (nueva): autoguardado.
- `study_skill_progress`: `status`, `last_practiced_at`; el UNIQUE con `organization_id` NULL
  se reemplazó por dos índices únicos parciales (global y por organización).

---

# 9. Tests

```powershell
cd backend
pytest
```

Cubren: login, niveles, API keys que nunca vuelven al frontend, flujo completo de clase,
autoguardado, failover, generación fallida y reintento, todos los proveedores caídos con
recuperación, aislamiento entre cuentas, conexiones de plataforma, normalización,
validación de lo que devuelve la IA y la migración (sube, coincide con modelos y baja).
