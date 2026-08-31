import os
from google import genai
import pandas as pd
import streamlit as st

# Configuración de la página
st.set_page_config(
    page_title="Agente de Turnos - Centro de Control",
    page_icon="🛡️",
    layout="wide",
)

st.title("🛡️ Agente Inteligente de Turnos - Centro de Control")
st.markdown(
    "Sistema autónomo para la planificación, optimización y gestión de turnos operativos 24/7."
)

# Sidebar para configuración de credenciales y parámetros
with st.sidebar:
    st.header("⚙️ Configuración")
    api_key_input = st.text_input(
        "Gemini API Key",
        type="password",
        help="Ingresa tu clave de API de Google Gemini",
    )

    st.markdown("---")
    st.subheader("📋 Parámetros del Rol")
    num_operadores = st.number_input(
        "Cantidad de Operadores", min_value=3, max_value=30, value=8
    )
    dias_ciclo = st.selectbox(
        "Esquema de Rotación", ["Lunes a Viernes (5x2)", "Turnos 24/7 (4x4)"]
    )
    turno_seleccionado = st.selectbox(
        "Modo de Operación",
        ["Generar Nuevo Rol", "Simular Imprevisto / Baja", "Consultar Reglas"],
    )

# Inicializar cliente de Gemini si hay API Key
client = None
if api_key_input:
    client = genai.Client(api_key=api_key_input)
else:
    # Opcional: Buscar en variables de entorno del sistema operativo
    if os.environ.get("GEMINI_API_KEY"):
        client = genai.Client()

# Área principal del chat / agente
st.markdown("### 💬 Interacción con el Agente")

# Historial de mensajes en la sesión
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "¡Hola! Soy tu agente experto en gestión de turnos para el centro de control. ¿Qué deseas hacer hoy? (Ej: *'Generar el rol para la próxima semana considerando 8 operadores'* o *'Juan reportó descanso médico, ¿quién lo cubre?'*)",
        }
    ]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Entrada del usuario
if prompt := st.chat_input(
    "Escribe tu solicitud para el agente de turnos..."
):
    if not client:
        st.error("Por favor, ingresa tu API Key de Gemini en la barra lateral.")
    else:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("El agente está analizando las restricciones y turnos..."):
                try:
                    # Instrucción de sistema para orientar a Gemini como agente de turnos
                    system_instruction = f"""
                    Eres un agente experto en gestión de recursos humanos y optimización de turnos para un Centro de Control 24/7.
                    Tienes configurados {num_operadores} operadores bajo el esquema: {dias_ciclo}.
                    Tu objetivo es ayudar a coordinar turnos justos, cumplir normativas de descanso, resolver imprevistos y proponer tablas claras.
                    """

                    # Llamada al modelo Gemini
                    response = client.models.generate_content(
                        model = "gemini-2.5-flash",
                        contents=prompt,
                        config=genai.types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.3,
                        ),
                    )

                    answer = response.text
                    st.markdown(answer)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": answer}
                    )
                except Exception as e:
                    error_msg = f"Ocurrió un error al procesar la solicitud: {e}"
                    st.error(error_msg)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": error_msg}
                    )

# Sección de visualización de ejemplo de tabla de turnos
st.markdown("---")
st.subheader("📊 Vista Previa del Rol Actual")
# Generar una tabla simulada para mostrar cómo se vería
data = {
    "Operador": [f"Operador {i+1}" for i in range(num_operadores)],
    "Lunes": ["Mañana", "Mañana", "Tarde", "Noche", "Libre", "Libre", "Tarde", "Noche"][:num_operadores],
    "Martes": ["Mañana", "Mañana", "Tarde", "Noche", "Libre", "Libre", "Tarde", "Noche"][:num_operadores],
    "Miércoles": ["Libre", "Mañana", "Tarde", "Noche", "Libre", "Libre", "Tarde", "Noche"][:num_operadores],
    "Jueves": ["Libre", "Libre", "Tarde", "Noche", "Mañana", "Mañana", "Libre", "Libre"][:num_operadores],
    "Viernes": ["Tarde", "Tarde", "Libre", "Libre", "Mañana", "Mañana", "Noche", "Noche"][:num_operadores],
    "Sábado": ["Noche", "Noche", "Libre", "Libre", "Tarde", "Tarde", "Mañana", "Mañana"][:num_operadores],
    "Domingo": ["Noche", "Libre", "Libre", "Libre", "Tarde", "Tarde", "Mañana", "Mañana"][:num_operadores],
}
df = pd.DataFrame(data)
st.dataframe(df, use_container_width=True)
