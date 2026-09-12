"""Corrected causal entry point; see docs/C题_修正版本说明.md."""
from __future__ import annotations
import json
from .dispatch import Policy, forecast_vector, plan_segment, run as run_policy


def run(output=None, pv_scale: float = 1.0):
    return run_policy('4-2', output=output, policy=Policy(pv_scale=pv_scale))


if __name__ == "__main__":
    print(json.dumps(run()["summary"], ensure_ascii=False, indent=2))
