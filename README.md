# Snow Alert - Sistema de Monitoreo de Condiciones de Nieve

Sistema serverless event-driven para el monitoreo de condiciones climáticas y de nieve en centros de esquí, pueblos de montaña y destinos de montañismo a nivel mundial, utilizando la Google Weather API y servicios de Google Cloud Platform.

## Descripción

**Snow Alert** es un proyecto que implementa una arquitectura moderna de datos meteorológicos basada en eventos, especializado en destinos de nieve y alta montaña:

- **Extrae** datos climáticos de la Google Weather API para centros de esquí, pueblos de montaña y bases de montañismo
- **Procesa** los datos de forma asíncrona usando Pub/Sub como bus de mensajes
- **Almacena** los datos en una arquitectura medallion:
  - **Capa Bronce** (Cloud Storage): Datos crudos sin transformar
  - **Capa Plata** (BigQuery): Datos limpios y estructurados para análisis
- **Orquesta** la extracción periódica mediante Cloud Scheduler

### Casos de Uso
- Monitoreo de condiciones para esquí y snowboard
- Alertas de clima para expediciones de montañismo
- Seguimiento de temperaturas y viento para deportes de invierno
- Análisis histórico de condiciones climáticas en alta montaña

## Arquitectura

```
┌─────────────────┐
│ Cloud Scheduler │ (08:00 / 14:00 / 20:00)
└────────┬────────┘
         │ HTTP POST
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Cloud Function: Extractor                       │
│  • Llama a 3 endpoints de Weather API:                          │
│    - currentConditions (condiciones actuales)                    │
│    - forecast/hours (próximas 24 horas)                         │
│    - forecast/days (próximos 5 días)                            │
│  • API Key desde Secret Manager                                  │
│  • Publica a 3 topics de Pub/Sub                                │
└────────┬────────────────────────────────────────────────────────┘
         │
         │ Pub/Sub (3 topics)
         │
    ┌────┴────────────────────┬────────────────────────┐
    │                         │                        │
    ▼                         ▼                        ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ clima-datos-     │  │ clima-pronostico-│  │ clima-pronostico-│
│ crudos           │  │ horas            │  │ dias             │
│ (+ DLQ)          │  │ (+ DLQ)          │  │ (+ DLQ)          │
└────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
         │                     │                     │
         ▼                     ▼                     ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ Procesador       │  │ Procesador       │  │ Procesador       │
│ (Condiciones)    │  │ (Horas)          │  │ (Días)           │
└────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
         │                     │                     │
         │                     │                     │
         └─────────────────────┴─────────────────────┘
                               │
              ┌────────────────┴────────────────┐
              ▼                                 ▼
┌────────────────────────┐        ┌────────────────────────────┐
│ Cloud Storage          │        │ BigQuery (Capa Plata)      │
│ (Capa Bronce)          │        │ • condiciones_actuales     │
│ • condiciones_actuales/│        │ • pronostico_horas         │
│ • pronostico_horas/    │        │ • pronostico_dias          │
│ • pronostico_dias/     │        │ Particionado + Clustering  │
└────────────────────────┘        └────────────────────────────┘
```



## Ubicaciones Monitoreadas

El sistema monitorea **57 ubicaciones** de destinos de nieve y montaña a nivel mundial, organizadas en las siguientes categorías:

### Centros de Esquí - Chile (19 ubicaciones — cobertura completa de norte a sur)

**Región de Valparaíso**
| Ubicación | Latitud | Longitud | Base / Cima | Descripción |
|-----------|---------|----------|-------------|-------------|
| **Portillo** | -32.8369 | -70.1287 | 2580m / 3310m | Centro Legendario, Los Andes |
| **Ski Arpa** | -32.6000 | -70.3900 | 2690m / 3740m | Único Cat-Ski de Chile, 4000 acres |

**Región Metropolitana**
| Ubicación | Latitud | Longitud | Elevación | Descripción |
|-----------|---------|----------|-----------|-------------|
| **La Parva — Sector Bajo** | -33.3630 | -70.3010 | 2650m | Villa La Parva, base, lodges, ski school |
| **La Parva — Sector Medio** | -33.3520 | -70.2900 | 3100m | Restaurante 3100, servicios de montaña |
| **La Parva — Sector Alto** | -33.3440 | -70.2800 | 3574m | Cima, terreno experto, La Chimenea |
| **El Colorado / Farellones** | -33.3600 | -70.3000 | 2350m / 3460m | Mayor nº de pistas del Tres Valles |
| **Valle Nevado** | -33.3547 | -70.2498 | 2860m / 3670m | Mayor Centro de Esquí de Sudamérica |
| **Lagunillas** | -33.6800 | -70.2500 | 2200m / 2550m | Centro familiar, San José de Maipo |

**Región de O'Higgins**
| Ubicación | Latitud | Longitud | Base / Cima | Descripción |
|-----------|---------|----------|-------------|-------------|
| **Chapa Verde** | -34.1700 | -70.3700 | 2260m / 3050m | Centro CODELCO, acceso restringido |

**Región de Ñuble / Biobío**
| Ubicación | Latitud | Longitud | Base / Cima | Descripción |
|-----------|---------|----------|-------------|-------------|
| **Nevados de Chillán** | -36.8580 | -71.3727 | 1530m / 2400m | Volcán activo, termas y tree skiing |
| **Antuco** | -37.4100 | -71.4200 | 1400m / 1850m | Volcán Antuco, Los Ángeles |

**Región de La Araucanía**
| Ubicación | Latitud | Longitud | Base / Cima | Descripción |
|-----------|---------|----------|-------------|-------------|
| **Corralco** | -38.3700 | -71.5700 | 1550m / 2400m | Volcán Lonquimay, bosques de araucarias |
| **Las Araucarias / Llaima** | -38.7300 | -71.7400 | 1550m / 1942m | Volcán Llaima |
| **Ski Pucón / Pillán** | -39.5000 | -71.9600 | 1380m / 2100m | Volcán Villarrica (activo) |
| **Los Arenales** | -38.8500 | -72.0000 | 1600m / 1845m | Centro entrenamiento, Temuco |

**Región de Los Lagos**
| Ubicación | Latitud | Longitud | Base / Cima | Descripción |
|-----------|---------|----------|-------------|-------------|
| **Antillanca** | -40.7756 | -72.2046 | 1040m / 1540m | Volcán Casablanca, Parque Puyehue |
| **Volcán Osorno** | -41.1000 | -72.5000 | 1230m / 1760m | Volcán icónico, Puerto Varas |

**Región de Aysén**
| Ubicación | Latitud | Longitud | Base / Cima | Descripción |
|-----------|---------|----------|-------------|-------------|
| **El Fraile** | -45.6800 | -71.9400 | 980m / 1280m | Bosques de Lenga, Coyhaique |

