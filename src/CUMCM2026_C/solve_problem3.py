"""Corrected causal entry point; see docs/C题_修正版本说明.md."""
from __future__ import annotations
import json
from .dispatch import Policy, forecast_vector, plan_segment, run as run_policy


def run(output=None, pv_scale: float = 0.85):
    return run_policy('3', output=output,
                      policy=Policy(history_days=14, load_quantile=1.0,
                                    historical_pv_quantile=0.2,
                                    pv_scale=pv_scale, known_daily_load=True,
                                    terminal_target_kwh=6000.0))


if __name__ == "__main__":
    print(json.dumps(run()["summary"], ensure_ascii=False, indent=2))
