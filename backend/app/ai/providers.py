"""Adapters de proveedores de IA.

Todos exponen la misma interfaz: `complete_json` y `health_check`.
Los errores se traducen a `ProviderError` con un estado de `AIConnectionStatus`,
que el router usa para decidir el failover.
"""

import base64
import json
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.ai.models import AIConnectionStatus
from app.core.config import settings


class ProviderError(Exception):
    def __init__(self, code: AIConnectionStatus, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
        # T-191: respuesta HTTP cruda del error (status, headers, cuerpo) para que la capa de
        # límites la normalice. Nunca se persiste completa.
        self.http: dict | None = None


@dataclass(frozen=True)
class ProviderInfo:
    key: str
    label: str
    default_model: str
    requires_key: bool = True
    supports_audio_input: bool = False


PROVIDERS: dict[str, ProviderInfo] = {
    "OPENAI": ProviderInfo("OPENAI", "OpenAI", "gpt-4o-mini", supports_audio_input=True),
    "GEMINI": ProviderInfo("GEMINI", "Google Gemini", "gemini-2.5-flash", supports_audio_input=True),
    "ANTHROPIC": ProviderInfo("ANTHROPIC", "Anthropic Claude", "claude-sonnet-4-5"),
    "MOCK": ProviderInfo(
        "MOCK", "Simulado (solo desarrollo)", "mock", requires_key=False, supports_audio_input=True
    ),
}


@dataclass(frozen=True)
class SpeechAnalysis:
    """Resultado de una respuesta hablada: transcripción literal y, si el proveedor puede,
    una estimación de pronunciación (dict crudo; se normaliza en app.pronunciation)."""

    text: str
    pronunciation: dict | None = None


@dataclass(frozen=True)
class ModelInfo:
    id: str
    label: str


class AIProvider(Protocol):
    def complete_json(self, system: str, user: str, task: dict) -> dict: ...

    def transcribe_audio(self, audio: bytes, mime_type: str) -> str: ...

    def analyze_speech(self, audio: bytes, mime_type: str) -> SpeechAnalysis: ...

    def health_check(self) -> None: ...

    def list_models(self) -> list[ModelInfo]: ...


# OpenAI lista todos sus modelos (embeddings, audio, imágenes...): solo sirven los de chat.
_OPENAI_CHAT_PREFIXES = ("gpt-", "o1", "o3", "o4", "o5", "chatgpt-")
_OPENAI_EXCLUDE = (
    "embedding", "tts", "whisper", "audio", "realtime", "transcribe", "image",
    "dall-e", "search", "moderation", "instruct", "codex", "computer-use",
)
_GEMINI_EXCLUDE = ("embedding", "aqa", "imagen", "tts", "image", "veo", "live")


def _http_snapshot(response: httpx.Response) -> dict:
    text = response.text[:20_000]
    try:
        body = response.json()
    except ValueError:
        body = None
    return {"status": response.status_code, "headers": dict(response.headers), "text": text, "json": body}


def _classify_http_error(response: httpx.Response) -> ProviderError:
    body = response.text[:500]
    lowered = body.lower()
    status = response.status_code
    if status in (401, 403):
        return ProviderError(AIConnectionStatus.INVALID_CREDENTIALS, "Credencial inválida o sin permisos.")
    if status == 404:
        return ProviderError(AIConnectionStatus.UNKNOWN_ERROR, "Modelo o endpoint inexistente. Revisá el nombre del modelo.")
    if status == 429:
        if any(word in lowered for word in ("quota", "insufficient", "billing", "resource_exhausted", "credit")):
            return ProviderError(AIConnectionStatus.QUOTA_EXCEEDED, "Cuota agotada.")
        return ProviderError(AIConnectionStatus.RATE_LIMITED, "Límite de requests alcanzado.")
    if status == 400 and ("credit" in lowered or "billing" in lowered):
        return ProviderError(AIConnectionStatus.QUOTA_EXCEEDED, "Sin crédito disponible.")
    if status >= 500:
        return ProviderError(AIConnectionStatus.PROVIDER_DOWN, f"El proveedor respondió {status}.")
    return ProviderError(AIConnectionStatus.UNKNOWN_ERROR, f"Error {status}: {body[:200]}")


# ---------------------------------------------------------------- T-169 / T-173

# Corrección abierta: hay que juzgar sentido y tarea, se deja un margen de razonamiento.
OPEN_EXERCISE_TYPES = {"short_writing", "conversation"}
NO_REASONING_KINDS = {"generate_class", "transcribe_audio"}


def reasoning_budget(task: dict | None) -> int | None:
    """Tokens de razonamiento permitidos para la tarea (None = no se fija, decide el modelo).

    T-169: Gemini 2.5 Flash razona por defecto (≈3.000 tokens por corrección medidos) y se
    cobra como salida. Transcribir, generar y corregir ítems cerrados no lo necesitan.
    """
    if not settings.ai_reasoning_control or not task:
        return None
    kind = task.get("kind")
    if kind in NO_REASONING_KINDS:
        return 0
    if kind == "evaluate_answer":
        types = [(task.get("exercise") or {}).get("type")]
    elif kind == "evaluate_batch":
        types = [item.get("type") for item in task.get("items") or [] if isinstance(item, dict)]
    else:
        return None
    if any(t in OPEN_EXERCISE_TYPES for t in types):
        return max(0, settings.ai_reasoning_budget_open)
    return 0


def gemini_budget_supported(model: str | None) -> bool:
    """Solo Gemini 2.5 Flash / Flash-Lite aceptan presupuesto 0; otras familias no se tocan."""
    return (model or "").lower().startswith("gemini-2.5-flash")


# T-202: Gemini 3 controla el razonamiento con niveles (thinkingLevel), no con presupuesto.
# "minimal" solo lo aceptan algunos modelos (3.8 Flash y Pro no): ahí lo más bajo es "low".
_GEMINI3_MINIMAL = ("gemini-3.5-flash", "gemini-3.6-flash", "gemini-3-flash", "gemini-3.1-flash-lite")


def gemini_thinking_level(model: str | None, budget: int | None) -> str | None:
    name = (model or "").lower()
    if budget is None or not name.startswith("gemini-3"):
        return None
    if budget == 0:
        return "minimal" if name.startswith(_GEMINI3_MINIMAL) else "low"
    return "low"  # corrección abierta: un poco de razonamiento, nunca el "medium" por defecto


def gemini_generation_config(model: str | None, task: dict | None, base: dict) -> dict:
    config = dict(base)
    budget = reasoning_budget(task)
    if budget is not None and gemini_budget_supported(model):
        config["thinkingConfig"] = {"thinkingBudget": budget}
    elif (level := gemini_thinking_level(model, budget)) is not None:
        config["thinkingConfig"] = {"thinkingLevel": level}
    schema = (task or {}).get("schema")
    if schema and settings.ai_response_schema and config.get("responseMimeType") == "application/json":
        config["responseSchema"] = schema
    return config


# T-179: tokens de entrada que el proveedor sirvió desde su caché de prefijo.
_CACHED_TOKEN_PATHS = (
    ("usageMetadata", "cachedContentTokenCount"),  # Gemini
    ("usage", "prompt_tokens_details", "cached_tokens"),  # OpenAI
    ("usage", "cache_read_input_tokens"),  # Anthropic
)


def cached_input_tokens(payload: dict | None) -> int | None:
    """Tokens cacheados informados por el proveedor (None si no los informa)."""
    if not isinstance(payload, dict):
        return None
    for path in _CACHED_TOKEN_PATHS:
        node = payload
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
        if isinstance(node, int) and not isinstance(node, bool) and node >= 0:
            return node
    # Gemini omite el campo cuando no hubo caché: si informa usage, es 0.
    if isinstance(payload.get("usageMetadata"), dict):
        return 0
    return None


def parse_json_text(text: str) -> dict:
    """Extrae un objeto JSON aunque venga envuelto en ```json ... ```."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    if not cleaned.startswith("{"):
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end == -1:
            raise ProviderError(AIConnectionStatus.UNKNOWN_ERROR, "La IA no devolvió JSON.")
        cleaned = cleaned[start : end + 1]
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ProviderError(AIConnectionStatus.UNKNOWN_ERROR, "La IA devolvió JSON inválido.") from exc
    if not isinstance(data, dict):
        raise ProviderError(AIConnectionStatus.UNKNOWN_ERROR, "La IA no devolvió un objeto JSON.")
    return data


class _HttpProvider:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        # Payload efímero de la última operación que puede contener usage.
        # Nunca se persiste completo: T-049 solo extrae los contadores configurados en BD.
        self.last_usage_payload: dict | None = None
        # T-191: headers de la última respuesta exitosa (límites informados por el proveedor).
        self.last_response_headers: dict | None = None

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            response = httpx.request(method, url, timeout=settings.ai_timeout_seconds, **kwargs)
        except httpx.TimeoutException as exc:
            raise ProviderError(AIConnectionStatus.NETWORK_ERROR, "Timeout con el proveedor.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(AIConnectionStatus.NETWORK_ERROR, "Error de red con el proveedor.") from exc
        if response.status_code >= 400:
            error = _classify_http_error(response)
            error.http = _http_snapshot(response)
            raise error
        self.last_response_headers = dict(getattr(response, "headers", None) or {})
        return response

    def analyze_speech(self, audio: bytes, mime_type: str) -> SpeechAnalysis:
        """Por defecto solo transcribe (sin estimación de pronunciación)."""
        return SpeechAnalysis(self.transcribe_audio(audio, mime_type), None)


class OpenAIProvider(_HttpProvider):
    base_url = "https://api.openai.com/v1"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def complete_json(self, system: str, user: str, task: dict) -> dict:
        response = self._request(
            "POST",
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_object"},
            },
        )
        try:
            payload = response.json()
            self.last_usage_payload = payload
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise ProviderError(AIConnectionStatus.UNKNOWN_ERROR, "Respuesta inesperada de OpenAI.") from exc
        return parse_json_text(text)

    def health_check(self) -> None:
        self._request("GET", f"{self.base_url}/models/{self.model}", headers=self._headers())

    def list_models(self) -> list[ModelInfo]:
        response = self._request("GET", f"{self.base_url}/models", headers=self._headers())
        try:
            rows = response.json()["data"]
        except (KeyError, ValueError) as exc:
            raise ProviderError(AIConnectionStatus.UNKNOWN_ERROR, "Respuesta inesperada de OpenAI.") from exc
        chat = [
            row
            for row in rows
            if str(row.get("id", "")).startswith(_OPENAI_CHAT_PREFIXES)
            and not any(word in row["id"] for word in _OPENAI_EXCLUDE)
        ]
        chat.sort(key=lambda row: row.get("created", 0), reverse=True)
        return [ModelInfo(row["id"], row["id"]) for row in chat]

    def transcribe_audio(self, audio: bytes, mime_type: str) -> str:
        """Speech-to-text literal. El audio vive solo durante este request."""
        response = self._request(
            "POST",
            f"{self.base_url}/audio/transcriptions",
            headers=self._headers(),
            data={
                "model": "gpt-4o-mini-transcribe",
                "language": "en",
                "prompt": (
                    "Transcribe exactly what the learner says in English. "
                    "Do not fix grammar, word choice, verb forms, or pronunciation mistakes."
                ),
            },
            files={"file": ("answer.webm", audio, mime_type or "audio/webm")},
        )
        try:
            payload = response.json()
            self.last_usage_payload = payload
            text = str(payload["text"]).strip()
        except (KeyError, ValueError) as exc:
            raise ProviderError(
                AIConnectionStatus.UNKNOWN_ERROR, "Respuesta inesperada de OpenAI al transcribir."
            ) from exc
        if not text:
            raise ProviderError(AIConnectionStatus.UNKNOWN_ERROR, "OpenAI no detectó voz.")
        return text


class GeminiProvider(_HttpProvider):
    base_url = "https://generativelanguage.googleapis.com/v1beta"

    def _headers(self) -> dict:
        return {"x-goog-api-key": self.api_key}

    def complete_json(self, system: str, user: str, task: dict) -> dict:
        response = self._request(
            "POST",
            f"{self.base_url}/models/{self.model}:generateContent",
            headers=self._headers(),
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": gemini_generation_config(
                    self.model, task, {"responseMimeType": "application/json"}
                ),
            },
        )
        try:
            payload = response.json()
            self.last_usage_payload = payload
            parts = payload["candidates"][0]["content"]["parts"]
            # Con razonamiento, Gemini puede devolver partes "thought": no son la respuesta.
            text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
        except (KeyError, IndexError, ValueError) as exc:
            raise ProviderError(AIConnectionStatus.UNKNOWN_ERROR, "Respuesta inesperada de Gemini.") from exc
        return parse_json_text(text)

    def health_check(self) -> None:
        self._request("GET", f"{self.base_url}/models/{self.model}", headers=self._headers())

    def list_models(self) -> list[ModelInfo]:
        models: list[ModelInfo] = []
        page_token = None
        for _ in range(10):  # tope de páginas por seguridad
            params = {"pageSize": 1000}
            if page_token:
                params["pageToken"] = page_token
            response = self._request(
                "GET", f"{self.base_url}/models", headers=self._headers(), params=params
            )
            try:
                data = response.json()
                rows = data.get("models", [])
            except ValueError as exc:
                raise ProviderError(AIConnectionStatus.UNKNOWN_ERROR, "Respuesta inesperada de Gemini.") from exc
            for row in rows:
                model_id = str(row.get("name", "")).removeprefix("models/")
                if "generateContent" not in row.get("supportedGenerationMethods", []):
                    continue
                if not model_id.startswith("gemini") or any(w in model_id for w in _GEMINI_EXCLUDE):
                    continue
                models.append(ModelInfo(model_id, row.get("displayName") or model_id))
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return models

    def transcribe_audio(self, audio: bytes, mime_type: str) -> str:
        """Transcripción literal usando audio inline; suficiente para respuestas cortas."""
        encoded = base64.b64encode(audio).decode("ascii")
        mime = (mime_type or "audio/webm").split(";", 1)[0].strip()
        response = self._request(
            "POST",
            f"{self.base_url}/models/{self.model}:generateContent",
            headers=self._headers(),
            json={
                "systemInstruction": {
                    "parts": [{
                        "text": (
                            "You are a literal speech-to-text engine for an English learner. "
                            "Never correct grammar, vocabulary, verb forms or wording."
                        )
                    }]
                },
                "contents": [{
                    "role": "user",
                    "parts": [
                        {"text": "Transcribe exactly what is spoken. Return only the transcript."},
                        {"inlineData": {"mimeType": mime, "data": encoded}},
                    ],
                }],
                "generationConfig": gemini_generation_config(
                    self.model, {"kind": "transcribe_audio"}, {"temperature": 0}
                ),
            },
        )
        try:
            payload = response.json()
            self.last_usage_payload = payload
            parts = payload["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts).strip()
        except (KeyError, IndexError, ValueError) as exc:
            raise ProviderError(
                AIConnectionStatus.UNKNOWN_ERROR, "Respuesta inesperada de Gemini al transcribir."
            ) from exc
        if not text:
            raise ProviderError(AIConnectionStatus.UNKNOWN_ERROR, "Gemini no detectó voz.")
        return text

    def analyze_speech(self, audio: bytes, mime_type: str) -> SpeechAnalysis:
        """Una sola llamada: transcripción literal + estimación de pronunciación (T-027).

        Si la respuesta no se puede interpretar, se cae a la transcripción simple: la
        pronunciación nunca hace fallar la respuesta del alumno.
        """
        encoded = base64.b64encode(audio).decode("ascii")
        mime = (mime_type or "audio/webm").split(";", 1)[0].strip()
        response = self._request(
            "POST",
            f"{self.base_url}/models/{self.model}:generateContent",
            headers=self._headers(),
            json={
                "systemInstruction": {"parts": [{"text": SPEECH_ANALYSIS_PROMPT}]},
                "contents": [{
                    "role": "user",
                    "parts": [
                        {"text": "Analyse this recording."},
                        {"inlineData": {"mimeType": mime, "data": encoded}},
                    ],
                }],
                "generationConfig": gemini_generation_config(
                    self.model,
                    {"kind": "transcribe_audio"},
                    {"temperature": 0, "responseMimeType": "application/json"},
                ),
            },
        )
        try:
            payload = response.json()
            self.last_usage_payload = payload
            parts = payload["candidates"][0]["content"]["parts"]
            data = parse_json_text("".join(part.get("text", "") for part in parts))
            text = str(data.get("transcript") or "").strip()
        except (KeyError, IndexError, ValueError, ProviderError):
            return SpeechAnalysis(self.transcribe_audio(audio, mime_type), None)
        if not text:
            raise ProviderError(AIConnectionStatus.UNKNOWN_ERROR, "Gemini no detectó voz.")
        pronunciation = data.get("pronunciation")
        return SpeechAnalysis(text, pronunciation if isinstance(pronunciation, dict) else None)


SPEECH_ANALYSIS_PROMPT = """You analyse a short spoken answer from an English learner.
Return ONLY a JSON object:
{
  "transcript": "exactly what was said, literally. Never correct grammar, vocabulary or verb forms",
  "pronunciation": {
    "score": 0-100,
    "words": [{"word": "<each word of the transcript, in order>", "score": 0-100}],
    "phonemes": [{"phoneme": "<IPA>", "word": "<word>", "score": 0-100}],
    "fluency": 0-100
  }
}
Rules for "pronunciation":
- Judge ONLY how the words that were actually said sound (clarity, sounds, stress, rhythm),
  as an English teacher would for a learner. Do NOT judge grammar or whether the answer is right.
- "phonemes": only the problematic sounds (e.g. /θ/ said as /s/); empty list if none.
- If there is no intelligible speech, return "transcript": "" and "pronunciation": null."""


class AnthropicProvider(_HttpProvider):
    base_url = "https://api.anthropic.com/v1"

    def _headers(self) -> dict:
        return {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}

    def complete_json(self, system: str, user: str, task: dict) -> dict:
        response = self._request(
            "POST",
            f"{self.base_url}/messages",
            headers=self._headers(),
            json={
                "model": self.model,
                "max_tokens": 4096,
                "system": system + "\nRespond with a single JSON object and nothing else.",
                "messages": [{"role": "user", "content": user}],
            },
        )
        try:
            payload = response.json()
            self.last_usage_payload = payload
            blocks = payload["content"]
            text = "".join(block.get("text", "") for block in blocks if block.get("type") == "text")
        except (KeyError, ValueError) as exc:
            raise ProviderError(AIConnectionStatus.UNKNOWN_ERROR, "Respuesta inesperada de Anthropic.") from exc
        return parse_json_text(text)

    def health_check(self) -> None:
        self._request("GET", f"{self.base_url}/models/{self.model}", headers=self._headers())

    def list_models(self) -> list[ModelInfo]:
        models: list[ModelInfo] = []
        params: dict = {"limit": 1000}
        for _ in range(10):
            response = self._request(
                "GET", f"{self.base_url}/models", headers=self._headers(), params=params
            )
            try:
                data = response.json()
                rows = data["data"]
            except (KeyError, ValueError) as exc:
                raise ProviderError(AIConnectionStatus.UNKNOWN_ERROR, "Respuesta inesperada de Anthropic.") from exc
            models += [ModelInfo(row["id"], row.get("display_name") or row["id"]) for row in rows]
            if not data.get("has_more") or not data.get("last_id"):
                break
            params = {"limit": 1000, "after_id": data["last_id"]}
        return models


def build_provider(provider: str, api_key: str | None, model: str | None) -> AIProvider:
    provider = provider.upper()
    info = PROVIDERS.get(provider)
    if info is None:
        raise ProviderError(AIConnectionStatus.UNKNOWN_ERROR, f"Proveedor desconocido: {provider}")
    model = model or info.default_model

    if provider == "MOCK":
        if not settings.mock_ai_allowed:
            raise ProviderError(AIConnectionStatus.DISABLED, "El proveedor simulado está deshabilitado.")
        from app.ai.mock import MockProvider

        return MockProvider(model)

    if not api_key:
        raise ProviderError(AIConnectionStatus.INVALID_CREDENTIALS, "Falta la API key.")
    classes = {"OPENAI": OpenAIProvider, "GEMINI": GeminiProvider, "ANTHROPIC": AnthropicProvider}
    return classes[provider](api_key, model)
