import json
import time
import redis
from kafka import KafkaConsumer

from common.config import KAFKA_BROKER, REDIS_HOST, REDIS_PORT, STALE_THRESHOLD_SECONDS
from common.logger import get_logger

TOPICS = ['processed-ecg', 'processed-eda', 'processed-resp', 'processed-temp']

logger = get_logger("orchestrator")


class SignalOrchestrator:
    def __init__(self):
        # Último dato recibido de cada señal
        self.latest = {
            'ecg': None,
            'eda': None,
            'resp': None,
            'temp': None
        }
        
        self.consumer = self._get_consumer()
        self.redis_client = self._get_redis()

    def _get_consumer(self):
        while True:
            try:
                logger.info(f"Conectando a Kafka ({KAFKA_BROKER})...")
                c = KafkaConsumer(
                    *TOPICS,
                    bootstrap_servers=KAFKA_BROKER,
                    auto_offset_reset='latest',
                    group_id='orchestrator',
                    value_deserializer=lambda x: json.loads(x.decode('utf-8'))
                )
                logger.info(f"Suscrito a {TOPICS}")
                return c
            except Exception as e:
                logger.warning(f"Esperando Kafka... ({e})")
                time.sleep(5)

    def _get_redis(self):
        while True:
            try:
                r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
                r.ping()
                logger.info("Redis conectado.")
                return r
            except Exception as e:
                logger.warning(f"Esperando Redis... ({e})")
                time.sleep(5)

    def is_stale(self, signal_data):
        """Comprueba si un dato de señal está obsoleto"""
        if signal_data is None:
            return True
        age = time.time() - signal_data.get('timestamp', 0)
        return age > STALE_THRESHOLD_SECONDS

    def fuse_signals(self):
        """Combina las 4 señales para determinar el estado cognitivo y su confianza."""
        ecg = self.latest['ecg']
        eda = self.latest['eda']
        resp = self.latest['resp']
        
        # Sin ECG no podemos determinar estado base
        if ecg is None or self.is_stale(ecg):
            return {
                "status": "UNCERTAIN",
                "confidence": 0.0,
                "signals_used": [],
                "reason": "Sin datos ECG disponibles",
                "timestamp": time.time()
            }
        
        # Estado base desde ECG
        base_state = ecg.get('state', 'UNCERTAIN')
        confidence = 0.5
        signals_used = ['ecg']
        reason = f"ECG: {base_state} (RMSSD: {ecg.get('rmssd')})"
        
        # Cross-validación con EDA
        if eda and not self.is_stale(eda):
            scl_ratio = eda.get('scl_ratio')
            scr_peaks = eda.get('scr_peaks', 0)
            signals_used.append('eda')
            
            if scl_ratio:
                if 'STRESS' in base_state:
                    if scl_ratio > 1.2:
                        # EDA confirma arousal alto → estrés real
                        confidence += 0.25
                        reason += f" | EDA confirma arousal (SCL ratio: {scl_ratio})"
                    elif scl_ratio < 0.8:
                        # EDA contradice → posible artefacto
                        confidence -= 0.2
                        base_state = "UNCERTAIN"
                        reason += f" | EDA contradice: baja activación (SCL ratio: {scl_ratio})"
                    
                elif 'BOREDOM' in base_state:
                    if scl_ratio < 0.8:
                        confidence += 0.2
                        reason += f" | EDA confirma baja activación (SCL ratio: {scl_ratio})"
                    elif scl_ratio > 1.3:
                        # Paradoja: HRV dice boredom pero EDA dice arousal
                        base_state = "FLOW (Optimal)"
                        confidence = 0.4
                        reason += f" | EDA corrige: arousal detectado (SCL ratio: {scl_ratio})"
                        
                elif 'FLOW' in base_state:
                    if 0.8 <= scl_ratio <= 1.3:
                        confidence += 0.2
                        reason += f" | EDA confirma activación moderada (SCL ratio: {scl_ratio})"

        # Cross-validación con temperatura
        temp = self.latest['temp']
        if temp and not self.is_stale(temp):
            temp_delta = temp.get('temp_delta', 0)
            trend = temp.get('trend', 'stable')
            signals_used.append('temp')
            
            if 'STRESS' in base_state:
                if trend == 'falling' or temp_delta < -0.1:
                    # Vasoconstricción confirma estrés
                    confidence += 0.1
                    reason += f" | Temp confirma: vasoconstricción (delta: {temp_delta:+.3f}°C)"
                elif trend == 'rising' and temp_delta > 0.1:
                    confidence -= 0.1
                    reason += f" | Temp contradice: temp subiendo (delta: {temp_delta:+.3f}°C)"
                    
            elif 'BOREDOM' in base_state:
                if trend == 'stable' or trend == 'rising':
                    confidence += 0.1
                    reason += f" | Temp confirma: relajación (delta: {temp_delta:+.3f}°C)"
                    
            elif 'FLOW' in base_state:
                if trend == 'stable':
                    confidence += 0.05
                    reason += f" | Temp confirma: estable (delta: {temp_delta:+.3f}°C)"

        # Cross-validación con respiración
        if resp and not self.is_stale(resp):
            rate_ratio = resp.get('rate_ratio')
            signals_used.append('resp')
            
            if rate_ratio:
                if 'STRESS' in base_state:
                    if rate_ratio > 1.3:
                        # Respiración acelerada confirma estrés
                        confidence += 0.15
                        reason += f" | Resp confirma: taquipnea (ratio: {rate_ratio})"
                    elif rate_ratio < 0.7:
                        confidence -= 0.1
                        reason += f" | Resp contradice: respiración lenta (ratio: {rate_ratio})"
                        
                elif 'BOREDOM' in base_state:
                    if rate_ratio < 0.8:
                        confidence += 0.15
                        reason += f" | Resp confirma: respiración lenta (ratio: {rate_ratio})"
                        
                elif 'FLOW' in base_state:
                    if 0.8 <= rate_ratio <= 1.2:
                        confidence += 0.1
                        reason += f" | Resp confirma: ritmo estable (ratio: {rate_ratio})"
        
        # Acotar confianza entre 0 y 1
        confidence = max(0.0, min(confidence, 1.0))
        
        return {
            "status": base_state,
            "confidence": round(confidence, 2),
            "signals_used": signals_used,
            "reason": reason,
            "rmssd": ecg.get('rmssd'),
            "baseline": ecg.get('baseline'),
            "timestamp": time.time(),
            "wesad_label_verification": ecg.get('wesad_label')
        }

    def save_composite_state(self, state):
        """Guarda el estado compuesto en Redis para que MCP lo lea"""
        try:
            self.redis_client.set("user_context", json.dumps(state))
        except Exception as e:
            logger.error(f"Error escribiendo en Redis: {e}")

    def run(self):
        logger.info("Signal Orchestrator Iniciado.")
        logger.info(f"Escuchando topics: {TOPICS}")
        
        for message in self.consumer:
            data = message.value
            signal_type = data.get('signal', message.topic.replace('processed-', ''))
            
            # Actualizar último dato de la señal correspondiente
            self.latest[signal_type] = data
            
            # Fusionar señales y publicar estado compuesto
            composite = self.fuse_signals()
            self.save_composite_state(composite)
            
            logger.info(f"{composite['status']} | Confianza: {composite['confidence']} | Señales: {composite['signals_used']}")

if __name__ == "__main__":
    time.sleep(10)  # Esperar a que los processors arranquen
    SignalOrchestrator().run()
