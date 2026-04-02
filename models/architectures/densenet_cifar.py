"""
DenseNet-40 (growth_rate=12) for CIFAR-10 — Huang et al. (2017)
3 dense blocks, no bottleneck, no compression (DenseNet-40-12).
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class DenseLayer(nn.Module):
    def __init__(self, in_channels, growth_rate):
        super().__init__()
        self.bn = nn.BatchNorm2d(in_channels)
        self.conv = nn.Conv2d(in_channels, growth_rate, kernel_size=3, padding=1, bias=False)

    def forward(self, x):
        out = self.conv(F.relu(self.bn(x)))
        return torch.cat([x, out], dim=1)


class DenseBlock(nn.Module):
    def __init__(self, n_layers, in_channels, growth_rate):
        super().__init__()
        layers = []
        for i in range(n_layers):
            layers.append(DenseLayer(in_channels + i * growth_rate, growth_rate))
        self.block = nn.Sequential(*layers)

    def forward(self, x):
        return self.block(x)


class TransitionLayer(nn.Module):
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.bn = nn.BatchNorm2d(in_channels)
        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size=1, bias=False)
        self.pool = nn.AvgPool2d(kernel_size=2, stride=2)

    def forward(self, x):
        return self.pool(self.conv(F.relu(self.bn(x))))


class DenseNet40(nn.Module):
    def __init__(self, growth_rate=12, num_classes=10):
        super().__init__()
        # depth=40, 3 blocks: (40 - 4) / 3 = 12 layers per block
        n_layers = 12
        k = growth_rate
        n_channels = 2 * k  # initial channels = 2 * growth_rate = 24

        self.conv1 = nn.Conv2d(3, n_channels, kernel_size=3, padding=1, bias=False)

        # Block 1
        self.block1 = DenseBlock(n_layers, n_channels, k)
        n_channels += n_layers * k
        self.trans1 = TransitionLayer(n_channels, n_channels)

        # Block 2
        self.block2 = DenseBlock(n_layers, n_channels, k)
        n_channels += n_layers * k
        self.trans2 = TransitionLayer(n_channels, n_channels)

        # Block 3
        self.block3 = DenseBlock(n_layers, n_channels, k)
        n_channels += n_layers * k

        self.bn_final = nn.BatchNorm2d(n_channels)
        self.fc = nn.Linear(n_channels, num_classes)

    def forward(self, x):
        out = self.conv1(x)
        out = self.trans1(self.block1(out))
        out = self.trans2(self.block2(out))
        out = self.block3(out)
        out = F.relu(self.bn_final(out))
        out = F.adaptive_avg_pool2d(out, 1)
        out = out.view(out.size(0), -1)
        return self.fc(out)


def densenet40_12(num_classes=10):
    return DenseNet40(growth_rate=12, num_classes=num_classes)
