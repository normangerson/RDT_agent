# Agente Inteligente de Turnos — Centro de Control

App Streamlit + Gemini para planificar y optimizar los turnos de un centro de
control eléctrico 24/7.

A diferencia de la versión anterior (donde el rol lo "imaginaba" el LLM), ahora
el rol lo construye un **motor determinista** portado desde la herramienta
`rol-turnos-coes.html` (proyecto *RDTLightning*). El agente Gemini **usa ese
motor como herramienta**: genera el rol, registra novedades y explica el
resultado, pero no inventa la grilla.

## Archivos

| Archivo | Qué hace |
|---|---|
| `motor_turnos.py` | Motor determinista puro (sin Streamlit/Gemini). Todos los criterios de elaboración del rol. Ejecutable como script para un smoke test: `python motor_turnos.py`. |
| `agente_turnos.py` | Envuelve el motor como *tools* de function calling para Gemini + el `system_instruction`. |
| `app.py` | Interfaz Streamlit: chat del agente + pestañas para editar todos los criterios y ver el rol generado. |
| `almacen.py` | Persistencia del estado: archivos locales o, en la nube, una rama del repo vía la API de GitHub. |
| `operadores.json` | Plantilla de operadores (se crea al primer guardado). |
| `config_rol.json` | Régimen, reglas, feriados, ausencias, forzados, prioridad y cobertura. |

## Criterios que aplica el motor

- **Régimen rotativo de 5 semanas** editable, anclado por operador
  (fecha base = un lunes + semana del ciclo en esa fecha).
- **Semana de descanso intocable** (Lun–Dom): el motor nunca la usa para cubrir.
- **Reglas de secuencia** (fijas): 1 turno por día y descanso mínimo de 8 h
  entre turnos → única transición prohibida al día siguiente: T1→T2.
- **Ausencias:** vacaciones / capacitación / permiso / licencia médica, con
  estado aprobada/solicitada.
- **Feriados:** cambian el tipo de día y activan la sobretasa.
- **Forzados:** OI permanente (Lun–Vie) o código en un día puntual.
- **Prioridad / jerarquía** entre operadores (el nº 1 manda al repartir roles).
- **Cobertura** por turno y tipo de día — **es la definición de prioridad**:
  cada mínimo ≥ 1 es **obligatorio** (cualquier puesto y turno, T1 incluido) y
  el motor recurre a régimen → personal de OI → horas extra hasta cumplirlo;
  si no lo logra es un incumplimiento (✕). Un mínimo en 0 es sólo un objetivo
  blando (se intenta 1 con gente de OI, sin error). Reglas duras: máx. 4
  personas por turno, 1 por puesto.
- **Reparto del personal escaso, escalonado:** 1º gente en su semana de OI,
  2º reasignar a quien cubre un slot no obligatorio, 3º horas extra (personal
  en descanso, fuera de régimen, con sobretasa). El orden de puestos
  (C › ET › Analista › EF) y turnos (T2 › T3 › T1) sólo desempata cuando no
  se puede cubrir todo.
- **Costos:** costo base (turnos en régimen) + sobretasa de los turnos fuera de
  régimen según factores configurables (D. Leg. 713 / D.S. 007-2002-TR).

## Herramientas expuestas al agente

`consultar_operadores`, `consultar_regimen`, `generar_rol`, `calcular_costos`,
`registrar_ausencia`, `eliminar_ausencia`, `registrar_feriado`,
`cargar_feriados_peru_2026`, `registrar_forzado_oi_permanente`,
`registrar_forzado_dia`, `quitar_forzados`, `fijar_cobertura`,
`mover_prioridad`, `fijar_regla_secuencia`.

## Uso

```bash
pip install -r requirements.txt
streamlit run app.py
```

Necesitas una API Key de Google Gemini (variable de entorno `GEMINI_API_KEY`,
`st.secrets["GEMINI_API_KEY"]` o el campo de la barra lateral) sólo para el
chat; las pestañas y el motor funcionan sin ella.

## Persistencia

| Dónde corre | Qué pasa |
|---|---|
| **Local** | `operadores.json` y `config_rol.json` se guardan junto a `app.py`. Permanente. |
| **Streamlit Cloud, sin secrets de GitHub** | Se guardan en el disco del contenedor: **efímero** (se pierde al dormir/reiniciar). |
| **Streamlit Cloud, con secrets de GitHub** | Se guardan como commits en una **rama de datos** del repo (`app-data` por defecto). Permanente y versionado. |

### Activar el guardado en GitHub

En *Manage app → Settings → Secrets* añade:

```toml
GEMINI_API_KEY = "..."
GITHUB_TOKEN = "github_pat_..."      # PAT con permiso Contents: Read and write sobre el repo
GITHUB_REPO = "normangerson/RDT_agent"
# opcionales:
# GITHUB_DATA_BRANCH = "app-data"    # rama donde se guarda el estado (no es la del deploy)
# GITHUB_DATA_PREFIX = ""            # subcarpeta dentro de esa rama
```

La app crea la rama `app-data` sola la primera vez que guarda. Esa rama **no**
debe ser la del deploy (si no, cada guardado dispara un redeploy). El estado del
almacenamiento y un botón «Guardar ahora» están en la barra lateral.

### Ejemplos de conversación

- «Genera el rol de agosto de 2026.»
- «Pon a Ana Gómez de vacaciones del 10 al 15 y recalcula.»
- «Carga los feriados de Perú 2026 y vuelve a generar.»
- «Jorge Díaz queda en OI permanente. ¿Cómo cambia la cobertura?»
- «¿Por qué hay incumplimientos en T1? ¿Qué ajusto?»

## Notas del port

- El identificador de operador es su **nombre** (la plantilla original no tenía
  IDs). Evita nombres duplicados.
- El régimen por defecto es el mismo patrón de 5 semanas que mostraba la app
  antes; ahora es editable desde la pestaña **Régimen**.
- La lógica es una traducción fiel de `regen()` del HTML original; ver
  `motor_turnos.py` para el detalle paso a paso.