**Región de Magallanes**
| Ubicación | Latitud | Longitud | Base / Cima | Descripción |
|-----------|---------|----------|-------------|-------------|
| **Cerro Mirador** | -53.1300 | -70.9800 | 380m / 570m | Centro más austral del mundo |

### Centros de Esquí - Argentina (5)
| Ubicación | Latitud | Longitud | Elevación | Descripción |
|-----------|---------|----------|-----------|-------------|
| **Cerro Catedral** | -41.1667 | -71.4500 | 2100m | Mayor Centro de Esquí de Sudamérica |
| **Las Leñas** | -35.1500 | -70.0833 | 3430m | Esquí de Alta Montaña y Freeride |
| **Chapelco** | -40.1500 | -71.2500 | 1980m | Esquí Patagónico |
| **Cerro Castor** | -54.7500 | -68.3333 | 1057m | Centro más Austral del Mundo |
| **Cerro Bayo** | -40.7167 | -71.5167 | 1780m | Esquí Boutique Patagonia |

### Centros de Esquí - Europa/Alpes (7)
| Ubicación | Latitud | Longitud | Elevación | Descripción |
|-----------|---------|----------|-----------|-------------|
| **Chamonix** | 45.9237 | 6.8694 | 1035m | Capital Mundial del Alpinismo |
| **Zermatt** | 46.0207 | 7.7491 | 1608m | Vista al Matterhorn |
| **St. Moritz** | 46.4908 | 9.8355 | 1822m | Turismo de Invierno de Lujo |
| **Verbier** | 46.0964 | 7.2286 | 1500m | Freeride y Alta Montaña |
| **Courchevel** | 45.4154 | 6.6347 | 1850m | Les 3 Vallées |
| **Val Thorens** | 45.2981 | 6.5797 | 2300m | Estación más Alta de Europa |
| **Cortina d'Ampezzo** | 46.5369 | 12.1356 | 1224m | Reina de las Dolomitas |

### Centros de Esquí - Norteamérica (6)
| Ubicación | Latitud | Longitud | Elevación | Descripción |
|-----------|---------|----------|-----------|-------------|
| **Vail** | 39.6403 | -106.3742 | 2476m | Legendario Resort de Colorado |
| **Aspen** | 39.1911 | -106.8175 | 2438m | Icono del Esquí de Lujo |
| **Jackson Hole** | 43.5875 | -110.8278 | 1924m | Esquí Extremo, Wyoming |
| **Whistler** | 50.1163 | -122.9574 | 675m | Mayor Resort de Norteamérica |
| **Park City** | 40.6461 | -111.4980 | 2103m | Mayor Resort de USA |
| **Mammoth Mountain** | 37.6308 | -119.0326 | 2424m | Sierra Nevada, California |

### Centros de Esquí - Oceanía y Asia (3)
| Ubicación | Latitud | Longitud | Descripción |
|-----------|---------|----------|-------------|
| **Queenstown** | -45.0312 | 168.6626 | Capital de la Aventura, Nueva Zelanda |
| **Niseko** | 42.8048 | 140.6874 | Mejor Nieve Polvo del Mundo, Japón |
| **Hakuba** | 36.6983 | 137.8619 | Alpes Japoneses, Sede Nagano 1998 |

### Pueblos de Montaña (7)
| Ubicación | Latitud | Longitud | Descripción |
|-----------|---------|----------|-------------|
| **Bariloche** | -41.1335 | -71.3103 | Suiza de Sudamérica, Argentina |
| **Ushuaia** | -54.8019 | -68.3030 | Fin del Mundo, Argentina |
| **Pucón** | -39.2819 | -71.9755 | Volcán Villarrica, Chile |
| **San Martín de los Andes** | -40.1575 | -71.3522 | Patagonia Argentina |
| **Innsbruck** | 47.2692 | 11.4041 | Capital del Tirol, Austria |
| **Interlaken** | 46.6863 | 7.8632 | Portal a Jungfrau, Suiza |
| **Banff** | 51.1784 | -115.5708 | Rockies Canadienses |

### Bases de Montañismo - Alta Montaña (8)
| Ubicación | Latitud | Longitud | Elevación | Montaña |
|-----------|---------|----------|-----------|---------|
| **Plaza de Mulas** | -32.6500 | -70.0167 | 4370m | Aconcagua (Techo de América) |
| **Everest Base Camp** | 28.0025 | 86.8528 | 5364m | Monte Everest |
| **Chamonix Mont Blanc** | 45.8326 | 6.8652 | 3817m | Mont Blanc |
| **Denali Base** | 63.0692 | -151.0070 | - | Denali/McKinley |
| **Torres del Paine** | -50.9423 | -72.9682 | - | Patagonia Chilena |
| **Kilimanjaro Gate** | -3.0674 | 37.3556 | 1800m | Kilimanjaro |
| **Monte Fitz Roy** | -49.2714 | -72.9411 | - | Fitz Roy, El Chaltén |
| **Matterhorn Zermatt** | 45.9766 | 7.6586 | 3260m | Matterhorn/Cervino |

## Características Técnicas

### Cloud Function: Extractor

- **Trigger**: HTTP (invocado por Cloud Scheduler)
- **Runtime**: Python 3.11
- **Memoria**: 256 MB
- **Timeout**: 60 segundos
- **Funcionalidades**:
  - Autenticación con API Key desde Secret Manager
  - Llamadas a 3 endpoints de Weather API para cada ubicación:
    - `currentConditions` - Condiciones actuales
    - `forecast/hours` - Pronóstico próximas 76 horas (~3 días)
    - `forecast/days` - Pronóstico próximos 10 días (máximo API)
  - Enriquecimiento de datos con metadata
  - Publicación a 3 topics de Pub/Sub según tipo de dato
  - Manejo robusto de errores y logging estructurado

### Cloud Function: Procesador (Condiciones Actuales)

- **Trigger**: Pub/Sub (topic: `clima-datos-crudos`)
- **Runtime**: Python 3.11
- **Memoria**: 512 MB
- **Timeout**: 120 segundos
- **Funcionalidades**:
  - Procesa condiciones climáticas actuales
  - Almacena en Cloud Storage (capa bronce)
  - Transforma e inserta en BigQuery (`condiciones_actuales`)
  - Dead letter queue: `clima-datos-dlq`

### Cloud Function: Procesador Horas

- **Trigger**: Pub/Sub (topic: `clima-pronostico-horas`)
- **Runtime**: Python 3.11
- **Memoria**: 512 MB
- **Timeout**: 120 segundos
- **Funcionalidades**:
  - Procesa pronóstico por horas (76 registros por ubicación)
  - Almacena en Cloud Storage (`pronostico_horas/`)
  - Transforma e inserta en BigQuery (`pronostico_horas`)
  - Dead letter queue: `clima-pronostico-horas-dlq`

### Cloud Function: Procesador Días

