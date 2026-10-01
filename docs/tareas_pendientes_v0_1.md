# Librería Inglés — Tareas pendientes y prioridades

**Versión:** 0.1  
**Base:** `main` en commit `1394bf8e23afeac489a38650ed64e55fee1eef11`

Este documento funciona como backlog técnico/funcional de temas a corregir, revisar o completar.

## Criterio de prioridad

| Prioridad | Significado |
|---|---|
| **P0 — Bloqueante** | No debería llegar a producción sin resolverse. |
| **P1 — Alta** | Conviene resolver pronto porque afecta estabilidad, seguridad, costo o forma de trabajar. |
| **P2 — Media** | Puede esperar mientras se prueba el MVP, pero debe resolverse antes de ampliar mucho el producto. |
| **P3 — Baja** | Mejora de orden, documentación o mantenibilidad; no bloquea el MVP. |
| **P4 — Muy baja** | Idea o mejora para analizar; no se planifica hasta cerrar lo anterior. |

---

# 1. Alcance actual acordado para IA

## Decisión actual

Para el MVP personal, el flujo funcional debe ser:

```text
Usuario
  ↓
Configura sus propias conexiones de IA
  ↓
ACCOUNT / BYOK
  ↓
prioridad
  ↓
failover
  ↓
backoff
```

Esto permite probar la aplicación con proveedores reales configurados por el propio usuario.

Las otras modalidades quedan como evolución:

```text
BYOK      → usuario/empresa aporta sus credenciales
PLATFORM  → la plataforma aporta IA incluida en el plan
HYBRID    → combinación configurable
```

La existencia de estas tres modalidades se mantiene como diseño futuro porque puede afectar el precio de la suscripción.

---

# 2. Backlog priorizado

## T-001 — CI automático y protección de `main`

**Prioridad:** P1 — Alta  
**Estado:** Resuelta

Problema actual:

```text
Pull Request
   ↓
merge
   ↓
main

sin validación automática obligatoria
```

Agregar CI que ejecute como mínimo:

```text
backend:
  pytest
  test de migraciones

frontend:
  npm ci
  npm run build
```

Luego proteger `main` para que los cambios entren mediante Pull Request y requieran checks exitosos.

**Motivo:** evita que tareas paralelas rompan `main` sin detectarlo.

---

## T-002 — Revisar vulnerabilidades npm

**Prioridad:** P1 — Alta  
**Estado:** Pendiente de análisis

Durante la instalación actual npm informó vulnerabilidades, incluyendo una crítica.

Acción:

```text
npm audit
  ↓
identificar dependencia directa o transitiva
  ↓
evaluar actualización compatible
  ↓
probar npm run build
```

No usar automáticamente:

```text
npm audit fix --force
```

porque puede introducir cambios incompatibles.

**No bloquea el desarrollo local**, pero debe revisarse antes de desplegar públicamente.

---

## T-003 — Ajustar el router de IA al alcance actual BYOK

**Prioridad:** P1 — Alta  
**Estado:** Pendiente  
**Bloquea prueba local:** No

El router actual considera conexiones:

```text
ACCOUNT
+
PLATFORM
```

Para el MVP personal actual debería comportarse como:

```text
ACCOUNT
solamente
```

hasta que exista una suscripción/plan que habilite explícitamente conexiones de plataforma.

Objetivo inmediato:

```pseudo
if MVP_PERSONAL:
    candidates = ACCOUNT_CONNECTIONS
```

No eliminar el modelo PLATFORM/HYBRID; solamente evitar que se active antes de implementar la política de planes.

---

## T-004 — Hacer que PLAN/SUBSCRIPTION gobiernen la fuente de IA

**Prioridad:** P2 — Media  
**Estado:** Futuro, antes de monetización

Implementar:

```pseudo
plan = plan_que_cubre(actividad)

switch plan.ai_source:
    BYOK:
        candidates = ACCOUNT / ORGANIZATION
    PLATFORM:
        candidates = PLATFORM
    HYBRID:
        candidates = orden_configurado(
            ACCOUNT,
            ORGANIZATION,
            PLATFORM
        )

router(candidates)
    -> priority
    -> active
    -> failover
    -> backoff
```

Esto debe quedar cerrado antes de cobrar planes o asumir costos de IA desde la plataforma.

---

## T-005 — Conexiones IA de organización

**Prioridad:** P2 — Media  
**Estado:** Futuro B2B

El modelo ya contempla:

```text
owner_type = ORGANIZATION
```

pero el flujo actual todavía no utiliza esas conexiones.

Implementar cuando se habilite el portal corporativo:

```text
Empresa
  ↓
configura sus propias credenciales
  ↓
AI_CONNECTION owner_type=ORGANIZATION
```

---

## T-006 — Gestión PLATFORM de IA desde la aplicación

**Prioridad:** P2 — Media  
**Estado:** Resuelta

Ya existe un portal protegido para `PLATFORM_OWNER` con:

```text
alta de conexiones PLATFORM
proveedor
modelo
credencial
prioridad
estado (probar / pausar / activar / eliminar)
límites globales de 24 h
límites por usuario
métricas de consumo
```

Todo se administra desde la aplicación, sin editar `.env` ni reiniciar el backend.

La UI permite editar nombre, modelo y API key de una conexión existente y volver a probarla al guardar.

Esto habilita la base para planes donde Librería Inglés incluya el costo de IA.

---

## T-007 — Seguridad de sesión

**Prioridad actual:** P2 — Media  
**Prioridad antes de producción pública:** P0 — Bloqueante  
**Estado:** Diferido

Actualmente:

```text
JWT
  ↓
localStorage
  ↓
duración por defecto: 7 días
```

Es suficiente para continuar probando el MVP local.

Antes de producción revisar:

- almacenamiento de sesión;
- cookies `HttpOnly / Secure / SameSite` vs bearer token;
- expiración;
- refresh de sesión;
- revocación;
- logout real del lado servidor si corresponde;
- protección ante XSS.

**Decisión actual:** no frenar el desarrollo funcional por este punto.

---

## T-008 — Endurecer configuración de producción

**Prioridad:** P1 — Alta antes de deploy  
**Estado:** Pendiente

Actualmente varias protecciones dependen de:

```text
APP_ENV=production
```

Antes de desplegar agregar validaciones de startup para impedir configuraciones inseguras.

Ejemplo:

```pseudo
if production:
    assert DEV_LOGIN_ENABLED == false
    assert MOCK_AI_ENABLED == false
    assert JWT_SECRET != default
    assert ENCRYPTION_KEY configured
```

---

## T-009 — Refactor de componentes Angular grandes

**Prioridad:** P2 — Media  
**Estado:** Pendiente

Componentes a vigilar:

```text
class.component.ts
ai-settings.component.ts
```

La funcionalidad puede seguir probándose, pero antes de agregar muchas más features conviene separar:

```text
page
  ├── state / facade
  ├── forms
  ├── exercise components
  ├── result components
  └── dialogs / panels
```

Objetivo: evitar componentes monolíticos difíciles de mantener y testear.

---

## T-010 — Portal de organización / ADMIN

**Prioridad:** P2 — Media  
**Estado:** Futuro B2B

Todavía falta implementar el portal corporativo completo:

- personas;
- ADMIN / STUDENT;
- invitaciones;
- carga CSV;
- branding;
- seguimiento de progreso;
- detalle por empleado;
- aislamiento de actividad personal;
- suscripción corporativa.

No bloquea el MVP personal.

---

## T-011 — Tests específicos de aislamiento B2B

**Prioridad:** P1 cuando comience B2B  
**Estado:** Pendiente

Agregar pruebas obligatorias:

```text
ADMIN empresa A
  ✓ ve actividad A
  ✗ ve empleados B
  ✗ ve actividad B
  ✗ ve actividad personal de sus empleados
```

El modelo ya guarda `organization_id` y `membership_id`; falta validar el flujo completo cuando exista el portal ADMIN.

---

## T-012 — Documentación actual vs documentación histórica

**Prioridad:** P3 — Baja  
**Estado:** Pendiente

Los documentos existentes se mantienen porque muestran la evolución del proyecto.

No sobrescribir versiones anteriores.

Cuando sea necesario, agregar una nueva versión que describa el estado actual:

```text
v0.1 → histórico
v0.2 → histórico
v0.3 → histórico
v0.4 → estado actualizado
```

También revisar referencias a ramas antiguas en documentos operativos cuando puedan confundir una instalación nueva.

---

## T-013 — Consolidar flujo de instalación desde `main`

**Prioridad:** P3 — Baja  
**Estado:** Pendiente

Algunos textos de primera instalación todavía mencionan ramas anteriores.

La referencia futura debe ser:

```text
main = baseline estable
  ↓
crear rama nueva desde main
  ↓
trabajar
  ↓
Pull Request
  ↓
main
```

No hace falta borrar documentos históricos; puede crearse una guía actual versionada.

---

## T-014 — Compatibilidad y mantenimiento de proveedores reales

**Prioridad:** P2 — Media  
**Estado:** A revisar durante pruebas

Actualmente existen adapters directos para:

```text
OpenAI
Gemini
Anthropic
```

Como los endpoints, nombres de modelos y contratos pueden cambiar, validar periódicamente:

- modelo por defecto vigente;
- health check;
- errores 401/403/429/5xx;
- formato JSON;
- timeouts;
- compatibilidad con Structured Outputs cuando corresponda.

