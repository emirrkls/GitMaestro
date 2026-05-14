#!/usr/bin/env sh
# Suggested Qwen / coder models for GitMaestro (Ollama)
# Qwen 3.5 / 3.6: ./scripts/ollama_pull_qwen_nextgen.sh
set -e
for m in \
  qwen2.5-coder:7b \
  qwen2.5-coder:14b \
  qwen3-coder:latest \
  qwen3-coder:30b
do
  echo "Pulling $m ..."
  ollama pull "$m"
done
