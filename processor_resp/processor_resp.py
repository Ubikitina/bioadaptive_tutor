import time
import numpy as np
import neurokit2 as nk

from common.base_processor import BaseProcessor
from common.config import SAMPLING_RATE


class RespProcessor(BaseProcessor):
    def __init__(self):
        super().__init__(
            signal_name="resp",
            topic_output="processed-resp",
            group_id="resp-processor"
        )
        self.baseline_rate = None

    def extract_value(self, message_data: dict):
        return message_data.get('resp')

    def process_window(self):
        """Procesa la señal respiratoria: extrae tasa y amplitud"""
        resp_signal = np.array(self.buffer)
        try:
            rsp_signals, info = nk.rsp_process(resp_signal, sampling_rate=SAMPLING_RATE)
            
            # Tasa respiratoria media (respiraciones por minuto)
            rate = rsp_signals['RSP_Rate'].dropna().mean()
            
            # Amplitud media (profundidad de la respiración)
            amplitude = None
            if 'RSP_Amplitude' in rsp_signals.columns:
                amplitude = rsp_signals['RSP_Amplitude'].dropna().mean()
            
            return rate, amplitude
        except Exception as e:
            self.logger.error(f"Error procesamiento: {e}")
            return None, None

    def is_valid_calibration(self, processed_result) -> bool:
        rate, _ = processed_result if processed_result != (None, None) else (None, None)
        return rate is not None and rate > 0

    def get_calibration_value(self, processed_result):
        rate, _ = processed_result
        return rate

    def on_calibrated(self, baseline):
        self.baseline_rate = baseline
        self.logger.info(f"CALIBRADO. Baseline Rate: {self.baseline_rate:.2f} bpm")

    def publish(self, message_data):
        """Publica métricas al topic processed-resp y a Redis"""
        result = self.process_window()
        rate, amplitude = result if result != (None, None) else (None, None)
        if rate is None:
            return
        rate_ratio = round(rate / self.baseline_rate, 2) if self.baseline_rate else None
        data = {
            "signal": "resp",
            "rate": round(rate, 2),
            "rate_baseline": round(self.baseline_rate, 2),
            "rate_ratio": rate_ratio,
            "amplitude": round(amplitude, 4) if amplitude else None,
            "timestamp": time.time()
        }
        self.publish_to_kafka_and_redis(data)
        ratio = rate / self.baseline_rate if self.baseline_rate else 0
        self.logger.info(f"Rate: {rate:.2f} bpm | Base: {self.baseline_rate:.2f} | Ratio: {ratio:.2f} | Amp: {amplitude}")


if __name__ == "__main__":
    time.sleep(5)
    RespProcessor().run()
