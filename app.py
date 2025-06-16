import hydralit_components as hc
import logging
import streamlit as st
import requests
import boto3
import uuid
import json
from datetime import datetime
import re
import pandas as pd
from pathlib import Path
from PIL import Image
from transformers import MarianMTModel, MarianTokenizer, pipeline
import torch
from streamlit.components.v1 import html
from street_bundling import group_by_street

# Set page configuration as the first Streamlit command
st.set_page_config(
    page_title="Gestión de Incidencias",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Suppress Streamlit and PyTorch warnings
logging.getLogger("streamlit").setLevel(logging.INFO)

# Contexto detallado para el chatbot
INSTRUCCIONES_CHATBOT = """
Eres un asistente virtual para ayudar a los ciudadanos a reportar incidencias relacionadas con el mobiliario urbano en una plataforma web de gestión de incidencias. La plataforma tiene una estructura con las siguientes páginas accesibles desde un menú de navegación:

- **Home**: Página principal con información general sobre la plataforma.
- **Poner Incidencia**: Página donde los usuarios pueden reportar una incidencia subiendo una foto de la etiqueta identificativa del mobiliario (como farolas, bancos, papeleras), indicando la calle/ubicación (por ejemplo, "Calle Mayor, 5, Valencia" o una intersección) y escribiendo una descripción clara del problema (por ejemplo, "la farola está rota").
- **Ver Incidencias**: Página restringida para técnicos autenticados donde se consultan incidencias reportadas.
- **Iniciar Sesión**: Página para que los técnicos inicien sesión.
- **Chatbot**: Página actual donde los usuarios interactúan contigo.

**Tu función al recibir un reporte de incidencia (por ejemplo, "una farola rota") es:**
1. Informar al usuario de forma amable y profesional que debe reportar la incidencia en la página "Poner Incidencia".
2. Explicar que en esa página puede subir una foto de la etiqueta identificativa del mobiliario, indicar la ubicación exacta (calle, número o intersección) y describir el problema.
3. No pedir detalles adicionales en el chat, ya que estos deben ingresarse en la página "Poner Incidencia".
4. Si el usuario no menciona una incidencia, responder de forma general ofreciendo ayuda y sugiriendo usar la página "Poner Incidencia" para reportar problemas.

**Ejemplo de respuesta para un reporte como "Veo una farola rota en la calle":**
"Gracias por informarme. Por favor, dirígete a la página 'Poner Incidencia' en el menú de navegación. Allí podrás subir una foto de la etiqueta identificativa de la farola, indicar la ubicación exacta (calle, número o intersección) y describir el problema. ¡Esto nos ayudará a procesar tu reporte rápidamente!"

Responde siempre en tono profesional, breve y cercano, en español.
"""

# Configurar clientes de AWS
s3 = boto3.client('s3', region_name='us-east-1')
rekognition = boto3.client('rekognition', region_name='us-east-1')
bucket_name = 'incidencias-ayuntamientos-dh'

# Determinar el dispositivo (forzar CPU para evitar problemas con MPS)
device = "cpu"
print(f"Using device: {device}")

# Cargar modelo y tokenizer para traducción español -> inglés
model_name = "Helsinki-NLP/opus-mt-en-es"
model, tokenizer = None, None
try:
    tokenizer = MarianTokenizer.from_pretrained(model_name)
    model = MarianMTModel.from_pretrained(model_name)
    # Mover el modelo a CPU de manera segura
    model = model.to_empty(device="cpu")
    print("Translation model initialized successfully")
except Exception as e:
    print(f"Error loading translation model: {e}")

# Inicializar el clasificador de zero-shot para categorización automática
classifier = None
try:
    # Usar un modelo más ligero para evitar problemas de memoria
    classifier = pipeline("zero-shot-classification", 
                        model="valhalla/distilbart-mnli-12-1", 
                        device="cpu")  # Forzar CPU
    print("Classifier initialized successfully")
except Exception as e:
    print(f"Error loading zero-shot classifier: {e}")


def traducir_texto(texto, modelo=model, tokenizer=tokenizer):
    if not texto.strip() or modelo is None or tokenizer is None:
        return ""
    try:
        # Asegurarse de que el modelo está en CPU
        modelo = modelo.to_empty(device="cpu")
        batch = tokenizer([texto], return_tensors="pt", padding=True)
        translated = modelo.generate(**batch)
        texto_traducido = tokenizer.decode(translated[0], skip_special_tokens=True)
        return texto_traducido
    except Exception as e:
        st.error(f"Error translating text: {e}")
        return ""

# Estilos CSS personalizados
st.markdown("""
    <style>
    /* Navbar principal - Elevado con sombra suave */
    div[role="tablist"] {
        background: rgba(255, 255, 255, 0.95);
        border-radius: 24px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.08);
        padding: 0.5rem 2rem;
        display: flex;
        justify-content: center;
        gap: 1.5rem;
        margin: 1rem auto;
        max-width: 80%;
        backdrop-filter: blur(4px);
        border: 1px solid rgba(0,0,0,0.05);
    }

    /* Botones - Estilo minimalista */
    div[role="tab"] {
        border: none;
        background: transparent !important;
        padding: 0.75rem 1.5rem;
        border-radius: 20px;
        font-weight: 500;
        color: #4a4a4a !important;
        cursor: pointer;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        margin: 0 0.25rem;
    }

    /* Efecto hover suave */
    div[role="tab"]:hover:not([aria-selected="true"]) {
        background: rgba(0, 0, 0, 0.03) !important;
        color: #2c3e50 !important;
        transform: translateY(-1px);
    }

    /* Estado activo - Destacado con acento */
    div[aria-selected="true"] {
        background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%) !important;
        color: #1a73e8 !important;
        box-shadow: 0 4px 12px rgba(26, 115, 232, 0.15);
        font-weight: 600;
    }

    /* Borde inferior animado en hover */
    div[role="tab"]:after {
        content: '';
        position: absolute;
        bottom: 6px;
        left: 50%;
        width: 0;
        height: 2px;
        background: #1a73e8;
        transition: all 0.3s ease;
        transform: translateX(-50%);
    }

    div[role="tab"]:hover:after {
        width: calc(100% - 2rem);
    }

    /* Ajustes generales de espaciado */
    .block-container {
        padding-top: 1.5rem;
    }

    /* Sidebar más consistente */
    [data-testid="stSidebar"] {
        padding: 2rem 1.5rem;
        background: #f8f9fa;
        box-shadow: 4px 0 20px rgba(0,0,0,0.06);
        border-right: 1px solid rgba(0,0,0,0.04);
    }
    </style>
""", unsafe_allow_html=True)


def setup_sidebar():
    with st.sidebar:
        st.image("Images/logo.png", use_container_width=True)
        st.markdown("## 📍 Menú Principal", unsafe_allow_html=True)

        # Botones de navegación con estilo
        def nav_button(name, emoji):
            clicked = st.button(f"{emoji}  {name}", key=f"nav_{name}")
            if clicked:
                st.session_state.selected_page = name

        if st.session_state.get("authenticated"):
            nav_button("Home", "🏠")
            nav_button("Ver Incidencias", "📋")
            nav_button("Estadísticas", "📊")
            nav_button("Cerrar Sesión", "🔒")
        else:
            nav_button("Home", "🏠")
            nav_button("Poner Incidencia", "📝")
            nav_button("Iniciar Sesión", "🔑")
            nav_button("Chatbot", "💬")

        # Estilos adicionales en la barra lateral
        st.markdown("""
        <style>
        section[data-testid="stSidebar"] .stButton > button {
            width: 100%;
            background-color: #f1f3f4;
            color: #333;
            padding: 1rem;
            border-radius: 12px;
            margin-bottom: 10px;
            font-weight: 600;
            font-size: 16px;
            transition: all 0.2s ease-in-out;
        }
        section[data-testid="stSidebar"] .stButton > button:hover {
            background-color: #e2e6ea;
            color: #1a73e8;
            transform: scale(1.02);
        }
        </style>
        """, unsafe_allow_html=True)

        # Ayuda y contacto
        st.markdown("## 📌 Ayuda Rápida")
        st.markdown("""
        - **Reporte de incidencias**: 24/7  
        - **Soporte técnico**: L-V 9:00-14:00  
        - **Teléfono emergencias**: 900 123 456
        """)
        st.markdown("---")
        st.markdown("## 📬 Contacto")
        st.markdown("""
        **Oficina de Atención Ciudadana**  
        Calle Municipal, 123  
        📞 963 000 000  
        📧 incidencias@ayto-valencia.es
        """)

# Función para extraer texto de la imagen con Rekognition
def extract_text_from_image(image):
    try:
        image_key = f"images/{str(uuid.uuid4())}.png"
        s3.upload_fileobj(image, bucket_name, image_key)
        response = rekognition.detect_text(Image={'S3Object': {'Bucket': bucket_name, 'Name': image_key}})
        detected_text = ' '.join([t['DetectedText'] for t in response['TextDetections'] if t['Type'] == 'LINE'])
        return detected_text
    except Exception as e:
        st.error(f"Error al procesar la imagen: {str(e)}")
        return None

# Home page
def pagina_home():
    st.title("🏙️ Bienvenido a la Plataforma de Incidencias de Valencia")
    st.image("Images/valencia.jpg", use_container_width=True, caption="Nuestra querida ciudad de Valencia")
    st.markdown("""
    ## Sobre Nosotros
    Somos el equipo encargado de mantener y mejorar los espacios públicos de la ciudad de Valencia.
    
    Esta plataforma permite a los ciudadanos:
    - 📢 Reportar incidencias en calles, parques y mobiliario urbano.
    - 📋 Consultar el estado de las incidencias ya registradas.
    - 🤝 Comunicarse directamente con el equipo de mantenimiento.
    
    ### Nuestra Misión
    Hacer de Valencia una ciudad más limpia, segura y agradable para todos.
    
    ---
    """)
    st.info("¿Tienes alguna incidencia? Usa el menú para **Poner Incidencia** o consulta las ya registradas en **Ver Incidencias**.")

# Página de inicio de sesión
def login():
    st.title("Login - Acceso restringido a ver incidencias")
    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if st.button("Iniciar sesión"):
        if username == "AjAlbuixech" and password == "1234":
            st.session_state.authenticated = True
            st.query_params["nav"] = "report"
            st.success("Bienvenido!")
            st.rerun()
        else:
            st.error("Credenciales incorrectas")

def reportar_incidencia():
    st.title("Reportar Incidencia")
    st.subheader("Captura una foto con la cámara o sube una foto de tu galería:")
    enable = st.checkbox("Activar cámara")
    picture = st.camera_input("Toma una foto de la etiqueta del mobiliario o elemento", disabled=not enable)
    photo = st.file_uploader("Sube una foto de la etiqueta del mobiliario o elemento", type=["jpg", "png"])
    
    ubicacion = st.text_input("Ubicación * (por ejemplo, Calle Sagasta, Madrid):")
    descripcion_input = st.text_area("Descripción adicional * (describe brevemente la incidencia, preferiblemente en inglés, pero se acepta español):")


    if st.button("Procesar Incidencia"):
        print("Iniciando procesamiento de incidencia...")
        image = picture if picture is not None else photo

        try:
            if image is None:
                st.error("Por favor, proporciona una imagen (cámara o subir).")
                return
            if not ubicacion or not descripcion_input:
                st.error("Ubicación y descripción son campos obligatorios.")
                return
            if classifier is None:
                st.error("Clasificador no disponible. Verifica la configuración del modelo.")
                return

            with st.spinner("Procesando la incidencia, espera un momento..."):
                # Procesar imagen con Rekognition
                print("Llamando a extract_text_from_image...")
                try:
                    detected_text = extract_text_from_image(image)
                    print("Extracción de texto completada:", detected_text)
                except Exception as e:
                    st.error(f"Error al procesar la imagen con Rekognition: {str(e)}")
                    return

                if detected_text:
                    # Extraer datos del texto detectado
                    print("Analizando texto detectado...")
                    id_match = re.search(r'ID:\s*([A-Z0-9-]+)', detected_text)
                    state_match = re.search(r'Estado:\s*(\w+)', detected_text)
                    installation_date_match = re.search(r'Fecha de instalación:\s*(\d{4}-\d{2}-\d{2})', detected_text)
                    last_review_match = re.search(r'Última revisión:\s*(\d{4}-\d{2}-\d{2})', detected_text)
                    type_match = re.search(r'Tipo:\s*(.+)', detected_text)
                    observations_match = re.search(r'Observaciones:\s*(.+)', detected_text)

                    # Traducir descripción al español (si es necesario) y al inglés para clasificación
                    print("Traduciendo descripción...")
                    descripcion_es = descripcion_input
                    descripcion_en = descripcion_input
                    try:
                        # Traducir de español a español (si ya está en español, no hace nada)
                        descripcion_es = traducir_texto(descripcion_input, model, tokenizer) if model and tokenizer else descripcion_input
                        # Traducir de español a inglés para el clasificador
                        en_trans_model_name = "Helsinki-NLP/opus-mt-es-en"
                        en_tokenizer = MarianTokenizer.from_pretrained(en_trans_model_name)
                        en_model = MarianMTModel.from_pretrained(en_trans_model_name)
                        en_model = en_model.to("cpu")  # Forzar CPU
                        batch = en_tokenizer([descripcion_input], return_tensors="pt", padding=True)
                        translated = en_model.generate(**batch)
                        descripcion_en = en_tokenizer.batch_decode(translated, skip_special_tokens=True)[0]
                        print("Traducción completada - Español:", descripcion_es, "Inglés:", descripcion_en)
                    except Exception as e:
                        st.warning(f"Error en la traducción: {e}. Usando descripción original.")
                        print(f"Error en la traducción: {str(e)}")
                        descripcion_es = descripcion_input
                        descripcion_en = descripcion_input

                    # Clasificación automática de la categoría
                    categorias = ["Farola", "Banco", "Papelera","Contenedor", "Señalización", "Otros"]
                    categoria = "Otros"  # Fallback por defecto
                    probabilidades = {}
                    print("Ejecutando clasificación zero-shot con input:", descripcion_en)
                    try:
                        # Añadir contexto adicional para mejorar la clasificación
                        context = f"This is a description of a street furniture issue: {descripcion_en}"
                        
                        # Obtener clasificación del modelo
                        result = classifier(context, candidate_labels=categorias)
                        probabilidades = dict(zip(result['labels'], result['scores']))
                        
                        # Ajustar probabilidades basado en metadatos
                        if id_match and id_match.group(1):
                            id_prefix = id_match.group(1)[0].upper()
                            if id_prefix == 'F':
                                probabilidades['Farola'] = min(1.0, probabilidades.get('Farola', 0) + 0.3)
                            elif id_prefix == 'B':
                                probabilidades['Banco'] = min(1.0, probabilidades.get('Banco', 0) + 0.3)
                            elif id_prefix == 'P':
                                probabilidades['Papelera'] = min(1.0, probabilidades.get('Papelera', 0) + 0.3)
                            elif id_prefix == 'C':
                                probabilidades['Contenedor'] = min(1.0, probabilidades.get('Contenedor', 0) + 0.3)
                            elif id_prefix == 'S':
                                probabilidades['Señalización'] = min(1.0, probabilidades.get('Señalización', 0) + 0.3)
                        
                        # Ajustar basado en el tipo
                        if type_match and type_match.group(1):
                            tipo = type_match.group(1).lower()
                            if 'farola' in tipo or 'lamp' in tipo or 'led' in tipo:
                                probabilidades['Farola'] = min(1.0, probabilidades.get('Farola', 0) + 0.3)
                            elif 'banco' in tipo or 'bench' in tipo:
                                probabilidades['Banco'] = min(1.0, probabilidades.get('Banco', 0) + 0.3)
                            elif 'papelera' in tipo or 'trash' in tipo:
                                probabilidades['Papelera'] = min(1.0, probabilidades.get('Papelera', 0) + 0.3)
                            elif 'contenedor' in tipo or 'bin' in tipo:
                                probabilidades['Contenedor'] = min(1.0, probabilidades.get('Contenedor', 0) + 0.3)
                            elif 'señal' in tipo or 'sign' in tipo:
                                probabilidades['Señalización'] = min(1.0, probabilidades.get('Señalización', 0) + 0.3)
                        
                        # Seleccionar la categoría con mayor probabilidad
                        categoria = max(probabilidades.items(), key=lambda x: x[1])[0]
                        print("Clasificación completada:", categoria, probabilidades)
                    except Exception as e:
                        st.warning(f"Error en la clasificación: {str(e)}. Usando categoría por defecto.")
                        print(f"Error en la clasificación: {str(e)}")
                        # Fallback heurístico mejorado
                        descripcion_lower = descripcion_input.lower()
                        # Palabras clave para farolas
                        farola_keywords = ["farola", "streetlight", "lamp", "luz", "iluminación", "poste", "poste de luz", 
                                         "lámpara", "luminaria", "alumbrado", "farol", "farolillo", "luz pública"]
                        # Palabras clave para otros elementos
                        banco_keywords = ["banco", "bench", "asiento", "banca"]
                        papelera_keywords = ["papelera", "trash", "basura", "contenedor", "waste", "litter"]
                        señal_keywords = ["señal", "sign", "señalización", "traffic", "tráfico", "semáforo"]
                        contenedor_keywords = ["contenedor", "bin", "container", "reciclaje", "recycling"]

                        # Contar coincidencias para cada categoría
                        farola_count = sum(1 for word in farola_keywords if word in descripcion_lower)
                        banco_count = sum(1 for word in banco_keywords if word in descripcion_lower)
                        papelera_count = sum(1 for word in papelera_keywords if word in descripcion_lower)
                        señal_count = sum(1 for word in señal_keywords if word in descripcion_lower)
                        contenedor_count = sum(1 for word in contenedor_keywords if word in descripcion_lower)

                        # Asignar la categoría con más coincidencias
                        counts = {
                            "Farola": farola_count,
                            "Banco": banco_count,
                            "Papelera": papelera_count,
                            "Señalización": señal_count,
                            "Contenedor": contenedor_count
                        }
                        
                        if max(counts.values()) > 0:
                            categoria = max(counts.items(), key=lambda x: x[1])[0]
                        
                        print("Categoría heurística asignada:", categoria)

                    incidence_data = {
                        'ID': id_match.group(1) if id_match else "No disponible",
                        'Ubicación': ubicacion,
                        'Estado': state_match.group(1) if state_match else "No disponible",
                        'Fecha de instalación': installation_date_match.group(1) if installation_date_match else "No disponible",
                        'Última revisión': last_review_match.group(1) if last_review_match else "No disponible",
                        'Tipo': type_match.group(1) if type_match else "No disponible",
                        'Observaciones': observations_match.group(1) if observations_match else "No disponible",
                        'Descripción adicional (EN)': descripcion_en,
                        'Descripción adicional (ES)': descripcion_es,
                        'Texto Extraído': detected_text,
                        'Timestamp': datetime.utcnow().isoformat(),
                        'Categoría': categoria,
                        'Probabilidades': probabilidades
                    }

                    # Guardar en S3
                    print("Subiendo a S3...")
                    try:
                        incidence_id = str(uuid.uuid4())
                        s3.put_object(
                            Bucket=bucket_name,
                            Key=f"incidencias/{incidence_id}.json",
                            Body=json.dumps(incidence_data)
                        )
                        print("Subida a S3 completada.")
                        st.success(f"Incidencia reportada correctamente. Categoría asignada: {categoria}")
                    except Exception as e:
                        st.error(f"Error al guardar en S3: {str(e)}")
                else:
                    st.warning("Por favor, sube una foto de la etiqueta de la farola.")
        except Exception as e:
            st.error(f"Error general al procesar la incidencia: {str(e)}")
            print(f"Error general: {str(e)}")
            
# Página de "Ver Incidencias"
def ver_incidencias():
    st.title("Ver Incidencias - Técnico")
    
    categorias = ["Todas", "Farola", "Banco", "Papelera", "Contenedor", "Señalización", "Otros"]
    categoria_filtro = st.selectbox("Filtrar por categoría:", categorias)
    
    try:
        response = s3.list_objects_v2(Bucket=bucket_name, Prefix="incidencias/")
        incidences = []

        if 'Contents' in response:
            for obj in response['Contents']:
                if obj['Key'].endswith('.json'):
                    metadata_obj = s3.get_object(Bucket=bucket_name, Key=obj['Key'])
                    metadata_content = metadata_obj['Body'].read().decode('utf-8')
                    if metadata_content.strip():
                        metadata = json.loads(metadata_content)
                        # Ensure 'Categoría' exists, default to 'Desconocida' if missing
                        if 'Categoría' not in metadata or not metadata['Categoría']:
                            metadata['Categoría'] = 'Desconocida'
                        # Only include if category matches filter (or "Todas")
                        if categoria_filtro == "Todas" or metadata['Categoría'] == categoria_filtro:
                            incidences.append(metadata)

        if incidences:
            
            if incidences:
                
            # — Agrupamiento automático por calle —
                street_groups = group_by_street(incidences)
            if street_groups:
                st.subheader("🔗 Agrupaciones automáticas por calle")
                for grp in street_groups:
                    calle = grp["street"].title()
                    n = grp["count"]
                    ids = [inc["ID"] for inc in grp["incidencias"]]
                    st.markdown(f"- **{calle}**: {n} incidencias → IDs: {', '.join(ids)}")
                st.markdown("---")
            # — Fin agrupamiento automático — 
                
            for inc in sorted(incidences, key=lambda x: x.get('Timestamp', ''), reverse=True):
                with st.expander(f"🆔 ID: {inc.get('ID', 'No disponible')} | 📍 {inc.get('Ubicación', 'No disponible')} | 📌 Categoría: {inc.get('Categoría', 'No disponible')}"):
                    st.markdown(f"**📍 Ubicación:** {inc.get('Ubicación', 'No disponible')}")
                    st.markdown(f"**🔧 Estado:** {inc.get('Estado', 'No disponible')}")
                    st.markdown(f"**📅 Fecha de instalación:** {inc.get('Fecha de instalación', 'No disponible')}")
                    st.markdown(f"**🔄 Última revisión:** {inc.get('Última revisión', 'No disponible')}")
                    st.markdown(f"**💡 Tipo:** {inc.get('Tipo', 'No disponible')}")
                    st.markdown(f"**📝 Observaciones:** {inc.get('Observaciones', 'No disponible')}")
                    st.markdown(f"**🗒️ Descripción en inglés:** {inc.get('Descripción adicional (EN)', 'No disponible')}")
                    st.markdown(f"**🗒️ Descripción traducida al español:** {inc.get('Descripción adicional (ES)', 'No disponible')}")
                    st.markdown(f"**📷 Texto extraído:** `{inc.get('Texto Extraído', '')}`")
                    st.markdown(f"**📊 Probabilidades por categoría:** {inc.get('Probabilidades', 'No disponible')}")
                    st.caption(f"🕒 Reportado: {inc.get('Timestamp', '')}")
                   
        else:
            st.info("No hay incidencias registradas para la categoría seleccionada.")
    except Exception as e:
        st.error(f"Error al cargar incidencias: {str(e)}")

def pagina_estadisticas():
    st.title("📊 Estadísticas de Incidencias")

    try:
        # Fetch incidencias
        response = s3.list_objects_v2(Bucket=bucket_name, Prefix="incidencias/")
        incidences = []

        if 'Contents' in response:
            for obj in response['Contents']:
                if obj['Key'].endswith('.json'):
                    metadata_obj = s3.get_object(Bucket=bucket_name, Key=obj['Key'])
                    metadata_content = metadata_obj['Body'].read().decode('utf-8')
                    if metadata_content.strip():
                        metadata = json.loads(metadata_content)
                        if 'Categoría' not in metadata or not metadata['Categoría']:
                            metadata['Categoría'] = 'Desconocida'
                        incidences.append(metadata)

        if not incidences:
            st.info("No hay incidencias para mostrar estadísticas.")
            return

        # Crear DataFrame
        df = pd.DataFrame(incidences)

        # Filtro de categoría
        categorias = ["Todas"] + sorted(df['Categoría'].unique())
        categoria_filtro = st.selectbox("Filtrar por categoría:", categorias)

        filtered_df = df if categoria_filtro == "Todas" else df[df['Categoría'] == categoria_filtro]

        if filtered_df.empty:
            st.info(f"No hay incidencias para la categoría '{categoria_filtro}'.")
            return

        # Crear dos columnas para las gráficas
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("📈 Distribución por Categoría")
            # Gráfico de barras
            categoria_counts = filtered_df['Categoría'].value_counts().to_dict()
            labels = list(categoria_counts.keys())
            values = list(categoria_counts.values())
            
            chart_html = f"""
            <canvas id="barChart" height="300"></canvas>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <script>
            const ctx = document.getElementById('barChart').getContext('2d');
            new Chart(ctx, {{
                type: 'bar',
                data: {{
                    labels: {labels},
                    datasets: [{{
                        label: 'Número de Incidencias',
                        data: {values},
                        backgroundColor: 'rgba(59, 130, 246, 0.7)',
                        borderColor: 'rgba(59, 130, 246, 1)',
                        borderWidth: 1
                    }}]
                }},
                options: {{
                    responsive: true,
                    plugins: {{
                        legend: {{
                            position: 'top',
                        }},
                        title: {{
                            display: true,
                            text: 'Incidencias por Categoría'
                        }}
                    }},
                    scales: {{
                        y: {{
                            beginAtZero: true,
                            ticks: {{
                                stepSize: 1
                            }}
                        }}
                    }}
                }}
            }});
            </script>
            """
            html(chart_html, height=400)

        with col2:
            st.subheader("🍩 Estado de Incidencias")
            # Gráfico circular
            estado_counts = filtered_df['Estado'].value_counts().to_dict()
            labels = list(estado_counts.keys())
            values = list(estado_counts.values())
            
            chart_html = f"""
            <canvas id="pieChart" height="300"></canvas>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <script>
            const ctx = document.getElementById('pieChart').getContext('2d');
            new Chart(ctx, {{
                type: 'doughnut',
                data: {{
                    labels: {labels},
                    datasets: [{{
                        data: {values},
                        backgroundColor: [
                            'rgba(255, 99, 132, 0.7)',
                            'rgba(54, 162, 235, 0.7)',
                            'rgba(255, 206, 86, 0.7)',
                            'rgba(75, 192, 192, 0.7)',
                            'rgba(153, 102, 255, 0.7)'
                        ],
                        borderColor: [
                            'rgba(255, 99, 132, 1)',
                            'rgba(54, 162, 235, 1)',
                            'rgba(255, 206, 86, 1)',
                            'rgba(75, 192, 192, 1)',
                            'rgba(153, 102, 255, 1)'
                        ],
                        borderWidth: 1
                    }}]
                }},
                options: {{
                    responsive: true,
                    plugins: {{
                        legend: {{
                            position: 'right',
                        }},
                        title: {{
                            display: true,
                            text: 'Distribución por Estado'
                        }}
                    }}
                }}
            }});
            </script>
            """
            html(chart_html, height=400)

        # Listado de incidencias
        st.subheader("📋 Listado de Incidencias")
        max_display = 10
        for idx, inc in enumerate(
            sorted(filtered_df.to_dict('records'), key=lambda x: x.get('Timestamp', ''), reverse=True)[:max_display]
        ):
            with st.expander(f"🆔 ID: {inc.get('ID', 'No disponible')} | 📍 {inc.get('Ubicación', 'No disponible')} | 📌 {inc.get('Categoría', 'No disponible')}"):
                st.markdown(f"📍 **Ubicación:** {inc.get('Ubicación', 'No disponible')}")
                st.markdown(f"🔧 **Estado:** {inc.get('Estado', 'No disponible')}")
                st.markdown(f"📅 **Fecha de instalación:** {inc.get('Fecha de instalación', 'No disponible')}")
                st.markdown(f"🔄 **Última revisión:** {inc.get('Última revisión', 'No disponible')}")
                st.markdown(f"💡 **Tipo:** {inc.get('Tipo', 'No disponible')}")
                st.markdown(f"📝 **Observaciones:** {inc.get('Observaciones', 'No disponible')}")
                st.markdown(f"🗒️ **Descripción (EN):** {inc.get('Descripción adicional (EN)', 'No disponible')}")
                st.markdown(f"🗒️ **Descripción (ES):** {inc.get('Descripción adicional (ES)', 'No disponible')}")
                st.markdown(f"📷 **Texto extraído:** {inc.get('Texto Extraído', '')}")
                st.caption(f"🕒 Reportado: {inc.get('Timestamp', '')}")

        if len(filtered_df) > max_display:
            st.info(f"Mostrando {max_display} de {len(filtered_df)} incidencias. Filtra por categoría para ver más detalles.")

    except Exception as e:
        st.error(f"Error al generar estadísticas: {str(e)}")
        print(f"Statistics error: {str(e)}")

# Página del Chatbot
def chatbot_page():
    st.title("🤖 Chatbot")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {"role": "system", "content": INSTRUCCIONES_CHATBOT}
        ]

    user_input = st.text_input("Escribe tu mensaje:")

    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        messages = st.session_state.chat_history.copy()

        try:
            response = requests.post(
                "http://localhost:11434/api/chat",
                json={"model": "llama3:latest", "messages": messages, "stream": False},
                timeout=30
            )

            if response.status_code == 200:
                try:
                    data = response.json()
                    answer = data.get("message", {}).get("content", "No response content")
                    if not answer:
                        st.error("No valid response content received from Ollama.")
                    else:
                        st.session_state.chat_history.append({"role": "assistant", "content": answer})
                except ValueError:
                    st.error("Error parsing JSON response from Ollama.")
            else:
                st.error(f"Ollama API error: status {response.status_code}, {response.text}")
        except requests.exceptions.RequestException as e:
            st.error(f"Failed to connect to Ollama: {e}")
            st.write("Ensure Ollama is running (`curl http://localhost:11434`) and the model 'llama3:latest' is available (`ollama list`).")

    if len(st.session_state.chat_history) >= 2:
        latest_messages = st.session_state.chat_history[-2:]
        for msg in latest_messages:
            if msg["role"] == "user":
                st.markdown(f"👤 **Tú**: {msg['content']}")
            elif msg["role"] == "assistant":
                st.markdown(f"🤖 **Chatbot**: {msg['content']}")
def main():
    if "selected_page" not in st.session_state:
        st.session_state.selected_page = "Home"

    setup_sidebar()
    selected_page = st.session_state.selected_page

    if selected_page == "Home":
        pagina_home()
    elif selected_page == "Iniciar Sesión":
        login()
    elif selected_page == "Cerrar Sesión":
        st.session_state.authenticated = False
        st.success("Sesión cerrada correctamente.")
        st.session_state.selected_page = "Home"
        st.rerun()
    elif selected_page == "Poner Incidencia":
        reportar_incidencia()
    elif selected_page == "Ver Incidencias":
        if st.session_state.get("authenticated"):
            ver_incidencias()
        else:
            st.warning("Por favor, inicia sesión para ver incidencias.")
            login()
    elif selected_page == "Estadísticas":
        if st.session_state.get("authenticated"):
            pagina_estadisticas()
        else:
            st.warning("Por favor, inicia sesión para ver estadísticas.")
            login()
    elif selected_page == "Chatbot":
        chatbot_page()

if __name__ == "__main__":
    main()
