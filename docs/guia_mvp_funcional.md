# Librería Inglés — MVP funcional

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
| Portal de plataforma: límites de consumo y uso de IA (T-006) | ✅ `/app/plataforma` |
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
PLATFORM_OWNER_EMAILS=sr.macros@gmail.com  # recibe el rol PLATFORM_OWNER al ingresar
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

# 6. Portal de plataforma (T-006)

Solo para cuentas con rol `PLATFORM_OWNER` (emails en `PLATFORM_OWNER_EMAILS`).
Menú **Plataforma** → `/app/plataforma`.

- Alta, prueba, prioridad, pausa y baja de conexiones de IA de la plataforma, sin tocar
  `.env` ni reiniciar.
- **Límites de consumo** por conexión (ventana móvil de 24 h, solo requests exitosos,
  sin contar health checks):
  - *Límite total 24 h*: tope de la conexión para todos los usuarios.
  - *Límite por usuario 24 h*: tope por cuenta.
  - Vacío = sin límite. Al alcanzarlo, la conexión se saltea (no se marca como caída) y el
    router sigue con la siguiente; si no queda ninguna, la clase queda pendiente como siempre.
- **Consumo**: requests de las últimas 24 h, requests por día (14 días), consumo por conexión
  (24 h y 30 días) y cuentas que más usan la IA de plataforma.
- Se registra cada llamada a un proveedor en `ai_usage_events` (solo metadatos: conexión,
  cuenta, operación, éxito/error). Nunca se guardan prompts ni respuestas.
- Los límites solo se aceptan en conexiones de plataforma; en conexiones propias la API
  responde 422.
- **Editar conexión** (propias y de plataforma): nombre, modelo y API key. El proveedor no se
  cambia (para otro proveedor se crea otra conexión). Cambiar modelo o key vuelve a probarla.
  Así no se pierde el historial de consumo, la prioridad ni los límites.
- **Lista de modelos del proveedor**: al alta (con la API key recién pegada, que no se guarda)
  y al editar (con la key guardada o una nueva), la app consulta los modelos disponibles en
  la cuenta: OpenAI `GET /v1/models` (solo modelos de chat), Gemini `GET /v1beta/models`
  (solo los que soportan `generateContent`) y Anthropic `GET /v1/models`. Si la consulta falla,
  se puede escribir el modelo a mano. Si el modelo actual ya no figura en la lista, se avisa
  (probablemente discontinuado).
- Cada registro de consumo guarda el modelo usado (migración `0004_usage_model`).
- Qué conexiones usa cada usuario (propias, de plataforma o ambas según el plan) queda para
  T-003/T-004.

Migraciones: `0003_platform_ai_usage` y `0004_usage_model`.

## 6.1 "Necesito lección" (T-020)

Es una práctica, no un examen: si el alumno no conoce el tema, consulta la lección sin salir
de la clase y después responde ese mismo ejercicio.

- Cada ejercicio tiene el botón **📘 Necesito lección**. La lección se abre dentro del
  ejercicio (regla, ejemplos, errores típicos, consejo) y al cerrarla sigue respondiendo ahí.
- Mientras la clase está abierta, el ejercicio queda marcado como respondido **con lección**
  (`assistance = LESSON`; `HINT` queda reservado para las pistas de T-018). Se ve el chip
  "📘 Con lección" en el ejercicio y en la corrección.
- Después de corregir, "Ver lección del tema" sigue disponible pero ya no marca nada.
- Progreso: un intento con lección cuenta como **media evidencia** (mueve el score la mitad y
  suma medio intento para confianza y dominio). El generador **refuerza** las skills que se
  vienen resolviendo con lección (`assisted_recent`: cuántos de los últimos 5 intentos).
- Contenido: una lección por skill y nivel, cargada como datos en
  `backend/app/curriculum/data/lessons/<nivel>.json` (sin IA: sin costo ni demora, revisable).
  Agregar un nivel = agregar su archivo. Un test verifica que toda skill del A1 tenga lección.

Migración: `0005_assistance`.

## 6.2 Examen de aprobación de nivel y certificado (T-024)

- **Cuándo se habilita** (tarjeta "Examen de nivel" en Inicio): haber practicado al menos el
  70 % de los temas del nivel y tener 70 % o más de promedio en lo practicado. Si no se cumple,
  la tarjeta muestra qué falta.
- **El examen** es una sesión aparte (`class_sessions.kind = EXAM`): 14 ejercicios repartidos
  por área (gramática 5, vocabulario 3, listening 2, lectura 2, escritura 2), temas al azar del nivel,
  sin lecciones y sin "rehacer". Usa la misma generación, autoguardado y corrección que las
  clases (también la apelación). **No modifica el progreso** de las clases.
