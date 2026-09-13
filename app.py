import os
import time
import streamlit as st
import asyncio
import json
import re
import pandas as pd
from openai import OpenAI
from mcp import ClientSession
from mcp.client.sse import sse_client
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/sse")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")

# Configuración de la página
st.set_page_config(page_title="Bio-Tutor TFM", layout="wide", page_icon="🎓")

async def obtener_contexto_biometrico():
    """Conecta con Docker (MCP) para leer el estado actual (compuesto multi-señal)"""
    try:
        async with sse_client(MCP_SERVER_URL) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                resource = await session.read_resource("user://state")
                return json.loads(resource.contents[0].text)
    except Exception as e:
        return {"status": "DESCONECTADO", "rmssd": 0, "confidence": 0, "error": str(e)}

async def llamar_mcp_tool(tool_name, arguments):
    """Llama a un tool MCP (ej: get_signal_detail) y devuelve el resultado"""
    try:
        async with sse_client(MCP_SERVER_URL) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                return result.content[0].text
    except Exception as e:
        return json.dumps({"error": str(e)})

def parse_text_tool_calls(content):
    """Detecta tool calls en formato nativo de texto (fallback cuando la API no devuelve tool_calls estructurados):
    Formato 1: <function>name {args}</function>
    Formato 2: <function=name{args}</function>
    """
    if not content:
        return []
    patterns = [
        r'<function>(\w+)\s*({.*?})</function>',
        r'<function=(\w+)({.*?})</function>',
    ]
    calls = []
    for pattern in patterns:
        matches = re.findall(pattern, content, re.DOTALL)
        for name, args_str in matches:
            try:
                calls.append((name, json.loads(args_str)))
            except json.JSONDecodeError:
                pass
    return calls

def clean_function_tags(content):
    """Elimina tags <function>...</function> y <function=...>...</function> del texto"""
    if not content:
        return content
    content = re.sub(r'<function=.*?</function>', '', content, flags=re.DOTALL)
    content = re.sub(r'<function>.*?</function>', '', content, flags=re.DOTALL)
    return content.strip()

def extract_failed_tool_call(error):
    """Extrae la generación fallida de un error 400 de Groq (tool_use_failed)"""
    try:
        error_body = getattr(error, 'body', None) or {}
        if isinstance(error_body, dict):
            err = error_body.get('error', {})
            if err.get('code') == 'tool_use_failed':
                return err.get('failed_generation', '')
        error_str = str(error)
        if 'failed_generation' in error_str:
            match = re.search(r"'failed_generation':\s*'(.*?)'", error_str, re.DOTALL)
            if match:
                return match.group(1)
    except Exception:
        pass
    return None

# Herramientas disponibles para el LLM
LLM_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_signal_detail",
            "description": "Consulta métricas detalladas de una señal biométrica específica. Úsala cuando necesites más contexto fisiológico o la confianza del estado actual sea baja.",
            "parameters": {
                "type": "object",
                "properties": {
                    "signal": {
                        "type": "string",
                        "enum": ["ecg", "eda", "resp", "temp"],
                        "description": "Tipo de señal: 'ecg' (variabilidad cardíaca), 'eda' (actividad electrodérmica), 'resp' (respiración), 'temp' (temperatura cutánea)"
                    }
                },
                "required": ["signal"]
            }
        }
    }
]

# Prompts del sistema multi-agente

TRIAGE_PROMPT = """Eres un clasificador de seguridad para una plataforma educativa.
Tu ÚNICA tarea es analizar el mensaje del alumno y determinar si hay indicios de:
- Ideación suicida o pensamientos de hacerse daño
- Autolesión
- Crisis emocional grave (desesperanza extrema, despedidas)
- Petición de ayuda urgente relacionada con salud mental

NO consideres como riesgo:
- Estrés académico normal ("estoy agobiado con los exámenes")
- Frustración con ejercicios ("no me sale nada", "esto es imposible")
- Quejas generales ("odio esta asignatura")

Contexto biométrico actual del alumno: {bio_context}

Responde SOLO con un JSON válido, sin texto adicional:
{{"risk": true, "confidence": 0.85, "reason": "motivo breve"}}
o
{{"risk": false, "confidence": 0.95, "reason": "sin indicios"}}"""

