import json
import time
import numpy as np
import redis
from abc import ABC, abstractmethod
from collections import deque
from kafka import KafkaConsumer, KafkaProducer

from common.config import (
    KAFKA_BROKER, TOPIC_INPUT, REDIS_HOST, REDIS_PORT,
    SAMPLING_RATE, WINDOW_SIZE, CALIBRATION_SAMPLES
)
from common.logger import get_logger


class BaseProcessor(ABC):
    """
    Clase base abstracta para todos los processors de señales biométricas.
    
    Cada processor concreto solo necesita implementar:
        - process_window(): lógica de procesamiento específica
        - publish():        qué métricas publicar a Kafka/Redis
        - on_calibrated():  callback cuando la calibración termina
        - extract_value():  cómo extraer el valor de la señal del mensaje Kafka
    """

    def __init__(self, signal_name: str, topic_output: str, group_id: str):
        self.signal_name = signal_name
        self.topic_output = topic_output
        self.logger = get_logger(f"processor-{signal_name}")

        self.buffer = deque(maxlen=WINDOW_SIZE)
        self.calibration_buffer = []
        self.is_calibrated = False
        self.samples_counter = 0

        self.consumer = self._get_consumer(group_id)
        self.producer = self._get_producer()
        self.redis_client = self._get_redis()

    def _get_consumer(self, group_id: str) -> KafkaConsumer:
        while True:
            try:
                self.logger.info(f"Conectando a Kafka consumer ({KAFKA_BROKER})...")
                c = KafkaConsumer(
                    TOPIC_INPUT,
                    bootstrap_servers=KAFKA_BROKER,
                    auto_offset_reset='latest',
                    group_id=group_id,
                    value_deserializer=lambda x: json.loads(x.decode('utf-8'))
                )
                self.logger.info("Kafka consumer conectado.")
                return c
            except Exception as e:
                self.logger.warning(f"Esperando Kafka consumer... ({e})")
                time.sleep(5)

    def _get_producer(self) -> KafkaProducer:
        while True:
            try:
                p = KafkaProducer(
                    bootstrap_servers=KAFKA_BROKER,
                    value_serializer=lambda v: json.dumps(v).encode('utf-8')
                )
                self.logger.info("Kafka producer conectado.")
                return p
            except Exception as e:
                self.logger.warning(f"Esperando Kafka producer... ({e})")
                time.sleep(5)

    def _get_redis(self) -> redis.Redis:
        while True:
            try:
                r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
                r.ping()
                self.logger.info("Redis conectado.")
                return r
            except Exception as e:
                self.logger.warning(f"Esperando Redis... ({e})")
                time.sleep(5)

    def publish_to_kafka_and_redis(self, data: dict):
        """Publica datos al topic de salida y a Redis"""
        self.producer.send(self.topic_output, data)
        self.redis_client.set(f"signal:{self.signal_name}", json.dumps(data))

    @abstractmethod
    def extract_value(self, message_data: dict):
        """Extrae el valor de la señal del mensaje Kafka. Retorna None si no está."""
        pass

    @abstractmethod
    def process_window(self):
        """Procesa la ventana actual del buffer. Retorna métricas o None."""
        pass

    @abstractmethod
    def on_calibrated(self, calibration_value):
        """Callback al completar calibración. Guarda el baseline."""
        pass

    @abstractmethod
    def publish(self, *args, **kwargs):
        """Lógica específica de publicación con métricas del processor."""
        pass

    @abstractmethod
    def is_valid_calibration(self, processed_result) -> bool:
        """Verifica si el resultado del procesamiento es válido para calibración."""
        pass

    @abstractmethod
    def get_calibration_value(self, processed_result):
        """Extrae el valor a usar para calibración del resultado procesado."""
        pass

    def run(self):
        self.logger.info(f"Iniciado. Ventana: {WINDOW_SIZE // SAMPLING_RATE}s")

        for message in self.consumer:
            data = message.value
            value = self.extract_value(data)

            if value is not None:
                self.buffer.append(value)
                self.samples_counter += 1

            if len(self.buffer) >= WINDOW_SIZE:
                # CALIBRACIÓN 
                if not self.is_calibrated:
                    result = self.process_window()
                    if self.is_valid_calibration(result):
                        cal_value = self.get_calibration_value(result)
                        self.calibration_buffer.append(cal_value)
                        if len(self.calibration_buffer) > CALIBRATION_SAMPLES:
                            baseline = float(np.mean(self.calibration_buffer))
                            self.on_calibrated(baseline)
                            self.is_calibrated = True
                    continue

                # PROCESAMIENTO EN TIEMPO REAL
                if self.samples_counter % SAMPLING_RATE == 0:
                    self.publish(data)
