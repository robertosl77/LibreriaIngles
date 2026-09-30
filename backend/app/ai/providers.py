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
class ModelInfo:
    id: str
    label: str


class AIProvider(Protocol):
    def complete_json(self, system: str, user: str, task: dict) -> dict: ...

    def transcribe_audio(self, audio: bytes, mime_type: str) -> str: ...

    def health_check(self) -> None: ...

    def list_models(self) -> list[ModelInfo]: ...


# OpenAI lista todos sus modelos (embeddings, audio, imágenes...): solo sirven los de chat.
_OPENAI_CHAT_PREFIXES = ("gpt-", "o1", "o3", "o4", "o5", "chatgpt-")
_OPENAI_EXCLUDE = (
    "embedding", "tts", "whisper", "audio", "realtime", "transcribe", "image",
    "dall-e", "search", "moderation", "instruct", "codex", "computer-use",
)
_GEMINI_EXCLUDE = ("embedding", "aqa", "imagen", "tts", "image", "veo", "live")


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

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            response = httpx.request(method, url, timeout=settings.ai_timeout_seconds, **kwargs)
        except httpx.TimeoutException as exc:
            raise ProviderError(AIConnectionStatus.NETWORK_ERROR, "Timeout con el proveedor.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(AIConnectionStatus.NETWORK_ERROR, "Error de red con el proveedor.") from exc
        if response.status_code >= 400:
            raise _classify_http_error(response)
        return response


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
            text = response.json()["choices"][0]["message"]["content"]
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
            text = str(response.json()["text"]).strip()
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
                "generationConfig": {"responseMimeType": "application/json"},
            },
        )
        try:
            parts = response.json()["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts)
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
                "generationConfig": {"temperature": 0},
            },
        )
        try:
            parts = response.json()["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts).strip()
        except (KeyError, IndexError, ValueError) as exc:
            raise ProviderError(
                AIConnectionStatus.UNKNOWN_ERROR, "Respuesta inesperada de Gemini al transcribir."
            ) from exc
        if not text:
            raise ProviderError(AIConnectionStatus.UNKNOWN_ERROR, "Gemini no detectó voz.")
        return text


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
            blocks = response.json()["content"]
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
