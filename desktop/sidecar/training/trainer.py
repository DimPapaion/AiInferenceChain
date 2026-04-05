"""
Training engine — runs a full training loop and streams metrics as SSE.
"""
import asyncio
import json
import os
import time
import importlib.util
import tempfile
import traceback
from pathlib import Path
from typing import AsyncGenerator

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader

# ── Global state (one training run at a time) ─────────────────────────────────
_run_state: dict = {"active": False, "cancel": False, "metrics": []}


def _load_model_from_source(source: str, num_classes: int, tmp_dir: str) -> nn.Module:
    fpath = os.path.join(tmp_dir, "_user_arch.py")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(source)
    spec = importlib.util.spec_from_file_location("_user_arch", fpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    candidates = [
        v for v in vars(mod).values()
        if isinstance(v, type) and issubclass(v, nn.Module) and v is not nn.Module
    ]
    if not candidates:
        raise ValueError("No nn.Module subclass found.")
    cls = candidates[0]
    try:
        return cls(num_classes=num_classes)
    except TypeError:
        return cls()


def _make_optimizer(model: nn.Module, config: dict) -> optim.Optimizer:
    name = config.get("optimizer", "adam").lower()
    lr = float(config.get("lr", 1e-3))
    wd = float(config.get("weight_decay", 1e-4))
    if name == "sgd":
        return optim.SGD(model.parameters(), lr=lr, momentum=0.9, weight_decay=wd)
    if name == "adamw":
        return optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
    return optim.Adam(model.parameters(), lr=lr, weight_decay=wd)


def _make_scheduler(optimizer: optim.Optimizer, config: dict, epochs: int):
    name = config.get("scheduler", "none").lower()
    if name == "cosine":
        return optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    if name == "step":
        return optim.lr_scheduler.StepLR(optimizer, step_size=max(1, epochs // 3), gamma=0.1)
    return None


def _make_loss(config: dict):
    name = config.get("loss", "crossentropy").lower().replace(" ", "").replace("-", "")
    if name == "focalloss":
        # Simple focal loss implementation (no extra deps)
        class FocalLoss(nn.Module):
            def __init__(self, gamma=2.0):
                super().__init__()
                self.gamma = gamma
            def forward(self, inp, target):
                ce = nn.functional.cross_entropy(inp, target, reduction="none")
                p = torch.exp(-ce)
                return ((1 - p) ** self.gamma * ce).mean()
        return FocalLoss()
    if name == "labelsmoothing":
        return nn.CrossEntropyLoss(label_smoothing=0.1)
    return nn.CrossEntropyLoss()


def _make_transforms(config: dict, split: str = "train"):
    from torchvision import transforms
    aug = config.get("augmentation", "none").lower()
    base = [transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])]

    if split != "train" or aug == "none":
        return transforms.Compose([transforms.Resize((32, 32))] + base)

    if aug == "light":
        return transforms.Compose([
            transforms.Resize((36, 36)),
            transforms.RandomCrop(32),
            transforms.RandomHorizontalFlip(),
        ] + base)

    # heavy
    return transforms.Compose([
        transforms.Resize((40, 40)),
        transforms.RandomCrop(32),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2),
        transforms.RandomRotation(15),
    ] + base)


def _load_datasets(dataset_info: dict, config: dict):
    from torchvision.datasets import ImageFolder
    from datasets import load_dataset

    source = dataset_info.get("source")
    batch_size = int(config.get("batch_size", 64))

    train_transform = _make_transforms(config, "train")
    val_transform = _make_transforms(config, "val")

    if source == "huggingface":
        from datasets import load_dataset
        from torch.utils.data import Dataset as TorchDataset

        raw = load_dataset(dataset_info["dataset_name"])
        train_split = raw.get("train") or raw[list(raw.keys())[0]]
        val_split = raw.get("validation") or raw.get("test")

        class HFDataset(TorchDataset):
            def __init__(self, hf_split, transform):
                self.data = hf_split
                self.transform = transform
                self.label_key = "label" if "label" in hf_split.features else "fine_label"
                self.img_key = "img" if "img" in hf_split.features else "image"

            def __len__(self): return len(self.data)

            def __getitem__(self, idx):
                item = self.data[idx]
                img = item[self.img_key].convert("RGB")
                if self.transform:
                    img = self.transform(img)
                return img, item[self.label_key]

        train_ds = HFDataset(train_split, train_transform)
        val_ds = HFDataset(val_split, val_transform) if val_split else None
    else:
        root = dataset_info.get("extracted_root", "")
        train_ds = ImageFolder(os.path.join(root, "train"), transform=train_transform)
        val_path = os.path.join(root, "val")
        if not os.path.isdir(val_path):
            val_path = os.path.join(root, "test")
        val_ds = ImageFolder(val_path, transform=val_transform) if os.path.isdir(val_path) else None

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True,
                              num_workers=2, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False,
                            num_workers=2, pin_memory=True) if val_ds else None
    return train_loader, val_loader


