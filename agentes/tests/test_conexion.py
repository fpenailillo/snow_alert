"""
Tests de Conexión — Sistema Multi-Agente de Predicción de Avalanchas

Verifica que la conexión a BigQuery funciona y que las tablas
necesarias existen con datos recientes.

Ejecutar:
    python -m pytest agentes/tests/test_conexion.py -v
"""

import sys
import os
import pytest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from google.cloud import bigquery


GCP_PROJECT = "climas-chileno"
DATASET = "clima"
TABLAS_ESPERADAS = [
    "condiciones_actuales",
    "pronostico_horas",
    "pronostico_dias",
    "imagenes_satelitales",
    "zonas_avalancha"
]
UBICACION_PILOTO = "La Parva Sector Bajo"


@pytest.fixture(scope="module")
def cliente_bq():
    """Fixture del cliente BigQuery compartido entre tests del módulo."""
    return bigquery.Client(project=GCP_PROJECT)


def test_bigquery_conecta(cliente_bq):
    """Verifica que el cliente BigQuery inicializa sin error."""
    assert cliente_bq is not None
    assert cliente_bq.project == GCP_PROJECT
    print(f"\n✓ Conectado a BigQuery — proyecto: {GCP_PROJECT}")


def test_cinco_tablas_existen(cliente_bq):
    """Verifica que las 5 tablas estén presentes en el dataset clima."""
    dataset_ref = f"{GCP_PROJECT}.{DATASET}"

    tablas_encontradas = []
    for tabla_nombre in TABLAS_ESPERADAS:
        tabla_ref = f"{dataset_ref}.{tabla_nombre}"
        try:
            tabla = cliente_bq.get_table(tabla_ref)
            tablas_encontradas.append(tabla_nombre)
            print(f"  ✓ {tabla_nombre} — {tabla.num_rows:,} filas")
        except Exception as e:
            pytest.fail(f"Tabla {tabla_nombre} no encontrada: {e}")

    assert len(tablas_encontradas) == len(TABLAS_ESPERADAS), (
        f"Solo se encontraron {len(tablas_encontradas)} de {len(TABLAS_ESPERADAS)} tablas: "
        f"{tablas_encontradas}"
    )
    print(f"\n✓ Las {len(TABLAS_ESPERADAS)} tablas existen en {dataset_ref}")


def test_datos_recientes_existen(cliente_bq):
    """Verifica que haya datos recientes en al menos 2 tablas de alta frecuencia."""
    tablas_con_datos = []

    # Consultas robustas por tipo de tabla (respetan el tipo de columna de tiempo)
    consultas_recientes = {
        "condiciones_actuales": """
            SELECT COUNT(*) as total
            FROM `{proyecto}.{dataset}.condiciones_actuales`
            WHERE hora_actual >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 48 HOUR)
        """,
        "pronostico_dias": """
            SELECT COUNT(*) as total
            FROM `{proyecto}.{dataset}.pronostico_dias`
            WHERE TIMESTAMP(fecha_inicio) >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 72 HOUR)
        """,
        "imagenes_satelitales": """
            SELECT COUNT(*) as total
            FROM `{proyecto}.{dataset}.imagenes_satelitales`
            WHERE fecha_captura >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 48 HOUR)
        """,
    }

    for tabla, sql in consultas_recientes.items():
        try:
            sql_formateado = sql.format(proyecto=GCP_PROJECT, dataset=DATASET)
            resultado = list(cliente_bq.query(sql_formateado).result())
            total = resultado[0]["total"]
            if total > 0:
                tablas_con_datos.append(tabla)
                print(f"  ✓ {tabla}: {total:,} registros recientes")
            else:
                print(f"  ✗ {tabla}: sin datos recientes")
        except Exception as e:
            print(f"  ⚠ {tabla}: error en query — {e}")

    assert len(tablas_con_datos) >= 2, (
        f"Solo {len(tablas_con_datos)} tablas tienen datos recientes (<48-72h). "
        f"Mínimo esperado: 2. Tablas con datos: {tablas_con_datos}"
    )
    print(f"\n✓ {len(tablas_con_datos)}/3 tablas verificadas tienen datos recientes")


def test_la_parva_tiene_datos(cliente_bq):
    """
    Verifica que 'La Parva Sector Bajo' tenga datos en las tablas de alta frecuencia.

    Nota: pronostico_horas y zonas_avalancha pueden estar vacías si el pipeline
    correspondiente no ha corrido aún (pronostico_horas) o es mensual (zonas_avalancha).
    El test exige datos en al menos 2 de las 5 tablas principales.
    """
    resultados = {}

    consultas = {
        "condiciones_actuales": """
            SELECT COUNT(*) as total
            FROM `{proyecto}.{dataset}.condiciones_actuales`
            WHERE nombre_ubicacion = 'La Parva Sector Bajo'
        """,
        "pronostico_horas": """
            SELECT COUNT(*) as total
            FROM `{proyecto}.{dataset}.pronostico_horas`
            WHERE nombre_ubicacion = 'La Parva Sector Bajo'
        """,
        "pronostico_dias": """
            SELECT COUNT(*) as total
            FROM `{proyecto}.{dataset}.pronostico_dias`
            WHERE nombre_ubicacion = 'La Parva Sector Bajo'
        """,
        "imagenes_satelitales": """
            SELECT COUNT(*) as total
            FROM `{proyecto}.{dataset}.imagenes_satelitales`
            WHERE nombre_ubicacion = 'La Parva Sector Bajo'
        """,
        "zonas_avalancha": """
            SELECT COUNT(*) as total
            FROM `{proyecto}.{dataset}.zonas_avalancha`
            WHERE nombre_ubicacion = 'La Parva Sector Bajo'
        """,
    }

    for tabla, sql in consultas.items():
        try:
            sql_formateado = sql.format(proyecto=GCP_PROJECT, dataset=DATASET)
            resultado = list(cliente_bq.query(sql_formateado).result())
            total = resultado[0]["total"]
            resultados[tabla] = total
            estado = "✓" if total > 0 else "⚠"
            print(f"  {estado} {tabla}: {total:,} registros para La Parva Sector Bajo")
        except Exception as e:
            resultados[tabla] = 0
            print(f"  ✗ {tabla}: error — {e}")

    tablas_con_datos = [t for t, n in resultados.items() if n > 0]
    tablas_vacias = [t for t, n in resultados.items() if n == 0]

    if tablas_vacias:
        print(f"\n  ⚠ Tablas sin datos (puede ser normal si el pipeline no ha corrido): "
              f"{tablas_vacias}")

    assert len(tablas_con_datos) >= 2, (
        f"La Parva Sector Bajo solo tiene datos en {len(tablas_con_datos)} tablas. "
        f"Mínimo esperado: 2. Tablas con datos: {tablas_con_datos}"
    )
    print(f"\n✓ La Parva Sector Bajo tiene datos en {len(tablas_con_datos)}/5 tablas")
