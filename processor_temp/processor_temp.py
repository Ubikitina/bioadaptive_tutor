import time
import numpy as np

from common.base_processor import BaseProcessor


class TempProcessor(BaseProcessor):
    def __init__(self):
        super().__init__(
            signal_name="temp",
            topic_output="processed-temp",
            group_id="temp-processor"
        )
        self.baseline_temp = None
        self.prev_mean = None  # Para calcular tendencia

    def extract_value(self, message_data: dict):
        return message_data.get('temp')

    def process_window(self):
        """Calcula media y tendencia de la temperatura"""
        temp_array = np.array(self.buffer)
        mean_temp = float(np.mean(temp_array))
        
        # Tendencia: comparar media actual con la media anterior
        trend = "stable"
        if self.prev_mean is not None:
            diff = mean_temp - self.prev_mean
            if diff > 0.05:
                trend = "rising"
            elif diff < -0.05:
                trend = "falling"
        
        self.prev_mean = mean_temp
        return mean_temp, trend

    def is_valid_calibration(self, processed_result) -> bool:
        mean_temp, _ = processed_result
        return mean_temp is not None and mean_temp > 0

    def get_calibration_value(self, processed_result):
        mean_temp, _ = processed_result
        return mean_temp

    def on_calibrated(self, baseline):
        self.baseline_temp = baseline
        self.logger.info(f"CALIBRADO. Baseline: {self.baseline_temp:.3f} °C")

    def publish(self, message_data):
        """Publica métricas al topic processed-temp y a Redis"""
        mean_temp, trend = self.process_window()
        delta = round(mean_temp - self.baseline_temp, 3) if self.baseline_temp else 0
        data = {
            "signal": "temp",
            "temp_mean": round(mean_temp, 3),
            "temp_baseline": round(self.baseline_temp, 3),
            "temp_delta": delta,
            "trend": trend,
            "timestamp": time.time()
        }
        self.publish_to_kafka_and_redis(data)
        self.logger.info(f"Mean: {mean_temp:.3f} °C | Base: {self.baseline_temp:.3f} | Delta: {delta:+.3f} | Trend: {trend}")


if __name__ == "__main__":
    time.sleep(5)
    TempProcessor().run()
