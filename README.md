# Tutor Inteligente Bio-Adaptativo

**Trabajo Fin de Máster** — Máster en Ingeniería y Ciencia de Datos, UNED

**Título:** Diseño e implementación de una arquitectura distribuida para la adaptación pedagógica de un LLM mediante telemetría fisiológica en un Sistema de Tutoría Inteligente

---

## Descripción

Sistema de tutoría inteligente bio-adaptativo que utiliza señales biométricas en tiempo real para detectar el estado cognitivo del estudiante (estrés, concentración o aburrimiento) y adaptar automáticamente la personalidad y estrategia pedagógica de un LLM. El sistema implementa un bucle biocibernético completo mediante una arquitectura distribuida de microservicios orientada a eventos.

### Funcionalidades principales

- **Procesamiento biométrico multi-señal**: ECG (HRV/RMSSD), EDA (SCL/SCR), respiración y temperatura cutánea, procesados en tiempo real con NeuroKit2.
- **Tres personalidades adaptativas** basadas en la Ley de Yerkes-Dodson:
  - *Estrés* → Mentor Zen (empático, calmado)
  - *Flow/Concentración* → Ingeniero Senior (técnico, directo)
  - *Aburrimiento* → Gamer/Youtuber (gamificado, retador)
- **Sistema multi-agente**: triaje de seguridad, tutor adaptativo y agente de emergencia (024).
- **Tool calling via MCP**: el LLM consulta detalles de señales biométricas cuando lo necesita.

---

## Arquitectura

```
Producer (WESAD) → Kafka → [Processor ECG|EDA|Resp|Temp] → Redis → MCP Server → Streamlit + LLM (Groq)
```

---

## Requisitos previos

- **Docker Desktop** (para la infraestructura de microservicios)
- **Python 3.10+** (para el cliente Streamlit)
- **Groq API Key** (gratuita, obtener en https://console.groq.com/)
- **Dataset WESAD** (ver instrucciones en [data/WESAD/README.md](data/WESAD/README.md))

---

## Instalación y arranque

### 1. Configurar variables de entorno

Crea el archivo `.env` a partir de la plantilla:

```powershell
cp .env.example .env
```

Edita `.env` con tu API key:

```env
GROQ_API_KEY=tu_api_key_de_groq
MCP_SERVER_URL=http://localhost:8000/sse
LLM_MODEL=openai/gpt-oss-120b
```

### 2. Descargar el dataset WESAD

Sigue las instrucciones de [data/WESAD/README.md](data/WESAD/README.md). Como mínimo necesitas la carpeta `S2/` con el archivo `S2.pkl`.

### 3. Crear entorno virtual e instalar dependencias del cliente

```powershell
python -m venv venv
.\venv\Scripts\Activate
pip install -r requirements_client.txt
```

> **Nota PowerShell:** si recibes un error de ejecución de scripts, ejecuta primero:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force
> ```

### 4. Levantar la infraestructura Docker

```powershell
docker-compose up --build -d
```

Verifica que los 9 contenedores están levantados:

```powershell
docker-compose ps -a
```

> Los processors necesitan ~2-3 minutos para calibrar. Puedes seguir el progreso con:
> ```powershell
> docker-compose logs -f orchestrator
> ```
> Cuando veas `FLOW (Optimal) | Confianza: 0.85 | Señales: ['ecg', 'eda', 'resp', 'temp']`, el sistema está listo.

### 5. Lanzar la interfaz gráfica

```powershell
.\venv\Scripts\Activate
streamlit run app.py
```

La aplicación se abrirá en `http://localhost:8501`.

---

## Verificación del sistema

### Verificar componentes individuales

```powershell
# Producer (envío de señales)
docker-compose logs -f producer

# Processors (calibración y procesamiento)
docker-compose logs -f processor-ecg
docker-compose logs -f processor-eda
docker-compose logs -f processor-resp
docker-compose logs -f processor-temp

# Orchestrator (fusión de señales)
docker-compose logs -f orchestrator

# Redis (estado almacenado)
docker exec -it redis redis-cli KEYS *
docker exec -it redis redis-cli GET user_context
```

### Tests funcionales del MCP Server

```powershell
python .\test\test_mcp_01_connection.py
python .\test\test_mcp_02_data.py
```

### Verificar el chat adaptativo

1. En la sidebar, verificar que aparece el estado cognitivo, HRV, confianza y señales activas.
2. Escribir: *"Explícame qué es una lista enlazada"* — observar la personalidad del tutor.
3. Esperar a que cambie el estado biométrico y repetir la pregunta para ver la adaptación.
4. Probar tool calling: *"¿Puedes verificar mis señales biométricas y decirme qué está pasando?"*
5. Probar agente de emergencia: *"No le encuentro sentido a nada, creo que no quiero seguir adelante"* — debe activarse el banner de emergencia con el teléfono 024.

---

## Simulación manual de escenarios

Para simular estados cognitivos específicos (estrés, flow, aburrimiento, sensores desconectados, señales contradictorias) sin depender del dataset, consultar la guía detallada:

**→ [docs/manual_simulation.md](docs/manual_simulation.md)**

---

## Estructura del proyecto

```
├── app.py                  # Cliente Streamlit + agentes LLM (Groq)
├── docker-compose.yml      # Orquestación de los 9 microservicios
├── .env.example            # Plantilla de variables de entorno
├── requirements_client.txt # Dependencias del cliente Streamlit
├── common/                 # Código compartido (config, logger, base_processor)
├── producer/               # Simulador de streaming WESAD → Kafka
├── processor_ecg/          # Procesador de señal ECG (HRV/RMSSD)
├── processor_eda/          # Procesador de actividad electrodérmica
├── processor_resp/         # Procesador de señal respiratoria
├── processor_temp/         # Procesador de temperatura cutánea
├── orchestrator/           # Fusión multi-señal con cross-validación
├── mcp_server/             # Servidor MCP (expone biometría al LLM)
├── test/                   # Tests funcionales del MCP Server
├── data/WESAD/             # Dataset (no incluido, ver README interno)
└── docs/
    └── manual_simulation.md  # Guía de simulación manual de escenarios
```

---

## Parar el sistema

```powershell
docker-compose down -v
```

> El flag `-v` elimina los volúmenes de Kafka para evitar datos residuales.

---

## Referencia

- **Dataset**: Schmidt, P., Reiss, A., Duerichen, R., Marquardt, C., & Van Laerhoven, K. (2018). *Introducing WESAD, a Multimodal Dataset for Wearable Stress and Affect Detection.* ICMI '18.
- **NeuroKit2**: Makowski, D. et al. (2021). *NeuroKit2: A Python Toolbox for Heart Rate Variability and Biosignal Analysis.* JOSS.
- **MCP**: Anthropic. *Model Context Protocol.*
- **Groq**: Groq, Inc.
