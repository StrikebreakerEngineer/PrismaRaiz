from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "datos"
DATABASE_FILE = DATA_DIR / "baseDeDatos" / "léxico.db"
RAW_DATA_DIR = DATA_DIR / "sinProcesar"
EXPORT_DIR = DATA_DIR / "exportaciones"
LOG_DIR = DATA_DIR / "registros"