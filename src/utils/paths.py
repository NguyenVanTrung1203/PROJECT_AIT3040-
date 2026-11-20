"""Resolve project paths independently of the caller's working directory."""
import os
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def resolve_dataset_root(root=None, default='./DATASET_FINAL'):
    value = root if root is not None else os.environ.get('DATASET_ROOT', default)
    path = Path(value).expanduser()
    return (path if path.is_absolute() else REPOSITORY_ROOT / path).resolve()
