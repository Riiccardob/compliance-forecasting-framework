from src.phase1.stat_forecaster import StatForecaster
print(hasattr(StatForecaster, "predict_adaptive"))
import inspect
if hasattr(StatForecaster, "predict_adaptive"):
    print(inspect.signature(StatForecaster.predict_adaptive))