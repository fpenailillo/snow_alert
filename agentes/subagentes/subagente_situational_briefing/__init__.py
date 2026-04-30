"""
Subagente Situational Briefing (S4 v2) — Genera descripción narrativa de la zona.

Reemplaza SubagenteNLP (scraping + sentiment). Usa Qwen3-80B vía Databricks
para producir un briefing estructurado combinando condiciones recientes, contexto
histórico-climatológico y características topográficas de la zona.
"""

from agentes.subagentes.subagente_situational_briefing.agente import (
    AgenteSituationalBriefing,
)

__all__ = ["AgenteSituationalBriefing"]
