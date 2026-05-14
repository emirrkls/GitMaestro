#!/usr/bin/env sh
# Qwen 3.5 / 3.6 on Ollama — see https://ollama.com/library/qwen3.5/tags
set -e
for m in \
  qwen3.5:latest \
  qwen3.5:35b-a3b-coding-nvfp4 \
  qwen3.6:27b-coding-nvfp4
do
  echo "Pulling $m ..."
  ollama pull "$m"
done
