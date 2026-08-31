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
    "Sistema autónomo para la planificación, optimización y gestión de turnos"
    " operativos 24/7."
)

# Inicializar cliente de Gemini si hay API Key o Secrets
client = None
try:
  api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
  if api_key:
    client = genai.Client(api_key=api_key)
except Exception:
  pass

# --- GESTIÓN DE OPERADORES EN SESSION STATE ---
if "operadores" not in st.session_state:
  st.session_state.operadores = [
      {"Nombre": "Carlos Pérez", "Rol": "Operador Senior", "Turno Preferido": "Mañana"},
      {"Nombre": "Ana Gómez", "Rol": "Operador Senior", "Turno Preferido": "Tarde"},
      {"Nombre": "Luis Torres", "Rol": "Operador Junior", "Turno Preferido": "Noche"},
      {"Nombre": "María Ruiz", "Rol": "Operador Junior", "Turno Preferido": "Rotativo"},
      {"Nombre": "Jorge Díaz", "Rol": "Operador Senior", "Turno Preferido": "Mañana"},
      {"Nombre": "Sofía Castro", "Rol": "Operador Junior", "Turno Preferido": "Tarde"},
  ]

# Sidebar para configuración de credenciales, parámetros y restricciones
with st.sidebar:
  st.header("⚙️ Configuración")
  if not client:
    api_key_input = st.text_input(
        "Gemini API Key",
        type="password",
        help="Ingresa tu clave de API de Google Gemini",
    )
    if api_key_input:
      client = genai.Client(api_key=api_key_input)

  st.markdown("---")
  st.subheader("📋 Parámetros del Rol")
  dias_ciclo = st.selectbox(
      "Esquema de Rotación", ["Lunes a Viernes (5x2)", "Turnos 24/7 (4x4)"]
  )
  turno_seleccionado = st.selectbox(
      "Modo de Operación",
      ["Generar Nuevo Rol", "Simular Imprevisto / Baja", "Consultar Reglas"],
  )

  st.markdown("---")
  st.subheader("👥 Gestión de Operadores")
  with st.form("form_nuevo_operador", clear_on_submit=True):
    nuevo_nombre = st.text_input("Nombre del Operador")
    nuevo_rol = st.selectbox("Nivel / Rol", ["Operador Senior", "Operador Junior", "Supervisor"])
    submit_op = st.form_submit_button("Agregar Operador")

    if submit_op and nuevo_nombre:
      st.session_state.operadores.append(
          {"Nombre": nuevo_nombre, "Rol": nuevo_rol, "Turno Preferido": "Rotativo"}
      )
      st.success(f"¡{nuevo_nombre} agregado con éxito!")
      st.rerun()

  st.markdown("---")
  st.subheader("🛡️ Restricciones y Políticas")
  min_descanso = st.slider("Descanso mínimo entre turnos (horas)", 8, 16, 12)
  max_nocturnos = st.number_input("Máximo turnos nocturnos consecutivos", 1, 5, 3)

  st.markdown("---")
  st.subheader("⚠️ Novedades Activas")
  novedades_input = st.text_area(
      "Registrar bajas, permisos o vacaciones",
      placeholder="Ej: Carlos Pérez de vacaciones del 10 al 15",
  )

# Número de operadores dinámico basado en la lista real
num_operadores = len(st.session_state.operadores)

# --- LAYOUT PRINCIPAL EN PESTAÑAS ---
tab_chat, tab_equipo = st.tabs(["💬 Agente de Turnos", "📋 Plantilla de Operadores"])

with tab_equipo:
  st.subheader("Personal Registrado en el Centro de Control")
  df_ops = pd.DataFrame(st.session_state.operadores)
  st.dataframe(df_ops, use_container_width=True)

  # Opción para eliminar operador
  op_a_eliminar = st.selectbox(
      "Seleccionar operador para eliminar", [op["Nombre"] for op in st.session_state.operadores]
  )
  if st.button("Eliminar Operador Seleccionado"):
    st.session_state.operadores = [
        op for op in st.session_state.operadores if op["Nombre"] != op_a_eliminar
    ]
    st.success(f"Operador {op_a_eliminar} eliminado.")
    st.rerun()

with tab_chat:
  # Área principal del chat / agente
  st.markdown("### 💬 Interacción con el Agente")

  # Historial de mensajes en la sesión
  if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "¡Hola! Soy tu agente experto en gestión de turnos para el centro de control."
                " Ya tengo cargada la plantilla de operadores y restricciones."
                " ¿Qué deseas hacer hoy? (Ej: *'Generar el rol para la próxima"
                " semana'* o *'Juan reportó descanso médico, ¿quién lo cubre?'*)"
            ),
        }
    ]

  for message in st.session_state.messages:
    with st.chat_message(message["role"]):
      st.markdown(message["content"])

  # Entrada del usuario
  if prompt := st.chat_input("Escribe tu solicitud para el agente de turnos..."):
    if not client:
      st.error("Por favor, ingresa tu API Key de Gemini en la barra lateral o en los Secrets.")
    else:
      st.session_state.messages.append({"role": "user", "content": prompt})
      with st.chat_message("user"):
        st.markdown(prompt)

      with st.chat_message("assistant"):
        with st.spinner("El agente está analizando las restricciones y turnos..."):
          try:
            # Lista estructurada de operadores para el prompt
            lista_nombres_ops = ", ".join(
                [f"{op['Nombre']} ({op['Rol']})" for op in st.session_state.operadores]
            )

            # Instrucción de sistema avanzada con operadores y restricciones integradas
            system_instruction = f"""
                        Eres un agente experto en gestión de recursos humanos y optimización de turnos para un Centro de Control 24/7.
                        
                        PLANTILLA DE OPERADORES ACTIVOS ({num_operadores} en total):
                        {lista_nombres_ops}
                        
                        REGLAS Y RESTRICCIONES OBLIGATORIAS:
                        1. Esquema de rotación: {dias_ciclo}.
                        2. Descanso mínimo obligatorio entre turnos: {min_descanso} horas.
                        3. Límite máximo de turnos nocturnos consecutivos: {max_nocturnos}.
                        4. Novedades activas, bajas o vacaciones: {novedades_input if novedades_input else "Ninguna"}.
                        
                        Tu objetivo es coordinar turnos justos utilizando exclusivamente los nombres de los operadores listados, cumplir normativas de descanso, resolver imprevistos y proponer tablas claras en formato Markdown.
                        """

            # Llamada al modelo Gemini
            response = client.models.generate_content(
                model="gemini-3.6-flash",
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
# Generar una tabla simulada basada en los operadores reales registrados
nombres_actuales = [op["Nombre"] for op in st.session_state.operadores]
data = {
    "Operador": nombres_actuales,
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
