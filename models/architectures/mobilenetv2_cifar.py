"""
MobileNetV2 for CIFAR-10 — Sandler et al. (2018)
Adapted for 32x32 input: initial conv stride=1, no early downsampling.
"""

import torch.nn as nn


def _make_divisible(v, divisor=8):
    return max(divisor, int(v + divisor / 2) // divisor * divisor)


class InvertedResidual(nn.Module):
    def __init__(self, in_channels, out_channels, stride, expand_ratio):
        super().__init__()
        self.use_residual = stride == 1 and in_channels == out_channels
        hidden = int(in_channels * expand_ratio)

        layers = []
        if expand_ratio != 1:
            layers += [
                nn.Conv2d(in_channels, hidden, 1, bias=False),
                nn.BatchNorm2d(hidden),
                nn.ReLU6(inplace=True)
            ]
        layers += [
            nn.Conv2d(hidden, hidden, 3, stride=stride, padding=1, groups=hidden, bias=False),
            nn.BatchNorm2d(hidden),
            nn.ReLU6(inplace=True),
            nn.Conv2d(hidden, out_channels, 1, bias=False),
            nn.BatchNorm2d(out_channels)
        ]
        self.conv = nn.Sequential(*layers)

    def forward(self, x):
        if self.use_residual:
            return x + self.conv(x)
        return self.conv(x)


# (expand_ratio, out_channels, n_blocks, stride)
INVERTED_RESIDUAL_CFG = [
    (1,  16, 1, 1),
    (6,  24, 2, 1),  # stride 1 instead of 2 (CIFAR-10 adaptation)
    (6,  32, 3, 2),
    (6,  64, 4, 2),
    (6,  96, 3, 1),
    (6, 160, 3, 2),
    (6, 320, 1, 1),
]


class MobileNetV2(nn.Module):
    def __init__(self, num_classes=10):
        super().__init__()
        # stride=1 for 32x32 input (original uses stride=2 for ImageNet)
        self.conv_stem = nn.Sequential(
            nn.Conv2d(3, 32, 3, stride=1, padding=1, bias=False),
            nn.BatchNorm2d(32),
            nn.ReLU6(inplace=True)
        )

        layers = []
        in_channels = 32
        for t, c, n, s in INVERTED_RESIDUAL_CFG:
            for i in range(n):
                stride = s if i == 0 else 1
                layers.append(InvertedResidual(in_channels, c, stride=stride, expand_ratio=t))
                in_channels = c
        self.layers = nn.Sequential(*layers)

        self.conv_head = nn.Sequential(
            nn.Conv2d(320, 1280, 1, bias=False),
            nn.BatchNorm2d(1280),
            nn.ReLU6(inplace=True)
        )
        self.classifier = nn.Linear(1280, num_classes)

    def forward(self, x):
        out = self.conv_stem(x)
        out = self.layers(out)
        out = self.conv_head(out)
        out = out.mean(dim=[2, 3])  # global average pool
        return self.classifier(out)


def mobilenetv2(num_classes=10):
    return MobileNetV2(num_classes=num_classes)
