# Guía de Simulación Manual de Escenarios

Esta guía explica cómo simular escenarios de estrés, flow y sensores desconectados **sin tocar código**. Se hace deteniendo contenedores y escribiendo valores directamente en Redis con `redis-cli`.

## Prerrequisitos

- El stack Docker está corriendo: `docker-compose up --build -d`
- La app Streamlit está corriendo: `streamlit run app.py`
- Has verificado que el sistema funciona en modo normal (ver README, Fase 2)

## Cómo funciona la simulación

El flujo de datos es:

```
Producer → Kafka → Processors → Redis → MCP Server → Streamlit
```

Tanto el MCP Server como la app de Streamlit leen de Redis, no de Kafka. Si escribimos valores directamente en Redis, el MCP y la app los leerán como si vinieran del pipeline real. Solo necesitamos **parar los processors y el orchestrator** para que no sobreescriban nuestros valores.

## Acceso a Redis

Todas las operaciones se hacen desde una terminal con:

```powershell
docker exec -it redis redis-cli
```

Para salir de `redis-cli`: `exit`

---

## Escenario 1: Simular ESTRÉS

### Paso 1: Parar el pipeline

```powershell
docker-compose stop producer processor-ecg processor-eda processor-resp processor-temp orchestrator
```

Esto evita que sobreescriban los valores que vamos a inyectar.

### Paso 2: Inyectar señales individuales en Redis

Entra a `redis-cli` y ejecuta estos comandos:

```redis
SET signal:ecg '{"signal":"ecg","rmssd":18.5,"baseline":42.0,"ratio":0.44,"state":"STRESS (Overload)","timestamp":9999999999,"wesad_label":1}'

SET signal:eda '{"signal":"eda","scl":3.8120,"scl_baseline":2.1000,"scl_ratio":1.82,"scr_peaks":7,"timestamp":9999999999}'

SET signal:resp '{"signal":"resp","rate":22.5,"rate_baseline":14.0,"rate_ratio":1.61,"amplitude":0.3850,"timestamp":9999999999}'

SET signal:temp '{"signal":"temp","temp_mean":33.120,"temp_baseline":34.500,"temp_delta":-1.380,"trend":"falling","timestamp":9999999999}'
```

### Paso 3: Inyectar estado compuesto en Redis

```redis
SET user_context '{"status":"STRESS (Overload)","confidence":0.90,"signals_used":["ecg","eda","resp","temp"],"reason":"ECG: STRESS (RMSSD: 18.5) | EDA confirma arousal (SCL ratio: 1.82) | Temp confirma: vasoconstriccion (delta: -1.380°C) | Resp confirma: taquipnea (ratio: 1.61)","rmssd":18.5,"baseline":42.0,"timestamp":9999999999,"wesad_label_verification":1}'
```

### Paso 4: Verificar

```redis
GET user_context
GET signal:ecg
```

Sal de `redis-cli` con `exit`.

### Paso 5: Probar en la app

En Streamlit, pulsa **"🔄 Actualizar sensor"** en la sidebar. Deberías ver:
- **Estado**: ESTRÉS 🧘
- **Confianza**: ~90%
- **HRV**: 18.5 ms
- **Señales**: las 4 activas (ECG, EDA, RESP, TEMP)

Escribe en el chat: *"Explícame qué es una lista enlazada"*

El tutor debería responder como **Mentor Zen** (frases cortas, tono calmado, solución directa).

---

## Escenario 2: Simular FLOW

### Paso 1: Parar el pipeline

```powershell
docker-compose stop producer processor-ecg processor-eda processor-resp processor-temp orchestrator
```

### Paso 2: Inyectar señales individuales

```redis
SET signal:ecg '{"signal":"ecg","rmssd":45.2,"baseline":42.0,"ratio":1.08,"state":"FLOW (Optimal)","timestamp":9999999999,"wesad_label":0}'

SET signal:eda '{"signal":"eda","scl":2.3500,"scl_baseline":2.1000,"scl_ratio":1.12,"scr_peaks":2,"timestamp":9999999999}'

SET signal:resp '{"signal":"resp","rate":14.8,"rate_baseline":14.0,"rate_ratio":1.06,"amplitude":0.4200,"timestamp":9999999999}'

SET signal:temp '{"signal":"temp","temp_mean":34.480,"temp_baseline":34.500,"temp_delta":-0.020,"trend":"stable","timestamp":9999999999}'
```

### Paso 3: Inyectar estado compuesto

