"""
Dataset loading and validation.
Supports:
  - ImageFolder layout: train/class_a/img.jpg, val/class_b/img.jpg
  - HuggingFace dataset name  (e.g. "cifar10", "imagenet-1k")
"""
import os
import tempfile
import urllib.request
import zipfile
import tarfile
from pathlib import Path
from typing import Optional

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def detect_imagefolder(root: str):
    """
    Returns class names and split counts if root looks like ImageFolder layout.
    Expects root/train/<class>/ and root/val/<class>/ (or root/test/).
    """
    root = Path(root)
    splits = {}
    class_names = None

    for split_name in ["train", "val", "test", "valid"]:
        split_dir = root / split_name
        if not split_dir.is_dir():
            continue
        classes = sorted(
            d.name for d in split_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
        if not classes:
            continue
        counts = {}
        for cls in classes:
            cls_dir = split_dir / cls
            imgs = [
                f for f in cls_dir.iterdir()
                if f.suffix.lower() in SUPPORTED_EXTENSIONS
            ]
            counts[cls] = len(imgs)
        splits[split_name] = counts
        if class_names is None:
            class_names = classes

    return splits, class_names


def validate_dataset_url(url: str, num_classes: Optional[int] = None):
    """
    Validate a dataset URL or HuggingFace dataset name.
    Returns a dict describing what was found.
    """
    url = url.strip()

    # HuggingFace dataset name (no slashes, no http)
    if not url.startswith("http") and "/" not in url:
        return _validate_hf_dataset(url, num_classes)

    # Direct archive URL
    return _validate_url_archive(url, num_classes)


def _validate_hf_dataset(name: str, num_classes: Optional[int]):
    try:
        from datasets import load_dataset_builder
        builder = load_dataset_builder(name)
        info = builder.info
        features = info.features or {}
        label_names = []

        for feat in features.values():
            if hasattr(feat, "names"):
                label_names = list(feat.names)
                break

        return {
            "ok": True,
            "source": "huggingface",
            "dataset_name": name,
            "description": info.description[:200] if info.description else "",
            "num_classes": len(label_names) or num_classes,
            "class_names": label_names[:20],  # preview first 20
            "splits": list(info.splits.keys()) if info.splits else [],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _validate_url_archive(url: str, num_classes: Optional[int]):
    try:
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = os.path.join(tmp, "dataset_archive")
            urllib.request.urlretrieve(url, archive_path)

            extract_dir = os.path.join(tmp, "extracted")
            os.makedirs(extract_dir, exist_ok=True)

            if zipfile.is_zipfile(archive_path):
                with zipfile.ZipFile(archive_path) as zf:
                    zf.extractall(extract_dir)
            elif tarfile.is_tarfile(archive_path):
                with tarfile.open(archive_path) as tf:
                    tf.extractall(extract_dir)
            else:
                return {"ok": False, "error": "Unrecognised archive format (expected .zip or .tar.gz)."}

            splits, class_names = detect_imagefolder(extract_dir)

            if not splits:
                # Try one level deeper
                subdirs = [d for d in Path(extract_dir).iterdir() if d.is_dir()]
                for sub in subdirs:
                    splits, class_names = detect_imagefolder(str(sub))
                    if splits:
                        break

            if not splits:
                return {
                    "ok": False,
                    "error": "Could not detect ImageFolder layout. Expected train/<class>/ and val/<class>/ structure.",
                }

            total = {
                split: {cls: cnt for cls, cnt in classes.items()}
                for split, classes in splits.items()
            }
            return {
                "ok": True,
                "source": "url",
                "num_classes": len(class_names) if class_names else num_classes,
                "class_names": (class_names or [])[:20],
                "splits": total,
            }
    except Exception as e:
        return {"ok": False, "error": str(e)}
