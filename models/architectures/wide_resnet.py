"""
Wide Residual Network (WideResNet-28-2) for CIFAR-10 — Zagoruyko & Komodakis (2016)
depth=28, widen_factor=2, dropout=0.3
"""

import torch.nn as nn
import torch.nn.functional as F


class WideBasicBlock(nn.Module):
    def __init__(self, in_planes, planes, stride=1, dropout=0.3):
        super().__init__()
        self.bn1 = nn.BatchNorm2d(in_planes)
        self.conv1 = nn.Conv2d(in_planes, planes, 3, stride=stride, padding=1, bias=False)
        self.dropout = nn.Dropout(dropout)
        self.bn2 = nn.BatchNorm2d(planes)
        self.conv2 = nn.Conv2d(planes, planes, 3, stride=1, padding=1, bias=False)

        self.shortcut = nn.Sequential()
        if stride != 1 or in_planes != planes:
            self.shortcut = nn.Conv2d(in_planes, planes, 1, stride=stride, bias=False)

    def forward(self, x):
        out = self.dropout(self.conv1(F.relu(self.bn1(x))))
        out = self.conv2(F.relu(self.bn2(out)))
        out += self.shortcut(x)
        return out


class WideResNet(nn.Module):
    def __init__(self, depth, widen_factor, dropout=0.3, num_classes=10):
        super().__init__()
        assert (depth - 4) % 6 == 0, "depth must be 6n+4"
        n = (depth - 4) // 6
        widths = [16, 16 * widen_factor, 32 * widen_factor, 64 * widen_factor]

        self.conv1 = nn.Conv2d(3, widths[0], 3, padding=1, bias=False)
        self.layer1 = self._make_layer(widths[0], widths[1], n, stride=1, dropout=dropout)
        self.layer2 = self._make_layer(widths[1], widths[2], n, stride=2, dropout=dropout)
        self.layer3 = self._make_layer(widths[2], widths[3], n, stride=2, dropout=dropout)
        self.bn_final = nn.BatchNorm2d(widths[3])
        self.fc = nn.Linear(widths[3], num_classes)

    def _make_layer(self, in_planes, planes, n, stride, dropout):
        layers = [WideBasicBlock(in_planes, planes, stride=stride, dropout=dropout)]
        for _ in range(1, n):
            layers.append(WideBasicBlock(planes, planes, stride=1, dropout=dropout))
        return nn.Sequential(*layers)

    def forward(self, x):
        out = self.conv1(x)
        out = self.layer1(out)
        out = self.layer2(out)
        out = self.layer3(out)
        out = F.relu(self.bn_final(out))
        out = F.adaptive_avg_pool2d(out, 1)
        out = out.view(out.size(0), -1)
        return self.fc(out)


def wide_resnet_28_2(num_classes=10):
    return WideResNet(depth=28, widen_factor=2, dropout=0.3, num_classes=num_classes)