- **Trigger**: Pub/Sub (topic: `clima-pronostico-dias`)
- **Runtime**: Python 3.11
- **Memoria**: 512 MB
- **Timeout**: 120 segundos
- **Funcionalidades**:
  - Procesa pronóstico diario (10 registros por ubicación)
  - Incluye datos de período diurno y nocturno
  - Almacena en Cloud Storage (`pronostico_dias/`)
  - Transforma e inserta en BigQuery (`pronostico_dias`)
  - Dead letter queue: `clima-pronostico-dias-dlq`

### Cloud Storage (Capa Bronce)

- **Estructura de particiones**: `{ubicacion}/{AAAA}/{MM}/{DD}/{timestamp}.json`
- **Versionado**: Habilitado
- **Ciclo de vida**:
  - 0-30 días: Standard
  - 30-90 días: Nearline
  - 90-365 días: Coldline
  - 365+ días: Eliminación automática

### BigQuery (Capa Plata)

- **Dataset**: `clima`

#### Tabla: `condiciones_actuales`
- **Particionamiento**: Por `DATE(hora_actual)`
- **Clustering**: Por `nombre_ubicacion`
- **Esquema** (27 campos):
  - Identificación: ubicación, coordenadas
  - Temporal: hora, zona horaria
  - Temperatura: actual, sensación térmica, punto de rocío, índice de calor
  - Condiciones: descripción, código
  - Precipitación: probabilidad, acumulación
  - Viento: velocidad, dirección, sensación de viento
  - Atmosféricas: presión, humedad, visibilidad
  - Otras: índice UV, cobertura de nubes, probabilidad de tormenta
  - Metadata: timestamp de ingesta, URI datos crudos, JSON completo

#### Tabla: `pronostico_horas`
- **Particionamiento**: Por `DATE(hora_inicio)`
- **Clustering**: Por `nombre_ubicacion`
- **Cobertura**: 76 horas (~3 días con detalle por hora)
- **Esquema** (27 campos):
  - Identificación: ubicación, coordenadas
  - Temporal: hora_inicio, hora_fin
  - Temperatura: temperatura, sensación térmica, índice calor, sensación viento
  - Condiciones: condición, descripción, icono URL
  - Precipitación: probabilidad, cantidad
  - Viento: velocidad, dirección
  - Atmosféricas: humedad, presión, visibilidad
  - Otras: índice UV, cobertura nubes, probabilidad tormenta, es_dia
  - Metadata: timestamps de extracción e ingestión, URI datos crudos

#### Tabla: `pronostico_dias`
- **Particionamiento**: Por `DATE(fecha_inicio)`
- **Clustering**: Por `nombre_ubicacion`
- **Cobertura**: 10 días (máximo de la API)
- **Esquema** (45 campos):
  - Identificación: ubicación, coordenadas
  - Temporal: fecha_inicio, fecha_fin, año, mes, día
  - Astronomía: hora_amanecer, hora_atardecer
  - Temperaturas del día: temp_max_dia, temp_min_dia
  - **Período diurno** (15 campos): condición, temperatura, sensación, viento, precipitación, nubes, UV
  - **Período nocturno** (15 campos): condición, temperatura, sensación, viento, precipitación, nubes, UV
  - Metadata: timestamps de extracción e ingestión, URI datos crudos

#### Tabla: `zonas_avalancha`
- **Particionamiento**: Por `DATE(fecha_analisis)`
- **Clustering**: Por `nombre_ubicacion`, `clasificacion_riesgo`
- **Cobertura**: Análisis estático mensual de todas las ubicaciones
- **Esquema** (36 campos):
  - Identificación: nombre_ubicacion, latitud, longitud, fecha_analisis
  - **Áreas de zonas** (7 campos): zona_inicio_ha, zona_transito_ha, zona_deposito_ha, porcentajes
  - **Pendientes** (3 campos): pendiente_media_inicio, pendiente_max_inicio, pendiente_p90_inicio
  - **Aspecto y elevación** (4 campos): aspecto_predominante, elevaciones, desnivel
  - **Sub-zonas de inicio** (3 campos): inicio_moderado_ha (30-45°), inicio_severo_ha (45-60°), inicio_extremo_ha (>60°)
  - **Índice de riesgo** (6 campos): indice_riesgo_topografico (0-100), clasificacion_riesgo, componentes
  - **Estimaciones EAWS** (4 campos): frecuencia_estimada, tamano_estimado, peligro_base, descripcion_riesgo
  - **Metadatos** (4 campos): hemisferio, radio_analisis, resolucion_dem, fuente_dem

---

## Analizador Satelital de Zonas Riesgosas en Avalanchas

### Descripción

Snow Alert incluye un módulo de **análisis satelital de zonas riesgosas en avalanchas** que utiliza Google Earth Engine (GEE) con datos SRTM para identificar, clasificar y cubicar las zonas funcionales de avalancha en cada ubicación monitoreada.

El análisis implementa la metodología **EAWS 2025** (European Avalanche Warning Services) según las publicaciones:
- Müller, K., Techel, F., & Mitterer, C. (2025). *The EAWS matrix, Part A*. Nat. Hazards Earth Syst. Sci., 25, 4503-4525.
- Techel, F., Müller, K., & Schweizer, J. (2025). *The EAWS matrix, Part B*. Nat. Hazards Earth Syst. Sci. (en revisión).

### Zonas Funcionales de Avalancha

El sistema identifica tres zonas funcionales basadas en parámetros topográficos:

| Zona | Pendiente | Curvatura | Descripción |
|------|-----------|-----------|-------------|
| **Inicio** | 30° - 60° | Convexa | Donde se suelta la avalancha. Área crítica para estabilidad del manto. |
| **Tránsito** | 15° - 30° | Cóncava | Corredor donde la avalancha acelera y fluye. Influye en el tamaño final. |
| **Depósito** | < 15° | Cóncava | Donde se acumula la nieve. Zona de impacto y potencial destructivo. |

### Factores EAWS Estimados

El módulo calcula estimaciones de los tres factores de la matriz EAWS:

1. **Estabilidad** (Factor 1): Evaluada mediante porcentaje de zona de inicio y aspectos de sombra
2. **Frecuencia** (Factor 2): Estimada según extensión de zona de inicio
   - `many`: >20% zona inicio
   - `some`: 10-20% zona inicio
   - `a_few`: 5-10% zona inicio
   - `nearly_none`: <5% zona inicio
3. **Tamaño** (Factor 3): Estimado según desnivel vertical inicio→depósito
   - Tamaño 1: <100m desnivel
   - Tamaño 2: 100-300m
   - Tamaño 3: 300-600m
   - Tamaño 4: 600-1000m
   - Tamaño 5: >1000m

### Índice de Riesgo Topográfico

El sistema genera un índice estático de susceptibilidad topográfica (0-100) con cuatro componentes:

