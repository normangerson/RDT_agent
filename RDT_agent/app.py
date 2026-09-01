import datetime
import os

import pandas as pd
import streamlit as st
from google import genai

import almacen
import motor_turnos as mt
import agente_turnos as ag

MODEL = "gemini-3.6-flash"

st.set_page_config(
    page_title="Rol de Turnos - Centro de Control",
    page_icon="🛡️",
    layout="wide",
)

# --- Estética portada de RDTLightning (paleta slate + sky) ---------------- #
st.markdown(
    """
    <style>
      :root{
        --ink:#0f172a; --text:#1e293b; --muted:#64748b; --muted2:#475569;
        --bg:#f8fafc; --line:#e2e8f0; --line2:#f1f5f9;
        --sky:#0ea5e9; --sky-dk:#0369a1; --sky-bg:#f0f9ff;
        --ok:#059669; --warn:#b45309; --err:#dc2626;
      }
      html, body, .stApp, [class*="css"], .stMarkdown,
      input, textarea, button, select, [data-baseweb]{
        font-family:"Segoe UI", system-ui, -apple-system, Roboto, sans-serif;
      }
      .stApp{ background:var(--bg); color:var(--text); }
      .stApp, .stMarkdown p, .stMarkdown li{ font-size:13px; line-height:1.55; }
      .block-container{ padding-top:2rem; padding-bottom:3rem; max-width:1440px; }

      /* Título principal compacto, tipo "header" del HTML */
      h1{ font-size:1.5rem !important; font-weight:800; color:var(--ink);
          letter-spacing:-.02em; }
      [data-testid="stHeaderActionElements"]{ display:none; }

      /* h2/h3 con barra sky a la izquierda y subrayado */
      h2, h3{ color:var(--ink); font-weight:800; letter-spacing:-.015em; }
      [data-testid="stMarkdownContainer"] h2,
      [data-testid="stMarkdownContainer"] h3{
        border-bottom:2px solid var(--line); padding-bottom:.4rem;
        margin:.6rem 0 .5rem; display:flex; align-items:center; gap:.6rem;
      }
      [data-testid="stMarkdownContainer"] h2::before,
      [data-testid="stMarkdownContainer"] h3::before{
        content:""; width:5px; height:1.05em; border-radius:3px;
        background:var(--sky); flex-shrink:0;
      }
      [data-testid="stMarkdownContainer"] h2{ font-size:1.05rem; }
      [data-testid="stMarkdownContainer"] h3, [data-testid="stMarkdownContainer"] h4{
        font-size:.82rem; text-transform:uppercase; letter-spacing:.06em;
        color:var(--muted); font-weight:800;
      }
      [data-testid="stMarkdownContainer"] h4{ border:0; padding:0; }

      /* Sidebar como panel blanco */
      [data-testid="stSidebar"]{ background:#fff; border-right:1px solid var(--line); }
      [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3{ font-size:.8rem; }

      /* Tarjetas con borde -> panel del HTML */
      [data-testid="stVerticalBlockBorderWrapper"]{
        background:#fff; border-radius:11px;
        box-shadow:0 2px 5px rgba(15,23,42,.05);
      }
      [data-testid="stExpander"]{ border-radius:11px; border:1px solid var(--line); }

      /* Labels tipo HTML: mayúsculas pequeñas */
      [data-testid="stWidgetLabel"] p{
        font-size:.7rem !important; font-weight:700; text-transform:uppercase;
        letter-spacing:.06em; color:var(--muted);
      }

      /* Botones */
      .stButton>button, .stDownloadButton>button, .stFormSubmitButton>button{
        border-radius:7px; font-weight:700; border:1px solid var(--line);
        transition:background .12s, border-color .12s;
      }
      .stButton>button:hover{ border-color:var(--sky); color:var(--sky-dk); }
      .stButton>button[kind="primary"], .stFormSubmitButton>button[kind="primary"]{
        background:var(--sky); border-color:var(--sky); color:#fff;
      }
      .stButton>button[kind="primary"]:hover,
      .stFormSubmitButton>button[kind="primary"]:hover{
        background:var(--sky-dk); border-color:var(--sky-dk); color:#fff;
      }

      /* Inputs */
      .stTextInput input, .stNumberInput input, .stDateInput input,
      .stTextArea textarea, div[data-baseweb="select"]>div{
        border-radius:7px !important; border-color:var(--line) !important;
      }
      .stTextInput input:focus, .stNumberInput input:focus,
      .stDateInput input:focus{ box-shadow:0 0 0 3px rgba(14,165,233,.12); }

      /* Tabs -> nav del HTML */
      .stTabs [data-baseweb="tab-list"]{ gap:2px; border-bottom:1px solid var(--line); }
      .stTabs [data-baseweb="tab"]{ font-weight:600; color:var(--muted2);
        padding:8px 12px; }
      .stTabs [data-baseweb="tab"]:hover{ color:var(--ink); }
      .stTabs [aria-selected="true"]{ color:var(--sky-dk) !important;
        font-weight:800; border-bottom:2px solid var(--sky); }

      /* Avisos: borde izquierdo de color, esquinas 0 8 8 0 (info/note del HTML) */
      [data-testid="stAlert"]{ border-radius:0 8px 8px 0 !important;
        border-left:4px solid var(--sky); }
      [data-testid="stAlert"][data-baseweb] { background:var(--sky-bg); }

      /* Métricas -> tarjetas KPI con filo sky */
      [data-testid="stMetric"]{
        background:#fff; border:1px solid var(--line); border-left:4px solid var(--sky);
        border-radius:9px; padding:10px 14px; box-shadow:0 2px 5px rgba(15,23,42,.05);
      }
      [data-testid="stMetricLabel"] p{ font-size:.66rem !important; font-weight:700;
        text-transform:uppercase; letter-spacing:.08em; color:var(--muted); }
      [data-testid="stMetricValue"]{ font-size:1.5rem; font-weight:800;
        color:var(--ink); letter-spacing:-.02em; }

      /* DataFrames */
      [data-testid="stDataFrame"], [data-testid="stTable"]{
        border:1px solid var(--line); border-radius:9px; }

      /* Chat */
      [data-testid="stChatMessage"]{ background:#fff; border:1px solid var(--line);
        border-radius:11px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🛡️ Rol de Turnos — Centro de Control")
st.caption(
    "Subdirección de Coordinación · el rol se construye con un **motor"
    " determinista** y el agente lo consulta, explica y ajusta."
)


# --- Coloreado de la grilla como en RDTLightning ------------------------- #
_CELL_BG = {
    "T1": ("#64748b", "#ffffff"), "T2": ("#e0f2fe", "#075985"),
    "T3": ("#fef3c7", "#92400e"), "OI": ("#f1f5f9", "#475569"),
    "D": ("#ffffff", "#cbd5e1"), "V": ("#f3e8ff", "#6b21a8"),
    "CP": ("#dcfce7", "#166534"), "PER": ("#ffedd5", "#9a3412"),
    "LM": ("#fee2e2", "#991b1b"),
}


def _cell_style(v):
  pc = mt.parse_code(str(v))
  if pc["tipo"] == "T":
    key = pc["turno"]
  elif pc["tipo"] in ("OI", "D"):
    key = pc["tipo"]
  else:
    key = str(v)
  bg, fg = _CELL_BG.get(key, ("#ffffff", "#1e293b"))
  return f"background-color:{bg};color:{fg};font-weight:700;text-align:center"

# --------------------------------------------------------------------------- #
#  Persistencia                                                                #
# --------------------------------------------------------------------------- #
_HERE = os.path.dirname(os.path.abspath(__file__))
DB_FILE = "operadores.json"
CFG_FILE = "config_rol.json"


def _secret(key, default=None):
  try:
    if key in st.secrets:
      return st.secrets[key]
  except Exception:
    pass
  return os.environ.get(key, default)


def _get_store():
  store = st.session_state.get("store")
  if store is None:
    store = almacen.make_store(
        _HERE,
        token=_secret("GITHUB_TOKEN"),
        repo=_secret("GITHUB_REPO", "normangerson/RDT_agent"),
        branch=_secret("GITHUB_DATA_BRANCH", "app-data"),
        prefix=_secret("GITHUB_DATA_PREFIX", ""),
    )
    st.session_state.store = store
  return store


STORE = _get_store()


def _merge(base, disk):
  for k, v in disk.items():
    if isinstance(v, dict) and isinstance(base.get(k), dict):
      base[k] = _merge(base[k], v)
    else:
      base[k] = v
  return base


def cargar_operadores():
  ops = STORE.load(DB_FILE)
  if not ops:
    return mt.operadores_ejemplo()
  for o in ops:  # completar campos nuevos en registros antiguos
    o.setdefault("Costo Turno", 50)
    o.setdefault("Fecha Base", "")
    o.setdefault("Activo", True)
  return ops


def guardar_operadores(ops):
  STORE.save(DB_FILE, ops)


def cargar_config():
  cfg = mt.config_default()
  disk = STORE.load(CFG_FILE)
  if disk:
    cfg = _merge(cfg, disk)
  return cfg


def guardar_config(cfg):
  STORE.save(CFG_FILE, cfg)


if "operadores" not in st.session_state:
  st.session_state.operadores = cargar_operadores()
if "config" not in st.session_state:
  st.session_state.config = cargar_config()

OPS = st.session_state.operadores
CFG = st.session_state.config

# --------------------------------------------------------------------------- #
#  Cliente Gemini                                                              #
# --------------------------------------------------------------------------- #
client = None
try:
  api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
  if api_key:
    client = genai.Client(api_key=api_key)
except Exception:
  pass

with st.sidebar:
  st.header("⚙️ Configuración")
  if not client:
    api_key_input = st.text_input("Gemini API Key", type="password",
                                  help="Clave de API de Google Gemini")
    if api_key_input:
      client = genai.Client(api_key=api_key_input)

  st.markdown("---")
  st.subheader("🗓️ Mes a planificar")
  ui = CFG.setdefault("ui", {})
  ui["mesOficial"] = st.text_input("Mes oficial (YYYY-MM)",
                                   ui.get("mesOficial", "2026-08"))
  ui["mesesRef"] = st.number_input("Meses de referencia", 0, 11,
                                   int(ui.get("mesesRef", 2)))

  st.markdown("---")
  st.subheader("⚠️ Novedades activas")
  novedades_input = st.text_area(
      "Bajas, permisos o vacaciones (texto libre para el agente)",
      placeholder="Ej: Carlos Pérez de vacaciones del 10 al 15",
  )

  guardar_config(CFG)

  st.markdown("---")
  st.subheader("💾 Almacenamiento")
  st.caption(STORE.describe())
  if STORE.kind == "local":
    st.caption("Efímero en Streamlit Cloud. Para guardado permanente define los "
               "secrets `GITHUB_TOKEN` y `GITHUB_REPO`.")
  if st.button("Guardar ahora"):
    guardar_operadores(OPS)
    guardar_config(CFG)
    st.success("Guardado." if not STORE.last_error else "")
  if STORE.last_error:
    st.error(f"Almacenamiento: {STORE.last_error}")

# --------------------------------------------------------------------------- #
#  Pestañas                                                                    #
# --------------------------------------------------------------------------- #
(tab_chat, tab_equipo, tab_regimen, tab_cobertura, tab_ausencias,
 tab_forzados, tab_feriados, tab_rol) = st.tabs([
     "💬 Agente",
     "📋 Operadores",
     "🗓️ Régimen",
     "🎯 Cobertura",
     "🏖️ Ausencias",
     "📌 Forzados / Prioridad",
     "🎉 Feriados",
     "📅 Rol generado",
 ])

# ===================== OPERADORES ========================================= #
with tab_equipo:
  st.subheader("Operadores del Centro de Control")
  st.markdown(
      "**Roles:** **C** Coordinador · **ET** Especialista Tensión · **EF**"
      " Especialista Frecuencia · **A** Analista.  ·  El **orden** de la lista"
      " es la jerarquía (el nº 1 manda al repartir roles)."
  )
  st.info(
      "**Anclaje del ciclo:** el motor calcula la rotación de cada operador a"
      " partir de dos datos — la **fecha base** (un lunes concreto) y la"
      " **semana del ciclo** en la que estaba ese lunes. Ej.: «el lunes"
      " 2026-07-27 este operador estaba en la semana 3». Si dejas la fecha"
      " vacía, se usa el lunes anterior al día 1 del mes oficial."
  )

  # --- Alta / edición: arriba y a todo lo ancho ---------------------------- #
  with st.container(border=True):
    nombres = ["➕ Nuevo operador"] + [o["Nombre"] for o in OPS]
    sel = st.selectbox("Editar operador existente o crear uno nuevo", nombres,
                       key="op_sel")
    editando = None if sel.startswith("➕") else next(
        o for o in OPS if o["Nombre"] == sel)

    _fb_prev = None
    if editando:
      _snap = mt._lunes_de_safe(editando.get("Fecha Base"))
      if _snap:
        _fb_prev = datetime.date.fromisoformat(_snap)

    with st.form("form_operador", clear_on_submit=(editando is None), border=False):
      r1 = st.columns([3.4, 1.2, 1])
      nombre = r1[0].text_input("Nombre", value=editando["Nombre"] if editando else "")
      costo = r1[1].number_input(
          "Costo/turno", 1, 100,
          int(editando.get("Costo Turno", 50)) if editando else 50)
      activo = r1[2].checkbox(
          "Activo", editando.get("Activo", True) if editando else True)

      hab = editando.get("Roles Habilitados", []) if editando else ["A"]
      st.caption("ROLES QUE PUEDE CUBRIR")
      rc = st.columns(4)
      rol_c = rc[0].checkbox("C — Coordinador", "C" in hab)
      rol_et = rc[1].checkbox("ET — Esp. Tensión", "ET" in hab)
      rol_ef = rc[2].checkbox("EF — Esp. Frecuencia", "EF" in hab)
      rol_a = rc[3].checkbox("A — Analista", ("A" in hab) or (editando is None))

      st.caption("ANCLAJE DEL CICLO")
      ra = st.columns([1, 1])
      semana = ra[0].selectbox(
          "Semana del ciclo en la fecha base", [1, 2, 3, 4, 5],
          index=(int(editando.get("Semana Ciclo", 1)) - 1) if editando else 0,
          format_func=lambda s: f"S{s} · {mt.SEM_NOMBRE[s]}")
      fecha_base = ra[1].date_input(
          "Fecha base (se ajusta al lunes)", value=_fb_prev,
          format="YYYY-MM-DD",
          help="Cualquier día vale: se usa el lunes de esa semana. "
               "Vacío = lunes anterior al día 1 del mes oficial.")

      if fecha_base:
        _lb = mt._lunes_de(fecha_base.isoformat())
        _av = "" if fecha_base.isoformat() == _lb else \
            f"  ·  {fecha_base.isoformat()} no es lunes → se usa {_lb}"
        st.caption(f"⚓ Ancla: lunes **{_lb}** = semana **{semana}** del ciclo{_av}")
      else:
        st.caption("⚓ Sin fecha base: ancla en el lunes anterior al día 1 del "
                   "mes oficial, con la semana del ciclo indicada.")

      ok = st.form_submit_button(
          "Guardar operador" if editando else "Crear operador", type="primary")

    if ok and nombre:
      roles = [r for r, v in
               (("C", rol_c), ("ET", rol_et), ("EF", rol_ef), ("A", rol_a)) if v]
      fb = mt._lunes_de(fecha_base.isoformat()) if fecha_base else ""
      rec = {
          "Nombre": nombre,
          "Roles Habilitados": roles or ["A"],
          "Semana Ciclo": int(semana),
          "Costo Turno": int(costo),
          "Fecha Base": fb,
          "Activo": activo,
      }
      if editando and "Puesto" in editando:
        del editando["Puesto"]
      if editando:
        editando.update(rec)
      else:
        OPS.append(rec)
      guardar_operadores(OPS)
      st.success(f"{nombre} guardado."
                 + (f" Ancla: {fb} (semana {semana})." if fb else ""))
      st.rerun()

  # --- Lista ------------------------------------------------------------- #
  st.markdown("#### Personal registrado")
  _W = [0.5, 4, 2.4, 1.1, 1, 0.6, 0.6, 0.6]
  h = st.columns(_W)
  for col, txt in zip(h, ["#", "Nombre", "Roles", "Ciclo", "Costo", "", "", ""]):
    col.caption(txt)
  for idx, op in enumerate(OPS):
    c = st.columns(_W)
    inact = "" if op.get("Activo", True) else " 💤"
    c[0].markdown(f"**{idx+1}**")
    c[1].markdown(f"**{op['Nombre']}**{inact}")
    c[2].markdown("`" + " ".join(op.get("Roles Habilitados", [])) + "`")
    c[3].markdown(f"S{op.get('Semana Ciclo', 1)}")
    c[4].markdown(str(op.get("Costo Turno", 50)))
    if idx > 0 and c[5].button("▲", key=f"up_{idx}"):
      OPS[idx - 1], OPS[idx] = OPS[idx], OPS[idx - 1]
      guardar_operadores(OPS)
      st.rerun()
    if idx < len(OPS) - 1 and c[6].button("▼", key=f"down_{idx}"):
      OPS[idx + 1], OPS[idx] = OPS[idx], OPS[idx + 1]
      guardar_operadores(OPS)
      st.rerun()
    if c[7].button("✕", key=f"del_{idx}"):
      OPS.pop(idx)
      guardar_operadores(OPS)
      st.rerun()

  # --- Verificación del anclaje del ciclo ------------------------------- #
  with st.expander("🔎 Verificar anclaje del ciclo", expanded=False):
    anc = mt.anclaje(OPS, CFG)
    st.caption(
        f"Primer lunes del mes oficial ({CFG['ui'].get('mesOficial')}): "
        f"**{anc['primer_lunes_mes_oficial']}**. Revisa que «Sem. en 1er lunes» "
        "sea la semana del ciclo que esperas para cada operador esa fecha."
    )
    dfa = pd.DataFrame([{
        "Operador": r["operador"],
        "Fecha base": r["fecha_base_ingresada"],
        "¿Era lunes?": "—" if r["era_lunes"] is None
        else ("sí" if r["era_lunes"] else "NO ⚠"),
        "Lunes efectivo": r["lunes_base"],
        "Sem. base": r["semana_base"],
        "Sem. en 1er lunes": r["semana_en_1er_lunes"],
        "Turno ese lunes": r["turno_1er_lunes"],
        "Activo": "sí" if r["activo"] else "no",
    } for r in anc["operadores"]])
    st.dataframe(dfa, use_container_width=True, hide_index=True)

  CFG["prioridad"] = [o["Nombre"] for o in OPS]
  guardar_config(CFG)

# ===================== RÉGIMEN =========================================== #
with tab_regimen:
  st.subheader("🗓️ Régimen natural de 5 semanas (Lun a Dom)")
  st.markdown(
      "Patrón estándar de rotación. El motor lo rota para cada operador según su"
      " fecha base y su semana del ciclo. Códigos: **OI** oficina · **T2**"
      " 07-15 · **T3** 15-23 · **T1** 23-07 · **D** descanso."
  )
  st.caption(
      "Reglas de secuencia (fijas): 1 turno por día y descanso mínimo entre"
      " turnos → no se encadena T1→T2, T1→T3 ni T3→T2 al día siguiente."
  )
  patron = CFG["regimen"]["patron"]
  dias = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
  df = pd.DataFrame(
      [patron[i * 7:i * 7 + 7] for i in range(5)],
      columns=dias,
      index=[f"S{i+1} · {mt.SEM_NOMBRE[i+1]}" for i in range(5)],
  )
  edited = st.data_editor(
      df, use_container_width=True,
      column_config={d: st.column_config.SelectboxColumn(
          d, options=["OI", "T1", "T2", "T3", "D"], required=True) for d in dias},
  )
  nuevo = [str(edited.iloc[i, j]) for i in range(5) for j in range(7)]
  if nuevo != patron:
    CFG["regimen"]["patron"] = nuevo
    guardar_config(CFG)
    st.success("Régimen actualizado.")

# ===================== COBERTURA ======================================== #
with tab_cobertura:
  st.subheader("🎯 Cobertura mínima por turno y tipo de día")
  st.markdown(
      "**1** = se exige al menos 1 (incumplimiento si falta). **0** = no"
      " obligatorio, pero el motor igual intenta poner 1 con personal de OI."
      "  ·  Reglas duras: máx. 4 por turno, 1 por puesto."
  )
  for k, nombre in mt.DIA_TIPO:
    st.markdown(f"**{nombre}**")
    filas = [{"Puesto": pu,
              **{tn: int(CFG["cobertura"][k][tn].get(pu, 0))
                 for tn in ("T1", "T2", "T3")}}
             for pu in mt.PUESTOS]
    dfc = pd.DataFrame(filas).set_index("Puesto")
    ed = st.data_editor(
        dfc, key=f"cob_{k}", use_container_width=True,
        column_config={tn: st.column_config.NumberColumn(
            tn, min_value=0, max_value=1, step=1) for tn in ("T1", "T2", "T3")})
    for pu in mt.PUESTOS:
      for tn in ("T1", "T2", "T3"):
        CFG["cobertura"][k][tn][pu] = 1 if int(ed.loc[pu, tn]) else 0
  guardar_config(CFG)

# ===================== AUSENCIAS ======================================== #
with tab_ausencias:
  st.subheader("🏖️ Vacaciones y ausencias")
  cfga = CFG.setdefault("ausenciasCfg", {"bloqPend": True})
  cfga["bloqPend"] = st.checkbox(
      "Bloquear también las solicitudes pendientes (no sólo las aprobadas)",
      cfga.get("bloqPend", True))

  with st.form("form_ausencia", clear_on_submit=True):
    c1, c2, c3, c4, c5 = st.columns(5)
    a_op = c1.selectbox("Operador", [o["Nombre"] for o in OPS])
    a_tipo = c2.selectbox("Tipo", list(mt.TIPO_AUS),
                          format_func=lambda t: mt.TIPO_AUS[t]["label"])
    a_desde = c3.text_input("Desde (YYYY-MM-DD)")
    a_hasta = c4.text_input("Hasta (YYYY-MM-DD)")
    a_estado = c5.selectbox("Estado", ["Aprobada", "Solicitada"])
    if st.form_submit_button("Agregar") and a_desde:
      CFG.setdefault("ausencias", []).append({
          "id": f"a{len(CFG.get('ausencias', []))}_{a_op}",
          "personaId": a_op, "tipo": a_tipo,
          "desde": a_desde, "hasta": a_hasta or a_desde, "estado": a_estado})
      guardar_config(CFG)
      st.rerun()

  aus = CFG.get("ausencias", [])
  if aus:
    for i, au in enumerate(list(aus)):
      c1, c2 = st.columns([6, 0.5])
      c1.markdown(
          f"**{au['personaId']}** · "
          f"{mt.TIPO_AUS.get(au['tipo'], {}).get('label', au['tipo'])}"
          f" · {au['desde']} → {au['hasta']} · {au['estado']}")
      if c2.button("✕", key=f"delaus_{i}"):
        aus.remove(au)
        guardar_config(CFG)
        st.rerun()
  else:
    st.caption("Sin ausencias registradas.")
  guardar_config(CFG)

# ===================== FORZADOS / PRIORIDAD ============================= #
with tab_forzados:
  st.subheader("📌 Forzados")
  st.markdown(
      "**OI permanente:** el operador hace OI de lunes a viernes; sábados y"
      " domingos siguen el régimen. Se respetan su semana de descanso y sus"
      " ausencias."
  )
  c1, c2, c3 = st.columns([2, 2, 1])
  f_op = c1.selectbox("Operador", [o["Nombre"] for o in OPS], key="fz_op")
  f_tipo = c2.selectbox("Tipo", ["OI permanente", "Día puntual"])
  if f_tipo == "Día puntual":
    d1, d2 = st.columns(2)
    d1.text_input("Fecha (YYYY-MM-DD)", key="fz_fecha")
    d2.selectbox("Código", ["D", "OI", "T1", "T2", "T3"], key="fz_cod")
  if c3.button("Agregar regla"):
    fz = CFG.setdefault("forzados", [])
    if f_tipo == "OI permanente":
      if not any(r["tipo"] == "OI_PERM" and r["personaId"] == f_op for r in fz):
        fz.append({"id": f"f{len(fz)}", "tipo": "OI_PERM", "personaId": f_op})
    else:
      fz.append({"id": f"f{len(fz)}", "tipo": "DIA", "personaId": f_op,
                 "fecha": st.session_state.get("fz_fecha", ""),
                 "cod": st.session_state.get("fz_cod", "OI")})
    guardar_config(CFG)
    st.rerun()

  for i, r in enumerate(list(CFG.get("forzados", []))):
    c1, c2 = st.columns([6, 0.5])
    if r["tipo"] == "OI_PERM":
      c1.markdown(f"**{r['personaId']}** · OI permanente (Lun–Vie)")
    else:
      c1.markdown(f"**{r['personaId']}** · {r.get('fecha')} → {r.get('cod')}")
    if c2.button("✕", key=f"delfz_{i}"):
      CFG["forzados"].remove(r)
      guardar_config(CFG)
      st.rerun()

  st.markdown("---")
  st.subheader("🧮 Prioridad / jerarquía")
  st.markdown(
      "Se edita reordenando la lista en la pestaña **Operadores**. Orden actual:")
  st.markdown("  →  ".join(
      f"{i+1}. {n}" for i, n in enumerate(o["Nombre"] for o in OPS)))

# ===================== FERIADOS ======================================== #
with tab_feriados:
  st.subheader("🎉 Feriados")
  c1, c2, c3 = st.columns([2, 3, 1])
  c1.text_input("Fecha (YYYY-MM-DD)", key="fe_fecha")
  c2.text_input("Descripción", key="fe_nom")
  if c3.button("Agregar"):
    fers = CFG.setdefault("feriados", [])
    fe_fecha = st.session_state.get("fe_fecha", "")
    if fe_fecha and not any(f["fecha"] == fe_fecha for f in fers):
      fers.append({"fecha": fe_fecha, "nombre": st.session_state.get("fe_nom", "")})
      fers.sort(key=lambda f: f["fecha"])
      guardar_config(CFG)
      st.rerun()
  if st.button("Cargar feriados Perú 2026"):
    fers = CFG.setdefault("feriados", [])
    ya = {f["fecha"] for f in fers}
    fers.extend(f for f in mt.feriados_peru_2026() if f["fecha"] not in ya)
    fers.sort(key=lambda f: f["fecha"])
    guardar_config(CFG)
    st.rerun()

  for i, f in enumerate(list(CFG.get("feriados", []))):
    c1, c2 = st.columns([6, 0.5])
    c1.markdown(f"**{f['fecha']}** · {f.get('nombre', '')}")
    if c2.button("✕", key=f"delfer_{i}"):
      CFG["feriados"].remove(f)
      guardar_config(CFG)
      st.rerun()
  guardar_config(CFG)

# ===================== ROL GENERADO =================================== #
with tab_rol:
  st.subheader("📅 Rol generado (motor determinista)")
  st.caption(
      "Cada mínimo ≥ 1 del módulo **Cobertura** es obligatorio: el motor lo"
      " cubre con régimen → personal de OI → horas extra. Los mínimos en 0 son"
      " sólo un objetivo blando."
  )
  c1, c2 = st.columns(2)
  opt_oi = c1.checkbox("Usar personal de OI para cubrir turnos", True)
  opt_extra = c2.checkbox(
      "Cubrir faltantes obligatorios con personal en descanso (horas extra)", True)

  if st.button("⚙️ Generar rol", type="primary"):
    st.session_state.rol = mt.generar_rol(
        OPS, CFG,
        mes_oficial=CFG["ui"].get("mesOficial") or None,
        meses_ref=CFG["ui"].get("mesesRef", 2),
        optimizar_oi=opt_oi, cubrir_con_descanso=opt_extra)

  rol = st.session_state.get("rol")
  if not rol:
    st.info("Genera el rol para ver la grilla.")
  else:
    res = mt.resumen(rol)
    m1, m2, m3 = st.columns(3)
    m1.metric("Incumplimientos (✕)", res["incumplimientos"])
    m2.metric("Advertencias (▲)", res["advertencias"])
    m3.metric("Turnos fuera de régimen", res["turnos_fuera_de_regimen"])

    ym = st.selectbox("Mes", rol["meses"])
    g = rol["grillas"][ym]
    fer = set(rol["feriados"])
    cols = [f"{mt.DIAS[mt._js_dow(mt._parse(f))]} {mt._parse(f).day}"
            + ("*" if f in fer else "") for f in g["fechas"]]
    data = {fila["nombre"]: [fila["celdas"][f] for f in g["fechas"]]
            for fila in g["filas"]}
    grid = pd.DataFrame(data, index=cols).T
    try:
      vista = grid.style.map(_cell_style)
    except AttributeError:  # pandas < 2.1
      vista = grid.style.applymap(_cell_style)
    st.dataframe(vista, use_container_width=True, height=min(60 + 35 * len(grid), 720))
    st.caption(
        "T1 23-07 · T2 07-15 · T3 15-23 · OI oficina · D descanso · "
        "V/CP/PER/LM ausencias. Cabecera con * = feriado. "
        "El prefijo del código es el rol (C/ET/EF/A)."
    )
    st.download_button(
        "⬇️ Descargar CSV", grid.to_csv().encode("utf-8-sig"),
        file_name=f"rol_{ym}.csv", mime="text/csv")

    if res["detalle_incumplimientos"]:
      with st.expander(f"✕ {res['incumplimientos']} incumplimientos", expanded=True):
        for t in res["detalle_incumplimientos"]:
          st.markdown(f"- {t}")
    if res["detalle_advertencias"]:
      with st.expander(f"▲ {res['advertencias']} advertencias"):
        for t in res["detalle_advertencias"]:
          st.markdown(f"- {t}")

    with st.expander("🔎 ¿Por qué (no) hay cobertura en un turno?"):
      d1, d2, d3 = st.columns(3)
      dfecha = d1.selectbox("Día", g["fechas"], key="diag_f",
                            format_func=lambda f: f"{mt.DIAS[mt._js_dow(mt._parse(f))]} "
                            f"{mt._parse(f).day}")
      dturno = d2.selectbox("Turno", ["T1", "T2", "T3"], key="diag_t")
      dpuesto = d3.selectbox("Puesto", mt.PUESTOS, key="diag_p",
                             index=1)
      dg = mt.diagnostico_slot(rol, CFG, dfecha, dturno, dpuesto)
      if not dg["obligatorio"]:
        estado = "○ no obligatorio (mínimo 0)"
      elif dg["cumple"]:
        estado = "✅ cubierto"
      else:
        estado = "✕ incumplimiento (obligatorio sin cubrir)"
      st.markdown(
          f"**{dg['dia']} {mt._parse(dfecha).day}** · {dturno} · {dpuesto} "
          f"({dg['tipo_dia']}) — mínimo {dg['requerido']}, "
          f"asignados {dg['asignados']} → {estado}")
      if dg["candidatos"]:
        st.dataframe(pd.DataFrame([{
            "Operador": r["operador"],
            "Roles": " ".join(mt.ABBR[x] for x in r["roles"]),
            "Régimen": f"S{r['regimen_semana']} · {r['regimen_turno']}",
            "Código final": r["codigo_final"],
            "Motivo": r["motivo"],
        } for r in dg["candidatos"]]), use_container_width=True, hide_index=True)
      else:
        st.info(f"Ningún operador tiene **{dpuesto}** entre sus roles habilitados.")
      if dg["nota"]:
        st.caption(dg["nota"])

# ===================== AGENTE (CHAT) ================================= #
with tab_chat:
  st.markdown("### 💬 Interacción con el agente")
  st.caption(
      "El agente usa el motor determinista como herramienta: genera el rol,"
      " registra ausencias/feriados/forzados y ajusta cobertura o prioridad."
  )

  if "messages" not in st.session_state:
    st.session_state.messages = [{
        "role": "assistant",
        "content": (
            "¡Hola! Soy tu agente de turnos. Genero el rol con el motor"
            " determinista y te ayudo a optimizarlo. Prueba: *«genera el rol de"
            " agosto»*, *«pon a Ana Gómez de vacaciones del 10 al 15 y"
            " recalcula»*, *«¿por qué hay incumplimientos en T1?»*."
        ),
    }]

  for m in st.session_state.messages:
    with st.chat_message(m["role"]):
      st.markdown(m["content"])

  if prompt := st.chat_input("Escribe tu solicitud para el agente..."):
    if not client:
      st.error("Ingresa tu API Key de Gemini en la barra lateral.")
    else:
      st.session_state.messages.append({"role": "user", "content": prompt})
      with st.chat_message("user"):
        st.markdown(prompt)

      with st.chat_message("assistant"):
        with st.spinner("El agente está procesando..."):
          try:
            ag.CTX.operadores = OPS
            ag.CTX.config = CFG
            ag.CTX.novedades = novedades_input or ""

            contents = [
                genai.types.Content(
                    role="user" if m["role"] == "user" else "model",
                    parts=[genai.types.Part(text=m["content"])])
                for m in st.session_state.messages
            ]
            cfg = genai.types.GenerateContentConfig(
                system_instruction=ag.system_instruction(),
                temperature=0.3,
                tools=ag.TOOLS,
            )
            response = client.models.generate_content(
                model=MODEL, contents=contents, config=cfg)

            guardar_operadores(OPS)  # el agente pudo modificar el estado
            guardar_config(CFG)
            if ag.CTX.ultimo_rol:
              st.session_state.rol = ag.CTX.ultimo_rol

            answer = response.text or "(sin respuesta)"
            st.markdown(answer)
            st.session_state.messages.append(
                {"role": "assistant", "content": answer})
          except Exception as e:
            msg = f"Ocurrió un error al procesar la solicitud: {e}"
            st.error(msg)
            st.session_state.messages.append({"role": "assistant", "content": msg})