EMERGENCY_PROMPT = """Eres un agente de apoyo emocional de emergencia en una plataforma educativa.
Se ha detectado que el alumno podría estar pasando por un momento muy difícil.

TU MISIÓN:
1. Responde con empatía y calidez. No juzgues.
2. Valida sus emociones: "Es normal sentirse así. No estás solo/a."
3. Proporciona SIEMPRE el recurso de ayuda:
   - Teléfono de la Esperanza / Línea de atención a la conducta suicida: 024 (España, gratuito, 24h)
   - En caso de peligro inmediato: 112
4. Anímale a hablar con alguien de confianza (familiar, amigo, profesional).
5. NO des consejos médicos ni psicológicos específicos.
6. NO actúes como terapeuta. Tu rol es de PRIMER CONTACTO y derivación.
7. Mantén un tono cálido, humano y cercano.
8. Si el alumno dice que está en peligro inmediato, insiste en llamar al 024 o al 112.

IMPORTANTE: No cambies de tema. No vuelvas a hablar de estudios. Mantente en modo apoyo."""


# Pre-filtro de palabras clave de crisis (independiente del LLM)
_CRISIS_KEYWORDS = re.compile(
    r"suicid|matarme|quitarme la vida|no quiero vivir|acabar con todo|"
    r"tirarme|cortarme|hacerme daño|no quiero seguir",
    re.IGNORECASE
)


def ejecutar_triage(client, user_message, estado_actual, confidence):
    """Clasifica el mensaje del usuario para detectar riesgo de crisis emocional.

    Diseño fail-safe: ante cualquier error (API, parseo, timeout), se asume
    riesgo positivo para evitar falsos negativos en seguridad.
    """
    # 1. Pre-filtro por palabras clave (no depende del LLM)
    if _CRISIS_KEYWORDS.search(user_message):
        return {"risk": True, "confidence": 0.99, "reason": "Keyword de crisis detectada (pre-filtro)"}

    bio_context = f"Estado: {estado_actual}, Confianza: {confidence:.0%}"
    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": TRIAGE_PROMPT.format(bio_context=bio_context)},
                {"role": "user", "content": user_message}
            ],
            temperature=0.0,
            max_tokens=100
        )
        raw = response.choices[0].message.content or ""
        # Intentar parseo directo; si falla, buscar JSON con regex
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            json_match = re.search(r'\{.*?\}', raw, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        # Si no se pudo parsear, fail-safe: asumir riesgo
        return {"risk": True, "confidence": 0.0, "reason": "Fallo de parseo — fail-safe activado"}
    except Exception as e:
        # Fail-safe: ante error de API/red, asumir riesgo
        return {"risk": True, "confidence": 0.0, "reason": f"Error triage (fail-safe): {e}"}


def generar_respuesta_emergencia(client, messages_for_llm):
    """Genera respuesta del agente de emergencia"""
    emergency_messages = [{"role": "system", "content": EMERGENCY_PROMPT}] + messages_for_llm
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=emergency_messages,
        temperature=0.3,
        max_tokens=512
    )
    return response.choices[0].message.content


