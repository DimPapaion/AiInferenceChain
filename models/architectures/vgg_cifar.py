"""
VGG-11 with Batch Normalization for CIFAR-10.
Adapted for 32x32 input: FC layers resized accordingly.
"""

import torch.nn as nn


CFG = [64, 'M', 128, 'M', 256, 256, 'M', 512, 512, 'M', 512, 512, 'M']


def _make_layers(cfg):
    layers = []
    in_channels = 3
    for v in cfg:
        if v == 'M':
            layers.append(nn.MaxPool2d(kernel_size=2, stride=2))
        else:
            layers += [
                nn.Conv2d(in_channels, v, kernel_size=3, padding=1),
                nn.BatchNorm2d(v),
                nn.ReLU(inplace=True)
            ]
            in_channels = v
    return nn.Sequential(*layers)


class VGG11BN(nn.Module):
    def __init__(self, num_classes=10):
        super().__init__()
        self.features = _make_layers(CFG)
        # After 5 MaxPool2d on 32x32 input: 32 / 2^5 = 1x1
        self.classifier = nn.Sequential(
            nn.Linear(512, 512),
            nn.ReLU(inplace=True),
            nn.Dropout(0.5),
            nn.Linear(512, 512),
            nn.ReLU(inplace=True),
            nn.Dropout(0.5),
            nn.Linear(512, num_classes)
        )

    def forward(self, x):
        out = self.features(x)
        out = out.view(out.size(0), -1)
        return self.classifier(out)


def vgg11_bn(num_classes=10):
    return VGG11BN(num_classes=num_classes)