La aplicación debe seguir dependiendo del adapter y no del proveedor concreto.

---

---

## T-015 — Identidad visual, logo y créditos del proyecto

**Prioridad:** P3 — Baja  
**Estado:** Pendiente

Definir una identidad visual mínima para Librería Inglés:

- logo;
- favicon;
- nombre/marca consistente;
- créditos visibles en una sección tipo footer / acerca de.

Información acordada para los créditos:

```text
Creador: Sr.Macros
Contacto: sr.macros@gmail.com
Desarrollado con asistencia de ChatGPT y Claude
```

Si en el futuro existiera una asociación formal con alguna empresa o proveedor, actualizar la redacción para reflejarla explícitamente.

## T-016 — Explicación opcional del alumno y control de los campos de respuesta

**Prioridad:** P4 — Muy baja  
**Estado:** Descartada (Roberto, 2026-10-01): un campo "¿Por qué?" en cada ejercicio ensucia lo
que corrige la IA y cuesta una llamada por ejercicio. La explicación del alumno pasa a la
apelación (**T-044**). El aviso de "texto de más" en los campos queda en espera: primero probar
más la usabilidad antes de agregar limitadores.

Objetivo: mejorar la experiencia del alumno cuando no interpreta del todo bien un ejercicio, y controlar lo que se escribe en cada campo de respuesta.

Situación actual:

```text
el alumno escribe la respuesta + una explicación en el mismo campo
  ↓
ya no coincide con acceptedAnswers → deja de resolverse por reglas
  ↓
se corrige con IA (más lento, consume crédito)
  ↓
resultado impredecible (puede marcarlo parcial por "texto de más")
  ↓
la explicación no suma nada al progreso
```

Propuesta a analizar:

1. **Campo opcional "¿Por qué?"** debajo de cada ejercicio, separado de la respuesta.
   - La respuesta se sigue corrigiendo igual (reglas cuando se puede, IA cuando hace falta).
   - Si el alumno escribe el porqué, la IA lo evalúa aparte como concepto de *comprensión*:
     confirma el razonamiento o lo corrige.
   - No baja la nota del ejercicio; suma evidencia a la confianza de la skill
     (reduce el "acertó de casualidad").
   - Sirve para detectar cuando el alumno entendió mal la consigna y explicársela.
2. **Control de los campos de respuesta** según el tipo de ejercicio:
   - completar: respuesta corta; avisar si parece que se escribió de más
     (ej.: "Parece que agregaste una explicación: escribila en ¿Por qué?");
   - reescribir: una oración; largo máximo razonable;
   - escritura libre: rango de largo sugerido;
   - avisos no bloqueantes antes de enviar, nunca modales.
3. Consignas más claras en pantalla (ejemplo de formato esperado por tipo de ejercicio).

Consideraciones:

- costo: el "¿Por qué?" siempre requiere IA; evaluar si se corrige en el mismo llamado o aparte;
- privacidad: es texto del alumno, se guarda como el resto de las respuestas;
- no debe convertir en obligatorio algo pensado como opcional.

---

## T-017 — Calidad y claridad de los ejercicios generados

**Prioridad:** P2 — Media  
**Estado:** Pendiente

Caso detectado en prueba real (A1, vocabulario *Daily life · Food*):

```text
Choose the word that does not belong.
bread · rice · milk · potato
```

Todas son comidas. La respuesta esperada (probablemente *milk*, por ser bebida) depende de un
criterio de clasificación que no se enuncia; *potato* también es defendible. El ejercicio evalúa
razonamiento de categorías, no inglés: un alumno A1 puede conocer las cuatro palabras y fallar.

Origen: la currícula A1 incluye como ejemplo semilla un ejercicio "odd one out"
(`apple · banana · carrot · orange`) y la IA replica el formato.

Acciones propuestas:

1. **Currícula:** reemplazar los "odd one out" por consignas con criterio explícito
   (ej.: *Which one is a drink?*), o eliminarlos en A1.
2. **Prompt de generación:** reglas explícitas:
   - una sola respuesta defendible, sin depender de conocimiento general ni de interpretación;
   - el criterio de la consigna siempre enunciado;
   - evaluar el idioma (vocabulario/gramática del nivel), no lógica ni cultura general;
   - instrucciones y vocabulario de la consigna acordes al nivel.
3. **Validación automática:** al generar, pedir a la IA una verificación de ambigüedad
   (o un segundo pase de revisión) y descartar el ejercicio si hay más de una respuesta posible.
4. **Reporte del alumno:** acción "Este ejercicio es confuso" que:
   - excluye el ejercicio del puntaje y del progreso;
   - lo registra para revisar el patrón (curricular o de prompt).
   Complementa la apelación "Creo que mi respuesta es correcta", que ya existe.
5. **Tests:** casos de ejercicios ambiguos que la validación debe rechazar.
6. **Ejercicios de escucha:** el audio debe aportar información indispensable para resolver.
   No generar ejercicios donde la respuesta pueda deducirse únicamente leyendo la consigna
   y las opciones. Caso detectado: *"Which item mentioned is a fruit?"* con opciones
   `toast / eggs / apple`; se puede elegir `apple` sin escuchar nada, por lo que el ejercicio
   evalúa vocabulario/lectura y no Listening.
   - la consigna visible puede explicar qué hay que hacer, pero no debe revelar el contenido
     necesario para responder;
   - las opciones pueden mostrarse, pero la elección correcta debe depender de lo oído;
   - la validación automática debe rechazar ejercicios de modalidad `LISTEN` que sean
     resolubles sin reproducir el audio.

---

## T-018 — Botón de ayuda: pistas durante la clase

**Prioridad:** P3 — Baja  
**Estado:** Futuro · diseño abierto (pensarlo bien antes de implementar)

Objetivo: que el alumno pueda pedir una pista en un ejercicio sin que le den la respuesta.

> Nota: el formato no está decidido. Una alternativa a evaluar es un **chatbot** acotado al
> ejercicio (el alumno pregunta y el agente orienta sin resolver), en lugar de pistas fijas.
> Lo de abajo es un punto de partida, no una definición.

Propuesta:

1. **Pistas graduales** por ejercicio, en español:
   - pista 1: orienta sin revelar (ej.: "Fijate quién es el sujeto");
   - pista 2: más concreta (ej.: "Con he/she/it el verbo cambia en presente simple");
   - nunca la respuesta ni, en opción múltiple, descartar opciones hasta dejar una sola.
2. **Origen de la pista** (a decidir):
   - pregenerada junto con el ejercicio (sin latencia ni costo extra al pedirla);
   - o generada a demanda por el agente, teniendo en cuenta el borrador que escribió el alumno
     (más personalizada, con costo y demora de IA);
   - posible combinación: primero la pregenerada, a demanda solo si pide más.
3. **Impacto en el progreso:** registrar cuántas pistas usó en cada intento
   (ej.: `hints_used`). Un acierto con pista no debería valer igual que uno sin pista
   para la confianza de la skill (el score del ejercicio se puede mantener).
4. **Control de costos:** límite de pistas a demanda por clase; cuentan para los límites de
   consumo de IA (T-006); caché por ejercicio.
5. **UX:** botón "Pedir pista" discreto en cada ejercicio, pista visible debajo de la consigna,
   sin modales; indicar en la corrección que se usó ayuda.

Relación: complementa T-016 (explicación del alumno) y T-017 (claridad de los ejercicios):
una consigna clara reduce la necesidad de pistas.

---

## T-019 — Presentación de la corrección: diferencias resaltadas y feedback sin repetir

**Prioridad:** P2 — Media  
**Estado:** Pendiente

Caso detectado en prueba real (A1, *Present Simple · Negativo*):

```text
Ejercicio:  David drinks coffee in the morning. → negativo
Respuesta:  david doesn't drinks coffee in the morning
Mostrado:   feedback → respuesta correcta → línea de error (tachado → corrección) → explicación
            (la misma explicación aparece 3 veces) · etiqueta "Incorrecto · 50%"
```

Problemas:

1. Lo importante (qué está mal) queda escondido; el orden no ayuda a ver la diferencia.
2. La explicación se repite en feedback, respuesta correcta y línea de error.
3. ~~**Bug:** cuando la respuesta coincide con un *commonError*, la etiqueta queda siempre en
   "Incorrecto" aunque el puntaje sea parcial (50 %). Debería decir "Parcial".~~ Resuelto en T-021.

Propuesta de presentación:

```text
Tu respuesta:       David doesn't [drinks] coffee in the morning.   ← en rojo / tachado
Respuesta correcta: David doesn't [drink]  coffee in the morning.   ← en verde

Después de 'doesn't' va el verbo en forma base (drink, no drinks).  ← una sola vez
```

- Diferencia palabra por palabra calculada en el frontend (sin IA).
- No marcar como error mayúsculas, puntuación final, apóstrofes tipográficos ni
  contracciones equivalentes (`doesn't` = `does not`), con la misma normalización del backend.
- Quitar la línea "tachado → corrección" cuando la diferencia ya lo muestra.
- Mostrar la explicación una sola vez; las sugerencias de estilo, aparte.
- En escritura libre (sin respuesta única) mostrar la versión corregida sugerida por la IA,
  sin presentarla como "la" respuesta correcta.

---

## T-020 — "Necesito lección": enseñar dentro de la sesión

**Prioridad:** P2 — Media  
**Estado:** Resuelta · rama `feat/t-020-necesito-leccion`

