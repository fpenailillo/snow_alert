"""
BaseSubagente — Clase base para todos los subagentes del sistema multi-agente.

Implementa el agentic loop con tool_use nativo de Anthropic.
Cada subagente es una instancia independiente de Claude con su propio
historial de mensajes y conjunto de tools especializadas.

Autenticación: usa CLAUDE_CODE_OAUTH_TOKEN del entorno.
"""

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

from agentes.datos.cliente_llm import crear_cliente


logger = logging.getLogger(__name__)


# Configuración de reintentos para llamadas a la API
MAX_REINTENTOS_API = 3
ESPERA_BASE_SEGUNDOS = 2.0
ESPERA_MAXIMA_SEGUNDOS = 30.0


class ErrorSubagente(Exception):
    """Excepción levantada cuando un subagente falla."""
    pass


class BaseSubagente(ABC):
    """
    Clase base abstracta para todos los subagentes especializados.

    Provee el agentic loop reutilizable con tool_use nativo.
    Cada subagente hereda esta clase e implementa sus propias tools
    y system prompt.

    Atributos de clase que las subclases deben definir:
        NOMBRE     : nombre descriptivo del subagente
        MODELO     : modelo a usar (referencial, el cliente puede ignorarlo)
        PROVEEDOR  : "databricks" (gratis) | "anthropic" (Claude, validación)
        MAX_TOKENS : máximo de tokens por respuesta
        MAX_ITERACIONES: límite del loop agentic
    """

    NOMBRE = "BaseSubagente"
    MODELO = "qwen3-next-80b-a3b-instruct"
    PROVEEDOR = "databricks"
    MAX_TOKENS = 4096
    MAX_ITERACIONES = 10

    def __init__(self):
        """Inicializa el subagente con el cliente LLM correspondiente al proveedor."""
        self.cliente = crear_cliente(self.PROVEEDOR)
        logger.debug(
            f"{self.NOMBRE}: cliente inicializado — proveedor: {self.PROVEEDOR}"
        )

        self._tools_definicion = self._cargar_tools()
        self._tools_ejecutores = self._cargar_ejecutores()
        logger.info(
            f"{self.NOMBRE} inicializado — "
            f"modelo: {self.MODELO}, "
            f"tools: {[t['name'] for t in self._tools_definicion]}"
        )

    @abstractmethod
    def _cargar_tools(self) -> list:
        """
        Retorna las definiciones de tools en formato Anthropic.

        Returns:
            Lista de dicts con name, description e input_schema
        """
        raise NotImplementedError

    @abstractmethod
    def _cargar_ejecutores(self) -> dict:
        """
        Retorna el mapa {nombre_tool: función_ejecutora}.

        Returns:
            Dict donde cada valor es un callable que recibe **kwargs
        """
        raise NotImplementedError

    @abstractmethod
    def _obtener_system_prompt(self) -> str:
        """
        Retorna el system prompt del subagente.

        Returns:
            String con el prompt del sistema en español
        """
        raise NotImplementedError

    def _construir_prompt_usuario(
        self,
        nombre_ubicacion: str,
        contexto_previo: Optional[str] = None
    ) -> str:
        """
        Construye el prompt inicial para el subagente.

        Args:
            nombre_ubicacion: ubicación a analizar
            contexto_previo: análisis acumulado de subagentes anteriores

        Returns:
            String con el prompt de usuario
        """
        prompt = f"Analiza la ubicación: {nombre_ubicacion}\n\n"
        if contexto_previo:
            prompt += f"Contexto de análisis previo:\n{contexto_previo}\n\n"
        prompt += "Usa todas tus tools disponibles para completar el análisis."
        return prompt

    def _llamar_api_con_reintentos(self, mensajes: list) -> object:
        """
        Llama a la API de Anthropic con reintentos y backoff exponencial.

        Reintenta en errores transitorios (rate limit, errores de servidor,
        errores de conexión). No reintenta en errores de cliente (400, 401, 403).

        Args:
            mensajes: lista de mensajes del agentic loop

        Returns:
            Respuesta de la API

        Raises:
            ErrorSubagente: si se agotan los reintentos
        """
        ultimo_error = None
        errores_recuperables = self.cliente.errores_recuperables
        error_servidor = self.cliente.error_servidor

        for intento in range(MAX_REINTENTOS_API):
            try:
                return self.cliente.crear_mensaje(
                    model=self.MODELO,
                    max_tokens=self.MAX_TOKENS,
                    system=self._obtener_system_prompt(),
                    tools=self._tools_definicion,
                    messages=mensajes,
                )
            except errores_recuperables as exc:
                ultimo_error = exc
                espera = min(
                    ESPERA_BASE_SEGUNDOS * (2 ** intento),
                    ESPERA_MAXIMA_SEGUNDOS
                )
                logger.warning(
                    f"{self.NOMBRE}: error recuperable (intento {intento + 1}/"
                    f"{MAX_REINTENTOS_API}), esperando {espera:.1f}s — {exc}"
                )
                time.sleep(espera)
            except error_servidor as exc:
                codigo = getattr(exc, "status_code", 0)
                if codigo >= 500:
                    ultimo_error = exc
                    espera = min(
                        ESPERA_BASE_SEGUNDOS * (2 ** intento),
                        ESPERA_MAXIMA_SEGUNDOS
                    )
                    logger.warning(
                        f"{self.NOMBRE}: error servidor {codigo} "
                        f"(intento {intento + 1}/{MAX_REINTENTOS_API}), "
                        f"esperando {espera:.1f}s"
                    )
                    time.sleep(espera)
                else:
                    raise ErrorSubagente(
                        f"{self.NOMBRE}: error API no recuperable "
                        f"(HTTP {codigo}): {exc}"
                    ) from exc

        raise ErrorSubagente(
            f"{self.NOMBRE}: agotados {MAX_REINTENTOS_API} reintentos API — "
            f"último error: {ultimo_error}"
        ) from ultimo_error

    def ejecutar(
        self,
        nombre_ubicacion: str,
        contexto_previo: Optional[str] = None
    ) -> dict:
        """
        Ejecuta el agentic loop del subagente para una ubicación.

        Args:
            nombre_ubicacion: nombre exacto de la ubicación en BigQuery
            contexto_previo: contexto acumulado de subagentes anteriores

        Returns:
            dict con analisis (texto), tools_llamadas, iteraciones,
            duracion_segundos, timestamp, modelo, nombre_subagente

        Raises:
            ErrorSubagente: si se supera el límite de iteraciones
        """
        inicio = time.time()
        prompt_usuario = self._construir_prompt_usuario(
            nombre_ubicacion, contexto_previo
        )
        mensajes = [{"role": "user", "content": prompt_usuario}]
        tools_llamadas = []
        iteracion = 0

        logger.info(
            f"{self.NOMBRE}: iniciando análisis de '{nombre_ubicacion}'"
        )

        while iteracion < self.MAX_ITERACIONES:
            logger.info(
                f"{self.NOMBRE}: iteración {iteracion} → llamando a {self.MODELO}"
            )

            respuesta = self._llamar_api_con_reintentos(mensajes)

            logger.info(
                f"{self.NOMBRE} it.{iteracion}: "
                f"stop_reason={respuesta.stop_reason}, "
                f"tokens_in={respuesta.usage.input_tokens}, "
                f"tokens_out={respuesta.usage.output_tokens}"
            )

            # El subagente terminó su análisis
            if respuesta.stop_reason == "end_turn":
                analisis_texto = next(
                    (b.text for b in respuesta.content if hasattr(b, 'text')),
                    ""
                )
                duracion = round(time.time() - inicio, 1)

                logger.info(
                    f"{self.NOMBRE}: análisis completado en {duracion}s, "
                    f"{iteracion} iteraciones, {len(tools_llamadas)} llamadas"
                )

                return {
                    "nombre_subagente": self.NOMBRE,
                    "ubicacion": nombre_ubicacion,
                    "analisis": analisis_texto,
                    "tools_llamadas": tools_llamadas,
                    "iteraciones": iteracion,
                    "duracion_segundos": duracion,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "modelo": self.MODELO
                }

            # El subagente quiere llamar tools
            if respuesta.stop_reason == "tool_use":
                mensajes.append({
                    "role": "assistant",
                    "content": respuesta.content
                })

                resultados_tools = []
                for bloque in respuesta.content:
                    if bloque.type == "tool_use":
                        logger.info(
                            f"{self.NOMBRE} → tool: {bloque.name} | "
                            f"inputs: {json.dumps(bloque.input, ensure_ascii=False)}"
                        )

                        inicio_tool = time.time()
                        try:
                            ejecutor = self._tools_ejecutores.get(bloque.name)
                            if ejecutor is None:
                                raise KeyError(
                                    f"Tool no registrada: {bloque.name}"
                                )
                            resultado = ejecutor(**bloque.input)
                        except Exception as exc:
                            logger.error(
                                f"{self.NOMBRE} ✗ Error en {bloque.name}: {exc}"
                            )
                            resultado = {"error": str(exc)}

                        duracion_tool = round(time.time() - inicio_tool, 2)
                        logger.info(
                            f"{self.NOMBRE} ✓ {bloque.name} en {duracion_tool}s"
                        )

                        resultados_tools.append({
                            "type": "tool_result",
                            "tool_use_id": bloque.id,
                            "content": json.dumps(
                                resultado, ensure_ascii=False, default=str
                            )
                        })

                        tools_llamadas.append({
                            "tool": bloque.name,
                            "iteracion": iteracion,
                            "inputs": bloque.input,
                            "resultado": resultado,
                            "duracion_segundos": duracion_tool,
                            "subagente": self.NOMBRE
                        })

                mensajes.append({
                    "role": "user",
                    "content": resultados_tools
                })
                iteracion += 1
                continue

            # stop_reason inesperado
            logger.warning(
                f"{self.NOMBRE}: stop_reason inesperado '{respuesta.stop_reason}' "
                f"en iteración {iteracion}"
            )
            break

        raise ErrorSubagente(
            f"{self.NOMBRE}: límite de {self.MAX_ITERACIONES} iteraciones "
            f"alcanzado para '{nombre_ubicacion}'"
        )
