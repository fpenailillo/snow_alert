"""
Consultor de BigQuery para el Sistema de Predicción de Avalanchas

Clase centralizada que accede a las 5 tablas de datos del proyecto
climas-chileno y retorna diccionarios compatibles con tool_use de Anthropic.

Reglas:
- Todos los métodos retornan dict (nunca DataFrame)
- Nunca lanzar excepciones — siempre retornar {"error": "..."} si falla
- Timeout de 30 segundos por query
- Consultas parametrizadas (nunca f-strings con SQL)
- Logging del tiempo de ejecución
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import concurrent.futures

from google.cloud import bigquery
from google.api_core import exceptions as google_exceptions


# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ErrorConexionBigQuery(Exception):
    """Excepción para errores de conexión con BigQuery."""
    pass


class ConsultorBigQuery:
    """
    Acceso centralizado a las tablas de BigQuery del proyecto climas-chileno.

    Todos los métodos retornan dict para compatibilidad con tool_use de Anthropic.
    Nunca lanzan excepciones: errores se retornan como {"error": "mensaje"}.
    """

    GCP_PROJECT = "climas-chileno"
    DATASET = "clima"
    TIMEOUT_SEGUNDOS = 30

    def __init__(self):
        """Inicializa el cliente de BigQuery con Application Default Credentials."""
        try:
            self.cliente = bigquery.Client(project=self.GCP_PROJECT)
            logger.info(f"ConsultorBigQuery inicializado para proyecto: {self.GCP_PROJECT}")
        except Exception as e:
            logger.error(f"Error al inicializar cliente BigQuery: {e}")
            raise ErrorConexionBigQuery(f"No se pudo conectar a BigQuery: {e}")

    def _ejecutar_query(self, sql: str, parametros: list) -> list:
        """
        Ejecuta una query parametrizada con timeout.

        Args:
            sql: Consulta SQL con placeholders @nombre
            parametros: Lista de bigquery.ScalarQueryParameter

        Returns:
            Lista de filas como dicts

        Raises:
            Exception: Si la query falla (manejado por los métodos públicos)
        """
        config_job = bigquery.QueryJobConfig(
            query_parameters=parametros
        )

        inicio = time.time()
        job = self.cliente.query(sql, job_config=config_job)
        filas = list(job.result(timeout=self.TIMEOUT_SEGUNDOS))
        duracion = round(time.time() - inicio, 2)

        logger.info(f"Query ejecutada en {duracion}s — {len(filas)} filas obtenidas")
        return [dict(fila) for fila in filas]

    def obtener_condiciones_actuales(self, ubicacion: str) -> dict:
        """
        Última fila de condiciones_actuales para la ubicación. Max antigüedad: 12h.

        Args:
            ubicacion: Nombre exacto de la ubicación

        Returns:
            dict con campos climáticos actuales, o {"disponible": False, "razon": "..."}
        """
        logger.info(f"Consultando condiciones actuales para: {ubicacion}")
        try:
            sql = """
                SELECT
                    temperatura,
                    sensacion_termica,
                    velocidad_viento,
                    direccion_viento,
                    precipitacion_acumulada,
                    probabilidad_precipitacion,
                    humedad_relativa,
                    presion_aire,
                    cobertura_nubes,
                    condicion_clima,
                    hora_actual,
                    es_dia
                FROM `{proyecto}.{dataset}.condiciones_actuales`
                WHERE nombre_ubicacion = @ubicacion
                  AND hora_actual >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 12 HOUR)
                ORDER BY hora_actual DESC
                LIMIT 1
            """.format(proyecto=self.GCP_PROJECT, dataset=self.DATASET)

            parametros = [
                bigquery.ScalarQueryParameter("ubicacion", "STRING", ubicacion)
            ]

            filas = self._ejecutar_query(sql, parametros)

            if not filas:
                logger.warning(f"Sin condiciones actuales recientes para: {ubicacion}")
                return {
                    "disponible": False,
                    "razon": "Sin datos en las últimas 12 horas"
                }

            resultado = filas[0]
            resultado["disponible"] = True

            # Serializar tipos especiales
            if resultado.get("hora_actual") and hasattr(resultado["hora_actual"], "isoformat"):
                resultado["hora_actual"] = resultado["hora_actual"].isoformat()

            return resultado

        except (google_exceptions.DeadlineExceeded, concurrent.futures.TimeoutError):
            logger.error(f"Timeout al consultar condiciones actuales para: {ubicacion}")
            return {"error": f"Timeout después de {self.TIMEOUT_SEGUNDOS}s"}
        except Exception as e:
            logger.error(f"Error consultando condiciones actuales para {ubicacion}: {e}")
            return {"error": str(e)}

    def obtener_tendencia_meteorologica(self, ubicacion: str) -> dict:
        """
        Resumen estadístico de las últimas 72h de pronostico_horas + próximas 48h.

        Args:
            ubicacion: Nombre exacto de la ubicación

        Returns:
            dict con estadísticas resumidas de temperatura, viento, precipitación y alertas
        """
        logger.info(f"Consultando tendencia meteorológica para: {ubicacion}")
        try:
            # Query de las últimas 72h
            sql_pasado = """
                SELECT
                    temperatura,
                    velocidad_viento,
                    probabilidad_precipitacion,
                    cantidad_precipitacion,
                    hora_inicio
                FROM `{proyecto}.{dataset}.pronostico_horas`
                WHERE nombre_ubicacion = @ubicacion
                  AND hora_inicio >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 72 HOUR)
                  AND hora_inicio <= CURRENT_TIMESTAMP()
                ORDER BY hora_inicio ASC
            """.format(proyecto=self.GCP_PROJECT, dataset=self.DATASET)

            # Query de las próximas 48h
            sql_futuro = """
                SELECT
                    temperatura,
                    velocidad_viento,
                    probabilidad_precipitacion,
                    cantidad_precipitacion,
                    hora_inicio
                FROM `{proyecto}.{dataset}.pronostico_horas`
                WHERE nombre_ubicacion = @ubicacion
                  AND hora_inicio > CURRENT_TIMESTAMP()
                  AND hora_inicio <= TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 48 HOUR)
                ORDER BY hora_inicio ASC
            """.format(proyecto=self.GCP_PROJECT, dataset=self.DATASET)

            parametros = [
                bigquery.ScalarQueryParameter("ubicacion", "STRING", ubicacion)
            ]

            filas_pasado = self._ejecutar_query(sql_pasado, parametros)
            filas_futuro = self._ejecutar_query(sql_futuro, parametros)

            if not filas_pasado and not filas_futuro:
                return {
                    "disponible": False,
                    "razon": "Sin datos de pronóstico horario"
                }

            todas_filas = filas_pasado + filas_futuro

            # Calcular estadísticas
            temperaturas = [f["temperatura"] for f in todas_filas if f.get("temperatura") is not None]
            vientos = [f["velocidad_viento"] for f in todas_filas if f.get("velocidad_viento") is not None]
            precipitaciones = [f["cantidad_precipitacion"] for f in todas_filas if f.get("cantidad_precipitacion") is not None]

            temp_min_72h = min(temperaturas) if temperaturas else None
            temp_max_72h = max(temperaturas) if temperaturas else None
            precip_total_acumulada_mm = sum(precipitaciones) if precipitaciones else 0
            viento_max_ms = max(vientos) if vientos else None

            # Hora de viento máximo
            hora_viento_max = None
            if vientos and viento_max_ms is not None:
                for f in todas_filas:
                    if f.get("velocidad_viento") == viento_max_ms:
                        if f.get("hora_inicio") and hasattr(f["hora_inicio"], "isoformat"):
                            hora_viento_max = f["hora_inicio"].isoformat()
                        elif f.get("hora_inicio"):
                            hora_viento_max = str(f["hora_inicio"])
                        break

            # Horas con precipitación probable (>50%)
            horas_con_precipitacion = sum(
                1 for f in todas_filas
                if f.get("probabilidad_precipitacion") and f["probabilidad_precipitacion"] > 50
            )

            # Tendencia de temperatura (últimas vs primeras horas disponibles)
            tendencia_temperatura = "estable"
            if len(temperaturas) >= 6:
                tercio = len(temperaturas) // 3
                temp_inicio = sum(temperaturas[:tercio]) / tercio
                temp_fin = sum(temperaturas[-tercio:]) / tercio
                diferencia = temp_fin - temp_inicio
                if diferencia < -2:
                    tendencia_temperatura = "bajando"
                elif diferencia > 2:
                    tendencia_temperatura = "subiendo"

            # Alertas automáticas
            alertas = []
            if precip_total_acumulada_mm > 30:
                alertas.append({
                    "tipo": "PRECIPITACION_CRITICA",
                    "valor": f"{round(precip_total_acumulada_mm, 1)}mm en 72h"
                })
            if viento_max_ms and viento_max_ms > 15:
                alertas.append({
                    "tipo": "VIENTO_FUERTE",
                    "hora": hora_viento_max,
                    "valor": f"{round(viento_max_ms, 1)} m/s ({round(viento_max_ms * 3.6, 1)} km/h)"
                })
            if temp_min_72h is not None and temp_max_72h is not None:
                if abs(temp_max_72h - temp_min_72h) > 15:
                    alertas.append({
                        "tipo": "CAMBIO_TERMICO",
                        "valor": f"variación de {round(abs(temp_max_72h - temp_min_72h), 1)}°C"
                    })

            return {
                "disponible": True,
                "temp_min_72h": round(temp_min_72h, 1) if temp_min_72h is not None else None,
                "temp_max_72h": round(temp_max_72h, 1) if temp_max_72h is not None else None,
                "precip_total_acumulada_mm": round(precip_total_acumulada_mm, 1),
                "viento_max_ms": round(viento_max_ms, 1) if viento_max_ms is not None else None,
                "hora_viento_max": hora_viento_max,
                "horas_con_precipitacion": horas_con_precipitacion,
                "tendencia_temperatura": tendencia_temperatura,
                "alertas": alertas
            }

        except (google_exceptions.DeadlineExceeded, concurrent.futures.TimeoutError):
            logger.error(f"Timeout al consultar tendencia meteorológica para: {ubicacion}")
            return {"error": f"Timeout después de {self.TIMEOUT_SEGUNDOS}s"}
        except Exception as e:
            logger.error(f"Error consultando tendencia meteorológica para {ubicacion}: {e}")
            return {"error": str(e)}

    def obtener_pronostico_proximos_dias(self, ubicacion: str) -> dict:
        """
        Próximos 3 días de pronostico_dias.

        Args:
            ubicacion: Nombre exacto de la ubicación

        Returns:
            dict con lista de 3 días de pronóstico
        """
        logger.info(f"Consultando pronóstico de días para: {ubicacion}")
        try:
            sql = """
                SELECT
                    fecha_inicio,
                    fecha_fin,
                    temp_max_dia,
                    temp_min_dia,
                    diurno_condicion,
                    nocturno_condicion,
                    diurno_prob_precipitacion,
                    nocturno_prob_precipitacion,
                    diurno_viento_max,
                    nocturno_viento_max
                FROM `{proyecto}.{dataset}.pronostico_dias`
                WHERE nombre_ubicacion = @ubicacion
                  AND fecha_inicio >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
                ORDER BY fecha_inicio ASC
                LIMIT 3
            """.format(proyecto=self.GCP_PROJECT, dataset=self.DATASET)

            parametros = [
                bigquery.ScalarQueryParameter("ubicacion", "STRING", ubicacion)
            ]

            filas = self._ejecutar_query(sql, parametros)

            if not filas:
                return {
                    "disponible": False,
                    "razon": "Sin pronóstico de días disponible"
                }

            # Serializar fechas
            dias = []
            for fila in filas:
                dia = dict(fila)
                for campo in ["fecha_inicio", "fecha_fin"]:
                    if dia.get(campo) and hasattr(dia[campo], "isoformat"):
                        dia[campo] = dia[campo].isoformat()
                    elif dia.get(campo):
                        dia[campo] = str(dia[campo])

                # Calcular prob_precipitacion_dia (máximo entre diurno y nocturno)
                prob_dia = dia.get("diurno_prob_precipitacion")
                prob_noche = dia.get("nocturno_prob_precipitacion")
                if prob_dia is not None and prob_noche is not None:
                    dia["prob_precipitacion_dia"] = max(prob_dia, prob_noche)
                elif prob_dia is not None:
                    dia["prob_precipitacion_dia"] = prob_dia
                elif prob_noche is not None:
                    dia["prob_precipitacion_dia"] = prob_noche

                # viento_max (máximo entre diurno y nocturno)
                viento_dia = dia.get("diurno_viento_max")
                viento_noche = dia.get("nocturno_viento_max")
                if viento_dia is not None and viento_noche is not None:
                    dia["viento_max"] = max(viento_dia, viento_noche)
                elif viento_dia is not None:
                    dia["viento_max"] = viento_dia
                elif viento_noche is not None:
                    dia["viento_max"] = viento_noche

                # condicion_dia (priorizar diurna)
                dia["condicion_dia"] = dia.get("diurno_condicion") or dia.get("nocturno_condicion")

                dias.append(dia)

            return {
                "disponible": True,
                "dias": dias
            }

        except (google_exceptions.DeadlineExceeded, concurrent.futures.TimeoutError):
            logger.error(f"Timeout al consultar pronóstico de días para: {ubicacion}")
            return {"error": f"Timeout después de {self.TIMEOUT_SEGUNDOS}s"}
        except Exception as e:
            logger.error(f"Error consultando pronóstico de días para {ubicacion}: {e}")
            return {"error": str(e)}

    def obtener_estado_satelital(self, ubicacion: str) -> dict:
        """
        Última fila de imagenes_satelitales. Max antigüedad: 48h.

        Args:
            ubicacion: Nombre exacto de la ubicación

        Returns:
            dict con estado del manto nival, o {"disponible": False, "razon": "..."}
        """
        logger.info(f"Consultando estado satelital para: {ubicacion}")
        try:
            sql = """
                SELECT
                    pct_cobertura_nieve,
                    ndsi_medio,
                    lst_dia_celsius,
                    lst_noche_celsius,
                    ciclo_diurno_amplitud,
                    snowline_elevacion_m,
                    delta_pct_nieve_24h,
                    tipo_cambio_nieve,
                    ami_7d,
                    ami_3d,
                    sar_disponible,
                    sar_pct_nieve_humeda,
                    transporte_eolico_activo,
                    viento_altura_vel_kmh,
                    fecha_captura
                FROM `{proyecto}.{dataset}.imagenes_satelitales`
                WHERE nombre_ubicacion = @ubicacion
                  AND fecha_captura >= DATE_SUB(CURRENT_DATE(), INTERVAL 2 DAY)
                ORDER BY fecha_captura DESC
                LIMIT 1
            """.format(proyecto=self.GCP_PROJECT, dataset=self.DATASET)

            parametros = [
                bigquery.ScalarQueryParameter("ubicacion", "STRING", ubicacion)
            ]

            filas = self._ejecutar_query(sql, parametros)

            if not filas:
                logger.warning(f"Sin datos satelitales recientes (<48h) para: {ubicacion}")
                return {
                    "disponible": False,
                    "razon": "sin datos <48h"
                }

            resultado = filas[0]
            resultado["disponible"] = True

            # Serializar fecha
            if resultado.get("fecha_captura") and hasattr(resultado["fecha_captura"], "isoformat"):
                resultado["fecha_captura"] = resultado["fecha_captura"].isoformat()

            return resultado

        except (google_exceptions.DeadlineExceeded, concurrent.futures.TimeoutError):
            logger.error(f"Timeout al consultar estado satelital para: {ubicacion}")
            return {"error": f"Timeout después de {self.TIMEOUT_SEGUNDOS}s"}
        except Exception as e:
            logger.error(f"Error consultando estado satelital para {ubicacion}: {e}")
            return {"error": str(e)}

    def obtener_perfil_topografico(self, ubicacion: str) -> dict:
        """
        Última fila de zonas_avalancha. Puede tener hasta 45 días de antigüedad.

        Args:
            ubicacion: Nombre exacto de la ubicación

        Returns:
            dict con perfil topográfico e índice de riesgo base EAWS
        """
        logger.info(f"Consultando perfil topográfico para: {ubicacion}")
        try:
            sql = """
                SELECT
                    indice_riesgo_topografico,
                    clasificacion_riesgo,
                    peligro_eaws_base,
                    frecuencia_estimada_eaws,
                    tamano_estimado_eaws,
                    zona_inicio_ha,
                    zona_inicio_pct,
                    pendiente_max_inicio,
                    pendiente_media_inicio,
                    desnivel_inicio_deposito,
                    aspecto_predominante_inicio,
                    descripcion_riesgo,
                    fecha_analisis,
                    latitud,
                    hemisferio
                FROM `{proyecto}.{dataset}.zonas_avalancha`
                WHERE nombre_ubicacion = @ubicacion
                ORDER BY fecha_analisis DESC
                LIMIT 1
            """.format(proyecto=self.GCP_PROJECT, dataset=self.DATASET)

            parametros = [
                bigquery.ScalarQueryParameter("ubicacion", "STRING", ubicacion)
            ]

            filas = self._ejecutar_query(sql, parametros)

            if not filas:
                return {
                    "disponible": False,
                    "razon": "Sin análisis topográfico disponible"
                }

            resultado = filas[0]
            resultado["disponible"] = True

            # Serializar fecha
            if resultado.get("fecha_analisis") and hasattr(resultado["fecha_analisis"], "isoformat"):
                resultado["fecha_analisis"] = resultado["fecha_analisis"].isoformat()

            # Computar campos derivados desde eaws_constantes
            import sys
            import os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../analizador_avalanchas'))
            try:
                from eaws_constantes import categorizar_aspecto, es_aspecto_sombra, detectar_hemisferio
                aspecto = resultado.get("aspecto_predominante_inicio")
                latitud = resultado.get("latitud", -33.0)  # Andes chilenos como default
                hemisferio = resultado.get("hemisferio") or detectar_hemisferio(latitud)

                if aspecto is not None:
                    resultado["categoria_aspecto"] = categorizar_aspecto(aspecto)
                    resultado["es_aspecto_sombra"] = es_aspecto_sombra(aspecto, hemisferio)
                else:
                    resultado["categoria_aspecto"] = None
                    resultado["es_aspecto_sombra"] = None
            except ImportError as e:
                logger.warning(f"No se pudo importar eaws_constantes: {e}")
                resultado["categoria_aspecto"] = None
                resultado["es_aspecto_sombra"] = None

            return resultado

        except (google_exceptions.DeadlineExceeded, concurrent.futures.TimeoutError):
            logger.error(f"Timeout al consultar perfil topográfico para: {ubicacion}")
            return {"error": f"Timeout después de {self.TIMEOUT_SEGUNDOS}s"}
        except Exception as e:
            logger.error(f"Error consultando perfil topográfico para {ubicacion}: {e}")
            return {"error": str(e)}

    def listar_ubicaciones_con_datos(self) -> list:
        """
        Ubicaciones con condiciones_actuales en las últimas 24h.

        Returns:
            Lista de nombres de ubicaciones con datos recientes
        """
        logger.info("Listando ubicaciones con datos recientes")
        try:
            sql = """
                SELECT DISTINCT nombre_ubicacion
                FROM `{proyecto}.{dataset}.condiciones_actuales`
                WHERE hora_actual >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
                ORDER BY nombre_ubicacion ASC
            """.format(proyecto=self.GCP_PROJECT, dataset=self.DATASET)

            filas = self._ejecutar_query(sql, [])
            ubicaciones = [f["nombre_ubicacion"] for f in filas]

            logger.info(f"Se encontraron {len(ubicaciones)} ubicaciones con datos recientes")
            return ubicaciones

        except (google_exceptions.DeadlineExceeded, concurrent.futures.TimeoutError):
            logger.error("Timeout al listar ubicaciones")
            return []
        except Exception as e:
            logger.error(f"Error listando ubicaciones: {e}")
            return []

    def obtener_relatos_ubicacion(self, ubicacion: str, limite: int = 20) -> dict:
        """
        Relatos históricos de montañistas para la ubicación o zona cercana.

        Busca por similitud en ubicacion_mencionada con LIKE para encontrar
        relatos aunque el nombre no sea exacto.

        Args:
            ubicacion: Nombre de la ubicación (busca coincidencias parciales)
            limite: Número máximo de relatos a retornar (default: 20)

        Returns:
            dict con lista de relatos y metadatos de búsqueda
        """
        logger.info(f"Buscando relatos para ubicación: {ubicacion}")
        try:
            # Extraer palabra clave de la ubicación (ej: "La Parva Sector Bajo" → "La Parva")
            palabras = ubicacion.split()
            termino_busqueda = " ".join(palabras[:3]) if len(palabras) >= 3 else ubicacion

            sql = """
                SELECT
                    id_relato,
                    titulo,
                    SUBSTR(texto_completo, 1, 500) as fragmento_texto,
                    fecha_relato,
                    ubicacion_mencionada,
                    url_fuente,
                    fuente
                FROM `{proyecto}.{dataset}.relatos_montanistas`
                WHERE
                    LOWER(ubicacion_mencionada) LIKE LOWER(@termino)
                    OR LOWER(titulo) LIKE LOWER(@termino)
                ORDER BY fecha_relato DESC
                LIMIT @limite
            """.format(proyecto=self.GCP_PROJECT, dataset=self.DATASET)

            parametros = [
                bigquery.ScalarQueryParameter("termino", "STRING", f"%{termino_busqueda}%"),
                bigquery.ScalarQueryParameter("limite", "INT64", limite),
            ]

            filas = self._ejecutar_query(sql, parametros)

            if not filas:
                # Si no hay resultados exactos, buscar por primera palabra (zona general)
                primera_palabra = palabras[0]
                sql_amplio = sql.replace("@termino", "@termino_amplio")
                parametros_amplio = [
                    bigquery.ScalarQueryParameter("termino_amplio", "STRING", f"%{primera_palabra}%"),
                    bigquery.ScalarQueryParameter("limite", "INT64", limite),
                ]
                filas = self._ejecutar_query(sql_amplio, parametros_amplio)

            # Serializar fechas
            for fila in filas:
                if fila.get("fecha_relato") and hasattr(fila["fecha_relato"], "isoformat"):
                    fila["fecha_relato"] = fila["fecha_relato"].isoformat()

            logger.info(f"  {len(filas)} relatos encontrados para: {ubicacion}")
            return {
                "disponible": True,
                "relatos": filas,
                "total_encontrados": len(filas),
                "termino_busqueda": termino_busqueda,
            }

        except Exception as e:
            tabla_msg = "relatos_montanistas no existe" if "Not found" in str(e) else str(e)
            logger.warning(f"Error buscando relatos para {ubicacion}: {tabla_msg}")
            return {
                "disponible": False,
                "relatos": [],
                "total_encontrados": 0,
                "razon": tabla_msg,
            }

    def buscar_relatos_condiciones(self, terminos: list, limite: int = 10) -> dict:
        """
        Busca relatos que mencionen términos específicos de condiciones de riesgo.

        Útil para el SubagenteNLP para encontrar patrones históricos relacionados
        con condiciones actuales (ej: "placa", "viento", "nieve blanda").

        Args:
            terminos: Lista de palabras clave a buscar en el texto de relatos
            limite: Número máximo de relatos por término (default: 10)

        Returns:
            dict con fragmentos relevantes, frecuencias y patrones detectados
        """
        logger.info(f"Buscando relatos con términos: {terminos}")
        if not terminos:
            return {"disponible": False, "razon": "Lista de términos vacía"}

        try:
            resultados_por_termino = {}
            todos_los_ids = set()

            for termino in terminos[:8]:  # Limitar a 8 términos para no saturar BQ
                sql = """
                    SELECT
                        id_relato,
                        titulo,
                        SUBSTR(texto_completo, 1, 300) as fragmento,
                        fecha_relato,
                        ubicacion_mencionada,
                        @termino as termino_encontrado
                    FROM `{proyecto}.{dataset}.relatos_montanistas`
                    WHERE LOWER(texto_completo) LIKE LOWER(CONCAT('%', @termino, '%'))
                       OR LOWER(titulo) LIKE LOWER(CONCAT('%', @termino, '%'))
                    ORDER BY fecha_relato DESC
                    LIMIT @limite
                """.format(proyecto=self.GCP_PROJECT, dataset=self.DATASET)

                parametros = [
                    bigquery.ScalarQueryParameter("termino", "STRING", termino),
                    bigquery.ScalarQueryParameter("limite", "INT64", limite),
                ]

                filas = self._ejecutar_query(sql, parametros)

                # Serializar fechas
                for fila in filas:
                    if fila.get("fecha_relato") and hasattr(fila["fecha_relato"], "isoformat"):
                        fila["fecha_relato"] = fila["fecha_relato"].isoformat()
                    todos_los_ids.add(fila.get("id_relato", ""))

                if filas:
                    resultados_por_termino[termino] = filas
                    logger.info(f"  '{termino}': {len(filas)} coincidencias")

            # Calcular índice de riesgo histórico basado en frecuencia de términos críticos
            terminos_criticos = {"alud", "avalancha", "placa", "peligroso", "inestable", "grieta"}
            frecuencia_criticos = sum(
                len(v) for k, v in resultados_por_termino.items()
                if k.lower() in terminos_criticos
            )
            total_menciones = sum(len(v) for v in resultados_por_termino.values())
            indice_riesgo = min(1.0, frecuencia_criticos / max(total_menciones, 1))

            return {
                "disponible": True,
                "resultados_por_termino": resultados_por_termino,
                "total_relatos_unicos": len(todos_los_ids),
                "total_menciones": total_menciones,
                "frecuencia_terminos_criticos": frecuencia_criticos,
                "indice_riesgo_calculado": round(indice_riesgo, 3),
                "terminos_buscados": terminos,
            }

        except Exception as e:
            tabla_msg = "relatos_montanistas no existe" if "Not found" in str(e) else str(e)
            logger.warning(f"Error buscando relatos por condiciones: {tabla_msg}")
            return {
                "disponible": False,
                "resultados_por_termino": {},
                "total_relatos_unicos": 0,
                "indice_riesgo_calculado": 0.0,
                "razon": tabla_msg,
            }
