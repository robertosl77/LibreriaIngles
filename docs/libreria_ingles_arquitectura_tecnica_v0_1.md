# Librería Inglés — Documento de arquitectura técnica
## Arquitectura inicial, componentes, decisiones tecnológicas y planes de migración

**Versión:** 0.1  
**Estado:** arquitectura técnica inicial  
**Alcance:** este documento define la base técnica de la aplicación. Complementa al documento funcional de aprendizaje y al documento funcional multiempresa. No reemplaza ninguno de ellos.

---

# Índice rápido

1. [Objetivo](#1-objetivo)
2. [Principios de arquitectura](#2-principios-de-arquitectura)
3. [Arquitectura general](#3-arquitectura-general)
4. [Frontend](#4-frontend)
5. [Backend](#5-backend)
6. [API](#6-api)
7. [Persistencia](#7-persistencia)
8. [SQLite para desarrollo inicial](#8-sqlite-para-desarrollo-inicial)
9. [Plan de migración SQLite → PostgreSQL](#9-plan-de-migración-sqlite--postgresql)
10. [ORM y migraciones de esquema](#10-orm-y-migraciones-de-esquema)
11. [Estructura modular del backend](#11-estructura-modular-del-backend)
12. [Arquitectura multi-tenant](#12-arquitectura-multi-tenant)
13. [Autenticación](#13-autenticación)
14. [Autorización y roles](#14-autorización-y-roles)
15. [Sesiones / perfiles de estudio](#15-sesiones--perfiles-de-estudio)
16. [Integración con proveedores de IA](#16-integración-con-proveedores-de-ia)
17. [Failover y health checks](#17-failover-y-health-checks)
18. [Procesos asíncronos y jobs](#18-procesos-asíncronos-y-jobs)
19. [Plan de migración del sistema de jobs](#19-plan-de-migración-del-sistema-de-jobs)
20. [Emails y notificaciones](#20-emails-y-notificaciones)
21. [Archivos y storage](#21-archivos-y-storage)
22. [Branding](#22-branding)
23. [Plan de migración de storage local → object storage](#23-plan-de-migración-de-storage-local--object-storage)
24. [Configuración](#24-configuración)
25. [Seguridad](#25-seguridad)
26. [Logs y auditoría](#26-logs-y-auditoría)
27. [Testing](#27-testing)
28. [Entornos](#28-entornos)
29. [Deployment inicial](#29-deployment-inicial)
30. [Plan de migración hacia producción](#30-plan-de-migración-hacia-producción)
31. [Estructura inicial sugerida del repositorio](#31-estructura-inicial-sugerida-del-repositorio)
32. [Dependencias técnicas iniciales](#32-dependencias-técnicas-iniciales)
33. [Decisiones tomadas](#33-decisiones-tomadas)
34. [Decisiones todavía abiertas](#34-decisiones-todavía-abiertas)
35. [Roadmap técnico inicial](#35-roadmap-técnico-inicial)

---

# 1. Objetivo

Definir una arquitectura técnica inicial que permita:

- desarrollar rápido en local;
- mantener frontend y backend desacoplados;
- soportar usuarios personales y organizaciones;
- soportar múltiples proveedores de IA;
- escalar funcionalmente sin reescribir la aplicación;
- migrar infraestructura sin quedar atados a tecnologías de desarrollo local;
- permitir evolución desde un MVP simple hacia una solución productiva multiempresa.

El criterio general será:

> Empezar simple, pero evitar decisiones que obliguen a reescribir todo cuando la aplicación crezca.

---

# 2. Principios de arquitectura

## 2.1 Separación de responsabilidades

La aplicación debe dividirse en capas y módulos.

No se quiere una aplicación monolítica en el sentido de tener toda la lógica mezclada dentro de pocos archivos.

Sí puede comenzar como un único backend desplegable, pero internamente debe estar modularizado.

---

## 2.2 Frontend y backend desacoplados

El frontend no debe contener:

- lógica de negocio crítica;
- API keys;
- reglas de scoring;
- decisiones de failover;
- acceso directo a base de datos.

El frontend consume una API.

---

## 2.3 Persistencia desacoplada

La lógica de negocio no debe depender directamente de SQLite.

Se utilizará una capa ORM.

Esto permitirá comenzar con SQLite y migrar a PostgreSQL más adelante.

---

## 2.4 Proveedores externos desacoplados

OpenAI, Gemini u otros proveedores no deben aparecer directamente mezclados en la lógica de negocio.

Se utilizarán adapters.

---

## 2.5 Infraestructura reemplazable

Componentes que empiezan simples deben tener una ruta clara de migración.

Ejemplos:

```text
SQLite
→ PostgreSQL

storage local
→ S3 / Azure Blob / equivalente

jobs internos simples
→ worker + cola

servidor local
→ contenedores / cloud
```

---

# 3. Arquitectura general

Arquitectura inicial:

```text
                 FRONTEND
                  Angular
                     │
                     │ HTTPS / JSON
                     ▼
                  REST API
                     │
                     ▼
                 BACKEND
             Python + FastAPI
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
   Dominio        Integraciones   Jobs
   / negocio         externas     async
        │
        ▼
   SQLAlchemy
        │
        ▼
      SQLite
   desarrollo inicial
```

Evolución prevista:

```text
Angular
   │
FastAPI
   │
   ├── PostgreSQL
   ├── Worker / Queue
   ├── Object Storage
   ├── Email Provider
   └── AI Providers
```

---

# 4. Frontend

Tecnología inicial:

```text
Angular
```

Responsabilidades:

- landing pública;
- login;
- portal personal;
- portal corporativo;
- panel de organización;
- dashboard;
- clases;
- configuración;
- branding;
- gestión de membresías;
- feedback al usuario.

---

## 4.1 Principios del frontend

- No hardcodear branding por empresa.
- No almacenar secretos.
- No acceder directamente a proveedores de IA.
- No tomar decisiones de negocio importantes.
- Consumir contratos definidos por la API.
- Preparar componentes reutilizables.
- Separar pantallas públicas, personales y corporativas.

---

# 5. Backend

Tecnología inicial:

```text
Python
FastAPI
```

FastAPI se propone porque encaja bien con:

- APIs REST;
- tipado;
- modelos estructurados;
- JSON;
- validación;
- integración con servicios externos;
- desarrollo rápido.

---

## 5.1 Responsabilidades del backend

- autenticación;
- autorización;
- usuarios;
- organizaciones;
- membresías;
- roles;
- suscripciones;
- sesiones de estudio;
- clases;
- ejercicios;
- evaluación;
- progreso;
- routing de proveedores IA;
- failover;
- health checks;
- emails;
- invitaciones;
- branding;
- carga masiva;
- seguridad;
- auditoría.

---

# 6. API

La comunicación principal será mediante:

```text
REST
JSON
HTTPS
```

Ejemplo:

```text
Angular
   ↓
POST /api/auth/login
GET  /api/me
GET  /api/organizations/{id}
POST /api/classes
POST /api/classes/{id}/submit
```

Los endpoints definitivos se diseñarán durante implementación.

---

## 6.1 Contratos estructurados

Las respuestas internas deben utilizar estructuras previsibles.

Especialmente en:

- generación de clases;
- evaluación;
- progreso;
- proveedores IA;
- errores;
- estados.

---

# 7. Persistencia

Se utilizará una base de datos relacional.

Primera etapa:

```text
SQLite
```

Evolución prevista:

```text
PostgreSQL
```

---

# 8. SQLite para desarrollo inicial

SQLite permite:

- instalación prácticamente nula;
- trabajar completamente en local;
- desarrollo rápido;
- backups sencillos;
- baja complejidad inicial.

Ejemplo:

```text
./data/libreria_ingles.db
```

Se considera apropiada para:

- desarrollo;
- pruebas iniciales;
- prototipo funcional;
- ejecución de un único desarrollador.

---

## 8.1 Limitaciones asumidas

SQLite no será considerada la base definitiva de producción.

A medida que aparezcan:

- usuarios concurrentes;
- múltiples organizaciones;
- workers;
- procesamiento asíncrono;
- mayor volumen;
- alta disponibilidad;

la aplicación deberá migrar.

---

# 9. Plan de migración SQLite → PostgreSQL

La migración queda registrada desde el comienzo.

## Fase 1 — desarrollo

```text
SQLite
```

La aplicación accede siempre mediante ORM.

No utilizar SQL específico de SQLite salvo necesidad excepcional.

---

## Fase 2 — entorno de integración

Introducir:

```text
PostgreSQL
```

en un entorno de testing/integración.

Ejecutar allí:

- migraciones;
- tests;
- validación de constraints;
- concurrencia básica.

---

## Fase 3 — producción

PostgreSQL pasa a ser:

```text
base principal
```

SQLite queda únicamente como opción local.

---

## 9.1 Regla de compatibilidad

Desde el día uno:

> Todo código de persistencia debe escribirse pensando que SQLite es temporal.

Evitar:

- dependencias específicas de SQLite;
- queries no portables;
- tipos exclusivos;
- uso manual innecesario de conexiones.

---

# 10. ORM y migraciones de esquema

Tecnologías propuestas:

```text
SQLAlchemy
Alembic
```

SQLAlchemy:

- abstracción de persistencia;
- mapeo de entidades;
- compatibilidad con distintos motores.

Alembic:

- evolución controlada del esquema.

Ejemplo:

```text
v001_create_users
v002_create_organizations
v003_create_memberships
v004_create_study_profiles
```

Nunca depender de editar manualmente la base de producción.

---

# 11. Estructura modular del backend

Propuesta inicial:

```text
app/
├── auth/
├── users/
├── organizations/
├── memberships/
├── roles/
├── subscriptions/
├── invitations/
├── branding/
├── study_profiles/
├── curriculum/
├── classes/
├── exercises/
├── evaluations/
├── progress/
├── ai/
├── notifications/
├── jobs/
├── storage/
├── audit/
└── shared/
```

---

## 11.1 Separación por dominio

Ejemplo:

```text
organizations
```

no debe conocer detalles internos de:

```text
OpenAI
```

Y:

```text
ai
```

no debe decidir reglas de membresías.

Cada módulo tiene responsabilidad limitada.

---

# 12. Arquitectura multi-tenant

La solución será multiempresa.

Cada organización se considera un:

```text
tenant
```

Los datos deben estar asociados explícitamente a:

```text
organization_id
```

cuando correspondan.

---

## 12.1 Primera etapa

No es necesario crear una base de datos separada por empresa.

Se utilizará:

```text
una misma base
+
organization_id
```

Ejemplo:

```text
MEMBERSHIP
account_id
organization_id
role
```

---

## 12.2 Regla crítica

Toda operación corporativa debe validar:

```text
usuario autenticado
+
membresía activa
+
organización correcta
+
rol requerido
```

Nunca confiar únicamente en que el frontend envíe un `organization_id`.

---

# 13. Autenticación

Existen dos flujos.

## Personal

```text
Google
```

## Corporativo

```text
email corporativo
+
autenticación propia
```

El método exacto corporativo queda abierto entre:

```text
password
OTP
magic link
combinación
```

---

## 13.1 Sesión de autenticación

El backend emitirá una sesión o token autenticado.

La implementación exacta puede ser:

```text
JWT
```

o:

```text
cookie segura de sesión
```

Queda pendiente definir cuál conviene más.

---

# 14. Autorización y roles

El backend valida permisos.

Roles iniciales:

```text
OWNER
STUDENT
```

Ejemplo:

```text
OWNER
→ puede administrar organización

STUDENT
→ no puede modificar organización
```

El frontend puede ocultar botones, pero eso no reemplaza la validación del backend.

---

# 15. Sesiones / perfiles de estudio

La arquitectura técnica debe respetar la decisión funcional:

```text
ACCOUNT
≠
STUDY_PROFILE
```

Modelo:

```text
ACCOUNT
    │
    ▼
ACCOUNT_STUDY_PROFILE
    │
    ▼
STUDY_PROFILE
```

Varias cuentas pueden acceder al mismo perfil.

---

# 16. Integración con proveedores de IA

Se debe utilizar una capa común.

Concepto:

```text
AIProviderAdapter
```

Implementaciones:

```text
OpenAIAdapter
GeminiAdapter
FutureProviderAdapter
```

Interfaz conceptual:

```text
generate_class()
evaluate_class()
health_check()
```

---

## 16.1 Router de IA

Responsable de:

```text
seleccionar conexión activa
ejecutar operación
detectar fallo
clasificar error
hacer failover
actualizar estado
```

La lógica pedagógica no debería saber qué proveedor concreto respondió.

---

# 17. Failover y health checks

Estados internos posibles:

```text
AVAILABLE
QUOTA_EXCEEDED
RATE_LIMITED
INVALID_CREDENTIALS
PROVIDER_DOWN
NETWORK_ERROR
UNKNOWN_ERROR
DISABLED
```

El sistema mantiene:

```text
prioridad configurada
+
conexión activa
```

Si la activa falla:

```text
probar siguiente
```

---

# 18. Procesos asíncronos y jobs

Hay operaciones que no deberían depender de una request HTTP larga.

Ejemplos:

- corregir clases pendientes;
- reintentar proveedores;
- health checks;
- enviar invitaciones masivas;
- enviar códigos;
- procesar CSV;
- enviar emails;
- tareas periódicas.

Arquitectónicamente se considera necesario un sistema de jobs.

---

## 18.1 Primera etapa

Puede comenzar con un mecanismo simple compatible con el backend.

No hace falta introducir desde el primer día una infraestructura compleja.

---

# 19. Plan de migración del sistema de jobs

## Fase 1

Procesos simples:

```text
FastAPI background tasks
o scheduler local
```

solo para desarrollo y baja carga.

---

## Fase 2

Cuando crezcan las necesidades:

```text
Queue
+
Worker
```

Ejemplo conceptual:

```text
Backend
   ↓
Queue
   ↓
Worker
```

---

## Fase 3

En producción se podrá utilizar una tecnología como:

```text
Celery + Redis
```

u otra equivalente.

No se decide todavía el producto concreto.

La arquitectura debe evitar que la lógica de negocio dependa de una implementación específica.

---

# 20. Emails y notificaciones

Se necesitará un módulo común para:

- invitaciones;
- verificación de email;
- códigos de seguridad;
- recuperación;
- avisos corporativos;
- eventos de cuenta.

Interfaz conceptual:

```text
NotificationService
```

Ejemplo:

```text
send_invitation()
send_verification_code()
send_account_recovery()
```

---

# 21. Archivos y storage

No guardar archivos directamente dentro de la base de datos salvo casos excepcionales.

Archivos previstos:

```text
logos de organizaciones
imágenes de branding
archivos temporales
CSV de importación temporal
```

---

## 21.1 Primera etapa

Storage local:

```text
/storage
```

Ejemplo:

```text
/storage/organizations/10/logo.png
```

La base guarda solamente:

```text
ruta / identificador / metadata
```

---

# 22. Branding

Para el MVP:

```text
logo de la organización
nombre visible
```

pueden ser suficientes.

El OWNER podrá configurarlos.

---

## 22.1 Primera implementación

Ejemplo:

```text
Organization 10
brand_name = Cacatúa
logo_path = /storage/organizations/10/logo.png
```

Cuando el usuario entra al portal corporativo:

```text
cargar branding del tenant
```

---

## 22.2 Evolución prevista

Más adelante:

```text
primary_color
secondary_color
font
favicon
login_background
border_radius
```

---

# 23. Plan de migración de storage local → object storage

## Fase 1

```text
filesystem local
```

---

## Fase 2

Introducir abstracción:

```text
StorageService
```

Métodos:

```text
save()
delete()
get_url()
```

---

## Fase 3

Migrar backend concreto a:

```text
S3
Azure Blob
Google Cloud Storage
o equivalente
```

Sin modificar la lógica de branding.

---

# 24. Configuración

La aplicación debe utilizar configuración externa.

Ejemplos:

```text
DATABASE_URL
JWT_SECRET
OPENAI_CONFIG
EMAIL_CONFIG
STORAGE_CONFIG
ENVIRONMENT
```

Nunca hardcodear credenciales.

Durante desarrollo:

```text
.env
```

En producción:

```text
secret manager / variables de entorno
```

---

# 25. Seguridad

Requisitos iniciales:

- contraseñas hasheadas;
- HTTPS en producción;
- secretos fuera del código;
- API keys cifradas;
- nunca devolver secretos completos al frontend;
- validación de tenant en backend;
- autorización por rol;
- códigos de verificación con expiración;
- protección contra intentos repetidos;
- validación de archivos;
- límites de tamaño;
- sanitización;
- logging sin secretos.

---

## 25.1 API keys de IA

Las credenciales de los usuarios deben:

```text
cifrarse en reposo
```

y nunca aparecer:

```text
en logs
en respuestas API
en Angular
```

---

# 26. Logs y auditoría

Debe existir logging técnico.

Ejemplos:

```text
request_id
user_id
organization_id
evento
resultado
timestamp
```

También será útil auditoría funcional para acciones sensibles:

```text
OWNER cambió rol
OWNER revocó membresía
branding modificado
suscripción modificada
```

---

# 27. Testing

Capas iniciales:

```text
unit tests
integration tests
API tests
```

Especialmente importantes:

- permisos;
- multi-tenant;
- membresías;
- cambio de roles;
- vinculación de study profiles;
- failover;
- scoring;
- persistencia.

---

## 27.1 Regla de multi-tenant

Debe existir testing específico para asegurar:

```text
Usuario de empresa A
NO puede acceder
a datos de empresa B
```

---

# 28. Entornos

Como mínimo:

```text
LOCAL
TEST
PRODUCTION
```

Posible evolución:

```text
LOCAL
DEV
TEST
STAGING
PRODUCTION
```

Cada entorno tendrá configuración independiente.

---

# 29. Deployment inicial

Primera etapa:

```text
Angular
FastAPI
SQLite
storage local
```

pueden ejecutarse en una única máquina de desarrollo.

Ejemplo conceptual:

```text
localhost:4200 → Angular
localhost:8000 → FastAPI
```

---

# 30. Plan de migración hacia producción

La arquitectura deberá permitir evolucionar gradualmente.

## Etapa 1 — desarrollo local

```text
Angular local
FastAPI local
SQLite
filesystem
jobs simples
```

---

## Etapa 2 — entorno compartido

```text
Angular build
FastAPI
PostgreSQL
storage persistente
servicio de email
```

---

## Etapa 3 — producción inicial

```text
Frontend servido estáticamente
Backend desplegado como servicio
PostgreSQL administrado
Object Storage
HTTPS
dominio real
backups
monitorización
```

---

## Etapa 4 — crecimiento

Si el volumen lo justifica:

```text
Load balancer
múltiples instancias FastAPI
workers independientes
Redis / queue
CDN
object storage
monitoring centralizado
autoscaling
```

No implementar esto antes de necesitarlo.

---

# 31. Estructura inicial sugerida del repositorio

Opción monorepo:

```text
libreria-ingles/
│
├── frontend/
│   └── Angular
│
├── backend/
│   └── FastAPI
│
├── docs/
│   ├── funcional-aprendizaje.md
│   ├── funcional-multiempresa.md
│   └── arquitectura-tecnica.md
│
├── storage/
│
└── README.md
```

Backend:

```text
backend/
├── app/
│   ├── main.py
│   ├── auth/
│   ├── users/
│   ├── organizations/
│   ├── memberships/
│   ├── subscriptions/
│   ├── study_profiles/
│   ├── curriculum/
│   ├── classes/
│   ├── ai/
│   ├── notifications/
│   ├── branding/
│   ├── jobs/
│   └── shared/
│
├── migrations/
├── tests/
└── requirements / pyproject
```

---

# 32. Dependencias técnicas iniciales

Propuesta inicial, no definitiva:

## Backend

```text
Python
FastAPI
SQLAlchemy
Alembic
Pydantic
```

## Base de datos inicial

```text
SQLite
```

## Producción futura

```text
PostgreSQL
```

## Frontend

```text
Angular
TypeScript
```

Las librerías exactas se elegirán cuando comience la implementación.

---

# 33. Decisiones tomadas

- Frontend: Angular.
- Backend: Python.
- Framework backend propuesto: FastAPI.
- API desacoplada mediante REST/JSON.
- Desarrollo inicial con SQLite.
- PostgreSQL previsto para producción.
- SQLAlchemy para abstraer persistencia.
- Alembic para migraciones.
- Arquitectura modular.
- Multi-tenant mediante `organization_id`.
- Una base compartida inicialmente.
- Personal autenticado con Google.
- Corporativo con autenticación propia.
- Proveedores IA detrás de adapters.
- Failover centralizado en backend.
- Jobs asíncronos previstos desde arquitectura.
- Storage local inicialmente.
- Object Storage previsto como evolución.
- Branding inicial basado principalmente en logo/nombre.
- Configuración de branding a cargo del OWNER.
- Secretos nunca hardcodeados.
- Testing específico de aislamiento entre tenants.

---

# 34. Decisiones todavía abiertas

1. Método exacto de login corporativo.
2. JWT vs. cookie de sesión.
3. Librería Angular de componentes, si se utiliza alguna.
4. Motor exacto de envío de emails.
5. Sistema inicial de background jobs.
6. Tecnología final de cola/worker.
7. Hosting inicial.
8. Proveedor de PostgreSQL productivo.
9. Object Storage productivo.
10. Servicio de observabilidad.
11. Estrategia exacta de backups.
12. CI/CD.
13. Docker desde primera etapa o posteriormente.
14. Dominio definitivo.
15. API versioning.
16. Estrategia exacta de cifrado de API keys.
17. Límite y formato de uploads.

---

# 35. Roadmap técnico inicial

## Paso 1 — estructura

```text
crear repositorio
crear frontend Angular
crear backend FastAPI
crear configuración
```

## Paso 2 — persistencia

```text
SQLAlchemy
SQLite
Alembic
```

Crear primeras entidades:

```text
Account
Organization
Membership
Role
Invitation
Subscription
StudyProfile
AccountStudyProfile
```

## Paso 3 — autenticación

```text
personal
corporativa
roles
```

## Paso 4 — organización

```text
registro empresa
OWNER
panel de personas
invitaciones
CSV
branding básico
```

## Paso 5 — aprendizaje

Conectar las entidades del documento funcional de aprendizaje.

## Paso 6 — IA

```text
AIProviderAdapter
router
generación
evaluación
```

## Paso 7 — resiliencia

```text
failover
health checks
pending jobs
```

## Paso 8 — migración de infraestructura

Cuando el proyecto lo necesite:

```text
SQLite → PostgreSQL
filesystem → Object Storage
background local → Worker/Queue
local → producción
```

---

# Resumen técnico

```text
Angular
   ↓
REST/JSON
   ↓
FastAPI
   ↓
dominio modular
   ↓
SQLAlchemy
   ↓
SQLite inicialmente
   ↓
PostgreSQL cuando el proyecto evolucione
```

El resto de integraciones se conectan mediante abstracciones para permitir reemplazo futuro sin reescribir el dominio.

La regla central de este documento es:

> Todo componente elegido por simplicidad para el MVP debe tener una ruta de migración explícita si sabemos desde el comienzo que no será la solución final.