Resolución: botón "Necesito lección" dentro del ejercicio; `assistance = LESSON` registrado en
el intento (media evidencia para el progreso y refuerzo en la generación). Punto 4 decidido:
opción b), lecciones por nivel cargadas como datos (`curriculum/data/lessons/a1.json`, 20
skills del A1), sin IA. Pendiente para más adelante: formato y posición definitivos de la UI
(se revisa junto con el resto de la pantalla de clase), y la opción a) como ampliación.

Hoy la app practica y corrige, pero no enseña: asume que el alumno ya conoce el tema.
Criterio del producto: **es una práctica, no un examen**. Si uno practica y no sabe, consulta
el manual; acá es la misma idea. Todo se resuelve **sin salir de la sesión**.

Definiciones:

1. **Botón "Necesito lección"** en cada ejercicio (no es un "No lo sé" que descarta el punto):
   - abre la lección del tema dentro de la clase (regla, ejemplos, error típico);
   - al cerrarla, el alumno **continúa y responde ese mismo ejercicio**;
   - el ejercicio se evalúa normalmente, pero queda registrado que se respondió con ayuda
     (ej.: `assistance = LESSON | HINT | NONE`), para que el sistema lo tenga en cuenta.
2. **La enseñanza se guía por los resultados de la sesión:**
   - no hay lección obligatoria antes de practicar un tema nuevo;
   - según cómo le va al alumno (errores, uso de lecciones y pistas), el sistema balancea
     dónde reforzar con más ejercicios en la clase actual y en las siguientes;
   - un acierto con lección no vale igual que uno sin ayuda para la confianza de la skill.
3. **Consulta libre:** la lección está disponible en cualquier momento del ejercicio,
   antes de responder (como abrir el manual), no solo después de la corrección.
4. **Origen del contenido de la lección (a decidir):**
   - a) **Generada por el agente** según el ejercicio y la respuesta: más personalizada,
     pero gasta tokens y agrega demora;
   - b) **Estructura de enseñanza por nivel** (A1, A2, B1…): cada tema de la currícula
     tiene cargada una lección/ejemplo base para consultar; sin costo de IA, revisable.
   - Posible combinación: b) como base y a) solo si el alumno pide más detalle.
5. Si se usa IA: cuenta para los límites de consumo (T-006) y se cachea por tema y nivel.

Relación: T-018 (pistas: para quien sabe algo; la lección: para quien no sabe nada),
T-017 (claridad de ejercicios).

---

## T-021 — Tolerancia a errores de ortografía menores

