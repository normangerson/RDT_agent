import json
import os
import pandas as pd
import streamlit as st

# 1. Configuración inicial de la página
st.set_page_config(
    page_title="Centro de Control COES - Turnos",
    page_icon="⚡",
    layout="wide",
)

# 2. Inyección de estilos CSS personalizados (Paleta Slate & Sky y botones compactos)
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
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }
        h1, h2, h3 {
            color: #f1f5f9 !important;
        }
        /* Estilo compacto y armónico para los botones de reordenamiento */
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

# 3. Archivo JSON para persistencia de datos
JSON_FILE = "turnos_personal.json"


# Función para cargar datos desde el JSON o inicializar valores por defecto
def cargar_datos():
  if os.path.exists(JSON_FILE):
    try:
      with open(JSON_FILE, "r", encoding="utf-8") as f:
        return pd.DataFrame(json.load(f))
    except Exception:
      pass

  # Datos iniciales por defecto si no existe el archivo
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


# Inicializar el estado de sesión de Streamlit
if "df_turnos" not in st.session_state:
  st.session_state.df_turnos = cargar_datos()

# 4. Barra Lateral (Sidebar) de Control
st.sidebar.header("Panel Operativo")
turno_activo = st.sidebar.selectbox(
    "Turno en Curso", ["Mañana (07:00 - 15:00)", "Tarde (15:00 - 23:00)", "Noche (23:00 - 07:00)"]
)
fecha_actual = st.sidebar.date_input("Fecha de Operación")

st.sidebar.markdown("---")
st.sidebar.info("Sistema de Control COES conectado al directorio local.")

# 5. Cuerpo Principal de la Aplicación
st.title("⚡ Centro de Control - Gestión de Turnos y Personal")
st.markdown(
    "Administra, edita y reordena el régimen operativo de manera interactiva."
)

# Métricas rápidas superiores estilo tarjeta
col1, col2, col3, col4 = st.columns(4)

with col1:
  st.markdown(
      '<div class="metric-card"><h4>Personal Registrado</h4><h2>'
      f"{len(st.session_state.df_turnos)}</h2></div>",
      unsafe_allow_html=True,
  )
with col2:
  st.markdown(
      '<div class="metric-card"><h4>Turno Asignado</h4><p'
      ' style="color: #0ea5e9; font-weight: bold; font-size:'
      ' 1.1rem;">Activo</p></div>',
      unsafe_allow_html=True,
  )
with col3:
  st.markdown(
      '<div class="metric-card"><h4>Incidencias</h4><p style="color: #eab308;'
      ' font-weight: bold; font-size: 1.1rem;">0 Alertas</p></div>',
      unsafe_allow_html=True,
  )
with col4:
  st.markdown(
      '<div class="metric-card"><h4>Estado Red</h4><p style="color: #22c55e;'
      ' font-weight: bold; font-size: 1.1rem;">Operativo</p></div>',
      unsafe_allow_html=True,
  )

st.markdown("---")
st.markdown("### 📋 Tabla de Régimen de Turnos")
st.info(
    "💡 Haz doble clic en cualquier celda para editar los datos o utiliza el"
    " botón inferior de la tabla para agregar filas."
)

# 6. Tabla Editable con st.data_editor
df_editado = st.data_editor(
    st.session_state.df_turnos,
    num_rows="dynamic",
    use_container_width=True,
    key="editor_turnos_main",
)

# Guardar los cambios directamente en el session_state al editar
st.session_state.df_turnos = df_editado

# Botón para persistir los cambios en el archivo JSON
col_btn_save, col_spacer = st.columns([2, 5])
with col_btn_save:
  if st.button("💾 Guardar Cambios en JSON", use_container_width=True):
    try:
      registro_dict = st.session_state.df_turnos.to_dict(orient="records")
      with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(registro_dict, f, ensure_ascii=False, indent=4)
      st.success("¡Datos guardados correctamente en el archivo JSON!")
    except Exception as e:
      st.error(f"Error al guardar el archivo: {e}")

st.markdown("---")
st.markdown("### ↕️ Control Armónico de Orden del Personal")
st.markdown(
    "<small>Usa los botones discretos para subir o bajar la prioridad de los"
    " especialistas en tiempo real.</small>",
    unsafe_allow_html=True,
)

# 7. Controles de ordenamiento fila por fila (botones compactos y armonizados)
for index, row in st.session_state.df_turnos.iterrows():
  col_info, col_up, col_down = st.columns([8, 1, 1])

  with col_info:
    nombre_resp = row.get("Especialista Responsable", "Sin asignar")
    area_resp = row.get("Área / Subestación", "General")
    st.text(f"[{index+1}] {nombre_resp} — {area_resp}")

  with col_up:
    if index > 0:
      if st.button("▲", key=f"subir_{index}"):
        # Intercambiar fila actual con la anterior
        st.session_state.df_turnos.iloc[index], st.session_state.df_turnos.iloc[
            index - 1
        ] = (
            st.session_state.df_turnos.iloc[index - 1].copy(),
            st.session_state.df_turnos.iloc[index].copy(),
        )
        st.rerun()

  with col_down:
    if index < len(st.session_state.df_turnos) - 1:
      if st.button("▼", key=f"bajar_{index}"):
        # Intercambiar fila actual con la siguiente
        st.session_state.df_turnos.iloc[index], st.session_state.df_turnos.iloc[
            index + 1
        ] = (
            st.session_state.df_turnos.iloc[index + 1].copy(),
            st.session_state.df_turnos.iloc[index].copy(),
        )
        st.rerun()
