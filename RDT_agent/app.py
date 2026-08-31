import json
import os
import pandas as pd
import streamlit as st

# Configuración de la página
st.set_page_config(
    page_title="Centro de Control COES - Turnos",
    page_icon="⚡",
    layout="wide",
)

# Inyección de estilos CSS para mantener la paleta Slate & Sky y reducir botones
st.markdown(
    """
    <style>
        .main {
            background-color: #0f172a;
            color: #f8fafc;
            font-family: 'Segoe UI', system-ui, sans-serif;
        }
        .metric-card {
            background-color: #1e293b;
            border: 1px solid #334155;
            padding: 1rem;
            border-radius: 0.5rem;
        }
        h1, h2, h3 {
            color: #f1f5f9 !important;
        }
        /* Estilo compacto para botones de reordenamiento */
        .stButton button {
            padding: 0px 8px !important;
            font-size: 12px !important;
            min-height: 24px !important;
            background-color: #1e293b;
            border: 1px solid #334155;
            color: #0ea5e9;
        }
        .stButton button:hover {
            background-color: #334155;
            color: #f8fafc;
        }
    </style>
""",
    unsafe_allow_html=True,
)

# Archivo JSON para persistencia
JSON_FILE = "turnos_personal.json"


# Función para cargar datos (inicializa por defecto si no existe)
def cargar_datos():
  if os.path.exists(JSON_FILE):
    with open(JSON_FILE, "r", encoding="utf-8") as f:
      return pd.DataFrame(json.load(f))
  else:
    # Datos iniciales por defecto
    data = {
        "Orden": [1, 2, 3, 4],
        "Hora": ["07:00 - 08:00", "08:00 - 09:00", "09:00 - 10:00", "10:00 - 11:00"],
        "Especialista Responsable": [
            "Carlos Mendoza",
            "Ana Torres",
            "Luis Gómez",
            "Sofía Ramírez",
        ],
        "Área / Subestación": [
            "SCADA / Principal",
            "Despacho de Carga",
            "Telecomunicaciones",
            "SCADA / Respaldo",
        ],
        "Estado": ["Completado", "En Curso", "Programado", "Programado"],
    }
    return pd.DataFrame(data)


# Inicializar Estado de Sesión para el DataFrame
if "df_turnos" not in st.session_state:
  st.session_state.df_turnos = cargar_datos()

# Interfaz Principal
st.title("⚡ Centro de Control - Gestión y Edición de Turnos")
st.markdown(
    "Modifica directamente las celdas, reordena al personal y guarda los cambios"
    " en el sistema."
)

# Sección de controles de ordenamiento discretos por fila
st.markdown("### 📋 Tabla de Asignaciones y Turnos")
st.info(
    "💡 Haz doble clic sobre cualquier celda de la tabla inferior para editarla"
    " directamente."
)

# Usamos st.data_editor para permitir la edición interactiva
df_editado = st.data_editor(
    st.session_state.df_turnos,
    num_rows="dynamic",  # Permite agregar o eliminar filas
    use_container_width=True,
    key="editor_turnos",
)

# Actualizar el estado con lo editado en la tabla
st.session_state.df_turnos = df_editado

# Botones de acción inferior (Guardar y Reordenar compacto)
col_save, col_spacer = st.columns([2, 6])

with col_save:
  if st.button("💾 Guardar Cambios en JSON", use_container_width=True):
    # Guardar a archivo JSON
    registro_dict = st.session_state.df_turnos.to_dict(orient="records")
    with open(JSON_FILE, "w", encoding="utf-8") as f:
      json.dump(registro_dict, f, ensure_ascii=False, indent=4)
    st.success("¡Cambios guardados exitosamente en el archivo JSON!")

st.markdown("---")
st.markdown("### ↕️ Control Rápido de Posición del Personal")

# Sistema de botones discretos y armónicos para subir/bajar filas de forma visual
for index, row in st.session_state.df_turnos.iterrows():
  col_info, col_up, col_down = st.columns([8, 1, 1])

  with col_info:
    st.text(
        f"Pos. {row.get('Orden', index+1)} | {row['Especialista Responsable']}"
        f" — {row['Área / Subestación']}"
    )

  with col_up:
    if index > 0:
      if st.button("▲", key=f"up_{index}"):
        # Intercambiar con la fila anterior
        st.session_state.df_turnos.iloc[index], st.session_state.df_turnos.iloc[
            index - 1
        ] = (
            st.session_state.df_turnos.iloc[index - 1].copy(),
            st.session_state.df_turnos.iloc[index].copy(),
        )
        st.rerun()

  with col_down:
    if index < len(st.session_state.df_turnos) - 1:
      if st.button("▼", key=f"down_{index}"):
        # Intercambiar con la fila siguiente
        st.session_state.df_turnos.iloc[index], st.session_state.df_turnos.iloc[
            index + 1
        ] = (
            st.session_state.df_turnos.iloc[index + 1].copy(),
            st.session_state.df_turnos.iloc[index].copy(),
        )
        st.rerun()