def generar_prompt_adaptativo(estado, rmssd, confidence=None, signals_used=None):
    """
    Lógica de personalidades RADICAL + contexto multi-señal
    """
    base = """Eres 'BioTutor'. Tienes prohibido actuar como un asistente de IA estándar. Debes meterte en el personaje asignado al 100%.
Dispones de la herramienta 'get_signal_detail' para consultar señales biométricas detalladas (ECG, EDA, respiración). Úsala si necesitas más contexto sobre el estado fisiológico del alumno."""
    
    if confidence is not None and confidence < 0.5:
        base += "\n[AVISO: La confianza del estado actual es BAJA. Considera usar get_signal_detail para obtener más información antes de responder.]"
    
    if signals_used:
        base += f"\n[Señales activas: {', '.join(signals_used)}]"

    if 'STRESS' in estado:
        return base + f"""
        [ESTADO ALUMNO: ESTRÉS ALTO (HRV: {rmssd})]
        >>> TU PERSONALIDAD AHORA: "EL MENTOR ZEN"
        PRINCIPIO: El alumno está sobrecargado. Necesita estructura clara y acompañamiento, NO menos contenido.
        1. FORMATO: Divide tu respuesta en pasos cortos numerados (máx. 4-5 pasos). Cada paso = 1-2 frases. No uses emojis.
        2. TONO: Cálido, pausado y cercano. Frases cortas. Transmite calma sin ser vacío.
        3. ACCIÓN: Usa scaffolding — guía paso a paso desde lo concreto a lo abstracto. Empieza con un ejemplo tangible antes de la teoría.
        4. CIERRE: Termina siempre con una pregunta sencilla o una invitación a probar algo pequeño ("¿Quieres que veamos el siguiente paso?").
        5. PROHIBIDO: Respuestas de una sola frase, dar "la solución directa" sin contexto, o decir "es simple/fácil".
        6. EJEMPLO: "Vamos paso a paso, sin prisa:\n1. Imagina que tienes una caja dentro de otra caja. Cada caja contiene lo mismo pero más pequeño.\n2. La recursividad funciona igual: una función se llama a sí misma con un problema más pequeño.\n3. Necesita un caso base — el momento en que deja de llamarse.\n¿Quieres que lo veamos con un ejemplo en código?"
        """
    elif 'BOREDOM' in estado:
        return base + f"""
        [ESTADO ALUMNO: ABURRIMIENTO (HRV: {rmssd})]
        >>> TU PERSONALIDAD AHORA: "GAMER / YOUTUBER ENÉRGICO"
        1. FORMATO: Usa emojis (🚀, 💥, 🎮). Habla con 'slang' ligero.
        2. TONO: Provocador, divertido, rápido.
        3. ACCIÓN: ¡NO EXPLIQUES LA TEORÍA! Lanza un reto inmediatamente.
        4. EJEMPLO: "¡Venga ya! Eso es muy fácil para ti 😜."
        """
    elif 'FLOW' in estado:
        return base + f"""
        [ESTADO ALUMNO: FLOW / CONCENTRACIÓN MÁXIMA (HRV: {rmssd})]
        >>> TU PERSONALIDAD AHORA: "INGENIERO SENIOR DE GOOGLE"
        1. FORMATO: "TL;DR". Ve directo al grano. No uses emojis.
        2. TONO: Técnico, seco, profesional, eficiente.
        3. ACCIÓN: Usa tecnicismos. Prioriza código.
        4. EJEMPLO: "Correcto. La complejidad es O(n). Implementa un Hash Map."
        """
    else:
        return base + "Actúa como un profesor normal. Sé claro y útil."

def render_debug_panel(debug_events):
    """Renderiza el panel de debug con los eventos de la pipeline de decisión"""
    if not debug_events:
        return
    with st.expander("🔍 Pipeline de decisión (debug)", expanded=False):
        for evt in debug_events:
            icon = evt.get("icon", "⚙️")
            label = evt.get("label", "")
            detail = evt.get("detail", "")
            duration = evt.get("duration_ms")
            
            time_str = f" `{duration}ms`" if duration is not None else ""
            
            if evt.get("type") == "separator":
                st.divider()
            elif evt.get("type") == "json":
                st.markdown(f"{icon} **{label}**{time_str}")
                st.json(detail)
            else:
                st.markdown(f"{icon} **{label}**{time_str}")
                if detail:
                    st.caption(detail)

if "messages" not in st.session_state:
    st.session_state.messages = []

if "bio_history" not in st.session_state:
    st.session_state.bio_history = []

if "emergency_mode" not in st.session_state:
    st.session_state.emergency_mode = False

