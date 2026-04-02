"""
GPU Setup Verification Script
Checks if CUDA, GPU, and PyTorch are properly configured before running training
"""

import torch
import sys

print("=" * 80)
print("GPU SETUP VERIFICATION")
print("=" * 80 + "\n")

# Check PyTorch and CUDA
print("✓ PyTorch Version:", torch.__version__)
print("✓ CUDA Available:", torch.cuda.is_available())

if not torch.cuda.is_available():
    print("\n[ERROR] CUDA is not available!")
    print("You need to install:")
    print("  1. NVIDIA GPU Driver")
    print("  2. CUDA Toolkit")
    print("  3. cuDNN")
    print("  4. PyTorch with CUDA support")
    sys.exit(1)

print("✓ CUDA Version:", torch.version.cuda)
print("✓ cuDNN Version:", torch.backends.cudnn.version())

# Check GPUs
num_gpus = torch.cuda.device_count()
print(f"✓ Number of GPUs: {num_gpus}\n")

if num_gpus == 0:
    print("[ERROR] No GPUs found!")
    sys.exit(1)

# List GPUs
for i in range(num_gpus):
    print(f"GPU {i}: {torch.cuda.get_device_name(i)}")
    props = torch.cuda.get_device_properties(i)
    print(f"  Memory: {props.total_memory / 1e9:.2f} GB")
    print(f"  Compute Capability: {props.major}.{props.minor}\n")

# Test GPU
print("Testing GPU computation...")
try:
    x = torch.randn(1000, 1000).cuda()
    y = torch.randn(1000, 1000).cuda()
    z = torch.matmul(x, y)
    print("✓ GPU computation test passed!")
except Exception as e:
    print(f"[ERROR] GPU computation failed: {e}")
    sys.exit(1)

print("\n" + "=" * 80)
print("ALL GPU CHECKS PASSED! Ready to train!")
print("=" * 80)
print("\nRun the training script with:")
print("  python train_cifar10_gpu.py")
