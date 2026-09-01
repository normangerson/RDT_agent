"""Herramientas del agente Gemini sobre el motor determinista de turnos.

El agente NO inventa el rol: llama a estas funciones, que ejecutan
`motor_turnos.generar_rol` y devuelven la grilla y las incidencias reales.
También puede registrar ausencias, feriados, forzados y ajustar la cobertura
o la prioridad antes de volver a generar.

Uso desde la app (Streamlit):

    import agente_turnos as ag
    ag.CTX.operadores = st.session_state.operadores
    ag.CTX.config = st.session_state.config
    ag.CTX.novedades = novedades_input
    resp = client.models.generate_content(
        model=MODEL, contents=contents,
        config=genai.types.GenerateContentConfig(
            system_instruction=ag.system_instruction(),
            temperature=0.3, tools=ag.TOOLS,
        ),
    )
    # persistir por si alguna herramienta modificó el estado:
    guardar_operadores(ag.CTX.operadores); guardar_config(ag.CTX.config)

La librería `google-genai` introspecciona la firma y el docstring de cada
función para exponerla como *tool* (automatic function calling).
"""

from __future__ import annotations

import datetime as _dt
import unicodedata
from dataclasses import dataclass, field

import motor_turnos as mt


def _fold(s: str) -> str:
    """minúsculas sin acentos, para comparar nombres de forma tolerante."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).strip().lower()


@dataclass
class _Ctx:
    operadores: list[dict] = field(default_factory=list)
    config: dict = field(default_factory=mt.config_default)
    novedades: str = ""
    ultimo_rol: dict | None = None  # resultado de la última generación (para la UI)


CTX = _Ctx()


# --------------------------------------------------------------------------- #
#  Helpers internos                                                            #
# --------------------------------------------------------------------------- #

def _resolver_operador(nombre: str) -> str | None:
    """Devuelve el id/nombre exacto de un operador a partir de un texto."""
    n = _fold(nombre)
    for op in CTX.operadores:
        if _fold(op.get("Nombre", "")) == n:
            return op["Nombre"]
    for op in CTX.operadores:  # coincidencia parcial
        if n and n in _fold(op.get("Nombre", "")):
            return op["Nombre"]
    return None


def _nuevo_id(prefijo: str) -> str:
    return prefijo + _dt.datetime.now().strftime("%Y%m%d%H%M%S%f")


# --------------------------------------------------------------------------- #
#  Herramientas de consulta                                                    #
# --------------------------------------------------------------------------- #

def consultar_operadores() -> list[dict]:
    """Lista los operadores registrados con sus roles habilitados, semana del
    ciclo, fecha base, costo por turno y si están activos. El orden de la lista
    es el orden de prioridad/jerarquía."""
    return [
        {
            "nombre": o.get("Nombre"),
            "roles_habilitados": o.get("Roles Habilitados", []),
            "semana_ciclo": o.get("Semana Ciclo", 1),
            "fecha_base": o.get("Fecha Base") or "(lunes de referencia)",
            "costo_turno": o.get("Costo Turno", 50),
            "activo": o.get("Activo", True),
        }
        for o in CTX.operadores
    ]


def verificar_anclaje(mes_oficial: str = "") -> dict:
    """Muestra cómo queda anclado cada operador en el ciclo rotativo: su lunes
    base efectivo, la semana del ciclo declarada y en qué semana del ciclo cae
    el primer lunes del mes oficial. Úsalo para revisar que el rol arranca
    donde debe o si el usuario pregunta por qué un operador rota como rota."""
    return mt.anclaje(CTX.operadores, CTX.config, mes_oficial or None)


def fijar_anclaje(operador: str, fecha_base: str = "", semana_ciclo: int = 0) -> dict:
    """Ajusta el anclaje de un operador en el ciclo.

    Args:
        operador: nombre del operador.
        fecha_base: un lunes "YYYY-MM-DD" (si no es lunes se ajusta al lunes de
            esa semana). Vacío = no cambiar.
        semana_ciclo: 1..5, la semana del ciclo en la que estaba ese lunes.
            0 = no cambiar.
    """
    n = _fold(operador)
    op = next((o for o in CTX.operadores if _fold(o.get("Nombre", "")) == n), None)
    if op is None:
        op = next((o for o in CTX.operadores
                   if n and n in _fold(o.get("Nombre", ""))), None)
    if op is None:
        return {"error": f"No encontré al operador '{operador}'."}
    if fecha_base:
        lun = mt._lunes_de_safe(fecha_base)
        if not lun:
            return {"error": f"Fecha inválida: '{fecha_base}'."}
        op["Fecha Base"] = lun
    if semana_ciclo:
        if not 1 <= int(semana_ciclo) <= 5:
            return {"error": "semana_ciclo debe estar entre 1 y 5."}
        op["Semana Ciclo"] = int(semana_ciclo)
    return {"ok": True,
            "operador": op["Nombre"],
            "fecha_base": op.get("Fecha Base", "(lunes de referencia)"),
            "semana_ciclo": op.get("Semana Ciclo", 1),
            "nota": "Vuelve a llamar a generar_rol para ver el efecto."}


def consultar_regimen() -> dict:
    """Devuelve el régimen rotativo vigente (patrón de 5 semanas, Lun..Dom),
    las reglas de secuencia (1 turno/día, descanso mínimo de 8 h) y los
    requisitos de cobertura por tipo de día y turno."""
    reg = CTX.config["regimen"]
    patron = reg["patron"]
    n = reg["nSem"]
    semanas = {
        f"Semana {i+1} ({mt.SEM_NOMBRE.get(i+1, '')})":
            dict(zip(["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"],
                     patron[i * 7:i * 7 + 7]))
        for i in range(n)
    }
    return {
        "semanas": semanas,
        "reglas": reg.get("reglas", {}),
        "cobertura_minima": CTX.config["cobertura"],
        "feriados": CTX.config.get("feriados", []),
        "forzados": CTX.config.get("forzados", []),
        "ausencias": CTX.config.get("ausencias", []),
    }


# --------------------------------------------------------------------------- #
#  Herramienta principal: generar el rol                                       #
# --------------------------------------------------------------------------- #

def generar_rol(
    mes_oficial: str = "",
    meses_referencia: int = 2,
    optimizar_oi: bool = True,
    cubrir_con_personal_en_descanso: bool = True,
) -> dict:
    """Genera el rol de turnos de forma DETERMINISTA aplicando todos los
    criterios: régimen de 5 semanas anclado por operador, semana de descanso
    intocable, ausencias, feriados, forzados, prioridad y requisitos de
    cobertura (máx. 4 por turno, 1 por puesto).

    Cada mínimo ≥ 1 del módulo de cobertura es OBLIGATORIO y el motor recurre a
    lo que haga falta para cumplirlo (personal en OI y, si no alcanza, horas
    extra de personal en descanso). Los mínimos en 0 son sólo un objetivo blando.

    Úsalo SIEMPRE que el usuario pida generar, recalcular, optimizar, simular o
    revisar el rol. No construyas la grilla a mano: llama a esta función y
    explica/comenta su resultado.

    Args:
        mes_oficial: mes a planificar en formato "YYYY-MM" (vacío = el configurado).
        meses_referencia: nº de meses siguientes a incluir como referencia (0-11).
        optimizar_oi: usar al personal en su semana de oficina para cubrir turnos.
        cubrir_con_personal_en_descanso: permitir horas extra (fuera de régimen,
            con sobretasa) para cumplir los mínimos obligatorios que no se
            cubren por régimen ni con personal de OI.

    Returns:
        dict con la grilla en Markdown del mes oficial, el resumen de cobertura,
        el nº de incumplimientos/advertencias y su detalle.
    """
    rol = mt.generar_rol(
        CTX.operadores,
        CTX.config,
        mes_oficial=mes_oficial or None,
        meses_ref=meses_referencia,
        optimizar_oi=optimizar_oi,
        cubrir_con_descanso=cubrir_con_personal_en_descanso,
    )
    CTX.ultimo_rol = rol
    res = mt.resumen(rol)
    ym = rol["meses"][0]
    return {
        "mes_oficial": ym,
        "meses_referencia": rol["meses"][1:],
        "grilla_markdown": mt.grilla_markdown(rol, ym),
        "incumplimientos": res["incumplimientos"],
        "advertencias": res["advertencias"],
        "turnos_fuera_de_regimen": res["turnos_fuera_de_regimen"],
        "detalle_incumplimientos": res["detalle_incumplimientos"],
        "detalle_advertencias": res["detalle_advertencias"],
        "carga_por_operador": res["por_operador"],
        "leyenda": "OI=oficina · T1=23-07 · T2=07-15 · T3=15-23 · D=descanso · "
                   "V/CP/PER/LM=ausencias · el prefijo es el rol (C/ET/EF/A). "
                   "Un '*' en la cabecera marca feriado.",
    }


def calcular_costos() -> dict:
    """Calcula el costo aproximado del último rol generado: costo base (turnos
    dentro del régimen) más sobretasa de los turnos fuera de régimen (día de
    descanso, feriado, nocturno) según los factores configurados. Requiere
    haber llamado antes a `generar_rol`."""
    if not CTX.ultimo_rol:
        return {"error": "Primero genera el rol con generar_rol."}
    return mt.calcular_costos(CTX.ultimo_rol, CTX.operadores, CTX.config["costos"])


def diagnosticar_slot(fecha: str, turno: str, puesto: str) -> dict:
    """Explica por qué un puesto está o no cubierto en un turno de un día
    concreto del último rol generado: lista a cada operador con ese rol
    habilitado y el motivo por el que ese día cubre o no (régimen, ausencia,
    semana de descanso, forzado, demote, en OI, en descanso...).

    Úsalo cuando el usuario pregunte «¿por qué no hay X en el turno Y el día Z?».

    Args:
        fecha: "YYYY-MM-DD".
        turno: "T1", "T2" o "T3".
        puesto: "Coordinador", "Especialista Tensión", "Especialista Frecuencia",
            "Analista" (o su abreviatura C/ET/EF/A).
    """
    if not CTX.ultimo_rol:
        return {"error": "Primero genera el rol con generar_rol."}
    return mt.diagnostico_slot(CTX.ultimo_rol, CTX.config, fecha,
                               turno, puesto)


# --------------------------------------------------------------------------- #
#  Herramientas que ajustan los criterios                                      #
# --------------------------------------------------------------------------- #

def registrar_ausencia(
    operador: str, tipo: str, desde: str, hasta: str = "", estado: str = "Aprobada"
) -> dict:
    """Registra una ausencia que saca al operador del rol en esas fechas.

    Args:
        operador: nombre del operador.
        tipo: uno de "VAC" (vacaciones), "CAP" (capacitación), "PER" (permiso)
            o "MED" (licencia médica).
        desde: fecha inicial "YYYY-MM-DD".
        hasta: fecha final "YYYY-MM-DD" (vacío = un solo día).
        estado: "Aprobada" o "Solicitada".
    """
    pid = _resolver_operador(operador)
    if not pid:
        return {"error": f"No encontré al operador '{operador}'."}
    tipo = tipo.upper()
    if tipo not in mt.TIPO_AUS:
        return {"error": f"Tipo inválido. Usa uno de {list(mt.TIPO_AUS)}."}
    if estado not in ("Aprobada", "Solicitada"):
        estado = "Aprobada"
    reg = {
        "id": _nuevo_id("a"), "personaId": pid, "tipo": tipo,
        "desde": desde, "hasta": hasta or desde, "estado": estado,
    }
    CTX.config.setdefault("ausencias", []).append(reg)
    return {"ok": True, "ausencia": reg,
            "nota": "Vuelve a llamar a generar_rol para ver el efecto."}


def eliminar_ausencia(operador: str, desde: str = "") -> dict:
    """Elimina ausencias de un operador (todas, o sólo la que empieza en `desde`)."""
    pid = _resolver_operador(operador)
    if not pid:
        return {"error": f"No encontré al operador '{operador}'."}
    antes = len(CTX.config.get("ausencias", []))
    CTX.config["ausencias"] = [
        a for a in CTX.config.get("ausencias", [])
        if not (a["personaId"] == pid and (not desde or a["desde"] == desde))
    ]
    return {"ok": True, "eliminadas": antes - len(CTX.config["ausencias"])}


def registrar_feriado(fecha: str, nombre: str = "") -> dict:
    """Agrega un feriado (formato "YYYY-MM-DD"). Los feriados cambian el tipo de
    día y activan la sobretasa para quien cubra fuera de su régimen ese día."""
    fers = CTX.config.setdefault("feriados", [])
    if any(f["fecha"] == fecha for f in fers):
        return {"error": "Ese feriado ya está registrado."}
    fers.append({"fecha": fecha, "nombre": nombre})
    fers.sort(key=lambda f: f["fecha"])
    return {"ok": True, "feriados": fers}


def cargar_feriados_peru_2026() -> dict:
    """Carga la lista de feriados nacionales de Perú para 2026."""
    fers = CTX.config.setdefault("feriados", [])
    ya = {f["fecha"] for f in fers}
    for f in mt.feriados_peru_2026():
        if f["fecha"] not in ya:
            fers.append(f)
    fers.sort(key=lambda f: f["fecha"])
    return {"ok": True, "feriados": fers}


def registrar_forzado_oi_permanente(operador: str) -> dict:
    """Fuerza a un operador a hacer OI (oficina) de lunes a viernes de forma
    permanente. Sábados y domingos siguen su rol natural del régimen; se
    respetan su semana de descanso y sus ausencias."""
    pid = _resolver_operador(operador)
    if not pid:
        return {"error": f"No encontré al operador '{operador}'."}
    fz = CTX.config.setdefault("forzados", [])
    if any(r["tipo"] == "OI_PERM" and r["personaId"] == pid for r in fz):
        return {"error": "Ese operador ya tiene la regla OI permanente."}
    fz.append({"id": _nuevo_id("f"), "tipo": "OI_PERM", "personaId": pid})
    return {"ok": True, "nota": "Vuelve a llamar a generar_rol para ver el efecto."}


def registrar_forzado_dia(operador: str, codigo: str, desde: str,
                          hasta: str = "") -> dict:
    """Forza un código para un operador en un día o en un rango de días.

    Args:
        operador: nombre del operador.
        codigo: "D", "OI", "T1", "T2" o "T3" (el prefijo del rol se añade solo),
            o un código completo tipo "ET2".
        desde: fecha inicial "YYYY-MM-DD".
        hasta: fecha final "YYYY-MM-DD" (vacío = un solo día).
    """
    pid = _resolver_operador(operador)
    if not pid:
        return {"error": f"No encontré al operador '{operador}'."}
    fz = CTX.config.setdefault("forzados", [])
    fz.append({"id": _nuevo_id("f"), "tipo": "DIA", "personaId": pid,
               "desde": desde, "hasta": hasta or desde, "cod": codigo.upper()})
    return {"ok": True, "nota": "Vuelve a llamar a generar_rol para ver el efecto."}


def quitar_forzados(operador: str) -> dict:
    """Elimina todas las reglas de forzado de un operador."""
    pid = _resolver_operador(operador)
    if not pid:
        return {"error": f"No encontré al operador '{operador}'."}
    antes = len(CTX.config.get("forzados", []))
    CTX.config["forzados"] = [
        r for r in CTX.config.get("forzados", []) if r["personaId"] != pid
    ]
    return {"ok": True, "eliminados": antes - len(CTX.config["forzados"])}


def fijar_cobertura(tipo_dia: str, turno: str, puesto: str, minimo: int) -> dict:
    """Fija el mínimo de personas de un puesto en un turno para un tipo de día.

    Args:
        tipo_dia: "LV" (lunes a viernes), "SAB", "DOM" o "FER" (feriado).
        turno: "T1", "T2" o "T3".
        puesto: "Coordinador", "Especialista Tensión", "Especialista Frecuencia"
            o "Analista".
        minimo: 0 o 1. Con 0 no es obligatorio (pero el motor igual intenta 1 con
            personal de OI); con 1 se exige y se marca incumplimiento si falta.
    """
    tipo_dia = tipo_dia.upper()
    turno = turno.upper()
    if tipo_dia not in dict(mt.DIA_TIPO):
        return {"error": f"tipo_dia inválido. Usa uno de {[k for k, _ in mt.DIA_TIPO]}."}
    if turno not in ("T1", "T2", "T3"):
        return {"error": "turno inválido. Usa T1, T2 o T3."}
    if puesto not in mt.PUESTOS:
        return {"error": f"puesto inválido. Usa uno de {mt.PUESTOS}."}
    CTX.config["cobertura"][tipo_dia][turno][puesto] = 1 if int(minimo) else 0
    return {"ok": True, "cobertura": CTX.config["cobertura"][tipo_dia][turno]}


def mover_prioridad(operador: str, direccion: str) -> dict:
    """Sube o baja a un operador en la lista de prioridad/jerarquía.
    `direccion` = "subir" o "bajar". El nº 1 tiene la mayor jerarquía."""
    pid = _resolver_operador(operador)
    if not pid:
        return {"error": f"No encontré al operador '{operador}'."}
    orden = [o["Nombre"] for o in CTX.operadores]
    if pid not in orden:
        return {"error": "Operador no está en la lista."}
    i = orden.index(pid)
    j = i - 1 if direccion.lower().startswith("sub") else i + 1
    if j < 0 or j >= len(orden):
        return {"error": "Ya está en el extremo."}
    CTX.operadores[i], CTX.operadores[j] = CTX.operadores[j], CTX.operadores[i]
    CTX.config["prioridad"] = [o["Nombre"] for o in CTX.operadores]
    return {"ok": True, "orden": CTX.config["prioridad"]}


# --------------------------------------------------------------------------- #
#  Registro de tools + system instruction                                      #
# --------------------------------------------------------------------------- #

TOOLS = [
    consultar_operadores,
    consultar_regimen,
    verificar_anclaje,
    fijar_anclaje,
    generar_rol,
    calcular_costos,
    diagnosticar_slot,
    registrar_ausencia,
    eliminar_ausencia,
    registrar_feriado,
    cargar_feriados_peru_2026,
    registrar_forzado_oi_permanente,
    registrar_forzado_dia,
    quitar_forzados,
    fijar_cobertura,
    mover_prioridad,
]


def system_instruction() -> str:
    nov = CTX.novedades.strip() or "Ninguna"
    return f"""\
