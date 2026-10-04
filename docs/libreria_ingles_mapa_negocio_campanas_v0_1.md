# Librería Inglés — Mapa funcional de negocio para campañas y automatizaciones
## Áreas de interacción, eventos, estados y oportunidades del motor de campañas

**Versión:** 0.1  
**Estado:** documento fundamental de exploración funcional / negocio  
**Alcance:** este documento identifica los dominios y funcionalidades de Librería Inglés con los que el motor de campañas puede interactuar. Complementa al documento funcional de aprendizaje, al documento funcional multiempresa y al documento de arquitectura técnica. No reemplaza ninguno de ellos.

---

# 1. Objetivo

El objetivo no es comenzar inventando campañas concretas.

Primero hay que identificar **lugares del negocio donde pueden nacer eventos, estados o señales que Campaigns debería poder consumir**. Después, sobre ese mapa, se diseñan campañas, automatizaciones, plantillas y acciones.

Una campaña concreta puede cambiar muchas veces. El evento o estado de negocio que la dispara debe ser estable.

Ejemplo:

~~~text
cliente solicita cancelar
        ↓
evento CANCEL_REQUESTED
        ↓
Campaigns evalúa contexto
        ↓
puede intentar retención
~~~

La respuesta podría ser un descuento, días gratis, un cambio de membresía, contacto comercial u otra acción futura.

La idea central es:

> primero descubrir el terreno de negocio; después definir qué campañas pueden vivir sobre él.

---

# 2. Mapa de áreas donde Campaigns puede interactuar

| Área / funcionalidad | Eventos o señales potenciales para Campaigns |
|---|---|
| **Suscripciones / membresías** | alta, renovación próxima, vencimiento, cancelación solicitada, cancelación efectiva, upgrade/downgrade |
| **Pagos** | pago aprobado, rechazado, mora, varios rechazos, renovación automática fallida, devolución |
| **Uso del producto** | primer uso, regreso, abandono, intensidad de uso, función nunca utilizada, caída brusca de actividad |
| **Aprendizaje** | mejora, estancamiento, retroceso, aprobación, desaprobación, certificado, racha, dificultad recurrente |
| **IA / consumo** | uso alto/bajo, límite cercano, fallo de claves propias, fallback a Plataforma, indisponibilidad de proveedor |
| **Operación de Plataforma** | incidente, degradación, interrupción, recuperación, compensación posterior |
| **Soporte / reclamos** | apertura de reclamo, reclamo grave, resolución favorable/desfavorable, reincidencia |
| **Satisfacción** | encuesta, NPS, valoración negativa/positiva, comentario posterior a una incidencia |
| **Invitaciones / referidos** | invitación enviada, no utilizada, aceptada, referido convertido, referido que paga |
| **Fidelización** | riesgo de baja, vuelta después de abandono, aniversario, renovación repetida, cliente histórico |
| **Comercial / pricing** | oferta, descuento, cupón, prueba, cambio de precio, promoción temporal |
| **B2B / empresas** | contratación, cancelación, ocupación de licencias, baja adopción, alta adopción, empleado inactivo, ADMIN sin actividad |
| **Administración corporativa** | incorporación masiva, licencias sin asignar, crecimiento de plantilla, expiración de contrato |
| **Cuenta / identidad** | registro incompleto, cuenta sin configurar, email verificado, recuperación, bloqueo/suspensión |
| **Costos internos** | cliente costoso, consumo desproporcionado, margen negativo, cambio de modelo/proveedor |
| **Comunicación** | email abierto/no abierto, notificación ignorada, campaña anterior aceptada/rechazada |
| **Datos / retención** | datos próximos a eliminación, recuperación antes del borrado, obligación de notificación |
| **Producto** | lanzamiento de nueva función, función compatible con determinado cliente, beta, migración obligatoria |

Este mapa no implica que todos esos dominios existan hoy ni que todas esas señales estén implementadas.

Su propósito es servir como **mapa de descubrimiento funcional** para que el motor pueda evolucionar sin quedar encerrado únicamente en campañas de login, beneficios o fidelización básica.

---

# 3. Tres familias de disparadores

Hasta ahora el motor está fuertemente apoyado en condiciones consultables y en triggers como LOGIN y FIRST_LOGIN.

A futuro debería poder vivir de tres familias distintas de disparadores.

## 3.1 Evento inmediato

