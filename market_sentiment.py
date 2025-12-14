import requests
from bs4 import BeautifulSoup
from transformers import pipeline
import time
import random
import sys
import duckdb
import hashlib
from datetime import datetime, timedelta

# ==========================================
# CONFIGURACION DEL USUARIO (EDITABLE)
# ==========================================

# Variables de configuracion
HORAS_VALIDEZ = 24*5  # <--- NOTICIAS DE LAS ULTIMAS X HORAS SE CONSIDERAN VALIDAS

# Lista de criptomonedas a analizar
activos_cripto = [
    "Bitcoin",
    "Ethereum",
    "Solana",
    "Cardano",
    "Tron"

]

# Lista de acciones a analizar
activos_acciones = [
    "S&P 500",
    "Gold",
    "Nasdaq",
    "MSCI Emerging Markets",
    "MSCI World",
    "Dow",
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    
]

# Fuentes de noticias CRIPTO (URLs base para busqueda)
fuentes_cripto = [
    'https://cointelegraph.com/search?query=',
    'https://www.coindesk.com/search?s='
]

# Fuentes de noticias ACCIONES (URLs base para busqueda)
# CAMBIO: Usamos Yahoo News Search para buscar noticias recientes por texto
fuentes_acciones = [
    'https://www.marketwatch.com/search?q=',
    'https://news.search.yahoo.com/search?p='
]

# Palabras clave para IGNORAR (filtros de basura del footer/nav)
palabras_excluir = [
    "policy", "terms", "privacy", "copyright", "subscribe", "login", 
    "sign up", "contact", "advertisement", "cookies", "all rights reserved",
    "jobs", "career"
]

# ==========================================
# GESTION DE BASE DE DATOS LOCAL (DuckDB)
# ==========================================

DB_PATH = "market_sentiment.db"

def init_db():
    """Conecta a DuckDB y crea la tabla si no existe."""
    con = duckdb.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS noticias (
            id VARCHAR PRIMARY KEY,
            fecha TIMESTAMP,
            activo VARCHAR,
            fuente VARCHAR,
            texto VARCHAR,
            sentimiento DOUBLE,
            tipo_activo VARCHAR
        )
    """)
    con.close()

def calcular_hash(texto):
    """Genera un ID unico para el titular basado en su texto."""
    return hashlib.md5(texto.encode('utf-8')).hexdigest()

def existe_noticia(con, texto_hash):
    """Verifica si la noticia ya fue analizada."""
    res = con.execute("SELECT 1 FROM noticias WHERE id = ?", [texto_hash]).fetchone()
    return res is not None

def guardar_noticia(con, texto_hash, activo, fuente, texto, sentimiento, tipo_activo):
    """Guarda la noticia analizada en la BD."""
    con.execute("""
        INSERT INTO noticias (id, fecha, activo, fuente, texto, sentimiento, tipo_activo)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [texto_hash, datetime.now(), activo, fuente, texto, sentimiento, tipo_activo])

def obtener_sentimiento_promedio(con, activo, horas):
    """Calcula el sentimiento promedio de las ultimas X horas usando DuckDB."""
    # DuckDB soporta sintaxis de intervalos
    query = f"""
        SELECT AVG(sentimiento), COUNT(*) 
        FROM noticias 
        WHERE activo = ? 
        AND fecha >= now() - INTERVAL '{horas} hours'
    """
    res = con.execute(query, [activo]).fetchone()
    if res and res[0] is not None:
        return res[0], res[1]
    return 0.0, 0

# ==========================================
# LOGICA PRINCIPAL
# ==========================================

def cargar_modelo():
    print(">>> Cargando modelo de Inteligencia Artificial (FinBERT)...")
    try:
        classifier = pipeline("text-classification", model="ProsusAI/finbert", device=-1)
        return classifier
    except Exception as e:
        print(f"Error cargando el modelo: {e}")
        sys.exit(1)

def obtener_html(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }
    tiempo_espera = random.uniform(3, 5)
    print(f"    ...Esperando {tiempo_espera:.2f}s...")
    time.sleep(tiempo_espera)
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.text
        return None
    except:
        return None

def limpiar_texto(texto):
    return texto.strip().replace("\n", " ")

def es_titular_valido(texto):
    if len(texto) < 20: return False # Muy corto
    texto_lower = texto.lower()
    for palabra in palabras_excluir:
        if palabra in texto_lower:
            return False
    return True

