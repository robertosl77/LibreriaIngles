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

**Estado:** Reabierta para revisión (2026-10-03) · la resolución anterior de PR #28 sigue vigente para
las vulnerabilidades originales.

Resolución anterior (2026-10-01): `npm audit` pasó de **29 (2 críticas, 14 altas) a 0**.

1. Causa: Angular 19 ya no recibe parches (todas las 19.x afectadas: XSS en el compilador,
   hidratación/SSR, etc.), y sus herramientas fijaban versiones viejas de vite, piscina, tar…
   Por eso `npm audit fix` no podía hacer nada sin `--force`.
2. Actualización oficial con `ng update`, de a una versión: 19 → 20 → 21 (LTS). Las migraciones
   automáticas solo agregaron `provideZoneChangeDetection()` (Angular 21 es *zoneless* por
   defecto; la app sigue con zone.js) y ajustaron `tsconfig`. TypeScript 5.9.
3. Builder nuevo `@angular/build` en lugar de `@angular-devkit/build-angular` (webpack): se van
   403 paquetes, incluidos webpack-dev-server/sockjs/uuid vulnerables.
4. `overrides: piscina 5.3.2` (la que ya usa Angular 22; misma versión mayor).
5. `start:remote` usaba `--disable-host-check` (no existe en el builder nuevo): ahora es
   `ng serve --configuration remote` (host 0.0.0.0, puerto 8081, `allowedHosts: true`).
6. CI: Node 22 y `npm audit --audit-level=high` en el job del frontend. Se borra el workflow
   viejo `t002-npm-audit.yml` (aplicaba `npm audit fix` automático en una rama que ya no existe).
7. Requisito: Node.js 22.12+ (o 20.19+/24+). Después de actualizar: `npm ci` en el frontend.