Algo acaba de ocurrir en otro dominio.

Ejemplos:

~~~text
CANCELLATION_REQUESTED
PAYMENT_FAILED
CERTIFICATE_ISSUED
COMPLAINT_RESOLVED
INVITATION_REDEEMED
PLATFORM_INCIDENT_STARTED
~~~

El evento dispara una evaluación inmediata de Campaigns.

## 3.2 Estado detectado

No ocurrió necesariamente un evento puntual. El sistema detecta que una condición es verdadera.

Ejemplos:

~~~text
30 días sin estudiar
consumo superior a un umbral
empresa con baja adopción
cuenta con servicio vencido
usuario con una habilidad estancada
~~~

Este tipo de caso normalmente requiere consultas de estado o métricas acumuladas.

## 3.3 Evento temporal o programado

La condición depende del paso del tiempo y debe evaluarse aunque el usuario no ingrese.

Ejemplos:

~~~text
faltan 7 días para renovar
pasaron 30 días desde el vencimiento
una invitación lleva 7 días sin canjearse
se cumple un año desde el alta
debe ejecutarse el cierre mensual de una empresa
~~~

Estos casos requieren scheduler/batch y no deben depender de un login para existir.

---

# 4. Ejemplo rector: intención de cancelación

Supongamos una cuenta personal o una empresa que paga un servicio y decide cancelarlo.

La campaña no debería definirse como:

> “Campaña de 30 % de descuento”.

Eso describe una posible respuesta, pero no el hecho de negocio.

El hecho estable es:

~~~text
SUBSCRIPTION_CANCELLATION_REQUESTED
~~~

Sobre ese evento, Campaigns podría evaluar:

- tipo de cliente: personal o empresa;
- membresía actual;
- antigüedad;
- precio;
- nivel de uso;
- consumo;
- historial de renovaciones;
- campañas anteriores;
- descuentos ya utilizados;
- reclamos;
- satisfacción;
- rentabilidad;
- cualquier otra condición disponible en los dominios correspondientes.

Y luego decidir una acción configurada:

~~~text
SUBSCRIPTION_CANCELLATION_REQUESTED
        ↓
cuenta PERSONAL o empresa pagadora
        ↓
evaluar condiciones
        ↓
APPLY_DISCOUNT 30 % durante 3 meses
        ↓
si acepta, cancelar la baja
~~~

La propuesta concreta puede cambiar sin cambiar el evento.

Hoy este caso completo todavía no existe porque faltan, entre otras cosas, el dominio comercial/pagos y la capacidad de Campaigns de reaccionar a una solicitud de cancelación.

Eso no invalida el modelo. Al contrario: permite detectar con claridad qué piezas faltan.

---

# 5. Separar evento, condición, acción y entrega

Una automatización debería poder pensarse como composición de piezas independientes:

~~~text
ÁREA / DOMINIO
      ↓
EVENTO o ESTADO
      ↓
CONDICIONES
      ↓
ACCIÓN
      ↓
ENTREGA
      ↓
TRACKING
~~~

Ejemplos:

~~~text
Pago rechazado
      ↓
PAYMENT_FAILED
      ↓
tercer fallo + cliente histórico
      ↓
EXTEND_GRACE_PERIOD
      ↓
EMAIL
      ↓
aceptó / renovó / canceló
~~~

~~~text
Incidente de IA
      ↓
PLATFORM_INCIDENT_RESOLVED
      ↓
cuenta afectada realmente
      ↓
GRANT_BENEFIT
      ↓
IN_APP + EMAIL
      ↓
compensación aplicada
~~~

~~~text
Certificado obtenido
      ↓
CERTIFICATE_ISSUED
      ↓
nivel B1
      ↓
CREATE_INVITATION
      ↓
IN_APP
      ↓
invitación creada / canjeada
~~~

El motor no debe apropiarse de la información de los otros dominios.

Campaigns debe **consumir señales y ejecutar acciones autorizadas**, mientras la fuente de verdad sigue perteneciendo al dominio correspondiente.

---

# 6. Regla arquitectónica: no inventar señales

Si el dominio no existe o la aplicación no registra el dato real, Campaigns no debe aproximarlo semánticamente.

Ejemplos:

