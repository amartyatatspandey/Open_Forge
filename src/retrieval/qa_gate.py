from __future__ import annotations

from pydantic import BaseModel, Field


class QAResult(BaseModel):
    passed: bool
    failed_parameters: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    confidence_below_threshold: list[str] = Field(default_factory=list)


class QAGate:
    CONFIDENCE_THRESHOLD = 0.70

    SANITY_RANGES: dict[str, tuple[float, float]] = {
        "en": (0.1, 5000.0),
        "VOS_drift": (0.001, 1000.0),
        "PSRR": (0.0, 150.0),
        "TC": (0.001, 500.0),
        "V_CC": (0.5, 60.0),
        "I_CC": (0.001, 5000.0),
        "T_J": (-55.0, 175.0),
    }

    def run(self, parameters: list[dict]) -> QAResult:
        failed_parameters: list[str] = []
        warnings: list[str] = []
        confidence_below_threshold: list[str] = []

        for param in parameters:
            name = param.get("parameter_name", "unknown")
            confidence = param.get("confidence", 1.0)
            if confidence < self.CONFIDENCE_THRESHOLD:
                failed_parameters.append(name)
                confidence_below_threshold.append(name)

            value_min = param.get("value_min")
            value_max = param.get("value_max")
            if value_min is not None and value_max is not None and value_min > value_max:
                failed_parameters.append(name)

            symbol = param.get("symbol")
            if symbol and symbol in self.SANITY_RANGES:
                low, high = self.SANITY_RANGES[symbol]
                for field in ("value_typ", "value_max"):
                    val = param.get(field)
                    if val is not None and (val < low or val > high):
                        if name not in warnings:
                            warnings.append(name)

        passed = len(failed_parameters) == 0
        return QAResult(
            passed=passed,
            failed_parameters=list(dict.fromkeys(failed_parameters)),
            warnings=warnings,
            confidence_below_threshold=confidence_below_threshold,
        )
