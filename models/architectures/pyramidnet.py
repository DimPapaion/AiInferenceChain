"""
PyramidNet for CIFAR-10 — Han et al. (2017)
Gradually widens channels across all layers (alpha=48, depth=110, bottleneck=False).
"""

import torch.nn as nn
import torch.nn.functional as F
import math


class PyramidBasicBlock(nn.Module):
    outchannel_ratio = 1

    def __init__(self, in_planes, planes, stride=1):
        super().__init__()
        self.bn1 = nn.BatchNorm2d(in_planes)
        self.conv1 = nn.Conv2d(in_planes, planes, 3, stride=stride, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(planes)
        self.conv2 = nn.Conv2d(planes, planes, 3, stride=1, padding=1, bias=False)
        self.bn3 = nn.BatchNorm2d(planes)

        self.shortcut = nn.Sequential()
        if stride != 1 or in_planes != planes:
            self.shortcut = nn.Sequential(
                nn.AvgPool2d(stride, stride, ceil_mode=True),
                nn.BatchNorm2d(in_planes)
            )
            self._pad = planes - in_planes
        else:
            self._pad = 0

    def forward(self, x):
        out = self.conv1(F.relu(self.bn1(x)))
        out = self.conv2(F.relu(self.bn2(out)))
        out = self.bn3(out)

        shortcut = self.shortcut(x)
        if self._pad > 0:
            # Zero-pad the shortcut to match channel dimension
            import torch
            shortcut = torch.cat([shortcut, shortcut.new_zeros(
                shortcut.size(0), self._pad, shortcut.size(2), shortcut.size(3)
            )], dim=1)
        return F.relu(out + shortcut)


class PyramidNet(nn.Module):
    def __init__(self, depth=110, alpha=48, num_classes=10):
        super().__init__()
        assert (depth - 2) % 6 == 0, "depth must be 6n+2"
        n = (depth - 2) // 6

        self.in_planes = 16
        step = alpha / (3 * n)  # channel increment per layer

        self.conv1 = nn.Conv2d(3, 16, 3, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(16)

        self.layer1 = self._make_layer(n, stride=1, step=step, start=0)
        self.layer2 = self._make_layer(n, stride=2, step=step, start=n)
        self.layer3 = self._make_layer(n, stride=2, step=step, start=2 * n)

        final_planes = 16 + int(round(alpha))
        self.bn_final = nn.BatchNorm2d(self.in_planes)
        self.fc = nn.Linear(self.in_planes, num_classes)

    def _make_layer(self, n, stride, step, start):
        layers = []
        for i in range(n):
            planes = 16 + int(round(step * (start + i + 1)))
            s = stride if i == 0 else 1
            layers.append(PyramidBasicBlock(self.in_planes, planes, stride=s))
            self.in_planes = planes
        return nn.Sequential(*layers)

    def forward(self, x):
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.layer1(out)
        out = self.layer2(out)
        out = self.layer3(out)
        out = F.relu(self.bn_final(out))
        out = F.adaptive_avg_pool2d(out, 1)
        out = out.view(out.size(0), -1)
        return self.fc(out)


def pyramidnet110_48(num_classes=10):
    return PyramidNet(depth=110, alpha=48, num_classes=num_classes)