- un servicio vencido no equivale a un pago rechazado;
- días desde creación de cuenta no equivalen a antigüedad como cliente pago;
- días desde última actividad no equivalen a una racha que se perdió;
- pocas clases completadas no demuestran por sí solas que hubo muchas clases abandonadas;
- un Benefit no equivale a un descuento comercial;
- un error aislado de IA no equivale automáticamente a un incidente global de plataforma.

Primero debe existir la fuente de verdad. Después Campaigns puede incorporarla a su vocabulario.

---

# 7. Personas y empresas no tienen siempre el mismo destinatario

En B2C, muchas campañas pueden dirigirse directamente al estudiante porque él mismo es quien decide contratar, renovar o cancelar.

En B2B esto cambia.

El estudiante corporativo puede usar el producto, pero normalmente no decide la compra.

Por eso deben distinguirse:

~~~text
USUARIO AFECTADO
USUARIO QUE GENERA LA SEÑAL
DESTINATARIO DE LA COMUNICACIÓN
DECISOR COMERCIAL
BENEFICIARIO FINAL
~~~

Ejemplo:

~~~text
30 empleados con baja actividad
        ↓
señal agregada de ORGANIZATION
        ↓
campaña de recuperación B2B
        ↓
destinatario = ADMIN / representante de la empresa
        ↓
acción comercial sobre contrato/licencias
~~~

No corresponde enviar al alumno una oferta que solo puede aceptar quien paga el servicio corporativo.

---

# 8. Campaigns como capa transversal, no como segundo negocio

Campaigns no debe reemplazar:

- pagos;
- suscripciones;
- soporte;
- invitaciones;
- progreso;
- IA;
- organizaciones;
- email;
- scheduler;
- facturación;
- encuestas;
- incidentes;
- pricing.

Cada área conserva su propia lógica y su propia fuente de verdad.

Campaigns funciona como una capa transversal capaz de decir:

> “cuando en alguno de esos dominios ocurra o se detecte algo que conozco, evalúo reglas y ejecuto una acción permitida”.

Esto permite reutilizar un único motor para:

- fidelización;
- compensaciones;
- onboarding;
- recuperación;
- promociones;
- invitaciones;
- retención;
- expansión B2B;
- comunicación;
- reconocimiento;
- acciones operativas futuras.

Sin crear un motor separado para cada caso.

---

# 9. Método para descubrir nuevas capacidades

Antes de agregar una nueva regla o acción al motor conviene seguir este orden:

1. identificar el área de negocio;
2. identificar el hecho real que ocurre;
3. decidir si es evento inmediato, estado detectado o evento temporal;
4. localizar la fuente de verdad;
5. verificar si Campaigns ya puede expresarlo;
6. si no puede, determinar si falta una condición, trigger, acción, target/scope, métrica, dominio completo, scheduler o delivery;
7. recién después diseñar campañas concretas y plantillas.

La pregunta inicial no debe ser:

> “¿Qué otra campaña podemos inventar?”

Debe ser:

> “¿En qué otros lugares del negocio ocurren hechos que podrían producir una reacción configurable?”

---

# 10. Uso de este documento

Este documento debe utilizarse como base para:

- buscar nuevos terrenos funcionales para Campaigns;
- diseñar futuros experimentos de simulación;
- revisar si una nueva idea ya pertenece a un dominio existente;
- detectar capacidades faltantes sin duplicar motores;
- separar correctamente triggers, condiciones, acciones y delivery;
- diseñar automatizaciones B2C y B2B;
- alimentar futuras versiones del catálogo central de capacidades;
- evitar que el motor quede limitado al conjunto de campañas imaginadas durante el MVP.

No constituye por sí mismo un backlog de implementación.

Los cambios concretos deben convertirse en Issues independientes y relacionarse con las tareas correspondientes cuando su alcance esté suficientemente definido.

---

# 11. Principio rector

El motor debe evolucionar hacia un lenguaje común capaz de expresar reacciones del producto frente a hechos reales del negocio.

La dirección buscada es:

~~~text
DOMINIOS DEL NEGOCIO
        ↓
EVENTOS / ESTADOS / MÉTRICAS
        ↓
CAMPAIGNS
        ↓
CONDICIONES
        ↓
ACCIONES
        ↓
DELIVERY
        ↓
TRACKING
~~~

El objetivo no es multiplicar motores.

El objetivo es **ampliar el vocabulario del mismo motor para que pueda escuchar y actuar sobre cada vez más áreas del negocio, sin apropiarse de ellas ni falsear sus datos**.