| Componente | Peso | Descripción |
|------------|------|-------------|
| **Área** | 25% | Hectáreas y porcentaje de zona de inicio |
| **Pendiente** | 25% | Pendiente máxima y media en zona de inicio |
| **Aspecto** | 25% | Orientación a sombra (N en HS, S en HN) |
| **Desnivel** | 25% | Desnivel vertical entre inicio y depósito |

**Clasificación resultante:**
- **BAJO** (0-25): Terreno con baja susceptibilidad
- **MEDIO** (26-50): Susceptibilidad moderada, atención en condiciones inestables
- **ALTO** (51-75): Alta susceptibilidad, evitar en peligro elevado
- **EXTREMO** (76-100): Solo para expertos con condiciones favorables confirmadas

### Cloud Function: Analizador Satelital de Zonas Riesgosas en Avalanchas

- **Nombre**: `analizador-satelital-zonas-riesgosas-avalanchas`
- **Trigger**: HTTP (invocado por Cloud Scheduler)
- **Runtime**: Python 3.11
- **Memoria**: 1024 MB
- **Timeout**: 540 segundos (9 minutos)
- **Frecuencia**: Mensual (día 1 a las 03:00)
- **Funcionalidades**:
  - Inicializa Google Earth Engine con proyecto GCP
  - Carga DEM SRTM de 30m de resolución (datos satelitales)
  - Clasifica zonas de inicio, tránsito y depósito
  - Calcula estadísticas de cubicación (áreas, pendientes, aspectos)
  - Genera índice de riesgo topográfico
  - **Genera visualizaciones** (mapas PNG, thumbnails, GeoJSON)
  - Almacena en BigQuery (tabla `zonas_avalancha`)
  - Almacena JSON detallado y visualizaciones en Cloud Storage

### Visualizaciones y Mapas

El módulo genera automáticamente visualizaciones para fácil integración:

| Tipo | Formato | Descripción | Uso |
|------|---------|-------------|-----|
| **Mapa de Zonas** | PNG (800x600) | Gráfico con distribución de zonas e indicadores | Dashboards, reportes |
| **Thumbnail** | PNG (200x200) | Indicador circular de riesgo | Listas, vistas previas |
| **GeoJSON** | JSON | Datos geográficos con estilos | Mapas web (Leaflet, Mapbox) |

#### Archivos Generados en GCS

```
gs://{proyecto}-datos-clima-bronce/topografia/visualizaciones/
├── 2025/02/22/
│   ├── valle_nevado_mapa_20250222_030000.png      # Mapa completo
│   ├── valle_nevado_thumb_20250222_030000.png     # Thumbnail
│   ├── valle_nevado_zonas_20250222_030000.geojson # Datos GeoJSON
│   └── ...
```

#### Integración con Mapas Web

El GeoJSON incluye estilos predefinidos compatibles con Leaflet/Mapbox:

```javascript
// Ejemplo de integración con Leaflet
fetch('ruta/a/zonas.geojson')
  .then(response => response.json())
  .then(data => {
    L.geoJSON(data, {
      style: feature => feature.properties.estilo
    }).addTo(map);
  });
```

#### Paleta de Colores EAWS

| Elemento | Color | Hex |
|----------|-------|-----|
| Zona Inicio | Rojo | `#E53935` |
| Zona Tránsito | Naranja | `#FB8C00` |
| Zona Depósito | Amarillo | `#FDD835` |
| Riesgo Bajo | Verde | `#4CAF50` |
| Riesgo Medio | Amarillo | `#FFC107` |
| Riesgo Alto | Naranja | `#FF5722` |
| Riesgo Extremo | Rojo oscuro | `#B71C1C` |

### Estructura del Módulo

```
analizador_avalanchas/
├── __init__.py              # Inicialización del paquete
├── main.py                  # Cloud Function orquestadora
├── eaws_constantes.py       # Matriz EAWS 2025 y constantes
├── zonas.py                 # Clasificación GEE de zonas
├── cubicacion.py            # Cálculo de áreas y estadísticas
├── indice_riesgo.py         # Índice de riesgo 0-100
├── visualizacion.py         # Generación de mapas PNG y GeoJSON
├── requirements.txt         # Dependencias (earthengine-api, matplotlib)
├── schema_zonas_bigquery.json  # Schema BigQuery
└── .gcloudignore            # Archivos a ignorar en deploy
```

### Consultas de Ejemplo

#### Ubicaciones con mayor riesgo topográfico

```sql
SELECT
  nombre_ubicacion,
  indice_riesgo_topografico,
  clasificacion_riesgo,
  zona_inicio_ha,
  desnivel_inicio_deposito,
  peligro_eaws_base
FROM
  `clima.zonas_avalancha`
WHERE
  fecha_analisis = (SELECT MAX(fecha_analisis) FROM `clima.zonas_avalancha`)
ORDER BY
  indice_riesgo_topografico DESC
LIMIT 10;
```

#### Centros de esquí por clasificación de riesgo

```sql
SELECT
  clasificacion_riesgo,
  COUNT(*) AS total_ubicaciones,
  ROUND(AVG(zona_inicio_ha), 2) AS avg_zona_inicio_ha,
  ROUND(AVG(pendiente_max_inicio), 1) AS avg_pendiente_max,
  ROUND(AVG(desnivel_inicio_deposito), 0) AS avg_desnivel
FROM
  `clima.zonas_avalancha`
WHERE
  fecha_analisis = (SELECT MAX(fecha_analisis) FROM `clima.zonas_avalancha`)
GROUP BY
  clasificacion_riesgo
ORDER BY
  CASE clasificacion_riesgo
    WHEN 'extremo' THEN 1
    WHEN 'alto' THEN 2
    WHEN 'medio' THEN 3
    WHEN 'bajo' THEN 4
  END;
```

#### Detalle de componentes de riesgo

```sql
SELECT
  nombre_ubicacion,
  indice_riesgo_topografico,
  componente_area,
  componente_pendiente,
  componente_aspecto,
  componente_desnivel,
  descripcion_riesgo
FROM
  `clima.zonas_avalancha`
WHERE
  clasificacion_riesgo = 'extremo'
  AND fecha_analisis = (SELECT MAX(fecha_analisis) FROM `clima.zonas_avalancha`)
ORDER BY
  indice_riesgo_topografico DESC;
```

---

## Monitor Satelital de Nieve

### Descripción

Snow Alert incluye un módulo de **monitoreo satelital de nieve** que utiliza Google Earth Engine (GEE) para descargar automáticamente imágenes satelitales de las ubicaciones monitoreadas. El sistema obtiene:

1. **Imagen visual** (true color + false color nieve)
2. **Cobertura de nieve** (NDSI / fracción de nieve)
3. **Temperatura superficial** (LST día y noche)
4. **Datos ERA5-Land** (gap-filler continuo sin nubes)

### Fuentes Satelitales por Región

El sistema adapta automáticamente la fuente satelital según la región geográfica:

