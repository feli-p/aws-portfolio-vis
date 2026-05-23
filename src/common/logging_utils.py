
"""
logging_utils.py

Configura logging consistente (archivo + consola).
"""

import logging
from datetime import datetime
from pathlib import Path


def setup_logger(log_prefix: str) -> logging.Logger:
    """Configura y retorna un logger para el script indicado."""
    # src/common/logging_utils.py -> parents[2] = raíz del repo
    project_root = Path(__file__).resolve().parents[2]
    log_dir = project_root / "artifacts" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"{log_prefix}_{timestamp}.log"

    logger = logging.getLogger(log_prefix)
    logger.setLevel(logging.INFO)
    logger.propagate = False  # evita duplicados por el root logger

    # Si ya está configurado, no vuelvas a agregar handlers
    if logger.handlers:
        return logger

    fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Archivo
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)

    # Consola
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)

    logger.info("Logger inicializado. Archivo: %s", log_path)
    return logger