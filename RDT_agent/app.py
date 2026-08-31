import json
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
    " operativos 24/7 con matriz de multi-roles, ordenamiento y régimen de 5"
    " semanas."
)

# Archivo local para guardar los operadores de forma permanente
DB_FILE = "operadores.json"


def cargar_operadores():
  if os.path.exists(DB_FILE):
    try:
      with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception:
      pass
  # Valores por defecto con semana de ciclo inicial (1 a 5)
  return [
      {
          "Nombre": "Carlos Pérez",
          "Roles Habilitados": ["C", "ET", "EF", "A"],
          "Semana Ciclo": 1,
      },
      {
          "Nombre": "Ana Gómez",
          "Roles Habilitados": ["ET", "EF", "A"],
          "Semana Ciclo": 2,
      },
      {
          "Nombre": "Luis Torres",
          "Roles Habilitados": ["EF", "A"],
          "Semana Ciclo": 3,
      },
      {
          "Nombre": "María Ruiz",
          "Roles Habilitados": ["A"],
          "Semana Ciclo": 4,
      },
      {
          "Nombre": "Jorge Díaz",
          "Roles Habilitados": ["C", "ET"],
          "Semana Ciclo": 5,
      },
      {
          "Nombre": "Sofía Castro",
          "Roles Habilitados": ["EF", "ET", "A"],
          "Semana Ciclo": 1,
      },
  ]


def guardar_operadores(ops):
  with open(DB_FILE, "w", encoding="utf-8") as f:
    json.dump(ops, f, ensure_ascii=False, indent=4)


# Inicializar cliente de Gemini si hay API Key o Secrets
client = None
try:
  api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
  if api_key:
    client = genai.Client(api_key=api_key)
except Exception:
  pass

# --- GESTIÓN DE OPERADORES CON PERSISTENCIA ---
if "operadores" not in st.session_state:
  st.session_state.operadores = cargar_operadores()

