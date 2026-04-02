"""
CIFAR-10 CNN Training Script with GPU Support (CUDA)
This script trains a simple CNN model on CIFAR-10 dataset using GPU acceleration
"""

import torch
import torch.nn as nn
import torch.optim as optim
import torchvision.transforms as transforms
import torchvision.datasets as datasets
from torch.utils.data import DataLoader
import os
import sys

print("=" * 80)
print("GPU/DirectML CONFIGURATION AND CHECK (AMD RADEON)")
print("=" * 80)

# 1. Check GPU Availability
print(f"\nPyTorch Version: {torch.__version__}")
print(f"CUDA Available: {torch.cuda.is_available()}")

# Try to use DirectML for AMD GPU
try:
    import torch_directml
    device = torch_directml.device()
    print(f"DirectML Available: True")
    print(f"Using DirectML Device for AMD GPU")
except ImportError:
    print(f"DirectML NOT Available! Install: pip install torch-directml")
    device = torch.device('cpu')
    print(f"Falling back to CPU")

# Alternative: Try CUDA if available
if torch.cuda.is_available():
    device = torch.device('cuda')
    print(f"CUDA Available: {torch.cuda.is_available()}")
    print(f"CUDA Version: {torch.version.cuda}")
    print(f"cuDNN Version: {torch.backends.cudnn.version()}")
    
    # Get number of GPUs
    num_gpus = torch.cuda.device_count()
    print(f"Number of GPUs Available: {num_gpus}")
    
    if num_gpus > 0:
        # List all available GPUs
        for i in range(num_gpus):
            print(f"\nGPU {i}:")
            print(f"  Name: {torch.cuda.get_device_name(i)}")
            print(f"  Capability: {torch.cuda.get_device_capability(i)}")
            props = torch.cuda.get_device_properties(i)
            print(f"  Total Memory: {props.total_memory / 1e9:.2f} GB")
            print(f"  Compute Capability: {props.major}.{props.minor}")
        
        # 2. Set GPU Device
        print(f"\nUsing Device: {device}")
        print(f"Current GPU: {torch.cuda.get_device_name(0)}")
        print(f"Current GPU Index: {torch.cuda.current_device()}")
        
        # 3. Configure CUDA settings for optimal performance
        torch.cuda.set_device(0)  # Set primary GPU
        torch.backends.cudnn.benchmark = True  # Enable cuDNN auto-tuner for performance
        torch.backends.cudnn.enabled = True
        print(f"cuDNN Enabled: {torch.backends.cudnn.enabled}")
        print(f"cuDNN Benchmark: {torch.backends.cudnn.benchmark}")

print(f"\n✓ Device Type: {device}")
print(f"✓ Training will run on: {str(device).upper()}")

print("\n" + "=" * 80)
print("MODEL AND TRAINING SETUP")
print("=" * 80 + "\n")

# 4. Define Simple CNN Model
class SimpleCNN(nn.Module):
    def __init__(self):
        super(SimpleCNN, self).__init__()
        # Convolutional layers
        self.conv1 = nn.Conv2d(3, 32, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
        self.conv3 = nn.Conv2d(64, 128, kernel_size=3, padding=1)
        
        # Pooling
        self.pool = nn.MaxPool2d(2, 2)
        
        # Fully connected layers
        self.fc1 = nn.Linear(128 * 4 * 4, 256)
        self.fc2 = nn.Linear(256, 128)
        self.fc3 = nn.Linear(128, 10)  # 10 classes for CIFAR-10
        
        # Activation and Dropout
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(0.5)
        
    def forward(self, x):
        # Convolutional blocks
        x = self.pool(self.relu(self.conv1(x)))
        x = self.pool(self.relu(self.conv2(x)))
        x = self.pool(self.relu(self.conv3(x)))
        
        # Flatten
        x = x.view(x.size(0), -1)
        
        # Fully connected layers
        x = self.dropout(self.relu(self.fc1(x)))
        x = self.dropout(self.relu(self.fc2(x)))
        x = self.fc3(x)
        
        return x

# 5. Initialize Model on GPU
print("Initializing Model...")
model = SimpleCNN()
model = model.to(device)  # Move model to GPU
print(f"Model moved to: {next(model.parameters()).device}")
print(f"Total parameters: {sum(p.numel() for p in model.parameters()):,}")

# 6. Data Preparation
print("\nPreparing CIFAR-10 Dataset...")
transform = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
])