def is_active() -> bool:
    return _run_state["active"]


def cancel_run():
    _run_state["cancel"] = True


async def run_training(
    arch_source: str,
    dataset_info: dict,
    config: dict,
    checkpoint_dir: str,
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields SSE-formatted JSON lines.
    Each event: {"type": "epoch"|"done"|"error", ...}
    """
    _run_state.update({"active": True, "cancel": False, "metrics": []})

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    epochs = int(config.get("epochs", 30))
    num_classes = int(dataset_info.get("num_classes", 10))

    try:
        with tempfile.TemporaryDirectory() as tmp:
            model = _load_model_from_source(arch_source, num_classes, tmp)

        model = model.to(device)
        optimizer = _make_optimizer(model, config)
        scheduler = _make_scheduler(optimizer, config, epochs)
        criterion = _make_loss(config)
        train_loader, val_loader = _load_datasets(dataset_info, config)

        ckpt_dir = Path(checkpoint_dir)
        ckpt_dir.mkdir(parents=True, exist_ok=True)

        for epoch in range(1, epochs + 1):
            if _run_state["cancel"]:
                yield f"data: {json.dumps({'type':'cancelled'})}\n\n"
                break

            # Train
            model.train()
            total_loss, correct, total = 0.0, 0, 0
            t0 = time.time()

            for xb, yb in train_loader:
                if _run_state["cancel"]:
                    break
                xb, yb = xb.to(device), yb.to(device)
                optimizer.zero_grad()
                out = model(xb)
                loss = criterion(out, yb)
                loss.backward()
                optimizer.step()

                total_loss += loss.item() * xb.size(0)
                preds = out.argmax(1)
                correct += (preds == yb).sum().item()
                total += xb.size(0)

                # Yield control to event loop periodically
                await asyncio.sleep(0)

            if scheduler:
                scheduler.step()

            train_loss = total_loss / max(total, 1)
            train_acc = correct / max(total, 1)

            # Validate
            val_loss, val_acc = None, None
            if val_loader:
                model.eval()
                v_loss, v_correct, v_total = 0.0, 0, 0
                with torch.no_grad():
                    for xb, yb in val_loader:
                        xb, yb = xb.to(device), yb.to(device)
                        out = model(xb)
                        v_loss += criterion(out, yb).item() * xb.size(0)
                        v_correct += (out.argmax(1) == yb).sum().item()
                        v_total += xb.size(0)
                        await asyncio.sleep(0)
                val_loss = v_loss / max(v_total, 1)
                val_acc = v_correct / max(v_total, 1)

            epoch_secs = time.time() - t0

            # Save checkpoint every 5 epochs
            if epoch % 5 == 0 or epoch == epochs:
                ckpt_path = ckpt_dir / f"checkpoint_epoch{epoch:03d}.pth"
                torch.save({"epoch": epoch, "model_state": model.state_dict(),
                            "optimizer_state": optimizer.state_dict()}, ckpt_path)

            metric = {
                "type": "epoch",
                "epoch": epoch,
                "total_epochs": epochs,
                "train_loss": round(train_loss, 4),
                "train_acc": round(train_acc, 4),
                "val_loss": round(val_loss, 4) if val_loss is not None else None,
                "val_acc": round(val_acc, 4) if val_acc is not None else None,
                "epoch_secs": round(epoch_secs, 1),
            }
            _run_state["metrics"].append(metric)
            yield f"data: {json.dumps(metric)}\n\n"

        # Final checkpoint path
        final_ckpt = str(ckpt_dir / f"checkpoint_epoch{epochs:03d}.pth")
        yield f"data: {json.dumps({'type':'done','checkpoint':final_ckpt,'metrics':_run_state['metrics']})}\n\n"

    except Exception:
        err = traceback.format_exc(limit=6)
        yield f"data: {json.dumps({'type':'error','error':err})}\n\n"
    finally:
        _run_state["active"] = False
