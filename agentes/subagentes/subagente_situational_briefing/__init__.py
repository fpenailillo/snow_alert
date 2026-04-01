"""
Subagente Situational Briefing (S4 v2) — Genera descripción narrativa de la zona.

Reemplaza SubagenteNLP (scraping + sentiment). Usa Gemini 2.5 Flash vía Vertex AI
para producir un briefing estructurado combinando condiciones recientes, contexto
histórico-climatológico y características topográficas de la zona.

Fallback: si Vertex AI falla, genera briefing textual a partir de datos crudos.
"""

from agentes.subagentes.subagente_situational_briefing.agente import (
    AgenteSituationalBriefing,
)

__all__ = ["AgenteSituationalBriefing"]