def extraer_titulares(html):
    titulares = []
    if not html: return titulares
    soup = BeautifulSoup(html, 'html.parser')
    
    # Busqueda generica de titulos (H1-H3 y clases especificas)
    # MarketWatch usa 'article__content' y 'a.link'
    # Yahoo usa 'h3'
    # Cointelegraph usa 'post-card__header'
    
    elementos = soup.find_all(['h1', 'h2', 'h3', 'a'])
    
    for el in elementos:
        texto = limpiar_texto(el.get_text())
        
        # Filtros extra para detectar posibles titulares reales
        clases = el.get('class')
        es_posible_titulo = False
        
        if el.name in ['h1', 'h2', 'h3']:
            es_posible_titulo = True
        elif clases and any('title' in str(c).lower() or 'headline' in str(c).lower() or 'header' in str(c).lower() for c in clases):
            es_posible_titulo = True
            
        # Truco para links dentro de listas de noticias
        if el.name == 'a' and len(texto) > 30: # Links largos suelen ser titulos en listas de resultados
            es_posible_titulo = True
        
        if es_posible_titulo and es_titular_valido(texto):
             if texto not in titulares:
                titulares.append(texto)

    # LIMITAMOS a los primeros 7 encontrados para priorizar 'recientes' (asumiendo orden web)
    return titulares[:7]

def analizar_sentimiento_modelo(texto, modelo):
    res = modelo(texto, truncation=True, max_length=512)[0]
    label = res['label']
    if label == 'positive': return 1.0
    if label == 'negative': return -1.0
    return 0.0

def procesar_activos(lista_activos, fuentes, modelo, con_db, tipo):
    resultados = {}
    
    for activo in lista_activos:
        print(f"\n>>> Procesando: {activo}")
        
        # 1. SCRAPING Y GUARDADO
        for fuente_base in fuentes:
            url = f"{fuente_base}{activo}"
            print(f"  - Fuente: {fuente_base}...")
            
            html = obtener_html(url)
            titulares = extraer_titulares(html)
            
            if titulares:
                for titular in titulares:
                    h = calcular_hash(titular)
                    
                    if not existe_noticia(con_db, h):
                        # CASO 1: Noticia NUEVA -> Analizar y Guardar
                        sentimiento = analizar_sentimiento_modelo(titular, modelo)
                        guardar_noticia(con_db, h, activo, fuente_base, titular, sentimiento, tipo)
                        print(f"    [NUEVA] {sentimiento:+.1f} | {titular[:50]}...")
                    else:
                        # CASO 2: Noticia EXISTENTE -> Ignorar (ya esta en DB)
                        # print(f"    [EXISTE] {titular[:30]}...") # Un-comment para debug
                        pass
            else:
                print("    Sin resultados validos.")
        
        # 2. CALCULO DE SENTIMIENTO (Ventana de tiempo)
        # Consultamos a DB por todo lo valido en las ultimas HORAS_VALIDEZ
        promedio, cuenta = obtener_sentimiento_promedio(con_db, activo, HORAS_VALIDEZ)
        
        resultados[activo] = {
            'score': promedio,
            'count': cuenta
        }
        
    return resultados

def main():
    print("==============================================")
    print("   ANALIZADOR DE SENTIMIENTO CON DUCKDB       ")
    print("==============================================")
    print(f"Ventana de Analisis: Ultimas {HORAS_VALIDEZ} horas.")
    print("==============================================\n")
    
    # Inicializar DB
    init_db()
    con = duckdb.connect(DB_PATH)
    
    # Cargar Modelo
    modelo = cargar_modelo()
    
    print("\n>>> CRIPTO NEWs CHECK")
    res_cripto = procesar_activos(activos_cripto, fuentes_cripto, modelo, con, "CRYPTO")
    
    print("\n>>> MARKET NEWs CHECK")
    res_acciones = procesar_activos(activos_acciones, fuentes_acciones, modelo, con, "STOCK")
    
    con.close()
    
    # REPORTE FINAL
    print("\n\n==============================================")
    print("           REPORTE DE SENTIMIENTO             ")
    print(f"           (Ultimas {HORAS_VALIDEZ} horas)             ")
    print("==============================================")
    all_results = {**res_cripto, **res_acciones}
    
    if all(d['count'] == 0 for d in all_results.values()):
        print("No se encontraron noticias recientes en la base de datos.")
        print("Intenta nuevamente mas tarde o revisa tu conexion.")
    else:
        print(f"{'ACTIVO':<15} | {'MUESTRAS':<8} | {'SENTIMIENTO'}")
        print("-" * 50)
        for activo, data in all_results.items():
            if data['count'] > 0:
                score = data['score']
                estado = "NEUTRO"
                if score > 0.2: estado = "POSITIVO"
                if score < -0.2: estado = "NEGATIVO"
                print(f"{activo:<15} | {data['count']:<8} | {score:>.4f} ({estado})")
            else:
                 print(f"{activo:<15} | 0        | ---")
    print("==============================================")

if __name__ == "__main__":
    main()
