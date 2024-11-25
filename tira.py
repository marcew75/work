import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import requests
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import streamlit as st



# Configuración de las API keys
MAPS_API_KEY = st.secrets["MAPS_API_KEY"]  # Clave de Google Maps
SERP_API_KEY = st.secrets["SERP_API_KEY"]  # Clave de SerpAPI

def is_valid_url(url):
    """Valida si una URL es válida y cumple con ciertos criterios."""
    try:
        parsed = urlparse(url)
        if not all([parsed.scheme, parsed.netloc]):
            return False
        excluded_domains = ['facebook.com', 'twitter.com', 'instagram.com']
        if any(domain in parsed.netloc for domain in excluded_domains):
            return False
        return True
    except Exception:
        return False

def extract_emails(text):
    """Extrae correos electrónicos de un texto usando expresiones regulares."""
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return list(set(re.findall(email_pattern, text)))

def scrape_page(url):
    """Extrae el contenido HTML de una página web."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        st.warning(f"Error al acceder a {url}: {str(e)}")
        return ""

def scrape_emails_from_urls(urls, max_workers=5):
    """Extrae correos electrónicos de una lista de URLs usando múltiples hilos."""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        html_contents = list(executor.map(scrape_page, urls))
        
    for url, html_content in zip(urls, html_contents):
        if html_content:
            emails = extract_emails(html_content)
            for email in emails:
                results.append([url, email])
    
    return results

def search_google(query, api_key, num_results=10):
    """Realiza una búsqueda en Google usando SerpAPI."""
    search_url = "https://serpapi.com/search"
    params = {
        'q': query,
        'engine': 'google',
        'api_key': api_key,
        'num': num_results,  # Usar num_results en lugar de un valor fijo
        'hl': 'es',
        'gl': 'ar',
        'google_domain': 'google.com.ar'
    }
    try:
        response = requests.get(search_url, params=params, timeout=10)
        response.raise_for_status()
        results = response.json().get("organic_results", [])
        return [result["link"] for result in results if "link" in result]
    except requests.exceptions.RequestException as e:
        st.error(f"Error en la búsqueda: {str(e)}")
        return []


def get_places_nearby(lat, lon, radius, api_key, keyword=None):
    """Busca lugares cercanos usando Google Maps Places API."""
    places_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{lat},{lon}",
        "radius": radius * 1000,  # Convertir km a metros
        "key": api_key,
    }
    if keyword:
        params["keyword"] = keyword  # Filtrar por palabra clave

    try:
        response = requests.get(places_url, params=params)
        response.raise_for_status()
        data = response.json()
        return [
            {
                "name": place["name"],
                "address": place.get("vicinity", ""),
                "types": place.get("types", [])
            }
            for place in data.get("results", [])
        ]
    except Exception as e:
        st.error(f"Error al obtener lugares cercanos: {str(e)}")
        return []

def create_map_with_search_radius(center_lat=-38.0, center_lon=-57.5, zoom=11):
    """Crea un mapa con círculo de radio de búsqueda."""
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom)
    folium.plugins.Draw(
        draw_options={
            'circle': True,
            'marker': True
        },
        position='topleft'
    ).add_to(m)
    return m

# Interfaz de usuario en Streamlit
st.title("Scraping de Correos Electrónicos con Filtro Geográfico")

# Entrada del usuario
query = st.text_input("Consulta de búsqueda (ej: 'gimnasios', 'restaurantes', etc.)")
radius = st.slider("Radio de búsqueda (km):", 1, 10, 5)

# Mostrar mapa y obtener coordenadas
st.subheader("Selecciona la ubicación en el mapa")
mapa = create_map_with_search_radius()
map_data = st_folium(mapa, height=500)

lat, lon = None, None
if map_data["last_clicked"]:
    lat = map_data["last_clicked"]["lat"]
    lon = map_data["last_clicked"]["lng"]
    st.success(f"Ubicación seleccionada: {lat}, {lon}")


max_emails = st.number_input(
    "Número máximo de correos electrónicos a encontrar:",
    min_value=1,
    max_value=1000,
    value=10,
    step=1,
    help="Define cuántos correos como máximo quieres encontrar en esta búsqueda."
)



# Botón de búsqueda
# Botón de búsqueda
if st.button("Buscar correos"):
    if not query:
        st.warning("Por favor, ingresa una consulta de búsqueda.")
    elif not lat or not lon:
        st.warning("Por favor, selecciona una ubicación en el mapa.")
    else:
        # Crear un contenedor dinámico para los mensajes
        progress_message = st.empty()
        progress_message.info("Iniciando la búsqueda...")

        with st.spinner("Realizando la búsqueda, por favor espera..."):
            # Paso 1: Buscar URLs válidas
            progress_message.info("Buscando URLs relacionadas con tu consulta...")
            urls = search_google(query, SERP_API_KEY, num_results=max_emails)
            
            if urls:
                progress_message.info(f"Se encontraron {len(urls)} URLs válidas. Iniciando el análisis de correos...")
                
                # Paso 2: Scraping de correos
                emails = scrape_emails_from_urls(urls)
                
                if emails:
                    # Filtrar correos según el límite especificado
                    emails = emails[:max_emails]

                    # Mostrar los resultados en una tabla
                    df = pd.DataFrame(emails, columns=["Sitio Web", "Correo Electrónico"])
                    st.dataframe(df)

                    # Actualizar el mensaje de progreso
                    progress_message.success(f"Se encontraron y se muestran un total de {len(df)} correos electrónicos.")
                    
                    # Botón para descargar los resultados
                    csv = df.to_csv(index=False).encode("utf-8")
                    st.download_button("Descargar CSV", csv, "emails.csv", "text/csv")
                else:
                    progress_message.warning("No se encontraron correos electrónicos en las páginas analizadas.")
            else:
                progress_message.warning("No se encontraron URLs válidas para analizar.")

        # Limpiar el contenedor dinámico al finalizar
        progress_message.empty()


                # Búsqueda en SerpAPI
        # Obtener lugares cercanos (antes de buscar correos)
        places = get_places_nearby(lat, lon, radius, MAPS_API_KEY)

# Iterar sobre los lugares
        for place in places:
            search_query = f"{query} {place['name']} {place['address']}"
            urls = search_google(search_query, SERP_API_KEY)
            st.write(f"Resultados para {search_query}: {urls}")
        for place in places:
                search_query = f"{query} {place['name']} {place['address']}"
                urls = search_google(search_query, SERP_API_KEY)
                st.write(f"Resultados para {search_query}: {urls}")

                    # Scraping de correos electrónicos
                emails = scrape_emails_from_urls(urls)
                if emails:
                    df = pd.DataFrame(emails, columns=["Sitio Web", "Correo Electrónico"])
                    st.dataframe(df)
                    csv = df.to_csv(index=False).encode("utf-8")
                    st.download_button("Descargar CSV", csv, "emails.csv", "text/csv")