| Región | Fuente Principal | Frecuencia | Resolución |
|--------|-----------------|------------|------------|
| **Chile / Argentina** | GOES-18 | Cada 10 min | 2 km |
| **Norteamérica** | GOES-16 | Cada 10 min | 2 km |
| **Europa / Alpes** | MODIS Terra/Aqua | 2x/día | 500 m |
| **Asia / Oceanía** | MODIS Terra/Aqua | 2x/día | 500 m |
| **Todas las regiones** | ERA5-Land (backup) | Horario | 11 km |

### Productos Generados

#### Por Cada Captura (3 veces al día)

| Producto | Formato | Uso |
|----------|---------|-----|
| **GeoTIFF Visual** | Multi-banda | Análisis GIS |
| **GeoTIFF NDSI** | 1 banda (0-100) | Cobertura de nieve |
| **GeoTIFF LST** | 1 banda (°C) | Temperatura superficial |
| **GeoTIFF ERA5** | 3 bandas | Snow depth, SWE, cover |
| **Preview PNG** | 768×768 px | Dashboards, reportes |
| **Thumbnail PNG** | 256×256 px | Landing page, listas |

### Métricas en BigQuery

El sistema registra las siguientes métricas en la tabla `clima.imagenes_satelitales`:

| Categoría | Métricas |
|-----------|----------|
| **Nubes** | pct_nubes, es_nublado |
| **Nieve NDSI** | ndsi_medio, ndsi_max, pct_cobertura_nieve, tiene_nieve |
| **Temperatura** | lst_dia_celsius, lst_noche_celsius, lst_min_celsius |
| **ERA5-Land** | snow_depth_m, swe_m, snow_cover, temp_2m_celsius |
| **Sentinel-2** | disponible, fecha, pct_nieve (cuando hay imagen) |

### Cloud Function: Monitor Satelital de Nieve

- **Nombre**: `monitor-satelital-nieve`
- **Trigger**: HTTP (invocado por Cloud Scheduler)
- **Runtime**: Python 3.11
- **Memoria**: 2048 MB
- **Timeout**: 540 segundos (9 minutos)
- **Frecuencia**: 3x/día (08:30, 14:30, 20:30)
- **Funcionalidades**:
  - Inicializa Google Earth Engine con proyecto GCP
  - Determina fuente satelital por región (GOES vs MODIS)
  - Descarga imágenes usando `getDownloadURL()` y `getThumbURL()`
  - Calcula métricas de cobertura de nieve y temperatura
  - Almacena GeoTIFF, previews y thumbnails en Cloud Storage
  - Registra métricas en BigQuery
  - ERA5-Land como gap-filler (sin problemas de nubes)

### Estructura de Archivos en Cloud Storage

```
gs://{proyecto}-datos-clima-bronce/satelital/
├── geotiff/
│   └── {ubicacion}/
│       └── {YYYY-MM-DD}/
│           ├── {ubicacion}_{captura}_{fuente}_visual.tif
│           ├── {ubicacion}_{captura}_{fuente}_ndsi.tif
│           ├── {ubicacion}_{captura}_{fuente}_lst.tif
│           └── {ubicacion}_{captura}_era5_nieve.tif
├── preview/
│   └── {ubicacion}/
│       └── {YYYY-MM-DD}/
│           ├── {ubicacion}_{captura}_visual_768px.png
│           ├── {ubicacion}_{captura}_ndsi_768px.png
│           └── {ubicacion}_{captura}_lst_768px.png
└── thumbnail/
    └── {ubicacion}/
        ├── {ubicacion}_ultimo_visual_256px.png
        ├── {ubicacion}_ultimo_ndsi_256px.png
        └── {ubicacion}_ultimo_lst_256px.png
```

### Estructura del Módulo

```
monitor_satelital/
├── __init__.py              # Inicialización del paquete
├── main.py                  # Cloud Function orquestadora
├── constantes.py            # Colecciones GEE, bandas, vis_params
├── fuentes.py               # Selección de fuente por región
├── productos.py             # Procesamiento por producto
├── metricas.py              # Cálculo de métricas para BigQuery
├── descargador.py           # Descarga GEE y subida a GCS
├── requirements.txt         # Dependencias (earthengine-api)
├── schema_imagenes_bigquery.json  # Schema BigQuery
└── .gcloudignore            # Archivos a ignorar en deploy
```

### Consultas de Ejemplo

#### Cobertura de nieve más reciente por ubicación

```sql
SELECT
  nombre_ubicacion,
  fecha_captura,
  tipo_captura,
  fuente_principal,
  pct_cobertura_nieve,
  ndsi_medio,
  lst_dia_celsius,
  era5_snow_depth_m
FROM
  `clima.imagenes_satelitales`
WHERE
  fecha_captura = (SELECT MAX(fecha_captura) FROM `clima.imagenes_satelitales`)
ORDER BY
  pct_cobertura_nieve DESC;
```

#### Evolución de cobertura de nieve (últimos 7 días)

```sql
SELECT
  nombre_ubicacion,
  fecha_captura,
  AVG(pct_cobertura_nieve) AS avg_cobertura_nieve,
  AVG(ndsi_medio) AS avg_ndsi,
  AVG(era5_snow_depth_m) AS avg_snow_depth
FROM
  `clima.imagenes_satelitales`
WHERE
  fecha_captura >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
GROUP BY
  nombre_ubicacion, fecha_captura
ORDER BY
  nombre_ubicacion, fecha_captura;
```

#### Ubicaciones con mejor cobertura de nieve

```sql
SELECT
  nombre_ubicacion,
  region,
  ROUND(AVG(pct_cobertura_nieve), 1) AS avg_cobertura,
  ROUND(AVG(era5_snow_depth_m), 3) AS avg_profundidad_m,
  COUNT(*) AS total_capturas
FROM
  `clima.imagenes_satelitales`
WHERE
  fecha_captura >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  AND es_nublado = FALSE
GROUP BY
  nombre_ubicacion, region
HAVING
  avg_cobertura > 50
ORDER BY
  avg_cobertura DESC;
```

### Cuota de Google Earth Engine

El tier gratuito Community provee **150 EECU-horas/mes**. Estimación de uso:

| Parámetro | Valor |
|-----------|-------|
| Ubicaciones | 57 |
| Capturas/día | 3 |
| Productos/captura | ~4 |
| EECU-seg/producto | ~10 |
| **Total/ejecución** | ~0.5 EECU-horas |
| **Total/mes** (3x/día × 30 días) | ~45 EECU-horas |

El uso está dentro del límite gratuito de 150 EECU-horas/mes.

---

## Requisitos Previos

### Software Necesario

- **Google Cloud SDK** (gcloud CLI) versión 400+
- **Python** 3.11+
- **Git** para control de versiones

### Cuenta de Google Cloud