train_dataset = datasets.CIFAR10(root='./data', train=True, download=True, transform=transform)
test_dataset = datasets.CIFAR10(root='./data', train=False, download=True, transform=transform)

batch_size = 128
train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=0)
test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False, num_workers=0)

print(f"Training samples: {len(train_dataset)}")
print(f"Test samples: {len(test_dataset)}")
print(f"Batch size: {batch_size}")

# 7. Loss and Optimizer
criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(model.parameters(), lr=0.001)

# 8. Training Function
def train_epoch(epoch):
    model.train()
    running_loss = 0.0
    correct = 0
    total = 0
    
    for batch_idx, (inputs, labels) in enumerate(train_loader):
        # Move data to GPU/Device
        inputs, labels = inputs.to(device), labels.to(device)
        
        # Verify on device
        assert str(inputs.device) != 'cpu', "Input tensor not on GPU/DirectML!"
        assert str(labels.device) != 'cpu', "Labels tensor not on GPU/DirectML!"
        
        # Forward pass
        optimizer.zero_grad()
        outputs = model(inputs)
        loss = criterion(outputs, labels)
        
        # Backward pass
        loss.backward()
        optimizer.step()
        
        # Statistics
        running_loss += loss.item()
        _, predicted = torch.max(outputs.data, 1)
        total += labels.size(0)
        correct += (predicted == labels).sum().item()
        
        if batch_idx % 50 == 0:
            print(f"  Batch [{batch_idx + 1}/{len(train_loader)}] | Loss: {loss.item():.4f}")
    
    avg_loss = running_loss / len(train_loader)
    accuracy = 100 * correct / total
    return avg_loss, accuracy

# 9. Test Function
@torch.no_grad()
def test_epoch():
    model.eval()
    correct = 0
    total = 0
    test_loss = 0.0
    
    for inputs, labels in test_loader:
        inputs, labels = inputs.to(device), labels.to(device)
        outputs = model(inputs)
        loss = criterion(outputs, labels)
        
        test_loss += loss.item()
        _, predicted = torch.max(outputs.data, 1)
        total += labels.size(0)
        correct += (predicted == labels).sum().item()
    
    avg_loss = test_loss / len(test_loader)
    accuracy = 100 * correct / total
    return avg_loss, accuracy

# 10. Training Loop
print("\n" + "=" * 80)
print("STARTING TRAINING ON GPU")
print("=" * 80 + "\n")

num_epochs = 5
best_accuracy = 0

try:
    for epoch in range(num_epochs):
        print(f"\nEpoch {epoch + 1}/{num_epochs}")
        print("-" * 40)
        
        # Check GPU memory (only for CUDA)
        if torch.cuda.is_available():
            print(f"GPU Memory Used: {torch.cuda.memory_allocated() / 1e9:.2f} GB")
        
        # Train
        train_loss, train_acc = train_epoch(epoch)
        
        # Test
        test_loss, test_acc = test_epoch()
        
        print(f"\nResults:")
        print(f"  Train Loss: {train_loss:.4f} | Train Acc: {train_acc:.2f}%")
        print(f"  Test Loss: {test_loss:.4f} | Test Acc: {test_acc:.2f}%")
        
        if test_acc > best_accuracy:
            best_accuracy = test_acc
            torch.save(model.state_dict(), 'best_model_gpu.pth')
            print(f"  ✓ Best model saved (Accuracy: {test_acc:.2f}%)")

except Exception as e:
    print(f"\n[ERROR] Training failed: {e}")
    sys.exit(1)

print("\n" + "=" * 80)
print("TRAINING COMPLETED")
print("=" * 80)
print(f"Best Test Accuracy: {best_accuracy:.2f}%")
if torch.cuda.is_available():
    print(f"GPU Memory Used (Final): {torch.cuda.memory_allocated() / 1e9:.2f} GB")

# Cleanup
if torch.cuda.is_available():
    torch.cuda.empty_cache()
print("\nGPU cache cleared. Training script completed successfully on GPU!")
