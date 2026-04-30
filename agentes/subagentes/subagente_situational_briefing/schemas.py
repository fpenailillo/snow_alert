"""
Schemas Pydantic para el Situational Briefing (S4 v2).

SituationalBriefing es el artefacto principal que produce el agente.
Producido por AgenteSituationalBriefing (Qwen3-80B vía Databricks).
"""

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


class CondicionesRecientes(BaseModel):
    """Resumen de condiciones meteorológicas de las últimas 72 horas."""
    temperatura_promedio_c: float = Field(description="Temperatura media 72h en °C")
    temperatura_min_c: float = Field(description="Temperatura mínima 72h en °C")
    temperatura_max_c: float = Field(description="Temperatura máxima 72h en °C")
    precipitacion_acumulada_mm: float = Field(description="Precipitación acumulada 72h en mm")
    viento_max_kmh: float = Field(description="Velocidad máxima de viento 72h en km/h")
    direccion_viento_dominante: str = Field(description="Dirección dominante: N, NE, E, SE, S, SW, W, NW")
    humedad_relativa_pct: float = Field(description="Humedad relativa promedio en %")
    condicion_predominante: str = Field(description="Condición predominante (ej: despejado, nevando, lluvia)")
    eventos_destacables: list[str] = Field(
        default_factory=list,
        description="Eventos notables como frentes fríos, ráfagas extremas, nevadas"
    )


class ContextoHistorico(BaseModel):
    """Contexto climatológico y estacional de la zona."""
    epoca_estacional: Literal[
        "pre-temporada", "temporada-temprana", "mid-winter", "primavera", "fin-temporada"
    ] = Field(description="Época del año respecto al ciclo de nieve andino (Hemisferio Sur)")
    mes_actual: str = Field(description="Mes y año actual")
    patron_climatologico_tipico: str = Field(
        description="Descripción breve del patrón climático típico para esta época en la zona"
    )
    desviacion_vs_normal: str = Field(
        description="Diferencia con el promedio histórico (ej: '5°C sobre el promedio', 'precipitación normal')"
    )
    nivel_nieve_estacional: Literal["bajo", "normal", "alto", "sin_datos"] = Field(
        description="Estimación cualitativa del nivel de nieve acumulada vs promedio estacional"
    )


class CaracteristicasZona(BaseModel):
    """Características topográficas relevantes para EAWS."""
    nombre_zona: str
    altitud_minima_m: int = Field(description="Altitud mínima de la zona esquiable en metros")
    altitud_maxima_m: int = Field(description="Altitud máxima en metros")
    orientaciones_criticas: list[str] = Field(
        description="Orientaciones con mayor riesgo de acumulación o desprendimiento"
    )
    rangos_pendiente_eaws: list[str] = Field(
        description="Rangos de pendiente predominantes según EAWS: <30°, 30-35°, 35-45°, 45-60°, >60°"
    )
    caracteristicas_especiales: list[str] = Field(
        default_factory=list,
        description="Características relevantes: glaciares, cornisas típicas, zonas de depósito"
    )


class SituationalBriefing(BaseModel):
    """
    Briefing situacional estructurado para la zona.
    Alimenta a S5 (Integrador EAWS) como contexto cualitativo.
    """
    zona: str
    timestamp_generacion: str = Field(description="ISO 8601 timestamp de generación")
    horizonte_validez_h: int = Field(default=24, description="Horas de validez del briefing")

    condiciones_recientes: CondicionesRecientes
    contexto_historico: ContextoHistorico
    caracteristicas_zona: CaracteristicasZona

    narrativa_integrada: str = Field(
        description=(
            "Descripción narrativa en español de Chile, 150-300 palabras. "
            "Integra condiciones recientes, contexto estacional y características topográficas. "
            "Enfocada en factores relevantes para peligro de avalanchas EAWS."
        )
    )

    factores_atencion_eaws: list[str] = Field(
        description=(
            "Lista de 3-6 factores de atención específicos para el integrador EAWS. "
            "Ej: 'Viento SE cargando pendientes N-NW', 'Temperatura en umbral de fusión'"
        )
    )

    # Campos de compatibilidad con S5 (mantiene interfaz del S4 anterior)
    indice_riesgo_cualitativo: Literal["bajo", "moderado", "considerable", "alto", "muy_alto"] = Field(
        description="Estimación cualitativa del riesgo basada en condiciones recientes y contexto"
    )
    tipo_problema_probable: Literal[
        "placa_viento", "nieve_reciente", "nieve_humeda", "avalancha_fondo", "mixto", "sin_datos"
    ] = Field(description="Tipo de problema de avalancha más probable para la época y condiciones")

    confianza: Literal["alta", "media", "baja"] = Field(
        description="Confianza en el briefing según disponibilidad de datos"
    )
    fuentes_datos: list[str] = Field(
        description="Fuentes de datos usadas: tabla BQ, cálculos climatológicos, etc."
    )
