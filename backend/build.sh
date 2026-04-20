#!/usr/bin/env bash
set -e

# Install CPU-only PyTorch first (150MB instead of 2GB+ with CUDA)
pip install torch --index-url https://download.pytorch.org/whl/cpu

# Then install everything else
pip install -r requirements.txt
