import json
import os

import pandas as pd
import streamlit as st
from google import genai

import motor_turnos as mt
import agente_turnos as ag

MODEL = "gemini-3.6-flash"

st.set_page_config(
    page_title="Agente de Turnos - Centro de Control",
    page_icon="🛡️",
    layout="wide",
)

st.title("🛡️ Agente Inteligente de Turnos - Centro de Control")
st.markdown(
    "Sistema autónomo para la planificación, optimización y gestión de turnos"
    " operativos 24/7. El rol se construye con un **motor determinista** y el"
    " agente lo consulta, explica y ajusta."
)

# --------------------------------------------------------------------------- #
#  Persistencia                                                                #
# --------------------------------------------------------------------------- #
DB_FILE = "operadores.json"
CFG_FILE = "config_rol.json"


def cargar_operadores():
  if os.path.exists(DB_FILE):
    try:
      with open(DB_FILE, "r", encoding="utf-8") as f:
        ops = json.load(f)
      for o in ops:  # completar campos nuevos en registros antiguos
        o.setdefault("Puesto", "")
        o.setdefault("Costo Turno", 50)
        o.setdefault("Fecha Base", "")
        o.setdefault("Activo", True)
      return ops
    except Exception:
      pass
  return mt.operadores_ejemplo()


def guardar_operadores(ops):
  with open(DB_FILE, "w", encoding="utf-8") as f:
    json.dump(ops, f, ensure_ascii=False, indent=4)


def _merge(base, disk):
  for k, v in disk.items():
    if isinstance(v, dict) and isinstance(base.get(k), dict):
      base[k] = _merge(base[k], v)
    else:
      base[k] = v
  return base


def cargar_config():
  cfg = mt.config_default()
  if os.path.exists(CFG_FILE):
    try:
      with open(CFG_FILE, "r", encoding="utf-8") as f:
        cfg = _merge(cfg, json.load(f))
    except Exception:
      pass
  return cfg


