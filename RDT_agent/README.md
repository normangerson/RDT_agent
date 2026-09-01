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
| `operadores.json` | Plantilla de operadores (se crea al primer guardado). |
| `config_rol.json` | Régimen, reglas, feriados, ausencias, forzados, prioridad y cobertura. |

## Criterios que aplica el motor

- **Régimen rotativo de 5 semanas** editable, anclado por operador
  (fecha base = un lunes + semana del ciclo en esa fecha).
- **Semana de descanso intocable** (Lun–Dom): el motor nunca la usa para cubrir.
- **Reglas de secuencia:** descanso mínimo entre turnos → transiciones
  prohibidas al día siguiente; máximo de turnos T1 (nocturnos) consecutivos.
- **Ausencias:** vacaciones / capacitación / permiso / licencia médica, con
  estado aprobada/solicitada.
- **Feriados:** cambian el tipo de día y activan la sobretasa.
- **Forzados:** OI permanente (Lun–Vie) o código en un día puntual.
- **Prioridad / jerarquía** entre operadores (el nº 1 manda al repartir roles).
- **Cobertura** mínima por turno y tipo de día, con reglas duras: máx. 4
  personas por turno, 1 por puesto; objetivo blando de 1 de cada rol.
- **Reparto del personal escaso, escalonado:** 1º gente en su semana de OI,
  2º reasignar a quien hace algo prescindible, 3º horas extra (personal en
  descanso, fuera de régimen, con sobretasa). Para T1 y Especialista Frecuencia
  sólo se gastan horas extra si el usuario lo autoriza.
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