```redis
SET user_context '{"status":"FLOW (Optimal)","confidence":0.85,"signals_used":["ecg","eda","resp","temp"],"reason":"ECG: FLOW (RMSSD: 45.2) | EDA confirma activacion moderada (SCL ratio: 1.12) | Temp confirma: estable (delta: -0.020°C) | Resp confirma: ritmo estable (ratio: 1.06)","rmssd":45.2,"baseline":42.0,"timestamp":9999999999,"wesad_label_verification":0}'
```

### Paso 4: Probar en la app

Pulsa **"🔄 Actualizar sensor"**. Deberías ver:
- **Estado**: FLOW 🤓
- **Confianza**: ~85%
- **HRV**: 45.2 ms

Escribe: *"Explícame qué es una lista enlazada"*

El tutor debería responder como **Ingeniero Senior** (técnico, seco, directo al grano, tecnicismos).

---

## Escenario 3: Simular BOREDOM (Aburrimiento)

El aburrimiento se caracteriza por HRV elevada (ratio > 1.30), EDA baja, respiración lenta y temperatura estable o subiendo.

### Paso 1: Parar el pipeline

```powershell
docker-compose stop producer processor-ecg processor-eda processor-resp processor-temp orchestrator
```

### Paso 2: Inyectar señales individuales

```redis
SET signal:ecg '{"signal":"ecg","rmssd":62.0,"baseline":42.0,"ratio":1.48,"state":"BOREDOM (Low Arousal)","timestamp":9999999999,"wesad_label":0}'

SET signal:eda '{"signal":"eda","scl":1.4700,"scl_baseline":2.1000,"scl_ratio":0.70,"scr_peaks":0,"timestamp":9999999999}'

SET signal:resp '{"signal":"resp","rate":10.8,"rate_baseline":14.0,"rate_ratio":0.77,"amplitude":0.5600,"timestamp":9999999999}'

SET signal:temp '{"signal":"temp","temp_mean":34.620,"temp_baseline":34.500,"temp_delta":0.120,"trend":"rising","timestamp":9999999999}'
```

### Paso 3: Inyectar estado compuesto

```redis
SET user_context '{"status":"BOREDOM (Low Arousal)","confidence":0.80,"signals_used":["ecg","eda","resp","temp"],"reason":"ECG: BOREDOM (RMSSD: 62.0) | EDA confirma baja activacion (SCL ratio: 0.70) | Temp confirma: relajacion (delta: +0.120°C) | Resp confirma: respiracion lenta (ratio: 0.77)","rmssd":62.0,"baseline":42.0,"timestamp":9999999999,"wesad_label_verification":0}'
```

### Paso 4: Probar en la app

Pulsa **"🔄 Actualizar sensor"**. Deberías ver:
- **Estado**: ABURRIMIENTO 🎮
- **Confianza**: ~80%
- **HRV**: 62.0 ms (claramente por encima del baseline de 42 ms)

Escribe: *"Explícame qué es una lista enlazada"*

El tutor debería responder como **Gamer / Youtuber** (emojis como 🚀 💥 🎮, tono provocador y divertido, lanza un reto inmediato en lugar de explicar teoría).

---

## Escenario 4: Simular sensor EDA desconectado

### Paso 1: Parar el pipeline

```powershell
docker-compose stop producer processor-ecg processor-eda processor-resp processor-temp orchestrator
```

### Paso 2: Eliminar la señal EDA de Redis

```redis
DEL signal:eda
```

### Paso 3: Inyectar las otras 3 señales (escenario de estrés)

```redis
SET signal:ecg '{"signal":"ecg","rmssd":18.5,"baseline":42.0,"ratio":0.44,"state":"STRESS (Overload)","timestamp":9999999999,"wesad_label":1}'

SET signal:resp '{"signal":"resp","rate":22.5,"rate_baseline":14.0,"rate_ratio":1.61,"amplitude":0.3850,"timestamp":9999999999}'

SET signal:temp '{"signal":"temp","temp_mean":33.120,"temp_baseline":34.500,"temp_delta":-1.380,"trend":"falling","timestamp":9999999999}'
```

### Paso 4: Inyectar estado compuesto SIN EDA

```redis
SET user_context '{"status":"STRESS (Overload)","confidence":0.65,"signals_used":["ecg","resp","temp"],"reason":"ECG: STRESS (RMSSD: 18.5) | Temp confirma: vasoconstriccion (delta: -1.380°C) | Resp confirma: taquipnea (ratio: 1.61) | EDA no disponible (sensor desconectado)","rmssd":18.5,"baseline":42.0,"timestamp":9999999999,"wesad_label_verification":1}'
```

