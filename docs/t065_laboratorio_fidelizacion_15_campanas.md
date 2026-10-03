# T-065 — Laboratorio de fidelización: 15 campañas

Fecha: 2026-10-03  
Estado de T-065: **En curso · pendiente de validación de Roberto**

Este laboratorio prueba el asistente IA de campañas contra quince intenciones de fidelización
deliberadamente diferentes. No busca variar solamente porcentajes o duraciones: cubre permanencia,
constancia, volumen, rachas, recuperación, onboarding, nivel, riesgo de abandono, reclamos,
referidos y descuentos.

La simulación automatizada vive en
`backend/tests/test_campaign_engine_t065.py::test_fifteen_fidelity_campaigns_are_simulated_and_supported_ones_can_be_created`.

Para los casos que el motor puede representar, el test toma el borrador de la IA, le asigna un
Benefit específico del escenario y crea una Campaign real en estado `DRAFT` dentro de la base
temporal de tests. Los casos que dependen de dominios inexistentes no se completan: deben devolver
una advertencia y dejar `benefitId=null` para impedir que el borrador parezca listo.

## Semántica de actividad validada

- `AVERAGE_CLASSES_PER_DAY`: promedio sobre **todos** los días de la ventana. Los días sin clases
  cuentan como cero.
- `AVERAGE_CLASSES_PER_ACTIVE_DAY`: promedio solamente entre días donde hubo actividad.
- `MIN_CLASSES_PER_ACTIVE_DAY`: mínimo de clases entre los días que tuvieron actividad.
- Para expresar “N clases todos los días durante K días” se combinan
  `MIN_CLASSES_PER_ACTIVE_DAY >= N` y `ACTIVE_STUDY_DAYS >= K`, ambas con `windowDays=K`.
- `CLASSES_COMPLETED`: volumen total dentro de una ventana.
- `ACTIVE_STUDY_DAYS`: cantidad de días distintos con actividad dentro de una ventana.
- `STUDY_STREAK_DAYS`: racha consecutiva actual.

## Los 15 escenarios

| # | Arista | Intención simulada | Borrador IA relevante | Resultado del laboratorio |
|---|---|---|---|---|
| 1 | Permanencia | Premiar cuentas personales con más de 1 año en la app | `DAYS_SINCE_CREATED >= 365` | Campaign DRAFT creada; Benefit de 7 días |
| 2 | Rendimiento sostenido | Promedio mínimo de 5 clases por día en últimos 30 días | `AVERAGE_CLASSES_PER_DAY >= 5`, ventana 30 | Campaign DRAFT creada; Benefit de 5 días |
| 3 | Constancia estricta | Al menos 3 clases todos los días durante 7 días | `MIN_CLASSES_PER_ACTIVE_DAY >= 3` + `ACTIVE_STUDY_DAYS >= 7`, ventana 7 | Campaign DRAFT creada; Benefit de 3 días |
| 4 | Racha | Racha de estudio de 14 días | `STUDY_STREAK_DAYS >= 14` | Campaign DRAFT creada; Benefit de 10 días |
| 5 | Presencia | Al menos 20 días con actividad en últimos 30 | `ACTIVE_STUDY_DAYS >= 20`, ventana 30 | Campaign DRAFT creada; Benefit de 14 días |
| 6 | Volumen | Al menos 50 clases en últimos 30 días | `CLASSES_COMPLETED >= 50`, ventana 30 | Campaign DRAFT creada; Benefit de 7 días |
| 7 | Win-back por inactividad | Sin membresía y sin estudiar hace 60 días | `HAS_GRANTED_SERVICE=false` + `DAYS_SINCE_LAST_ACTIVITY >= 60` | Campaign DRAFT creada; Benefit de 5 días |
| 8 | Win-back tras vencimiento | Servicio vencido hace al menos 30 días y sin membresía vigente | `HAS_GRANTED_SERVICE=false` + `DAYS_SINCE_SERVICE_EXPIRED >= 30` | Campaign DRAFT creada; Benefit de 10 días |
| 9 | Onboarding abandonado | Registrado pero nunca completó una clase | `NEVER_STUDIED=true` | Campaign DRAFT creada; Benefit de 3 días |
| 10 | Impulso por nivel | A1 con al menos 30 clases en últimos 14 días | `CURRENT_LEVEL=A1` + `CLASSES_COMPLETED >= 30`, ventana 14 | Campaign DRAFT creada; Benefit de 14 días |
| 11 | Riesgo por bajo volumen | Como máximo 3 clases en últimos 30 días | `CLASSES_COMPLETED <= 3`, ventana 30 | Campaign DRAFT creada; Benefit de 7 días |
| 12 | Riesgo por promedio bajo | Promedio máximo de 1 clase por día en últimos 14 días | `AVERAGE_CLASSES_PER_DAY <= 1`, ventana 14 | Campaign DRAFT creada; Benefit de 5 días |
| 13 | Gestión de reclamo | Compensar a quien tuvo un reclamo resuelto por soporte | No existe métrica de reclamos/soporte | No se crea Campaign; advertencia obligatoria y `benefitId=null` |
| 14 | Referidos | Premiar a quien invitó amigos que terminaron registrándose | No existe métrica de referidos exitosos | No se crea Campaign; advertencia obligatoria y `benefitId=null` |
| 15 | Descuento comercial | Personal, más de 6 meses, promedio >=5 clases/día y 10% de descuento | `DAYS_SINCE_CREATED >= 180` + `AVERAGE_CLASSES_PER_DAY >= 5`, ventana 30 | Segmentación válida; descuento no disponible. No se crea Campaign y `benefitId=null` |

