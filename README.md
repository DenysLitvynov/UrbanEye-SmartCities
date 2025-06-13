# 🏗️ UrbanEye - Plataforma de Gestión de Incidencias Urbanas

## 📝 Descripción
UrbanEye es una plataforma web inteligente diseñada para facilitar la gestión y reporte de incidencias relacionadas con el mobiliario urbano. La aplicación permite a los ciudadanos reportar problemas de manera eficiente y a los técnicos municipales gestionar y dar seguimiento a estas incidencias.

## ✨ Características Principales

- 📸 **Reporte de Incidencias**: Los ciudadanos pueden subir fotos de etiquetas identificativas del mobiliario urbano y reportar problemas.
- 🤖 **Chatbot Inteligente**: Asistente virtual que guía a los usuarios en el proceso de reporte de incidencias.
- 🔍 **Reconocimiento de Imágenes**: Utiliza AWS Rekognition para procesar y analizar las imágenes subidas.
- 🌐 **Traducción Automática**: Integración con modelos de traducción para procesar reportes en diferentes idiomas.
- 📊 **Panel de Estadísticas**: Visualización de datos y métricas sobre las incidencias reportadas.
- 🔒 **Sistema de Autenticación**: Acceso seguro para técnicos municipales.

## 🚀 Tecnologías Utilizadas

- **Frontend**: Streamlit, Hydralit Components
- **Backend**: Python
- **IA/ML**: 
  - Transformers (Hugging Face)
  - PyTorch
  - AWS Rekognition
- **Cloud**: AWS (S3, Rekognition)
- **Procesamiento de Datos**: Pandas, Pillow

## ⚙️ Requisitos del Sistema

- Python 3.8 o superior
- Conexión a Internet
- Cuenta de AWS (para servicios de Rekognition y S3)

## 🛠️ Instalación

1. Clonar el repositorio:
```bash
git clone [URL_DEL_REPOSITORIO]
cd UrbanEye-SmartCities
```

2. Instalar dependencias:
```bash
pip install -r requirements.txt
```

3. Configurar variables de entorno:
   - Crear un archivo `.env` con las credenciales de AWS
   - Configurar las variables necesarias para el acceso a los servicios

4. Ejecutar la aplicación:
```bash
streamlit run app.py
```

## 📱 Uso

1. **Para Ciudadanos**:
   - Acceder a la página principal
   - Navegar a "Poner Incidencia"
   - Subir foto y completar el formulario de reporte
   - Usar el chatbot para obtener ayuda

2. **Para Técnicos**:
   - Iniciar sesión con credenciales autorizadas
   - Acceder al panel de gestión de incidencias
   - Revisar y actualizar el estado de las incidencias
   - Consultar estadísticas y métricas

## 🤝 Contribución

Las contribuciones son bienvenidas. Por favor, sigue estos pasos:
1. Fork el repositorio
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📞 Contacto

Para más información o soporte, por favor contacta al equipo de desarrollo.