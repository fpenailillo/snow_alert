"""
Orquestador del Sistema Multi-Agente de Predicción de Avalanchas (v2)

Coordina 5 subagentes independientes de Claude en secuencia:
1. SubagenteTopografico — análisis DEM + PINNs
2. SubagenteSatelital — análisis satelital + ViT
3. SubagenteMeteorologico — condiciones y ventanas críticas
4. SubagenteNLP — análisis de relatos históricos de montañistas
5. SubagenteIntegrador — clasificación EAWS + boletín final

El contexto se acumula de cada subagente al siguiente.
Mantiene retrocompatibilidad con la interfaz v1 (AgenteRiesgoAvalancha).

Autenticación: usa CLAUDE_CODE_OAUTH_TOKEN del entorno.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

from agentes.subagentes.subagente_topografico.agente import SubagenteTopografico
from agentes.subagentes.subagente_satelital.agente import SubagenteSatelital
from agentes.subagentes.subagente_meteorologico.agente import SubagenteMeteorologico
from agentes.subagentes.subagente_integrador.agente import SubagenteIntegrador
from agentes.subagentes.subagente_nlp.agente import SubagenteNLP
from agentes.prompts.registro_versiones import obtener_version_actual, verificar_integridad


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ErrorOrquestador(Exception):
    """Excepción levantada cuando el orquestador falla."""
    pass


class OrquestadorAvalancha:
    """
    Orquestador del sistema multi-agente de predicción de avalanchas.

    Coordina 5 subagentes independientes de Claude en secuencia:
    1. Topográfico (DEM + PINNs)
    2. Satelital (imágenes + ViT)
    3. Meteorológico (condiciones + ventanas críticas)
    4. NLP Relatos (análisis histórico de montañistas)
    5. Integrador (EAWS + boletín final)

    El contexto se acumula de cada subagente al siguiente para
    proporcionar información enriquecida a cada etapa del análisis.
    """

    MODELO_SUBAGENTES = "claude-sonnet-4-5"

    def __init__(self):
        """Inicializa el orquestador y los 5 subagentes."""
        logger.info("Inicializando OrquestadorAvalancha (v3 multi-agente)...")

        self.subagente_topografico = SubagenteTopografico()
        self.subagente_satelital = SubagenteSatelital()
        self.subagente_meteorologico = SubagenteMeteorologico()
        self.subagente_nlp = SubagenteNLP()
        self.subagente_integrador = SubagenteIntegrador()

        # Verificar integridad de prompts al inicializar
        self._version_prompts = obtener_version_actual()
        if not verificar_integridad():
            logger.warning(
                "Integridad de prompts NO verificada — algún prompt fue "
                "modificado sin actualizar registro_versiones.py"
            )

        logger.info(
            "OrquestadorAvalancha inicializado — "
            f"5 subagentes con modelo {self.MODELO_SUBAGENTES}, "
            f"prompts {self._version_prompts}"
        )

    def generar_boletin(self, nombre_ubicacion: str) -> dict:
        """
        Genera un boletín EAWS completo para una ubicación.

        Ejecuta los 5 subagentes en secuencia, acumulando el contexto
        de cada uno para el siguiente.

        Args:
            nombre_ubicacion: nombre exacto de la ubicación en BigQuery

        Returns:
            dict con boletín completo, nivel EAWS, metadata y resultados
            por subagente. Compatible con la interfaz v1.

        Raises:
            ErrorOrquestador: si algún subagente falla
        """
        inicio_total = time.time()
        logger.info(
            f"\n{'=' * 60}\n"
            f"ORQUESTADOR: iniciando análisis para '{nombre_ubicacion}'\n"
            f"{'=' * 60}"
        )

        contexto_acumulado = ""
        resultados_subagentes = {}
        tools_llamadas_total = []

        try:
            # ─── Subagente 1: Topográfico ─────────────────────────────────────
            logger.info("\n--- Subagente 1: Topográfico (DEM + PINNs) ---")
            resultado_topo = self.subagente_topografico.ejecutar(
                nombre_ubicacion=nombre_ubicacion,
                contexto_previo=None  # Primer subagente sin contexto previo
            )
            resultados_subagentes["topografico"] = resultado_topo
            tools_llamadas_total.extend(resultado_topo.get("tools_llamadas", []))

            # Actualizar contexto acumulado
            contexto_acumulado = self._construir_contexto(
                contexto_previo="",
                nombre_subagente="ANÁLISIS TOPOGRÁFICO (PINN)",
                analisis=resultado_topo.get("analisis", "")
            )
            logger.info(
                f"✓ Subagente Topográfico completado en "
                f"{resultado_topo.get('duracion_segundos', 0)}s"
            )

            # ─── Subagente 2: Satelital ───────────────────────────────────────
            logger.info("\n--- Subagente 2: Satelital (ViT) ---")
            resultado_sat = self.subagente_satelital.ejecutar(
                nombre_ubicacion=nombre_ubicacion,
                contexto_previo=contexto_acumulado
            )
            resultados_subagentes["satelital"] = resultado_sat
            tools_llamadas_total.extend(resultado_sat.get("tools_llamadas", []))

            contexto_acumulado = self._construir_contexto(
                contexto_previo=contexto_acumulado,
                nombre_subagente="ANÁLISIS SATELITAL (ViT)",
                analisis=resultado_sat.get("analisis", "")
            )
            logger.info(
                f"✓ Subagente Satelital completado en "
                f"{resultado_sat.get('duracion_segundos', 0)}s"
            )

            # ─── Subagente 3: Meteorológico ───────────────────────────────────
            logger.info("\n--- Subagente 3: Meteorológico ---")
            resultado_meteo = self.subagente_meteorologico.ejecutar(
                nombre_ubicacion=nombre_ubicacion,
                contexto_previo=contexto_acumulado
            )
            resultados_subagentes["meteorologico"] = resultado_meteo
            tools_llamadas_total.extend(resultado_meteo.get("tools_llamadas", []))

            contexto_acumulado = self._construir_contexto(
                contexto_previo=contexto_acumulado,
                nombre_subagente="ANÁLISIS METEOROLÓGICO",
                analisis=resultado_meteo.get("analisis", "")
            )
            logger.info(
                f"✓ Subagente Meteorológico completado en "
                f"{resultado_meteo.get('duracion_segundos', 0)}s"
            )

            # ─── Subagente 4: NLP Relatos ─────────────────────────────────────
            # NLP es no-crítico: si falla, el pipeline continúa con los datos
            # de los 3 subagentes anteriores + integrador
            logger.info("\n--- Subagente 4: NLP Relatos ---")
            try:
                resultado_nlp = self.subagente_nlp.ejecutar(
                    nombre_ubicacion=nombre_ubicacion,
                    contexto_previo=contexto_acumulado
                )
                resultados_subagentes["nlp"] = resultado_nlp
                tools_llamadas_total.extend(resultado_nlp.get("tools_llamadas", []))

                contexto_acumulado = self._construir_contexto(
                    contexto_previo=contexto_acumulado,
                    nombre_subagente="ANÁLISIS NLP RELATOS",
                    analisis=resultado_nlp.get("analisis", "")
                )
                logger.info(
                    f"✓ Subagente NLP completado en "
                    f"{resultado_nlp.get('duracion_segundos', 0)}s"
                )
            except Exception as exc_nlp:
                logger.warning(
                    f"⚠ Subagente NLP falló (no-crítico, continuando): {exc_nlp}"
                )
                resultados_subagentes["nlp"] = {
                    "analisis": f"[SubagenteNLP no disponible: {exc_nlp}]",
                    "tools_llamadas": [],
                    "iteraciones": 0,
                    "duracion_segundos": 0,
                    "error": str(exc_nlp),
                    "degradado": True,
                }
                contexto_acumulado = self._construir_contexto(
                    contexto_previo=contexto_acumulado,
                    nombre_subagente="ANÁLISIS NLP RELATOS",
                    analisis="[No disponible — sin datos históricos de relatos]"
                )

            # ─── Subagente 5: Integrador ──────────────────────────────────────
            logger.info("\n--- Subagente 5: Integrador EAWS ---")
            resultado_int = self.subagente_integrador.ejecutar(
                nombre_ubicacion=nombre_ubicacion,
                contexto_previo=contexto_acumulado
            )
            resultados_subagentes["integrador"] = resultado_int
            tools_llamadas_total.extend(resultado_int.get("tools_llamadas", []))
            logger.info(
                f"✓ Subagente Integrador completado en "
                f"{resultado_int.get('duracion_segundos', 0)}s"
            )

        except Exception as exc:
            logger.error(f"Error en orquestador: {exc}")
            raise ErrorOrquestador(
                f"Fallo en el sistema multi-agente para '{nombre_ubicacion}': {exc}"
            ) from exc

        # ─── Extraer boletín y nivel del integrador ───────────────────────────
        boletin_texto = resultado_int.get("analisis", "")
        nivel_eaws_24h = self._extraer_nivel(boletin_texto)

        duracion_total = round(time.time() - inicio_total, 1)

        logger.info(
            f"\n{'=' * 60}\n"
            f"ORQUESTADOR: análisis completado\n"
            f"Ubicación: {nombre_ubicacion}\n"
            f"Nivel EAWS 24h: {nivel_eaws_24h}\n"
            f"Duración total: {duracion_total}s\n"
            f"Tools llamadas: {len(tools_llamadas_total)}\n"
            f"{'=' * 60}"
        )

        # Detectar si algún subagente operó en modo degradado
        subagentes_degradados = [
            nombre for nombre, resultado in resultados_subagentes.items()
            if resultado.get("degradado")
        ]

        return {
            # Campos principales (compatibles con v1)
            "ubicacion": nombre_ubicacion,
            "boletin": boletin_texto,
            "nivel_eaws_24h": nivel_eaws_24h,
            "tools_llamadas": tools_llamadas_total,
            "iteraciones": sum(
                r.get("iteraciones", 0)
                for r in resultados_subagentes.values()
            ),
            "duracion_segundos": duracion_total,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "modelo": self.MODELO_SUBAGENTES,
            # Campos adicionales v2
            "arquitectura": "multi_agente_v3",
            "version_prompts": self._version_prompts,
            "subagentes_ejecutados": list(resultados_subagentes.keys()),
            "subagentes_degradados": subagentes_degradados,
            "duracion_por_subagente": {
                nombre: resultado.get("duracion_segundos", 0)
                for nombre, resultado in resultados_subagentes.items()
            },
            "resultados_subagentes": {
                nombre: {
                    "analisis": resultado.get("analisis", "")[:500] + "...",
                    "iteraciones": resultado.get("iteraciones"),
                    "duracion_segundos": resultado.get("duracion_segundos")
                }
                for nombre, resultado in resultados_subagentes.items()
            }
        }

    def generar_boletines_masivos(
        self,
        ubicaciones: Optional[list] = None
    ) -> list:
        """
        Genera boletines para múltiples ubicaciones.

        Args:
            ubicaciones: lista de ubicaciones. Si None, usa las primeras
                         10 ubicaciones con datos recientes.

        Returns:
            lista de dicts con resultados de cada boletín
        """
        from agentes.datos.consultor_bigquery import ConsultorBigQuery

        if ubicaciones is None:
            consultor = ConsultorBigQuery()
            ubicaciones = consultor.listar_ubicaciones_con_datos()[:10]
            logger.info(f"Usando primeras {len(ubicaciones)} ubicaciones con datos recientes")

        if not ubicaciones:
            logger.warning("No hay ubicaciones disponibles para generar boletines")
            return []

        resultados = []
        tamano_lote = 3  # Lotes más pequeños por la mayor complejidad del análisis
        pausa_entre_lotes = 5

        for i in range(0, len(ubicaciones), tamano_lote):
            lote = ubicaciones[i:i + tamano_lote]
            numero_lote = (i // tamano_lote) + 1
            total_lotes = (len(ubicaciones) + tamano_lote - 1) // tamano_lote

            logger.info(
                f"Procesando lote {numero_lote}/{total_lotes}: "
                f"{', '.join(lote)}"
            )

            for ubicacion in lote:
                try:
                    resultado = self.generar_boletin(ubicacion)
                    resultados.append(resultado)
                    logger.info(
                        f"✓ Boletín generado para {ubicacion} — "
                        f"nivel: {resultado.get('nivel_eaws_24h')}"
                    )
                except ErrorOrquestador as exc:
                    logger.error(f"✗ Error en {ubicacion}: {exc}")
                    resultados.append({
                        "ubicacion": ubicacion,
                        "error": str(exc),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                except Exception as exc:
                    logger.error(f"✗ Error inesperado en {ubicacion}: {exc}")
                    resultados.append({
                        "ubicacion": ubicacion,
                        "error": str(exc),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })

            if i + tamano_lote < len(ubicaciones):
                logger.info(f"Pausando {pausa_entre_lotes}s entre lotes...")
                time.sleep(pausa_entre_lotes)

        exitosos = sum(1 for r in resultados if "boletin" in r)
        logger.info(
            f"Generación masiva completada — "
            f"{exitosos}/{len(resultados)} boletines exitosos"
        )
        return resultados

    def _construir_contexto(
        self,
        contexto_previo: str,
        nombre_subagente: str,
        analisis: str
    ) -> str:
        """
        Construye el contexto acumulado para el siguiente subagente.

        Args:
            contexto_previo: contexto ya acumulado
            nombre_subagente: nombre del subagente que acaba de completar
            analisis: texto del análisis del subagente

        Returns:
            string con el contexto actualizado
        """
        # Limitar el tamaño del contexto para no saturar el prompt
        # Mantener máximo 3000 caracteres por subagente
        analisis_truncado = analisis[:3000] + "..." if len(analisis) > 3000 else analisis

        nuevo_bloque = (
            f"\n\n[{nombre_subagente}]\n"
            f"{analisis_truncado}"
        )

        # Limitar el contexto total
        contexto_nuevo = contexto_previo + nuevo_bloque
        if len(contexto_nuevo) > 12000:
            # Mantener solo los últimos ~12000 caracteres
            contexto_nuevo = "...[contexto anterior truncado]...\n" + contexto_nuevo[-11000:]

        return contexto_nuevo

    def _extraer_nivel(self, boletin: str) -> Optional[int]:
        """
        Extrae el nivel EAWS 24h del texto del boletín con regex.

        Args:
            boletin: texto del boletín generado

        Returns:
            int con el nivel EAWS (1-5) o None si no se encuentra
        """
        # Buscar "24h → N" o "24h: N" o "Nivel X"
        patrones = [
            r'24h\s*[→\-:]\s*(\d)',
            r'NIVEL DE PELIGRO.*?24h.*?(\d)',
            r'Nivel\s+(\d)\s*\(',
        ]
        for patron in patrones:
            match = re.search(patron, boletin, re.IGNORECASE | re.DOTALL)
            if match:
                nivel = int(match.group(1))
                if 1 <= nivel <= 5:
                    return nivel
        return None


# ─── Alias de retrocompatibilidad con v1 ──────────────────────────────────────

class AgenteRiesgoAvalancha(OrquestadorAvalancha):
    """
    Alias de retrocompatibilidad con la interfaz v1.

    Los scripts y tests existentes que usan AgenteRiesgoAvalancha
    seguirán funcionando sin modificación.
    """

    MODELO = "claude-sonnet-4-5"

    def __init__(self):
        super().__init__()
        logger.info(
            "AgenteRiesgoAvalancha: usando OrquestadorAvalancha v2 "
            "(multi-agente con PINNs + ViT)"
        )