Eres un agente experto en planificación y optimización de turnos para un Centro
de Control eléctrico que opera 24/7.

REGLA DE ORO: el rol se construye con el MOTOR DETERMINISTA, no de memoria.
Para cualquier petición de generar, recalcular, optimizar, simular o revisar el
rol, llama a la herramienta `generar_rol` y basa tu respuesta en lo que
devuelve (grilla, cobertura, incumplimientos). Si el usuario pide un cambio de
criterio (una baja, un feriado, un OI permanente, subir/bajar una cobertura o la
prioridad de alguien), primero llama a la herramienta correspondiente y luego
vuelve a llamar a `generar_rol`.

CRITERIOS QUE APLICA EL MOTOR (ya implementados, no los recalcules tú):
- Régimen rotativo de 5 semanas, anclado por operador: cada uno tiene una
  FECHA BASE (un lunes concreto) y la SEMANA DEL CICLO en la que estaba ese
  lunes; desde ahí el motor propaga la rotación. Si el usuario dice cosas como
  «el lunes 27 de julio Fulano estaba en la semana 3», usa `fijar_anclaje`.
  Para revisar cómo queda cada operador usa `verificar_anclaje`.
  Códigos: OI oficina · T1 23-07 · T2 07-15 · T3 15-23 · D.
