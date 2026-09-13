import time
import json
import pickle
import numpy as np
import os
from kafka import KafkaProducer

from common.config import KAFKA_BROKER, TOPIC_INPUT, SUBJECT_ID, WESAD_DATA_FILE, SAMPLING_RATE
from common.logger import get_logger

logger = get_logger("producer")

SLEEP_TIME = 1.0 / SAMPLING_RATE

def get_producer():
    # Bucle de reintento por si Kafka tarda en levantar
    while True:
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BROKER,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            logger.info("Conectado a Kafka exitosamente.")
            return producer
        except Exception as e:
            logger.warning(f"Esperando a Kafka... ({e})")
            time.sleep(5)

def load_wesad_data():
    logger.info(f"Cargando dataset WESAD desde: {WESAD_DATA_FILE} ...")
    logger.info("(Esto puede tardar un poco porque el archivo es grande)")
    
    if not os.path.exists(WESAD_DATA_FILE):
        logger.error(f"No encuentro el archivo {WESAD_DATA_FILE}")
        logger.error("Asegúrate de que la carpeta data/ está bien mapeada en docker-compose.")
        exit(1)

    with open(WESAD_DATA_FILE, 'rb') as f:
        # Los pickles de WESAD se crearon en Python 2, necesitamos encoding='latin1'
        u_data = pickle.load(f, encoding='latin1')
        
    ecg_signal = u_data['signal']['chest']['ECG'].flatten()
    eda_signal = u_data['signal']['chest']['EDA'].flatten()
    resp_signal = u_data['signal']['chest']['Resp'].flatten()
    temp_signal = u_data['signal']['chest']['Temp'].flatten()
    
    labels = u_data['label']
    
    logger.info(f"Datos cargados. Muestras totales: {len(ecg_signal)}")
    logger.info(f"Señales extraídas: ECG, EDA, Resp, Temp (todas a 700Hz)")
    return ecg_signal, eda_signal, resp_signal, temp_signal, labels

def simulate_sensor():
    producer = get_producer()
    ecg_data, eda_data, resp_data, temp_data, labels = load_wesad_data()
    
    logger.info(f"Iniciando streaming simulado a {SAMPLING_RATE} Hz...")
    
    # Iteramos sobre los datos
    # step=7 significa que saltamos de 7 en 7 para bajar de 700Hz a 100Hz aprox.
    step = 7 
    
    for i in range(0, len(ecg_data), step):
        
        payload = {
            'sensor_id': SUBJECT_ID,
            'ecg': float(ecg_data[i]),
            'eda': float(eda_data[i]),
            'resp': float(resp_data[i]),
            'temp': float(temp_data[i]),
            'label': int(labels[i]),
            'timestamp': time.time(),
            'sequence': i
        }
        
        producer.send(TOPIC_INPUT, payload)
        
        # Log visual cada 1000 mensajes (cada 10 segundos aprox)
        if i % (step * 100) == 0:
            logger.info(f"[Stream] Label: {payload['label']} | ECG: {payload['ecg']:.4f} | EDA: {payload['eda']:.4f} | Resp: {payload['resp']:.4f} | Temp: {payload['temp']:.2f}")
            
        time.sleep(SLEEP_TIME)

if __name__ == "__main__":
    time.sleep(5)
    simulate_sensor()