"""Locate bundled data files regardless of how the package was installed.

The catalogues (schemes, knowledge, disease symptoms, market snapshot) must be
readable in three very different layouts:

* a source checkout / editable install, where they live in ``ml-service/data``;
* a plain ``pip install .``, where only files declared as *package data* exist,
  inside ``site-packages/agrotech_ml/data``;
* a container whose working directory is the service root.

The previous code used ``Path(__file__).parents[3] / "data"``, which silently
resolves into ``site-packages`` on a non-editable install: every catalogue came
back empty in production while working perfectly in development. Resolution now
tries the packaged copy first, then the repo layout, then the CWD.
"""
from __future__ import annotations

from pathlib import Path

_PACKAGE_DATA_DIR = Path(__file__).resolve().parent / "data"
_REPO_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def data_file(name: str) -> Path:
    """Return the first existing path for bundled data file ``name``.

    Falls back to the packaged location so callers get a stable path (and a
    legible ``FileNotFoundError``) even when the file is genuinely absent.
    """
    for candidate in (
        _PACKAGE_DATA_DIR / name,
        _REPO_DATA_DIR / name,
        Path.cwd() / "data" / name,
    ):
        if candidate.is_file():
            return candidate
    return _PACKAGE_DATA_DIR / name


__all__ = ["data_file"]