## Caso 15: frase usada en la validación manual

Entrada:

> Necesito crear una campaña para beneficiar a los alumnos personal no corporativos que lleven
> más de 6 meses en la app y hagan un promedio de 5 clases diarias como mínimo; a estos les quiero
> ofrecer un 10% de descuento en la membresía.

Interpretación que ahora debe producir el motor:

```text
ACCOUNT_TYPE = PERSONAL
DAYS_SINCE_CREATED >= 180
AVERAGE_CLASSES_PER_DAY >= 5
windowDays = 30
```

Como el usuario no indicó la ventana del promedio, se propone 30 días y se advierte que es
editable. El 10% de descuento **no** se transforma en un Benefit de servicio: mientras no exista
un dominio comercial de precios/promociones, el borrador debe advertir la limitación y mantener
`benefitId=null`.

Esto evita la interpretación incorrecta anterior:

```text
MIN_CLASSES_PER_ACTIVE_DAY >= 5
```

Esa condición significaría “cada día en que estudió hizo al menos 5 clases”, y permitiría que una
persona estudiase solo dos días de treinta. No representa un promedio diario.

## Resultado técnico de la corrida

Última corrida de validación de esta iteración:

- Backend: **278 tests passed**.
- Migraciones: OK.
- Frontend build: OK.
- Audit de dependencias runtime: OK.
- Campañas simuladas por IA: **15**.
- Campañas soportadas creadas realmente como DRAFT en la base de tests: **12**.
- Casos rechazados de forma explícita por depender de dominios inexistentes: **3**.

T-065 no se considera resuelta por esta validación automática. Permanece **En curso** hasta la
validación funcional del usuario.


## Carga real en la base local

Además de la simulación automatizada, T-065 siembra **15 campañas reales en estado DRAFT**
cuando `APP_ENV` es `local`, `dev` o `development`.

Características del seed:

- es idempotente: cada caso tiene un `code` y un `CampaignSeedMarker`;
- no se ejecuta en producción ni en tests;
- no activa ninguna campaña;
- crea Benefits de laboratorio reutilizables y luego las Campaigns;
- funciona también sobre una base local ya existente que tenga sembrada la bienvenida;
- si una campaña de laboratorio se elimina posteriormente, el marker evita que reaparezca en
  cada reinicio.

Los casos persistidos son:

1. Permanencia 6 meses + promedio alto.
2. Aniversario de 1 año.
3. Constancia diaria 7 días.
4. Racha de estudio 14 días.
5. Alta presencia mensual.
6. Volumen mensual de 50 clases.
7. Impulso A1 intensivo.
8. Volvé después de 30 días.
9. Recuperación larga 90 días.
10. Regreso tras servicio vencido.
11. Registrado pero nunca empezó.
12. Riesgo por baja actividad.
13. Fidelidad usando propias keys.
14. Fidelidad híbrida + actividad.
15. Compensación manual post-reclamo.

El caso 15 usa `ACCOUNT_EMAIL = reemplazar@ejemplo.invalid` para que sea imposible aplicarlo
accidentalmente. El operador debe editar la campaña y reemplazar ese email por la cuenta real
después de resolver el reclamo. Esto permite probar una gestión manual de compensación sin fingir
que hoy existe un sistema automático de tickets/reclamos.

Los tres casos no ejecutables del laboratorio IA (reclamos automáticos, referidos automáticos y
descuento porcentual) siguen sirviendo como pruebas negativas: el asistente debe advertir esas
limitaciones y no inventar una segmentación. La campaña post-reclamo persistida es deliberadamente
un flujo **manual por email exacto**, no una automatización de reclamos.
