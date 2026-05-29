"""Tests for the PARSeq OCR adapter loader (Issue #131).

The adapter wraps a torch checkpoint, so the only thing we can (and must) test
without torch/weights is the **graceful-fallback contract**: when the variant
is not ``parseq-ocr``, or the checkpoint / torch is unavailable, the loader
returns ``None`` so ``stage_reid`` keeps using Tesseract. This also guards the
critical invariant that importing the module never pulls torch into pytest
collection.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.tracking import parseq_ocr_adapter
from pipeline.tracking.parseq_ocr_adapter import PARSEQ_PREFIX, get_parseq_adapter


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("REID_OCR_MODEL", raising=False)
    yield
    monkeypatch.delenv("REID_OCR_MODEL", raising=False)


def test_module_imports_without_torch() -> None:
    # If this import dragged torch in, pytest collection would already fail.
    assert hasattr(parseq_ocr_adapter, "PARSeqOCRAdapter")
    assert PARSEQ_PREFIX == "parseq:"


def test_get_parseq_adapter_none_when_unset() -> None:
    assert get_parseq_adapter() is None


def test_get_parseq_adapter_none_for_non_parseq_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REID_OCR_MODEL", "tesseract")
    assert get_parseq_adapter() is None


def test_get_parseq_adapter_none_when_weights_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    # parseq: scheme but the checkpoint does not exist -> falls back to None.
    monkeypatch.setenv("REID_OCR_MODEL", f"{PARSEQ_PREFIX}{tmp_path / 'nope.pt'}")
    assert get_parseq_adapter() is None


def test_constructor_raises_file_not_found_for_missing_weights(tmp_path) -> None:
    from pipeline.tracking.parseq_ocr_adapter import PARSeqOCRAdapter

    with pytest.raises(FileNotFoundError):
        PARSeqOCRAdapter(str(tmp_path / "missing.pt"))
