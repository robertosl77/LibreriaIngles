# BK / OpenPronounce

Backup técnico del trabajo experimental de pronunciación precisa realizado para T-027/T-039.

## Origen

- Rama archivada: `archivo/t-027-openpronounce`
- Último commit preservado: `a960c359ce20b0a093b44d036ac15829be700d8f`
- Issue de continuidad: #83 — T-039 · Motor de pronunciación preciso (OpenPronounce)
- La solución productiva posterior usa pronunciación estimada por IA; este código queda como referencia y posible motor opcional futuro.

## Qué se preserva

La carpeta `original/` contiene copias exactas de los archivos relevantes tal como estaban en la rama archivada:

- `backend/app/pronunciation.py`: adaptador OpenPronounce y normalización del resultado.
- `backend/app/classes/api.py`: integración histórica del motor con respuestas habladas.
- `backend/tests/test_pronunciation.py`: tests del adaptador OpenPronounce.
- `backend/tests/test_speaking.py`: tests end-to-end de Speaking/pronunciación de esa rama.
- `backend/pyproject.toml`: dependencia opcional `openpronounce==0.3.0`.
- `setup-pronunciation.ps1`: script original de preparación local.
- `.gitignore`: evidencia de las dependencias binarias locales excluidas del repositorio.

## Dependencias ejecutables

Durante las pruebas se usaban dos dependencias locales principales:

1. **FFmpeg**
   - destino esperado: `<repo>/ffmpeg/bin/ffmpeg.exe`
2. **eSpeak NG**
   - destino esperado: `<repo>/espeak-ng/libespeak-ng.dll`
   - datos: `<repo>/espeak-ng/espeak-ng-data`

Estos binarios **nunca estuvieron versionados**: la rama los ignoraba explícitamente porque son dependencias grandes/locales. Por eso no pueden copiarse desde GitHub al backup.

El archivo `setup-pronunciation.ps1` de esta carpeta es una versión ejecutable desde `BK/OpenPronounce` que vuelve a descargar y preparar FFmpeg/eSpeak NG en el root del repositorio. La copia exacta histórica permanece en `original/setup-pronunciation.ps1`.

## Rehidratación futura

Este backup es inerte: nada dentro de `BK/` participa del runtime actual.

Para retomar T-039:

1. revisar #83 y la infraestructura disponible;
2. recuperar/adaptar `original/backend/app/pronunciation.py`;
3. recuperar la integración necesaria desde `original/backend/app/classes/api.py`;
4. reinstalar la dependencia Python OpenPronounce;
5. ejecutar `BK/OpenPronounce/setup-pronunciation.ps1` para preparar FFmpeg/eSpeak NG;
6. recalibrar puntajes y volver a correr los tests archivados antes de integrar nada al runtime.

No copiar ciegamente los archivos sobre el backend actual: el proyecto evolucionó significativamente desde esta rama.
