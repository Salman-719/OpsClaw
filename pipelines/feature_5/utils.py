"""
utils.py – Shared helpers: logging setup and path resolution.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Return a logger with a consistent format."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s – %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


def resolve_output_dir(base: str | Path, sub: str = "outputs/feature_5") -> Path:
    """Resolve and create the output directory under *base* (repo root)."""
    out = Path(base) / sub
    out.mkdir(parents=True, exist_ok=True)
    return out


def repo_root() -> Path:
    """Walk up from this file to find the repo root (contains pipelines/)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pipelines").is_dir():
            return parent
    return here.parents[2]  # fallback: 3 levels up from feature_5/
