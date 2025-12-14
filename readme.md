# Guía de Uso: Script de Análisis de Sentimiento (v2)

## Resumen
He actualizado el script para incluir una **Base de Datos Local (DuckDB)**.
Ahora el script procesa noticias, las guarda, y el análisis de sentimiento se basa en una **"ventana de tiempo"** configurable (por defecto las últimas 5 horas).

## Archivos
*   [market_sentiment.py](file:///d:/00_PROG/23_algo_trd/16_sentiment_analisis/market_sentiment.py): Script principal actualizado.

## Instalación de Nuevos Requisitos
Es necesario instalar `duckdb` además de las librerías anteriores:
```bash
pip install duckdb requests beautifulsoup4 torch transformers
```

## Configuración de "Recencia"
Puedes cambiar cuántas horas hacia atrás buscar noticias editando esta variable al principio del script:
```python
# Variables de configuracion
HORAS_VALIDEZ = 5  # <--- Cambia esto a 24, 48, etc.
```

## Nueva Lógica de Funcionamiento
1.  **Ejecución**: Al correr el script, buscará nuevas noticias.
2.  **Base de Datos**: 
    *   Si encuentra una noticia **NUEVA**, la analiza con IA y la guarda en `market_sentiment.db`.
    *   Si la noticia **YA EXISTE**, la ignora (para no gastar CPU analizándola de nuevo).
3.  **Cálculo del Score**:
    *   El script consulta la base de datos y promedia el sentimiento de **TODAS** las noticias (nuevas o viejas) que tengan menos de `HORAS_VALIDEZ` de antigüedad.
    
> [!TIP]
> Si corres el script muy seguido, verás que analiza pocas noticias "NUEVAS", pero tu reporte final seguirá mostrando datos basados en las noticias encontradas en las últimas 5 horas.
