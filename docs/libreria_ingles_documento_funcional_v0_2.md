# English Learning App con IA
## Documento funcional / memoria de continuidad del proyecto
**Versión:** 0.2  
**Estado:** definición funcional inicial  
**Objetivo de este documento:** conservar con suficiente detalle todo lo definido durante la conversación para poder continuar el proyecto aunque se pierda el contexto del chat.

---

# Índice rápido de temas

1. [Visión general del producto](#1-visión-general-del-producto)
2. [Principios centrales que no deben perderse](#2-principios-centrales-que-no-deben-perderse)
3. [Niveles CEFR / MCER como columna vertebral](#3-niveles-cefr--mcer-como-columna-vertebral)
4. [Currícula y estructura pedagógica](#4-currícula-y-estructura-pedagógica)
5. [Habilidades a evaluar](#5-habilidades-a-evaluar)
6. [Nivel seleccionado, nivel estimado y nivel operativo](#6-nivel-seleccionado-nivel-estimado-y-nivel-operativo)
7. [Diagnóstico inicial](#7-diagnóstico-inicial)
8. [Promoción y descenso automático de nivel](#8-promoción-y-descenso-automático-de-nivel)
9. [Mapa de habilidades, score y confianza](#9-mapa-de-habilidades-score-y-confianza)
10. [Generación dinámica de clases y ejercicios](#10-generación-dinámica-de-clases-y-ejercicios)
11. [Corrección dinámica con IA](#11-corrección-dinámica-con-ia)
12. [Corrección vs. mejora de estilo o naturalidad](#12-corrección-vs-mejora-de-estilo-o-naturalidad)
13. [Estructura de una clase](#13-estructura-de-una-clase)
14. [Historial, reintentos y repetición de clases](#14-historial-reintentos-y-repetición-de-clases)
15. [Listening](#15-listening)
16. [Speaking](#16-speaking)
17. [Pronunciación / fonética](#17-pronunciación--fonética)
18. [Dashboard](#18-dashboard)
19. [Estados de una clase o sesión](#19-estados-de-una-clase-o-sesión)
20. [Autoguardado y recuperación](#20-autoguardado-y-recuperación)
21. [Pantalla inicial y navegación](#21-pantalla-inicial-y-navegación)
22. [Login y usuarios](#22-login-y-usuarios)
23. [Configuración de agentes / proveedores de IA](#23-configuración-de-agentes--proveedores-de-ia)
24. [Prioridad, agente activo y failover](#24-prioridad-agente-activo-y-failover)
25. [Ciclo de disponibilidad de agentes](#25-ciclo-de-disponibilidad-de-agentes)
26. [Health check / “ping” de agentes](#26-health-check--ping-de-agentes)
27. [Qué ocurre si todos los agentes quedan sin disponibilidad](#27-qué-ocurre-si-todos-los-agentes-quedan-sin-disponibilidad)
28. [Reintentos automáticos y backoff](#28-reintentos-automáticos-y-backoff)
29. [Cambio de agente sin molestar al usuario](#29-cambio-de-agente-sin-molestar-al-usuario)
30. [Independencia entre la clase y el proveedor de IA](#30-independencia-entre-la-clase-y-el-proveedor-de-ia)
31. [Formato estructurado de intercambio con la IA](#31-formato-estructurado-de-intercambio-con-la-ia)
32. [Modelo conceptual de datos](#32-modelo-conceptual-de-datos)
33. [Ejemplo de generación de ejercicio](#33-ejemplo-de-generación-de-ejercicio)
34. [Ejemplo de evaluación de respuesta](#34-ejemplo-de-evaluación-de-respuesta)
35. [Reglas funcionales importantes](#35-reglas-funcionales-importantes)
36. [Requisitos de seguridad para API keys](#36-requisitos-de-seguridad-para-api-keys)
37. [Arquitectura técnica tentativa](#37-arquitectura-técnica-tentativa)
38. [Escalabilidad](#38-escalabilidad)
39. [MVP propuesto](#39-mvp-propuesto)
40. [Evoluciones futuras](#40-evoluciones-futuras)
41. [Decisiones ya tomadas](#41-decisiones-ya-tomadas)
42. [Preguntas todavía abiertas](#42-preguntas-todavía-abiertas)
43. [Storytime completo del usuario](#43-storytime-completo-del-usuario)
44. [Prompt maestro para retomar el proyecto en otro chat](#44-prompt-maestro-para-retomar-el-proyecto-en-otro-chat)

---

# 1. Visión general del producto

La idea es construir una aplicación web de aprendizaje y práctica de inglés que combine:

- una **estructura pedagógica propia y controlada por la aplicación**;
- los niveles **CEFR / MCER** como columna vertebral;
- ejercicios generados dinámicamente por IA;
- corrección dinámica por IA;
- seguimiento persistente por usuario;
- adaptación automática a fortalezas y debilidades;
- práctica de gramática, vocabulario, lectura, escritura, escucha y habla;
- un dashboard que muestre qué domina el usuario y qué necesita reforzar;
- soporte para múltiples proveedores o conexiones de IA por usuario;
- continuidad automática cuando un proveedor deja de estar disponible.

El objetivo no es hacer un simple “generador de ejercicios con IA”.

El producto debería comportarse más como un **sistema de aprendizaje adaptativo**, donde la IA es una herramienta dentro de un marco definido por la aplicación.

La aplicación decide qué debe aprenderse, qué nivel corresponde, qué habilidades existen, cómo progresa una persona y cómo se consolidan las métricas.

La IA genera contenido y evalúa respuestas dentro de ese marco.

---

# 2. Principios centrales que no deben perderse

## 2.1 La aplicación maneja los hilos

La IA **no debe decidir qué significa A1, A2, B1, etc.**

La aplicación tendrá una currícula propia y estructurada.

La IA recibirá parámetros concretos, por ejemplo:

```text
Nivel: A1
Área: Grammar
Tema: Present Simple
Subtema: Questions with do/does
Dificultad: básica
Modalidad: writing
Objetivos evaluados:
- seleccionar correctamente do/does
- usar verbo base después de does
```

La IA genera el ejercicio dentro de esas restricciones.

---

## 2.2 El contenido debe ser dinámico, la estructura no

No se quiere hardcodear miles de frases.

No se quiere escribir una enorme cantidad de `if` para aceptar todas las variantes posibles.

Lo que sí debe existir de forma controlada es:

```text
Nivel
→ Área
→ Tema
→ Skill / subskill
→ Objetivos
→ Dificultad
→ Modalidad
```

La IA rellena esa estructura con contenido diferente.

---

## 2.3 La clase pertenece a la aplicación, no al agente

Una clase puede ser:

- generada por ChatGPT;
- corregida por Gemini;
- continuada por otro proveedor.

Eso no debe romper nada.

Una vez generada una clase, queda persistida en el backend en un formato propio.

El proveedor que la generó es información de trazabilidad, pero **no es dueño de la clase**.

---

## 2.4 Persistir primero, procesar después

Especialmente en correcciones:

```text
Usuario termina clase
        ↓
Backend guarda respuestas
        ↓
Backend intenta corrección
```

Nunca debe ocurrir:

```text
Backend intenta corrección
        ↓
falla IA
        ↓
se pierden respuestas
```

Si todos los agentes fallan, las respuestas ya están guardadas.

---

## 2.5 Correcto/incorrecto no alcanza

La aplicación debe guardar una evaluación descompuesta.

Ejemplo:

```text
Present Simple:
- uso de does: correcto
- verbo base después de does: incorrecto
- orden de palabras: correcto
- ortografía: correcto
```

Eso permitirá construir un dashboard realmente útil.

---

# 3. Niveles CEFR / MCER como columna vertebral

Los niveles principales utilizados serán:

```text
A1
A2
B1
B2
C1
C2
```

No existe un nivel estándar A3 dentro de esta escala.

La aplicación utilizará estas categorías como estructura general.

Sin embargo, un nivel CEFR no debe tratarse como un bloque aislado de gramática.

Un tema puede aparecer en múltiples niveles con objetivos diferentes.

Ejemplo:

```text
Present Simple
```

Puede introducirse en A1 para:

- rutinas;
- afirmaciones básicas;
- preguntas con do/does;
- negaciones simples.

Pero en un nivel mucho más avanzado podría aparecer dentro de:

- análisis de registro;
- contraste estilístico;
- reescritura;
- explicación de matices;
- elección entre presente simple y otras estructuras;
- redacción de textos complejos.

Por lo tanto:

> El nivel no define solamente “qué tiempo verbal aparece”, sino la profundidad, complejidad y dominio esperado.

---

# 4. Currícula y estructura pedagógica

La currícula debe existir como **datos**, no como código.

Agregar A2, B1 o C1 no debería requerir reescribir el motor.

Una estructura conceptual posible:

```text
LEVEL
  └── AREA
       └── TOPIC
            └── SKILL
                 └── LEARNING_OBJECTIVE
```

Ejemplo:

```text
A1
└── Grammar
    └── Present Simple
        ├── affirmative
        ├── negative
        ├── questions_do_does
        └── third_person_singular
```

Otro ejemplo:

```text
A1
└── Vocabulary
    └── Daily Life
        ├── family
        ├── routines
        ├── work
        └── food
```

Esto puede estar inicialmente en:

- JSON;
- YAML;
- tablas de base de datos.

La elección técnica se definirá más adelante.

Lo importante funcionalmente es:

> Los niveles y habilidades deben ser parametrizables.

---

## 4.1 Contenido orientativo inicial de A1

Durante la conversación se mencionaron como ejemplos de A1:

- saludos y presentaciones;
- `to be`;
- pronombres;
- posesivos;
- artículos;
- singular y plural;
- presente simple;
- `do / does`;
- presente continuo;
- `can / can't`;
- `there is / there are`;
- `have got`;
- imperativos;
- preguntas básicas;
- `what / where / who / when / how`;
- preposiciones básicas;
- `in / on / at`;
- demostrativos como `this / that`;
- conectores básicos:
  - `and`;
  - `but`;
  - `or`;
  - `because`;
- vocabulario cotidiano.

Esto todavía deberá formalizarse antes de implementar la currícula definitiva.

---

# 5. Habilidades a evaluar

La aplicación no debe reducir el nivel de inglés a “gramática”.

Debe existir un mapa de habilidades.

Como mínimo:

```text
Grammar
Vocabulary
Reading
Writing
Listening
Speaking
Pronunciation
```

También puede existir una categoría de comunicación o uso práctico.

Una persona puede ser:

```text
B1 en Grammar
B1 en Reading
A2 en Listening
A2 en Speaking
```

Por lo tanto, un único número global tiene valor orientativo, pero no describe completamente al usuario.

---

# 6. Nivel seleccionado, nivel estimado y nivel operativo

Conviene distinguir conceptos.

## 6.1 Nivel seleccionado

El usuario puede elegir manualmente:

```text
“Quiero comenzar en B1”
```

No se le debe impedir experimentar.

---

## 6.2 Nivel estimado

Puede provenir del diagnóstico inicial.

Ejemplo:

```text
Nivel estimado inicial: A2
```

---

## 6.3 Nivel operativo

Es el nivel que el sistema considera adecuado basándose en evidencia acumulada.

Ejemplo:

```text
Seleccionado por el usuario: C1
Operativo actual: B1
```

Esto permite que alguien elija C1 y lo pruebe.

Si demuestra dominio, continúa.

Si falla consistentemente en distintas habilidades, el sistema puede bajar progresivamente el nivel operativo.

---

# 7. Diagnóstico inicial

No se quiere obligar a todos a comenzar en A1.

La primera vez deben existir, como mínimo, dos caminos:

```text
1. Hacer diagnóstico
2. Elegir nivel manualmente
```

El diagnóstico ideal debería ser **adaptativo**.

Ejemplo:

```text
Pregunta sencilla
     ↓
respuesta correcta
     ↓
sube dificultad
     ↓
respuesta correcta
     ↓
sube dificultad
     ↓
comienzan los errores
     ↓
se identifica una zona probable
```

Así no hace falta hacer un examen enorme.

El diagnóstico también puede evaluar distintas dimensiones:

```text
Grammar
Reading
Writing
Listening
...
```

Una primera versión puede comenzar más simple.

---

# 8. Promoción y descenso automático de nivel

## 8.1 Promoción

No debe funcionar así:

```text
200 ejercicios A1 obligatorios
→ recién entonces A2
```

Debe ser adaptativo.

Ejemplo:

```text
Present Simple A1
18 intentos
94 % de dominio
confianza alta
        ↓
prueba de transición
        ↓
contenido equivalente de A2
```

Si el usuario demuestra dominio rápidamente, puede avanzar rápidamente.

---

## 8.2 Descenso

Tampoco se debe bajar a una persona por una mala clase.

El descenso requiere **evidencia suficiente y transversal**.

Ejemplo:

Usuario se colocó en C1.

Durante distintas clases aparecen resultados débiles en:

```text
Writing C1        → bajo
Listening C1      → bajo
Grammar C1        → bajo
Reading C1        → bajo
```

Si el patrón se sostiene, el sistema baja el nivel operativo.

Ejemplo:

```text
C1 → B2
```

Si en B2 continúa existiendo evidencia de dificultad:

```text
B2 → B1
```

Esto permite encontrar el nivel real mediante uso.

---

## 8.3 No confundir problema puntual con problema de nivel

Si una persona falla únicamente en:

```text
Third person singular
```

pero obtiene buen rendimiento en todo lo demás, no corresponde necesariamente bajar su nivel completo.

El sistema debe diferenciar:

```text
debilidad localizada
```

de:

```text
evidencia transversal de que el nivel es demasiado alto
```

---

# 9. Mapa de habilidades, score y confianza

No alcanza con guardar:

```text
score = 100
```

Porque:

```text
2 ejercicios correctos de 2
```

no significan lo mismo que:

```text
28 ejercicios correctos de 30
```

Por eso cada skill debería tener, como mínimo:

```text
score
attempt_count
confidence
status
trend
```

Ejemplo:

```json
{
  "skill": "present_simple.questions_do_does",
  "score": 94,
  "attemptCount": 18,
  "confidence": "high",
  "status": "MASTERED"
}
```

Otro:

```json
{
  "skill": "to_be.questions",
  "score": 100,
  "attemptCount": 2,
  "confidence": "low",
  "status": "LEARNING"
}
```

Estados considerados:

```text
LEARNING
MASTERED
NEEDS_REVIEW
```

Podrán agregarse otros más adelante.

---

# 10. Generación dinámica de clases y ejercicios

La aplicación determina qué necesita.

La IA genera el contenido.

Flujo:

```text
Dashboard / motor adaptativo
        ↓
selecciona habilidades
        ↓
construye parámetros de clase
        ↓
envía solicitud a IA
        ↓
IA devuelve clase estructurada
        ↓
backend valida
        ↓
backend guarda
        ↓
frontend muestra
```

Una clase puede incluir ejercicios de distintos tipos.

Por ejemplo:

```text
Clase A1
├── Present Simple
├── Vocabulary
├── Reading
├── Listening
└── Writing
```

En una primera versión puede limitarse a menos modalidades.

---

## 10.1 Dos usuarios no necesariamente reciben la misma clase

Si Roberto y otro usuario solicitan:

```text
A1
Present Simple
```

los objetivos pueden ser iguales, pero las frases y contextos pueden ser diferentes.

Ejemplo:

Usuario A:

```text
Does Sarah work on Saturdays?
```

Usuario B:

```text
Does Peter play football after school?
```

Ambos practican la misma skill.

---

# 11. Corrección dinámica con IA

La IA que corrige debe recibir:

- nivel;
- ejercicio original;
- objetivos;
- respuesta del usuario;
- criterios de evaluación.

Nunca solamente:

```text
“Corregí esta frase”
```

Debe conocer exactamente qué estaba siendo evaluado.

---

## 11.1 Evaluación descompuesta

Ejemplo:

Ejercicio:

```text
Complete the question:
___ she work on Saturdays?
```

Respuesta:

```text
Does she works on Saturdays?
```

La devolución puede identificar:

```text
does                          → correcto
estructura interrogativa      → correcto
verbo base después de does    → incorrecto
```

De esa forma el usuario no recibe simplemente un `0`.

---

## 11.2 El backend conserva la última palabra

La IA puede devolver:

```text
score sugerido
errores
conceptos correctos
conceptos incorrectos
```

Pero la aplicación define cómo eso afecta el progreso.

Esto evita que cambiar de modelo de IA cambie completamente el sistema de puntuación.

---

# 12. Corrección vs. mejora de estilo o naturalidad

Esto fue considerado especialmente importante.

Hay que distinguir:

```text
“Está mal”
```

de:

```text
“Está bien, pero suena poco natural”
```

Ejemplo:

Una frase puede ser:

- gramaticalmente correcta;
- comprensible;
- pero demasiado rígida o artificial.

No corresponde bajarle la nota de gramática por eso.

Tipos de feedback posibles:

```text
GRAMMAR_ERROR
VOCABULARY_ERROR
SPELLING_ERROR
WORD_ORDER_ERROR
PRONUNCIATION_ERROR

STYLE_SUGGESTION
NATURALNESS_SUGGESTION
SHORTER_ALTERNATIVE
```

Las sugerencias de estilo no deberían necesariamente descontar puntos.

La devolución al usuario puede decir:

```text
Correcto.

Una forma más natural sería:
...
```

---

# 13. Estructura de una clase

Se imaginó una experiencia similar a recibir una “hoja” de ejercicios.

Flujo:

```text
Usuario solicita nueva clase
        ↓
Sistema decide objetivos
        ↓
IA genera clase
        ↓
Clase se guarda
        ↓
Usuario responde
        ↓
Autoguardado durante el trabajo
        ↓
Usuario finaliza / comprobar
        ↓
Respuestas se guardan
        ↓
Se solicita evaluación
        ↓
Se guarda devolución
        ↓
Dashboard se actualiza
```

Cada clase debe ser única y estar vinculada al usuario.

---

# 14. Historial, reintentos y repetición de clases

Cada clase debe poder conservarse.

Así el usuario podrá:

```text
Rehacer esta clase
```

y comparar resultados.

Ejemplo:

```text
Clase #153

Intento 1
score: 62 %

Intento 2
score: 81 %

Intento 3
score: 93 %
```

Puede existir más adelante:

```text
Repetir exactamente
```

o:

```text
Generar una variante de esta clase
```

La segunda opción mantiene las mismas skills pero cambia frases y situaciones.

---

## 14.1 Dashboard vs. historial detallado

El dashboard no necesita mostrar cada pregunta.

El historial sí puede conservar:

- ejercicio;
- respuesta;
- evaluación;
- feedback;
- intento;
- fecha.

El dashboard trabaja sobre datos agregados.

---

# 15. Listening

Listening se considera relativamente simple desde la arquitectura.

La IA puede generar:

```text
texto
```

Luego un sistema Text-to-Speech lo reproduce.

No es necesario almacenar permanentemente el archivo de audio.

Se puede guardar:

```text
texto original
idioma
voz
velocidad
otros parámetros de reproducción
```

Y regenerar el audio cuando sea necesario.

Eso reduce almacenamiento.

---

## 15.1 Ejemplo

La IA genera:

```text
“Sarah usually takes the bus to work, but today she is walking.”
```

La pantalla no necesariamente muestra el texto.

Lo reproduce.

El usuario responde preguntas.

Al rehacer la clase:

```text
texto guardado
        ↓
TTS
        ↓
audio regenerado
```

---

# 16. Speaking

Para speaking el flujo cambia.

```text
Usuario habla al micrófono
        ↓
frontend captura audio
        ↓
backend / servicio procesa audio
        ↓
Speech-to-Text
        ↓
transcripción
        ↓
IA evalúa contenido lingüístico
```

La transcripción permite evaluar:

- gramática;
- vocabulario;
- estructura;
- adecuación a la consigna;
- fluidez textual aproximada.

Pero hay una diferencia importante:

> Speech-to-Text permite saber qué entendió el sistema que dijo el usuario. No alcanza para evaluar correctamente la pronunciación.

---

# 17. Pronunciación / fonética

Para pronunciación se necesita una capa adicional especializada.

El audio puede enviarse a un motor capaz de analizar:

- pronunciación;
- precisión;
- fluidez;
- palabras problemáticas;
- fonemas;
- ritmo;
- eventualmente entonación.

Ejemplo:

```text
Contenido: correcto
Pronunciación: 74 %
Problema detectado: /θ/
Palabra problemática: think
```

---

## 17.1 Política de almacenamiento de audio

No se quiere almacenar audio permanentemente por defecto.

Flujo esperado:

```text
audio temporal
       ↓
Speech-to-Text / pronunciation assessment
       ↓
guardar resultado
       ↓
descartar audio
```

Persistir:

```text
transcripción
scores
errores fonéticos
palabras problemáticas
feedback
```

No persistir normalmente:

```text
archivo WAV / MP3 original
```

Esto reduce:

- almacenamiento;
- complejidad;
- exposición de información sensible.

---

# 18. Dashboard

El dashboard debe ser uno de los componentes centrales.

Debe responder rápidamente:

```text
¿En qué estoy bien?
¿En qué estoy flojo?
¿Qué estoy practicando?
¿Qué debería practicar?
¿Estoy mejorando?
¿Qué tengo pendiente?
```

---

## 18.1 Ejemplo de estructura

```text
A1

Grammar                        81 %
├── Present Simple             78 %
│   ├── Affirmative            94 %
│   ├── Negative               81 %
│   ├── Questions do/does      62 %
│   └── Third person singular  55 %
│
├── To Be                      91 %
└── Present Continuous         73 %

Vocabulary                     84 %
Reading                        88 %
Writing                        71 %
Listening                      59 %
Speaking                       52 %
Pronunciation                  64 %
```

---

## 18.2 Adaptación automática

Si el sistema detecta:

```text
Reading     91 %
Grammar     87 %
Listening   51 %
Speaking    47 %
```

las clases siguientes deberían aumentar el peso de:

```text
Listening
Speaking
```

No significa abandonar por completo las demás skills.

Significa balancear el aprendizaje.

---

# 19. Estados de una clase o sesión

Esto surgió a partir de la necesidad de saber qué dejó pendiente el usuario.

Estados mínimos sugeridos:

```text
NEW
IN_PROGRESS
AWAITING_EVALUATION
COMPLETED
```

Podrían agregarse:

```text
EVALUATING
EVALUATION_FAILED
CANCELLED
```

pero el conjunto exacto deberá definirse.

---

## 19.1 Ejemplos visibles

Pantalla principal:

```text
Clase 32
A1 · Present Simple
65 % completada
Estado: En progreso
```

Otra:

```text
Clase 31
A1 · Mixed Skills
Estado: Esperando corrección
```

Otra:

```text
Clase 30
Completada
82 %
```

---

# 20. Autoguardado y recuperación

La clase debe autoguardarse.

El usuario no debería depender de presionar:

```text
Guardar
```

para no perder trabajo.

Ejemplo:

```text
usuario responde ejercicio 1
→ autosave

usuario responde ejercicio 2
→ autosave

usuario cierra navegador
→ respuestas siguen guardadas
```

Al volver:

```text
Continuar clase
```

---

# 21. Pantalla inicial y navegación

Antes del login debe existir una página que explique brevemente el producto.

No hay todavía una estética decidida.

Debe comunicar ideas como:

- aprendizaje dinámico;
- clases únicas;
- adaptación al nivel;
- práctica de distintas habilidades;
- seguimiento del progreso;
- IA como apoyo.

No se quiere construir de entrada una landing comercial compleja.

---

## 21.1 Después del login

La pantalla principal debería mostrar al menos:

```text
Nivel operativo actual
Progreso
Clases pendientes
Clases esperando corrección
Últimas clases
Botón Nueva clase
Dashboard
Estado general de IA
Configuración
```

---

# 22. Login y usuarios

Se propuso utilizar Google para evitar construir un sistema completo de autenticación desde cero.

Por lo tanto:

```text
Login with Google
```

Cada usuario tendrá información propia:

- perfil;
- nivel;
- historial;
- dashboard;
- clases;
- intentos;
- agentes configurados;
- prioridades;
- configuraciones.

La posibilidad de comercializar el producto en el futuro hace importante que el diseño sea multiusuario desde el principio.

---

# 23. Configuración de agentes / proveedores de IA

Cada usuario debe poder configurar **N conexiones de IA**.

No limitar a una sola.

Ejemplo:

```text
1. OpenAI principal
2. Gemini
3. OpenAI secundaria
```

Incluso puede haber dos conexiones del mismo proveedor usando credenciales diferentes.

---

## 23.1 Motivo

Si una conexión:

- agota cuota;
- llega a un límite;
- falla;
- está temporalmente indisponible;

la aplicación puede continuar usando otra.

---

## 23.2 Concepto de conexión

Conviene considerar como unidad lógica:

```text
AI_CONNECTION
```

que puede contener:

```text
provider
credential
model
priority
enabled
status
lastCheck
lastError
```

El usuario podrá:

- agregar;
- eliminar;
- activar/desactivar;
- ordenar prioridades;
- configurar modelo;
- probar conexión.

---

# 24. Prioridad, agente activo y failover

Deben existir dos conceptos separados:

```text
PRIORITY ORDER
ACTIVE CONNECTION
```

Ejemplo:

```text
Prioridad:
1. OpenAI A
2. Gemini
3. OpenAI B

Activo:
Gemini
```

El activo no tiene que ser permanentemente el número 1.

Puede haber llegado a Gemini porque OpenAI A falló.

---

# 25. Ciclo de disponibilidad de agentes

## 25.1 Al entrar a la aplicación

Supongamos que el usuario tiene:

```text
1. Agente A
2. Agente B
3. Agente C
```

Después de tres días vuelve a entrar.

El sistema comienza por el primero según prioridad.

```text
check A
```

Si A responde correctamente:

```text
ACTIVE = A
```

Y no hace falta consultar B y C en ese momento.

---

## 25.2 Si el activo falla durante una operación

Supongamos:

```text
ACTIVE = A
```

Se solicita:

```text
corregir clase
```

A devuelve error de cuota.

Entonces:

```text
A → marcado como no disponible en esta vuelta
B → comprobar / intentar
```

Si B funciona:

```text
ACTIVE = B
```

La operación continúa.

---

## 25.3 Failover circular

Supongamos ahora:

```text
ACTIVE = C
```

C falla.

El siguiente ciclo puede volver al comienzo:

```text
A
B
```

sin insistir inmediatamente otra vez con C.

El recorrido conceptual es circular.

---

## 25.4 Regla de estabilidad

Mientras un agente funciona:

```text
seguir usándolo
```

No cambiar de proveedor innecesariamente en cada request.

Esto aporta:

- menor complejidad;
- mejor trazabilidad;
- menos diferencias entre respuestas;
- menos health checks.

---

# 26. Health check / “ping” de agentes

El concepto de “ping” no significa necesariamente un ICMP ping.

Se necesita comprobar:

```text
¿esta conexión puede atender una operación?
```

Dependiendo del proveedor se puede usar:

- endpoint de estado o modelos;
- llamada mínima;
- request de muy bajo costo;
- operación equivalente soportada por la API.

---

## 26.1 Estados internos posibles

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

La UI no necesita mostrar toda esta complejidad, pero el backend sí debería distinguirla.

---

## 26.2 Importante: no todos los proveedores permiten consultar “cuánta cuota queda”

En algunos casos la única forma confiable de saber si una credencial puede operar será:

```text
realizar una operación mínima
```

Por eso el sistema no debe asumir que existe universalmente:

```text
GET /quota
```

La implementación deberá adaptarse a cada proveedor mediante un adapter.

---

## 26.3 Cuándo ejecutar health checks

Momentos definidos durante la conversación:

### Al agregar una conexión

```text
Usuario guarda API key
        ↓
test inmediato
```

### Al iniciar la aplicación

Probar la conexión de mayor prioridad.

### Cuando una operación falla

Iniciar failover.

### Cuando todas fallaron

Activar reintentos periódicos.

---

# 27. Qué ocurre si todos los agentes quedan sin disponibilidad

Este escenario se consideró explícitamente.

Ejemplo:

```text
Usuario termina una clase
        ↓
presiona Finalizar / Comprobar
        ↓
Agente A falla
Agente B falla
Agente C falla
```

Resultado:

**NO se pierde la clase.**

Antes de evaluar:

```text
guardar respuestas
```

Luego:

```text
class.status = AWAITING_EVALUATION
```

El usuario puede cerrar la aplicación.

---

## 27.1 Pantalla principal

Debe aparecer claramente:

```text
1 clase pendiente de corrección
```

No ocultar la situación.

También puede mostrarse:

```text
No hay conexiones de IA disponibles actualmente.
```

---

## 27.2 Cuando vuelva una conexión

El sistema podrá retomar automáticamente:

```text
clase pendiente
       ↓
agente disponible
       ↓
corregir
       ↓
guardar resultado
       ↓
COMPLETED
```

El usuario no necesita rehacer nada.

---

# 28. Reintentos automáticos y backoff

Si ninguna conexión funciona, no conviene probar constantemente.

Se planteó un esquema progresivo.

Ejemplo conceptual:

```text
1 minuto
5 minutos
15 minutos
1 hora
luego intervalos mayores/configurables
```

Los valores finales todavía pueden ajustarse.

La idea importante es:

```text
BACKOFF
```

No bombardear APIs.

---

## 28.1 Reinicio del ciclo

Si aparece una conexión nueva:

```text
test inmediato
```

Si el usuario vuelve a abrir la aplicación:

```text
nuevo chequeo
```

Si un health check periódico encuentra disponibilidad:

```text
detener estado NO_AI_AVAILABLE
```

y comenzar a procesar pendientes.

---

# 29. Cambio de agente sin molestar al usuario

Se decidió evitar modales de confirmación innecesarios.

Ejemplo:

```text
OpenAI → agotó cuota
Gemini → disponible
```

La aplicación cambia automáticamente.

Puede mostrar:

```text
Se cambió automáticamente el proveedor de IA.
```

pero como:

- toast;
- banner;
- mensaje pequeño;
- estado visible.

**No como ventana bloqueante con botón OK.**

---

## 29.1 Cuándo sí puede ser necesaria una acción visible

Si:

```text
todos los agentes fallaron
```

y una acción no puede completarse, la aplicación debe explicarlo claramente.

Aun así, conviene preferir una interfaz no intrusiva cuando sea posible.

---

# 30. Independencia entre la clase y el proveedor de IA

Esta es una de las decisiones arquitectónicas más importantes.

Ejemplo:

```text
OpenAI genera clase
```

La clase se guarda en nuestro formato.

Más tarde:

```text
OpenAI falla
Gemini corrige
```

Gemini debe recibir:

- contenido completo;
- objetivos;
- respuestas;
- criterios.

No necesita conocer una conversación previa con OpenAI.

Esto evita dependencia del contexto interno de un proveedor.

---

# 31. Formato estructurado de intercambio con la IA

No se quiere depender de texto libre para procesos internos.

Generación y corrección deben devolver estructuras validadas.

Preferentemente:

```text
JSON
```

---

## 31.1 Beneficios

- guardar fácilmente;
- validar;
- cambiar proveedor;
- construir dashboard;
- auditar;
- reintentar;
- comparar resultados;
- evitar parsing frágil.

---

# 32. Modelo conceptual de datos

No es diseño definitivo de base de datos.

Es una guía funcional.

---

## 32.1 USER

```text
id
google_subject
email
display_name
created_at
```

---

## 32.2 USER_PROFILE

```text
user_id
selected_level
estimated_level
operational_level
```

---

## 32.3 AI_CONNECTION

```text
id
user_id
provider
model
encrypted_credential
priority
enabled
status
last_check_at
last_error_code
last_error_at
```

---

## 32.4 CURRICULUM_LEVEL

```text
id
code
name
order
```

Ejemplo:

```text
A1
A2
B1
B2
C1
C2
```

---

## 32.5 SKILL

```text
id
level
area
topic
subtopic
objective
```

---

## 32.6 CLASS_SESSION

```text
id
user_id
target_level
status
created_at
started_at
submitted_at
evaluated_at
generated_by_connection
```

---

## 32.7 EXERCISE

```text
id
class_session_id
type
level
area
topic
skill
instruction
content
expected_concepts
generation_metadata
```

---

## 32.8 USER_ANSWER

```text
id
exercise_id
user_id
answer_text
transcript
created_at
updated_at
```

---

## 32.9 ATTEMPT

Permite repetir ejercicios o clases.

```text
id
exercise_id
user_id
attempt_number
submitted_answer
overall_score
result
created_at
```

---

## 32.10 ATTEMPT_CONCEPT

```text
attempt_id
skill
status
score
```

---

## 32.11 ATTEMPT_ERROR

```text
attempt_id
error_type
fragment
correction
explanation
severity
```

---

## 32.12 USER_SKILL_PROGRESS

Tabla derivada o materializada para dashboard.

```text
user_id
skill
score
attempt_count
confidence
status
trend
last_practiced_at
```

---

# 33. Ejemplo de generación de ejercicio

Solicitud conceptual:

```text
Generá un ejercicio de inglés.

Nivel: A1
Categoría: Grammar
Tema: Present Simple
Subtema: Questions with do/does
Dificultad: básica

Condiciones:
- usar solo estructuras compatibles con A1;
- evaluar do/does;
- evaluar verbo base después de does;
- generar una única pregunta;
- devolver JSON válido.
```

Respuesta posible:

```json
{
  "level": "A1",
  "category": "grammar",
  "topic": "present_simple",
  "skill": "questions_do_does",
  "instruction": "Complete the question",
  "question": "___ she work on Saturdays?",
  "expectedConcepts": [
    "does",
    "base_verb_after_does"
  ]
}
```

El backend valida y persiste.

---

# 34. Ejemplo de evaluación de respuesta

Respuesta del usuario:

```text
Does she works on Saturdays?
```

Solicitud conceptual:

```text
Evaluá la respuesta del alumno.

Nivel: A1

Ejercicio:
___ she work on Saturdays?

Objetivos:
- uso de does
- verbo base después de does

Respuesta:
Does she works on Saturdays?

Separá errores reales de sugerencias de estilo.
Devolvé JSON.
```

Respuesta posible:

```json
{
  "result": "partially_correct",
  "scoreSuggested": 70,
  "conceptResults": [
    {
      "concept": "does",
      "status": "correct",
      "score": 100
    },
    {
      "concept": "base_verb_after_does",
      "status": "incorrect",
      "score": 0
    }
  ],
  "errors": [
    {
      "type": "GRAMMAR_ERROR",
      "fragment": "works",
      "correction": "work",
      "explanation": "After 'does', use the base form of the verb."
    }
  ],
  "correctAnswer": "Does she work on Saturdays?",
  "feedback": "You used 'does' correctly. After 'does', use the base form of the verb.",
  "suggestions": []
}
```

El backend aplica su propia regla de scoring sobre estos resultados.

---

# 35. Reglas funcionales importantes

1. Una respuesta gramaticalmente correcta no debe marcarse incorrecta solo porque exista otra opción más natural.

2. Una sugerencia de estilo no debe tratarse automáticamente como error.

3. Una única mala clase no debe bajar de nivel al usuario.

4. Un único buen ejercicio no debe promoverlo.

5. La cantidad de evidencia importa.

6. Una debilidad puntual no equivale necesariamente a un nivel general bajo.

7. La aplicación debe poder bajar automáticamente el nivel operativo si existe evidencia transversal suficiente.

8. La aplicación también debe poder subir rápidamente a alguien que demuestra dominio.

9. Los ejercicios de niveles superiores pueden reutilizar conceptos básicos con mayor profundidad.

10. Todo ejercicio generado debe persistirse antes de depender de futuras llamadas al proveedor.

11. Toda respuesta debe persistirse antes de iniciar corrección.

12. Los cambios de proveedor no deben romper una clase.

13. El usuario no debe tener que confirmar un failover automático.

14. Si no queda ninguna conexión disponible, el trabajo queda guardado.

15. El dashboard debe mostrar pendientes claramente.

16. No guardar audio permanentemente por defecto.

17. El contenido del dashboard debe construirse desde datos estructurados, no desde una nueva interpretación libre de la IA cada vez que se abre.

---

# 36. Requisitos de seguridad para API keys

Aunque durante la conversación el foco estuvo en funcionalidad, este punto es necesario para la implementación.

Las API keys de usuarios:

- no deben guardarse en texto plano;
- no deben enviarse nuevamente al frontend;
- no deben aparecer en logs;
- deberían cifrarse en reposo;
- las llamadas a proveedores deberían realizarse desde el backend.

El frontend puede mostrar:

```text
OpenAI principal
••••••••••9F2A
```

pero nunca devolver la credencial completa.

---

# 37. Arquitectura técnica tentativa

La idea planteada fue:

```text
Frontend
Angular
```

y:

```text
Backend
Python
```

Arquitectura lógica:

```text
Angular
   ↓
REST API
   ↓
Python Backend
   ├── Auth
   ├── Curriculum Engine
   ├── Learning Engine
   ├── AI Provider Router
   ├── Evaluation Engine
   ├── TTS/STT Integration
   └── Persistence
          ↓
       Database
```

---

## 37.1 AI Provider Router

Responsabilidades:

```text
getActiveConnection(user)
healthCheck(connection)
execute(request)
failover()
backoff()
```

Cada proveedor debe estar detrás de una interfaz común.

Conceptualmente:

```text
AIProviderAdapter
├── OpenAIAdapter
├── GeminiAdapter
└── ... futuros
```

Esto es necesario porque no todas las APIs funcionan de la misma manera.

---

# 38. Escalabilidad

La escalabilidad se logra principalmente evitando esta estructura:

```text
if level == A1:
   ...
elif level == A2:
   ...
elif level == B1:
   ...
```

El motor debería consumir configuración.

Ejemplo:

```json
{
  "level": "A1",
  "topic": "present_simple",
  "skills": [
    "affirmative",
    "negative",
    "questions_do_does",
    "third_person_singular"
  ]
}
```

Agregar B1 debería significar principalmente:

```text
agregar datos
```

no:

```text
reescribir motor
```

---

# 39. MVP propuesto

Para no intentar construir todo desde el día uno, un MVP razonable puede ser:

## Etapa 1

- login Google;
- perfil de usuario;
- A1;
- generación de clases;
- ejercicios de texto;
- corrección con IA;
- JSON estructurado;
- guardar clases;
- guardar respuestas;
- historial;
- dashboard básico;
- un proveedor de IA inicialmente.

## Etapa 2

- múltiples proveedores;
- prioridad;
- failover;
- estados de disponibilidad;
- pendientes de corrección;
- backoff.

## Etapa 3

- diagnóstico adaptativo;
- promoción / descenso;
- confidence score;
- recomendaciones automáticas.

## Etapa 4

- listening;
- Text-to-Speech.

## Etapa 5

- speaking;
- Speech-to-Text.

## Etapa 6

- pronunciation assessment.

## Etapa 7

- ampliar currícula:
  - A2;
  - B1;
  - B2;
  - C1;
  - C2.

El orden exacto podrá cambiar.

---

# 40. Evoluciones futuras

Se mencionó que, si el resultado es bueno, podría llegar a comercializarse.

Por eso la base debe permitir:

- múltiples usuarios;
- múltiples proveedores;
- crecimiento de currícula;
- nuevas modalidades;
- métricas;
- posibles planes;
- límites;
- eventualmente cuentas administradas por la plataforma en vez de BYOK;
- nuevos idiomas en el futuro si se quisiera.

Nada de esto es requisito inmediato.

---

# 41. Decisiones ya tomadas

Estas son ideas que en la conversación quedaron bastante consolidadas.

## Producto

- usar CEFR/MCER;
- niveles A1, A2, B1, B2, C1, C2;
- currícula propia;
- IA subordinada a la currícula;
- clases dinámicas;
- seguimiento por usuario.

## Evaluación

- evaluación estructurada;
- no limitarse a bien/mal;
- separar error de sugerencia;
- guardar resultados por skill;
- dashboard calculado desde esos datos.

## Progreso

- score + intentos + confianza;
- promoción adaptativa;
- descenso basado en evidencia;
- debilidades por habilidad.

## Clases

- persistentes;
- autoguardadas;
- repetibles;
- comparables entre intentos;
- independientes del proveedor.

## Audio

- listening regenerable desde texto;
- speaking mediante STT;
- pronunciación mediante servicio específico;
- no guardar audio original por defecto.

## Agentes IA

- múltiples conexiones por usuario;
- prioridad;
- uno activo;
- failover automático;
- notificación no bloqueante;
- backoff si ninguno funciona.

## Interfaz

- login Google;
- landing explicativa antes del login;
- dashboard;
- estado de clases;
- pendientes visibles;
- evitar modales de confirmación innecesarios.

---

# 42. Preguntas todavía abiertas

No todo está cerrado.

Temas a definir más adelante:

### Currícula

- definición exacta de A1;
- definición exacta de A2;
- definición exacta de B1;
- definición exacta de B2;
- definición exacta de C1;
- definición exacta de C2.

### Scoring

- fórmula exacta;
- pesos por error;
- cálculo de confianza;
- cantidad mínima de evidencia;
- umbral de promoción;
- umbral de descenso.

### Diagnóstico

- longitud;
- áreas incluidas;
- algoritmo adaptativo.

### Clases

- cantidad de ejercicios;
- mezcla de modalidades;
- duración objetivo;
- corrección por ejercicio o por clase completa.

### Audio

- proveedor TTS;
- proveedor STT;
- motor de pronunciation assessment.

### IA

- proveedores soportados inicialmente;
- modelos recomendados;
- estrategia de Structured Outputs de cada proveedor;
- costos mínimos de health checks.

### Frontend

- estética;
- layout;
- componentes exactos;
- versión mobile.

### Comercialización

- fuera de alcance por ahora.

---

# 43. Storytime completo del usuario

Este apartado expresa el flujo deseado desde la perspectiva de uso.

---

## 43.1 Primera entrada

Roberto entra a la aplicación.

Ve una página introductoria que explica:

```text
Aprendé inglés con clases dinámicas.
La app adapta los ejercicios a tu nivel.
Tus errores construyen un mapa de progreso.
Podés practicar lectura, escritura, escucha y habla.
```

Presiona:

```text
Continuar con Google
```

Se crea su usuario.

---

## 43.2 Selección inicial

Como no tiene historial, aparecen dos opciones:

```text
Hacer diagnóstico
Elegir mi nivel
```

Roberto puede hacer el diagnóstico.

O puede decir:

```text
Quiero comenzar en A1
```

También podría ser aventurero y seleccionar:

```text
C1
```

El sistema se lo permite.

---

## 43.3 Configuración de IA

Roberto entra a configuración.

Carga:

```text
1. OpenAI
2. Gemini
3. Otra conexión OpenAI
```

Asigna prioridades:

```text
1
2
3
```

El sistema prueba las credenciales.

Una queda activa.

---

## 43.4 Nueva clase

Roberto presiona:

```text
Nueva clase
```

El sistema observa:

```text
nivel operativo
historial
debilidades
confidence
últimas skills practicadas
```

Decide, por ejemplo:

```text
A1
Present Simple
Writing
Listening
```

Construye un pedido estructurado.

La IA genera una clase única.

La clase se guarda.

---

## 43.5 Resolución

Roberto comienza.

Responde ejercicios.

Cada respuesta se autoguarda.

Si cierra la pestaña accidentalmente:

```text
IN_PROGRESS
```

Al volver puede continuar.

---

## 43.6 Listening

Una parte contiene un texto generado por IA.

La aplicación lo reproduce con TTS.

Roberto escucha.

Responde preguntas.

Solo se necesita guardar el texto y configuración de reproducción.

---

## 43.7 Speaking

En otro ejercicio debe hablar.

El navegador captura audio temporal.

Se transcribe.

La IA evalúa el contenido.

Un motor específico puede evaluar pronunciación.

El audio se descarta.

Se guardan:

```text
transcripción
evaluación
pronunciation score
errores
```

---

## 43.8 Finalizar

Roberto presiona:

```text
Finalizar y comprobar
```

Primero:

```text
guardar absolutamente todas las respuestas
```

Después:

```text
solicitar corrección
```

---

## 43.9 Corrección

La IA devuelve:

```text
resultado general
conceptos correctos
conceptos incorrectos
errores
explicaciones
sugerencias de naturalidad
```

El backend guarda todo.

El dashboard actualiza.

---

## 43.10 El proveedor muere en ese momento

Supongamos que la clase había sido generada por:

```text
OpenAI A
```

Pero al corregir:

```text
quota exceeded
```

El sistema no muestra modal.

Prueba:

```text
Gemini
```

Si funciona:

```text
ACTIVE = Gemini
```

Gemini recibe la clase guardada y la corrige.

Roberto puede ver un pequeño aviso:

```text
Se cambió el proveedor de IA automáticamente.
```

No tiene que hacer nada.

---

## 43.11 Todos los proveedores fallan

Supongamos:

```text
OpenAI A → sin cuota
Gemini    → sin cuota
OpenAI B  → sin cuota
```

Como las respuestas ya estaban guardadas:

```text
AWAITING_EVALUATION
```

La aplicación informa:

```text
Tus respuestas están guardadas.
La corrección está pendiente porque no hay conexiones de IA disponibles.
```

Roberto puede salir.

La pantalla principal muestra:

```text
1 clase pendiente de corrección
```

---

## 43.12 Recuperación

El backend aplica backoff.

Más tarde:

```text
health check OpenAI A
→ sigue caído

health check Gemini
→ disponible
```

La aplicación puede reanudar la corrección.

Cuando termina:

```text
COMPLETED
```

El dashboard se actualiza.

---

## 43.13 Próxima clase

Supongamos que el dashboard muestra:

```text
Grammar       86 %
Reading       89 %
Listening     48 %
Speaking      44 %
```

El motor adapta la siguiente clase.

Aumenta la presencia de:

```text
Listening
Speaking
```

---

## 43.14 Evolución de nivel

Después de varias clases:

```text
A1 dominado con alta confianza
```

El sistema introduce pruebas A2.

Si Roberto responde bien:

```text
operational_level = A2
```

---

## 43.15 Caso inverso

Roberto había elegido manualmente:

```text
C1
```

pero durante varias clases falla transversalmente en:

```text
Reading
Listening
Writing
Grammar
```

La aplicación acumula evidencia.

Finalmente decide:

```text
C1 → B2
```

No porque “una clase salió mal”, sino porque existe suficiente señal.

Si hace falta:

```text
B2 → B1
```

---

## 43.16 Repetición

Un mes más tarde Roberto abre:

```text
Historial
```

Ve una clase donde había obtenido:

```text
58 %
```

Selecciona:

```text
Rehacer
```

Completa nuevamente.

Resultado:

```text
Intento 1: 58 %
Intento 2: 84 %
```

La mejora también puede alimentar el dashboard.

---

# 44. Prompt maestro para retomar el proyecto en otro chat

Copiar este bloque en un nuevo chat si se pierde el contexto.

---

## PROMPT DE CONTINUIDAD

Estoy diseñando una aplicación web de aprendizaje de inglés asistida por IA.

Quiero que tomes las siguientes decisiones como contexto ya establecido y NO reinicies el diseño desde cero.

### Objetivo

Crear una aplicación de aprendizaje adaptativo de inglés con niveles CEFR:

```text
A1, A2, B1, B2, C1, C2
```

La aplicación define la currícula. La IA NO decide qué corresponde a cada nivel.

Los niveles, temas, skills y objetivos deben ser datos parametrizables para poder agregar niveles sin reescribir el motor.

### Stack tentativo

```text
Frontend: Angular
Backend: Python
```

La arquitectura es cliente-servidor.

### Usuarios

Login inicialmente con Google.

Cada usuario tiene:

- perfil;
- nivel seleccionado;
- nivel estimado;
- nivel operativo;
- progreso;
- historial;
- clases;
- intentos;
- conexiones de IA.

### Diagnóstico y nivel

En la primera entrada el usuario puede:

1. realizar un diagnóstico adaptativo;
2. elegir manualmente un nivel.

Nunca forzar a todos a empezar en A1.

El sistema puede promover o bajar automáticamente el nivel operativo, pero solo con evidencia suficiente.

Una mala clase no baja el nivel.

Un buen ejercicio no lo sube.

Debe considerarse evidencia transversal y confianza estadística.

### Mapa de habilidades

No existe solo un nivel global.

Registrar progreso por:

```text
Grammar
Vocabulary
Reading
Writing
Listening
Speaking
Pronunciation
```

y por skills más específicas.

Cada skill debe poder tener:

```text
score
attemptCount
confidence
status
trend
```

Estados considerados:

```text
LEARNING
MASTERED
NEEDS_REVIEW
```

### Generación

La aplicación determina:

```text
nivel
área
tema
skill
objetivos
dificultad
modalidad
```

y se lo envía a la IA.

La IA genera ejercicios dinámicos en formato estructurado JSON.

Dos usuarios pueden recibir frases diferentes aunque practiquen el mismo objetivo.

### Corrección

La IA recibe:

- ejercicio original;
- nivel;
- objetivos;
- respuesta.

Devuelve JSON estructurado con:

```text
result
conceptResults
errors
correctAnswer
feedback
suggestions
```

No guardar solo correcto/incorrecto.

Guardar qué concepto estuvo bien y cuál mal.

El backend tiene la última palabra sobre el scoring.

### Corrección vs. sugerencias

Separar:

```text
GRAMMAR_ERROR
VOCABULARY_ERROR
SPELLING_ERROR
WORD_ORDER_ERROR
PRONUNCIATION_ERROR
```

de:

```text
STYLE_SUGGESTION
NATURALNESS_SUGGESTION
SHORTER_ALTERNATIVE
```

Una frase correcta no debe perder puntos solamente porque podría sonar más natural.

### Clases

Una clase contiene varios ejercicios.

Se guarda antes de mostrarse.

El usuario responde y existe autoguardado.

Al finalizar:

1. guardar respuestas;
2. luego intentar evaluación.

Estados mínimos:

```text
NEW
IN_PROGRESS
AWAITING_EVALUATION
COMPLETED
```

La pantalla principal debe mostrar clases:

- pendientes;
- en progreso;
- pendientes de corrección;
- completadas.

### Historial

Guardar clases completas e intentos.

Permitir:

```text
Rehacer clase
```

y comparar:

```text
Intento 1
Intento 2
...
```

También puede existir en el futuro:

```text
Generar variante
```

con las mismas skills.

### Dashboard

No mostrar solamente una nota global.

Mostrar progreso por nivel / área / skill.

Ejemplo:

```text
A1
Present Simple
- affirmative
- negative
- questions do/does
- third person singular
```

Usar score + intentos + confidence.

Las clases futuras deben priorizar debilidades.

### Listening

IA genera texto.

TTS reproduce.

Guardar:

```text
texto
voz
velocidad
```

No es necesario persistir el audio generado.

### Speaking

Capturar audio temporal.

Speech-to-Text produce transcripción.

Evaluar contenido desde la transcripción.

### Pronunciación

STT no alcanza para evaluar fonética.

Usar un servicio específico de pronunciation assessment.

Guardar:

```text
scores
palabras problemáticas
errores fonéticos
feedback
transcripción
```

No guardar audio original permanentemente por defecto.

### Proveedores de IA

Cada usuario puede configurar N conexiones.

Puede haber varias del mismo proveedor.

Ejemplo:

```text
1. OpenAI principal
2. Gemini
3. OpenAI secundaria
```

Cada conexión tiene prioridad.

Existe una sola conexión ACTIVE en un momento dado.

La clase pertenece a nuestra aplicación, NO al proveedor.

Una clase puede ser generada por un proveedor y corregida por otro.

### Failover

Al entrar a la app:

```text
comprobar primero en prioridad
si funciona → ACTIVE
no hace falta comprobar el resto
```

Cuando el ACTIVE falla:

```text
ir al siguiente
```

El recorrido es circular.

No volver inmediatamente a un proveedor que falló en la misma vuelta.

Cuando uno funciona:

```text
ACTIVE = ese proveedor
```

y se mantiene hasta que falle.

### Cambio automático

No utilizar modal con botón OK cuando ocurre failover.

Mostrar, como máximo:

- toast;
- banner;
- aviso pequeño.

La continuidad debe ser automática.

### Health check

Cada proveedor debe implementar una forma ligera de comprobar disponibilidad.

Estados internos posibles:

```text
AVAILABLE
QUOTA_EXCEEDED
RATE_LIMITED
INVALID_CREDENTIALS
PROVIDER_DOWN
NETWORK_ERROR
UNKNOWN_ERROR
```

No asumir que todos los proveedores permiten consultar cuota directamente.

Puede ser necesario realizar una llamada mínima.

### Sin agentes disponibles

Si todos fallan:

```text
AWAITING_EVALUATION
```

Nunca perder respuestas.

Mostrar el pendiente en el home.

Activar reintentos automáticos con backoff.

Esquema conceptual discutido:

```text
1 min
5 min
15 min
1 h
...
```

Si el usuario agrega una nueva conexión:

```text
health check inmediato
```

Si vuelve a entrar a la app:

```text
nuevo chequeo
```

Cuando vuelve un proveedor, procesar pendientes.

### Seguridad

Las API keys:

- cifradas;
- nunca en logs;
- nunca devueltas completas al frontend;
- llamadas a proveedores desde backend.

### Idea central

La arquitectura debe ser escalable.

Agregar A2, B1, etc. debe ser fundamentalmente agregar configuración/currícula, no reescribir la aplicación.

El motor de aprendizaje, generación, evaluación, dashboard y routing de IA debe ser genérico.

Continuá el diseño a partir de este punto y preservá estas decisiones salvo que encontremos una razón concreta para modificarlas.

---

# Fin del documento

Este documento debe considerarse la memoria funcional actual del proyecto.

Antes de modificar una decisión importante, conviene verificar si contradice alguno de los principios anteriores.
