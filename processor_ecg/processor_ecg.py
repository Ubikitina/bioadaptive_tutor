import time
import numpy as np
import neurokit2 as nk

from common.base_processor import BaseProcessor
from common.config import SAMPLING_RATE

# Umbrales Relativos al HRV basal (Heurística Yerkes-Dodson)
THRESHOLD_STRESS = 0.75
THRESHOLD_BOREDOM = 1.30


class ECGProcessor(BaseProcessor):
    def __init__(self):
        super().__init__(
            signal_name="ecg",
            topic_output="processed-ecg",
            group_id="ecg-processor"
        )
        self.baseline_rmssd = None

    def extract_value(self, message_data: dict):
        return message_data.get('ecg')

    def process_window(self):
        """Calcula HRV sobre el buffer actual"""
        ecg_signal = np.array(self.buffer)
        try:
            ecg_cleaned = nk.ecg_clean(ecg_signal, sampling_rate=SAMPLING_RATE)
            peaks, _ = nk.ecg_peaks(ecg_cleaned, sampling_rate=SAMPLING_RATE)
            hrv_metrics = nk.hrv_time(peaks, sampling_rate=SAMPLING_RATE)
            rmssd = hrv_metrics['HRV_RMSSD'].values[0]
            return rmssd
        except Exception as e:
            self.logger.error(f"Error cálculo HRV: {e}")
            return None

    def is_valid_calibration(self, processed_result) -> bool:
        return processed_result is not None and processed_result > 0

    def get_calibration_value(self, processed_result):
        return processed_result

    def on_calibrated(self, baseline):
        self.baseline_rmssd = baseline
        self.logger.info(f"CALIBRADO. Baseline RMSSD: {self.baseline_rmssd:.2f} ms")

    def determine_state(self, current_rmssd):
        """Aplica la Ley de Yerkes-Dodson basada en reglas"""
        if current_rmssd is None or self.baseline_rmssd is None:
            return "UNCERTAIN"
        ratio = current_rmssd / self.baseline_rmssd
        if ratio < THRESHOLD_STRESS:
            return "STRESS (Overload)"
        elif ratio > THRESHOLD_BOREDOM:
            return "BOREDOM (Low Arousal)"
        else:
            return "FLOW (Optimal)"

    def publish(self, message_data):
        """Publica métricas al topic processed-ecg y a Redis"""
        current_rmssd = self.process_window()
        if current_rmssd is None:
            return
        state = self.determine_state(current_rmssd)
        wesad_label = message_data.get('label', '?')
        data = {
            "signal": "ecg",
            "rmssd": round(current_rmssd, 2),
            "baseline": round(self.baseline_rmssd, 2),
            "ratio": round(current_rmssd / self.baseline_rmssd, 2),
            "state": state,
            "timestamp": time.time(),
            "wesad_label": wesad_label
        }
        self.publish_to_kafka_and_redis(data)
        self.logger.info(f"RMSSD: {current_rmssd:.2f} | Base: {self.baseline_rmssd:.2f} | Estado: {state} (Label: {wesad_label})")


if __name__ == "__main__":
    time.sleep(5)
    ECGProcessor().run()