# Sidebar para configuración general y restricciones
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
  st.subheader("📋 Parámetros del Régimen 24/7")
  st.markdown("""
        **Esquema de las 5 Semanas del Ciclo:**
        - **Semana 1 (OI):** Oficina (L-V), T2 (Sáb), Descanso (Dom).
        - **Semana 2 (T2):** Tarde (L, M, Mi, V), T1 (Jue), T3 (Sáb, Dom).
        - **Semana 3 (T3):** Noche (L-J), Descanso (Vie), T2 (Sáb).
        - **Semana 4 (T1):** Madrugada (L-Mi), T2 (Jue), Madrugada (V-Dom).
        - **Semana 5 (D):** Descanso toda la semana (L-Dom).
        """)

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
  st.subheader("Matriz de Personal y Régimen de 5 Semanas")
  st.markdown(
      "**Leyenda de Roles:** **C** = Coordinador | **ET** = Especialista Tensión"
      " | **EF** = Especialista Frecuencia | **A** = Analista  \n**Leyenda de"
      " Turnos:** **OI** = Oficina | **T2** = 07:00-15:00 | **T3** ="
      " 15:00-23:00 | **T1** = 23:00-07:00 | **D** = Descanso"
  )

  # Dividir la pestaña en dos columnas: Izquierda la tabla con controles de orden, Derecha el formulario
  col_tabla, col_form = st.columns([2, 1])

  with col_tabla:
    st.markdown("### Personal Registrado y Orden de Prioridad")

    # Mostrar tabla interactiva con botones para mover arriba/abajo
    for idx, op in enumerate(st.session_state.operadores):
      c_info, c_up, c_down, c_del = st.columns([4, 1, 1, 1])
      with c_info:
        roles_str = ", ".join(op["Roles Habilitados"])
        ciclo_val = op.get("Semana Ciclo", 1)
        st.markdown(
            f"**{idx+1}. {op['Nombre']}** — Roles: `[{roles_str}]` | Ciclo:"
            f" **Semana {ciclo_val}**"
        )
      with c_up:
        if idx > 0:
          if st.button("⬆️", key=f"up_{idx}"):
            (
                st.session_state.operadores[idx],
                st.session_state.operadores[idx - 1],
            ) = (
                st.session_state.operadores[idx - 1],
                st.session_state.operadores[idx],
            )
            guardar_operadores(st.session_state.operadores)
            st.rerun()
      with c_down:
        if idx < len(st.session_state.operadores) - 1:
          if st.button("⬇️", key=f"down_{idx}"):
            (
                st.session_state.operadores[idx],
                st.session_state.operadores[idx + 1],
            ) = (
                st.session_state.operadores[idx + 1],
                st.session_state.operadores[idx],
            )
            guardar_operadores(st.session_state.operadores)
            st.rerun()
      with c_del:
        if st.button("❌", key=f"del_{idx}"):
          st.session_state.operadores.pop(idx)
          guardar_operadores(st.session_state.operadores)
          st.rerun()

  with col_form:
    st.markdown("### ➕ Agregar Operador")
    with st.form("form_nuevo_operador_principal", clear_on_submit=True):
      nuevo_nombre = st.text_input("Nombre del Operador")
      semana_inicial = st.selectbox(
          "Semana Inicial del Ciclo (1 al 5)", [1, 2, 3, 4, 5]
      )

      st.markdown("Roles que puede cumplir:")
      rol_c = st.checkbox("Coordinador (C)")
      rol_et = st.checkbox("Espec. Tensión (ET)")
      rol_ef = st.checkbox("Espec. Frecuencia (EF)")
      rol_a = st.checkbox("Analista (A)", value=True)
      submit_op = st.form_submit_button("Guardar Nuevo Operador")

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

        nuevo_registro = {
            "Nombre": nuevo_nombre,
            "Roles Habilitados": (
                roles_seleccionados if roles_seleccionados else ["A"]
            ),
            "Semana Ciclo": semana_inicial,
        }
        st.session_state.operadores.append(nuevo_registro)
        guardar_operadores(st.session_state.operadores)
        st.success(f"¡{nuevo_nombre} agregado con éxito!")
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
                "¡Hola! Soy tu agente experto en gestión de turnos. Ya tengo"
                " configurada la matriz de multi-roles, el orden de operadores y"
                " el régimen natural de 5 semanas (OI, T2, T3, T1, D)."
                " ¿Qué deseas planificar o consultar hoy?"
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
        with st.spinner("El agente está analizando el régimen de 5 semanas y turnos..."):
          try:
            # Lista estructurada de operadores con su semana de ciclo y competencias
            lista_nombres_ops = "\n_{idx+1}._ ".join([
                f"- {op['Nombre']}: Semana de ciclo {op.get('Semana Ciclo', 1)},"
                f" Roles habilitados: {op['Roles Habilitados']}"
                for op in st.session_state.operadores
            ])

            # Instrucción de sistema avanzada con el régimen de 5 semanas
            system_instruction = f"""
                        Eres un agente experto en gestión de recursos humanos y optimización de turnos para un Centro de Control 24/7.
                        
                        PLANTILLA DE OPERADORES Y SU POSICIÓN EN EL CICLO DE 5 SEMANAS:
                        {lista_nombres_ops}
                        
                        DEFINICIÓN DEL RÉGIMEN NATURAL DE 5 SEMANAS (Lunes a Domingo):
                        - Semana 1 (OI - Oficina): L-V OI (Oficina / soporte), Sáb T2 (07-15h), Dom Descanso (D).
                        - Semana 2 (T2 - Turno 2): L-Mi T2 (07-15h), Jue T1 (23-07h), V T2 (07-15h), Sáb-Dom T3 (15-23h).
                        - Semana 3 (T3 - Turno 3): L-J T3 (15-23h), Vie Descanso (D), Sáb T2 (07-15h), Dom Descanso (D).
                        - Semana 4 (T1 - Turno 1): L-Mi T1 (23-07h), Jue T2 (07-15h), V-Dom T1 (23-07h).
                        - Semana 5 (D - Descanso): Descanso total toda la semana (L a D).
                        
                        DEFINICIÓN DE ROLES EN EL CENTRO DE CONTROL:
                        - C: Coordinador
                        - ET: Especialista Tensión
                        - EF: Especialista Frecuencia
                        - A: Analista
                        
                        REGLAS OBLIGATORIAS:
                        1. Respeta el orden de prioridad de los operadores tal como están listados.
                        2. Asigna los turnos diarios (OI, T2, T3, T1, D) según la semana de ciclo en la que se encuentre cada operador.
                        3. Novedades activas a considerar: {novedades_input if novedades_input else "Ninguna"}.
                        4. Presenta siempre las respuestas y propuestas en tablas Markdown claras de Lunes a Domingo.
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

# Sección de visualización de ejemplo de la tabla de 5 semanas del ciclo
st.markdown("---")
st.subheader("📊 Vista Previa del Régimen de Turnos (Semana a Semana)")
nombres_actuales = [op["Nombre"] for op in st.session_state.operadores]
data = {
    "Operador": nombres_actuales,
    "Ciclo Actual": [f"Semana {op.get('Semana Ciclo', 1)}" for op in st.session_state.operadores],
    "Lunes": ["OI", "T2", "T3", "T1", "D", "OI"][:num_operadores],
    "Martes": ["OI", "T2", "T3", "T1", "D", "OI"][:num_operadores],
    "Miércoles": ["OI", "T2", "T3", "T1", "D", "OI"][:num_operadores],
    "Jueves": ["OI", "T1", "T3", "T2", "D", "OI"][:num_operadores],
    "Viernes": ["OI", "T2", "D", "T1", "D", "OI"][:num_operadores],
    "Sábado": ["T2", "T3", "T2", "T1", "D", "T2"][:num_operadores],
    "Domingo": ["D", "T3", "D", "T1", "D", "D"][:num_operadores],
}
df = pd.DataFrame(data)
st.dataframe(df, use_container_width=True)