### Paso 5: Probar en la app

Pulsa **"🔄 Actualizar sensor"**. Deberías ver:
- **Estado**: ESTRÉS 🧘
- **Confianza**: ~65% (más baja que con todas las señales)
- **Señales**: ECG, RESP, TEMP activas; **EDA apagada** (○ —)

Escribe algo que fuerce tool calling: *"Noto que me cuesta concentrarme, ¿puedes verificar mis señales biométricas, darme sus valores y decirme qué está pasando?"*

Si el LLM consulta `get_signal_detail("eda")`, el MCP devolverá `{"error": "No data available for signal: eda"}`. Esto prueba que el sistema maneja la desconexión gracefully.

---

## Escenario 5: Simular ECG desconectado (sin señal base)

El ECG es la señal base del orchestrator. Sin ECG, el sistema no puede determinar el estado.

### Paso 1: Parar el pipeline

```powershell
docker-compose stop producer processor-ecg processor-eda processor-resp processor-temp orchestrator
```

### Paso 2: Eliminar ECG de Redis

```redis
DEL signal:ecg
```

### Paso 3: Inyectar las otras 3 señales

```redis
SET signal:eda '{"signal":"eda","scl":3.8120,"scl_baseline":2.1000,"scl_ratio":1.82,"scr_peaks":7,"timestamp":9999999999}'

SET signal:resp '{"signal":"resp","rate":22.5,"rate_baseline":14.0,"rate_ratio":1.61,"amplitude":0.3850,"timestamp":9999999999}'

SET signal:temp '{"signal":"temp","temp_mean":33.120,"temp_baseline":34.500,"temp_delta":-1.380,"trend":"falling","timestamp":9999999999}'
```

### Paso 4: Inyectar estado UNCERTAIN

```redis
SET user_context '{"status":"UNCERTAIN","confidence":0.0,"signals_used":[],"reason":"Sin datos ECG disponibles","rmssd":0,"baseline":0,"timestamp":9999999999,"wesad_label_verification":"?"}'
```

### Paso 5: Probar en la app

Pulsa **"🔄 Actualizar sensor"**. Deberías ver:
- **Estado**: — ❓ (desconocido)
- **Confianza**: 0%
- **Señales**: ECG apagada; las otras 3 pueden aparecer activas o no según `signals_used`

El tutor debería responder como **Profesor normal** (sin personalidad específica, ya que no hay estado biométrico).

---

## Escenario 6: Simular confianza baja (señales contradictorias)

Útil para probar que el LLM usa tool calling cuando hay incertidumbre.

### Paso 1: Parar el pipeline

```powershell
docker-compose stop producer processor-ecg processor-eda processor-resp processor-temp orchestrator
```

### Paso 2: Inyectar señales contradictorias

ECG dice STRESS pero EDA y Resp dicen lo contrario:

```redis
SET signal:ecg '{"signal":"ecg","rmssd":20.0,"baseline":42.0,"ratio":0.48,"state":"STRESS (Overload)","timestamp":9999999999,"wesad_label":1}'

SET signal:eda '{"signal":"eda","scl":1.6800,"scl_baseline":2.1000,"scl_ratio":0.80,"scr_peaks":0,"timestamp":9999999999}'

SET signal:resp '{"signal":"resp","rate":10.5,"rate_baseline":14.0,"rate_ratio":0.75,"amplitude":0.5200,"timestamp":9999999999}'

SET signal:temp '{"signal":"temp","temp_mean":34.600,"temp_baseline":34.500,"temp_delta":0.100,"trend":"rising","timestamp":9999999999}'
```

### Paso 3: Inyectar estado compuesto con confianza baja

```redis
SET user_context '{"status":"UNCERTAIN","confidence":0.20,"signals_used":["ecg","eda","resp","temp"],"reason":"ECG: STRESS (RMSSD: 20.0) | EDA contradice: baja activacion (SCL ratio: 0.80) | Temp contradice: temp subiendo (delta: +0.100°C) | Resp contradice: respiracion lenta (ratio: 0.75)","rmssd":20.0,"baseline":42.0,"timestamp":9999999999,"wesad_label_verification":1}'
```

### Paso 4: Probar en la app

Pulsa **"🔄 Actualizar sensor"**. Deberías ver:
- **Estado**: — ❓ (UNCERTAIN)
- **Confianza**: 20%
- **Señales**: las 4 activas pero contradictorias

El sistema prompt del LLM incluye `[AVISO: La confianza del estado actual es BAJA...]`, lo que debería llevar al tutor a usar `get_signal_detail` para investigar.