- **Aprobación:** 70 % global **y** al menos 60 % en cada área (una debilidad no se compensa
  con otras áreas). Si no aprueba, puede volver a rendir a las 24 h.
- **Certificado:** al aprobar se emite uno propio de Librería Inglés con código de verificación
  (`LI-A1-XXXX-XXXX`). Se guardan los datos (`level_certificates`); el documento es una
  plantilla fija sin IA que se regenera idéntica, así que no hace falta almacenar el PDF.
  "Descargar PDF" usa la impresión del navegador (A4 horizontal).
- **Verificación pública:** `/certificado/<código>` se puede abrir sin sesión. El certificado
  aclara que no es una certificación oficial CEFR ni de Cambridge.
- Parámetros en `backend/app/exams/service.py` (`EXAM_BLUEPRINT`, `PASS_SCORE`,
  `AREA_MIN_SCORE`, `ELIGIBLE_COVERAGE`, `ELIGIBLE_SCORE`, `RETRY_COOLDOWN`).
- Al aprobar, si existe la currícula del nivel siguiente se ofrece cambiar; hoy A2 figura como
  "próximamente".

Migración: `0006_level_exams`.

## 6.3 Listening como modalidad (T-025)

Listening y Speaking **no son tipos de ejercicio**. Los tipos siguen siendo los mismos
(`fill_blank`, `multiple_choice`, `rewrite`, `short_writing`, `reading_multiple_choice`); cambia
**cómo se presenta** y **cómo se responde**:

```text
Exercise.presentation_mode : READ | LISTEN
Exercise.response_mode     : WRITE | SELECT | SPEAK   (SPEAK: T-026)
Attempt.response_mode      : modalidad con la que respondió efectivamente
```

- **Estímulo unificado:** con LISTEN, `content.stimulus` (+ `stimulusLang`, `stimulusRate`) es lo que
  el alumno escucha; con READ se muestra escrito (pasaje) o no hay estímulo. La API expone
  `presentation`, `response` y `stimulus {mode, text, lang, rate}`.
- **Corrección igual:** la evaluación no mira la modalidad; a la IA se le informa `presentation` y
  el `stimulus` como contexto.
- **Motor:** cada ejercicio de una clase se presenta LISTEN con 30 % de probabilidad (si la skill lo
  admite) y cada clase trae **al menos 1** escuchado. Ejemplos: completar la oración que se escucha,
  elegir la opción sobre lo que se escuchó, reescribir la oración escuchada, responder por escrito
  una pregunta oída.
- **Currícula:** cada skill declara `presentations` (por defecto `["READ","LISTEN"]`). Los 4 temas de
  comprensión auditiva de A1 (números/horas, datos personales, diálogos, instrucciones) son
  `["LISTEN"]`.
- **Validación:** con LISTEN el estímulo es obligatorio y no puede aparecer escrito en la consigna
  (salvo `fill_blank`, donde la consigna es la misma oración con el hueco).
- **Voz del navegador** (Web Speech API), sin costo ni API key; no se guarda audio (§15). Reproducir,
  Lento/Normal. El texto se muestra recién en la corrección ("El audio decía: …").
- **Transversal:**
  - dashboard: sección **Por modalidad** (Escucha = todo lo practicado escuchando, con el mismo
    cálculo que una skill); Habla aparece cuando exista práctica (T-026);
  - examen: 14 ejercicios (incluye el área Listening) y **al menos 3 escuchados**; aprueba solo si
    lo escuchado llega al 60 %; cada audio se escucha **2 veces**.
- Limitación: el navegador necesita el texto para generar la voz (visible con herramientas de
  desarrollo) y el límite de reproducciones se reinicia al recargar. Para el examen, a futuro,
  generar el audio en el backend.

Migración: `0007_modalities`.

## 6.4 Currícula A1 completa (T-028) y primer incremento de contenido (T-032)

- A1 pasa de 24 a **37 temas**, cubriendo la lista del documento funcional §4.1:
  - gramática nueva: pronombres sujeto, singular y plural, *have got*, imperativos,
    *this/that/these/those*, preposiciones de lugar, conectores (*and/but/or/because*);
  - vocabulario nuevo: saludos y presentaciones, números, días/meses/fechas, colores, ropa, la casa.
- Todos los temas nuevos tienen lección ("Necesito lección") y se pueden leer o escuchar.
- **Primer incremento de contenido:** cada tema tiene al menos 2 ejemplos semilla y un ejemplo por
  cada tipo de ejercicio que admite (antes muchos tenían 1).
