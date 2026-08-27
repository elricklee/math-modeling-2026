from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
FIGURES_DIR = ROOT / "figures"
REPORTS_DIR = ROOT / "reports"
RESULTS_DIR = ROOT / "results"