**Prioridad:** P3 — Baja  
**Estado:** Resuelta (PR #17 a `develop`) · Claude

Resolución (detalle en `guia_mvp_funcional.md` §7):

1. Comparación previa **sin IA** (`app/classes/spelling.py`): distancia de edición con
   transposición; 1 cambio (2 en palabras de 8+ letras), hasta 2 palabras por respuesta.
2. Ortografía menor = concepto correcto + `SPELLING_ERROR` → **Parcial 80 %**, nunca 0 %;
   feedback coherente ("La respuesta es correcta, pero revisá la ortografía: …").
3. No se perdonan errores reales: palabras de menos de 4 letras (in/on), terminaciones que son
   gramática (-s/-es/-ies, -ed, -ing) ni otra palabra conocida ("sleep" por "sheep"). El
   diccionario sale del currículo y las lecciones (sin las formas "wrong" de los ejemplos).
4. Corrector IA: regla en el prompt (tipeo menor ≠ error de concepto; feedback coherente con el
   resultado). En ejercicios cerrados, "solo ortografía" vale 80 % también por IA y en apelación
   (la palabra mal escrita nunca entra como respuesta aceptada).
5. Bug de T-019 resuelto acá: con un *commonError* parcial la etiqueta decía "Incorrecto"; ahora
   sigue al puntaje ("Parcial").
6. Pendiente: reforzar la ortografía si se repite (registrar como aspecto en el progreso).

Caso detectado en prueba real (A1, *Completar · Daily life · Trabajos*):

```text
Consigna:   A ___ drives a taxi and takes people to different places.
Respuesta:  taxy driver
Resultado:  Incorrecto · 0%
Feedback:   "Casi correcto, pero hay un error de ortografía..."
```

Problemas:

1. El concepto (el oficio) es correcto; el error es solo de ortografía, pero puntúa 0 %.
2. Incoherencia: el feedback dice "casi correcto" y la etiqueta dice "Incorrecto · 0%".

Propuesta:

- Distinguir **error de concepto** de **error de ortografía menor** (1–2 letras, palabra
  reconocible). La IA puede presuponer la intención cuando no hay ambigüedad.
- Ortografía menor → "Parcial" (o correcto con observación), nunca 0 %; se señala la forma
  correcta sin penalizar el concepto.
- Registrar la ortografía como aspecto aparte para que el sistema la refuerce si se repite.
- Evaluar una comparación previa sin IA (distancia de edición) antes de llamar al agente.
- La etiqueta debe ser coherente con el feedback (relacionado con el bug de T-019).

---


## T-022 — Mejorar selector de modelos IA

**Prioridad:** P2 — Media  
**Estado:** Pendiente

El selector de modelos ya no es texto libre y obtiene la lista disponible del proveedor, pero necesita dos mejoras.

### 1. Corregir el desplegable

Actualmente la lista puede crecer hasta ocupar casi toda la pantalla.

Objetivo:

```text
selector
  ↓
desplegable con altura máxima
  ↓
scroll interno
  ↓
sin invadir el resto de la página
```

Debe funcionar igual tanto al crear como al editar una conexión.

### 2. Mostrar costo relativo del modelo

Agregar información que ayude al usuario a distinguir modelos económicos de modelos más costosos.

Idealmente mostrar, cuando la información esté disponible:

```text
modelo
precio input
precio output
unidad del precio
categoría aproximada: económico / medio / alto
```

La información de precios debe provenir de una fuente mantenible por proveedor y no inferirse solamente por el nombre del modelo.

Objetivo visual aproximado:

```text
gpt-4o-mini      Económico
gpt-4.1          Medio
modelo premium   Alto
```

El selector debe seguir permitiendo elegir el modelo aunque no exista información de precio para ese modelo.

---


## T-023 — Test de nivelación inicial opcional

**Prioridad:** P2 — Media  
**Estado:** Pendiente

Al iniciar, el usuario podrá:

```text
elegir manualmente un nivel
o
hacer un test de nivelación
```

El test debe ser propio, inspirado en criterios CEFR y no una copia literal de un examen externo.

Objetivo:

```text
evaluación inicial
  ↓
análisis por áreas
  ↓
nivel recomendado
  ↓
usuario confirma desde qué nivel quiere empezar
```

Idealmente debe ser adaptativo para no obligar a responder una cantidad excesiva de preguntas cuando el nivel ya puede estimarse con suficiente confianza.

---

## T-024 — Examen de aprobación de nivel y certificado

**Prioridad:** P2 — Media  
**Estado:** Resuelta (PR a `main`)

Resolución: examen como sesión `kind=EXAM` (12 ejercicios por área, sin lecciones ni rehacer,
no modifica el progreso), aprobación con 70 % global y 60 % mínimo por área, reintento a las
24 h, certificado con código de verificación y página pública `/certificado/:code` con PDF
(plantilla fija, se regenera idéntico; no se almacena el archivo). Migración `0006_level_exams`.

Cuando el sistema detecte que el alumno tiene desempeño suficiente en un nivel:

```text
progreso suficiente
  ↓
propuesta: "Podés rendir el examen del nivel"
  ↓
examen formal
  ↓
aprobación
  ↓
nivel completado
  ↓
habilitación del siguiente nivel
  ↓
certificado
```

El examen debe ser independiente de las clases normales y evaluar varias áreas del nivel.

La aprobación no debe depender solamente de un promedio global; debe contemplar también mínimos por área para evitar aprobar con una debilidad importante compensada por otras áreas.

### Certificado

Generar un certificado propio de Librería Inglés con plantilla fija y diseño uniforme.

Datos variables posibles:

```text
nombre del alumno
nivel aprobado
fecha
identificador del certificado
otros datos definidos más adelante
```

No generar el diseño con IA en cada emisión.

Guardar permanentemente los datos del certificado. El archivo PDF/imagen puede conservarse temporalmente (por ejemplo, 90 días) y regenerarse de forma idéntica cuando el usuario vuelva a solicitarlo.

El certificado debe identificarse como emitido por Librería Inglés y no presentarse como certificación oficial CEFR/Cambridge salvo que exista acreditación formal.

---

## Plan acordado: completar A1 antes de A2

Decisión (2026-09-30): el A1 está incompleto respecto del documento funcional v0.3.
Se completa **un tema a la vez**, en este orden, y recién después se pasa a A2:

```text
T-025 Listening (reproducir audio)      ← primero, el más simple
T-026 Speaking (grabar y transcribir)
T-027 Pronunciación / fonética
T-028 Temas faltantes de A1 (§4.1)
T-029 Descenso de nivel por evidencia    (cuando exista A2)
T-030 Currícula A2 → B2                  (después de A1 completo)
T-031 Temáticas en tres capas + portal  (futuro, después de A1)
T-032 Incremento de contenido por versión (recurrente; arranca con T-028)
T-033 Tema opcional al pedir nueva clase (mejora rápida, adelanto de T-031)
T-034 Evidencias + dashboard por habilidad + balanceo (Claude) — resuelta
T-035 Migración a Bootstrap con tema configurable por empresa
T-036 Reglas de examen y aprendizaje configurables (owner / ADMIN)
T-037 Bloquear el formulario al enviar la clase (bug, Claude)
T-038 Publicación: servidor para backend con fonética + frontend (servidor pendiente)
T-039 Motor de pronunciación preciso OpenPronounce (futuro, rama archivo/t-027-openpronounce: NO BORRAR)
T-043 Calibrar la corrección de escritura libre según el nivel (Claude)
T-044 Apelación con justificación escrita o grabada (Claude)
T-046 v2 Grabación de Speaking: corte más rápido y sin "Confirmar respuesta" (Claude)
```

Referencias: documento funcional v0.3 §4.1, §5, §8, §15, §16, §17, §17.1, §39, §41 (Audio), §42 (Audio).

---

## T-025 — Listening: comprensión auditiva con voz sintética

**Prioridad:** P1 — Alta (siguiente a implementar)  
**Estado:** Resuelta (PR #10 a `main`)

Resolución final (modelo de modalidades, decisión arquitectónica acordada):
Listening **no es un tipo de ejercicio**. `Exercise.presentation_mode` (READ | LISTEN) y
`Exercise.response_mode` (WRITE | SELECT | SPEAK), `Attempt.response_mode`, estímulo unificado
`content.stimulus` (+ `stimulusLang`, `stimulusRate`). Los mismos tipos existentes se presentan
leídos o escuchados; la corrección no cambia. Motor: 30 % LISTEN y al menos 1 por clase; los 4 temas
de comprensión auditiva de A1 son solo LISTEN. Dashboard "Por modalidad" (Escucha) y examen con
al menos 3 escuchados y mínimo del 60 % en la modalidad. Voz del navegador, sin guardar audio.
Migración `0007_modalities`. Detalle en `docs/guia_mvp_funcional.md` §6.3.
El diseño original de abajo (tipos `listening_*`) quedó **reemplazado** por este modelo.  
**Referencia:** documento funcional §15, §43.6

Objetivo: ejercicios donde el alumno **escucha** un texto en inglés y responde, sin ver el texto
hasta la corrección.

Decisiones:

1. **Voz sintética del navegador** (Web Speech API, `speechSynthesis`):
   - sin costo, sin backend, sin API key; voces en inglés disponibles en Chrome/Edge/Windows;
   - voz de proveedor (OpenAI / Gemini TTS) queda como mejora opcional, no en esta tarea.
2. **No se guarda audio** (§15): se guarda el texto y los parámetros de reproducción
   (`lang`, voz preferida, velocidad) y el audio se regenera en cada reproducción.

Alcance:

1. **Tipos de ejercicio nuevos:**
   - `listening_multiple_choice`: escuchar y elegir (evaluación determinística);
   - `listening_fill_blank`: escuchar y completar la palabra que falta / dictado corto
     (evaluación híbrida, misma normalización que `fill_blank`).
2. **Contenido del ejercicio:** `content.audioText`, `content.audioLang` (`en-US` / `en-GB`) y
   `content.rate` sugerido por nivel. El texto se usa solo para sintetizar la voz y **no se
   muestra en pantalla** hasta la corrección (ver "Riesgo" abajo).
3. **Currícula A1:** nueva área `listening` con skills, por ejemplo:
   - números, precios y horas;
   - datos personales (nombre, edad, país, deletreo);
   - diálogos cortos cotidianos (saludos, comprar, pedir comida);
   - instrucciones simples.
   Con ejemplos semilla (para el mock y como guía de la IA) y **lección** por skill
   (estrategias: anticipar, palabras clave, números).
4. **Generación:** reglas en el prompt: texto de 1–4 oraciones en A1, vocabulario del nivel,
   una sola respuesta defendible, la pregunta no se responde sin escuchar.
5. **Reproductor en la clase:**
   - botón Play / Pausa, "Escuchar de nuevo", velocidad 0.75× / 1×;
   - aviso claro si el navegador no tiene voces en inglés (y cómo instalarlas);
   - el texto se muestra **después** de la corrección, junto al feedback.
6. **Progreso / examen:** área `Listening` en el dashboard; el examen de nivel (T-024) suma
   ejercicios de listening al blueprint y el mínimo por área la incluye.
7. **Tests:** generación y validación de los tipos nuevos, que `audioText` no se filtre antes de
   corregir, evaluación, examen con el área nueva.

Riesgo a resolver en el diseño: para sintetizar en el navegador el frontend necesita el texto.
Opciones: (a) enviarlo en un campo separado y no mostrarlo (un usuario técnico podría verlo en
las herramientas del navegador — aceptable en práctica, no en examen); (b) en el examen,
sintetizar en el backend con un proveedor TTS. Decidir al implementar.

Fuera de alcance: voces de proveedores pagos, guardar audio.

---

## T-026 — Speaking: grabar, transcribir y corregir

**Prioridad:** P2 — Media  
**Estado:** **RESUELTA**  
**Referencia:** documento funcional §16, §17.1, §43.7

Speaking queda implementado como **modalidad de respuesta** (`response_mode = SPEAK`) sobre
los tipos de ejercicio existentes; no crea un tipo de ejercicio nuevo.

Implementado:

1. **Captura en navegador** con `MediaRecorder`, límite de duración, reproducción previa,
   regrabación libre en práctica y confirmación explícita de la respuesta.
2. **Transcripción en backend** mediante conexiones compatibles con audio:
   - OpenAI;
   - Gemini;
   - MOCK para desarrollo/tests;
   - Anthropic se excluye del router de audio.
3. **Failover por prioridad** entre conexiones compatibles con audio.
4. **Transcripción literal**: el texto resultante entra al evaluador existente sin corregir
   previamente la gramática o el contenido del alumno.
5. **Sin ayuda visual involuntaria**: la transcripción se guarda internamente como borrador
   pero no se muestra al alumno antes de finalizar/corregir. La UI solo confirma
   `Respuesta grabada`.
6. **Audio temporal**: el backend procesa el audio y no lo persiste. Se conservan la
   transcripción y la duración.
7. **Combinación LISTEN + SPEAK** soportada.
8. **Generación**: SPEAK se aplica a tipos compatibles existentes (`fill_blank`, `rewrite`,
   `short_writing`) únicamente cuando hay una conexión con audio disponible.
9. **Progreso y examen** reutilizan la modalidad `SPEAK` ya incorporada por T-025.
10. **Migración** `0008_speaking_audio` con `down_revision = "0007_modalities"`.
11. **Tests y CI** de backend/frontend aprobados.

La evaluación específica de pronunciación/fonética queda separada en **T-027**.

---

## T-027 — Pronunciación / fonética

**Prioridad:** P3 — Baja (después de T-026)  
**Estado:** Resuelta (PR #14 a `develop`)

Resolución: práctica de fonética orientativa en el navegador (ChatGPT) + evaluación final
**estimada por la IA en la misma llamada que transcribe** (Gemini; OpenAI transcribe sin
pronunciación; Anthropic sin audio). `pronunciation_result` con el contrato acordado y
`estimated: true`; migración `0009_pronunciation_result`. Audio procesado al entregar la clase y
nunca persistido en el servidor. OpenPronounce (funcionando, pero lento y pesado) queda guardado
en la rama `archivo/t-027-openpronounce` → T-039.  
**Referencia:** documento funcional §17, §17.1

Objetivo: evaluar **cómo** se pronuncia, no solo qué se dijo. La transcripción no alcanza (§16).

Propuesta:

1. **Proveedor especializado:** Azure Speech — *Pronunciation Assessment* (puntaje por
   fonema/palabra, precisión, fluidez, completitud y prosodia; capa gratuita mensual).
   Alternativas a evaluar: Speechace, ELSA API. Una evaluación cualitativa con Gemini (sin
   puntaje por fonema) puede servir como fallback.
2. **Nuevo tipo de conexión "servicio de voz"** (proveedor `AZURE_SPEECH`: key + región),
   guardada encriptada como las de IA, con prueba de conexión y límites.
3. **Ejercicio `read_aloud`:** leer en voz alta una oración de referencia del nivel
   (la evaluación por fonema necesita texto de referencia). En habla libre (T-026) solo se
   podría medir fluidez.
4. **Audio:** convertir en el navegador al formato que pida el servicio (ej. WAV PCM 16 kHz
   mono); temporal, se descarta después de evaluar.
5. **Persistir** (§17.1): puntajes, palabras y fonemas problemáticos, feedback, transcripción.
6. **UI:** oración con las palabras problemáticas resaltadas y el fonema a practicar
   (ej. `/θ/` en *think*), opción de escuchar la pronunciación modelo (voz de T-025).
7. **Currícula / lecciones A1:** sonidos difíciles para hispanohablantes: `/θ/ /ð/`, `/v/ vs /b/`,
   vocales cortas y largas (*ship/sheep*), terminación *-ed*, `/h/`, *s* inicial (*sp-, st-*).
8. **Progreso:** área `Pronunciation` y palabras/fonemas a reforzar en la generación.

Decisión pendiente del usuario: crear cuenta de Azure (u otro proveedor).

---

## T-028 — Temas faltantes de A1 (documento funcional §4.1)

**Prioridad:** P2 — Media  
**Estado:** Resuelta (rama `feat/t-028-temas-a1`)

Resolución: A1 pasa de 24 a 37 temas (los 13 de la lista, cada uno con 2 ejemplos y lección).
Se reemplazó el "odd one out" de comida y el prompt prohíbe ese formato.
`tests/test_curriculum_content.py` valida todos los ejemplos semilla y las lecciones.

La currícula A1 actual tiene 20 skills. Comparada con §4.1, faltan:

1. **Saludos y presentaciones** (funcional: *Hello, Nice to meet you, How are you?*).
2. **Pronombres personales** (sujeto: *I, you, he, she, it, we, they*).
3. **Singular y plural** (-s, -es, -ies, irregulares: *man/men, child/children*).
4. **Have got** (posesión: *I have got / She has got*, negativo y preguntas).
5. **Imperativos** (*Open the door. Don't run.*).
6. **Demostrativos** (*this / that / these / those*).
7. **Preposiciones básicas de lugar** (*in, on, under, next to, behind*).
8. **Conectores básicos** (*and, but, or, because*).
9. **Vocabulario cotidiano faltante:** números, fechas, días y meses, colores, la casa, ropa.

Por cada skill: objetivos, tipos de ejercicio, **al menos 2 ejemplos semilla con consigna
clara y una sola respuesta** (lección de T-017) y **lección** (T-020). Revisar también los
ejemplos existentes tipo "odd one out".

Criterio de cierre: el test `test_every_a1_skill_has_a_lesson` sigue pasando y el examen
(T-024) cubre las áreas nuevas.

---

## T-029 — Descenso de nivel por evidencia transversal

**Prioridad:** P3 — Baja (tiene sentido cuando exista A2)  
**Estado:** Pendiente  
**Referencia:** documento funcional §8.2, §8.3

- Bajar el nivel operativo solo con evidencia **sostenida y en varias áreas**, nunca por una
  mala clase ni por una debilidad localizada (ej. solo *third person singular*).
- Proponerlo al alumno ("Te recomendamos reforzar A1") en lugar de aplicarlo sin aviso.
- La promoción ya está cubierta por el examen de nivel (T-024).

---

## T-030 — Currícula A2 → B2

**Prioridad:** P2 — Media (**después de completar A1**: T-025 a T-028)  
**Estado:** Futuro

- Un PR por nivel: A2, luego B1, luego B2 (`data/<nivel>.json` + `data/lessons/<nivel>.json`).
- Cada nivel nace con las **7 áreas**: Grammar, Vocabulary, Reading, Writing, Listening,
  Speaking, Pronunciation.
- Temas propuestos (a validar):
  - **A2 (~26):** pasado de *to be*, pasado simple, irregulares, pasado continuo, *going to*,
    *will*, comparativos, superlativos, frecuencia, contables/incontables, *much/many*,
    pronombres objeto, posesivos, preposiciones de lugar, *must/have to/should*,
    *would like*, *present perfect* inicial; vocabulario de viajes, compras, salud, casa, clima,
    tiempo libre.
  - **B1 (~28):** *present perfect* vs pasado, *present perfect continuous*, *past perfect*,
    *used to*, futuros, condicional 1 y 2, pasiva, relativas especificativas, estilo indirecto,
    *might/may/could*, gerundio vs infinitivo, conectores; trabajo, educación, ambiente,
    tecnología, *phrasal verbs*.
  - **B2 (~30):** condicional 3 y mixtos, *wish/if only*, pasiva completa y *have something
    done*, estilo indirecto completo, relativas explicativas, deducción en pasado, futuro
    continuo/perfecto, oraciones de participio, formación de palabras, colocaciones, registro.
- B2 probablemente necesite tipos nuevos: "corregir el error" y "formación de palabras".
- Con A2–B2 cargados, el test de nivelación (T-023) tiene contenido para ubicar al alumno.

---

## T-031 — Temáticas en tres capas (plataforma, organización, alumno) con portal

**Prioridad:** P3 — Baja (después de completar A1)  
**Estado:** Futuro

Problema detectado en pruebas: los ejercicios se repiten porque hay pocos contextos
(A1 tiene solo 4 temas de vocabulario y la IA imita los mismos ejemplos).

Idea central: separar **habilidad** (qué se practica: *present simple negativo*) de
**temática** (dónde sucede: fútbol, viajes, tecnología, aeronáutica…).

- Las **habilidades** siguen siendo curadas y estables (sostienen progreso, lecciones y examen).
- Las **temáticas** son abiertas: cada ejercicio combina habilidad + temática
  (20 habilidades × 40 temáticas = 800 combinaciones sin tocar la currícula).

Tres capas de temáticas:

| Capa | Quién la carga | Alcance | Ejemplo |
|---|---|---|---|
| Plataforma | PLATFORM_OWNER (y el equipo de desarrollo, ver T-032) | Todos | Viajes, deporte, salud, tecnología |
| Organización | ADMIN de la empresa | Solo sus miembros | Atención al cliente, ingeniería, aeronaves |
| Alumno | El propio alumno, en su perfil | Solo él | Fútbol, cocina, series |

Alcance:

1. **Modelo de datos:** tabla de temáticas (clave, nombre, descripción, capa, `organization_id`
   o `study_profile_id` según capa, estado BORRADOR/PUBLICADA, vocabulario sugerido por nivel).
   Las temáticas pasan de archivo a base de datos.
2. **Portal:**
   - portal de plataforma (T-006): ABM del catálogo base;
   - portal de organización (T-010): ABM de temáticas propias;
   - perfil del alumno: elegir intereses del catálogo.
3. **Asistente IA (propone, una persona aprueba):** se escribe el nombre de la temática y la IA
   arma un borrador (vocabulario por nivel, frases típicas, ejemplos); se revisa, se corrige y se
   publica. La IA nunca publica sola.
4. **Generación:** cada slot recibe una temática, rotando entre las no usadas recientemente y
   priorizando intereses del alumno y temáticas de su organización.
5. **Aislamiento B2B:** las temáticas de una organización no se ven en otra (tests en T-011).
6. Se combina con el anti-repetición (enviar a la IA lo ya visto por el alumno).
7. **Pedido en texto asistido por IA:** el alumno o el ADMIN escribe, por ejemplo,
   *"Quiero practicar con vocabulario de aviación"* o *"Cambiá los ejercicios a temas de
   viajes"*, y:
   - la IA lo interpreta y devuelve una **propuesta estructurada** (temática, alcance —próxima
     clase / próximas N clases / permanente—, nivel) que se muestra antes de aplicar;
   - la persona confirma, ajusta o cancela; recién ahí se guarda como temática o preferencia;
   - el texto solo puede cambiar el **contexto**: nunca nivel ni habilidades (el backend valida
     los campos y descarta el resto);
   - el texto libre nunca va directo al prompt de las clases (protección contra manipulación);
   - filtro de temas inapropiados y adaptación del vocabulario al nivel;
   - para el ADMIN, el resultado queda como temática en BORRADOR para aprobar.

---

## T-033 — Tema opcional al pedir una nueva clase (mejora rápida)

**Prioridad:** P2 — Media (chica; se puede hacer antes que T-031)  
**Estado:** Pendiente

Adelanto de T-031 para atacar la repetición sin esperar el portal:

1. Al tocar **Nueva clase**, campo opcional *"¿Sobre qué tema querés tu próxima clase?"*
   (ej.: *viajes*, *fútbol*, *mi trabajo en redes eléctricas*).
2. El backend valida el texto (largo máximo, filtro de temas inapropiados) y lo guarda en la
   solicitud de generación (`generation_request.theme`).
3. El generador lo usa **solo como contexto** de los ejercicios: no cambia nivel, habilidades ni
   tipos; el vocabulario se adapta al nivel.
4. El tema queda visible en la clase y en el historial.
5. Tests: el tema llega al prompt como contexto, textos inválidos se rechazan, el examen de
   nivel no acepta tema.

---

## T-032 — Incremento de contenido por versión

**Prioridad:** P2 — Media (proceso recurrente; primer incremento junto con T-028)  
**Estado:** En curso (recurrente)

- Incremento 1 (con T-028): todos los temas de A1 con al menos 2 ejemplos y uno por tipo admitido;
  13 temas nuevos con lección; test de calidad de contenido.

Además de lo que carguen organizaciones y alumnos (T-031), el producto tiene que salir
**completo de fábrica**: el equipo de desarrollo incrementa el contenido **en cada entrega**,
de forma planificada y versionada (no la IA "de la nada" en producción).

Qué se incrementa en cada versión:

1. **Temáticas base** del catálogo de plataforma (con vocabulario por nivel).
2. **Ejemplos semilla** por habilidad (objetivo: al menos 3–4 por habilidad y tipo, variados,
   con consigna clara y una sola respuesta — criterio de T-017).
3. **Lecciones** nuevas o ampliadas (más ejemplos y errores típicos).
4. **Temas de vocabulario** del nivel (números, fechas, colores, casa, ropa… — ver T-028).

Proceso por entrega:

```text
elegir metas del incremento (ej.: +10 temáticas, +2 ejemplos por habilidad)
  ↓
borrador asistido por IA (fuera de producción)
  ↓
revisión humana en el Pull Request
  ↓
tests de contenido (esquema, claves únicas, nivel, una sola respuesta en opción múltiple,
  toda habilidad con lección)
  ↓
merge + versión de contenido (ej. content v1.3) + changelog de contenido
```

Requisitos técnicos:

- **Versión de contenido** registrada (archivo/tabla) y visible en el portal de plataforma.
- **Carga idempotente:** si el contenido vive en base de datos (T-031), un import/seed que
  agrega y actualiza sin duplicar ni borrar lo cargado por organizaciones o alumnos.
- **Claves estables:** nunca renombrar claves de habilidades existentes (rompería el progreso);
  deprecar en lugar de borrar.
- **Métrica de cobertura** por nivel (temáticas, ejemplos por habilidad, lecciones) para
  planificar el siguiente incremento.

---

## T-034 — Evidencias por habilidad, dashboard por habilidad y balanceo adaptativo

**Prioridad:** P1 — Alta (el dashboard es lo más importante del producto)  
**Estado:** Resuelta (PR #15 a `develop`)  
**Responsable:** Claude

Resolución (detalle en `guia_mvp_funcional.md` §6.5–6.7):

1. **Evidencias:** señales por respuesta (escuchas, lento, prácticas; migración `0010_answer_signals`),
   varias evidencias por ejercicio, ayuda = media evidencia y marca de asistencia (lección, escuchar
   más de 2 veces o en lento, practicar más de 2 veces); con ayuda reciente no se da por dominado.
   think/sink → `PRONUNCIATION_ERROR` también sin IA (`classes/spoken.py`). Examen sin lento y
   2 escuchas persistentes.
2. **Dashboard:** tarjeta desplegable por habilidad, color por tramo, marca de ayuda, "de dónde vino"
   en Listening/Speaking/Pronunciation, evolución de la práctica aparte. Sin "Por modalidad".
3. **Balanceo:** hasta 2 habilidades flojas reforzadas por clase (área con más peso + ejercicio
   garantizado; Listening ≥2 escuchados; Speaking/Pronunciation ≥2 hablados; Writing escrito) y
   hasta 2 temas flojos; visible en "Esta clase refuerza". 4 temas nuevos de escritura A1.

Cambios respecto del plan original (decididos con Roberto, 2026-10-01):

- **Writing solo cuenta ejercicios del área Writing.** Contar *rewrite* de gramática como señal
  secundaria inflaba Writing (77 % real 56 %): reescribir una oración dada es Grammar.
- Balanceo por foco (máx. 2 habilidades) en vez de "mínimo 1 por habilidad": 7 habilidades no
  entran en 6 ejercicios; Listening y Speaking siguen teniendo mínimo 1 siempre.
- Pendiente para otra tarea: que una habilidad no sea "Dominado" si tiene muchos temas sin practicar.

Decisión de arquitectura (debatida 2026-09-30): **un ejercicio genera varias evidencias**.
Cada ejercicio tiene un **foco principal** (su habilidad) y puede dejar **señales** en otras
habilidades, cada una medida a su manera (no se copia el mismo puntaje).

Storytime de referencia: escuchar una pregunta y responder hablando.

| Qué pasó | Habilidad | Qué se mide |
|---|---|---|
| 4 reproducciones y uso de "lento" | Listening | esfuerzo para entender (sin IA) |
| 3 prácticas de pronunciación antes de grabar | Pronunciation | evolución (sin IA, estimado) |
| Grabó y confirmó | Pronunciation | resultado final (servicio de fonética) |
| Contenido de lo dicho | Speaking + su tema (Grammar…) | corrección (evaluador con la conexión de IA del usuario) |

### Etapa 1 — Modelo de evidencias (backend)

1. Cada respuesta guarda sus **señales**: reproducciones, uso de lento, ayudas
   (lección, pista, práctica de pronunciación con sus porcentajes), duración del audio.
2. Puntaje por habilidad:
   - **Tema** (Grammar, Vocabulary…): resultado; con lección pesa la mitad.
   - **Writing**: además de *short_writing*, recibe señal de todo ejercicio que exige
     **producir una oración** (*rewrite*, respuestas de varias palabras); completar una
     palabra no cuenta como escritura.
   - **Listening**: resultado ponderado por esfuerzo (inicial: 1 escucha normal = 100 %,
     −15 % por escucha extra, −20 % si usó lento, piso 40 %; valores configurables).
   - **Speaking**: resultado de lo dicho.
   - **Pronunciation**: resultado final; la evolución de las prácticas se muestra aparte
     (practicar no debe castigar: incentivar la práctica).
3. **Pedir lección / pista / práctica = señal de debilidad** del foco del ejercicio, aunque la
   respuesta final sea correcta.
4. **Pronunciación vs. contenido (decisión acordada):** la fonética se compara contra la
   **transcripción** (si sonó bien lo que dijiste); el contenido lo evalúa el corrector (si tu
   respuesta es correcta). No se mezclan: "he do" bien pronunciado = Grammar mal, Pronunciation bien.
   Caso a cubrir en T-034: palabras que suenan casi igual (*think/sink*, *very/berry*,
   *ship/sheep*). En ejercicios SPEAK, el corrector clasifica esa diferencia como
   `PRONUNCIATION_ERROR` (tipo ya existente) y esa señal suma en Pronunciation, no en el tema.
5. **Examen sin ayudas:** sin lección, máximo **2 escuchas** y **sin modo lento**
   (hoy el examen permite lento: corregir). Configurable a futuro desde portal de owner/ADMIN.

### Etapa 2 — Dashboard por habilidad

1. Una tarjeta por habilidad: Grammar, Vocabulary, Listening, Speaking, Pronunciation, Reading,
   Writing. Se elimina la sección "Por modalidad".
2. **Collapse** (nativo por ahora; Bootstrap en T-035), todo cerrado al entrar:
   - cabecera: %, barra, tendencia (↑ → ↓) y estado (Dominado / Aprendiendo / Sin practicar);
   - detalle: temas; en Listening/Speaking/Pronunciation, de qué temas vino la evidencia y cuánta
     ayuda se usó.

### Etapa 3 — Balanceo adaptativo visible

1. Selección en dos pasos:
   - **cuántos ejercicios por habilidad**: parejo al empezar de cero; después proporcional a lo
     flojo, con mínimo 1 por habilidad;
   - **qué temas dentro de cada habilidad**: los más flojos primero (ya existe).
2. Si Writing es lo más flojo, la clase trae más ejercicios de **producir oraciones**.
3. **Visible:** cada clase indica qué refuerza ("Esta clase refuerza: Writing (oraciones),
   Present Simple negativo").
4. **Contenido:** sumar temas de escritura A1 (rutina, mensaje corto, describir familia/casa,
   responder con oraciones completas) — incremento de T-032.

Entrega: **una rama por etapa** desde `develop`, cada una probada por Roberto.

---

## T-035 — Migración visual a Bootstrap con tema configurable

**Prioridad:** P3 — Baja (después de T-034)  
**Estado:** Pendiente

1. Migrar el frontend a Bootstrap (grilla *responsive*, collapse, modales, tabs) de forma
   completa, no solo una pantalla, para no mezclar dos sistemas de estilos.
   Relación: T-009 (refactor de componentes) y T-015 (identidad visual).
2. **Tema por empresa** (multiempresa §28): la empresa **no carga CSS ni Bootstrap propio**
   (descartado por seguridad y soporte), sino que **configura valores** del tema —colores,
   tipografía, logo, bordes— que se aplican a las variables de Bootstrap (`--bs-primary`, etc.).
   Así se personaliza el diseño sin código arbitrario.
3. Tema por defecto de Librería Inglés definido por la plataforma.
4. El collapse nativo de T-034 se reemplaza por el de Bootstrap sin cambiar la lógica.

---

## T-036 — Reglas de examen y aprendizaje configurables desde portal (owner / ADMIN)

**Prioridad:** P3 — Baja (futuro; requiere portales T-006 / T-010)  
**Estado:** Pendiente

Hoy los parámetros están fijos en código (`backend/app/exams/service.py`,
`backend/app/classes/generation.py`, `backend/app/progress/service.py`). Pasarlos a
configuración editable:

| Parámetro | Valor actual |
|---|---|
| Reproducciones de audio en examen | 2, sin modo lento |
| Promedio mínimo para aprobar | 70 % |
| Mínimo por área / modalidad | 60 % |
| Habilitación del examen | 70 % de temas practicados y 70 % de promedio |
| Espera para reintentar el examen | 24 h |
| Ejercicios del examen por área | 5/3/2/2/2 (+ mínimo 3 escuchados) |
| Porción de ejercicios escuchados en clases | 30 % (mínimo 1) |
| Peso de una respuesta con ayuda (lección/pista) | 50 % |
| Penalización por esfuerzo en Listening (T-034) | −15 % por escucha extra, −20 % lento, piso 40 % |

Niveles de configuración:

1. **Plataforma (PLATFORM_OWNER):** valores por defecto para todos.
2. **Organización (ADMIN):** puede ajustar dentro de rangos permitidos por la plataforma
   (ej.: exigir 80 % para su equipo), solo para sus miembros.
3. Validación de rangos en backend; los cambios no afectan exámenes ya rendidos
   (se guarda la regla aplicada en cada resultado).

---

## T-037 — Bloquear el formulario al enviar la clase

**Prioridad:** P1 — Alta (bug)  
**Estado:** Resuelta (PR #14 a `develop`)

Resolución: formulario bloqueado mientras se procesan audios y se envía (ChatGPT), solo lectura
después; se desbloquea si el envío falla. Además: "Finalizar" habilitado solo con todos los
ejercicios respondidos (las habladas, confirmadas), aviso de grabaciones sin confirmar y botón
"Ir al primero pendiente". La lección sigue consultable con la clase corregida (solo lectura).

Detectado en prueba: después de tocar **Finalizar y comprobar** los controles siguen habilitados
(se puede cambiar una opción o un texto después de mandar a corregir).

1. Al tocar Finalizar, bloquear **todos** los controles de la clase (opciones, textos, grabación,
   práctica, lección) mientras se procesan los audios y se envía.
2. Una vez enviada (esperando corrección o corregida), la clase es solo lectura.
3. Mensaje visible durante el envío ("Procesando audios y corrigiendo…").
4. Si el envío falla, se desbloquea para reintentar sin perder lo respondido.
5. Test de que no se puede modificar una respuesta después de enviar (backend ya rechaza;
   el frontend no debe permitirlo).

---

## T-038 — Publicación: servidor para backend con fonética + frontend

**Prioridad:** P2 — Media  
**Estado:** Pendiente · servidor elegido: **Render** (Roberto ya lo usa)

Nota Render: el plan gratuito tiene 512 MB de RAM; PyTorch + modelo de fonemas necesita
2–4 GB. Para el backend con fonética hace falta un plan pago (verificar precios) o separar la
fonética en un servicio aparte. Windows/local: OpenPronounce requiere espeak-ng instalado y
`PHONEMIZER_ESPEAK_LIBRARY` / `PHONEMIZER_ESPEAK_PATH` configuradas.

1. **Frontend Angular:** Vercel (o similar) es viable.
2. **Backend FastAPI + OpenPronounce:** Vercel no es viable (límites de tamaño y tiempo de las
   funciones Python; PyTorch + ~2,5 GB de modelos). Necesita servidor propio o servicio con
   memoria suficiente (Render, Railway, Fly.io, VM). Requiere `ffmpeg` y `espeak-ng`.
3. Voz de referencia de OpenPronounce: por defecto gTTS (internet, Google); evaluar Piper
   (local) para no depender de red.
4. PostgreSQL en lugar de SQLite, HTTPS (necesario para el micrófono) y T-008 (configuración
   de producción).

---

## T-039 — Motor de pronunciación preciso (OpenPronounce)

**Prioridad:** P3 — Baja (futuro; requiere servidor con más recursos, ver T-038)  
**Estado:** Pendiente · código guardado en la rama de archivo `archivo/t-027-openpronounce`.
**No borrar esa rama hasta implementar esta tarea** (decisión de Roberto, 2026-10-01): en las
limpiezas de ramas quedan `main`, `develop` y esta.

Decisión (2026-10-01): por defecto la pronunciación la estima la **IA en la misma llamada que
transcribe** (rápida, sin instalaciones, publicable en Render gratis). OpenPronounce funcionó
(ChatGPT, con `setup-pronunciation.ps1` para FFmpeg/eSpeak NG portables) pero es lento en CPU,
pesado de instalar (PyTorch + ~2,5 GB de modelos) y sus puntajes salen bajos sin calibrar
(frases bien dichas en 67–70 %). Se guarda como **motor preciso opcional**.

Para retomarlo:

1. Partir de la rama `archivo/t-027-openpronounce` (adaptador `backend/app/pronunciation.py`,
   script de instalación, tests).
2. Motor configurable: `PRONUNCIATION_ENGINE=ai | openpronounce` (por defecto `ai`); con
   `openpronounce` no instalado, caer a `ai` sin errores.
3. **No bloquear la corrección:** el contenido se muestra al instante y la pronunciación se
   calcula en segundo plano ("calculando pronunciación…"); precargar el modelo al iniciar.
4. **Calibrar puntajes** con grabaciones de referencia (hablantes con acento hispano que
   pronuncian bien no deberían quedar debajo de ~80 %); mostrar palabras/fonemas a mejorar.
5. Servidor con 2–4 GB de RAM (T-038), `espeak-ng` y `ffmpeg` disponibles.
6. Mismo contrato `pronunciation_result` (con `estimated: false` para este motor).

---

## T-040 — Dockerizar la aplicación y su configuración

**Prioridad:** P2 — Media  
**Estado:** Pendiente · para evaluar antes de despliegue estable

Objetivo: poder levantar Librería Inglés de forma reproducible con Docker, evitando configurar
manualmente Python, Node, dependencias del sistema y variables en cada máquina.

Alcance a evaluar:

1. **Backend FastAPI:** imagen propia con dependencias Python y migraciones Alembic.
2. **Frontend Angular:** build reproducible y servidor web dentro de contenedor.
3. **Configuración:** variables sensibles y de entorno fuera de la imagen (`.env` / secrets);
   separar claramente desarrollo y producción.
4. **Base de datos:** usar volumen para desarrollo y preparar `docker-compose` para PostgreSQL
   cuando se abandone SQLite (relación con T-038).
5. **Arranque simple:** objetivo de desarrollo tipo `docker compose up` para levantar el stack
   completo sin instalaciones adicionales salvo Docker.
6. **Pronunciación:** la solución principal por IA no necesita dependencias locales especiales;
   si se habilita OpenPronounce (T-039), resolver `ffmpeg`, `espeak-ng` y modelos dentro de
   una imagen/perfil separado para no hacer pesado el contenedor normal.
7. **Persistencia y seguridad:** no incluir API keys, JWT secrets, bases de datos ni archivos
   generados dentro de la imagen o del repositorio.

**Criterio:** Docker debe simplificar la instalación y el despliegue; no introducir una segunda
configuración paralela difícil de mantener.

---

## T-041 — Mostrar proveedor y modelo de IA usados en cada clase

**Prioridad:** P3 — Baja  
**Estado:** Resuelta (PR #16 a `develop`)  
**Responsable:** ChatGPT

Objetivo: hacer visible qué conexión de IA y qué modelo se usaron realmente en la clase,
tanto para dar trazabilidad como para evitar que textos como “generada con Google Gemini”
parezcan una firma o crédito del sitio.

Alcance:

1. **Persistir la información usada realmente:** proveedor/agente, nombre de la conexión y
   modelo efectivo de IA en la generación/corrección que corresponda. No alcanza con mostrar
   cuántas conexiones están disponibles: debe poder saberse cuál intervino.
2. **Pantalla de conexiones IA:** además del estado y cantidad disponible, mostrar cuál es la
   conexión/modelo que se está usando como primera opción en ese momento, respetando prioridad,
   disponibilidad, backoff y failover.
3. **Clase / formulario:** reemplazar la leyenda inferior actual por una descripción explícita
   del proceso, por ejemplo:

   `Clase realizada por el agente Google Gemini · motor gemini-2.5-flash`

   La redacción final puede ajustarse, pero debe comunicar proveedor + modelo y no parecer
   un crédito del propietario de la página.
4. **Pronunciación por IA:** donde hoy se muestra `estimada por IA (GEMINI)`, agregar también
   el modelo/motor que realizó esa evaluación cuando esté disponible.
5. **Failover:** si durante una operación se cambia de conexión o proveedor, mostrar/persistir
   el que efectivamente produjo el resultado, no solamente el configurado como prioritario.
6. **Histórico:** la información debe quedar asociada a la clase/resultado para que una clase
   antigua siga indicando qué proveedor y modelo utilizó aunque luego cambie la configuración.

**Criterio:** distinguir claramente `proveedor/agente` (Gemini, OpenAI, etc.), `conexión`
configurada y `modelo/motor` (por ejemplo `gemini-2.5-flash`).

---

## T-042 — Permitir al PLATFORM_OWNER revelar y copiar API keys administradas

**Prioridad:** P3 — Baja  
**Estado:** En curso  
**Responsable:** ChatGPT

Objetivo: permitir que únicamente el dueño de la plataforma (`PLATFORM_OWNER`) pueda revelar
y copiar desde la interfaz una API key ya guardada cuando necesite reutilizarla o administrarla.

Alcance y restricciones:

1. **Solo PLATFORM_OWNER:** ningún usuario común, ADMIN de organización ni otra cuenta puede
   recuperar una credencial ya persistida.
2. **Solo conexiones que el owner puede administrar:** conexiones PLATFORM y, si corresponde,
   conexiones ACCOUNT pertenecientes a su propia cuenta. Nunca permitir leer las BYOK de otros usuarios.
3. **Acción explícita:** la key permanece enmascarada por defecto; botones `Mostrar` / `Copiar`
   solicitan el secreto al backend únicamente al usarlos.
4. **No exponerla en listados:** el endpoint normal de conexiones sigue devolviendo únicamente
   `credentialHint`; la credencial completa debe tener un endpoint específico protegido por rol.
5. **Auditoría:** registrar quién reveló/copió una credencial, qué conexión y cuándo, sin guardar
   el valor de la key en logs.
6. **Frontend:** evitar persistir el secreto en estado más tiempo del necesario; limpiar el valor
   después de copiar/ocultar y no almacenarlo en localStorage/sessionStorage.

**Criterio de seguridad:** esta capacidad es una excepción deliberada a la regla actual de que
las API keys cifradas nunca regresan al navegador, y por eso debe quedar limitada al owner y a
credenciales bajo su propia administración.

---

## T-043 — Calibrar la corrección de escritura libre según el nivel

**Prioridad:** P1 — Alta  
**Estado:** Resuelta (PR #18 a `develop`) · Claude  
**Responsable:** Claude  
**Relación:** T-021 (ortografía), T-019 (presentación), T-034 (puntaje de Writing)

Origen (Roberto, 2026-10-01): "siempre que tengo que escribir una sentencia la IA me machaca".
Si la IA corrige las oraciones escritas con más exigencia que la del nivel, el puntaje de
Writing miente para abajo y desmotiva justo donde más hay que practicar.

1. **Diagnóstico con datos reales:** exportar los intentos de *short_writing* de Roberto y
   revisarlos uno por uno: ¿errores reales de A1, o estilo/naturalidad contados como error?
2. **Informe** con los casos injustos antes de cambiar nada.
3. **Ajuste** (con OK): prompt del evaluador calibrado por nivel (qué es error en A1 y qué es
   sugerencia), estilo/naturalidad nunca descuentan, ortografía según T-021; tests con esos casos.

Diagnóstico (2026-10-01, 9 escrituras libres reales de Roberto en A1):

| Resultado | Casos | Causa |
|---|---|---|
| Nota dura | 2 (67 % → ~90; 38 % → ~60-65) | 1 error chico = −33 %; mayúsculas/puntos como gramática (6 de 12 "errores") |
| Algo dura | 2 | errores reales + mayúsculas sumando |
| Justa | 5 | errores reales o la respuesta no cumplía la consigna |

Causas de severidad: (1) mayúsculas/puntuación contadas como GRAMMAR_ERROR; (2) el mismo
error repetido contado varias veces; (3) un concepto castigado por errores de otro tema;
(4) puntaje a saltos 100/50/0. Errores reales que se repiten (la corrección está bien):
*like + verbo* ("I like read" → "I like reading / to read") y *at the morning* → *in the morning*.

Cambios: puntaje fino por concepto acotado a la banda de su estado; mayúsculas/puntuación →
una observación `MECHANICS_NOTE` que no descuenta; errores repetidos se agrupan (`occurrences`,
"×3" en pantalla); prompt con evaluación por concepto y calibración por nivel. Tests con casos
de la misma forma que los reales (sin copiar los textos del alumno).

---

## T-044 — Apelación con justificación

**Prioridad:** P2 — Media  
**Estado:** Pendiente  
**Responsable:** Claude  
**Relación:** reemplaza el "¿Por qué?" de T-016 (descartada), T-034 (evidencias)

Origen (Roberto, 2026-10-01): al apelar, la IA vuelve a corregir lo mismo sin información
nueva y repite su criterio. La apelación debe permitir explicar por qué la respuesta está bien.

```text
"Creo que mi respuesta es correcta"
   └─ el alumno justifica (opcional)
        ├─ flojo en Writing                → la app sugiere justificar ESCRIBIENDO
        └─ flojo en Speaking/Pronunciation → la app sugiere justificar GRABANDO (si hay IA con audio)
        (siempre puede elegir la otra forma)
   └─ IA re-corrige: respuesta + justificación como CONTEXTO (no se deja convencer por elocuencia)
   └─ nota del ejercicio = solo si la respuesta es correcta
   └─ justificación en inglés = evidencia aparte (Writing o Speaking/Pronunciation)
```

1. **Parte 1:** justificación escrita (sin costo extra: va en la misma llamada de la apelación).
2. **Parte 2:** justificación grabada (1 llamada de audio extra por apelación; apelar es poco
   frecuente) y sugerencia automática según la habilidad floja.
3. Se mantiene: una apelación por intento; la regla de ortografía de T-021; si la IA acepta,
   la respuesta queda como aceptada del ejercicio.

---

## T-045 — Presentar el examen de nivel solo cuando el alumno esté cerca de habilitarlo

**Prioridad:** P2 — Media  
**Estado:** Resuelta (PR #19 a `develop`)  
**Responsable:** ChatGPT

Problema detectado en prueba real: con muy poca práctica el inicio ya muestra el bloque
de examen y puede marcar en verde el requisito de promedio (por ejemplo, 83,3 % después
de una sola clase), aunque todavía falta mucha cobertura del nivel. El dato es correcto
como promedio de lo practicado, pero la presentación resulta engañosa.

Solución acordada:

1. **Lejos del examen:** no mostrar el bloque de examen mientras la cobertura del nivel sea
   menor al 60 %.
2. **Cerca del examen (60 % a <70 % de cobertura):** mostrar un bloque de anticipación,
   por ejemplo `Te estás acercando al examen A1`, con:
   - progreso de cobertura hacia el 70 % requerido;
   - promedio actual como información (`Vas bien: 83,3 %`) si alcanza el 70 %, pero sin
     presentarlo como requisito formal ya cumplido;
   - sin botón para rendir todavía.
3. **Desde 70 % de cobertura:** mostrar el bloque formal de examen con ambos requisitos:
   cobertura ≥70 % y promedio ≥70 %, cada uno con su estado real.
4. **Habilitación:** el examen solo puede iniciarse cuando se cumplen ambos requisitos;
   esta regla de backend se mantiene.
5. **Datos explícitos:** el frontend no debe inferir porcentajes leyendo textos de `detail`;
   el estado del examen debe exponer cobertura, cantidad practicada, total y umbrales necesarios.

**Criterio UX:** evitar que un alumno que recién empieza reciba señales prematuras de que
ya está en condiciones de rendir, sin ocultar que su rendimiento actual viene bien cuando
realmente se está acercando al requisito.

---

## T-046 — Detención automática por silencio en respuestas Speaking

**Prioridad:** P2 — Media  
**Estado:** Resuelta (PR #20 a `develop`)  
**Responsable:** ChatGPT

Problema detectado en uso real: en los ejercicios de Speaking el alumno debe iniciar la
grabación y luego pulsar manualmente `Detener`, mientras que la práctica de pronunciación
finaliza sola cuando el navegador detecta que terminó de hablar.

Objetivo: mantener `MediaRecorder` para conservar el audio real de la respuesta, pero mejorar
la experiencia agregando detección local de fin de habla.

Solución:

1. Detectar actividad de voz localmente con Web Audio API durante la grabación.
2. No detener la grabación hasta haber detectado voz real al menos una vez.
3. Después de detectar voz, detener automáticamente tras aproximadamente 1,8–2 segundos
   continuos de silencio.
4. Mantener siempre el botón `Detener` para corte manual.
5. Mantener el límite máximo actual como salvaguarda.
6. Si Web Audio API no está disponible, conservar el comportamiento manual actual sin bloquear
   el ejercicio.
7. La detección de silencio no debe enviar audio a servicios externos ni consumir IA.
8. Después del auto-stop se conserva el flujo actual: escuchar, confirmar o volver a grabar.

**Criterio UX:** una pausa normal al hablar no debe cortar prematuramente la respuesta; el
auto-stop debe sentirse similar a la práctica de pronunciación sin sacrificar el audio final.

---

## T-046 v2 — Grabación de Speaking: corte más rápido y sin "Confirmar respuesta"

**Prioridad:** P2 — Media  
**Estado:** En curso · Claude  
**Relación:** T-046 (auto-stop por silencio, ChatGPT), T-034 (evidencias/señales)

Problemas detectados por Roberto al usar T-046:

1. El corte automático tarda 1-2 s de más después de terminar de hablar.
2. Paso de más: grabar → corta → **Confirmar respuesta**. La respuesta grabada ya es la
   respuesta: se transcribe y corrige recién al enviar la clase, así que confirmar no aporta.

Flujo nuevo:

```text
Grabar → hablar → corta solo (más rápido) → queda como respuesta ✓
                                           └─ "Volver a grabar" (opcional)
                                                 └─ cuenta como señal de esfuerzo en Speaking
```

1. Ajustar la detección de fin de habla para cortar antes sin cortar pausas normales.
2. Quitar "Confirmar respuesta": la grabación se guarda sola al cortar (manual o automático).
3. "Volver a grabar" se registra como señal (como las escuchas extra en Listening) y aparece en
   el resumen de esfuerzo; muchas regrabaciones marcan Speaking como asistido.

---

# 3. Orden sugerido de trabajo

Para continuar probando la aplicación sin frenar el MVP:

```text
1. Probar flujo personal completo
2. T-001 CI + protección de main
3. T-002 revisar npm audit
4. T-003 limitar MVP actual a BYOK personal
5. T-008 endurecer configuración productiva
6. seguir pruebas funcionales
7. T-009 refactor frontend cuando empiece a crecer más
8. T-004 / T-005 al comenzar planes y B2B
9. T-007 antes de producción pública
```

---

# 4. Regla de ramas a partir de ahora

Flujo vigente (desde 2026-09-30): **`develop` es la rama de integración** y **solo Roberto pasa
`develop` → `main`**.

```text
develop actualizado
  ↓
rama nueva de la tarea (feat/t-XXX-...)
  ↓
cambios + tests
  ↓
Roberto prueba la rama
  ↓
OK de Roberto
  ↓
el desarrollador abre el Pull Request rama → develop
  ↓
se elimina la rama de la tarea
  ↓
la tarea se marca como resuelta en esta rama de tareas
  ↓
(Roberto) develop → main
```

Reglas:

- Nunca trabajar sobre `main` ni sobre `develop` directamente; siempre en una rama propia.
- No reutilizar ramas antiguas como base para nuevas entregas.
- Migraciones: numerar a continuación de la última de `develop` para no chocar entre ramas.
- Esta rama (`docs/tareas-pendientes-v0.1`) es solo para administrar tareas.