st.markdown("""
<style>
/* Indicador de estado */
.state-badge {
    padding: 0.75rem 1rem;
    border-radius: 12px;
    text-align: center;
    font-weight: 700;
    font-size: 1.1rem;
    color: white;
    margin-bottom: 0.75rem;
    letter-spacing: 0.5px;
}
.state-flow    { background: linear-gradient(135deg, #00b894, #00cec9); }
.state-stress  { background: linear-gradient(135deg, #e17055, #d63031); }
.state-boredom { background: linear-gradient(135deg, #fdcb6e, #e17055); color: #2d3436; }
.state-unknown { background: linear-gradient(135deg, #636e72, #b2bec3); }

/* Barra de confianza */
.conf-bar-bg {
    height: 8px; border-radius: 4px; background: #dfe6e9;
    overflow: hidden; margin-top: 2px;
}
.conf-bar-fill {
    height: 100%; border-radius: 4px;
    transition: width 0.3s ease;
}

/* Tarjetas de señal */
.signal-card {
    background: #f8f9fa; border-radius: 10px; padding: 0.5rem 0.25rem;
    text-align: center; border: 1px solid #e9ecef;
}
.signal-card.inactive { opacity: 0.35; }
.signal-icon { font-size: 1.3rem; }
.signal-name { font-size: 0.7rem; color: #636e72; font-weight: 600; margin-top: 2px; }
.signal-dot  { font-size: 0.6rem; }
.signal-dot.on  { color: #00b894; }
.signal-dot.off { color: #b2bec3; }

/* Indicador de agente */
.agent-badge {
    padding: 0.5rem 0.75rem;
    border-radius: 10px;
    text-align: center;
    font-size: 0.85rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
}
.agent-badge-normal { background: #f0f0f0; border: 1px solid #dfe6e9; color: #2d3436; }
.agent-badge-emergency { background: #fce4e4; border: 2px solid #d63031; color: #d63031; }

/* Chip biométrico en el chat */
.bio-chip {
    display: inline-flex; align-items: center; gap: 0.3rem;
    padding: 0.15rem 0.65rem; border-radius: 20px;
    font-size: 0.72rem; margin: 0.15rem 0; color: #555;
}
.bio-chip-flow    { background: #e8f8f5; }
.bio-chip-stress  { background: #fce4e4; }
.bio-chip-boredom { background: #fef9e7; }
.bio-chip-emergency { background: #fce4e4; color: #d63031; font-weight: 600; }

/* Aviso persistente de emergencia */
.emergency-banner {
    background: linear-gradient(135deg, #d63031, #e17055);
    color: white; padding: 0.6rem 1rem; border-radius: 10px;
    text-align: center; font-weight: 600; margin-bottom: 0.5rem;
    animation: pulse-emergency 2s infinite;
}
@keyframes pulse-emergency {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.8; }
}

</style>
""", unsafe_allow_html=True)

bio_data = asyncio.run(obtener_contexto_biometrico())
estado_actual = bio_data.get("status", "Unknown")
rmssd_actual = bio_data.get("rmssd", 0)
confidence = bio_data.get("confidence", 0)
signals_used = bio_data.get("signals_used", [])
baseline_rmssd = bio_data.get("baseline", rmssd_actual)

# Historial HRV
timestamp = datetime.now().strftime("%H:%M:%S")
st.session_state.bio_history.append({"Hora": timestamp, "HRV": rmssd_actual})
if len(st.session_state.bio_history) > 20:
    st.session_state.bio_history.pop(0)

# Funciones auxiliares de estado
def _state_class(estado):
    if 'STRESS' in estado: return 'stress'
    if 'BOREDOM' in estado: return 'boredom'
    if 'FLOW' in estado: return 'flow'
    return 'unknown'

def _state_display(estado):
    if 'STRESS' in estado: return "ESTRÉS", "🧘"
    if 'BOREDOM' in estado: return "ABURRIMIENTO", "🎮"
    if 'FLOW' in estado: return "FLOW", "🤓"
    return "—", "❓"

def _personality(estado):
    if 'STRESS' in estado: return "Mentor Zen"
    if 'BOREDOM' in estado: return "Gamer / Youtuber"
    if 'FLOW' in estado: return "Ingeniero Senior"
    return "Profesor"

state_class = _state_class(estado_actual)
state_label, state_emoji = _state_display(estado_actual)
personality = _personality(estado_actual)

