import os

# Kafka
KAFKA_BROKER = os.getenv('KAFKA_BROKER', 'kafka:29092')
TOPIC_INPUT = os.getenv('TOPIC_INPUT', 'bio-sensors')

# Redis
REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))

# Procesamiento de señales
SAMPLING_RATE = int(os.getenv('SAMPLING_RATE', 100))
WINDOW_SECONDS = int(os.getenv('WINDOW_SECONDS', 60))
WINDOW_SIZE = SAMPLING_RATE * WINDOW_SECONDS

# Calibración
CALIBRATION_SAMPLES = int(os.getenv('CALIBRATION_SAMPLES', 10))

# Orchestrator
STALE_THRESHOLD_SECONDS = int(os.getenv('STALE_THRESHOLD_SECONDS', 30))

# WESAD 
SUBJECT_ID = os.getenv('SUBJECT_ID', 'S2')
WESAD_DATA_FILE = f'/app/data/WESAD/{SUBJECT_ID}/{SUBJECT_ID}.pkl'
