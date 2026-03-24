"""
cliente_llm.py — Abstracción multi-proveedor de cliente LLM.

Soporta dos proveedores:
  - "anthropic"  → Claude (pago, reservado para validación final)
  - "databricks" → Databricks AI Gateway / OpenAI-compatible (gratuito, uso general)

Normaliza las respuestas de Databricks al formato Anthropic para que
base_subagente.py no requiera cambios en el agentic loop.

Variables de entorno:
    DATABRICKS_TOKEN    — token de acceso Databricks (dapi...)
    DATABRICKS_BASE_URL — URL del AI Gateway (con /mlflow/v1)
    DATABRICKS_MODEL    — nombre del modelo (por defecto: qwen3-next-80b-a3b-instruct)
    ANTHROPIC_API_KEY   — clave Anthropic (solo para validación)
    CLAUDE_CODE_OAUTH_TOKEN — token OAuth Claude (alternativa a API key)
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# ─── Estructuras de respuesta normalizadas (formato Anthropic) ────────────────


@dataclass
class BloqueTexto:
    text: str
    type: str = "text"


@dataclass
class BloqueToolUse:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class _Usage:
    input_tokens: int
    output_tokens: int


@dataclass
class RespuestaNormalizada:
    """Respuesta normalizada al formato Anthropic para uso en base_subagente."""
    stop_reason: str       # "end_turn" | "tool_use"
    content: List[Any]     # lista de BloqueTexto | BloqueToolUse
    usage: _Usage


# ─── Cliente Anthropic ────────────────────────────────────────────────────────

class ClienteAnthropic:
    """Wrapper del SDK Anthropic. Retorna respuestas nativas (sin normalizar)."""

    def __init__(self):
        import anthropic
        token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        self._sdk = anthropic
        if token:
            self._cliente = anthropic.Anthropic(auth_token=token)
        else:
            self._cliente = anthropic.Anthropic()
        logger.debug("ClienteAnthropic inicializado")

    @property
    def errores_recuperables(self):
        """Tupla de excepciones que se deben reintentar."""
        return (
            self._sdk.RateLimitError,
            self._sdk.APIConnectionError,
        )

    @property
    def error_servidor(self):
        return self._sdk.APIStatusError

    def crear_mensaje(self, *, model, max_tokens, system, tools, messages):
        return self._cliente.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            messages=messages,
        )


# ─── Cliente Databricks (OpenAI-compatible) ───────────────────────────────────

class ClienteDatabricks:
    """
    Wrapper del SDK OpenAI apuntando al Databricks AI Gateway.
    Convierte tool definitions Anthropic → OpenAI y normaliza la respuesta
    de vuelta al formato Anthropic para que base_subagente.py no cambie.
    """

    MODELO_DEFAULT = "databricks-qwen3-next-80b-a3b-instruct"
    BASE_URL_DEFAULT = (
        "https://2113388677481041.ai-gateway.cloud.databricks.com/mlflow/v1"
    )
    SECRET_NAME = "projects/climas-chileno/secrets/databricks-token/versions/latest"

    def __init__(self):
        try:
            from openai import OpenAI, RateLimitError, APIConnectionError, APIStatusError
        except ImportError as exc:
            raise ImportError(
                "Paquete 'openai' requerido para ClienteDatabricks. "
                "Instalar con: pip install openai"
            ) from exc

        self._RateLimitError = RateLimitError
        self._APIConnectionError = APIConnectionError
        self._APIStatusError = APIStatusError

        token = os.environ.get("DATABRICKS_TOKEN")
        if not token:
            try:
                from google.cloud import secretmanager
                sm = secretmanager.SecretManagerServiceClient()
                resp = sm.access_secret_version(name=self.SECRET_NAME)
                token = resp.payload.data.decode("utf-8").strip()
                logger.debug("ClienteDatabricks: token cargado desde Secret Manager")
            except Exception as exc:
                raise ValueError(
                    "DATABRICKS_TOKEN no encontrado en variables de entorno ni en "
                    f"Secret Manager ({self.SECRET_NAME}): {exc}"
                ) from exc

        base_url = os.environ.get("DATABRICKS_BASE_URL", self.BASE_URL_DEFAULT)
        self._modelo = os.environ.get("DATABRICKS_MODEL", self.MODELO_DEFAULT)

        self._cliente = OpenAI(api_key=token, base_url=base_url)
        logger.debug(
            f"ClienteDatabricks inicializado → modelo: {self._modelo}, "
            f"base_url: {base_url}"
        )

    @property
    def errores_recuperables(self):
        return (self._RateLimitError, self._APIConnectionError)

    @property
    def error_servidor(self):
        return self._APIStatusError

    # ── Conversiones Anthropic → OpenAI ──────────────────────────────────────

    def _tools_a_openai(self, tools: list) -> list:
        """Convierte definición de tools Anthropic → OpenAI."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get(
                        "input_schema",
                        {"type": "object", "properties": {}},
                    ),
                },
            }
            for t in tools
        ]

    def _mensajes_a_openai(self, system: str, messages: list) -> list:
        """Convierte historial de mensajes Anthropic → OpenAI."""
        resultado = [{"role": "system", "content": system}]

        for msg in messages:
            rol = msg["role"]
            contenido = msg["content"]

            if rol == "user":
                if isinstance(contenido, str):
                    resultado.append({"role": "user", "content": contenido})
                elif isinstance(contenido, list):
                    # Lista: puede mezclar tool_results y texto
                    tool_results = []
                    texto_extra = []
                    for item in contenido:
                        if (
                            isinstance(item, dict)
                            and item.get("type") == "tool_result"
                        ):
                            tool_results.append({
                                "role": "tool",
                                "tool_call_id": item["tool_use_id"],
                                "content": item["content"],
                            })
                        else:
                            texto_extra.append(str(item))
                    resultado.extend(tool_results)
                    if texto_extra:
                        resultado.append({
                            "role": "user",
                            "content": " ".join(texto_extra),
                        })

            elif rol == "assistant":
                if isinstance(contenido, list):
                    texto = ""
                    tool_calls = []
                    for bloque in contenido:
                        tipo = (
                            bloque.type
                            if hasattr(bloque, "type")
                            else bloque.get("type", "")
                        )
                        if tipo == "text":
                            texto += (
                                bloque.text
                                if hasattr(bloque, "text")
                                else bloque.get("text", "")
                            )
                        elif tipo == "tool_use":
                            nombre = (
                                bloque.name
                                if hasattr(bloque, "name")
                                else bloque.get("name", "")
                            )
                            inp = (
                                bloque.input
                                if hasattr(bloque, "input")
                                else bloque.get("input", {})
                            )
                            bid = (
                                bloque.id
                                if hasattr(bloque, "id")
                                else bloque.get("id", "")
                            )
                            tool_calls.append({
                                "id": bid,
                                "type": "function",
                                "function": {
                                    "name": nombre,
                                    "arguments": json.dumps(
                                        inp, ensure_ascii=False
                                    ),
                                },
                            })
                    msg_asistente: dict = {
                        "role": "assistant",
                        "content": texto or None,
                    }
                    if tool_calls:
                        msg_asistente["tool_calls"] = tool_calls
                    resultado.append(msg_asistente)
                else:
                    resultado.append({
                        "role": "assistant",
                        "content": str(contenido),
                    })

        return resultado

    # ── Normalización OpenAI → Anthropic ─────────────────────────────────────

    def _normalizar_respuesta(self, resp) -> RespuestaNormalizada:
        """Convierte respuesta OpenAI → RespuestaNormalizada (formato Anthropic)."""
        choice = resp.choices[0]
        message = choice.message
        finish_reason = choice.finish_reason

        bloques: list = []

        if message.content:
            bloques.append(BloqueTexto(text=message.content))

        if getattr(message, "tool_calls", None):
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {"_raw": tc.function.arguments}
                bloques.append(BloqueToolUse(
                    id=tc.id,
                    name=tc.function.name,
                    input=args,
                ))

        stop_reason = "tool_use" if finish_reason == "tool_calls" else "end_turn"
        uso = _Usage(
            input_tokens=getattr(
                getattr(resp, "usage", None), "prompt_tokens", 0
            ),
            output_tokens=getattr(
                getattr(resp, "usage", None), "completion_tokens", 0
            ),
        )
        return RespuestaNormalizada(
            stop_reason=stop_reason,
            content=bloques,
            usage=uso,
        )

    TIMEOUT_SEGUNDOS = 300  # 5 minutos por llamada LLM

    def crear_mensaje(self, *, model, max_tokens, system, tools, messages):
        tools_oi = self._tools_a_openai(tools)
        messages_oi = self._mensajes_a_openai(system, messages)
        resp = self._cliente.chat.completions.create(
            model=self._modelo,
            max_tokens=max_tokens,
            tools=tools_oi,
            messages=messages_oi,
            timeout=self.TIMEOUT_SEGUNDOS,
        )
        return self._normalizar_respuesta(resp)


# ─── Factory ──────────────────────────────────────────────────────────────────

def crear_cliente(proveedor: str = "databricks"):
    """
    Crea el cliente LLM según el proveedor.

    Args:
        proveedor: "databricks" (gratis, por defecto) o "anthropic" (Claude, validación)

    Returns:
        ClienteDatabricks o ClienteAnthropic
    """
    if proveedor == "anthropic":
        return ClienteAnthropic()
    return ClienteDatabricks()
