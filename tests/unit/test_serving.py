"""
Unit tests for core/serving/image_store.py (ImageStore).
"""

import hashlib

import pytest

from core.serving.image_store import ImageStore


SAMPLE_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100   # fake PNG header + padding


class TestImageStore:
    def test_put_returns_sha256(self, tmp_path):
        store = ImageStore(base_dir=tmp_path / "images")
        h = store.put(SAMPLE_BYTES)
        assert h == hashlib.sha256(SAMPLE_BYTES).hexdigest()

    def test_put_is_idempotent(self, tmp_path):
        store = ImageStore(base_dir=tmp_path / "images")
        h1 = store.put(SAMPLE_BYTES)
        h2 = store.put(SAMPLE_BYTES)
        assert h1 == h2
        assert store.count() == 1

    def test_get_returns_original_bytes(self, tmp_path):
        store = ImageStore(base_dir=tmp_path / "images")
        h = store.put(SAMPLE_BYTES)
        retrieved = store.get(h)
        assert retrieved == SAMPLE_BYTES

    def test_get_missing_returns_none(self, tmp_path):
        store = ImageStore(base_dir=tmp_path / "images")
        assert store.get("a" * 64) is None

    def test_has(self, tmp_path):
        store = ImageStore(base_dir=tmp_path / "images")
        h = store.put(SAMPLE_BYTES)
        assert store.has(h) is True
        assert store.has("b" * 64) is False

    def test_integrity_check_corrupted_file(self, tmp_path):
        store = ImageStore(base_dir=tmp_path / "images")
        h = store.put(SAMPLE_BYTES)
        # Corrupt the stored file
        path = store._path(h)
        path.write_bytes(b"corrupted data")
        # get() should detect mismatch, delete the file, and return None
        assert store.get(h) is None
        assert not path.exists()

    def test_count_and_total_bytes(self, tmp_path):
        store = ImageStore(base_dir=tmp_path / "images")
        assert store.count() == 0
        assert store.total_bytes() == 0

        store.put(SAMPLE_BYTES)
        assert store.count() == 1
        assert store.total_bytes() == len(SAMPLE_BYTES)

        store.put(b"another image")
        assert store.count() == 2

    def test_path_layout(self, tmp_path):
        """Files are split into 2-char prefix dirs (git-style layout)."""
        store = ImageStore(base_dir=tmp_path / "images")
        h = store.put(SAMPLE_BYTES)
        expected = tmp_path / "images" / h[:2] / (h[2:] + ".bin")
        assert expected.exists()

    def test_get_tensor_missing_returns_none(self, tmp_path):
        store = ImageStore(base_dir=tmp_path / "images")
        result = store.get_tensor("c" * 64)
        assert result is None
