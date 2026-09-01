"""Motor determinista de elaboración del rol de turnos.

Port a Python de la lógica del archivo `rol-turnos-coes.html` (proyecto
RDTLightning). Aquí vive todo lo que **da criterios** a la construcción del rol:

  * Régimen rotativo de 5 semanas (editable) anclado por operador
    (fecha base = un lunes + semana del ciclo en esa fecha).
  * Reglas de secuencia (fijas): 1 turno por día y descanso mínimo de 8 h
    entre turnos. T1 es nocturno rotulado por el día en que termina (23:00 de
    la víspera -> 07:00). Única transición prohibida: T3 -> T1 al día siguiente.
  * Semana de descanso "intocable" (Lun-Dom).
  * Ausencias (vacaciones / capacitación / permiso / licencia médica).
  * Forzados (OI permanente de lunes a viernes, o un código fijo en un rango
    de días).
  * Prioridad / jerarquía entre operadores.
  * Requerimientos de cobertura por turno y tipo de día, con reglas duras
    (máx. 4 personas por turno, 1 por puesto) y objetivo blando de 1 de cada rol.
  * Feriados (cambian el tipo de día y activan la sobretasa).
  * Reparto escalonado del personal escaso: primero gente en OI, luego
    reasignar a quien hace algo prescindible, y sólo al final horas extra
    (personal en descanso, fuera de régimen).

El módulo es **puro**: no depende de Streamlit ni de Gemini. Entra un estado
(operadores + configuración) y sale una estructura con la grilla, el resumen de
cobertura y la lista de incumplimientos/advertencias.
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
from typing import Any

# --------------------------------------------------------------------------- #
#  Constantes de dominio                                                       #
# --------------------------------------------------------------------------- #

CARGOS = ["Coordinador", "Especialista", "Especialista Jr", "Analista"]
PUESTOS = [
    "Coordinador",
    "Especialista Tensión",
    "Especialista Frecuencia",
    "Analista",
]

# rol base que el régimen le da a cada operador según su cargo
CARGO_ROL = {
    "Coordinador": "Coordinador",
    "Especialista": "Especialista Tensión",
    "Especialista Jr": "Especialista Frecuencia",
    "Analista": "Analista",
}
ABBR = {
    "Coordinador": "C",
    "Especialista Tensión": "ET",
    "Especialista Frecuencia": "EF",
    "Analista": "A",
}
ABBR_INV = {v: k for k, v in ABBR.items()}

# Especialista Tensión y Especialista Frecuencia rotan juntos (2 por turno)
FAMILIA = {"Especialista Tensión": "ESP", "Especialista Frecuencia": "ESP"}

# Jerarquía de roles: C > ET > EF > A. Se usa para todo —
#   * inferir el rol base de un operador,
#   * ORDEN de asignación: se llena primero el rol más alto y se le da al
#     operador de mayor jerarquía (posición en el módulo de operadores) que lo
#     pueda cubrir. Ej.: si hay que repartir EF y A entre dos personas, el de
#     mayor jerarquía se lleva EF.
JERARQUIA = [
    "Coordinador",
    "Especialista Tensión",
    "Especialista Frecuencia",
    "Analista",
]

# Orden de turnos cuando el personal no alcanza para cubrir todo (T1 cede antes).
PRIO_TURNO = ["T2", "T3", "T1"]

TIPO_AUS = {
    "VAC": {"cod": "V", "label": "Vacaciones"},
    "CAP": {"cod": "CP", "label": "Capacitación"},
    "PER": {"cod": "PER", "label": "Permiso"},
    "MED": {"cod": "LM", "label": "Licencia médica"},
}
SEM_NOMBRE = {1: "OI (oficina)", 2: "Turno 2", 3: "Turno 3", 4: "Turno 1", 5: "Descanso"}

# Horario de cada turno en horas del DÍA QUE ROTULA la celda.
# T1 es nocturno y se rotula por el día en que TERMINA: T1 del día N va de las
# 23:00 del día N-1 (hora -1) a las 07:00 del día N. Dentro de un día el orden
# es T1 (madrugada) -> T2 -> T3.
TURNO_H = {
    "T1": {"ini": -1, "fin": 7},
    "T2": {"ini": 7, "fin": 15},
    "T3": {"ini": 15, "fin": 23},
}
TURNO_NUM = {"T1": "1", "T2": "2", "T3": "3"}

# Reglas de secuencia (fijas): 1 turno por día y descanso mínimo entre turnos
# de 8 horas (= la duración de un turno). Con este horario, la única transición
# que queda prohibida es T3 -> T1 al día siguiente: T3 termina 23:00 y el T1
# del día siguiente arranca esa misma hora (0 h de descanso).
DESCANSO_MIN_HORAS = 8

DIA_TIPO = [
    ("LV", "Lunes a viernes"),
    ("SAB", "Sábado"),
    ("DOM", "Domingo"),
    ("FER", "Feriado"),
]
DIAS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"]  # índice = getDay() estilo JS

MAX_TURNO = 4  # regla dura: como máximo 4 personas por turno


# --------------------------------------------------------------------------- #
#  Utilidades de fecha (equivalentes a las del HTML)                           #
# --------------------------------------------------------------------------- #

def _parse(s: str) -> dt.date:
    y, m, d = (int(x) for x in s.split("-"))
    return dt.date(y, m, d)


def _ymd(d: dt.date) -> str:
    return f"{d.year:04d}-{d.month:02d}-{d.day:02d}"


def _js_dow(d: dt.date) -> int:
    """0 = domingo ... 6 = sábado (como Date.getDay() en JavaScript)."""
    return d.isoweekday() % 7


def _add_days(d: dt.date, n: int) -> dt.date:
    return d + dt.timedelta(days=n)


def _diff_days(a: dt.date, b: dt.date) -> int:
    return (a - b).days


def _month_days(ym: str) -> int:
    y, m = (int(x) for x in ym.split("-"))
    return calendar.monthrange(y, m)[1]


def _month_list(ym: str, extra: int) -> list[str]:
    y, m = (int(x) for x in ym.split("-"))
    out = []
    for i in range(extra + 1):
        mm = m - 1 + i
        yy = y + mm // 12
        out.append(f"{yy:04d}-{mm % 12 + 1:02d}")
    return out


def _lunes_ref(mes_oficial: str) -> str:
    """Lunes de (o anterior a) el día 1 del mes oficial."""
    m1 = _parse((mes_oficial or "2026-08")[:7] + "-01")
    return _ymd(_add_days(m1, -(((m1.isoweekday() - 1) + 7) % 7)))


def _lunes_de(fecha: str) -> str:
    """Ajusta cualquier fecha 'YYYY-MM-DD' al lunes de esa semana."""
    d = _parse(fecha)
    return _ymd(_add_days(d, -(((d.isoweekday() - 1) + 7) % 7)))


def es_lunes(fecha: str) -> bool:
    try:
        return _parse(fecha).isoweekday() == 1
    except Exception:
        return False


def _lunes_de_safe(fecha) -> str | None:
    """Como _lunes_de pero tolerante: None si la fecha es vacía o inválida."""
    if not fecha:
        return None
    try:
        return _lunes_de(str(fecha)[:10])
    except Exception:
        return None


# --------------------------------------------------------------------------- #
#  Estado por defecto                                                          #
# --------------------------------------------------------------------------- #

def patron_default() -> list[str]:
    """Régimen rotativo de 5 semanas (Lun..Dom por fila).

    Patrón uniforme por semana (una semana entera en cada turno). Es editable
    desde la pestaña Régimen. Se elige uniforme por defecto porque no genera
    transiciones prohibidas entre días ni al cambiar de semana.
    """
    semanas = [
        ["OI", "OI", "OI", "OI", "OI", "OI", "OI"],   # semana 1 · oficina
        ["T2", "T2", "T2", "T2", "T2", "T2", "T2"],   # semana 2 · turno 2
        ["T3", "T3", "T3", "T3", "T3", "T3", "T3"],   # semana 3 · turno 3
        ["T1", "T1", "T1", "T1", "T1", "T1", "T1"],   # semana 4 · turno 1
        ["D", "D", "D", "D", "D", "D", "D"],          # semana 5 · descanso
    ]
    return [c for wk in semanas for c in wk]


def cobertura_default() -> dict:
    base = {pu: 1 for pu in PUESTOS}
    mk = lambda: {tn: dict(base) for tn in ("T1", "T2", "T3")}
    return {k: mk() for k, _ in DIA_TIPO}


def config_default() -> dict:
    return {
        "regimen": {
            "nSem": 5,
            "bloqueDow": 1,  # cada semana del ciclo inicia el lunes
            "patron": patron_default(),
            # Reglas fijas: 1 turno por día y descanso mínimo de 8 h entre turnos.
            # Con 8 h la única transición prohibida al día siguiente es T1->T2.
            "reglas": {
                "unoPorDia": True,
                "minDescansoHoras": DESCANSO_MIN_HORAS,
            },
        },
        "feriados": [],          # [{fecha, nombre}]
        "ausencias": [],         # [{id, personaId, tipo, desde, hasta, estado}]
        "ausenciasCfg": {"bloqPend": True},
        "forzados": [],          # [{id, tipo:'OI_PERM'|'DIA', personaId, fecha?, cod?}]
        "prioridad": [],         # [personaId] en orden de jerarquía (1º manda)
        "cobertura": cobertura_default(),
        "overrides": {},         # "personaId|YYYY-MM-DD" -> "COD"
        "costos": {"fDesc": None, "fFer": None, "fNoc": None},
        "ui": {"mesOficial": "2026-08", "mesesRef": 2},
    }


def feriados_peru_2026() -> list[dict]:
    F = [
        ("2026-01-01", "Año Nuevo"),
        ("2026-04-02", "Jueves Santo"),
        ("2026-04-03", "Viernes Santo"),
        ("2026-05-01", "Día del Trabajo"),
        ("2026-06-07", "Batalla de Arica y Día de la Bandera"),
        ("2026-06-29", "San Pedro y San Pablo"),
        ("2026-07-23", "Día de la Fuerza Aérea"),
        ("2026-07-28", "Fiestas Patrias"),
        ("2026-07-29", "Fiestas Patrias"),
        ("2026-08-06", "Batalla de Junín"),
        ("2026-08-30", "Santa Rosa de Lima"),
        ("2026-10-08", "Combate de Angamos"),
        ("2026-11-01", "Todos los Santos"),
        ("2026-12-08", "Inmaculada Concepción"),
        ("2026-12-09", "Batalla de Ayacucho"),
        ("2026-12-25", "Navidad"),
    ]
    return [{"fecha": f, "nombre": n} for f, n in F]


def operadores_ejemplo() -> list[dict]:
    """Plantilla de ejemplo de RDT_agent, con los campos nuevos ya poblados."""
    base = [
        ("Carlos Pérez", ["C", "ET", "EF", "A"], 1),
        ("Ana Gómez", ["ET", "EF", "A"], 2),
        ("Luis Torres", ["EF", "A"], 3),
        ("María Ruiz", ["A"], 4),
        ("Jorge Díaz", ["C", "ET"], 5),
        ("Sofía Castro", ["ET", "EF", "A"], 1),
    ]
    return [
        {
            "Nombre": n,
            "Roles Habilitados": roles,
            "Semana Ciclo": sem,
            "Costo Turno": 50,
            "Fecha Base": "",
            "Activo": True,
        }
        for n, roles, sem in base
    ]


# --------------------------------------------------------------------------- #
#  Normalización de operadores                                                 #
# --------------------------------------------------------------------------- #

def habil_default(cargo_o_rol: str) -> dict:
    cruce = {
        "Especialista Tensión": ["Especialista Frecuencia"],
        "Especialista Frecuencia": ["Especialista Tensión"],
    }
    rb = CARGO_ROL.get(cargo_o_rol, cargo_o_rol)
    h = {rb: True}
    for r in cruce.get(rb, []):
        h[r] = True
    return h


def _norm_operador(op: dict, lunes_ref: str) -> dict:
    roles = op.get("Roles Habilitados") or ["A"]
    habil: dict[str, bool] = {}
    for ab in roles:
        full = ABBR_INV.get(ab, ab if ab in PUESTOS else None)
        if full:
            habil[full] = True

    puesto = op.get("Puesto") or op.get("Puesto Principal")
    try:
        sb = int(op.get("Semana Ciclo", op.get("semanaBase", 1)) or 1)
    except (TypeError, ValueError):
        sb = 1
    rec = {
        "id": str(op.get("id") or op.get("Nombre") or "").strip(),
        "nombre": op.get("Nombre", "—"),
        "dni": str(op.get("DNI", "")),
        "_puesto": puesto,
        "_habil": habil,
        "costo": int(op.get("Costo Turno", op.get("costo", 50)) or 50),
        # fecha base = un lunes. Si viene vacía o inválida -> lunes de referencia.
        # Si no cae en lunes, se ajusta al lunes de esa semana.
        "fecha_base": _lunes_de_safe(op.get("Fecha Base") or op.get("fechaBase"))
                      or _lunes_de_safe(lunes_ref) or lunes_ref,
        "semana_base": sb,
        "activo": bool(op.get("Activo", op.get("activo", True))),
    }
    if not rec["_habil"]:
        rec["_habil"] = habil_default(rol_base(rec))
    return rec


def rol_base(p: dict) -> str:
    cargo = p.get("_puesto")
    if cargo in CARGO_ROL:
        return CARGO_ROL[cargo]
    if cargo in PUESTOS:
        return cargo
    for pu in JERARQUIA:
        if p["_habil"].get(pu):
            return pu
    return "Analista"


def familia(rol: str) -> str:
    return FAMILIA.get(rol, rol)


# --------------------------------------------------------------------------- #
#  Régimen y códigos                                                           #
# --------------------------------------------------------------------------- #

def prohibidas(min_horas: int) -> list[tuple[str, str]]:
    T = ["T1", "T2", "T3"]
    out = []
    for a in T:
        for b in T:
            fin_a = TURNO_H[a]["fin"]
            ini_b = TURNO_H[b]["ini"] + 24
            if ini_b - fin_a < min_horas:
                out.append((a, b))
    return out


def _codigo_regimen(
    p: dict, fecha: str, n_sem: int, bd: int, patron: list[str]
) -> tuple[str, int, bool]:
    d = _parse(fecha)
    pos = (_js_dow(d) - bd + 7) % 7
    b_start = _add_days(d, -pos)
    bref = _parse(p["fecha_base"])
    bref_start = _add_days(bref, -((_js_dow(bref) - bd + 7) % 7))
    semanas = round(_diff_days(b_start, bref_start) / 7)
    sb = p["semana_base"] or 1
    fase = ((((sb - 1) + semanas) % n_sem) + n_sem) % n_sem
    wk = patron[fase * 7 : fase * 7 + 7]
    base = wk[pos] if pos < len(wk) else "D"
    descanso_sem = wk.count("D") >= 6
    return base, fase, descanso_sem


def _code_for(p: dict, base: str, turno_forzado: str | None = None) -> str:
    if base == "D":
        return "D"
    if base == "OI" and not turno_forzado:
        return "OI"
    t = turno_forzado or base
    return (ABBR.get(rol_base(p), "?")) + TURNO_NUM[t]


_RE_TURNO = re.compile(r"([123])$")


def parse_code(cod: str | None) -> dict:
    if not cod or cod == "D":
        return {"tipo": "D"}
    if cod == "OI":
        return {"tipo": "OI"}
    m = _RE_TURNO.search(cod)
    if m:
        return {"tipo": "T", "turno": "T" + m.group(1)}
    return {"tipo": "OTRO"}


def tipo_dia(fecha: str, fer_set: set[str]) -> str:
    if fecha in fer_set:
        return "FER"
    g = _js_dow(_parse(fecha))
    if g == 0:
        return "DOM"
    if g == 6:
        return "SAB"
    return "LV"


# --------------------------------------------------------------------------- #
#  Prioridad                                                                   #
# --------------------------------------------------------------------------- #

def _rol_rank(rol: str) -> int:
    try:
        return JERARQUIA.index(rol)
    except ValueError:
        return 99


def sinc_prioridad(prioridad: list[str], pers: list[dict]) -> list[str]:
    activos = [p["id"] for p in pers]
    aset = set(activos)
    orden = [i for i in (prioridad or []) if i in aset]
    faltan = [p for p in pers if p["id"] not in orden]
    faltan.sort(key=lambda p: (_rol_rank(rol_base(p)), (p["nombre"] or "").lower()))
    orden.extend(p["id"] for p in faltan)
    return orden


# --------------------------------------------------------------------------- #
#  Anclaje del ciclo (fecha base lunes + semana base)                          #
# --------------------------------------------------------------------------- #

def anclaje(operadores: list[dict], config: dict,
            mes_oficial: str | None = None) -> dict:
    """Explica cómo queda anclado cada operador en el ciclo.

    Para cada operador devuelve:
      * ``fecha_base_ingresada`` — lo que se guardó (o vacío).
      * ``era_lunes`` — si el valor ingresado ya caía en lunes.
      * ``lunes_base`` — el lunes efectivo que usa el motor (ajustado).
      * ``semana_base`` — la semana del ciclo declarada para ese lunes.
      * ``semana_en_1er_lunes`` — en qué semana del ciclo (1..N) cae ese
        operador el primer lunes del mes oficial, propagando el régimen.
      * ``turno_1er_lunes`` — el código de régimen ese lunes (OI/T1/T2/T3/D).

    Sirve para verificar a ojo que el rol arranca donde debe.
    """
    reg = config["regimen"]
    n_sem = int(reg.get("nSem", 5))
    bd = int(reg.get("bloqueDow", 1))
    patron = reg["patron"]
    mes_oficial = mes_oficial or config.get("ui", {}).get("mesOficial", "2026-08")
    lref = _lunes_ref(mes_oficial)

    filas = []
    for o in operadores:
        activo = bool(o.get("Activo", o.get("activo", True)))
        p = _norm_operador(o, lref)
        ingresada = str(o.get("Fecha Base") or o.get("fechaBase") or "").strip()
        base, fase, _ds = _codigo_regimen(p, lref, n_sem, bd, patron)
        filas.append({
            "operador": p["nombre"],
            "activo": activo,
            "fecha_base_ingresada": ingresada or "(vacía)",
            "era_lunes": es_lunes(ingresada) if ingresada else None,
            "lunes_base": p["fecha_base"],
            "semana_base": p["semana_base"],
            "semana_en_1er_lunes": fase + 1,
            "turno_1er_lunes": base,
        })
    return {"primer_lunes_mes_oficial": lref, "operadores": filas}


# --------------------------------------------------------------------------- #
#  MOTOR                                                                       #
# --------------------------------------------------------------------------- #

def generar_rol(
    operadores: list[dict],
    config: dict,
    mes_oficial: str | None = None,
    meses_ref: int | None = None,
    optimizar_oi: bool = True,
    cubrir_con_descanso: bool = True,
) -> dict:
    """Genera el rol completo de forma determinista.

    Devuelve un dict con:
      ``meses``, ``operadores``, ``asig`` (id -> fecha -> celda),
      ``grillas`` (ym -> {fechas, filas}), ``cobertura`` (fecha -> turno -> puesto),
      ``errores`` ([{tipo:'e'|'w', f, txt}]), ``feriados``, ``prioridad``.
    """
    reg = config["regimen"]
    n_sem = int(reg.get("nSem", 5))
    bd = int(reg.get("bloqueDow", 1))
    patron = reg["patron"]
    # Regla fija: descanso mínimo de 8 h (se ignora lo que traiga el config
    # guardado, para no arrastrar valores viejos).
    min_h = DESCANSO_MIN_HORAS

    cob = config["cobertura"]
    ui = config.get("ui", {})
    mes_oficial = mes_oficial or ui.get("mesOficial", "2026-08")
    meses_ref = ui.get("mesesRef", 2) if meses_ref is None else int(meses_ref)

    lunes_ref = _lunes_ref(mes_oficial)
    pers = [_norm_operador(o, lunes_ref) for o in operadores
            if bool(o.get("Activo", o.get("activo", True)))]
    prioridad = sinc_prioridad(config.get("prioridad", []), pers)
    prio_idx = {pid: i for i, pid in enumerate(prioridad)}
    prio_de = lambda p: prio_idx.get(p["id"], 9999)
    by_id = {p["id"]: p for p in pers}

    fer_set = {f["fecha"] for f in config.get("feriados", [])}
    meses = _month_list(mes_oficial, meses_ref)
    all_fechas: list[str] = []
    for ym in meses:
        for d in range(1, _month_days(ym) + 1):
            all_fechas.append(f"{ym}-{d:02d}")

    proh = set(prohibidas(min_h))
    is_proh = lambda a, b: (a, b) in proh

    errores: list[dict] = []

    # 1) asignación base por régimen -------------------------------------------------
    asig: dict[str, dict[str, dict]] = {}
    for p in pers:
        asig[p["id"]] = {}
        for f in all_fechas:
            base, _fase, dsem = _codigo_regimen(p, f, n_sem, bd, patron)
            asig[p["id"]][f] = {
                "base": base,
                "cod": _code_for(p, base),
                "fuera": False,
                "descansoSem": dsem,
            }

    # 1.5) ausencias ---------------------------------------------------------------
    bloq_pend = config.get("ausenciasCfg", {}).get("bloqPend", True)
    for au in config.get("ausencias", []):
        a = asig.get(au["personaId"])
        if a is None:
            continue
        if au.get("estado") != "Aprobada" and not bloq_pend:
            continue
        cod = TIPO_AUS.get(au["tipo"], {}).get("cod", "V")
        x, h = _parse(au["desde"]), _parse(au.get("hasta") or au["desde"])
        while x <= h:
            f = _ymd(x)
            if f in a:
                a[f]["cod"] = cod
                a[f]["ausencia"] = au.get("estado", "Aprobada")
                a[f]["ausTipo"] = au["tipo"]
            x = _add_days(x, 1)

    # 1.7) forzados --------------------------------------------------------------
    for r in config.get("forzados", []):
        a = asig.get(r["personaId"])
        per = by_id.get(r["personaId"])
        if a is None or per is None:
            continue
        if r["tipo"] == "OI_PERM":
            for f in all_fechas:
                cell = a.get(f)
                if not cell or cell.get("ausencia") or cell["descansoSem"]:
                    continue
                dow = _js_dow(_parse(f))
                if dow in (0, 6):
                    continue  # fin de semana: régimen natural
                cell["cod"] = "OI"
                cell["forzado"] = True
                cell["oiPerm"] = True
                cell.pop("spillOI", None)
        elif r["tipo"] == "DIA":
            # acepta un día (`fecha`) o un rango (`desde`/`hasta`)
            desde = r.get("desde") or r.get("fecha")
            hasta = r.get("hasta") or r.get("fecha") or desde
            if not desde:
                continue
            c = r.get("cod") or "OI"
            if c in ("T1", "T2", "T3"):
                c = (ABBR.get(rol_base(per), "?")) + TURNO_NUM[c]
            try:
                x, h = _parse(desde), _parse(hasta)
            except Exception:
                continue
            while x <= h:
                cell = a.get(_ymd(x))
                x = _add_days(x, 1)
                if not cell:
                    continue
                cell["cod"] = c
                cell["forzado"] = True
                cell.pop("ausencia", None)
                cell.pop("spillOI", None)

    # 2) overrides manuales -----------------------------------------------------
    for k, v in config.get("overrides", {}).items():
        pid, _, f = k.partition("|")
        if pid in asig and f in asig[pid]:
            asig[pid][f]["cod"] = v
            asig[pid][f]["manual"] = True

    # ---- helpers dependientes de la asignación -------------------------------
    def turno_de(pid: str, f: str) -> str | None:
        cell = asig[pid].get(f)
        return parse_code(cell["cod"]).get("turno") if cell else None

    def viola_secuencia(pid: str, f: str, turno: str) -> bool:
        prev = _ymd(_add_days(_parse(f), -1))
        nxt = _ymd(_add_days(_parse(f), 1))
        tp, tn = turno_de(pid, prev), turno_de(pid, nxt)
        if tp and is_proh(tp, turno):
            return True
        if tn and is_proh(turno, tn):
            return True
        return False

    def ef_puesto(p: dict, f: str) -> str:
        return asig[p["id"]][f].get("puestoCubierto") or rol_base(p)

    def turno_info(f: str, tn: str) -> tuple[int, set[str]]:
        roles: set[str] = set()
        count = 0
        for p in pers:
            a = asig[p["id"]][f]
            c = parse_code(a["cod"])
            if c["tipo"] == "T" and c.get("turno") == tn:
                count += 1
                roles.add(a.get("puestoCubierto") or rol_base(p))
        return count, roles

    def en_turno_rol(f: str, tn: str, pu: str) -> list[dict]:
        out = []
        for p in pers:
            c = parse_code(asig[p["id"]][f]["cod"])
            if c["tipo"] == "T" and c.get("turno") == tn and ef_puesto(p, f) == pu:
                out.append(p)
        return out

    # 3) cobertura por fecha y turno ------------------------------------------
    #    Regla: TODO mínimo >= 1 del módulo de cobertura es OBLIGATORIO y el
    #    motor recurre a lo que haga falta para cumplirlo (personal en OI y,
    #    si no alcanza, horas extra de personal en descanso). Los mínimos en 0
    #    son sólo un objetivo blando (se intenta 1 con gente de OI, sin error).
    #    Se asigna en orden de JERARQUIA de roles (C, ET, EF, A): para cada rol
    #    se elige al operador de mayor jerarquía (posición en el módulo de
    #    operadores) que lo pueda cubrir. PRIO_TURNO decide qué turno cede
    #    cuando el personal no alcanza.
    cob_resumen: dict[str, dict] = {}
    for f in all_fechas:
        td = tipo_dia(f, fer_set)
        cob_resumen[f] = {}

        # 3.0) DEMOTAR excedentes: máx. 1 por puesto en un turno (regla dura)
        for tn in ("T1", "T2", "T3"):
            for pu in PUESTOS:
                dentro = [
                    p for p in en_turno_rol(f, tn, pu)
                    if not asig[p["id"]][f].get("forzado")
                    and not asig[p["id"]][f].get("manual")
                    and not asig[p["id"]][f].get("fuera")
                ]
                dentro.sort(key=lambda p: (-prio_de(p), -p["costo"]))  # menor jerarquía 1º
                sobra = len(dentro) - 1
                for p in dentro:
                    if sobra <= 0:
                        break
                    lateral = None
                    for pu2 in JERARQUIA:
                        if pu2 == pu or not p["_habil"].get(pu2):
                            continue
                        obj2 = max(cob[td][tn].get(pu2, 0), 1)
                        if len(en_turno_rol(f, tn, pu2)) < obj2:
                            lateral = pu2
                            break
                    a = asig[p["id"]][f]
                    if lateral:
                        a["cod"] = (ABBR.get(lateral, "?")) + TURNO_NUM[tn]
                        a["puestoCubierto"] = lateral
                        a["lateral"] = True
                        a.pop("spillOI", None)
                    else:
                        a["cod"] = "OI"
                        a["spillOI"] = True
                        a.pop("puestoCubierto", None)
                    sobra -= 1

        def prescindible(p: dict) -> bool:
            """¿Se le puede mover a otro turno sin romper nada importante?"""
            a = asig[p["id"]][f]
            if (a.get("forzado") or a.get("manual") or a.get("fuera")
                    or a.get("descansoSem") or a.get("oiPerm")):
                return False
            if a.get("spillOI"):
                return True
            c = parse_code(a["cod"])
            if c["tipo"] == "T":
                # Respetar el régimen: si está en el turno que le toca por
                # régimen, NO se le mueve para tapar otro turno.
                if a["base"] == c["turno"]:
                    return False
                rol = a.get("puestoCubierto") or rol_base(p)
                # está fuera de su turno de régimen y cubriendo un slot no
                # obligatorio -> se puede reubicar en uno que sí lo sea.
                return (cob[td][c["turno"]].get(rol, 0)) == 0
            return False

        def llenar(tn: str, pu: str, objetivo: int, extra: bool) -> None:
            have = len(en_turno_rol(f, tn, pu))

            # (1) gente en su semana de OI (o spill) — por jerarquía y luego costo.
            #     Vale para cualquier turno, T1 incluido.
            if have < objetivo and optimizar_oi:
                cand = [
                    p for p in pers
                    if parse_code(asig[p["id"]][f]["cod"])["tipo"] == "OI"
                    and not asig[p["id"]][f].get("descansoSem")
                    and not asig[p["id"]][f].get("forzado")
                    and p["_habil"].get(pu)
                    and not viola_secuencia(p["id"], f, tn)
                ]
                cand.sort(key=lambda p: (
                    0 if asig[p["id"]][f]["base"] == "OI" else 1,
                    prio_de(p), p["costo"]))
                for p in cand:
                    if have >= objetivo:
                        break
                    cnt, roles = turno_info(f, tn)
                    if cnt >= MAX_TURNO or pu in roles:
                        break
                    a = asig[p["id"]][f]
                    a["cod"] = (ABBR.get(pu, "?")) + TURNO_NUM[tn]
                    a["optOI"] = True
                    a["puestoCubierto"] = pu
                    a.pop("spillOI", None)
                    have += 1

            # (2) antes de horas extra: mover a quien hace algo prescindible
            if have < objetivo and extra:
                cand = [
                    p for p in pers
                    if prescindible(p) and p["_habil"].get(pu)
                    and not viola_secuencia(p["id"], f, tn)
                ]
                cand.sort(key=lambda p: (prio_de(p), p["costo"]))
                for p in cand:
                    if have >= objetivo:
                        break
                    cnt, roles = turno_info(f, tn)
                    if cnt >= MAX_TURNO or pu in roles:
                        break
                    a = asig[p["id"]][f]
                    a["cod"] = (ABBR.get(pu, "?")) + TURNO_NUM[tn]
                    a["puestoCubierto"] = pu
                    a["reasignado"] = True
                    for k in ("lateral", "spillOI", "optOI"):
                        a.pop(k, None)
                    have += 1

            # (3) horas extra: personal en descanso -> fuera de régimen (sobretasa)
            if have < objetivo and extra and cubrir_con_descanso:
                cand = [
                    p for p in pers
                    if parse_code(asig[p["id"]][f]["cod"])["tipo"] == "D"
                    and not asig[p["id"]][f].get("descansoSem")
                    and not asig[p["id"]][f].get("forzado")
                    and p["_habil"].get(pu)
                    and not viola_secuencia(p["id"], f, tn)
                ]
                cand.sort(key=lambda p: (prio_de(p), p["costo"]))
                for p in cand:
                    if have >= objetivo:
                        break
                    cnt, roles = turno_info(f, tn)
                    if cnt >= MAX_TURNO or pu in roles:
                        break
                    a = asig[p["id"]][f]
                    a["cod"] = (ABBR.get(pu, "?")) + TURNO_NUM[tn]
                    a["fuera"] = True
                    a["puestoCubierto"] = pu
                    have += 1

        # PASO A: todos los mínimos >= 1 son OBLIGATORIOS -> cubrir con lo que
        #         haga falta (OI y, si no alcanza, horas extra).
        for tn in PRIO_TURNO:
            for pu in JERARQUIA:
                req = cob[td][tn].get(pu, 0)
                if req > 0:
                    llenar(tn, pu, req, extra=cubrir_con_descanso)
        # PASO B: objetivo blando donde el mínimo es 0 -> intentar 1 sólo con
        #         gente de OI (sin horas extra, sin marcar error).
        for tn in PRIO_TURNO:
            for pu in JERARQUIA:
                if cob[td][tn].get(pu, 0) == 0:
                    llenar(tn, pu, 1, extra=False)

        # PASO C: intercambios por jerarquía dentro de cada turno. Si alguien de
        #         mayor jerarquía cubre un rol más bajo que otro de menor
        #         jerarquía del mismo turno, y ambos pueden cubrir el rol del
        #         otro, se intercambian (el senior se queda el rol más alto).
        for tn in ("T1", "T2", "T3"):
            for _ in range(len(pers)):  # tope de iteraciones
                hecho = False
                en_tn = [p for p in pers
                         if parse_code(asig[p["id"]][f]["cod"]).get("turno") == tn
                         and not asig[p["id"]][f].get("forzado")
                         and not asig[p["id"]][f].get("manual")]
                for pa in en_tn:
                    ra = asig[pa["id"]][f].get("puestoCubierto") or rol_base(pa)
                    if ra not in JERARQUIA:
                        continue
                    for pb in en_tn:
                        rb = asig[pb["id"]][f].get("puestoCubierto") or rol_base(pb)
                        if rb not in JERARQUIA or pa is pb:
                            continue
                        if (prio_de(pa) < prio_de(pb)
                                and JERARQUIA.index(ra) > JERARQUIA.index(rb)
                                and pa["_habil"].get(rb)
                                and pb["_habil"].get(ra)):
                            asig[pa["id"]][f]["cod"] = ABBR[rb] + TURNO_NUM[tn]
                            asig[pa["id"]][f]["puestoCubierto"] = rb
                            asig[pb["id"]][f]["cod"] = ABBR[ra] + TURNO_NUM[tn]
                            asig[pb["id"]][f]["puestoCubierto"] = ra
                            hecho = True
                            break
                    if hecho:
                        break
                if not hecho:
                    break

        # registrar cobertura y déficits (todo mínimo incumplido = incumplimiento)
        for tn in PRIO_TURNO:
            cob_resumen[f][tn] = {}
            for pu in JERARQUIA:
                req = cob[td][tn].get(pu, 0)
                have = len(en_turno_rol(f, tn, pu))
                cob_resumen[f][tn][pu] = {"req": req, "have": have,
                                          "obligatorio": req > 0}
                if have < req:
                    errores.append({
                        "tipo": "e", "f": f,
                        "txt": f"{f} {tn} {pu}: hay {have}, mínimo {req}",
                    })

    # 4) validación de secuencia y semana de descanso -------------------------
    for p in pers:
        for f in all_fechas:
            t = turno_de(p["id"], f)
            if not t:
                continue
            prev = _ymd(_add_days(_parse(f), -1))
            tp = turno_de(p["id"], prev)
            if tp and is_proh(tp, t):
                errores.append({
                    "tipo": "e", "f": f,
                    "txt": f"{p['nombre']}: {tp}({prev}) → {t}({f}) sin descanso mínimo",
                })
            c = parse_code(asig[p["id"]][f]["cod"])
            if c["tipo"] == "T" and not p["_habil"].get(rol_base(p)):
                errores.append({
                    "tipo": "w", "f": f,
                    "txt": f"{p['nombre']}: no habilitado para su rol base ({rol_base(p)})",
                })
            if c["tipo"] == "T" and asig[p["id"]][f].get("descansoSem"):
                errores.append({
                    "tipo": "w", "f": f,
                    "txt": f"{p['nombre']}: turno {t} en su SEMANA DE DESCANSO ({f}) "
                           "— semana Lun–Dom intocable",
                })

    # 5) reglas duras del turno (agregado) ----------------------------------
    for tn in ("T1", "T2", "T3"):
        dias4 = 0
        max_tot = 0
        dup_rol: dict[str, int] = {}
        for f in all_fechas:
            by_role: dict[str, int] = {}
            for p in pers:
                a = asig[p["id"]][f]
                c = parse_code(a["cod"])
                if c["tipo"] == "T" and c.get("turno") == tn:
                    rol = a.get("puestoCubierto") or rol_base(p)
                    by_role[rol] = by_role.get(rol, 0) + 1
            total = sum(by_role.values())
            if total > MAX_TURNO:
                dias4 += 1
                max_tot = max(max_tot, total)
            for rol, n in by_role.items():
                if n > 1:
                    dup_rol[rol] = max(dup_rol.get(rol, 0), n)
        if dias4:
            errores.append({
                "tipo": "e", "f": meses[0] + "-01",
                "txt": f"{tn}: más de {MAX_TURNO} personas en el turno en {dias4} "
                       f"día(s) (hasta {max_tot}) — revisa forzados / celdas manuales.",
            })
        for rol, n in dup_rol.items():
            errores.append({
                "tipo": "e", "f": meses[0] + "-01",
                "txt": f"{tn}: hasta {n} {rol} en el mismo turno (máx 1) "
                       "— revisa forzados / celdas manuales.",
            })

    # empaquetar por mes ---------------------------------------------------
    grillas = {}
    for ym in meses:
        fechas = [f"{ym}-{d:02d}" for d in range(1, _month_days(ym) + 1)]
        filas = []
        for p in pers:
            filas.append({
                "id": p["id"],
                "nombre": p["nombre"],
                "dni": p["dni"],
                "puesto": p.get("_puesto") or rol_base(p),
                "celdas": {f: asig[p["id"]][f]["cod"] for f in fechas},
            })
        grillas[ym] = {"fechas": fechas, "filas": filas}

    return {
        "meses": meses,
        "operadores": [
            {"id": p["id"], "nombre": p["nombre"], "dni": p["dni"],
             "puesto": p.get("_puesto") or rol_base(p), "rol_base": rol_base(p),
             "habil": sorted(k for k, v in p["_habil"].items() if v),
             "fecha_base": p["fecha_base"], "semana_base": p["semana_base"]}
            for p in pers
        ],
        "asig": asig,
        "grillas": grillas,
        "cobertura": cob_resumen,
        "errores": errores,
        "feriados": sorted(fer_set),
        "prioridad": prioridad,
    }


# --------------------------------------------------------------------------- #
#  Diagnóstico: ¿por qué (no) hay X en el turno Y el día Z?                     #
# --------------------------------------------------------------------------- #

def diagnostico_slot(rol: dict, config: dict, fecha: str, turno: str,
                     puesto: str) -> dict:
    """Explica, operador por operador, por qué un puesto está o no cubierto en
    un turno concreto de un día concreto del rol ya generado."""
    turno = turno.upper()
    if puesto not in PUESTOS:
        # aceptar abreviaturas
        puesto = ABBR_INV.get(puesto.upper(), puesto)
    reg = config["regimen"]
    n_sem = int(reg.get("nSem", 5))
    bd = int(reg.get("bloqueDow", 1))
    patron = reg["patron"]
    fer_set = set(rol.get("feriados", []))
    td = tipo_dia(fecha, fer_set)
    req = config["cobertura"].get(td, {}).get(turno, {}).get(puesto, 0)
    resumen_slot = rol["cobertura"].get(fecha, {}).get(turno, {}).get(puesto, {})
    have = resumen_slot.get("have", 0)
    obligatorio = req > 0

    filas = []
    for op in rol["operadores"]:
        if puesto not in op.get("habil", []):
            continue
        cell = rol["asig"].get(op["id"], {}).get(fecha)
        if not cell:
            continue
        base, fase, dsem = _codigo_regimen(
            {"fecha_base": op["fecha_base"], "semana_base": op["semana_base"]},
            fecha, n_sem, bd, patron)
        pc = parse_code(cell["cod"])
        cubierto_por = cell.get("puestoCubierto") or op["rol_base"]
        reg_turno = base if base in ("T1", "T2", "T3") else None

        if pc["tipo"] == "T" and pc.get("turno") == turno and cubierto_por == puesto:
            motivo = "✅ CUBRE este slot"
        elif cell.get("ausencia"):
            lbl = TIPO_AUS.get(cell.get("ausTipo"), {}).get("label", "ausencia")
            motivo = f"ausente ({lbl}, {cell.get('ausencia')})"
        elif dsem:
            motivo = "en su SEMANA DE DESCANSO (Lun–Dom intocable)"
        elif cell.get("oiPerm"):
            motivo = "forzado a OI permanente (Lun–Vie)"
        elif cell.get("forzado"):
            motivo = f"forzado a {cell['cod']}"
        elif pc["tipo"] == "T" and pc.get("turno") == turno:
            if (JERARQUIA.index(cubierto_por) < JERARQUIA.index(puesto)
                    and not cell.get("lateral") and not cell.get("reasignado")):
                motivo = (f"está en {turno} pero cubre {cubierto_por}, un rol de "
                          f"mayor jerarquía que {puesto} (sólo puede cubrir uno)")
            else:
                motivo = (f"está en {turno} cubriendo {cubierto_por} "
                          f"(se le movió de {puesto})")
        elif reg_turno == turno and cell.get("spillOI"):
            motivo = (f"el régimen lo puso en {turno} pero el puesto {puesto} "
                      "ya estaba cubierto por alguien de mayor jerarquía → pasó a OI")
        elif pc["tipo"] == "T":
            if reg_turno == pc["turno"]:
                motivo = f"el régimen lo tiene en {pc['turno']} ese día"
            else:
                origen = {"OI": "OI", "D": "descanso"}.get(base, base)
                motivo = f"cubriendo {pc['turno']} (su régimen ese día era {origen})"
        elif pc["tipo"] == "OI":
            _proh = set(prohibidas(DESCANSO_MIN_HORAS))
            _tp = parse_code(rol["asig"][op["id"]].get(
                _ymd(_add_days(_parse(fecha), -1)), {}).get("cod", "")).get("turno")
            _tn = parse_code(rol["asig"][op["id"]].get(
                _ymd(_add_days(_parse(fecha), 1)), {}).get("cod", "")).get("turno")
            if _tp and (_tp, turno) in _proh:
                motivo = (f"en OI, pero hizo {_tp} el día anterior → no puede "
                          f"encadenar {turno} (descanso mínimo)")
            elif _tn and (turno, _tn) in _proh:
                motivo = (f"en OI, pero hace {_tn} al día siguiente → no puede "
                          f"encadenar {turno} (descanso mínimo)")
            else:
                motivo = "en OI, disponible (no se necesitó o hay prioridad mayor)"
        elif pc["tipo"] == "D":
            motivo = "en descanso ese día"
            motivo += (" — el motor sólo lo usaría con horas extra si el slot es"
                       " obligatorio y está activado «cubrir con personal en"
                       " descanso»") if obligatorio else \
                      " — no se toca porque este slot no es obligatorio (mínimo 0)"
        else:
            motivo = cell["cod"]

        filas.append({
            "operador": op["nombre"],
            "roles": op["habil"],
            "regimen_semana": fase + 1,
            "regimen_turno": base,
            "codigo_final": cell["cod"],
            "motivo": motivo,
        })

    if not obligatorio:
        nota = ("Este slot NO es obligatorio (mínimo 0 en el módulo de"
                " cobertura): el motor sólo intenta poner 1 con personal de OI"
                " y no marca error si no lo logra. Súbelo a 1 para exigirlo.")
    elif have >= req:
        nota = None
    else:
        nota = ("Slot OBLIGATORIO sin cubrir. El motor ya intentó régimen + OI"
                " + horas extra. Los motivos de arriba explican por qué no"
                " alcanzó: si todos están en descanso, activa «cubrir faltantes"
                " con personal en descanso»; si es cosa del régimen o del"
                " anclaje, ajústalo; si no hay personal con ese rol, habilítalo"
                " en más operadores.")

    return {
        "fecha": fecha,
        "dia": DIAS[_js_dow(_parse(fecha))],
        "tipo_dia": td,
        "turno": turno,
        "puesto": puesto,
        "obligatorio": obligatorio,
        "requerido": req,
        "asignados": have,
        "cumple": have >= req,
        "candidatos": filas,
        "nota": nota,
    }


# --------------------------------------------------------------------------- #
#  Salidas legibles                                                            #
# --------------------------------------------------------------------------- #

def grilla_markdown(rol: dict, ym: str | None = None) -> str:
    ym = ym or rol["meses"][0]
    g = rol["grillas"][ym]
    fechas = g["fechas"]
    fer = set(rol["feriados"])
    cab = ["Operador"] + [
        f"{DIAS[_js_dow(_parse(f))]}{_parse(f).day}" + ("*" if f in fer else "")
        for f in fechas
    ]
    lineas = ["| " + " | ".join(cab) + " |",
              "|" + "|".join(["---"] * len(cab)) + "|"]
    for fila in g["filas"]:
        celdas = [fila["nombre"]] + [fila["celdas"][f] or "" for f in fechas]
        lineas.append("| " + " | ".join(celdas) + " |")
    return "\n".join(lineas)


def resumen(rol: dict) -> dict:
    errs = [e for e in rol["errores"] if e["tipo"] == "e"]
    warns = [e for e in rol["errores"] if e["tipo"] == "w"]
    fuera = 0
    por_operador = {}
    for pid, dias in rol["asig"].items():
        c = {"turnos": 0, "OI": 0, "D": 0, "fuera": 0, "ausencia": 0}
        for cell in dias.values():
            pc = parse_code(cell["cod"])
            if pc["tipo"] == "T":
                c["turnos"] += 1
            elif pc["tipo"] == "OI":
                c["OI"] += 1
            elif pc["tipo"] == "D":
                c["D"] += 1
            else:
                c["ausencia"] += 1
            if cell.get("fuera"):
                c["fuera"] += 1
                fuera += 1
        por_operador[pid] = c
    return {
        "meses": rol["meses"],
        "incumplimientos": len(errs),
        "advertencias": len(warns),
        "turnos_fuera_de_regimen": fuera,
        "detalle_incumplimientos": [e["txt"] for e in errs[:60]],
        "detalle_advertencias": [e["txt"] for e in warns[:60]],
        "por_operador": por_operador,
    }


def calcular_costos(rol: dict, operadores: list[dict], costos: dict) -> dict:
    fer = set(rol["feriados"])
    f_desc, f_fer, f_noc = costos.get("fDesc"), costos.get("fFer"), costos.get("fNoc")
    faltan = False
    lunes_ref = _lunes_ref(rol["meses"][0])
    normal = {o["Nombre"] if "Nombre" in o else o.get("nombre"): _norm_operador(o, lunes_ref)
              for o in operadores}
    filas = []
    tot_base = tot_extra = 0.0
    for op in rol["operadores"]:
        p = normal.get(op["nombre"])
        costo = p["costo"] if p else 50
        tb = tf = 0
        cb = cx = 0.0
        for f, cell in rol["asig"].get(op["id"], {}).items():
            c = parse_code(cell["cod"])
            if c["tipo"] != "T":
                continue
            if cell.get("fuera"):
                tf += 1
                base = f_fer if f in fer else f_desc
                if base is None:
                    faltan = True
                    base = 1
                fac = base
                if c["turno"] == "T1":
                    if f_noc is None:
                        faltan = True
                    else:
                        fac *= f_noc
                cx += costo * fac
            else:
                tb += 1
                cb += costo
        tot_base += cb
        tot_extra += cx
        filas.append({
            "operador": op["nombre"], "puesto": op["puesto"], "costo_turno": costo,
            "turnos_regimen": tb, "costo_base": round(cb),
            "turnos_fuera": tf, "costo_sobretasa": round(cx),
            "costo_total": round(cb + cx),
        })
    return {
        "faltan_factores": faltan,
        "costo_total": round(tot_base + tot_extra),
        "costo_base": round(tot_base),
        "costo_sobretasa": round(tot_extra),
        "filas": filas,
    }


# --------------------------------------------------------------------------- #
#  Smoke test                                                                  #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    cfg = config_default()
    cfg["feriados"] = feriados_peru_2026()
    ops = operadores_ejemplo()
    rol = generar_rol(ops, cfg, mes_oficial="2026-08", meses_ref=1)
    r = resumen(rol)
    print("Meses:", r["meses"])
    print("Incumplimientos:", r["incumplimientos"], "| Advertencias:", r["advertencias"])
    print("Turnos fuera de régimen:", r["turnos_fuera_de_regimen"])
    print()
    print(grilla_markdown(rol))
    print()
    for txt in r["detalle_incumplimientos"][:10]:
        print(" [x]", txt)
    for txt in r["detalle_advertencias"][:10]:
        print(" [!]", txt)
    print()
    cst = calcular_costos(rol, ops, {"fDesc": 2.0, "fFer": 2.0, "fNoc": 1.35})
    print("Costo total:", cst["costo_total"], "| base:", cst["costo_base"],
          "| sobretasa:", cst["costo_sobretasa"])
