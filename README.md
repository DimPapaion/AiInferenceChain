# CIFAR-10 GPU Training Script

Complete test scripts for training a simple CNN on CIFAR-10 dataset using CUDA GPU acceleration.

## Files

1. **check_gpu_setup.py** - Verifies GPU and CUDA configuration
2. **train_cifar10_gpu.py** - Main training script for CNN on CIFAR-10
3. **requirements.txt** - Python package dependencies

## Prerequisites

### System Requirements
- NVIDIA GPU (with CUDA Compute Capability 3.5+)
- NVIDIA GPU Driver installed
- CUDA Toolkit installed (11.8 or higher recommended)
- cuDNN installed

### Software Setup

1. **Install PyTorch with CUDA support:**
   ```bash
   # For CUDA 11.8
   pip install torch==2.0.1 torchvision==0.15.2 --index-url https://download.pytorch.org/whl/cu118
   
   # Or for CUDA 12.1
   pip install torch==2.0.1 torchvision==0.15.2 --index-url https://download.pytorch.org/whl/cu121
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Step 1: Verify GPU Setup
Run the verification script first to ensure everything is configured correctly:

```bash
python check_gpu_setup.py
```

You should see output showing:
- ✓ GPU availability confirmed
- ✓ CUDA and cuDNN versions
- ✓ GPU device name and memory
- ✓ GPU computation test passed

### Step 2: Run Training
If verification passes, start the training:

```bash
python train_cifar10_gpu.py
```

This will:
1. **Detect and Display GPU Information:**
   - GPU model name
   - CUDA version
   - cuDNN version
   - Total GPU memory
   - Current device being used

2. **Initialize Model:**
   - Simple 3-layer CNN architecture
   - All tensors **explicitly moved to GPU** with `.to(device)`

3. **Train on CIFAR-10:**
   - Download dataset automatically (first run)
   - Train for 5 epochs
   - Uses 128 batch size with `pin_memory=True` for GPU optimization
   - Validates GPU placement of tensors
   - Saves best model to `best_model_gpu.pth`

4. **Display Results:**
   - Training and test loss
   - Accuracy metrics
   - GPU memory usage statistics

## Key GPU Features

✓ **Automatic GPU Detection** - Finds and lists all available GPUs
✓ **Explicit GPU Placement** - All tensors and models verified on GPU
✓ **GPU Memory Monitoring** - Tracks memory usage during training
✓ **Optimized for GPU** - 
  - cuDNN auto-tuner enabled (`cudnn.benchmark = True`)
  - Pinned memory in data loaders
  - Non-blocking tensor transfers
✓ **No CPU Fallback** - Script exits if GPU not available

## Troubleshooting

### ERROR: No GPU detected
- Check NVIDIA driver: `nvidia-smi`
- Verify CUDA installation
- Check PyTorch CUDA version matches your CUDA Toolkit

### ERROR: CUDA out of memory
- Reduce `batch_size` in the script (currently 128)
- Reduce model size or number of epochs

### ERROR: CUDA driver error
- Update NVIDIA drivers
- Restart your system
- Check GPU is not already in use by another process

## Model Architecture

Simple CNN with:
- 3 Convolutional blocks (32, 64, 128 filters)
- 3 Max pooling layers
- 3 Fully connected layers (256, 128, 10)
- ReLU activations
- Dropout regularization

## Performance Notes

- First run downloads ~170MB CIFAR-10 dataset
- Training time depends on GPU (typically 2-5 minutes per epoch)
- Best accuracy achieved: ~70-75% after 5 epochs
- GPU memory usage: ~3-5 GB during training

---

**IMPORTANT:** This script is designed to run EXCLUSIVELY on GPU. It will not fall back to CPU and will exit if no CUDA GPU is detected.
