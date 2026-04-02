"""
Model Registry — unified interface for loading and running inference
with any of the 7 CIFAR-10 CNN models.

Usage:
    registry = ModelRegistry(weights_dir="models/weights")
    model = registry.load("resnet20", device="cuda")
    probs, label = registry.infer(model, image_tensor)
"""

import os
import torch
import torch.nn.functional as F

from models.architectures import (
    resnet20, resnet56,
    vgg11_bn,
    densenet40_12,
    wide_resnet_28_2,
    mobilenetv2,
    preact_resnet18,
    pyramidnet110_48,
)

CIFAR10_CLASSES = [
    "airplane", "automobile", "bird", "cat", "deer",
    "dog", "frog", "horse", "ship", "truck"
]

_REGISTRY = {
    "resnet20":          resnet20,
    "resnet56":          resnet56,
    "vgg11_bn":          vgg11_bn,
    "densenet40_12":     densenet40_12,
    "wide_resnet_28_2":  wide_resnet_28_2,
    "mobilenetv2":       mobilenetv2,
    "preact_resnet18":   preact_resnet18,
    "pyramidnet110_48":  pyramidnet110_48,
}


class ModelRegistry:
    def __init__(self, weights_dir: str = "models/weights"):
        self.weights_dir = weights_dir

    def available(self) -> list[str]:
        """Return list of all registered model names."""
        return list(_REGISTRY.keys())

    def load(self, name: str, device: str = "cpu") -> torch.nn.Module:
        """
        Load a model by name and move it to device.
        Weights are loaded from weights_dir/<name>.pth if it exists.
        """
        if name not in _REGISTRY:
            raise ValueError(f"Unknown model '{name}'. Available: {self.available()}")

        model = _REGISTRY[name](num_classes=10)

        weights_path = os.path.join(self.weights_dir, f"{name}.pth")
        if os.path.exists(weights_path):
            state = torch.load(weights_path, map_location=device)
            model.load_state_dict(state)
        else:
            raise FileNotFoundError(
                f"No weights found at '{weights_path}'. "
                f"Run scratch/train_cifar10_models.py to generate them."
            )

        model.to(device)
        model.eval()
        return model

    def infer(self, model: torch.nn.Module, x: torch.Tensor) -> tuple[torch.Tensor, int]:
        """
        Run inference on a single image tensor or a batch.
        x: Tensor of shape (C, H, W) or (N, C, H, W), values normalized to [-1, 1]

        Returns:
            probs: Tensor of shape (10,) or (N, 10) — class probabilities
            label: int or list[int] — predicted class index
        """
        if x.dim() == 3:
            x = x.unsqueeze(0)
            squeeze = True
        else:
            squeeze = False

        with torch.no_grad():
            logits = model(x)
            probs = F.softmax(logits, dim=1)

        if squeeze:
            probs = probs.squeeze(0)
            return probs, probs.argmax().item()
        else:
            labels = probs.argmax(dim=1).tolist()
            return probs, labels

    def model_info(self, name: str) -> dict:
        """Return metadata for a given model."""
        if name not in _REGISTRY:
            raise ValueError(f"Unknown model '{name}'.")
        model = _REGISTRY[name](num_classes=10)
        n_params = sum(p.numel() for p in model.parameters())
        return {
            "name": name,
            "parameters": n_params,
            "dataset": "CIFAR-10",
            "classes": CIFAR10_CLASSES,
        }