def guardar_config(cfg):
  with open(CFG_FILE, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=4)


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
  st.subheader("🛡️ Reglas de secuencia")
  reglas = CFG["regimen"].setdefault("reglas", {})
  reglas["minDescansoHoras"] = st.slider(
      "Descanso mínimo entre turnos (horas)", 8, 16,
      int(reglas.get("minDescansoHoras", 12)))
  reglas["maxNocturnosSeguidos"] = st.number_input(
      "Máx. turnos T1 (nocturnos) consecutivos", 1, 7,
      int(reglas.get("maxNocturnosSeguidos", 3)))
  proh = ", ".join(f"{a}→{b}" for a, b in mt.prohibidas(reglas["minDescansoHoras"]))
  st.caption(f"Transiciones prohibidas: {proh or 'ninguna'}")

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
  st.subheader("Gestión de personal y orden de prioridad")
  st.markdown(
      "**Roles:** **C** Coordinador · **ET** Especialista Tensión · **EF**"
      " Especialista Frecuencia · **A** Analista.  ·  El **orden** de la lista"
      " es la jerarquía (el nº 1 manda al repartir roles)."
  )

  col_tabla, col_form = st.columns([2, 1])

  with col_tabla:
    st.markdown("### Personal registrado")
    for idx, op in enumerate(OPS):
      c_info, c_up, c_down, c_del = st.columns([5, 0.6, 0.6, 0.6])
      with c_info:
        roles_str = ", ".join(op.get("Roles Habilitados", []))
        act = "" if op.get("Activo", True) else " · _inactivo_"
        st.markdown(
            f"**{idx+1}. {op['Nombre']}** — `[{roles_str}]` · "
            f"{op.get('Puesto') or 'sin puesto'} · Ciclo S{op.get('Semana Ciclo', 1)}"
            f" · costo {op.get('Costo Turno', 50)}{act}"
        )
      with c_up:
        if idx > 0 and st.button("▲", key=f"up_{idx}"):
          OPS[idx - 1], OPS[idx] = OPS[idx], OPS[idx - 1]
          guardar_operadores(OPS)
          st.rerun()
      with c_down:
        if idx < len(OPS) - 1 and st.button("▼", key=f"down_{idx}"):
          OPS[idx + 1], OPS[idx] = OPS[idx], OPS[idx + 1]
          guardar_operadores(OPS)
          st.rerun()
      with c_del:
        if st.button("✕", key=f"del_{idx}"):
          OPS.pop(idx)
          guardar_operadores(OPS)
          st.rerun()

  with col_form:
    st.markdown("### ➕ Agregar / editar")
    nombres = ["(nuevo)"] + [o["Nombre"] for o in OPS]
    sel = st.selectbox("Operador", nombres)
    editando = None if sel == "(nuevo)" else next(o for o in OPS if o["Nombre"] == sel)
    with st.form("form_operador", clear_on_submit=(editando is None)):
      nombre = st.text_input("Nombre", value=editando["Nombre"] if editando else "")
      puesto = st.selectbox(
          "Puesto principal", mt.CARGOS,
          index=mt.CARGOS.index(editando["Puesto"])
          if editando and editando.get("Puesto") in mt.CARGOS else 3)
      semana = st.selectbox(
          "Semana actual del ciclo", [1, 2, 3, 4, 5],
          index=(editando.get("Semana Ciclo", 1) - 1) if editando else 0)
      hab = editando.get("Roles Habilitados", []) if editando else ["A"]
      c1, c2 = st.columns(2)
      rol_c = c1.checkbox("Coordinador (C)", "C" in hab)
      rol_et = c1.checkbox("Esp. Tensión (ET)", "ET" in hab)
      rol_ef = c2.checkbox("Esp. Frecuencia (EF)", "EF" in hab)
      rol_a = c2.checkbox("Analista (A)", ("A" in hab) or (editando is None))
      costo = st.slider("Costo por turno (1-100)", 1, 100,
                        int(editando.get("Costo Turno", 50)) if editando else 50)
      fecha_base = st.text_input(
          "Fecha base — un lunes (YYYY-MM-DD, opcional)",
          value=editando.get("Fecha Base", "") if editando else "")
      activo = st.checkbox("Activo", editando.get("Activo", True) if editando else True)
      ok = st.form_submit_button("Guardar")

      if ok and nombre:
        roles = [r for r, v in
                 (("C", rol_c), ("ET", rol_et), ("EF", rol_ef), ("A", rol_a)) if v]
        rec = {
            "Nombre": nombre,
            "Roles Habilitados": roles or ["A"],
            "Semana Ciclo": semana,
            "Puesto": puesto,
            "Costo Turno": costo,
            "Fecha Base": fecha_base.strip(),
            "Activo": activo,
        }
        if editando:
          editando.update(rec)
        else:
          OPS.append(rec)
        guardar_operadores(OPS)
        st.success(f"{nombre} guardado.")
        st.rerun()

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
  c1, c2, c3 = st.columns(3)
  opt_oi = c1.checkbox("Optimizar semana OI para cobertura", True)
  opt_extra = c2.checkbox("Cubrir faltantes con personal en descanso", True)
  opt_t1 = c3.checkbox("Horas extra en T1 y Esp. Frecuencia", False)

  if st.button("⚙️ Generar rol", type="primary"):
    st.session_state.rol = mt.generar_rol(
        OPS, CFG,
        mes_oficial=CFG["ui"].get("mesOficial") or None,
        meses_ref=CFG["ui"].get("mesesRef", 2),
        optimizar_oi=opt_oi, cubrir_con_descanso=opt_extra,
        horas_extra_t1_ef=opt_t1)

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
    st.dataframe(grid, use_container_width=True)
    st.caption("Cabecera con * = feriado. Prefijo del código = rol (C/ET/EF/A).")
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