# Sidebar
with st.sidebar:
    st.markdown("### 🎓 Bio-Tutor")

    if st.button("🔄 Actualizar sensor", use_container_width=True):
        st.rerun()

    # Aviso de emergencia (si activo)
    if st.session_state.emergency_mode:
        st.markdown('<div class="emergency-banner">🚨 EMERGENCIA ACTIVA</div>', unsafe_allow_html=True)

    # Estado cognitivo
    st.markdown(f'<div class="state-badge state-{state_class}">{state_emoji} {state_label}</div>', unsafe_allow_html=True)

    # — Agente activo —
    agent_name = "🆘 Emergencia" if st.session_state.emergency_mode else f"{personality}"
    agent_cls = "emergency" if st.session_state.emergency_mode else "normal"
    st.markdown(f'<div class="agent-badge agent-badge-{agent_cls}">🤖 {agent_name}</div>', unsafe_allow_html=True)

    # Barra de confianza
    conf_color = "#00b894" if confidence > 0.7 else "#fdcb6e" if confidence > 0.4 else "#d63031"
    st.markdown(
        f'<div style="display:flex;justify-content:space-between;font-size:0.75rem;color:#636e72;">'
        f'<span>Confianza</span><span><b>{confidence:.0%}</b></span></div>'
        f'<div class="conf-bar-bg"><div class="conf-bar-fill" style="width:{confidence*100:.0f}%;background:{conf_color};"></div></div>',
        unsafe_allow_html=True,
    )

    st.markdown("")

    # HRV con delta respecto a baseline
    hrv_delta = rmssd_actual - baseline_rmssd
    st.metric(
        label="♥️ HRV (RMSSD)",
        value=f"{rmssd_actual:.1f} ms",
        delta=f"{hrv_delta:+.1f} vs baseline"
    )

    # Señales activas
    st.markdown("**Señales**")
    signal_meta = {
        "ecg":  ("♥️", "ECG"),
        "eda":  ("⚡", "EDA"),
        "resp": ("🫁", "RESP"),
        "temp": ("🌡️", "TEMP"),
    }
    cols = st.columns(4)
    for i, (sig, (icon, name)) in enumerate(signal_meta.items()):
        active = sig in signals_used
        cls = "" if active else " inactive"
        dot_cls = "on" if active else "off"
        dot_txt = "● ON" if active else "○ —"
        with cols[i]:
            st.markdown(
                f'<div class="signal-card{cls}">'
                f'<div class="signal-icon">{icon}</div>'
                f'<div class="signal-name">{name}</div>'
                f'<div class="signal-dot {dot_cls}">{dot_txt}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("")

    # Tendencia HRV
    st.markdown("**📈 Tendencia HRV**")
    df_chart = pd.DataFrame(st.session_state.bio_history)
    if not df_chart.empty:
        st.line_chart(df_chart, x="Hora", y="HRV", color="#FF4B4B", height=150)

    st.divider()
    st.caption("WESAD · Kafka · GPT-OSS · Multi-señal")

# Chat principal
st.title("🎓 Tutor Inteligente Bio-Adaptativo")

# Renderiza indicadores biométricos en el chat
def _render_bio_chip(contenido, tipo):
    if "EMERGENCY" in tipo:
        st.markdown(f'<div class="bio-chip bio-chip-emergency">🚨 {contenido}</div>', unsafe_allow_html=True)
    else:
        cls = "bio-chip-flow" if "FLOW" in tipo else "bio-chip-stress" if "STRESS" in tipo else "bio-chip-boredom" if "BOREDOM" in tipo else ""
        emoji = "🤓" if "FLOW" in tipo else "🧘" if "STRESS" in tipo else "🎮" if "BOREDOM" in tipo else "📊"
        st.markdown(f'<div class="bio-chip {cls}">{emoji} {contenido}</div>', unsafe_allow_html=True)

# BUCLE DE RENDERIZADO DEL HISTORIAL
for message in st.session_state.messages:
    if message["role"] == "user":
        with st.chat_message("user"):
            st.markdown(message["content"])
    elif message["role"] == "assistant":
        with st.chat_message("assistant"):
            st.markdown(message["content"])
            if message.get("debug"):
                render_debug_panel(message["debug"])
    elif message["role"] == "log":
        _render_bio_chip(message["content"], message.get("type", "NORMAL"))

# INPUT DEL USUARIO
if prompt := st.chat_input("Escribe tu duda aquí..."):

    # 1. Mostrar y guardar mensaje del usuario
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Bio log compacto
    log_text = f"{estado_actual} | HRV: {rmssd_actual:.1f} ms | Confianza: {confidence:.0%}"
    st.session_state.messages.append({
        "role": "log",
        "content": log_text,
        "type": estado_actual
    })
    _render_bio_chip(log_text, estado_actual)

    # 3. Generar respuesta (ARQUITECTURA DUAL: Triage → Profesor / Emergencia)
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        
        try:
            client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)
            
            # Log de depuración para esta interacción
            debug_events = []
            t_start = time.time()
            
            # FILTRO CRÍTICO: Eliminamos los mensajes de 'log' antes de enviar a Groq
            messages_for_llm = [
                {"role": m["role"], "content": m["content"]} 
                for m in st.session_state.messages 
                if m["role"] in ["user", "assistant"]
            ]
            
            debug_events.append({
                "icon": "📡", "label": "Contexto biométrico",
                "detail": f"Estado: {estado_actual} | HRV: {rmssd_actual:.2f} ms | Confianza: {confidence:.0%} | Señales: {', '.join(s.upper() for s in signals_used)}"
            })
            
            # Paso 1: triage
            t_triage = time.time()
            triage_result = ejecutar_triage(client, prompt, estado_actual, confidence)
            triage_ms = int((time.time() - t_triage) * 1000)
            is_emergency = triage_result.get("risk", False)
            
            debug_events.append({
                "icon": "🛡️", "label": "Agente Triage",
                "type": "json", "detail": triage_result,
                "duration_ms": triage_ms
            })
            
            if is_emergency:
                # Crisis detectada → emergencia
                st.session_state.emergency_mode = True
                
                debug_events.append({"icon": "🚨", "label": "Agente seleccionado: EMERGENCIA", "detail": "El triage ha detectado riesgo. Se activa el agente de emergencia en lugar del profesor."})
                
                # Log de emergencia
                emergency_log = f"Triage: riesgo detectado (confianza: {triage_result.get('confidence', 0):.0%}) — Agente de emergencia activado"
                st.session_state.messages.append({
                    "role": "log",
                    "content": emergency_log,
                    "type": "EMERGENCY"
                })
                _render_bio_chip(emergency_log, "EMERGENCY")
                
                t_emergency = time.time()
                bot_reply = generar_respuesta_emergencia(client, messages_for_llm)
                emergency_ms = int((time.time() - t_emergency) * 1000)
                debug_events.append({"icon": "💬", "label": "LLM → Agente Emergencia", "detail": f"Modelo: {LLM_MODEL} | temp=0.3", "duration_ms": emergency_ms})
            
            else:
                # Flujo normal → profesor
                st.session_state.emergency_mode = False
                
                # Determinar personalidad
                if 'STRESS' in estado_actual:
                    personalidad = "Mentor Zen"
                elif 'BOREDOM' in estado_actual:
                    personalidad = "Gamer/Youtuber"
                elif 'FLOW' in estado_actual:
                    personalidad = "Ingeniero Senior"
                else:
                    personalidad = "Profesor Normal"
                
                debug_events.append({"icon": "🎓", "label": f"Agente seleccionado: PROFESOR ({personalidad})", "detail": f"Personalidad adaptada al estado biométrico: {estado_actual}"})
                
                system_prompt = generar_prompt_adaptativo(
                    estado_actual, rmssd_actual, confidence, signals_used
                )
                
                full_messages = [{"role": "system", "content": system_prompt}] + messages_for_llm

                # --- Llamada al LLM con tools ---
                # Groq puede devolver 400 si el modelo genera tool calls en formato
                # incorrecto. Capturamos ese caso y parseamos manualmente.
                raw_content = None
                response = None
                t_llm = time.time()
                try:
                    response = client.chat.completions.create(
                        model=LLM_MODEL,
                        messages=full_messages,
                        tools=LLM_TOOLS,
                        tool_choice="auto",
                        temperature=0.8,
                        max_tokens=1024
                    )
                except Exception as tool_error:
                    failed_gen = extract_failed_tool_call(tool_error)
                    if failed_gen:
                        raw_content = failed_gen
                        debug_events.append({"icon": "⚠️", "label": "Groq 400: tool_use_failed → recuperado", "detail": f"Se parseará manualmente: {failed_gen[:100]}..."})
                    else:
                        raise tool_error
                llm_ms = int((time.time() - t_llm) * 1000)
                debug_events.append({"icon": "💬", "label": "LLM → Agente Profesor", "detail": f"Modelo: {LLM_MODEL} | temp=0.8", "duration_ms": llm_ms})
                
                # --- TOOL CALLING ---
                bot_reply = None
                
                # Caso 1: Tool calls estructurados (API estándar)
                if response and response.choices[0].message.tool_calls:
                    full_messages.append(response.choices[0].message)
                    
                    for tool_call in response.choices[0].message.tool_calls:
                        if tool_call.function.name == "get_signal_detail":
                            args = json.loads(tool_call.function.arguments)
                            debug_events.append({"icon": "🔧", "label": f"MCP Tool Call: get_signal_detail({args.get('signal', '?')})", "detail": f"Llamada al servidor MCP → Redis → signal:{args.get('signal', '?')}"})
                            t_mcp = time.time()
                            tool_result = asyncio.run(
                                llamar_mcp_tool("get_signal_detail", args)
                            )
                            mcp_ms = int((time.time() - t_mcp) * 1000)
                            debug_events.append({"icon": "📦", "label": f"MCP Respuesta: signal:{args.get('signal', '?')}", "type": "json", "detail": json.loads(tool_result) if tool_result.startswith('{') else tool_result, "duration_ms": mcp_ms})
                            full_messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": tool_result
                            })
                    
                    t_llm2 = time.time()
                    response = client.chat.completions.create(
                        model=LLM_MODEL,
                        messages=full_messages,
                        temperature=0.8,
                        max_tokens=1024
                    )
                    llm2_ms = int((time.time() - t_llm2) * 1000)
                    debug_events.append({"icon": "💬", "label": "LLM → Re-query con datos MCP", "detail": f"Modelo: {LLM_MODEL}", "duration_ms": llm2_ms})
                    bot_reply = response.choices[0].message.content
                
                else:
                    # Caso 2: El modelo emite tool calls como texto <function>...</function>
                    # (incluye failed_generation recuperado del error 400)
                    if raw_content is None and response:
                        raw_content = response.choices[0].message.content or ""
                    raw_content = raw_content or ""
                    text_calls = parse_text_tool_calls(raw_content)
                    
                    if text_calls:
                        debug_events.append({"icon": "📝", "label": f"Tool calls detectados en texto: {len(text_calls)}", "detail": f"Formato nativo parseado manualmente"})
                        cleaned = clean_function_tags(raw_content)
                        tool_results_text = []
                        
                        for tool_name, tool_args in text_calls:
                            if tool_name == "get_signal_detail":
                                debug_events.append({"icon": "🔧", "label": f"MCP Tool Call: get_signal_detail({tool_args.get('signal', '?')})", "detail": f"Llamada al servidor MCP → Redis → signal:{tool_args.get('signal', '?')}"})
                                t_mcp = time.time()
                                result = asyncio.run(
                                    llamar_mcp_tool("get_signal_detail", tool_args)
                                )
                                mcp_ms = int((time.time() - t_mcp) * 1000)
                                signal_name = tool_args.get('signal', 'unknown')
                                debug_events.append({"icon": "📦", "label": f"MCP Respuesta: signal:{signal_name}", "type": "json", "detail": json.loads(result) if result.startswith('{') else result, "duration_ms": mcp_ms})
                                tool_results_text.append(
                                    f"[Datos biométricos de {signal_name.upper()}]: {result}"
                                )
                        
                        # Re-query con el contexto de los tools
                        if cleaned:
                            full_messages.append({"role": "assistant", "content": cleaned})
                        full_messages.append({
                            "role": "user",
                            "content": "El sistema ha consultado las señales que pediste. Aquí están los resultados: "
                                       + " | ".join(tool_results_text)
                                       + ". Ahora responde al alumno usando esta información."
                        })
                        
                        t_llm2 = time.time()
                        response = client.chat.completions.create(
                            model=LLM_MODEL,
                            messages=full_messages,
                            temperature=0.8,
                            max_tokens=1024
                        )
                        llm2_ms = int((time.time() - t_llm2) * 1000)
                        debug_events.append({"icon": "💬", "label": "LLM → Re-query con datos MCP", "detail": f"Modelo: {LLM_MODEL}", "duration_ms": llm2_ms})
                        bot_reply = response.choices[0].message.content
                    else:
                        debug_events.append({"icon": "✅", "label": "Respuesta directa (sin tool calls)", "detail": ""})
                        bot_reply = raw_content
            
            # Limpieza final por si quedan tags residuales
            bot_reply = clean_function_tags(bot_reply)
            
            # Tiempo total
            total_ms = int((time.time() - t_start) * 1000)
            debug_events.append({"type": "separator"})
            debug_events.append({"icon": "⏱️", "label": "Tiempo total de respuesta", "duration_ms": total_ms})
            
            message_placeholder.markdown(bot_reply)
            st.session_state.messages.append({"role": "assistant", "content": bot_reply, "debug": debug_events})
            
            # Renderizar panel de debug para esta interacción
            render_debug_panel(debug_events)
            
        except Exception as e:
            message_placeholder.error(f"Error: {e}")