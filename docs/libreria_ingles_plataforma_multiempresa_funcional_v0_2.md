# Librería Inglés — Documento funcional de plataforma multiempresa
## Identidad, organizaciones, membresías, roles, suscripciones y white-label

**Versión:** 0.2  
**Estado:** diseño funcional en elaboración  
**Alcance:** este documento cubre exclusivamente la arquitectura comercial/multiempresa de la plataforma. La lógica pedagógica, clases, niveles CEFR, IA, scoring, listening, speaking y progreso académico general pertenecen al documento funcional de aprendizaje.

---

# Índice rápido

1. [Objetivo](#1-objetivo)
2. [Principios del modelo](#2-principios-del-modelo)
3. [Conceptos principales](#3-conceptos-principales)
4. [Tipos de cuenta y autenticación](#4-tipos-de-cuenta-y-autenticación)
5. [Landing pública](#5-landing-pública)
6. [Portal corporativo por organización](#6-portal-corporativo-por-organización)
7. [Registro de una organización](#7-registro-de-una-organización)
8. [Primer OWNER](#8-primer-owner)
9. [Roles iniciales](#9-roles-iniciales)
10. [Panel de personas de una organización](#10-panel-de-personas-de-una-organización)
11. [Carga masiva inicial](#11-carga-masiva-inicial)
12. [Pre-registro e invitaciones](#12-pre-registro-e-invitaciones)
13. [Alta del empleado invitado](#13-alta-del-empleado-invitado)
14. [Cuenta personal y cuenta corporativa](#14-cuenta-personal-y-cuenta-corporativa)
15. [Separación entre autenticación y sesión de estudio](#15-separación-entre-autenticación-y-sesión-de-estudio)
16. [Compartir o continuar una sesión de estudio](#16-compartir-o-continuar-una-sesión-de-estudio)
17. [Validación para reutilizar una sesión existente](#17-validación-para-reutilizar-una-sesión-existente)
18. [DNI / documento como posible mecanismo de detección](#18-dni--documento-como-posible-mecanismo-de-detección)
19. [Escenarios de continuidad del aprendizaje](#19-escenarios-de-continuidad-del-aprendizaje)
20. [Suscripción personal y membresía corporativa](#20-suscripción-personal-y-membresía-corporativa)
21. [Fin de una membresía corporativa](#21-fin-de-una-membresía-corporativa)
22. [Datos y contexto del usuario](#22-datos-y-contexto-del-usuario)
23. [Múltiples organizaciones](#23-múltiples-organizaciones)
24. [Gestión de OWNER](#24-gestión-de-owner)
25. [Suscripción y pago corporativo](#25-suscripción-y-pago-corporativo)
26. [White-label y branding](#26-white-label-y-branding)
27. [Design tokens](#27-design-tokens)
28. [Por qué no permitir Bootstrap/CSS arbitrario](#28-por-qué-no-permitir-bootstrapcss-arbitrario)
29. [Funciones específicas por cliente](#29-funciones-específicas-por-cliente)
30. [Modelo conceptual de datos](#30-modelo-conceptual-de-datos)
31. [Estados principales](#31-estados-principales)
32. [Storytime completo](#32-storytime-completo)
33. [Decisiones tomadas](#33-decisiones-tomadas)
34. [Puntos todavía abiertos](#34-puntos-todavía-abiertos)
35. [Fuera del MVP](#35-fuera-del-mvp)

---

# 1. Objetivo

La aplicación debe poder comercializarse tanto a personas individuales como a organizaciones sin mantener productos separados.

Debe soportar:

```text
B2C
Usuario individual
→ crea su cuenta personal
→ paga su propio plan
→ estudia por su cuenta

B2B
Empresa / escuela / universidad / instituto
→ contrata el servicio
→ incorpora personas
→ administra membresías y roles
→ paga las licencias
```

La plataforma debe continuar siendo una sola solución técnica y funcional.

---

# 2. Principios del modelo

La arquitectura debe separar claramente:

```text
AUTENTICACIÓN
ORGANIZACIÓN
MEMBRESÍA
ROL
SUSCRIPCIÓN
SESIÓN / PERFIL DE ESTUDIO
```

No deben tratarse como si fueran la misma entidad.

La decisión más importante de este modelo es:

> Las autenticaciones no se fusionan. Lo que puede compartirse entre distintas cuentas es la sesión o perfil de estudio.

---

# 3. Conceptos principales

## 3.1 Cuenta

Representa una identidad de acceso.

Ejemplos:

```text
roberto@gmail.com
roberto@cacatua.com
```

Cada cuenta mantiene:

- su email;
- su mecanismo de autenticación;
- sus datos;
- su estado.

---

## 3.2 Organización

Representa a la entidad que contrata el servicio.

Ejemplos:

```text
Cacatúa S.A.
Universidad X
Instituto Y
```

---

## 3.3 Membresía

Representa la pertenencia de una cuenta a una organización.

Ejemplo:

```text
Cuenta:
roberto@cacatua.com

Organización:
Cacatúa

Membresía:
ACTIVE

Rol:
STUDENT
```

La empresa no entrega una “cuenta ya creada”.

Entrega una invitación a una futura membresía.

---

## 3.4 Rol

Define qué puede hacer una cuenta dentro de una organización.

Para el MVP se simplifica inicialmente a:

```text
OWNER
STUDENT
```

No se incluye `ADMIN` hasta que aparezca una necesidad funcional concreta que lo justifique.

---

## 3.5 Suscripción

Define quién paga por el acceso.

Puede pertenecer a:

```text
una cuenta personal
```

o:

```text
una organización
```

---

## 3.6 Sesión / perfil de estudio

Representa el recorrido de aprendizaje.

Contiene conceptualmente:

- nivel;
- habilidades;
- clases;
- intentos;
- progreso;
- métricas;
- historial;
- estado pedagógico.

No debe pertenecer rígidamente a una única autenticación.

Una o más cuentas autorizadas pueden acceder a la misma sesión de estudio.

---

# 4. Tipos de cuenta y autenticación

## 4.1 Cuenta personal

Para el flujo inicial:

```text
Cuenta personal
→ autenticación con Google
```

Ejemplo:

```text
roberto@gmail.com
```

---

## 4.2 Cuenta corporativa

Para usuarios provenientes de una organización:

```text
Cuenta corporativa
→ email corporativo
→ autenticación propia de la aplicación
```

Ejemplo:

```text
roberto@cacatua.com
```

En este flujo no se utiliza Google.

---

## 4.3 No fusionar autenticaciones

Si Roberto tiene:

```text
roberto@gmail.com
```

y:

```text
roberto@cacatua.com
```

continúan siendo dos cuentas y dos mecanismos de autenticación diferentes.

No se transforma una en la otra.

No se reemplaza un email por el otro.

No se crea una autenticación única combinada.

La continuidad del aprendizaje se resuelve a nivel de la sesión de estudio.

---

# 5. Landing pública

La landing general debe explicar el producto y permitir distinguir los principales caminos.

Conceptualmente:

```text
Librería Inglés

[ Iniciar sesión ]

Quiero aprender por mi cuenta
[ Crear cuenta personal ]

Represento a una empresa o institución
[ Registrar organización ]
```

La página podrá utilizar:

- imágenes;
- animaciones;
- videos;
- demostraciones;
- contenido promocional.

La tecnología visual concreta queda abierta.

---

# 6. Portal corporativo por organización

Cada organización debe poder tener su propia entrada visual.

Ejemplo:

```text
Librería Inglés
+
logo de Cacatúa
+
colores de Cacatúa
```

Una invitación corporativa debe llevar directamente a ese contexto.

El portal mostraría como mínimo:

```text
[ Iniciar sesión ]

[ Registrarme ]
```

Por lo tanto, un empleado invitado por Cacatúa no necesariamente aterriza en una pantalla genérica.

Aterriza en el portal corporativo de Cacatúa.

El portal conoce el tenant/organización correspondiente a partir de la invitación o del mecanismo de resolución de organización.

---

# 7. Registro de una organización

Flujo conceptual:

```text
Registrar organización
        ↓
datos de la empresa
        ↓
datos del responsable inicial
        ↓
validar email del responsable
        ↓
crear cuenta corporativa del responsable
        ↓
crear organización
        ↓
crear primera membresía OWNER
        ↓
contratar / activar plan
```

Datos de empresa posibles:

```text
razón social
CUIT
nombre comercial
web
teléfono
país
datos de facturación
```

La lista definitiva queda pendiente.

---

# 8. Primer OWNER

La persona que registra inicialmente la empresa se convierte en su primer `OWNER`.

Ejemplo:

```text
ORGANIZATION
Cacatúa

ACCOUNT
maria@cacatua.com

MEMBERSHIP
maria@cacatua.com
→ Cacatúa
→ OWNER
```

No existe un usuario compartido tipo:

```text
admin_cacatua
```

Cada persona administra con su propia cuenta.

---

# 9. Roles iniciales

Para evitar complejidad innecesaria, inicialmente:

```text
OWNER
STUDENT
```

## OWNER

Puede:

- ver las personas de la organización;
- ver invitados;
- ver miembros activos;
- cambiar roles;
- promover otro usuario a OWNER;
- revocar membresías;
- cargar personas;
- lanzar cargas masivas;
- gestionar branding;
- gestionar configuración;
- gestionar la suscripción corporativa.

## STUDENT

Utiliza el sistema de aprendizaje.

---

## 9.1 ADMIN

No se incorpora inicialmente.

Si más adelante aparece una necesidad concreta de delegar administración sin otorgar poderes completos de OWNER, se agregará.

---

# 10. Panel de personas de una organización

Cada organización tendrá un panel propio.

El OWNER debe poder ver el universo de personas asociado a la empresa.

Ejemplo:

```text
Personas

Invitados
Activos
Pendientes de registro
Membresía revocada
```

Cada fila puede mostrar, según corresponda:

```text
nombre
apellido
email corporativo
estado
rol
fecha de invitación
fecha de alta
```

El OWNER podrá seleccionar:

```text
una persona
```

o:

```text
N personas
```

y ejecutar acciones.

Ejemplos:

```text
Cambiar rol
Revocar membresía
Reenviar invitación
Eliminar invitación pendiente
```

---

# 11. Carga masiva inicial

La carga masiva está orientada inicialmente al rol base de usuario final.

No es necesario seleccionar rol antes de importar.

La importación masiva inicial crea candidatos para:

```text
STUDENT
```

El OWNER podrá modificar posteriormente los roles desde el panel.

Archivo ejemplo:

```csv
email,nombre,apellido
juan@cacatua.com,Juan,Perez
ana@cacatua.com,Ana,Gomez
pedro@cacatua.com,Pedro,Lopez
```

El rol no viaja en el CSV.

---

## 11.1 Validación previa

Antes de confirmar la carga, la plataforma puede informar:

```text
4.982 registros válidos
12 duplicados
6 inválidos
```

El OWNER confirma y comienza el proceso de invitación.

---

# 12. Pre-registro e invitaciones

Procesar el CSV NO crea inmediatamente usuarios definitivos.

Primero se genera una entidad intermedia.

Conceptualmente:

```text
INVITATION
```

o:

```text
PENDING_MEMBER
```

Ejemplo:

```text
organization = Cacatúa
email = juan@cacatua.com
name = Juan
surname = Perez
default_role = STUDENT
status = PENDING
```

Esto permite que una empresa cargue miles de personas que todavía nunca ingresaron a la plataforma sin llenar la tabla de cuentas con usuarios inexistentes o inactivos.

Después se envía la invitación.

---

# 13. Alta del empleado invitado

Juan recibe:

```text
Cacatúa te invita a utilizar Librería Inglés
```

El botón lo lleva al portal de Cacatúa.

Ahí encuentra:

```text
[ Iniciar sesión ]

[ Registrarme ]
```

---

## 13.1 Si intenta iniciar sesión sin haberse registrado

La plataforma informa:

```text
Todavía no existe una cuenta activa para este acceso.
Primero tenés que registrarte.
```

Y permite ir a:

```text
[ Registrarme ]
```

---

## 13.2 Registro corporativo

La invitación ya conoce:

```text
organización
email corporativo invitado
rol inicial
```

El usuario completa los datos necesarios.

Se valida el acceso al email corporativo.

Se crea:

```text
ACCOUNT
```

Luego la invitación pasa de:

```text
PENDING
```

a:

```text
ACCEPTED
```

y se crea:

```text
MEMBERSHIP
account → Cacatúa → STUDENT
```

---

# 14. Cuenta personal y cuenta corporativa

Ejemplo:

```text
Cuenta personal
ID 1
roberto@gmail.com

Cuenta corporativa
ID 2
roberto@cacatua.com
```

Ambas pueden pertenecer en la vida real a Roberto.

Sin embargo, desde autenticación continúan siendo independientes.

Esto permite que:

- el empleo cambie;
- desaparezca una membresía;
- cambie el email corporativo;
- continúe existiendo el acceso personal;
- una cuenta no dependa técnicamente de la otra.

---

# 15. Separación entre autenticación y sesión de estudio

La sesión de estudio debe independizarse de la cuenta.

Modelo conceptual:

```text
ACCOUNT
ID 1

STUDY_PROFILE
ID 100

ACCOUNT_STUDY_PROFILE
ACCOUNT 1 → STUDY 100
```

Si existe otra cuenta:

```text
ACCOUNT
ID 2
```

también puede autorizarse:

```text
ACCOUNT 2 → STUDY 100
```

Así:

```text
dos autenticaciones diferentes
→ un mismo recorrido de aprendizaje
```

---

## 15.1 No se fusionan cuentas

No hacemos:

```text
ACCOUNT 1 + ACCOUNT 2 → nueva cuenta
```

Hacemos:

```text
ACCOUNT 1 → STUDY 100
ACCOUNT 2 → STUDY 100
```

Esto simplifica mucho la continuidad del aprendizaje.

---

# 16. Compartir o continuar una sesión de estudio

Cuando una persona crea una cuenta nueva puede decidir:

```text
Empezar de cero
```

o:

```text
Ya poseo una cuenta / quiero continuar mi progreso
```

Ejemplo:

Roberto estudió originalmente con:

```text
ACCOUNT 1
roberto@cacatua.com
```

y tenía:

```text
STUDY 100
```

Más adelante crea:

```text
ACCOUNT 2
roberto@gmail.com
```

Puede elegir:

### Empezar de cero

```text
ACCOUNT 1 → STUDY 100
ACCOUNT 2 → STUDY 101
```

### Continuar progreso existente

```text
ACCOUNT 1 → STUDY 100
ACCOUNT 2 → STUDY 100
```

---

# 17. Validación para reutilizar una sesión existente

La asociación de una segunda cuenta a una sesión existente nunca debe hacerse sin demostrar control de la cuenta anterior.

Flujo acordado:

```text
Ya poseo una cuenta
        ↓
ingresar email de la otra cuenta
        ↓
enviar código de seguridad a ese email
        ↓
usuario ingresa código
        ↓
validar código
        ↓
permitir reutilizar la sesión de estudio
```

Ejemplo:

```text
Código enviado:
38142
```

Requisitos:

```text
un solo uso
caducidad corta
cantidad máxima de intentos
invalidación después de éxito
```

La cantidad exacta de dígitos puede definirse durante implementación.

La idea actual es un código corto enviado por email.

---

# 18. DNI / documento como posible mecanismo de detección

Hay dos mecanismos posibles que todavía deben decidirse definitivamente.

## Alternativa A — DNI como detección

Al registrarse una cuenta nueva:

```text
DNI = 12345678
```

el sistema busca si existe otra cuenta con ese documento.

Si encuentra coincidencia:

```text
Parece que ya tenés otro acceso a Librería Inglés.

¿Querés continuar el mismo progreso?
```

La coincidencia no autoriza nada por sí sola.

Igualmente deberá realizarse la verificación por email/código.

---

## Alternativa B — acción explícita “Ya poseo una cuenta”

No es necesario buscar automáticamente por DNI.

Durante el alta el usuario elige:

```text
Ya poseo una cuenta
```

Ingresa el email anterior.

Recibe el código.

Valida.

Selecciona la sesión existente.

---

## 18.1 Estado actual de esta decisión

Ambas alternativas son compatibles.

Puede usarse:

```text
DNI → ayuda a detectar
```

y:

```text
email + código → autoriza
```

Pero todavía debe decidirse si vale la pena almacenar y usar DNI desde el MVP o si inicialmente basta con la opción explícita `Ya poseo una cuenta`.

---

# 19. Escenarios de continuidad del aprendizaje

## 19.1 Personal primero, corporativo después

Roberto ya tiene:

```text
ACCOUNT 1
roberto@gmail.com

STUDY 100

SUBSCRIPTION PERSONAL
ACTIVE
```

Cacatúa lo invita a:

```text
roberto@cacatua.com
```

Roberto crea:

```text
ACCOUNT 2
```

y obtiene:

```text
MEMBERSHIP
ACCOUNT 2 → CACATÚA
```

Puede:

```text
empezar un nuevo STUDY
```

o:

```text
verificar ACCOUNT 1
y usar STUDY 100 desde ACCOUNT 2
```

---

## 19.2 Corporativo primero, personal después

Roberto entra por primera vez a través de Cacatúa.

```text
ACCOUNT 1
roberto@cacatua.com

STUDY 100
```

Tiempo después termina su membresía corporativa.

Le gustó el producto y crea:

```text
ACCOUNT 2
roberto@gmail.com
```

Durante el registro elige:

```text
Ya poseo una cuenta
```

Verifica:

```text
roberto@cacatua.com
```

mediante código.

Después elige:

### Empezar nuevamente

```text
ACCOUNT 2 → STUDY 101
```

### Continuar

```text
ACCOUNT 2 → STUDY 100
```

Aunque `ACCOUNT 1` ya no tenga una membresía activa, `STUDY 100` continúa existiendo porque no dependía de la membresía.

---

# 20. Suscripción personal y membresía corporativa

Una cuenta personal puede tener:

```text
SUBSCRIPTION PERSONAL = ACTIVE
```

y simultáneamente existir una cuenta corporativa de la misma persona con:

```text
MEMBERSHIP CACATÚA = ACTIVE
```

No se modifica automáticamente el pago personal.

La aplicación puede ofrecer:

```text
Cacatúa ahora cubre tu acceso.

[ Pausar plan personal ]
[ Mantener plan personal ]
```

---

## 20.1 Pausar

Si el usuario decide pausar:

```text
SUBSCRIPTION PERSONAL
ACTIVE → PAUSED
```

Esto no elimina:

- cuenta personal;
- sesión de estudio;
- progreso;
- historial.

---

# 21. Fin de una membresía corporativa

Si la empresa revoca:

```text
MEMBERSHIP
ACTIVE → REVOKED
```

la sesión de estudio no desaparece.

Si esa sesión también está autorizada para una cuenta personal:

```text
ACCOUNT PERSONAL → STUDY 100
```

el usuario continúa normalmente desde su cuenta personal.

---

## 21.1 Plan personal previamente pausado

No se reactiva automáticamente.

Se informa:

```text
Tu acceso corporativo finalizó.

Tu progreso sigue disponible.

[ Reactivar plan personal ]
```

La plataforma no debe comenzar a cobrar nuevamente sin una acción explícita.

---

# 22. Datos y contexto del usuario

El usuario deberá disponer de un área donde pueda consultar al menos:

```text
Mi sesión / recorrido de estudio
Mis datos
Mis membresías
Mis suscripciones / pagos
```

Desde membresías/suscripciones se podrán incorporar acciones como:

```text
pausar
cancelar
reactivar
pagar
consultar estado
```

La funcionalidad exacta se irá ampliando.

---

## 22.1 Visibilidad de la organización

El OWNER tendrá panel de personas y podrá administrar sus membresías y roles.

La definición exacta de qué métricas académicas de cada empleado puede consultar la organización se definirá más adelante.

No debe asumirse automáticamente que por pagar una licencia la organización recibe acceso ilimitado a toda la historia personal previa del usuario.

---

# 23. Múltiples organizaciones

El modelo debe permitir que una persona tenga distintas cuentas corporativas y/o distintas membresías.

Ejemplo:

```text
ACCOUNT 1
roberto@gmail.com

ACCOUNT 2
roberto@cacatua.com
→ Cacatúa

ACCOUNT 3
roberto@universidad.edu
→ Universidad X
```

Las tres podrían, si el usuario lo autoriza, acceder al mismo:

```text
STUDY 100
```

o cada una podría utilizar un recorrido diferente.

La decisión pertenece al usuario.

---

# 24. Gestión de OWNER

El primer registrante queda como OWNER.

Después puede promover otros miembros:

```text
STUDENT → OWNER
```

Debe poder existir más de un OWNER.

Ejemplo:

```text
María → OWNER
Roberto → OWNER
Juan → STUDENT
```

Si María deja la empresa, Roberto continúa administrando.

---

## 24.1 Único OWNER perdido

Si una organización pierde acceso a su único OWNER, será necesario un procedimiento de recuperación.

Para el MVP puede resolverse mediante soporte manual.

No es necesario construir todavía mecanismos avanzados.

---

# 25. Suscripción y pago corporativo

La suscripción pertenece a la organización.

Ejemplo:

```text
ORGANIZATION
Cacatúa

SUBSCRIPTION
Plan Empresa
ACTIVE
```

La organización podrá contratar una cantidad o modalidad de uso.

El esquema comercial exacto todavía no se decide:

```text
por usuario
por licencia
por paquete
por consumo
```

Los STUDENT no necesitan cargar una tarjeta para utilizar una licencia pagada por la organización.

---

# 26. White-label y branding

La solución debe ser multiempresa también visualmente.

Cacatúa podría tener:

```text
logo propio
color primario
color secundario
tipografía
imagen de login
```

Empresa B puede tener otra configuración.

La funcionalidad de fondo sigue siendo la misma.

---

## 26.1 Portal corporativo

El portal de Cacatúa puede verse conceptualmente:

```text
[ Logo Librería Inglés ] + [ Logo Cacatúa ]

Bienvenido al portal de aprendizaje de Cacatúa

[ Iniciar sesión ]
[ Registrarme ]
```

El grado exacto de presencia de nuestra marca y la marca de la empresa podrá ser configurable en el futuro.

---

# 27. Design tokens

La personalización visual debe hacerse mediante configuración controlada.

Ejemplo:

```json
{
  "brandName": "Cacatúa Learning",
  "logo": "...",
  "primaryColor": "#...",
  "secondaryColor": "#...",
  "fontFamily": "...",
  "borderRadius": "...",
  "loginBackground": "..."
}
```

Frontend:

```text
--brand-primary
--brand-secondary
--brand-font
--brand-radius
```

Cada organización carga su configuración sin modificar código.

---

# 28. Por qué no permitir Bootstrap/CSS arbitrario

La idea original fue permitir que una empresa cargara su propio Bootstrap o CSS.

No se recomienda porque podría:

- romper componentes;
- romper responsive;
- afectar accesibilidad;
- generar incompatibilidades;
- dificultar actualizaciones;
- aumentar muchísimo el soporte;
- introducir riesgos de seguridad.

Por eso:

```text
empresa configura tema
```

pero:

```text
empresa no ejecuta CSS/código arbitrario
```

---

# 29. Funciones específicas por cliente

La personalización visual no debe confundirse con personalización funcional.

Ejemplo:

```text
Cacatúa quiere azul
→ THEME
```

Ejemplo:

```text
Cacatúa quiere un módulo exclusivo
→ FEATURE
```

Las diferencias funcionales futuras pueden manejarse mediante:

```text
feature flags
```

para evitar forks diferentes del código por cliente.

---

# 30. Modelo conceptual de datos

El siguiente esquema es conceptual y podrá modificarse durante el diseño técnico.

## ACCOUNT

```text
id
email
account_type
auth_method
status
document_type
document_number
document_country
created_at
```

Ejemplos:

```text
account_type = PERSONAL
auth_method = GOOGLE
```

o:

```text
account_type = CORPORATE
auth_method = LOCAL
```

---

## ORGANIZATION

```text
id
legal_name
display_name
tax_id
country
website
phone
status
created_at
```

---

## MEMBERSHIP

```text
id
account_id
organization_id
role_id
status
created_at
revoked_at
```

---

## ROLE

```text
id
code
display_name
```

Inicialmente:

```text
OWNER
STUDENT
```

---

## INVITATION

```text
id
organization_id
email
name
surname
role_id
token
status
expires_at
created_at
accepted_at
```

---

## SUBSCRIPTION

```text
id
owner_type
owner_id
plan_id
status
created_at
```

`owner_type` puede ser:

```text
ACCOUNT
ORGANIZATION
```

---

## STUDY_PROFILE

```text
id
created_at
status
```

Representa el recorrido pedagógico.

---

## ACCOUNT_STUDY_PROFILE

```text
account_id
study_profile_id
linked_at
link_method
status
```

Permite:

```text
ACCOUNT 1 → STUDY 100
ACCOUNT 2 → STUDY 100
```

---

## STUDY ACTIVITY

Toda la estructura pedagógica detallada vive en el documento funcional de aprendizaje.

Cada actividad deberá poder vincularse al `STUDY_PROFILE`.

También puede conservar contexto de origen cuando sea necesario:

```text
organization_id
membership_id
account_id
```

para trazabilidad.

---

## ACCOUNT_LINK_VERIFICATION

Entidad posible para controlar el código de vinculación:

```text
id
requesting_account_id
target_email
verification_code_hash
expires_at
attempt_count
status
created_at
verified_at
```

No implica fusionar autenticaciones.

Solo demuestra que el usuario controla la otra cuenta y permite autorizar acceso a su sesión de estudio.

---

# 31. Estados principales

## Invitación

```text
PENDING
ACCEPTED
EXPIRED
CANCELLED
```

## Membresía

```text
ACTIVE
REVOKED
SUSPENDED
```

## Cuenta

```text
PENDING_VERIFICATION
ACTIVE
DISABLED
```

## Suscripción

```text
TRIAL
PENDING_PAYMENT
ACTIVE
PAUSED
PAST_DUE
CANCELLED
```

## Sesión / perfil de estudio

```text
ACTIVE
ARCHIVED
```

---

# 32. Storytime completo

## 32.1 Cacatúa contrata

María entra a la landing.

Selecciona:

```text
Registrar organización
```

Carga:

```text
Cacatúa S.A.
CUIT
sitio web
teléfono
...
```

Carga sus datos:

```text
María
maria@cacatua.com
```

Verifica su email.

Se crea:

```text
ACCOUNT 1
maria@cacatua.com
```

Se crea:

```text
ORGANIZATION 10
Cacatúa
```

Se crea:

```text
MEMBERSHIP
ACCOUNT 1
→ ORGANIZATION 10
→ OWNER
```

Cacatúa activa su suscripción.

---

## 32.2 Cacatúa carga empleados

María entra al panel:

```text
Personas
```

Carga:

```text
empleados.csv
```

con:

```csv
email,nombre,apellido
juan@cacatua.com,Juan,Perez
roberto@cacatua.com,Roberto,Gomez
ana@cacatua.com,Ana,Lopez
```

La carga masiva corresponde al rol base:

```text
STUDENT
```

No tiene que elegir un rol previamente.

El backend valida el archivo.

No crea todavía cuentas.

Crea:

```text
INVITATION 1
INVITATION 2
INVITATION 3
```

y envía emails.

---

## 32.3 Juan se registra

Juan abre su email.

Presiona:

```text
Aceptar invitación
```

Llega al portal:

```text
Librería Inglés + Cacatúa
```

Ve:

```text
[ Iniciar sesión ]
[ Registrarme ]
```

Nunca usó el sistema.

Presiona:

```text
Registrarme
```

Completa sus datos.

Activa su cuenta corporativa:

```text
juan@cacatua.com
```

La invitación pasa a `ACCEPTED`.

Se crea:

```text
Juan → Cacatúa → STUDENT
```

Juan inicia:

```text
STUDY 200
```

---

## 32.4 El OWNER modifica roles

María vuelve al panel.

Selecciona a Juan.

Puede cambiar:

```text
STUDENT → OWNER
```

También puede seleccionar varios registros para ejecutar acciones masivas.

No existe ADMIN en esta primera versión.

---

## 32.5 Roberto ya tenía una cuenta personal

Antes de que Cacatúa contratara la aplicación, Roberto estudiaba personalmente.

Tenía:

```text
ACCOUNT 20
roberto@gmail.com

STUDY 300

SUBSCRIPTION PERSONAL
ACTIVE
```

Cacatúa lo invita a:

```text
roberto@cacatua.com
```

Roberto se registra corporativamente.

Se crea:

```text
ACCOUNT 21
roberto@cacatua.com
```

y:

```text
MEMBERSHIP
ACCOUNT 21 → Cacatúa → STUDENT
```

En este punto:

```text
ACCOUNT 20
y
ACCOUNT 21
```

siguen siendo autenticaciones diferentes.

---

## 32.6 Roberto quiere conservar su progreso

Durante el registro o desde una opción posterior puede seleccionar:

```text
Ya poseo una cuenta
```

Ingresa:

```text
roberto@gmail.com
```

El sistema envía:

```text
Código 38142
```

a ese email.

Roberto carga correctamente el código.

Entonces puede elegir:

```text
Continuar mi sesión existente
```

Resultado:

```text
ACCOUNT 20 → STUDY 300
ACCOUNT 21 → STUDY 300
```

No se fusionaron las cuentas.

Se compartió el acceso al mismo recorrido de estudio.

---

## 32.7 Roberto prefiere separar trabajo y vida personal

También puede decidir no compartir nada.

Resultado:

```text
ACCOUNT 20 → STUDY 300
ACCOUNT 21 → STUDY 301
```

Ambas experiencias son completamente independientes.

---

## 32.8 Cacatúa paga el servicio de Roberto

Roberto todavía tiene:

```text
SUBSCRIPTION PERSONAL
ACTIVE
```

La plataforma puede ofrecer:

```text
Cacatúa ahora cubre tu acceso.

[ Pausar plan personal ]
[ Mantener plan personal ]
```

Roberto decide pausar.

```text
PERSONAL SUBSCRIPTION → PAUSED
```

Su Gmail y su STUDY 300 continúan existiendo.

---

## 32.9 Roberto deja Cacatúa

Cacatúa revoca:

```text
MEMBERSHIP ACCOUNT 21
```

La cuenta corporativa ya no obtiene acceso por esa membresía.

Pero:

```text
ACCOUNT 20 → STUDY 300
```

continúa existiendo.

Roberto entra con Google y mantiene todo su progreso.

Su plan personal continúa `PAUSED` hasta que él elija:

```text
Reactivar
```

No se le cobra automáticamente.

---

## 32.10 Caso inverso: comenzó en Cacatúa

Pedro nunca tuvo cuenta personal.

Empieza:

```text
ACCOUNT 30
pedro@cacatua.com

STUDY 400
```

Dos años después deja Cacatúa.

Crea una cuenta personal:

```text
ACCOUNT 31
pedro@gmail.com
```

Puede elegir:

```text
Empezar de cero
```

Resultado:

```text
ACCOUNT 31 → STUDY 401
```

o:

```text
Ya poseo una cuenta
```

Verifica por código:

```text
pedro@cacatua.com
```

y elige continuar:

```text
ACCOUNT 31 → STUDY 400
```

La finalización de la membresía laboral no destruyó su recorrido de aprendizaje.

---

# 33. Decisiones tomadas

## Arquitectura

- Una sola plataforma multiempresa.
- B2C y B2B conviven.
- Organización, cuenta, membresía, rol, suscripción y sesión de estudio son entidades diferentes.

## Autenticación

- Personal: Google.
- Corporativo: autenticación propia con email corporativo.
- No se fusionan autenticaciones.
- El email personal y el corporativo permanecen separados.

## Empresa

- El registrante inicial queda como OWNER.
- Puede haber varios OWNER.
- No se crea una cuenta compartida de empresa.

## Roles

MVP:

```text
OWNER
STUDENT
```

`ADMIN` queda fuera por ahora.

## Personas

- Existe un panel de personas por organización.
- El OWNER puede modificar roles.
- Puede seleccionar una o varias personas.

## Carga masiva

- CSV/Excel con datos de personas.
- La carga masiva inicial genera STUDENT.
- El rol no viaja en el archivo.
- Después puede modificarse desde el panel.

## Invitaciones

- Importar no crea cuentas.
- Se crean invitaciones/pre-registros.
- La cuenta se crea cuando la persona acepta y se registra.

## Portal corporativo

- Cada empresa puede disponer de un portal con su branding.
- El portal corporativo ofrece `Iniciar sesión` y `Registrarme`.

## Sesión de estudio

- La sesión de estudio es independiente de la autenticación.
- Varias cuentas pueden acceder al mismo STUDY_PROFILE.
- El usuario puede también mantener recorridos diferentes.

## Continuidad

- Existe opción `Ya poseo una cuenta`.
- Se ingresa el email anterior.
- Se envía un código de seguridad.
- El usuario debe validarlo.
- Después puede asociar la nueva cuenta al recorrido existente.

## DNI

- Puede utilizarse como ayuda para detectar una cuenta existente.
- No debe autorizar una unión por sí solo.
- La autorización real sigue siendo email + código.
- Todavía debe decidirse si entra en el MVP.

## Pagos

- Una membresía corporativa no modifica automáticamente un plan personal.
- El usuario puede pausar su plan personal.
- Al perder una membresía no se reactiva automáticamente el cobro.

## White-label

- Branding mediante configuración.
- No CSS/Bootstrap arbitrario.
- Design tokens.
- Funcionalidades específicas mediante feature flags.

---

# 34. Puntos todavía abiertos

No bloquean el diseño actual, pero deben resolverse más adelante:

1. Usar DNI desde el MVP o solamente `Ya poseo una cuenta`.
2. Datos definitivos pedidos al registrar una empresa.
3. Método exacto de autenticación corporativa:
   - password;
   - OTP;
   - magic link;
   - combinación.
4. Qué información académica puede consultar una organización sobre sus miembros.
5. Qué datos exactos conserva un usuario después de abandonar una organización.
6. Modelo comercial corporativo:
   - licencia;
   - usuario activo;
   - paquete;
   - consumo.
7. Alcance exacto del branding inicial.
8. Política para eliminar definitivamente una cuenta.
9. Política para eliminar o archivar una sesión de estudio.
10. Procedimiento de recuperación si una empresa pierde todos sus OWNER.
11. Si una misma cuenta corporativa puede pertenecer a varias organizaciones en el MVP.
12. Cantidad de dígitos y reglas finales del código de validación.

---

# 35. Fuera del MVP

Mantener conceptualmente posibles, pero no implementar inicialmente:

```text
DNS verification
SAML
SSO empresarial
OIDC corporativo
LDAP
Active Directory
SCIM
integración automática con RRHH
custom domains
subdominios dedicados
roles complejos
ADMIN
permisos granulares
CSS cargado por clientes
facturación empresarial compleja
```

---

# Resumen del modelo

```text
La cuenta sirve para autenticarse.

La organización contrata el servicio.

La membresía relaciona una cuenta corporativa con una organización.

El rol determina permisos dentro de esa organización.

La suscripción determina quién paga.

La sesión de estudio guarda el recorrido de aprendizaje.

Dos cuentas distintas pueden, con autorización del usuario,
acceder a la misma sesión de estudio sin fusionar sus autenticaciones.
```
