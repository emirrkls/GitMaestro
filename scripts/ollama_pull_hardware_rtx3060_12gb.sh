#!/usr/bin/env sh
# Fits typical 12GB VRAM setups; skip tags you do not need.
set -e
for m in qwen3.5:latest qwen2.5-coder:7b qwen2.5-coder:14b; do
  echo "Pulling $m ..."
  ollama pull "$m"
done
