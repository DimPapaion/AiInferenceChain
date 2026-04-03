"""
ImageStore — content-addressed storage for inference images.

Images are stored by SHA-256(raw_bytes) so any node can verify integrity.
The hash is committed on-chain in the INFERENCE_REQUEST tx (image_hash field).

When a QoI round starts, each DNN validator:
  1. Fetches the image from the store by its hash
  2. Runs inference to get their probability vector
  3. Participates in QoI consensus

Storage layout:
  data/images/<first2>/<remaining62>.bin
  e.g. sha256=abcdef... → data/images/ab/cdef....bin

This is the same layout used by git object storage — efficient and hash-verified.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

DEFAULT_IMAGE_DIR = Path("data") / "images"


class ImageStore:
    """
    Content-addressed binary store for inference images.
    Thread-safe (no shared mutable state beyond the filesystem).
    """

    def __init__(self, base_dir: Path | str = DEFAULT_IMAGE_DIR) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ── Store ─────────────────────────────────────────────────────────────────

    def put(self, image_bytes: bytes) -> str:
        """
        Store raw image bytes and return their SHA-256 hex hash.
        Idempotent — storing the same bytes twice is a no-op.
        """
        h    = hashlib.sha256(image_bytes).hexdigest()
        path = self._path(h)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(image_bytes)
            log.debug("Stored image %s… (%d bytes)", h[:12], len(image_bytes))
        return h

    # ── Retrieve ──────────────────────────────────────────────────────────────

    def get(self, image_hash: str) -> Optional[bytes]:
        """
        Retrieve image bytes by hash.
        Returns None if not found locally (must be fetched from a peer).
        """
        path = self._path(image_hash)
        if not path.exists():
            return None
        data = path.read_bytes()
        # Verify integrity
        actual = hashlib.sha256(data).hexdigest()
        if actual != image_hash:
            log.error("Image integrity failure: expected %s got %s", image_hash[:12], actual[:12])
            path.unlink(missing_ok=True)
            return None
        return data

    def has(self, image_hash: str) -> bool:
        return self._path(image_hash).exists()

    # ── Tensor helper (for DNN inference) ────────────────────────────────────

    def get_tensor(self, image_hash: str):
        """
        Load image bytes and convert to a normalised PyTorch tensor.
        Returns None if image not found locally.
        Raises RuntimeError if PIL/torch not available.
        """
        data = self.get(image_hash)
        if data is None:
            return None
        try:
            import io
            import torch
            import torchvision.transforms as T
            from PIL import Image as PILImage

            img = PILImage.open(io.BytesIO(data)).convert("RGB")
            transform = T.Compose([
                T.Resize((32, 32)),
                T.ToTensor(),
                T.Normalize((0.4914, 0.4822, 0.4465),
                             (0.2023, 0.1994, 0.2010)),
            ])
            return transform(img).unsqueeze(0)   # (1, C, H, W)
        except Exception as e:
            raise RuntimeError(f"Failed to load image tensor for {image_hash[:12]}: {e}")

    # ── Stats ─────────────────────────────────────────────────────────────────

    def count(self) -> int:
        return sum(1 for _ in self.base_dir.rglob("*.bin"))

    def total_bytes(self) -> int:
        return sum(p.stat().st_size for p in self.base_dir.rglob("*.bin"))

    # ── Internal ──────────────────────────────────────────────────────────────

    def _path(self, image_hash: str) -> Path:
        return self.base_dir / image_hash[:2] / (image_hash[2:] + ".bin")

    def __repr__(self) -> str:
        return f"ImageStore({self.base_dir}, count={self.count()})"
