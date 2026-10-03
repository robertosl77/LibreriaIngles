# Librería Inglés — Guía de desarrollo local del frontend

**Objetivo:** documentar cómo preparar y levantar el frontend Angular durante el desarrollo.

Esta guía refleja el flujo probado en Windows con Visual Studio Code.

---

# 1. Requisitos

Para el frontend se necesita:

- Node.js **22.12 o superior** (o 20.19+ / 24+; lo exige Angular 21);
- npm;
- Git;
- Visual Studio Code.

Verificar las instalaciones:

```powershell
node --version
npm --version
```

El proyecto utiliza actualmente **Angular 21** (actualizado desde 19 en T-002: Angular 19 dejó de
recibir parches de seguridad). Builder: `@angular/build` (esbuild); `npm audit` en 0.

Tras actualizar el repo, reinstalar dependencias en el frontend: `npm ci`.

---

# 2. Preparación inicial

Desde la raíz del repositorio:

```powershell
cd frontend
```

La terminal debería quedar ubicada en una ruta similar a:

```text
...\LibreriaIngles\frontend>
```

El entorno virtual de Python del backend no es necesario para ejecutar Angular. Si la terminal muestra `(.venv)`, no impide ejecutar el frontend, pero no es requerido.

---

# 3. Instalar dependencias

La primera vez, o cuando cambie `package.json`, ejecutar:

```powershell
npm install
```

Esto instala las dependencias del frontend dentro de:

```text
frontend/node_modules/
```

La carpeta `node_modules` no se versiona en Git.

---

# 4. Iniciar el frontend

Desde `frontend/`:

```powershell
npm start
```

No es necesario ejecutar `ng serve` manualmente.

El script definido en `package.json` es:

```json
"start": "ng serve"
```

Por lo tanto:

```text
npm start
    ↓
ng serve
```

---

# 5. Pregunta de Analytics de Angular

En la primera ejecución Angular puede mostrar:

```text
Would you like to share pseudonymous usage data about this project with the Angular Team
at Google ... ? (y/N)
```

Para este proyecto responder:

```text
N
```

o seleccionar:

```text
No
```

Esto desactiva el envío de métricas de uso del proyecto y no afecta su funcionamiento.

Una salida correcta puede mostrar:

```text
Global setting: enabled
Local setting: disabled
Effective status: disabled
```

El proyecto ya tiene actualmente configurado:

```json
"cli": {
  "analytics": false
}
```

en `angular.json`.

---

# 6. Confirmar que Angular inició correctamente

Una ejecución correcta de:

```powershell
npm start
```

muestra una salida similar a:

```text
Application bundle generation complete.

Watch mode enabled. Watching for file changes...

Local: http://localhost:4200/
```

El frontend queda disponible en:

```text
http://localhost:4200
```

Mientras el proceso siga activo, Angular queda en modo watch y recompila automáticamente cuando detecta cambios en los archivos.

Para detenerlo:

```text
Ctrl + C
```

---

# 7. Qué debería verse

Al abrir:

```text
http://localhost:4200
```

debe mostrarse la landing de **Librería Inglés**, con elementos como:

- Librería Inglés;
- Iniciar sesión;
- Aprendizaje adaptativo de inglés;
- Tu curso cambia con vos.

Si la página carga esos elementos, el frontend está funcionando correctamente.

---

# 8. Backend y frontend

Durante el desarrollo pueden ejecutarse simultáneamente:

```text
Backend  → http://127.0.0.1:8000
Frontend → http://localhost:4200
```

Para la landing actual el frontend puede renderizarse sin consumir todavía la API.

Cuando se incorporen llamadas al backend, ambos procesos deberán estar levantados para probar el flujo completo.

---

# 9. Build manual

Para generar un build del frontend:

```powershell
npm run build
```

Angular genera la salida en:

```text
frontend/dist/libreria-ingles/
```

según la configuración actual de `angular.json`.

Para desarrollo normal se utiliza:

```powershell
npm start
```

---

# 10. Problemas encontrados durante la preparación inicial

## 10.1 Falta `outputPath`

Durante el primer arranque apareció:

```text
Error: Schema validation failed with the following errors:
Data path "" must have required property 'outputPath'.
```

La causa era que `frontend/angular.json` no tenía definido el destino del build.

La configuración correcta ya está incorporada:

```json
"outputPath": "dist/libreria-ingles"
```

No es necesario agregarla manualmente.

---

## 10.2 Angular compila pero la página queda en blanco

También ocurrió que `npm start` compilaba correctamente y mostraba:

```text
Local: http://localhost:4200/
```

pero el navegador quedaba completamente en blanco.

La causa era que faltaba cargar `zone.js` como polyfill.

La configuración correcta ya está incluida en `angular.json`:

```json
"polyfills": ["zone.js"]
```

Después de incorporar esta configuración, la landing comenzó a renderizar correctamente.

---

# 11. Flujo habitual de trabajo

Una vez instaladas las dependencias, el flujo normal es:

```text
Abrir LibreriaIngles en VS Code
        ↓
abrir una terminal
        ↓
cd frontend
        ↓
npm start
        ↓
abrir http://localhost:4200
```

No hace falta repetir `npm install` todos los días.

Debe volver a ejecutarse cuando:

- se clona el repositorio por primera vez;
- se elimina `node_modules`;
- cambia `package.json`;
- cambia de manera relevante el árbol de dependencias.

---

# 12. Estado confirmado

El flujo fue probado correctamente en Windows con:

```text
npm start
→ Application bundle generation complete.
→ Watch mode enabled.
→ Local: http://localhost:4200/
```

La landing de **Librería Inglés** fue verificada visualmente en el navegador.

Por lo tanto, la base inicial del frontend queda operativa con:

- Node.js;
- npm;
- Angular 21 (antes 19);
- `npm start`;
- hot reload / watch mode;
- configuración local de Analytics desactivada;
- build configurado;
- `zone.js` cargado correctamente.
