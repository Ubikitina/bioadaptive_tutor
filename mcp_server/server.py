import json
import redis
from fastmcp import FastMCP

from common.config import REDIS_HOST, REDIS_PORT
from common.logger import get_logger

logger = get_logger("mcp-server")

# Inicializar el servidor MCP
mcp = FastMCP("BioFeedback System")

# Conexión a Redis
try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
except Exception as e:
    logger.error(f"Error conectando a Redis: {e}")

@mcp.resource("user://state")
def get_user_state() -> str:
    """
    Devuelve el estado cognitivo y fisiológico actual del usuario en tiempo real.
    Devuelve un JSON con campos: status (FLOW, STRESS, BOREDOM), rmssd, y baseline.
    """
    try:
        data = redis_client.get("user_context")
        if data:
            return data
        return json.dumps({"status": "UNCERTAIN", "info": "Esperando datos del sensor..."})
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def get_signal_detail(signal: str) -> str:
    """
    Devuelve métricas detalladas de un procesador de señal biométrica específico.
    Úsala cuando el estado compuesto tenga baja confianza o necesites
    más contexto fisiológico para adaptar tu respuesta.
    
    Señales disponibles:
    - 'ecg': Variabilidad cardíaca (RMSSD, baseline, ratio, estado)
    - 'eda': Actividad electrodérmica (SCL, picos SCR, nivel de arousal)
    - 'resp': Datos respiratorios (frecuencia en bpm, amplitud, ratio)
    - 'temp': Temperatura cutánea (media, baseline, delta, tendencia)
    """
    valid_signals = ['ecg', 'eda', 'resp', 'temp']
    if signal not in valid_signals:
        return json.dumps({"error": f"Señal '{signal}' no válida. Usa una de: {valid_signals}"})
    try:
        data = redis_client.get(f"signal:{signal}")
        if data:
            return data
        return json.dumps({"error": f"Sin datos disponibles para la señal: {signal}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

if __name__ == "__main__":
    logger.info("Arrancando Servidor MCP (Modo SSE)...")
    mcp.run(transport="sse", host="0.0.0.0", port=8000)