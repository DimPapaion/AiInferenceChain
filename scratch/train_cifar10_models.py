"""
scratch/train_cifar10_models.py

Trains all 7 CIFAR-10 CNN models and saves weights to models/weights/.
Run from the project root: python scratch/train_cifar10_models.py

NOT part of the InferenceChain protocol — helper script only.
"""

import os
import sys
import time
import torch
import torch.nn as nn
import torch.optim as optim
import torchvision
import torchvision.transforms as transforms
from torch.utils.data import DataLoader

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from models.architectures import (
    resnet20, resnet56,
    vgg11_bn,
    densenet40_12,
    wide_resnet_28_2,
    mobilenetv2,
    preact_resnet18,
    pyramidnet110_48,
)

# ── Config ────────────────────────────────────────────────────────────────────
WEIGHTS_DIR = os.path.join(os.path.dirname(__file__), "..", "models", "weights")
DATA_DIR    = os.path.join(os.path.dirname(__file__), "..", "data")
EPOCHS      = 100
BATCH_SIZE  = 128
LR          = 0.1
MOMENTUM    = 0.9
WEIGHT_DECAY = 5e-4

MODELS = {
    "resnet20":         resnet20,
    "resnet56":         resnet56,
    "vgg11_bn":         vgg11_bn,
    "densenet40_12":    densenet40_12,
    "wide_resnet_28_2": wide_resnet_28_2,
    "mobilenetv2":      mobilenetv2,
    "preact_resnet18":  preact_resnet18,
    "pyramidnet110_48": pyramidnet110_48,
}

# ── Data ──────────────────────────────────────────────────────────────────────
train_transform = transforms.Compose([
    transforms.RandomCrop(32, padding=4),
    transforms.RandomHorizontalFlip(),
    transforms.ToTensor(),
    transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
])

test_transform = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
])

train_set = torchvision.datasets.CIFAR10(DATA_DIR, train=True,  download=True, transform=train_transform)
test_set  = torchvision.datasets.CIFAR10(DATA_DIR, train=False, download=True, transform=test_transform)

train_loader = DataLoader(train_set, batch_size=BATCH_SIZE, shuffle=True,  num_workers=2, pin_memory=True)
test_loader  = DataLoader(test_set,  batch_size=BATCH_SIZE, shuffle=False, num_workers=2, pin_memory=True)

# ── Device ────────────────────────────────────────────────────────────────────
try:
    import torch_directml
    device = torch_directml.device()
    print("Using DirectML (AMD GPU)")
except ImportError:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

os.makedirs(WEIGHTS_DIR, exist_ok=True)

# ── Training ──────────────────────────────────────────────────────────────────
def train_one_epoch(model, optimizer, criterion):
    model.train()
    total_loss, correct, total = 0.0, 0, 0
    for inputs, labels in train_loader:
        inputs, labels = inputs.to(device), labels.to(device)
        optimizer.zero_grad()
        outputs = model(inputs)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
        correct += outputs.argmax(1).eq(labels).sum().item()
        total += labels.size(0)
    return total_loss / len(train_loader), 100.0 * correct / total


@torch.no_grad()
def evaluate(model):
    model.eval()
    correct, total = 0, 0
    for inputs, labels in test_loader:
        inputs, labels = inputs.to(device), labels.to(device)
        correct += model(inputs).argmax(1).eq(labels).sum().item()
        total += labels.size(0)
    return 100.0 * correct / total


def train_model(name, model_fn):
    weights_path = os.path.join(WEIGHTS_DIR, f"{name}.pth")
    if os.path.exists(weights_path):
        print(f"[{name}] weights already exist, skipping.")
        return

    print(f"\n{'='*60}")
    print(f"Training: {name}")
    print(f"{'='*60}")

    model = model_fn(num_classes=10).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"Parameters: {n_params:,}")

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.SGD(model.parameters(), lr=LR, momentum=MOMENTUM, weight_decay=WEIGHT_DECAY)
    scheduler = optim.lr_scheduler.MultiStepLR(optimizer, milestones=[50, 75], gamma=0.1)

    best_acc = 0.0
    t0 = time.time()

    for epoch in range(1, EPOCHS + 1):
        train_loss, train_acc = train_one_epoch(model, optimizer, criterion)
        scheduler.step()

        if epoch % 10 == 0 or epoch == EPOCHS:
            test_acc = evaluate(model)
            elapsed = time.time() - t0
            print(f"  Epoch {epoch:3d}/{EPOCHS} | loss {train_loss:.4f} | train {train_acc:.1f}% | test {test_acc:.1f}% | {elapsed:.0f}s")

            if test_acc > best_acc:
                best_acc = test_acc
                torch.save(model.state_dict(), weights_path)

    print(f"[{name}] Best test accuracy: {best_acc:.2f}% — saved to {weights_path}")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="all", help="Model name or 'all'")
    args = parser.parse_args()

    if args.model == "all":
        for name, fn in MODELS.items():
            train_model(name, fn)
    else:
        if args.model not in MODELS:
            print(f"Unknown model '{args.model}'. Choose from: {list(MODELS.keys())}")
            sys.exit(1)
        train_model(args.model, MODELS[args.model])

    print("\nAll done.")
