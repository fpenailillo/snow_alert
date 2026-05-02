"""
Registro de Versiones de Prompts — Sistema Multi-Agente Avalanchas

Permite rastrear qué versión exacta de cada prompt se usó para generar
un boletín. Fundamental para reproducibilidad académica (tesina).

Cada prompt se identifica por:
- componente: nombre del subagente o módulo
- version: semver (e.g. "3.1.0")
- hash_sha256: hash del contenido para verificar integridad

Uso:
    from agentes.prompts.registro_versiones import (
        obtener_version_actual,
        verificar_integridad,
        REGISTRO_PROMPTS
    )

    version = obtener_version_actual()  # "v3.1"
    ok = verificar_integridad()         # True si todos los hashes coinciden
"""

import hashlib
import importlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ─── Registro central de prompts ────────────────────────────────────────────
# Actualizar este registro cada vez que se modifique un prompt.
# El hash se genera con _calcular_hash() sobre el contenido del prompt.
#
# Para regenerar hashes después de editar un prompt:
#   python -m agentes.prompts.registro_versiones --actualizar-hashes

REGISTRO_PROMPTS = {
    "orquestador": {
        "modulo": "agentes.orquestador.prompts",
        "variable": "SYSTEM_PROMPT",
        "version": "3.0.0",
        "descripcion": "Pipeline 6 pasos: DEM → satélite → meteo → EAWS → boletín",
        "hash_sha256": "50c62aa5b22af4bf",
    },
    "topografico": {
        "modulo": "agentes.subagentes.subagente_topografico.prompts",
        "variable": "SYSTEM_PROMPT_TOPOGRAFICO",
        "version": "3.0.0",
        "descripcion": "PINN con Mohr-Coulomb, difusión térmica, gradiente desde LST satelital",
        "hash_sha256": "1ceef64e71741bc4",
    },
    "satelital": {
        "modulo": "agentes.subagentes.subagente_satelital.prompts",
        "variable": "SYSTEM_PROMPT_SATELITAL",
        "version": "4.0.0",
        "descripcion": "ViT + estado manto: MODIS LST + ERA5 suelo + SAR humedad superficial (REQ-02a/02b)",
        "hash_sha256": "be0b1be58880835c",
    },
    "meteorologico": {
        "modulo": "agentes.subagentes.subagente_meteorologico.prompts",
        "variable": "SYSTEM_PROMPT_METEOROLOGICO",
        "version": "5.0.0",
        "descripcion": "REQ-06: CICLO_DIURNO_NORMAL neutro vs FUSION_ACTIVA_CON_CARGA; precipitacion_72h_mm chain",
        "hash_sha256": "819b6fddb6adf48a",
    },
    "nlp": {
        "modulo": "agentes.subagentes.subagente_nlp.prompts",
        "variable": "SYSTEM_PROMPT_NLP",
        "version": "3.1.0",
        "descripcion": "Análisis relatos Andeshandbook, índice riesgo histórico + guía conversión frecuencias",
        "hash_sha256": "ba1f7309d30ba8bd",
    },
    "integrador": {
        "modulo": "agentes.subagentes.subagente_integrador.prompts",
        "variable": "SYSTEM_PROMPT_INTEGRADOR",
        "version": "5.0.0",
        "descripcion": "REQ-06: CICLO_DIURNO_NORMAL sin ajuste EAWS; FUSION_ACTIVA_CON_CARGA → poor",
        "hash_sha256": "5f65608c80fc378c",
    },
}

# Versión global del conjunto de prompts (se incrementa cuando cambia cualquiera)
VERSION_GLOBAL = "5.0"


def _calcular_hash(contenido: str) -> str:
    """Calcula SHA-256 del contenido de un prompt (sin espacios trailing)."""
    normalizado = contenido.strip()
    return hashlib.sha256(normalizado.encode("utf-8")).hexdigest()[:16]


def _cargar_prompt(componente: str) -> Optional[str]:
    """Carga dinámicamente el contenido de un prompt desde su módulo."""
    info = REGISTRO_PROMPTS.get(componente)
    if not info:
        return None

    try:
        modulo = importlib.import_module(info["modulo"])
        return getattr(modulo, info["variable"], None)
    except (ImportError, AttributeError) as e:
        logger.warning(f"No se pudo cargar prompt '{componente}': {e}")
        return None