- La semana de descanso (Lun-Dom) es intocable: el motor nunca la usa.
- Reglas de secuencia fijas: 1 turno por día y descanso mínimo de 8 h entre
  turnos, lo que prohíbe encadenar T1->T2 al día siguiente.
- Ausencias (VAC/CAP/PER/MED) y feriados.
- Forzados: OI permanente (Lun-Vie) o un código fijo en un día o rango de días.
- Jerarquía de roles: C > ET > EF > A. La POSICIÓN del operador en el módulo
  (el orden de la lista, el nº 1 es el de mayor jerarquía) decide quién se
  lleva el rol más alto: si hay que repartir p. ej. EF y A entre dos personas,
  el de mayor jerarquía se lleva EF. Ajústala con `mover_prioridad`.
- Cobertura por turno y tipo de día. El módulo de cobertura ES la definición de
  qué es obligatorio: cada mínimo >= 1 es OBLIGATORIO (para cualquier puesto y
  turno, incluido T1) y el motor recurre a régimen -> personal en OI -> horas
  extra de personal en descanso hasta cumplirlo; si no lo logra es un
  incumplimiento (X). Un mínimo en 0 es sólo un objetivo blando (se intenta 1
  con gente de OI, sin error si falta). Reglas duras: máx. 4 personas por
  turno y 1 por puesto.
- Reparto del personal escaso: 1º gente en OI, 2º reasignar a quien cubre un
  slot no obligatorio, 3º horas extra (personal en descanso, fuera de régimen,
  con sobretasa). Cuando no se puede cubrir todo, T1 cede antes que T2/T3.

ROLES: C Coordinador · ET Especialista Tensión · EF Especialista Frecuencia ·
A Analista. En la grilla el prefijo del código es el rol (p. ej. ET2 = Esp.
Tensión en turno 2).

Presenta la grilla y las propuestas en tablas Markdown limpias. Señala siempre
los incumplimientos (✕) y advertencias (▲) que reporte el motor y propón cómo
resolverlos (ajustar cobertura, mover prioridad, autorizar horas extra, etc.).

NOVEDADES ACTIVAS declaradas por el usuario: {nov}
"""