- Se reemplazó el "odd one out" de comida (ambiguo) por consignas con criterio explícito
  (*Which one is a drink?*) y el prompt prohíbe ese formato.
- `tests/test_curriculum_content.py` valida cada ejemplo semilla (formato, una sola respuesta,
  opciones sin repetir, sin "odd one out") y que todo tema tenga lección.
- Efecto en el examen: la habilitación pide practicar el 70 % de 37 temas (26).

## 6.5 Evidencias por habilidad (T-034, etapa 1)

Un ejercicio genera **varias evidencias**, una por habilidad que toca, cada una medida a su manera
(`backend/app/progress/evidence.py`):

| Situación | Habilidad | Cómo se mide |
|---|---|---|
| Foco del ejercicio (su área) | Grammar / Vocabulary / Reading / Writing / Listening | resultado |
| Presentado escuchando | Listening | resultado × esfuerzo: −15 % por escucha extra, −20 % si usó lento, piso 40 % |
| Respondido hablando | Speaking | resultado del contenido |
| Respondido hablando | Pronunciation | estimación final; una palabra dicha como otra parecida (think/sink) la limita a 50 % |
| Ejercicio del área Writing (armar/componer oraciones) | Writing | resultado (reescribir una oración dada en gramática **no** cuenta: es Grammar) |
| Usó "Necesito lección" | todas sus evidencias | pesan la mitad y quedan marcadas como asistidas |
| Escuchó más de 2 veces o en lento | Listening | además del descuento, queda marcada como asistida |
| Practicó la pronunciación más de 2 veces | Pronunciation | pesa la mitad y queda asistida; el puntaje no baja |

- Lo escuchado no cuenta como Reading; lo hablado no cuenta como Writing.
- **Señales** (`signals` en borrador e intento, migración `0010_answer_signals`): escuchas, escuchas en
  lento y prácticas de pronunciación, registradas con `POST /classes/{id}/exercises/{eid}/signals`
  mientras la clase está abierta. Se muestran en la corrección ("Escuchaste el audio 3 veces (1 en lento)").
- **Ayuda = señal de debilidad:** con ayuda en las últimas 5 evidencias, una skill o habilidad no
  puede quedar como dominada aunque el puntaje dé (`assistedRecent`, lo usará el balanceo de la etapa 3).
- **Respuestas habladas** (`app/classes/spoken.py`): se compara la transcripción sin puntuación ni
  mayúsculas. Si coincide con la respuesta salvo palabras que suenan parecido (think/sink, three/tree,
  very/berry, ship/sheep…), el contenido es correcto y se marca `PRONUNCIATION_ERROR`, sin IA. Una
  transcripción que no coincide va a la IA aunque el ejercicio sea determinístico (si no hay IA, incorrecta).
  Los casos más difusos los resuelve la IA con la misma regla.
- `/progress` devuelve `abilities` (puntaje, evidencias, ayudas, ayuda reciente, tendencia, estado y, en
  Pronunciation, prácticas con su primer y último puntaje). Ya no devuelve `modalities`.

## 6.6 Dashboard por habilidad (T-034, etapa 2)

- Una tarjeta por habilidad (Grammar, Vocabulary, Listening, Speaking, Pronunciation, Reading, Writing)
  con puntaje, estado, barra, evidencias, tendencia y la marca "N reciente(s) con ayuda".
- Desplegable nativo (`<details>`): qué suma a esa habilidad, cuántas evidencias fueron con ayuda,
  en Listening/Speaking/Pronunciation **de qué temas vino la evidencia** (`sources`) y, si la
  habilidad es un área del currículum, sus temas y skills.
- Color de la barra por tramo: 0-25 rojo, 25-50 naranja, 50-75 azul, 75-100 verde. Pronunciation muestra aparte la
  evolución de la práctica (no cambia el puntaje).
- Se quitó "Por modalidad": lo escuchado y lo hablado ahora son Listening, Speaking y Pronunciation.

## 6.7 Balanceo por habilidad (T-034, etapa 3)

Al armar una clase, el motor mira las habilidades (`weak_abilities` en `classes/generation.py`):

- **Débil**: estado Repasar, o menos de 70 % con al menos 2 evidencias, o ayuda en 2 o más de las
  últimas evidencias (lección, escuchar varias veces o en lento, practicar mucho) aunque acierte.
- Se refuerzan como máximo **2** por clase (la más necesitada primero); el resto sigue variado.
  Speaking/Pronunciation solo si hay una IA con audio.
