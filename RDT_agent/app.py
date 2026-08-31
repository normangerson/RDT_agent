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
    " operativos 24/7 con matriz de multi-roles."
)

# Inicializar cliente de Gemini si hay API Key o Secrets
client = None
try:
  api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
  if api_key:
    client = genai.Client(api_key=api_key)
except Exception:
  pass

# --- GESTIÓN DE OPERADORES Y MULTI-ROLES EN SESSION STATE ---
if "operadores" not in st.session_state:
  st.session_state.operadores = [
      {
          "Nombre": "Carlos Pérez",
          "Roles Habilitados": ["C", "ET", "EF", "A"],
      },
      {"Nombre": "Ana Gómez", "Roles Habilitados": ["ET", "EF", "A"]},
      {"Nombre": "Luis Torres", "Roles Habilitados": ["EF", "A"]},
      {"Nombre": "María Ruiz", "Roles Habilitados": ["A"]},
      {"Nombre": "Jorge Díaz", "Roles Habilitados": ["C", "ET"]},
      {"Nombre": "Sofía Castro", "Roles Habilitados": ["EF", "ET", "A"]},
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
  st.subheader("👥 Gestión de Operadores y Roles")
  with st.form("form_nuevo_operador", clear_on_submit=True):
    nuevo_nombre = st.text_input("Nombre del Operador")
    st.markdown("Roles que puede cumplir:")
    rol_c = st.checkbox("Coordinador (C)")
    rol_et = st.checkbox("Espec. Tensión (ET)")
    rol_ef = st.checkbox("Espec. Frecuencia (EF)")
    rol_a = st.checkbox("Analista (A)", value=True)
    submit_op = st.form_submit_button("Agregar Operador")

    if submit_op and nuevo_nombre:
      roles_seleccionados = []
      if rol_c:
        roles_seleccionados.append("C")
      if rol_et:
        roles_seleccionados.append("ET")
      if rol_ef:
        roles_seleccionados.append("EF")
      if rol_a:
        roles_seleccionados.append("A")

      st.session_state.operadores.append(
          {
              "Nombre": nuevo_nombre,
              "Roles Habilitados": (
                  roles_seleccionados if roles_seleccionados else ["A"]
              ),
          }
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
  st.subheader("Matriz de Personal y Roles Habilitados en el Centro de Control")
  st.markdown(
      "**Leyenda de Roles:** **C** = Coordinador | **ET** = Especialista Tensión"
      " | **EF** = Especialista Frecuencia | **A** = Analista"
  )

  # Preparar dataframe formateando la lista de roles a texto legible
  df_display = []
  for op in st.session_state.operadores:
    df_display.append({
        "Nombre": op["Nombre"],
        "Roles Habilitados": ", ".join(op["Roles Habilitados"]),
    })
  df_ops = pd.DataFrame(df_display)
  st.dataframe(df_ops, use_container_width=True)

  # Opción para eliminar operador
  op_a_eliminar = st.selectbox(
      "Seleccionar operador para eliminar",
      [op["Nombre"] for op in st.session_state.operadores],
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
                "¡Hola! Soy tu agente experto en gestión de turnos."
                " Ya tengo registrada la matriz de multi-roles de los"
                " operadores (C, ET, EF, A) y las restricciones."
                " ¿Qué deseas planificar hoy?"
            ),
        }
    ]

  for message in st.session_state.messages:
    with st.chat_message(message["role"]):
      st.markdown(message["content"])

  # Entrada del usuario
  if prompt := st.chat_input("Escribe tu solicitud para el agente de turnos..."):
    if not client:
      st.error("Por favor, ingresa tu API Key de Gemini en la barra lateral.")
    else:
      st.session_state.messages.append({"role": "user", "content": prompt})
      with st.chat_message("user"):
        st.markdown(prompt)

      with st.chat_message("assistant"):
        with st.spinner("El agente está analizando la matriz de roles y turnos..."):
          try:
            # Lista estructurada de operadores y sus competencias para el prompt
            lista_nombres_ops = "\n".join([
                f"- {op['Nombre']}: Habilitado para los roles"
                f" {op['Roles Habilitados']}"
                for op in st.session_state.operadores
            ])

            # Instrucción de sistema avanzada con multi-roles integrados
            system_instruction = f"""
                        Eres un agente experto en gestión de recursos humanos y optimización de turnos para un Centro de Control 24/7.
                        
                        MATRIZ DE OPERADORES Y ROLES HABILITADOS:
                        {lista_nombres_ops}
                        
                        DEFINICIÓN DE PUESTOS EN EL CENTRO DE CONTROL:
                        - C: Coordinador
                        - ET: Especialista Tensión
                        - EF: Especialista Frecuencia
                        - A: Analista
                        
                        REGLAS Y RESTRICCIONES OBLIGATORIAS:
                        1. Esquema de rotación: {dias_ciclo}.
                        2. Descanso mínimo obligatorio entre turnos: {min_descanso} horas.
                        3. Límite máximo de turnos nocturnos consecutivos: {max_nocturnos}.
                        4. Novedades activas, bajas o vacaciones: {novedades_input if novedades_input else "Ninguna"}.
                        
                        INSTRUCCIONES CLAVE:
                        - Al asignar puestos en los turnos, DEBES RESPETAR ESTRICTAMENTE la matriz de roles habilitados de cada operador (por ejemplo, nunca asignes un rol para el que un operador no esté habilitado).
                        - Distribuye las cargas de manera justa y equitativa.
                        - Presenta las propuestas siempre en una tabla clara en formato Markdown indicando el puesto asignado (C, ET, EF, A) por cada día u hora.
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
st.subheader("📊 Vista Previa de Asignación por Competencias")
nombres_actuales = [op["Nombre"] for op in st.session_state.operadores]
data = {
    "Operador": nombres_actuales,
    "Lunes": ["C (Coordinador)", "ET (Esp. Tensión)", "EF (Esp. Frecuencia)", "A (Analista)", "Libre", "Libre"][:num_operadores],
    "Martes": ["C (Coordinador)", "ET (Esp. Tensión)", "EF (Esp. Frecuencia)", "A (Analista)", "Libre", "Libre"][:num_operadores],
    "Miércoles": ["Libre", "C (Coordinador)", "ET (Esp. Tensión)", "EF (Esp. Frecuencia)", "Libre", "Libre"][:num_operadores],
    "Jueves": ["Libre", "Libre", "C (Coordinador)", "ET (Esp. Tensión)", "A (Analista)", "A (Analista)"][:num_operadores],
    "Viernes": ["EF (Esp. Frecuencia)", "EF (Esp. Frecuencia)", "Libre", "Libre", "C (Coordinador)", "ET (Esp. Tensión)"][:num_operadores],
    "Sábado": ["Noche (ET)", "Noche (EF)", "Libre", "Libre", "Tarde (A)", "Tarde (A)"][:num_operadores],
    "Domingo": ["Libre", "Libre", "Noche (ET)", "Noche (EF)", "Tarde (A)", "Tarde (A)"][:num_operadores],
}
df = pd.DataFrame(data)
st.dataframe(df, use_container_width=True)
