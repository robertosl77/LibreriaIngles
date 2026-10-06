# BK / GitHubCopilotMCP

Backup técnico de la integración experimental **GitHub Copilot (VS Code) → MCP → Agent Dev Kit**.

## Origen

- Rama archivada: `feat/github-copilot-mcp` (eliminada después de este backup)
- Último commit preservado: `0e983aa46ae6ce8de5c9a72b627767d7f0e1111b`
- Issue de continuidad en agent-dev-kit: M-051 — Integración GitHub Copilot ↔ Agent Dev Kit sobre MCP (robertosl77/agent-dev-kit#92)
- Se archivó porque, por ahora, Agent Dev Kit se usa **por consola** (`agent-dev-kit run .`, ver `machete.txt`).

## Qué se preserva

La carpeta `original/` contiene copias exactas de los archivos que la rama agregaba y que no estaban en `develop`:

- `.vscode/mcp.json`: hace que VS Code levante `agent-dev-kit mcp .` desde `backend\.venv` como servidor MCP (stdio).
- `.github/agents/agent-dev-kit.agent.md`: agente de Copilot que delega la orquestación en Agent Dev Kit y usa las herramientas de Copilot (leer, buscar, editar, ejecutar) para materializar el trabajo.

`machete.txt`, que también estaba en esa rama, ya se había pasado a `develop`.

## Por qué sirve

Hoy (Agent Dev Kit v0.2.0) los agentes **no tienen herramientas**: por consola solo planifican y proponen texto. Con esta integración, **Copilot pone las manos**: Agent Dev Kit decide el plan y Copilot edita archivos y corre tests. Es la alternativa a M-076 (herramientas propias de Agent Dev Kit, robertosl77/agent-dev-kit#119).

## Rehidratación futura

Este backup es inerte: VS Code solo lee `.vscode/mcp.json` y Copilot solo lee `.github/agents/` cuando están en la raíz del repo; dentro de `BK/` no se activan.

Para retomarlo:

1. crear una rama desde `develop`;
2. copiar `original/.vscode/mcp.json` a `.vscode/mcp.json`;
3. copiar `original/.github/agents/agent-dev-kit.agent.md` a `.github/agents/`;
4. en modo MCP no hay menú: agregar la key del proveedor al servidor, sin versionarla. Por ejemplo, en `mcp.json` agregar `"inputs"` con `promptString` y `"password": true` y referenciarlo en `"env"` como `${input:...}` (ANTHROPIC_API_KEY, GEMINI_API_KEY u OPENAI_API_KEY según el proveedor);
5. en `.agent-dev-kit/project.yaml`, fijar `provider.default_model` (en modo MCP, Anthropic y Gemini lo exigen);
6. abrir VS Code, iniciar el servidor MCP y probar con el agente "Agent Dev Kit" en el chat de Copilot (modo agente).

Revisar antes la versión vigente de Agent Dev Kit: estos archivos se escribieron para v0.1.0.