- Cómo se refuerza:
  - Grammar / Vocabulary / Reading / Writing / Listening: sus skills pesan el doble y la clase trae al
    menos un ejercicio de esa área.
  - Writing: además, esos ejercicios se escriben (no se pasan a hablados).
  - Listening: al menos 2 ejercicios escuchados (normal: 1).
  - Speaking / Pronunciation: al menos 2 respuestas habladas; si faltan tipos que se puedan hablar, se
    cambia el tipo de un ejercicio cuya skill lo admita.
- La clase muestra **"Esta clase refuerza"** (campo `focus`): hasta 2 habilidades (`kind: ability`)
  y hasta 2 temas flojos que entraron en la clase (`kind: topic`, ej. "Present Continuous ·
  Preguntas · vas 0 % y usaste la lección hace poco").
- Contenido A1 de escritura de oraciones: About me, Daily life (rutina), Short messages, Descriptions
  (personas y lugares) y Sentence building (ordenar palabras), cada uno con su lección.
- **Examen sin ayudas:** sin lección, 2 escuchas por audio (el contador sobrevive a recargar) y sin modo lento.

# 7. Flujo técnico

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
        tipeo menor     → parcial 80 % + SPELLING_ERROR (T-021, sin IA)
        opción múltiple → incorrecto por regla
        caché IA        → AI
        IA              → AI   (sin IA: queda pendiente)
     todos evaluados → COMPLETED + recalcula STUDY_SKILL_PROGRESS
```

El score lo calcula el backend a partir de los conceptos (correct = 100, partial = 50,
incorrect = 0); las sugerencias de estilo no descuentan.

**Ortografía menor (T-021, `app/classes/spelling.py`):** si una respuesta escrita coincide con
una aceptada salvo 1-2 palabras con un tipeo mínimo ("taxy driver", "Wendesday", "freind"), el
concepto cuenta como correcto, se marca `SPELLING_ERROR` y vale **80 %** ("Parcial", nunca 0 %).
No se perdona si la palabra tiene menos de 4 letras (in/on, do/is), si el error está en una
terminación que se enseña como gramática (-s/-es/-ies, -ed, -ing: "watchs"), ni si lo escrito
es otra palabra que la app conoce ("sleep" por "sheep"). No aplica a respuestas habladas ni de
opción múltiple. Si la IA corrige y el único problema es ortografía, en ejercicios cerrados
también vale 80 % (y una apelación así nunca agrega la palabra mal escrita como aceptada).

**Corrección proporcional de la escritura (T-043):**

- Puntaje fino por concepto: la IA da 0-100 y se respeta dentro de la banda de su estado
  (correcto 85-100, parcial 35-84, incorrecto 0-34). Sin puntaje fino, se usa 100/50/0 como antes.
- Mayúsculas y puntuación ("i" → "I", falta el punto final) no son errores de gramática: se
  convierten en **una** observación `MECHANICS_NOTE` que no descuenta.
- El mismo error repetido se informa una vez, con `occurrences` (la corrección muestra "×3").
- Prompt: cada concepto se evalúa solo por sus propios errores; calibración por nivel (en A1-A2
  las expresiones por encima del nivel son sugerencias, nunca errores).

---

# 8. Endpoints nuevos

```text
GET  /api/v1/auth/config
POST /api/v1/auth/google
POST /api/v1/auth/dev-login
GET  /api/v1/me
PUT  /api/v1/me/level

GET    /api/v1/ai/providers
POST   /api/v1/ai/models                         (modelos para una key nueva, no se guarda)
GET    /api/v1/ai/connections/{id}/models        (modelos con la key guardada)
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
POST /api/v1/classes/{id}/exercises/{exercise_id}/lesson   (lección del tema; registra la ayuda)

GET  /api/v1/exams/status                 (requisitos, examen en curso, aprobación)
POST /api/v1/exams                        (arma el examen del nivel actual)
GET  /api/v1/certificates                 (mis certificados)
GET  /api/v1/certificates/{code}          (público: verificación)

GET  /api/v1/progress

GET  /api/v1/platform/overview      (solo PLATFORM_OWNER)
```

---

# 9. Cambios de modelo (migración `0002_learning_flow`)

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

# 10. Tests

```powershell
cd backend
pytest
```

Cubren: login, niveles, API keys que nunca vuelven al frontend, flujo completo de clase,
autoguardado, failover, generación fallida y reintento, todos los proveedores caídos con
recuperación, aislamiento entre cuentas, conexiones de plataforma, normalización,
validación de lo que devuelve la IA y la migración (sube, coincide con modelos y baja).