1. Proyecto de GCP activo
2. Facturación habilitada
3. Permisos necesarios:
   - Editor de proyecto o roles específicos:
     - Cloud Functions Admin
     - Pub/Sub Admin
     - Storage Admin
     - BigQuery Admin
     - Service Account Admin
     - Cloud Scheduler Admin

### APIs Requeridas

Las siguientes APIs deben estar habilitadas (el script de despliegue las habilita automáticamente):

- Cloud Functions API
- Cloud Build API
- Cloud Scheduler API
- Pub/Sub API
- Cloud Storage API
- BigQuery API
- Cloud Logging API
- Cloud Run API
- Secret Manager API
- Weather API

### Weather API Key

**IMPORTANTE**: Necesitas una API Key con acceso a la Weather API:

1. Ve a [Google Cloud Console - API Credentials](https://console.cloud.google.com/apis/credentials)
2. Crea una API Key o usa una existente
3. Asegúrate de que la API Key tenga acceso a `weather.googleapis.com`
4. Durante el despliegue, se te solicitará agregar esta API Key a Secret Manager

## Configuración

### 1. Clonar el Repositorio

```bash
git clone https://github.com/fpenailillo/snow_alert
cd snow_alert
```

### 2. Configurar Variables de Entorno

```bash
export ID_PROYECTO="climas-chileno"
export REGION="us-central1"
```

### 3. Autenticación con GCP

```bash
# Autenticarse con cuenta de GCP
gcloud auth login

# Configurar proyecto
gcloud config set project $ID_PROYECTO

# Configurar credenciales para Application Default Credentials
gcloud auth application-default login

gcloud auth list
gcloud config list project

```

## Despliegue

### Opción 1: Script Automatizado (Recomendado)

El script `desplegar.sh` despliega toda la infraestructura automáticamente:

```bash
./desplegar.sh [ID_PROYECTO] [REGION]
```

Ejemplo:

```bash
./desplegar.sh climas-chileno us-central1
```

El script realiza las siguientes acciones:

1. ✓ Valida dependencias
2. ✓ Habilita APIs necesarias (incluyendo Weather API, Earth Engine y Secret Manager)
3. ✓ Crea cuenta de servicio y asigna permisos
4. ✓ Configura Secret Manager para Weather API Key
5. ✓ Crea 6 topics de Pub/Sub:
   - `clima-datos-crudos` + DLQ
   - `clima-pronostico-horas` + DLQ
   - `clima-pronostico-dias` + DLQ
6. ✓ Crea bucket de Cloud Storage con ciclo de vida
7. ✓ Crea dataset y 5 tablas de BigQuery:
   - `condiciones_actuales`
   - `pronostico_horas`
   - `pronostico_dias`
   - `zonas_avalancha`
   - `imagenes_satelitales`
8. ✓ Despliega Cloud Function Extractor
9. ✓ Despliega Cloud Function Procesador (condiciones actuales)
10. ✓ Despliega Cloud Function Procesador Horas
11. ✓ Despliega Cloud Function Procesador Días
12. ✓ Despliega Cloud Function Analizador Satelital de Zonas Riesgosas en Avalanchas
13. ✓ Despliega Cloud Function Monitor Satelital de Nieve
14. ✓ Configura 3 jobs de Cloud Scheduler:
    - `extraer-clima-job` (3x/día: 08:00, 14:00, 20:00)
    - `monitor-satelital-job` (3x/día: 08:30, 14:30, 20:30)
    - `analizar-topografia-job` (mensual: día 1 a las 03:00)

**Tiempo estimado**: 5-10 minutos

**Nota**: El script pausará para que agregues tu Weather API Key a Secret Manager. Sigue las instrucciones en pantalla.

### Opción 2: Despliegue Manual

#### 2.1 Crear Topics de Pub/Sub

```bash
gcloud pubsub topics create clima-datos-crudos --project=$ID_PROYECTO
gcloud pubsub topics create clima-datos-dlq --project=$ID_PROYECTO
```

#### 2.2 Crear Bucket de Cloud Storage

```bash
gsutil mb -p $ID_PROYECTO -l $REGION gs://${ID_PROYECTO}-datos-clima-bronce
gsutil versioning set on gs://${ID_PROYECTO}-datos-clima-bronce
```

#### 2.3 Crear Dataset y Tabla de BigQuery

```bash
# Crear dataset
bq mk --project_id=$ID_PROYECTO --location=$REGION clima

# Crear tabla (el schema completo se crea automáticamente con desplegar.sh)
# Aquí se muestra solo la estructura básica
bq mk --project_id=$ID_PROYECTO \
  --table \
  --time_partitioning_field=hora_actual \
  --time_partitioning_type=DAY \
  --clustering_fields=nombre_ubicacion \
  clima.condiciones_actuales
```

#### 2.4 Desplegar Cloud Functions

```bash
# Extractor
gcloud functions deploy extractor-clima \
  --gen2 \
  --runtime=python311 \
  --region=$REGION \
  --source=./extractor \
  --entry-point=extraer_clima \
  --trigger-http \
  --set-env-vars=GCP_PROJECT=$ID_PROYECTO

# Procesador
gcloud functions deploy procesador-clima \
  --gen2 \
  --runtime=python311 \
  --region=$REGION \
  --source=./procesador \
  --entry-point=procesar_clima \
  --trigger-topic=clima-datos-crudos \
  --set-env-vars=GCP_PROJECT=$ID_PROYECTO
```

#### 2.5 Configurar Cloud Scheduler

```bash
# Obtener URL del extractor
URL_EXTRACTOR=$(gcloud functions describe extractor-clima \
  --gen2 --region=$REGION --format='value(serviceConfig.uri)')

# Crear job
gcloud scheduler jobs create http extraer-clima-job \
  --location=$REGION \
  --schedule="0 * * * *" \
  --uri=$URL_EXTRACTOR \
  --http-method=POST
```

## Verificar Despliegue

Después del despliegue, verifica que todo funcione correctamente:

```bash
# 1. Ejecutar el scheduler manualmente
gcloud scheduler jobs run extraer-clima-job --location=us-central1

# 2. Esperar 60 segundos para que los mensajes se procesen
sleep 60

# 3. Verificar datos en BigQuery
bq query --use_legacy_sql=false \
  "SELECT nombre_ubicacion, temperatura, descripcion_clima, hora_actual
   FROM clima.condiciones_actuales
   ORDER BY hora_actual DESC
   LIMIT 5"

# 4. Verificar archivos en Cloud Storage
gsutil ls gs://climas-chileno-datos-clima-bronce/**/*.json | head -10
```

## Uso

### Ejecución Manual

Para probar el sistema manualmente con autenticación:

```bash
# Obtener URL del extractor
URL_EXTRACTOR=$(gcloud functions describe extractor-clima \
  --gen2 --region=$REGION --format='value(serviceConfig.uri)')

# Ejecutar extractor con autenticación
curl -X POST $URL_EXTRACTOR \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)"
```

### Ejecución Programada

Cloud Scheduler ejecuta automáticamente el extractor 3 veces al día según la configuración:

- **Frecuencia**: `0 8,14,20 * * *` (08:00 mañana, 14:00 tarde, 20:00 noche)
- **Zona horaria**: America/Santiago
- **Reintentos**: Hasta 3 intentos con backoff exponencial

### Ver Logs

```bash
# Logs del extractor
gcloud functions logs read extractor-clima --gen2 --region=$REGION --limit=50

# Logs del procesador
gcloud functions logs read procesador-clima --gen2 --region=$REGION --limit=50

# Logs en tiempo real
gcloud functions logs read extractor-clima --gen2 --region=$REGION --tail
```

### Consultar Datos en BigQuery

#### Últimas 10 mediciones

```sql
SELECT
  nombre_ubicacion,
  hora_actual,
  temperatura,
  descripcion_clima,
  humedad_relativa,
  velocidad_viento
FROM
  `clima.condiciones_actuales`
ORDER BY
  hora_actual DESC
LIMIT 10;
```

#### Promedio de temperatura por ubicación (últimas 24 horas)

```sql
SELECT
  nombre_ubicacion,
  AVG(temperatura) AS temperatura_promedio,
  MIN(temperatura) AS temperatura_minima,
  MAX(temperatura) AS temperatura_maxima,
  COUNT(*) AS total_mediciones
FROM
  `clima.condiciones_actuales`
WHERE
  hora_actual >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
GROUP BY
  nombre_ubicacion
ORDER BY
  nombre_ubicacion;
```

#### Condiciones climáticas más frecuentes

```sql
SELECT
  nombre_ubicacion,
  descripcion_clima,
  COUNT(*) AS frecuencia
FROM
  `clima.condiciones_actuales`
WHERE
  descripcion_clima IS NOT NULL
  AND hora_actual >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY
  nombre_ubicacion,
  descripcion_clima
ORDER BY
  nombre_ubicacion,
  frecuencia DESC;
```

#### Condiciones actuales para esquí (sensación de viento y temperatura)

```sql
SELECT
  nombre_ubicacion,
  temperatura,
  sensacion_viento AS wind_chill,
  velocidad_viento,
  humedad_relativa,
  descripcion_clima,
  hora_actual
FROM
  `clima.condiciones_actuales`
WHERE
  hora_actual = (SELECT MAX(hora_actual) FROM `clima.condiciones_actuales`)
  AND nombre_ubicacion IN ('Valle Nevado', 'Portillo', 'Cerro Catedral', 'Vail', 'Chamonix')
ORDER BY
  temperatura ASC;
```

#### Comparación de temperaturas por región de esquí

```sql
WITH ultima_hora AS (
  SELECT MAX(hora_actual) AS max_hora
  FROM `clima.condiciones_actuales`
)
SELECT
  CASE
    WHEN longitud BETWEEN -75 AND -65 THEN 'Sudamérica (Chile/Argentina)'
    WHEN longitud BETWEEN -130 AND -100 THEN 'Norteamérica'
    WHEN longitud BETWEEN 0 AND 20 THEN 'Alpes Europeos'
    WHEN longitud > 100 THEN 'Asia/Oceanía'
    ELSE 'Otras Regiones'
  END AS region_esqui,
  COUNT(DISTINCT nombre_ubicacion) AS centros,
  ROUND(AVG(temperatura), 1) AS temp_promedio,
  ROUND(MIN(temperatura), 1) AS temp_minima,
  ROUND(MAX(temperatura), 1) AS temp_maxima,
  ROUND(AVG(velocidad_viento), 1) AS viento_promedio
FROM
  `clima.condiciones_actuales`
CROSS JOIN
  ultima_hora
WHERE
  hora_actual = ultima_hora.max_hora
GROUP BY
  region_esqui
ORDER BY
  temp_promedio ASC;
```

#### Alertas de viento fuerte para montañismo

```sql
SELECT
  nombre_ubicacion,
  temperatura,
  sensacion_viento,
  velocidad_viento,
  direccion_viento,
  descripcion_clima,
  hora_actual
FROM
  `clima.condiciones_actuales`
WHERE
  hora_actual >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
  AND velocidad_viento > 50  -- km/h
ORDER BY
  velocidad_viento DESC;
```

### Explorar Datos Crudos en Cloud Storage

```bash
# Listar archivos recientes
gsutil ls -l gs://${ID_PROYECTO}-datos-clima-bronce/santiago/$(date +%Y)

# Descargar un archivo
gsutil cp gs://${ID_PROYECTO}-datos-clima-bronce/santiago/2024/01/15/20240115_120000.json .

# Ver contenido
cat 20240115_120000.json | jq .
```

## Monitoreo y Alertas

### Métricas Importantes

1. **Cloud Functions**:
   - Tasa de invocaciones
   - Tasa de errores
   - Duración de ejecución
   - Memoria utilizada

2. **Pub/Sub**:
   - Mensajes publicados/procesados
   - Mensajes no confirmados
   - Mensajes en DLQ

3. **BigQuery**:
   - Filas insertadas
   - Bytes procesados
   - Errores de inserción

### Configurar Alertas

Crear alertas en Cloud Monitoring para:

```bash
# Tasa de errores alta en Cloud Functions (>5%)
# Mensajes acumulados en DLQ (>10)
# Falta de datos nuevos en BigQuery (>2 horas sin inserts)
```

Ver [documentación de Cloud Monitoring](https://cloud.google.com/monitoring/docs) para configuración detallada.

## Costos Estimados

Estimación mensual para **57 ubicaciones** con ejecución **3 veces al día** (~90 invocaciones/mes):

| Servicio | Uso | Costo Estimado (USD) |
|----------|-----|----------------------|
| Cloud Functions | 180 invocaciones (2 funciones × 90) | Gratis (tier: 2M/mes) |
| Pub/Sub | ~5,130 mensajes (57 ubicaciones × 90) | Gratis (tier: 10 GB/mes) |
| Cloud Storage | ~10 MB/mes (5,130 archivos JSON × 2 KB) | $0.00 |
| BigQuery | ~0.3 GB almacenado/mes | $0.01 |
| BigQuery | ~1 GB queries/mes | Gratis (tier: 1 TB/mes) |
| Cloud Scheduler | 1 job | $0.10 |
| Secret Manager | 1 secret, ~90 accesos/mes | $0.00 |
| **TOTAL** | | **~$0.11/mes** |

**Nota**:
- Los costos son aproximados y pueden variar según el uso real y la región
- Primer año incluye $300 de créditos gratuitos de GCP
- Con 3 ejecuciones/día: **3 mediciones/día** por ubicación (171 total para 57 ubicaciones)
- Volumen mensual: ~5,130 registros
- Prácticamente toda la operación cae dentro del tier gratuito de GCP
- Estimación basada en precios de us-central1 (Enero 2026)

## Estructura del Proyecto

```
snow_alert/
├── extractor/
│   ├── main.py                 # Cloud Function de extracción (3 APIs)
│   ├── requirements.txt        # Dependencias del extractor
│   └── .gcloudignore          # Archivos a ignorar en deploy
├── procesador/
│   ├── main.py                 # Procesador de condiciones actuales
│   ├── requirements.txt        # Dependencias del procesador
│   └── .gcloudignore          # Archivos a ignorar en deploy
├── procesador_horas/
│   ├── main.py                 # Procesador de pronóstico por horas
│   ├── requirements.txt        # Dependencias
│   └── .gcloudignore          # Archivos a ignorar en deploy
├── procesador_dias/
│   ├── main.py                 # Procesador de pronóstico por días
│   ├── requirements.txt        # Dependencias
│   └── .gcloudignore          # Archivos a ignorar en deploy
├── analizador_avalanchas/      # Analizador Satelital de Zonas Riesgosas
│   ├── __init__.py             # Inicialización del paquete
│   ├── main.py                 # Cloud Function de análisis satelital
│   ├── eaws_constantes.py      # Matriz EAWS 2025 y constantes de terreno
│   ├── zonas.py                # Clasificación GEE de zonas de avalancha
│   ├── cubicacion.py           # Cálculo de áreas y estadísticas
│   ├── indice_riesgo.py        # Índice de riesgo topográfico 0-100
│   ├── visualizacion.py        # Generación de mapas PNG y GeoJSON
│   ├── requirements.txt        # Dependencias (earthengine-api, matplotlib)
│   ├── schema_zonas_bigquery.json  # Schema BigQuery
│   └── .gcloudignore          # Archivos a ignorar en deploy
├── monitor_satelital/          # Monitor Satelital de Nieve
│   ├── __init__.py             # Inicialización del paquete
│   ├── main.py                 # Cloud Function orquestadora
│   ├── constantes.py           # Colecciones GEE, bandas, vis_params
│   ├── fuentes.py              # Selección de fuente por región
│   ├── productos.py            # Procesamiento por producto
│   ├── metricas.py             # Cálculo de métricas para BigQuery
│   ├── descargador.py          # Descarga GEE y subida a GCS
│   ├── requirements.txt        # Dependencias (earthengine-api)
│   ├── schema_imagenes_bigquery.json  # Schema BigQuery
│   └── .gcloudignore          # Archivos a ignorar en deploy
├── desplegar.sh                # Script de despliegue automatizado
├── .gcloudignore              # Archivos a ignorar en deploy general
├── .gitignore                  # Archivos a ignorar en git
├── requerimientos.md           # Requerimientos técnicos del proyecto
├── CLAUDE.md                   # Guía para asistentes de IA
└── README.md                   # Este archivo (documentación completa)
```

## Solución de Problemas

### Error: Cloud Scheduler "The request was not authenticated"

**Síntoma**: Cloud Scheduler no puede invocar Cloud Function Gen2

**Causa**: Problema con permisos de Cloud Run (Cloud Functions Gen2 corre sobre Cloud Run)

**Solución**:
```bash
# 1. Agregar permisos de Cloud Run a la cuenta de servicio
gcloud run services add-iam-policy-binding extractor-clima \
  --region=us-central1 \
  --member="serviceAccount:funciones-clima-sa@climas-chileno.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

# 2. Verificar con ejecución manual
gcloud scheduler jobs run extraer-clima-job --location=us-central1

# 3. Ver logs para confirmar
gcloud functions logs read extractor-clima --gen2 --region=us-central1 --limit=20
```

### Error: Permisos insuficientes

**Síntoma**: Error 403 o "Permission denied"

**Solución**:
```bash
# Verificar permisos de la cuenta de servicio
gcloud projects get-iam-policy $ID_PROYECTO \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:funciones-clima-sa@"

# Asignar permisos faltantes
gcloud projects add-iam-policy-binding $ID_PROYECTO \
  --member="serviceAccount:funciones-clima-sa@${ID_PROYECTO}.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"
```

### Error: API no habilitada

**Síntoma**: "API [nombre] has not been used in project"

**Solución**:
```bash
# Habilitar API específica
gcloud services enable [nombre-api].googleapis.com --project=$ID_PROYECTO

# Ejemplo
gcloud services enable cloudfunctions.googleapis.com --project=$ID_PROYECTO
```

### Error: Timeout en Cloud Function

**Síntoma**: Function timeout, exceeded time limit

**Solución**:
```bash
# Aumentar timeout del extractor
gcloud functions deploy extractor-clima \
  --gen2 \
  --timeout=120s \
  --region=$REGION

# Aumentar timeout del procesador
gcloud functions deploy procesador-clima \
  --gen2 \
  --timeout=180s \
  --region=$REGION
```

### Mensajes en Dead Letter Queue

**Síntoma**: Mensajes acumulados en topic clima-datos-dlq

**Solución**:
```bash
# Ver mensajes en DLQ
gcloud pubsub subscriptions pull clima-datos-dlq-sub --limit=10

# Revisar logs del procesador para identificar causa
gcloud functions logs read procesador-clima --gen2 --region=$REGION --limit=100

# Reprocesar mensajes manualmente si es necesario
```



## Referencias

### Google Cloud Platform
- [Google Weather API Documentation](https://developers.google.com/maps/documentation/weather)
- [Google Cloud Functions](https://cloud.google.com/functions/docs)
- [Google Cloud Pub/Sub](https://cloud.google.com/pubsub/docs)
- [Google BigQuery](https://cloud.google.com/bigquery/docs)
- [Cloud Scheduler](https://cloud.google.com/scheduler/docs)
- [Google Earth Engine](https://earthengine.google.com/)
- [Arquitectura Medallion](https://www.databricks.com/glossary/medallion-architecture)

### Metodología EAWS (Avalanchas)
- Müller, K., Techel, F., & Mitterer, C. (2025). *The EAWS matrix, Part A: Building a new European avalanche danger scale based on three interacting factors*. Nat. Hazards Earth Syst. Sci., 25, 4503-4525. [DOI: 10.5194/nhess-25-4503-2025](https://doi.org/10.5194/nhess-25-4503-2025)
- Techel, F., Müller, K., & Schweizer, J. (2025). *The EAWS matrix, Part B: Deriving European avalanche danger level definitions using explicit decision criteria*. Nat. Hazards Earth Syst. Sci. (en revisión)
- Statham, G., et al. (2018). *A conceptual model of avalanche hazard*. Natural Hazards, 90, 663-691
- [EAWS - European Avalanche Warning Services](https://www.avalanches.org/)

---

**Nota**: Snow Alert está diseñado para monitoreo de condiciones climáticas en destinos de nieve y montaña. Úselo para planificar sus aventuras de esquí, snowboard y montañismo de forma segura.
