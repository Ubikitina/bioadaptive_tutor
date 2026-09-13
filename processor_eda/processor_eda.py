import time
import numpy as np
import neurokit2 as nk

from common.base_processor import BaseProcessor
from common.config import SAMPLING_RATE


class EDAProcessor(BaseProcessor):
    def __init__(self):
        super().__init__(
            signal_name="eda",
            topic_output="processed-eda",
            group_id="eda-processor"
        )
        self.baseline_scl = None

    def extract_value(self, message_data: dict):
        return message_data.get('eda')

    def process_window(self):
        """Procesa la señal EDA: extrae SCL (tónico) y cuenta de picos SCR (fásico)"""
        eda_signal = np.array(self.buffer)
        try:
            eda_signals, info = nk.eda_process(eda_signal, sampling_rate=SAMPLING_RATE)
            
            # SCL = componente tónico (nivel basal de conductancia)
            scl = eda_signals['EDA_Tonic'].mean()
            
            # SCR = picos del componente fásico (respuestas puntuales)
            scr_count = 0
            if 'SCR_Peaks' in eda_signals.columns:
                scr_count = int(eda_signals['SCR_Peaks'].sum())
            
            return scl, scr_count
        except Exception as e:
            self.logger.error(f"Error procesamiento: {e}")
            return None, None

    def is_valid_calibration(self, processed_result) -> bool:
        scl, _ = processed_result if processed_result != (None, None) else (None, None)
        return scl is not None and scl > 0

    def get_calibration_value(self, processed_result):
        scl, _ = processed_result
        return scl

    def on_calibrated(self, baseline):
        self.baseline_scl = baseline
        self.logger.info(f"CALIBRADO. Baseline SCL: {self.baseline_scl:.4f}")

    def publish(self, message_data):
        """Publica métricas al topic processed-eda y a Redis"""
        result = self.process_window()
        scl, scr_count = result if result != (None, None) else (None, None)
        if scl is None:
            return
        scl_ratio = round(scl / self.baseline_scl, 2) if self.baseline_scl else None
        data = {
            "signal": "eda",
            "scl": round(scl, 4),
            "scl_baseline": round(self.baseline_scl, 4),
            "scl_ratio": scl_ratio,
            "scr_peaks": scr_count,
            "timestamp": time.time()
        }
        self.publish_to_kafka_and_redis(data)
        ratio = scl / self.baseline_scl if self.baseline_scl else 0
        self.logger.info(f"SCL: {scl:.4f} | Base: {self.baseline_scl:.4f} | Ratio: {ratio:.2f} | SCR Peaks: {scr_count}")


if __name__ == "__main__":
    time.sleep(5)
    EDAProcessor().run()