def obtener_version_actual() -> str:
    """
    Retorna la versión global del conjunto de prompts.

    Se usa para guardar en el campo `version_prompts` de BigQuery,
    permitiendo rastrear qué prompts generaron cada boletín.
    """
    return f"v{VERSION_GLOBAL}"


def obtener_versiones_detalladas() -> dict:
    """
    Retorna un diccionario con la versión y hash de cada componente.

    Útil para auditoría y debugging.
    """
    resultado = {
        "version_global": obtener_version_actual(),
        "componentes": {}
    }

    for componente, info in REGISTRO_PROMPTS.items():
        contenido = _cargar_prompt(componente)
        hash_actual = _calcular_hash(contenido) if contenido else "NO_DISPONIBLE"

        resultado["componentes"][componente] = {
            "version": info["version"],
            "hash_actual": hash_actual,
            "hash_registrado": info["hash_sha256"],
            "integridad_ok": (
                info["hash_sha256"] is None or  # Sin hash registrado = OK
                hash_actual == info["hash_sha256"]
            ),
            "descripcion": info["descripcion"],
        }

    return resultado


def verificar_integridad() -> bool:
    """
    Verifica que los prompts actuales coincidan con los hashes registrados.

    Retorna True si todos los prompts con hash registrado coinciden.
    Prompts sin hash registrado (hash_sha256=None) se omiten.
    """
    todos_ok = True

    for componente, info in REGISTRO_PROMPTS.items():
        if info["hash_sha256"] is None:
            continue

        contenido = _cargar_prompt(componente)
        if contenido is None:
            logger.error(f"Prompt '{componente}' no se pudo cargar")
            todos_ok = False
            continue

        hash_actual = _calcular_hash(contenido)
        if hash_actual != info["hash_sha256"]:
            logger.warning(
                f"Hash de '{componente}' no coincide: "
                f"esperado={info['hash_sha256']}, actual={hash_actual}. "
                f"El prompt fue modificado sin actualizar el registro."
            )
            todos_ok = False

    return todos_ok


def registrar_hashes_actuales() -> dict:
    """
    Calcula y registra los hashes SHA-256 de todos los prompts actuales.

    Actualiza REGISTRO_PROMPTS in-memory. Para persistir los cambios,
    ejecutar como script: python -m agentes.prompts.registro_versiones --actualizar-hashes
    """
    hashes = {}
    for componente in REGISTRO_PROMPTS:
        contenido = _cargar_prompt(componente)
        if contenido:
            h = _calcular_hash(contenido)
            REGISTRO_PROMPTS[componente]["hash_sha256"] = h
            hashes[componente] = h
        else:
            hashes[componente] = None
            logger.warning(f"No se pudo cargar prompt '{componente}' para hash")

    return hashes


# ─── CLI para gestión de hashes ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if "--actualizar-hashes" in sys.argv:
        print("Calculando hashes de prompts actuales...\n")
        hashes = registrar_hashes_actuales()
        print("Actualizar REGISTRO_PROMPTS con estos hashes:\n")
        for comp, h in hashes.items():
            version = REGISTRO_PROMPTS[comp]["version"]
            print(f'    "{comp}": {{"hash_sha256": "{h}", "version": "{version}"}},')
        print(f"\nVERSION_GLOBAL = \"{VERSION_GLOBAL}\"")

    elif "--verificar" in sys.argv:
        print("Verificando integridad de prompts...\n")
        detalles = obtener_versiones_detalladas()
        print(f"Versión global: {detalles['version_global']}\n")
        for comp, info in detalles["componentes"].items():
            estado = "✅" if info["integridad_ok"] else "❌"
            print(f"  {estado} {comp} v{info['version']} hash={info['hash_actual']}")
        ok = verificar_integridad()
        print(f"\nIntegridad global: {'✅ OK' if ok else '❌ FALLÓ'}")

    else:
        detalles = obtener_versiones_detalladas()
        print(f"Versión global: {detalles['version_global']}\n")
        for comp, info in detalles["componentes"].items():
            print(f"  {comp}: v{info['version']} — {info['descripcion']}")
        print(f"\nUso:")
        print(f"  python -m agentes.prompts.registro_versiones --actualizar-hashes")
        print(f"  python -m agentes.prompts.registro_versiones --verificar")