**Nueva detección (2026-10-03):** durante la validación de T-004, `npm audit --audit-level=high`
volvió a informar **9 vulnerabilidades altas** por el advisory
`GHSA-ch52-4w7c-c8xp` de `http-cache-semantics`, arrastrado por dependencias de
`@angular/cli`/npm (`make-fetch-happen`, `sigstore`, `pacote`, etc.). El build de Angular
sigue pasando. npm propone corregirlo únicamente con `npm audit fix --force`, que actualizaría a
Angular CLI 22.2.1 y es un cambio mayor; **no aplicar automáticamente** dentro de T-004. Revisar
como tarea separada.

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
**Estado:** Resuelta (PR #23 a `develop`) · Claude  
**Bloquea prueba local:** No

Resolución (2026-10-01): hasta ahora **cualquier** cuenta sin conexiones propias usaba las de
la plataforma (las del dueño). Ahora:

```text
usuario común   → solo sus conexiones propias (BYOK)
PLATFORM_OWNER  → las suyas + las de la plataforma
membresía paga  → (T-004) la habilitará; único punto a cambiar: platform_ai_allowed()
```

- `app/ai/service.py`: `platform_ai_allowed(account)` decide si la cuenta ve conexiones de
  plataforma; lo usan generación, corrección, audio y el contador de IA del inicio.
- Un usuario nuevo sin IA propia ve "Conectá una IA" y no puede crear clases hasta cargar la suya.
- Los tests de topes de consumo (T-006) se mantienen simulando una membresía.

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

## T-004 — Membresías, servicios, campañas e invitaciones

**Prioridad:** P1 — Alta (antes de publicar la app o cobrar)  
**Estado:** Diseño acordado (Roberto + Claude, 2026-10-01) · Etapa 1 (Servicios) resuelta (PR #26) · Etapa 2 (Campañas) resuelta (PR #34) · Etapa 3 (Invitaciones) en desarrollo/pruebas en `feat/t-004-invitations` · etapas 4–6 pendientes  
**Responsable:** Claude  
**Relación:** T-003 (cada usuario usa solo su IA propia: hoy decide `platform_ai_allowed()`),
T-005 (conexiones de IA de una organización), T-006 (portal del dueño con las keys de
plataforma), T-049 (tokens y costo por uso), T-050 (fidelización), T-051 (emails)

Base existente sin usar (migración inicial): tablas `plans` (`ai_source` BYOK / PLATFORM / HYBRID),
`subscriptions` (cuenta u organización, estado, fechas), `organizations`, `memberships`
(ADMIN/STUDENT) e `invitations`. Se reutilizan; los nombres de tablas pueden ajustarse.

### 1. El modelo

```text
VÍNCULO      (no se elige: se deduce)
   ¿vino invitado por una empresa?  sí → CORPORATIVO (empresa X)
                                    no → PERSONAL (cliente independiente, "sin empresa")

FUENTE DE IA (lo único que elige la persona)
   BYOK        → sus propias keys (corporativo: las keys que carga la empresa)
   PLATAFORMA  → las keys de sr.macros
   HÍBRIDO     → las propias primero; si fallan de fondo, las de sr.macros

SERVICIO     = fila del modelo de negocio (PERSONAL; CORPORATIVA futuro)
FUENTE IA    = columna fija (BYOK / PLATAFORMA / HÍBRIDO)
MEMBRESÍA    = servicio × fuente; se puede habilitar/deshabilitar
BENEFICIO    = servicio + fuente + duración/vigencia + política de otorgamiento

OTORGAMIENTO (cómo alguien recibe un servicio)
   PAGO        → lo contrata el cliente (futuro)
   INVITACIÓN  → alguien llega/reclama mediante un link (nominado o abierto)
   CAMPAÑA     → automático a un grupo (ej. "todos los que se registren desde hoy")
```

- **El servicio base** es Personal o Corporativa y se deduce del contexto de la cuenta.
  La **membresía** es la intersección efectiva entre ese Servicio y la Fuente de IA.
- **Hoy (sin pagos):** vínculo + fuente y ya funciona. **Con pagos:** triple restricción
  vínculo × fuente × pago (el pago habilita el servicio por un período, ej. mensual).
- Analogías: **home banking** (uno para personas, otro para empresas: el de empresas es el que
  tiene una empresa de por medio), AWS (base fija + uso variable) y el celular (cuenta controlada
  / línea libre).

### 2. Servicios, fuentes y membresías

El modelo se separa explícitamente en dos ejes fijos y una intersección configurable:

```text
                │ BYOK              │ PLATAFORMA          │ HÍBRIDO
────────────────┼───────────────────┼─────────────────────┼──────────────────────
PERSONAL        │ membresía         │ membresía           │ membresía
CORPORATIVA fut.│ membresía         │ membresía           │ membresía
```

**Decisión Roberto + ChatGPT, 2026-10-02:**

- **Servicios (filas):** hoy solo `PERSONAL`; futuro `CORPORATIVA`. Se muestran como información
  del modelo de negocio y no se crean, editan, activan ni desactivan desde el portal.
- **Fuentes (columnas):** `BYOK`, `PLATFORM` y `HYBRID`. También son fijas e informativas.
- **Membresías:** la intersección Servicio × Fuente sí se administra. El OWNER puede habilitar o
  deshabilitar, por ejemplo, `Personal × Híbrido`.
- Una membresía **no puede deshabilitarse** mientras tenga una cuenta vigente, un beneficio
  activo, una campaña ACTIVE/PAUSED o una invitación todavía canjeable vinculada.
- Una empresa concreta (por ejemplo Cacatúa) no es una fila: utiliza el servicio Corporativa.
- Agregar una nueva fila o una nueva fuente implica una decisión de modelo y cambios de código.
- Servicio **no lleva duración ni límites de consumo**. La duración pertenece exclusivamente a
  Beneficio y los límites actuales pertenecen a cada conexión de IA.
- **Costos (futuro):** PLATAFORMA = cuota fija estimada para cubrir los tokens; HÍBRIDO = base +
  uso a demanda de sr.macros, detallado como factura (T-049).
- **BYOK corporativo:** las keys las carga la empresa (paga la capacitación, no el empleado) →
  requiere T-005.

### 3. Campañas (sr.macros otorga un servicio automáticamente a un grupo)

```text
CAMPAÑA
  beneficio    → referencia un Benefit (ej. Plataforma 3 días)
  para quién   → ej. personas registradas a partir de que se activa la campaña
  estado       → activa / pausada / terminada
```

- **Panel de campañas de sr.macros.** Una campaña referencia un Beneficio; no vuelve a configurar
  servicio ni días.
- **Constructor híbrido de campañas (2026-10-03):** "Nueva campaña" ofrece tres entradas que
  convergen en el mismo formulario y el mismo `CampaignDraft`:
  1. **Plantillas** determinísticas para casos frecuentes; cargan condiciones/trigger/límites y el
     OWNER elige el Beneficio antes de guardar.
  2. **Describir con IA**: una conexión de IA de **plataforma** convierte lenguaje natural a un
     borrador revisable. Nunca persiste ni activa la campaña.
  3. **Manual**: mantiene el constructor completo.
  La IA recibe únicamente los campos soportados por el motor. Si se pide algo todavía inexistente
  (por ejemplo descuentos, precios o antigüedad de una suscripción paga), debe advertirlo y no
  inventar una condición equivalente.
- **La bienvenida es la primera campaña** (no algo fijo en el código): usa el beneficio
  "Bienvenida", configurado como PERSONAL + PLATAFORMA por 3 días. Deja probar la app sin
  saber qué es una API key. Como PedidosYa: cupones a todos al principio; después solo para
  fidelizar (T-050).

### 4. Invitaciones (un solo motor para plataforma y empresas)

**Decisión Roberto + ChatGPT, 2026-10-02:** existe **un solo motor de invitaciones**. No se construye
un motor para sr.macros y otro para empresas. La Etapa 3 habilita primero la gestión del
PLATFORM_OWNER; la Etapa 5/T-010 expondrá el mismo motor a los ADMIN de organización, limitado por
scope/permisos/capacidades.

```text
MOTOR DE INVITACIONES (100 % de capacidades)
             │
             ├── PLATFORM / OWNER (sr.macros)
             │      └── beneficios PERSONALES
             │
             └── ORGANIZATION / ADMIN (futuro T-010)
                    └── beneficios CORPORATIVOS
```

sr.macros se comporta conceptualmente como la "empresa dueña" para clientes individuales, pero
**Librería Inglés no se modela como una Organization**: el cliente personal no debe convertirse en
miembro corporativo ni heredar semántica ADMIN/STUDENT.

#### 4.1. Capa central de Beneficios: no duplicar servicio + días

Campañas e invitaciones **no deben configurar por separado la misma cosa**. Se extrae una capa
atómica reutilizable:

```text
PLAN / SERVICIO
¿Qué servicio existe?
        │
        ▼
BENEFICIO
¿Qué se otorga?
servicio + fuente + duración + política de conflicto
        │
        ├────────────────┐
        ▼                ▼
    CAMPAÑA          INVITACIÓN
cuándo/a quién       cómo se reclama
automáticamente      mediante link
        │                │
        └───────┬────────┘
                ▼
          grant_service()
```

Ejemplo:

```text
BENEFICIO
"Plataforma 30 días"
  servicio = Personal
  fuente = Plataforma
  duración = 30 días

CAMPAÑA "Volvé a estudiar" ────────┐
                                   ├── usa el MISMO beneficio
INVITACIÓN "Regalo amigo" ─────────┘
```

La comunicación **no pertenece al Beneficio**. El mismo beneficio puede llegar por aviso IN_APP,
email de invitación o link compartido por WhatsApp.

Política conservadora inicial al aplicar un beneficio:

- sin servicio otorgado vigente → se otorga normalmente;
- mismo servicio vigente → se suman los días;
- servicio vigente **distinto** → no se reemplaza silenciosamente y el canje no consume cupo;
- reemplazo/crédito/unificación requieren una política explícita futura (ver sección 10).

**Corrección de frontera de responsabilidades (2026-10-02):** `Plan/Service.duration_days` se elimina.
Servicio ya no tiene vigencia propia. Si una configuración anterior tenía duración en Servicio, la
migración 0017 la materializa en Beneficio antes de quitar la columna. Desde ese punto, vacío en
`Benefit.duration_days` significa explícitamente **sin vencimiento**, no "heredar del servicio".

El otorgamiento manual desde "Cuentas y servicios" también debe elegir un **Beneficio**, no volver a
pedir Servicio + días. Así los cuatro mecanismos convergen en la misma capa:

```text
MANUAL ───────┐
CAMPAÑA ──────┤
INVITACIÓN ───┼──> BENEFICIO ──> grant_service() ──> Subscription
PAGO futuro ──┘
```

Para estados booleanos reutilizar el mismo control visual Activo/Inactivo en Servicios y Beneficios.
Campañas e Invitaciones conservan controles distintos porque tienen ciclos de vida multietapa.

#### 4.2. Dos modalidades del mismo objeto Invitation

```text
NAMED / NOMINADA
  destinatario = email concreto
  cupo = 1
  solo esa identidad puede canjear el beneficio

OPEN / ABIERTA
  destinatario = ninguno
  cupo = 1, N, ...
  cualquier cuenta con el link puede canjear mientras quede cupo
```

`max_redemptions` = **cantidad máxima total de canjes del link por cuentas distintas**. No significa
que una misma cuenta pueda cobrar el beneficio N veces. El canje de la misma invitación por la misma
cuenta es idempotente.

Casos:

```text
OPEN + cupo 1   → regalo transferible: quien lo use primero lo consume
OPEN + cupo 10  → las primeras 10 cuentas distintas reciben el beneficio
NAMED           → amigo@ejemplo.com; otra identidad no recibe ese beneficio
```

Si alguien abre una invitación NAMED pero inicia sesión con otro email, **no se rechaza el login**:
entra como usuario normal; simplemente no canjea la invitación. Las campañas normales (por ejemplo
Bienvenida) siguen pudiendo aplicarle.

Cuando el login sí llega con una invitación válida, el motor intenta el canje **antes** de evaluar
campañas de login/primer login. Así la invitación correcta no queda pisada ni bloqueada por la
campaña de bienvenida.

#### 4.3. Pre-invitación ≠ cuenta

Una persona invitada que todavía nunca ingresó no se agrega a "Cuentas y servicios". Vive en
**Invitaciones / pre-invitaciones pendientes**:

```text
pre-invitación
(email / nombre / apellido / beneficio / token / estado)
        ↓
la persona llega + verifica su identidad
        ↓
cuenta existente o nueva
        ↓
canje
        ↓
Subscription origin=INVITATION
```

La invitación y sus canjes se separan:

```text
INVITATION
  qué beneficio ofrece
  quién la creó
  scope plataforma/organización
  modalidad NAMED/OPEN
  destinatario (si NAMED)
  token
  cupo
  vigencia
  estado

INVITATION_REDEMPTION (CANJE)
  qué cuenta la utilizó
  cuándo
  qué suscripción recibió
  resumen histórico del beneficio
```

Esto reemplaza el modelo de un único `accepted_at`: un link abierto puede producir muchos canjes y
cada uno necesita trazabilidad propia.

El token se busca por **hash** y se conserva además **cifrado** para que el OWNER pueda copiarlo y
T-051 pueda reenviar exactamente el mismo link sin guardar el secreto en texto plano.

#### 4.4. Email y carga masiva futura

Una invitación NAMED, tanto creada manualmente como generada por una futura importación de empleados,
**debe enviarse por email** cuando T-051 esté implementada. En Etapa 3 queda en cola
`email_status=PENDING`; mientras no exista proveedor de correo, el OWNER puede copiar el mismo link
como respaldo.

Para empresa (Etapa 5/T-010), el archivo CSV/XLS describe **personas, no reglas internas**:

```text
SÍ:
email
nombre
apellido
(+ datos personales opcionales que se definan: DNI, nacimiento, etc.)

NO:
rol
servicio
beneficio
plan
fuente de IA
permisos internos
```

El ADMIN primero selecciona/configura el beneficio y luego importa. Cada fila crea una invitación
NAMED independiente y el rol por defecto es **STUDENT**. El archivo no puede elevar privilegios ni
cambiar reglas de negocio por un error de tipeo.

#### 4.5. Recuperación sin link y controles corporativos futuros

Si un email corporativo precargado no recibe el correo o pierde el link, el futuro portal corporativo
debe poder detectar una invitación NAMED pendiente por **email verificado**. No debe incorporar a la
persona silenciosamente por usar un email corporativo: debe ofrecer explícitamente algo como:
"Tenés una invitación pendiente de Cacatúa. ¿Querés incorporarte?"

También queda para T-010 definir dominios permitidos por organización (`@cacatua.com`,
`@cacatua.com.ar`, etc.) y una política de capacidades controlada por PLATFORM_OWNER. Ejemplo:
sr.macros puede permitir a una empresa invitaciones NAMED y carga masiva, pero deshabilitar links
OPEN; si en el futuro habilita OPEN, puede exigir dominio corporativo verificado.

La invitación no es una membresía: es el medio de incorporación/otorgamiento. En el flujo
corporativo, el canje exitoso podrá además crear/activar la membresía STUDENT correspondiente.

### 5. Estructura: sr.macros como "empresa dueña"

```text
Librería Inglés (sr.macros, OWNER)  → servicios, campañas, invitaciones, keys de plataforma
Empresa X (ADMIN / STUDENT)         → invitaciones a empleados, keys de la empresa (T-005)
Cliente personal                    → "sin empresa" (NO es miembro de Librería Inglés:
                                       un ADMIN ve la actividad de sus miembros y eso no aplica)
```

### 6. Vigencia y vencimiento

- **Vigencia = duración del servicio otorgado** (invitación de 7 días: 07/10 → 14/10; pago
  mensual: 07/10 → 07/11). El historial de pagos es otra cosa (con los pagos).
- **Al vencer:** puede **ver** clases, resultados, progreso, historial y certificados; **no puede
  crear** clases ni exámenes hasta renovar.
- **Retención:** al año de vencida **se borra todo** (avisos previos: T-050).
- **Usuarios que ya existen** (ej. robertosl77): son PERSONAL + BYOK → siguen funcionando, sin
  borrar nada ni reconfigurar keys. sr.macros (OWNER) no vence nunca.

### 7. Híbrido: cuándo salta a las keys de sr.macros

```text
falla temporal (caída, red, rate limit)  → NO salta: reintenta con las propias al rato
falla de fondo (sin saldo, key inválida) → salta a sr.macros
siempre:
  · aviso visible: "Tus keys se quedaron sin saldo: estás usando la IA de la plataforma"
  · tope de gasto mensual elegido por el cliente ("cuenta controlada" del celular)
  · cada 10-15 min se prueban (ping) las propias para volver a ellas cuando respondan
```

### 8. Topes y frenos (para no perder plata ni sufrir abusos)

1. **Límites actuales por PEDIDOS:** pertenecen exclusivamente a cada **conexión de IA de
   plataforma**, nunca al Servicio. Cada conexión puede definir:
   - límite total de pedidos en ventana móvil de 24 h;
   - límite de pedidos por usuario en ventana móvil de 24 h.
   Ambos campos deben mostrar explícitamente la unidad **pedidos**.
2. **Tokens/costo (T-049):** cuando exista medición real de tokens, definir allí la política
   comercial/operativa correspondiente sin volver a introducir un límite de pedidos dentro de
   Servicio.
3. **Generar una clase ya consume IA:** crear clases y no terminarlas igualmente consume pedidos
   y, cuando T-049 exista, tokens/costo.
4. **Máximo de clases abiertas a la vez** (ej. 3, configurable): para crear otra, terminá o
   descartá una.
5. El control de consumo se evalúa al intentar usar una conexión. La visualización para el alumno
   deberá diseñarse con T-049/T-053 y no inferirse desde un límite del Servicio.

### 9. Consumo de tokens (T-049)

Se registra en **todas** las fuentes: cuándo, proveedor, modelo, operación y tokens. El cliente ve
su propio detalle; en híbrido es la base de la factura. La tabla de precios por modelo la mantiene
sr.macros en su portal (más adelante).

### 10. Dos vínculos a la vez (personal pagado + corporativo nuevo)

Ej.: pagó su individual hasta el 15/10 y el 01/10 su empresa lo invita.

- **Mantiene separados** su estudio personal y el corporativo → siguen los dos, cada uno con sus
  clases y su progreso.
- **Unifica** su estudio → manda el corporativo y los días pagados que le quedaban se convierten
  en un **código de crédito** (cupón): queda guardado y visible en su cuenta; puede usarlo más
  adelante o regalarlo a un amigo (es una invitación por esos días).

### 11. Etapas (de a una, cada una con su OK)

```text
1. Servicios: catálogo + panel de sr.macros; vínculo y fuente efectivos;
   platform_ai_allowed() pasa a mirar el servicio vigente; vencimiento en solo lectura
2. Campañas: panel + bienvenida (3 días, plataforma, tope provisorio por pedidos)
3. Beneficios reutilizables + invitaciones por link (motor genérico; UI inicial PLATFORM_OWNER)
4. Tokens y costo por uso (T-049) → topes por tokens, frenos de clases abiertas, detalle al cliente
5. Corporativo: empresas, keys de la empresa (T-005), invitaciones de empresa, unificar/separar
6. Pagos (otro otorgamiento; débito automático a definir)
```

**Etapa 1 — Resuelta (PR #26 a `develop`):**

```text
migración 0012     plans: vínculo, tope diario, descripción
corrección 0017     duración retirada de plans; vigencia centralizada en benefits
                   subscriptions: vence, origen (manual/campaña/invitación/pago), otorgado por, nota
                   siembra: Individual · propias keys / · Plataforma / · Híbrido
servicio vigente   effective_service(cuenta): suscripción activa; si no hay o venció →
                   "Individual · propias keys" (+ aviso "venció" durante 14 días)
router de IA       BYOK → propias · PLATAFORMA → plataforma · HÍBRIDO → propias y luego
                   plataforma · dueño → ambas (reemplaza platform_ai_allowed de T-003)
límites actuales  solo en ai_connections: total 24 h + por usuario 24 h, medidos en pedidos
portal sr.macros   Servicios (sin límites) + Beneficios (servicio + duración)
                   + Cuentas y servicios (buscar, otorgar beneficio, quitar)
usuario            "Tu servicio" en IA e Inicio: nombre, vence, % de uso de hoy, aviso de vencido
```

Al vencer, por ahora vuelve a "Individual · propias keys": si tiene keys propias sigue; si
no, no puede generar clases nuevas pero ve todo lo hecho (solo lectura de hecho).

**Etapa 2 — Resuelta (PR #34 a `develop`):**

```text
campañas        trigger + condiciones + prioridad + acumulabilidad + vigencia + límites
historial       CampaignGrant idempotente por campaña/cuenta
bienvenida      ejemplo en borrador: 3 días de Plataforma
ciclo           borrador / activa / pausada / terminada + borrado seguro
seguridad       una falla del motor nunca impide login, /me o /me/level
```

**Etapa 3 — Resuelta (PR #37 a `develop`, 2026-10-03):**

```text
benefits        única fuente de verdad para servicio + duración + política de conflicto
servicios       sin duración ni límites de consumo; vínculo + fuente + metadatos
conexiones       única fuente de verdad para límites actuales: total 24 h + por usuario 24 h
manual          Cuentas y servicios otorga benefit_id, no service_id + días
campañas        pasan a referenciar benefit_id (sin duplicar plan_id + grant_days)
invitaciones    NAMED u OPEN, token, cupo, vigencia opcional, cancelación/regeneración
canjes          InvitationRedemption por cuenta; Subscription origin=INVITATION
login           canje de invitación antes de campañas; errores de invitación no bloquean login
portal OWNER    Beneficios + Invitaciones
email           NAMED queda PENDING hasta implementar T-051
```

### 12. Ajustes de Configuración resueltos en revisión manual (Roberto, 2026-10-02)

Aplicados en `feat/t-004-invitations`:

- **Fuentes de IA visibles y fijas:** Configuración tiene un bloque propio e informativo con
  BYOK / PLATFORM / HYBRID. No se agregan ni eliminan desde el portal; son columnas fijas del
  modelo de negocio.
- **Servicios y membresías separados:** Servicios muestra solo las filas del modelo (hoy
  Personal; Corporativa futuro), sin editar/activar. Un bloque separado de Membresías administra
  qué intersecciones Servicio × Fuente están habilitadas.
- **Cuentas en dos vistas con responsabilidades distintas:** Resumen muestra únicamente información
  de cuentas y membresías efectivas, sin acciones. Configuración conserva la administración de
  cuentas (otorgar/cambiar/quitar beneficio y acciones DEV).
- **Beneficio separado por ejes:** al crear/editar un Beneficio se seleccionan por separado
  Servicio, Fuente de IA y duración; ya no se elige una membresía prearmada en un único campo.
- **Campañas e Invitaciones muestran solo el nombre del Beneficio:** la composición
  Servicio/Fuente/Duración se consulta en Beneficios y no se repite en esos selectores/listados.
- **Filtro de Campañas:** la etiqueta visible `Tiene servicio otorgado` pasa a
  `Tiene membresía otorgada`; el identificador técnico interno puede conservarse por compatibilidad.
- **Cuentas:** se renombra "Cuentas y servicios" a "Cuentas".
- **Beneficio efectivo:** la fila de cada cuenta muestra el nombre del Benefit vigente; el Servicio
  queda como dato secundario.
- **Trazabilidad:** `subscriptions.benefit_id` identifica el último Benefit que dejó vigente la
  suscripción. La migración 0019 recupera referencias históricas desde canjes, campañas y notas
  manuales cuando es posible.
- **Selector manual:** muestra solo el nombre del beneficio y preselecciona el `benefit_id` real
  de la cuenta.
- **Refresco cruzado:** guardar o dar de baja un Beneficio refresca Cuentas sin necesitar F5.
- **Cambio manual directo:** el OWNER puede reemplazar un beneficio por otro en una sola
  confirmación. La suscripción anterior queda CANCELLED como historial; Campañas e Invitaciones
  conservan su política segura de no reemplazar silenciosamente un servicio distinto.
- **Baja lógica de Benefit:** la acción Eliminar marca `deleted_at` + inactivo; las referencias
  históricas siguen existiendo. La baja queda bloqueada mientras exista al menos una cuenta con el
  beneficio vigente, una campaña ACTIVE/PAUSED que lo referencie o una invitación todavía
  canjeable. Beneficiarios históricos, campañas terminadas e invitaciones canceladas/expiradas/
  agotadas no bloquean. En UI el botón Eliminar permanece visible pero deshabilitado/grisado.
- **Usos fuera de Configuración:** campañas/invitaciones que usan cada Benefit se muestran en
  Resumen, no en la tabla de edición.
- **Resumen de beneficios por cuenta:** muestra cuenta, beneficio vigente, servicio resultante,
  origen y vencimiento.
- **Nombre semántico:** el seed `WELCOME_PLATFORM_3D` se llama "Bienvenida"; servicio y duración
  siguen siendo campos de su configuración y no parte obligatoria del nombre.
- **Patrones UI compartidos:** el sistema de tabs usado por Plataforma se extrajo a
  `shared/ui/TabNavComponent`, igual que Collapse y Activo/Inactivo, para reutilizarlo sin copiar
  estilos.
- **Cabecera de Plataforma:** se elimina el subtítulo interno redundante de Configuración. Debajo de
  "Plataforma" queda una única descripción dinámica: Resumen explica estadísticas/estado y
  Configuración explica los elementos administrables.

### 13. Pendiente de definir más adelante

- **Paginación real en Cuentas:** el backend ya limita resultados, pero la UI necesita navegación
  por páginas (o estrategia equivalente) para evitar listas/scroll interminables cuando haya cientos
  de cuentas. Bootstrap puede resolver la apariencia del paginador, pero la paginación funcional no
  debe depender de Bootstrap.
- **Suspender/bloquear cuentas:** diseñar una acción administrativa distinta de eliminar. Debe
  permitir suspender temporalmente una cuenta por abuso, exceso de consumo u otro motivo, conservar
  historial/auditoría y definir con precisión qué acciones quedan bloqueadas durante la suspensión.
- Nombres comerciales definitivos de los servicios.
- Tope inicial de la bienvenida (tokens/día) y máximo de clases abiertas.
- Unión de cuentas personal/corporativa de una misma persona (¿por DNI?).
- Débito automático y medios de pago.
- **Estrategia de una fuente futura:** no asumir que `HYBRID` siempre será únicamente
  "propias primero y plataforma si fallan". La futura sección de Fuentes de IA debe permitir
  evolucionar hacia políticas configurables de reparto/ruteo (por ejemplo 50/50, prioridad,
  fallback u otras estrategias) sin tener que redefinir el catálogo de Servicios. **No implementar
  ahora; queda documentado para una etapa posterior.**
- **Unidades de los límites:** toda pantalla que muestre/configure límites de conexiones debe
  indicar explícitamente la unidad usada. **Implementado para límites actuales:** cantidad de
  **pedidos** en ventana móvil de 24 h, tanto total como por usuario. Futuro: tokens/costo cuando
  corresponda (T-049).

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
**Relación:** T-004 Etapa 3/5 (beneficios e invitaciones), T-005 (IA de organización), T-011 (aislamiento),
T-051 (email)

Todavía falta implementar el portal corporativo completo:

- personas;
- ADMIN / STUDENT;
- invitaciones;
- carga CSV/XLS;
- branding;
- seguimiento de progreso;
- detalle por empleado;
- aislamiento de actividad personal;
- suscripción corporativa.

### Invitaciones corporativas: reutilizar el motor único de T-004

**No crear un segundo motor.** El ADMIN usa el mismo `Benefit + Invitation + InvitationRedemption`
con `organization_id` y permisos de tenant. PLATFORM_OWNER administra el 100 % de capacidades del
motor y define cuáles quedan habilitadas para empresas.

Ejemplo de política futura configurable:

```text
Capacidad                         PLATFORM_OWNER     ADMIN organización
NAMED                             sí                 configurable
OPEN cupo 1                       sí                 configurable
OPEN cupo N                       sí                 configurable
Carga masiva NAMED                configurable       configurable
Beneficio PERSONAL                sí                 no
Beneficio CORPORATE               no                 sí, dentro de su organización
```

No asumir todavía esos valores concretos: la decisión es que el **motor soporte las capacidades** y
el permiso determine qué actor puede usarlas.

### Alta/carga masiva de empleados

Antes de importar, el ADMIN debe elegir el beneficio/configuración que aplicará al lote. El archivo
describe solamente personas:

```text
email | nombre | apellido | [datos personales opcionales futuros]
```

No aceptar en el archivo `role`, `service`, `benefit`, `plan`, fuente de IA ni permisos. Todas las
filas importadas crean pre-invitaciones **NAMED** independientes y entran como **STUDENT por
defecto**. Los ADMIN adicionales se crean/gestionan explícitamente, fuera del archivo masivo.

Cada invitación nominada, tanto manual como masiva, debe dejar email `PENDING` para que T-051 envíe
el link automáticamente.

### Dominio corporativo y recuperación de invitación

Permitir que una organización declare uno o más dominios de correo admitidos (ej. `cacatua.com`,
`cacatua.com.ar`). Esto puede utilizarse como condición de seguridad para las modalidades que
PLATFORM_OWNER habilite, en especial si alguna empresa puede generar links OPEN.

Si el empleado pierde/no recibe el link, una autenticación con email verificado que coincide con una
pre-invitación NAMED puede **descubrir** esa invitación. No asociar automáticamente la actividad
personal a la empresa: mostrar confirmación explícita ("Tenés una invitación pendiente de X.
¿Querés incorporarte?") y recién después crear/activar membresía corporativa.

No bloquea el MVP personal.

---

## T-011 — Tests específicos de aislamiento B2B

**Prioridad:** P1 cuando comience B2B  
**Estado:** Pendiente  
**Relación:** T-010 (portal ADMIN), T-004 Etapa 5 (beneficios/invitaciones corporativas)

Agregar pruebas obligatorias:

```text
ADMIN empresa A
  ✓ ve actividad A
  ✗ ve empleados B
  ✗ ve actividad B
  ✗ ve actividad personal de sus empleados
```

Al habilitar invitaciones corporativas agregar además:

- un ADMIN de A no puede listar/editar/cancelar beneficios ni invitaciones de B;
- una invitación de A no puede referenciar un beneficio de B;
- una invitación NAMED solo puede canjearla la identidad autorizada;
- una restricción de dominio de A nunca acepta dominios configurados solamente por B;
- el CSV/XLS no puede inyectar `ADMIN`, servicio, beneficio, plan ni permisos internos;
- las filas masivas crean STUDENT por defecto y quedan siempre dentro del tenant que importó;
- encontrar una pre-invitación por email verificado **no** debe vincular silenciosamente el contexto
  personal con la empresa: requiere aceptación explícita;
- un link OPEN, si PLATFORM_OWNER lo habilita para una empresa, respeta cupo y política de dominio;
- regenerar/anular un link de A no afecta invitaciones de B;
- todos los canjes conservan trazabilidad de cuenta, invitación, beneficio y organización.

El modelo ya guarda `organization_id` y `membership_id`; falta validar el flujo completo cuando exista
el portal ADMIN.

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
T-047 Avisos claros cuando no hay IA y reintento al entrar a la clase (Claude)
T-049 Registro de tokens y costo por cada uso de IA (Claude)
T-050 Fidelización: retención de datos, avisos y promociones (futuro)
T-051 Sistema de envío de emails
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
5. **Al pasar a PostgreSQL, revisar concurrencia de campañas** (T-004 etapa 2, revisión de
   Claude 2026-10-02): si dos pedidos simultáneos (login + `/me`) aplican la misma campaña a la
   misma cuenta, la restricción única `uq_campaign_grant_account` hace fallar el segundo con
   `IntegrityError` (error 500) en vez de ignorarlo. En SQLite no pasa porque serializa las
   escrituras. Resolver con savepoint + capturar la violación de unicidad como "ya otorgada".

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

## T-042 — Permitir al PLATFORM_OWNER copiar API keys administradas

**Prioridad:** P3 — Baja  
**Estado:** Resuelta (PR #22 a `develop`)  
**Responsable:** ChatGPT

Objetivo: permitir que únicamente el dueño de la plataforma (`PLATFORM_OWNER`) pueda copiar
al portapapeles una API key ya guardada cuando necesite reutilizarla o administrarla.

Alcance y restricciones:

1. **Solo PLATFORM_OWNER:** ningún usuario común, ADMIN de organización ni otra cuenta puede
   recuperar una credencial ya persistida.
2. **Solo conexiones que el owner puede administrar:** conexiones PLATFORM y, si corresponde,
   conexiones ACCOUNT pertenecientes a su propia cuenta. Nunca permitir leer las BYOK de otros usuarios.
3. **Solo copiar, nunca mostrar:** la key permanece siempre enmascarada en pantalla. Un icono
   sutil de copiar (dos hojas superpuestas) solicita el secreto al backend únicamente al pulsarlo
   y lo envía directamente al portapapeles.
4. **No exponerla en listados:** el endpoint normal de conexiones sigue devolviendo únicamente
   `credentialHint`; la credencial completa tiene un endpoint específico protegido por rol.
5. **Auditoría:** registrar quién copió una credencial, qué conexión y cuándo, sin guardar
   el valor de la key en logs ni en la auditoría.
6. **Frontend:** no persistir el secreto en estado, DOM, localStorage ni sessionStorage; usarlo
   solo durante la operación de copia.

**Criterio de seguridad:** esta capacidad es una excepción deliberada a la regla general de que
las API keys cifradas no regresan al navegador. La excepción queda limitada al owner, a una
acción explícita de copia y a credenciales bajo su propia administración.

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
**Estado:** Resuelta (PR #21 a `develop`) · Claude  
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

Resolución:

1. Silencio para cortar: 1,8 s → **1,0 s** (`AUTO_STOP_SILENCE_MS`). Prueba con audio simulado
   (1,5 s de voz + silencio): corta y guarda en ~2,9 s desde "Grabar" (antes ~3,7 s).
2. Sin "Confirmar respuesta": al cortar (solo o con "Detener") la grabación se guarda sola en el
   dispositivo y cuenta como respondida. Si el guardado falla, aparece "Reintentar".
3. "Volver a grabar" sobre una respuesta ya guardada registra la señal `speakRetakes`
   (`POST …/signals` con `kind: "retake"`); el resumen de esfuerzo muestra "grabaste tu respuesta
   N veces". Más de 1 regrabación marca Speaking como asistido, sin bajar la nota.

---

## T-047 — Avisos claros cuando no hay IA y reintento al entrar a la clase

**Prioridad:** P2 — Media  
**Estado:** Pendiente  
**Responsable:** Claude  
**Relación:** T-003 (cada usuario usa solo su IA propia)

Detectado al probar T-003 (2026-10-01) con un usuario con 2 APIs propias, una caída y otra sin saldo.
Lo que ya funciona bien: las respuestas se guardan, lo que no necesita IA se corrige igual, el resto
queda "Esperando corrección" y cada API queda en espera (caída 5 min, sin saldo 60 min).

Problemas:

1. **Mensaje sin motivo:** al pedir una clase nueva dice solo "No hay conexiones de IA disponibles."
   (las APIs en espera ni siquiera se listan). Debe decir por qué y cuándo:
   `Gemini mía: proveedor caído (se reintenta en 5 min) · OpenAI mía: sin saldo (cargá crédito o agregá otra API)`.
2. **Promesa incumplida:** el cartel de una clase "Esperando corrección" dice "se reintenta
   automáticamente cuando vuelvas a entrar", pero eso solo ocurre entrando por el Inicio; entrando
   directo a la clase queda pendiente aunque la IA ya funcione. Al abrir la clase, si hay IA
   disponible, debe corregir sola.

---

---

## T-048 — Conversation A1 + ortografía transversal y evaluación integrada

**Prioridad:** P1 — Alta  
**Estado:** Resuelta (PR #25 a `develop`) · ChatGPT  
**Responsable:** ChatGPT  
**Relación:** T-019 (modalidades), T-020 (lección), T-021/T-043 (mecánica de escritura), T-024 (examen), T-034 (evidencias por habilidad)

Objetivo: incorporar **Conversation** como contenido curricular real de A1, con microconversaciones
controladas y escalables a niveles futuros, manteniendo Listening/Speaking/Pronunciation como
habilidades transversales; además incorporar el seguimiento explícito de **Ortografía** dentro de
Writing y hacerlo visible en progreso y examen.

Diseño acordado:

1. **Conversation es curricular, no una habilidad transversal.**
   - A1 debe definir temas/skills conversacionales (saludos, presentaciones, información personal,
     intercambios cotidianos breves, etc.).
   - La práctica inicial será una microconversación corta y controlada, con aproximadamente dos
     intervenciones reales del alumno y cierre.
   - El formato debe poder crecer en A2+ sin rediseñar el contrato completo.
2. **Modalidades independientes del contenido conversacional.**
   - El turno recibido puede ser READ o LISTEN.
   - La respuesta puede ser SELECT, WRITE o SPEAK cuando el ejercicio lo permita.
   - Listening, Speaking y Pronunciation siguen alimentándose transversalmente según la modalidad
     y las señales de esfuerzo existentes.
3. **Evaluación semántica por IA.**
   - No exigir una única frase exacta: evaluar si la intervención responde a la intención,
     mantiene el contexto, es comprensible y es apropiada para A1.
   - Evaluar además errores lingüísticos observables (Grammar, Vocabulary y Writing) sin confundir
     pertinencia conversacional con corrección formal.
   - Una respuesta puede ser conversacionalmente válida y dejar evidencias secundarias negativas
     en otras skills.
4. **Evidencias curriculares secundarias.**
   - Extender el mecanismo actual para que un intento pueda dejar evidencia en skills curriculares
     secundarias cuando la IA detecta un error concreto, además de la skill principal.
   - No inventar evidencia cuando la modalidad no permite observarla (por ejemplo, capitalización
     en una respuesta hablada).
5. **Ortografía dentro de Writing.**
   - Agregar skills específicas para convenciones de escritura A1: capitalización, spelling básico,
     apóstrofes/contracciones y puntuación básica según corresponda al nivel.
   - Errores como `i am Robert` deben afectar la skill de capitalización, no Grammar.
   - El dashboard debe mostrar un indicador explícito **Ortografía** agregado desde esas skills,
     aunque internamente pertenezcan a Writing.
6. **Dashboard y adaptación de clases.**
   - Conversation debe aparecer como área curricular con su avance.
   - Ortografía debe ser visible como indicador propio.
   - Las evidencias secundarias y la ayuda/esfuerzo deben participar del balanceo futuro de clases
     de forma coherente con el mecanismo existente.
7. **Examen de nivel.**
   - Incluir Conversation y Ortografía en la cobertura/evaluación del nivel.
   - Mantener los requisitos actuales para habilitar el examen: al menos 70 % de cobertura del
     nivel y 70 % de promedio sobre lo practicado.
   - El examen debe representar también Conversation/Ortografía de forma coherente con el dashboard
     y seguir siendo independiente del progreso de las clases.
8. **Frontend.**
   - Presentar la microconversación como una interacción legible tipo chat/turnos, sin convertirla
     todavía en un chat abierto ilimitado.
   - Mantener autoguardado, señales de Listening/Speaking/Pronunciation y corrección final.
9. **Tests.**
   - Cubrir currícula A1, generación/validación del nuevo ejercicio, evaluación conversacional,
     evidencias curriculares secundarias, ortografía, dashboard, balanceo y examen.
   - Mantener compatibilidad con las clases existentes y ejecutar la suite configurada del proyecto.

**Criterio:** una conversación debe medir interacción contextual y poder producir evidencias
lingüísticas adicionales sin confundirlas con la habilidad principal; Ortografía debe quedar
curricularmente dentro de Writing pero visible y evaluable como dimensión propia.

---

## T-049 — Registro de tokens y costo por cada uso de IA

**Prioridad:** P2 — Media (imprescindible antes de vender el servicio híbrido de T-004)  
**Estado:** Pendiente  
**Responsable:** Claude  
**Relación:** T-004 (membresías y facturación), T-006 (consumo en el portal del dueño), T-041
(proveedor y modelo usados en cada clase)

Hoy cada uso de IA se registra (`ai_usage_events`: cuándo, conexión, cuenta, operación, éxito,
modelo), pero **sin tokens** y solo lo ve sr.macros.

1. **Averiguar y guardar tokens** por respuesta: OpenAI (`usage.prompt_tokens` /
   `completion_tokens`), Gemini (`usageMetadata`), Anthropic (`usage.input_tokens` /
   `output_tokens`). Verificar también en transcripción de audio.
2. Registrar en **todas** las fuentes: BYOK, plataforma e híbrido.
3. **Costo estimado:** tokens × precio del modelo (tabla de precios mantenida por sr.macros en
   su portal).
4. **Detalle para el cliente**, como una factura:
   `01/10 22:12 · Gemini (gemini-2.5-flash) · corregir ejercicio · 1.240 tokens · USD 0,0004`
5. Nunca guardar prompts ni respuestas: solo metadatos y conteos.

**Unidades visibles (pedido de Roberto, 2026-10-02):** en el portal de plataforma los números
salen sin unidad ("24 h: 7 ok") y se confunden con tokens. Mostrar siempre la unidad y, cuando
exista el registro de tokens, ambas: `7 pedidos · 12.340 tokens` (por conexión, por cuenta, en el
gráfico diario y en el ranking de cuentas). Lo mismo en "Uso de hoy" del alumno y en T-053
(dashboard de consumo por cliente).

---

## T-050 — Fidelización: retención de datos, avisos y promociones

**Prioridad:** P4 — Muy baja (mucho más adelante)  
**Estado:** Para analizar  
**Relación:** T-004 (vencimiento de membresías), T-051 (emails)

Ideas anotadas para no perderlas (Roberto, 2026-10-01):

1. **Retención:** los datos de una membresía vencida se guardan 1 año. Al cumplirse **se borra
   todo** (decisión de Roberto: no se anonimiza).
2. **Aviso antes de perder los datos:** email un mes antes ("tus datos pueden perderse").
3. **Campañas de fidelización:** ej. "dejaste de pagar hace 3 meses → 20 % de descuento".

---

## T-051 — Sistema de envío de emails

**Prioridad:** P3 — Baja  
**Estado:** Pendiente  
**Relación:** T-004 (invitaciones/campañas), T-050 (avisos y promociones),
T-059 (campañas programadas y reportes periódicos por empresa)

La app no envía emails. Hace falta un servicio para: invitaciones, avisos de vencimiento,
recuperación de cuenta, campañas de fidelización y **entrega automática de reportes generados por
campañas programadas** (caso guía: resumen mensual de progreso de empleados para los ADMIN de una
empresa, definido en T-059). Remitente: la cuenta real de sr.macros. Elegir proveedor (SMTP propio o
servicio transaccional) y plantillas.

### Contrato con invitaciones (T-004)

Toda invitación **NAMED/nominada** debe enviarse automáticamente por email, tanto si fue creada a mano
como si provino de una importación masiva corporativa. El correo transporta el **mismo link/token**
del motor de invitaciones; email no crea otra clase de invitación.

La Etapa 3 deja esas invitaciones con `email_status=PENDING`. T-051 debe consumir esa cola y registrar,
como mínimo:

```text
PENDING  → todavía no enviada
SENT     → proveedor aceptó el envío
FAILED   → error; debe quedar trazable y permitir reintento
```

Evaluar además reintentos, bounce/rechazo y fecha del último intento. El token se conserva cifrado
además de su hash precisamente para poder reenviar el mismo link de forma segura.

Un link OPEN se comparte/copia por el canal que el emisor quiera; solo se envía por email si existe
un destinatario explícito o una acción futura que así lo defina.

El email **no es requisito único para acreditar una invitación nominada corporativa**: T-010 podrá
recuperarla mediante identidad/email verificado si el mensaje se pierde, siempre con confirmación
explícita antes de incorporar a la empresa.

---

## T-052 — Continuar a la siguiente clase desde el resultado

**Prioridad:** P2 — Media  
**Estado:** Pendiente  
**Relación:** T-020 (lección por tema), T-034 (balanceo adaptativo)

Al terminar y corregir una clase, la pantalla de resultado ofrece hoy **“Rehacer esta clase”** y
**“Volver al inicio”**, pero no permite continuar directamente con el aprendizaje.

Objetivo: agregar una acción **“Continuar a la siguiente clase”** en la pantalla de clase completada,
sin obligar al alumno a volver al Inicio.

Criterios:

1. Mostrar el botón únicamente cuando la clase esté efectivamente corregida/completada.
2. Al pulsarlo, reutilizar el flujo normal que determina o genera la próxima clase para el alumno,
   respetando nivel, refuerzos y adaptación existentes; no asumir que la siguiente clase es
   simplemente `id + 1`.
3. Si la próxima clase ya existe, abrirla; si el flujo actual debe generarla, generarla y luego abrirla,
   evitando duplicados o dobles solicitudes.
4. Mantener disponibles **“Rehacer esta clase”** y **“Volver al inicio”**.
5. Cubrir el flujo con tests de frontend y, si la resolución de la próxima clase requiere cambios de
   API, agregar también los tests de backend correspondientes.

**Criterio de aceptación:** desde el resultado de una clase completada, el alumno puede pasar a su
próxima clase con una sola acción, usando exactamente las mismas reglas de selección/adaptación que
el flujo normal de Inicio.

---


## T-053 — Dashboard de consumo de IA por cliente según modalidad de API

**Prioridad:** P2 — Media  
**Estado:** Pendiente  
**Relación:** T-004 (membresías / modalidades BYOK, plataforma e híbrida), T-006 (portal del cliente),
T-041 (proveedor y modelo usados), T-049 (tokens y costo por uso de IA)

El PLATFORM_OWNER ya dispone de un panel con métricas de uso de IA, gráfico diario y ranking de
cuentas que consumen IA de plataforma. Cada cliente debe disponer de una vista equivalente, pero
**limitada a sus propios datos** y adaptada a la modalidad de API que tenga configurada.

Objetivo: incorporar en el portal de cada cliente un dashboard de consumo de IA que permita entender
cuánto está usando, de dónde sale ese consumo y cómo evoluciona en el tiempo.

Criterios:

1. **Aislamiento por cliente / tenant.**
   - Nunca mostrar consumo global de la plataforma ni datos de otros clientes.
   - En organizaciones con varios usuarios, las métricas y rankings internos deben limitarse a las
     cuentas pertenecientes a ese mismo cliente.
2. **Información distinta según modalidad de IA.**
   - **BYOK / APIs propias:** mostrar requests y tokens consumidos por las conexiones propias del
     cliente, discriminando cuando sea útil por proveedor/modelo.
   - **IA de plataforma:** mostrar requests y tokens consumidos contra las conexiones de la
     plataforma y la información económica o de cuota que corresponda al plan.
   - **Híbrido:** separar claramente consumo propio y consumo de plataforma, tanto en los totales
     como en la evolución diaria.
3. **Gráfico temporal.**
   - Incluir una vista por día similar al panel del PLATFORM_OWNER.
   - El gráfico debe reflejar las métricas relevantes para la modalidad del cliente y permitir
     distinguir origen del consumo cuando sea híbrido.
4. **Detalle de tokens.**
   - Adjuntar una tabla o desglose diario con tokens consumidos.
   - Cuando T-049 esté disponible, reutilizar sus datos de input/output tokens, proveedor, modelo,
     operación y costo estimado, sin guardar ni mostrar prompts o respuestas.
5. **Resumen de consumo.**
   - Mostrar totales recientes (por ejemplo requests, errores, tokens y consumo de plataforma)
     usando etiquetas comprensibles para el cliente.
   - No mostrar tarjetas sin sentido para una modalidad concreta; adaptar u ocultar métricas que no
     apliquen.
6. **Ranking / segundo bloque del panel.**
   - Para clientes con múltiples cuentas, reutilizar el concepto de “cuentas que más usan IA”, pero
     únicamente dentro de su organización.
   - En cuentas personales o cuando no aporte información, ocultar ese bloque o reemplazarlo por un
     desglose más útil de proveedor/modelo.
7. **Permisos y tests.**
   - Validar backend y frontend para impedir acceso cruzado entre clientes.
   - Cubrir BYOK, plataforma e híbrido, incluyendo clientes personales y organizaciones con varios
     usuarios.

**Criterio de aceptación:** cada cliente puede entrar a su portal y entender su consumo de IA por día
y en tokens, con una presentación coherente con su modalidad BYOK/plataforma/híbrida y sin acceso a
datos de terceros.

---

## T-054 — Servicio Híbrido sin API keys propias: ¿funciona o no?

**Prioridad:** P2 — Media (definir antes de otorgar Híbrido a usuarios reales)  
**Estado:** Pendiente de decisión (detectado por Roberto probando T-004 etapa 1, 2026-10-02)  
**Relación:** T-004 (membresías: servicio = vínculo + fuente de IA; Híbrido = propias primero,
plataforma si fallan), T-049 (tokens y costo por uso), T-047 (avisos claros cuando no hay IA)

Situación: una cuenta tiene el servicio **Individual · Híbrido** pero **no cargó ninguna API key
propia**. Hoy (etapa 1) el router simplemente salta a la IA de la plataforma: el alumno usa
Librería Inglés (con el tope del servicio), igual que con el servicio Plataforma.

```text
Híbrido + keys propias OK        → usa las propias            (esperado)
Híbrido + keys propias fallan    → usa la plataforma          (esperado, con aviso y tope)
Híbrido + SIN keys propias       → ¿?                          ← a decidir
```

Opciones a discutir:

1. Funciona igual, todo por plataforma (como hoy). Riesgo: Híbrido = Plataforma encubierto.
2. No genera clases hasta que cargue una key: Inicio muestra "Conectá una IA" como obligatorio.
3. Funciona por plataforma con un tope más bajo / período de gracia (N días) para cargar su key.

Además: el paso 2 de "Primeros pasos" en Inicio debe reflejar la decisión (hoy, para Híbrido,
se muestra como opcional).

---

## T-055 — Pantalla "IA" según el servicio: no ofrecer configurar keys que no se usan

**Prioridad:** P2 — Media (antes de otorgar servicios Plataforma a usuarios reales)  
**Estado:** Resuelta (PR #30 a `develop`) · Claude (detectado por Roberto probando T-004 etapa 1, 2026-10-02)  
**Relación:** T-004 (membresías: servicio = vínculo + fuente de IA, bandera `ownKeys`
required / optional / unused), T-054 (Híbrido sin keys propias), T-005 (keys de la empresa)

Problema: un alumno con servicio **Plataforma** (ej. 1 día otorgado por sr.macros) entra al
menú **IA** y ve "Tus conexiones" + "Agregar conexión". Si carga una key, **no se usa** (el
servicio Plataforma ignora las propias): confunde. Además el cartel "En uso ahora" muestra el
nombre y el motor de la conexión de la plataforma (ej. `Google Gemini · gemini-3.5-flash-lite`),
información interna de sr.macros / la empresa que el alumno no necesita ver.

Qué debe mostrar el menú IA según el servicio (decidirlo por la bandera `ownKeys`, no por el
nombre del servicio, para que un tipo nuevo no obligue a tocar pantallas):

```text
Propias keys (required)  → como hoy: "Tu servicio" + Tus conexiones + Agregar conexión
Plataforma   (unused)    → solo "Tu servicio": "Usás la IA de Librería Inglés"
                           (o "de tu empresa" cuando sea corporativo). Sin alta de keys.
                           Sin nombre/motor de la conexión de plataforma.
Híbrido      (optional)  → "Tu servicio" + Tus conexiones + Agregar conexión
                           (se usan primero las propias; ver T-054 si no carga ninguna)
```

Criterios:
- Con Plataforma no se ve el alta de conexiones; si el alumno ya tenía keys propias cargadas,
  las sigue viendo y administrando (editar/pausar/eliminar), con aviso de que quedan sin uso
  mientras dure el servicio (no se borran: al vencer vuelve a usarlas).
- "En uso ahora" solo nombra conexiones **propias**; si la que se usa es de plataforma o de
  empresa, dice genéricamente "IA de Librería Inglés" / "IA de tu empresa".
- La API tampoco expone nombre/modelo de conexiones de plataforma a cuentas que no son el dueño.

Hecho:

```text
Backend   public_trace(): toda traza de IA de plataforma sale como "IA de Librería Inglés"
          (sin connectionId ni motor) para quien no es el dueño:
          /ai/active · clase (generada por, generationAi) · corrección de cada ejercicio
          · transcripción y pronunciación · mensajes de error ("Gemini interna: sin cuota")
          Las trazas nuevas guardan ownerType; las viejas se resuelven por connectionId.
          /me → ai.own cuenta las propias guardadas aunque el servicio no las use.
Pantalla  IA con Plataforma: título "IA" + "Tu servicio", sin "Agregar conexión".
          Si nunca cargó keys: no ve conexiones. Si ya tenía (pedido de Roberto): ve
          "Tus conexiones guardadas" y puede editarlas, pausarlas o eliminarlas; aviso de que
          no se usan mientras dure el servicio y vuelven a usarse al vencer.
          Híbrido y Propias keys: como antes. "· motor X" solo si hay motor.
```

---


## T-056 — Tiempo límite configurable para exámenes según duración estimada

**Prioridad:** P2 — Media  
**Estado:** Pendiente  
**Relación:** T-024 (examen de aprobación de nivel), T-030 (currícula A2 → B2)

Objetivo: cuando se prepare/g genere un examen de nivel, además de sus ejercicios y criterios de
evaluación debe obtenerse una **duración estimada de resolución** y, a partir de ella, definir un
**tiempo límite real del examen** con una holgura razonable.

La solución debe servir para A1 y quedar preparada para reutilizarse en los niveles futuros, ya que
la duración dependerá de la cantidad, tipo y dificultad de ejercicios de cada examen.

Criterios:

1. **Estimación al preparar el examen.**
   - El proceso que construye/genera el examen debe devolver también una estimación de tiempo de
     resolución para un alumno del nivel correspondiente.
   - La estimación debe considerar la estructura real del examen y no ser un valor fijo global.
2. **Holgura antes del límite.**
   - El límite no debe ser exactamente la estimación: debe agregarse un margen razonable para evitar
     penalizar a un alumno por pequeñas variaciones normales de ritmo.
   - La fórmula concreta de holgura debe quedar centralizada/configurable para poder ajustarla sin
     rehacer el flujo.
3. **Redondeo siempre hacia arriba.**
   - Después de aplicar la holgura, convertir el resultado a bloques redondos de tiempo.
   - Analizar si conviene trabajar con bloques de **10 o 20 minutos**; en ambos casos el redondeo debe
     ser siempre hacia arriba.
   - Ejemplo conceptual: si la estimación más holgura supera un bloque de 40 minutos usando bloques
     de 20, el límite resultante pasa al siguiente bloque (60 minutos).
4. **Temporizador visible.**
   - Al comenzar el examen, mostrar claramente el tiempo disponible y un contador regresivo.
   - El tiempo debe empezar a correr cuando el intento de examen quede efectivamente iniciado.
5. **Vencimiento.**
   - Al llegar a cero, el examen debe cerrarse/enviarse automáticamente con las respuestas que haya
     hasta ese momento, sin permitir seguir respondiendo fuera de tiempo.
   - El backend debe ser la autoridad del tiempo para evitar que recargar la página, cambiar el reloj
     local o manipular el frontend extienda el examen.
6. **Persistencia y reingreso.**
   - Guardar inicio y vencimiento del intento para que una recarga o reconexión continúe mostrando el
     tiempo restante real.
   - Definir el comportamiento ante una interrupción técnica genuina sin abrir una forma trivial de
     extender el tiempo.
7. **Configuración por nivel/examen.**
   - No asumir que A1, A2, B1, etc. tendrán la misma duración.
   - Conservar junto al intento el tiempo estimado y el límite finalmente asignado, para auditoría y
     futuros ajustes.
8. **Tests.**
   - Cubrir cálculo de holgura, redondeo al siguiente bloque, vencimiento automático, recarga,
     reconexión y validación autoritativa en backend.

**Criterio de aceptación:** todo examen de nivel tiene una duración estimada calculada al prepararse y
un tiempo límite redondeado hacia arriba con margen suficiente; el alumno ve el tiempo restante y el
intento finaliza automáticamente al vencer, sin poder extenderlo desde el cliente.

---
## T-057 — Habilitar el examen sin haber practicado un área (ej. Reading) · A ANALIZAR

**Prioridad:** P2 — Media  
**Estado:** ⚠️ **Para analizar y volver a discutir** (no implementar todavía) · detectado por Roberto
al aprobar A1 (2026-10-02)  
**Relación:** T-024 (examen de nivel y certificado: requisitos para habilitarlo), T-034
(evidencias por habilidad y balanceo adaptativo de las clases), T-056 (tiempo límite de exámenes)

Qué pasó: Roberto aprobó el examen A1 (89 %) con **Reading "Sin practicar"** en Progreso. Nunca
le tocó un ejercicio de Reading en las clases y aun así se le habilitó el examen.

Por qué pasa (código actual, `app/exams/service.py`):

```text
Requisitos para habilitar el examen (solo miran el TOTAL, no cada área)
  1. Practicar el 70 % de los temas del nivel   A1 = 50 temas → 35
  2. Promedio ≥ 70 % en lo practicado

Temas de A1 por área
  Grammar 21 · Vocabulary 10 · Writing 9 · Conversation 5 · Listening 4 · Reading 1
  → Reading es 1 tema de 50 (2 %): se llega a 35 sin tocarlo
```

- Las clases eligen temas por peso/debilidad: con 1 solo tema, Reading casi nunca aparece.
- Las respuestas del examen no cuentan como práctica (a propósito): Reading salió 100 % en el
  examen pero Progreso sigue en "Sin practicar".
- Para **aprobar**, el examen sí exige ≥ 60 % en cada área: el certificado es válido; el problema
  es que se llega al examen sin haber practicado esa área.

Propuesta de Claude (a discutir):

```text
Requisito nuevo   3. Practicar al menos 1 tema de CADA área del nivel
                     (visible en la lista de requisitos del examen, con qué áreas faltan)
Clases            si un área del nivel todavía no tiene práctica, la próxima clase la incluye
                  sí o sí (balanceo de T-034)
```

Preguntas abiertas:
- ¿Alcanza con 1 tema por área o pedir un % por área (ej. 50 % de los temas de cada una)?
- ¿Sumar más temas de Reading a A1 (hoy hay 1) en vez de, o además de, la regla?
- ¿El resultado del examen debería contar como evidencia en Progreso?

---


## T-058 — Integrar Ortografía al mismo nivel visual que las demás áreas de Progreso

**Prioridad:** P3 — Baja  
**Estado:** Para analizar  
**Relación:** T-034 (dashboard por habilidad), T-048 (Conversation A1 + ortografía transversal)

En la pantalla de **Progreso**, Ortografía aparece actualmente como un bloque destacado y separado
de Grammar, Vocabulary, Listening, etc. Esa presentación le da un tratamiento visual especial que no
corresponde con el criterio funcional acordado.

Objetivo: analizar y ajustar la presentación para que **Ortografía quede al mismo nivel visual que las
demás áreas/habilidades**, usando el mismo patrón de fila/tarjeta colapsable.

Criterios:

1. Ortografía debe verse como un elemento más del listado principal de progreso, no como un bloque
   destacado independiente.
2. Debe reutilizar el mismo patrón visual y de interacción que las demás áreas: título, porcentaje,
   estado, barra de progreso y posibilidad de expandir/colapsar el detalle cuando corresponda.
3. Mantener el concepto funcional definido en T-048: Ortografía sigue perteneciendo internamente a
   Writing, pero puede mostrarse como dimensión visible propia.
4. Revisar si conviene ubicarla junto a Writing o respetar el orden general actual de habilidades,
   evitando jerarquías visuales artificiales.
5. No modificar el cálculo de evidencias ni porcentajes por esta tarea salvo que el análisis detecte
   una inconsistencia funcional relacionada.
6. Validar que el cambio mantenga coherencia visual en desktop y resoluciones más angostas.

**Criterio de aceptación:** en Progreso, Ortografía se percibe visualmente como un elemento del mismo
nivel que Grammar, Vocabulary, Listening y el resto, sin un tratamiento especial separado.

---


## T-059 — Motor programable de ejecución de campañas y campañas ejemplo por empresa

**Prioridad:** P2 — Media  
**Estado:** Para analizar / diseñar  
**Relación:** T-004 (campañas), T-050 (fidelización), T-051 (emails),
T-053 (dashboard/consumo por cliente; posible fuente adicional de métricas)

Objetivo: separar del motor de campañas el concepto de **cuándo se evalúan campañas programadas**.
Las campañas no deben depender únicamente de eventos como login/registro: hace falta un segundo motor
de ejecución programada que permita evaluar campañas aunque el usuario no entre a la aplicación.

### A. Scheduler / batch de campañas

Inicialmente puede implementarse de forma simple o incluso con una ejecución diaria hardcodeada, pero
el diseño debe permitir evolucionar a una configuración dinámica.

El scheduler debe poder expresar, como mínimo:

1. **Frecuencia:** una vez por día, varias veces por día, semanal, ciertos días de la semana, etc.
2. **Horario:** una o más horas de ejecución.
3. **Vigencia:** fecha/hora desde y hasta cuándo corre esa programación.
4. **Ciclos:** permitir repeticiones periódicas sin crear lógica especial por campaña.
5. **Asociación con campañas:** una programación puede indicar qué campaña(s) debe evaluar en cada
   ejecución.
6. **Estado:** activa / pausada / finalizada.
7. **Idempotencia:** una ejecución repetida no debe volver a aplicar una campaña ya otorgada cuando
   la regla de campaña sea de una sola vez.
8. **Trazabilidad:** registrar cuándo corrió el batch, qué campaña evaluó, cuántos candidatos encontró,
   cuántos beneficios aplicó y qué errores tuvo.

Flujo conceptual:

```text
SCHEDULER
   ↓
llega fecha/hora de ejecución
   ↓
obtiene campañas asociadas y activas
   ↓
busca candidatos
   ↓
evalúa ELIGIBILITY
   ↓
verifica nunca_recibió(campaña) / límites
   ↓
ejecuta ACTION
   ↓
ejecuta NOTIFICATION si corresponde
   ↓
registra resultado
```

Ejemplo:

```text
Programación:
todos los días 08:00

Campaña:
"Volvé con 50 %"

Condición:
último pago entre 90 y 120 días
AND sin servicio activo
AND nunca_recibió(campaña)

Acción:
crear promoción

Notificación:
EMAIL
```

Importante: **scheduler y campaña son conceptos distintos**. La campaña define audiencia, condiciones,
acciones, notificación y límites. El scheduler solamente define cuándo debe evaluarse.

### B. Campañas iniciales / ejemplos para nuevas empresas

Al crear una organización, precargar campañas de ejemplo en estado **BORRADOR / INACTIVAS** para que
el ADMIN tenga configuraciones reales como referencia y pueda entender el sistema sin empezar desde
cero.

Ejemplos iniciales posibles:

- bienvenida a nuevo empleado;
- beneficio por primera actividad;
- recordatorio por inactividad;
- campaña programada de fidelización;
- invitación/regalo mediante link.

Las campañas precargadas:

1. nunca deben activarse automáticamente solo por crear la empresa;
2. deben quedar limitadas por backend al `organization_id` de esa empresa;
3. pueden editarse, duplicarse o eliminarse;
4. deben servir como ejemplos funcionales del constructor de campañas;
5. no deben contener condiciones o acciones que el ADMIN de empresa no tenga permiso de utilizar.

**Criterio de aceptación:** el sistema puede ejecutar campañas tanto por eventos como por una
programación independiente y configurable, y una empresa nueva recibe campañas de ejemplo inactivas
que muestran al ADMIN cómo configurarlas dentro de su propio tenant.


### C. Caso de uso guía: reporte mensual de progreso por empresa

Usar como caso de diseño principal una campaña modelo precargada para organizaciones:

```text
CAMPAÑA
"Resumen mensual de progreso"

SCOPE
organization_id = Empresa X

TRIGGER
SCHEDULED

SCHEDULE
1 vez por mes
ej. día 1 a las 08:00

TARGET / DATOS
empleados activos de Empresa X

ACTION
GENERATE_REPORT

CONTENIDO POSIBLE
- empleados totales
- cuántos avanzaron
- cuántos están estancados
- cuántos no tuvieron actividad
- clases realizadas
- progreso / niveles
- opcionalmente consumo de IA (T-053)

DELIVERY
EMAIL a ADMIN(s) de Empresa X
```

Esta campaña debe crearse al dar de alta una empresa como **BORRADOR / INACTIVA** y funcionar como
ejemplo editable: el ADMIN puede activarla, pausarla, cambiar periodicidad/destinatarios, duplicarla
o eliminarla. La copia pertenece al tenant de la empresa; modificarla nunca afecta a otras empresas.

Este caso debe guiar la evolución del motor porque obliga a resolver en conjunto tres capacidades:

1. **Campañas ejemplo por tenant:** una organización nueva recibe configuraciones reales de referencia.
2. **Scheduler/batch configurable (T-059):** frecuencia, días, horarios, ciclos y vigencia no deben
   quedar hardcodeados dentro de la campaña.
3. **Entrega por email (T-051):** el resultado generado debe poder enviarse automáticamente a
   destinatarios definidos, por ejemplo los ADMIN de la organización.

Además fuerza una generalización importante de T-004: una campaña no debe quedar limitada a
`GRANT_SERVICE`. La Etapa 3 de T-004 separa ya el **Benefit** (servicio + duración) de la Campaña.
Por lo tanto, cuando se generalicen acciones, la acción de servicio debe referenciar un Benefit en
vez de volver a guardar servicio/días dentro de la campaña:

```text
ACTION = GRANT_SERVICE    → benefit_id
ACTION = GENERATE_REPORT  → configuración de reporte
ACTION = CREATE_INVITATION → configuración/plantilla de invitación
```

Una invitación **no es una campaña**: pueden relacionarse mediante una acción futura
`CREATE_INVITATION`, pero `Invitation` mantiene su propio ciclo, token, cupo y canjes. Del mismo
modo, `Benefit` no debe convertirse en un contenedor genérico de reportes, emails o descuentos:
representa específicamente una definición reutilizable de otorgamiento de servicio.

El concepto de acción debe poder crecer, por ejemplo:

```text
GRANT_SERVICE
GENERATE_REPORT
SEND_NOTIFICATION
CREATE_INVITATION
APPLY_DISCOUNT
...
```

y la entrega/comunicación debe mantenerse separada de la acción:

```text
NONE
IN_APP
EMAIL
IN_APP + EMAIL
```

Flujo conceptual:

```text
TRIGGER / SCHEDULE
        ↓
SCOPE / TARGET
        ↓
CONDITIONS
        ↓
ACTION
        ↓
DELIVERY
```

**Decisión de diseño:** no hardcodear "reporte mensual" como una función especial. Debe surgir de la
combinación `schedule + scope + target/conditions + action + delivery`. Este caso se usará como
prueba de que T-004, T-059 y T-051 quedan suficientemente genéricos y combinables.

**Criterio de aceptación adicional:** al crear una empresa existe al menos una campaña modelo de
reporte periódico, inactiva y limitada a su tenant, que pueda configurarse para generar un resumen de
sus empleados y enviarlo por email a sus administradores.

---

## T-060 — Plataforma sin IA disponible: detectar el "fuera de servicio" y compensar al cliente

**Prioridad:** P2 — Media (antes de cobrar o de otorgar Plataforma a muchos usuarios)  
**Estado:** Para analizar / diseñar (pedido de Roberto, 2026-10-02)  
**Relación:** T-004 (servicios y campañas: la compensación se otorga como una campaña),
T-059 (scheduler de campañas), T-047 (avisos claros cuando no hay IA), T-049 (tokens y costo),
T-051 (emails), T-053 (dashboard de consumo por cliente)

Situación: un alumno con servicio **Plataforma** (o Híbrido cuando fallan sus keys) depende de las
conexiones de sr.macros. Si **todas** las conexiones de plataforma quedan sin cuota, caídas o con
key inválida, el alumno no puede generar clases y sus respuestas abiertas quedan "Esperando
corrección", mientras **su servicio sigue corriendo** (los días se consumen igual).

Comportamiento actual (ya probado en tests):

```text
Generar clase      → GENERATION_FAILED "No hay conexiones de IA disponibles"
Corregir           → lo automático se corrige; lo abierto queda "Esperando corrección"
                     y se reintenta al volver a entrar (si hay IA)
Mensajes           → no nombran la conexión de plataforma (T-055)
Registro           → cada fallo queda en ai_usage_events con su error_code
```

Qué falta:

1. **Detectar el incidente**: registrar un "fuera de servicio de plataforma" cuando no queda ninguna
   conexión de plataforma utilizable (inicio, fin, duración, causa: QUOTA / DOWN / AUTH…), y qué
   cuentas con servicio Plataforma/Híbrido quedaron afectadas (intentaron usar IA y no pudieron).
2. **Avisar**:
   - a sr.macros (portal, y email con T-051) apenas empieza, para que reponga cuota o cambie de key;
   - al alumno, con un mensaje claro ("La IA de Librería Inglés no está disponible en este
     momento; tu trabajo queda guardado") en vez del error genérico (T-047).
3. **Compensar al cliente** (devolución), **automáticamente**, como una **campaña de
   compensación** (T-004 etapa 2 + scheduler de T-059).

Definiciones de Roberto (2026-10-02):

```text
¿A quién se compensa?   POR PEDIDO: solo a quien hizo un pedido a la IA de plataforma
                        (generar clase, examen, corregir, transcribir…) y falló porque no
                        había ninguna conexión de plataforma disponible.
¿Quién decide?          AUTOMÁTICO. sr.macros no gestiona compensaciones a mano.
```

⚠️ **A analizar — ¿desde cuándo y hasta cuándo cuenta el fuera de servicio?**

```text
Desde   el primer pedido que falla (el fallo del pedido abre el incidente)
Hasta   ⚠️ NO puede ser "el próximo pedido OK" del alumno: si se queda sin IA y no vuelve
        en una semana, el sistema contaría toda esa semana como fuera de servicio.
Idea    un proceso batch (scheduler, ver T-059) que pruebe periódicamente las conexiones
        de plataforma (health check) y, apenas una vuelve a responder, CIERRA el incidente
        y corta la compensación. La duración real = apertura → reactivación detectada.
```

A definir: cada cuánto prueba el batch, si los health checks consumen cuota del proveedor,
y si el incidente es global (toda la plataforma) o por fuente/servicio.

⚠️ **A analizar — ¿qué se devuelve?**

Si se copia el modelo de consumo por pedidos (T-004 tope diario; T-049 tokens/costo), la
compensación podría ser:

- tiempo de vigencia extra (horas/días),
- pedidos/tope extra,
- **cupón** (código canjeable, como la conversión de días a crédito de T-004 §10),
- **dinero en cuenta** (cuando existan pagos, T-004 etapa 6).

Queda abierto cuál (o cuáles) y cómo se calcula el monto en cada caso.

---


---

## T-061 — Estado visual claro para conexiones de IA activas y pausadas

**Prioridad:** P2 — Media  
**Estado:** Pendiente  

Objetivo: mejorar la lectura visual del estado de las conexiones de IA para que una conexión
**activa/disponible** y una conexión **pausada/inactiva** se distingan inmediatamente por color y
tratamiento visual, sin depender únicamente del texto del estado.

Alcance:

1. Aplicar el criterio visual en todos los lugares donde se administren o activen conexiones de IA,
   tanto para conexiones individuales del usuario como para conexiones de la plataforma.
2. Mantener visibles los estados actuales y sus acciones (`Pausar`, `Activar`, etc.), pero sumar
   un código visual consistente que permita identificar rápidamente si la conexión está activa o
   pausada.
3. Reutilizar los estilos/chips existentes cuando sea posible y mantener coherencia con el resto de
   estados visuales de la aplicación.
4. Definir colores con contraste suficiente y sin depender exclusivamente del color para transmitir
   el estado.
5. Verificar el resultado en las pantallas de conexiones individuales y en el portal del
   PLATFORM_OWNER.

**Criterio:** al recorrer cualquier listado de conexiones de IA debe poder distinguirse de forma
inmediata cuáles están activas y cuáles están pausadas, conservando además el texto explícito del
estado.


---

## T-062 — Enriquecer el selector de modelos IA con atributos útiles

**Prioridad:** P2 — Media  
**Estado:** Pendiente  
**Relación:** T-022 (selector de modelos IA), T-061 (claridad visual de conexiones)

Objetivo: hacer que la lista de modelos de cada proveedor ayude realmente a elegir un motor y no
muestre solamente nombre + identificador técnico cuando ambos aportan prácticamente la misma
información.

Alcance:

1. Revisar qué metadatos entrega actualmente la API de cada proveedor al listar modelos
   (OpenAI, Gemini, Anthropic y los que se incorporen después).
2. Si la API oficial expone atributos útiles, mostrarlos de forma breve junto al modelo. Ejemplos:
   - velocidad / latencia relativa;
   - costo o categoría de costo;
   - capacidad de audio;
   - capacidades relevantes como multimodalidad, razonamiento u otras categorías oficiales.
3. No inventar clasificaciones ni mantener manualmente etiquetas que puedan quedar obsoletas si el
   proveedor no las entrega o no existe una fuente confiable.
4. Si un proveedor devuelve únicamente `id` / nombre sin metadata útil, presentar una opción limpia:
   evitar mostrar de forma redundante un nombre amigable y un identificador prácticamente iguales.
   El ID técnico puede quedar como dato secundario cuando realmente ayude a distinguir versiones.
5. Mantener una estructura extensible para que cada proveedor pueda exponer distintos atributos sin
   obligar a que todos tengan exactamente la misma metadata.
6. Aplicar el resultado tanto al alta como a la edición de conexiones individuales y de plataforma,
   reutilizando el mismo selector/componente cuando corresponda.
7. Revisar especialmente la identificación de modelos compatibles con audio: si esa capacidad puede
   conocerse por modelo mediante información oficial, reflejarla en el selector; si solo se conoce a
   nivel proveedor, no atribuirla falsamente a cada modelo.

**Estado actual a revisar:** el backend normaliza hoy la respuesta de modelos a `id` + `label`,
por lo que cualquier metadata adicional del proveedor se descarta antes de llegar al frontend.

**Criterio:** el selector debe aportar información útil para elegir modelo cuando esa información
exista de forma confiable; cuando no exista, debe mantenerse simple y sin duplicar texto ni fabricar
atributos.


---

## T-065 — Evolución del motor de campañas para fidelización y automatizaciones futuras

**Prioridad:** P3 — Baja / futura  
**Estado:** Para analizar / diseñar  
**Relación:** T-004 (motor actual de campañas, beneficios e invitaciones), T-050 (fidelización),
T-051 (emails), T-053 (métricas/consumo por cliente), T-059 (scheduler y campañas programadas)

Objetivo: evolucionar el motor actual de campañas, sin reemplazarlo ni crear un segundo motor
paralelo, para que pueda reutilizarse más adelante en fidelización, recuperación de usuarios,
promociones, automatizaciones y casos corporativos. Esta tarea **no debe modificar el alcance actual
de T-004**: T-004 debe cerrarse con el modelo y capacidades ya acordados. T-065 toma esa base como
punto de partida futuro.

### 1. Principio rector: un solo motor

No crear un “motor de fidelización” separado. Bienvenida, recuperación, fidelización, promociones,
reportes y automatizaciones futuras deben expresarse como combinaciones de las mismas piezas:

~~~text
CAMPAÑA
   SCOPE       → sobre quién opera
   TRIGGER     → qué la dispara
   CONDITIONS  → quién califica
   ACTION      → qué hace
   DELIVERY    → cómo se comunica
   LIMITS      → cuántos / cuántas veces
   TRACKING    → qué ocurrió
~~~

El objetivo es evitar funciones especiales del tipo win_back_campaign, welcome_campaign,
monthly_report_campaign, etc. Cada caso debe surgir de configuración + capacidades del motor.

### 2. Catálogo central de capacidades

Crear una única fuente de verdad en backend para las capacidades disponibles del motor:

- campos de condición soportados;
- operadores válidos por campo;
- triggers disponibles;
- acciones disponibles;
- deliveries disponibles;
- tipos y validaciones de valores;
- capacidades permitidas por scope/rol.

El formulario manual, las plantillas y el asistente IA deben consumir o derivarse de ese mismo
catálogo. No repetir manualmente la misma capacidad en backend, prompt IA, frontend y plantillas.

Ejemplo: si se agrega DAYS_SINCE_LAST_ACTIVITY, debe definirse una sola vez como capacidad del
motor y desde ahí quedar disponible para validación, constructor y asistencia IA.

### 3. Segmentación orientada a fidelización

Extender las condiciones cuando existan las fuentes de datos necesarias. Casos a contemplar:

- días desde última actividad;
- días desde vencimiento del último servicio/membresía;
- tiene / no tiene servicio activo;
- fecha del último otorgamiento;
- clases realizadas en una ventana de tiempo;
- inactividad durante N días;
- progreso detenido durante N días;
- nivel actual;
- consumo o comportamiento de IA cuando T-053 lo permita;
- antigüedad de pago / fecha de último pago **solo cuando exista un dominio real de facturación**.

No aproximar conceptos comerciales con otros datos. Ejemplo: “90 días desde que dejó de pagar” no
puede reemplazarse por “90 días desde que creó la cuenta”.

### 4. Acción explícita y desacoplada

Hoy la campaña está centrada en otorgar un Benefit. A futuro debe modelarse una acción explícita,
manteniendo Benefit exclusivamente como definición reutilizable de otorgamiento de servicio.

Acciones posibles:

~~~text
GRANT_BENEFIT
SEND_NOTIFICATION
GENERATE_REPORT
CREATE_INVITATION
APPLY_DISCOUNT        ← solo cuando exista facturación/promociones reales
...
~~~

No convertir Benefit en un contenedor genérico para descuentos, reportes, emails u otras acciones.

### 5. Scheduler independiente — T-059

Las campañas de fidelización no pueden depender del login del usuario. Reutilizar T-059 para que un
scheduler independiente determine cuándo evaluar campañas programadas.

Ejemplo:

~~~text
todos los días 09:00
   ↓
buscar campañas SCHEDULED activas
   ↓
obtener candidatos
   ↓
evaluar CONDITIONS con el mismo motor
   ↓
ejecutar ACTION
   ↓
ejecutar DELIVERY
   ↓
registrar resultado
~~~

Scheduler y campaña deben seguir siendo conceptos separados. El scheduler decide **cuándo**; la
campaña decide **sobre quién, bajo qué condiciones y qué acción ejecutar**.

### 6. Delivery separado — T-051

La entrega/comunicación debe seguir desacoplada de la acción:

~~~text
NONE
IN_APP
EMAIL
IN_APP_EMAIL
~~~

T-051 debe encargarse del envío real de email. El motor de campañas solo debe generar el trabajo /
estado pendiente correspondiente y registrar el resultado de entrega.

### 7. Preview de audiencia antes de activar

Agregar una capacidad de simulación/previsualización:

- cantidad aproximada o exacta de cuentas que calificarían;
- muestra opcional de cuentas elegibles;
- explicación de por qué una cuenta entra o queda afuera;
- advertencias cuando una campaña resulte demasiado amplia;
- sin ejecutar la acción ni crear grants.

El objetivo es que SrMacros pueda validar una campaña antes de activarla y detectar errores de
segmentación sin afectar usuarios reales.

### 8. Tracking e historial de ejecuciones

Registrar cada ejecución programada o masiva con trazabilidad suficiente:

- fecha/hora;
- campaña;
- cantidad de candidatos;
- elegibles;
- aplicados;
- omitidos;
- errores;
- duración de ejecución;
- resultado de delivery cuando corresponda.

Esta información debe permitir posteriormente medir efectividad sin reconstruirla de forma
indirecta desde otras tablas.

### 9. IA como asistente del mismo motor

Potenciar el asistente IA de T-004 para que use el catálogo central de capacidades.

Ejemplo futuro:

~~~text
"Usuarios que hace 60 días no estudian y no tienen membresía activa;
darles 7 días de plataforma y avisarles por email."
~~~

La IA debe transformar la intención en una propuesta estructurada usando únicamente capacidades
reales. Si falta una capacidad, debe advertirlo y dejar el campo sin resolver; nunca inventar una
regla equivalente.

Las plantillas y la IA pueden combinarse: una plantilla puede ser punto de partida y luego ajustarse
con IA, pero ambos caminos deben terminar en el mismo draft/formulario de campaña.

### 10. Fidelización como capa de producto, no como segundo motor — T-050

La futura sección “Fidelización” de SrMacros debe ser una vista especializada sobre Campaigns:

- segmentos frecuentes;
- campañas activas de retención;
- campañas de recuperación;
- resultados y métricas;
- plantillas orientadas a fidelización;
- acceso al mismo constructor manual / plantilla / IA.

Crear una campaña desde Fidelización debe generar una Campaign normal. No debe existir una segunda
tabla o lógica paralela de “fidelization campaigns”.

### 11. Retención y borrado de datos fuera del motor

T-050 incluye la política futura de conservar datos de una membresía vencida durante 1 año y luego
borrarlos. La **eliminación obligatoria** de datos no debe depender de una campaña.

Sí puede existir una campaña de aviso, por ejemplo:

~~~text
faltan 30 días para eliminación
   ↓
SEND_NOTIFICATION / EMAIL
~~~

Pero el proceso que efectivamente elimina datos al cumplirse la política debe ser independiente,
obligatorio e inmune a que una campaña se pause, edite o elimine.

### 12. Caso guía para validar la arquitectura

Antes de considerar esta evolución terminada, el motor debería poder representar sin lógica especial:

~~~text
Campaña: "Volvé a estudiar"

SCHEDULE:
todos los días 09:00

CONDITIONS:
cuenta PERSONAL
AND sin membresía activa
AND última actividad >= 60 días
AND nunca recibió esta campaña

ACTION:
GRANT_BENEFIT → "Plataforma 7 días"

DELIVERY:
IN_APP + EMAIL

LIMIT:
una vez por persona
~~~

Si este caso puede configurarse combinando capacidades genéricas, sin agregar código específico para
“recuperación” o “fidelización”, el diseño está correctamente generalizado.

**Criterio final:** ampliar el vocabulario del motor, no multiplicar motores. T-004 permanece como la
base actual; T-065 se aborda más adelante, coordinada con T-050, T-051 y T-059 cuando esas etapas
entren en desarrollo.

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

## T-063 — Quitar el borrado físico de cuentas (DEV) antes de publicar

**Prioridad:** P2 — Media (hacerlo cuando el proyecto esté avanzado, antes de publicar)  
**Estado:** Pendiente (pedido de Roberto, 2026-10-02)  
**Relación:** T-004 etapa 2 (campañas: el botón se agregó para repetir pruebas de primer login),
T-038 (publicación), T-008 (configuración de producción), T-050 (retención y borrado de datos)

Situación: el portal de sr.macros tiene **"Eliminar cuenta (DEV)"** (`DELETE
/platform/accounts/{id}/dev-purge`), que borra físicamente una cuenta y todos sus datos. Se
habilita cuando `APP_ENV` es local/dev/test, y **el valor por defecto de `APP_ENV` es `local`**:
si en producción falta esa variable, el botón queda activo y permite borrar cuentas reales
(solo sr.macros lo ve, pero un descuido de configuración o una sesión robada alcanzan).

Decisión de Roberto: no parchearlo ahora, sino **resolverlo de forma definitiva** más adelante:

```text
Opción A  eliminar la acción (endpoint + botón) y usar una base de prueba descartable o un
          script de desarrollo fuera de la app
Opción B  mantenerla solo detrás de un permiso explícito (ej. DEV_ACCOUNT_PURGE_ENABLED=true),
          apagado por defecto, y nunca disponible en producción aunque falte APP_ENV
```

Criterio de aceptación: en una instalación de producción, con o sin `APP_ENV` configurado, no
existe forma de borrar físicamente una cuenta desde la app. El borrado real de datos queda a
cargo de la política de retención de T-050.

---

## T-064 — Ingreso sin cuenta de Google (Microsoft, email, etc.)

**Prioridad:** P2 — Media (antes de publicar o de sumar empresas)  
**Estado:** Pendiente · para más adelante (pedido de Roberto, 2026-10-03)  
**Relación:** T-004 etapa 3 (invitaciones por link: una invitación nominada exige entrar con
ese email), T-004 etapa 5 / T-005 (empresas: muchas usan Microsoft 365), T-051 (emails)

Situación: la app solo permite ingresar con Google. Una invitación nominada a un email solo se
puede aceptar entrando con una cuenta de Google de ese mismo email.

```text
✅ pueden entrar   gmail · correo de empresa en Google Workspace · hotmail/outlook/yahoo que
                   creó una cuenta de Google con ese email
❌ no pueden       hotmail/outlook/yahoo SIN cuenta de Google · empresas con Microsoft 365
```

Impacto: limita a quién se puede invitar (ej. un amigo con hotmail) y, sobre todo, la etapa
corporativa.

A analizar más adelante: qué métodos de ingreso agregar (cuenta Microsoft, código o link por
email, otros) y cómo se unifican con la cuenta existente si la misma persona entra por dos vías.

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
