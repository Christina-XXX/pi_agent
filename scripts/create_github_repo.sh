#!/usr/bin/env bash
# 一键创建 GitHub 仓库并推送（需要先安装 GitHub CLI：gh）
# 用法：./scripts/create_github_repo.sh <仓库名> [--private]
set -euo pipefail

NAME="${1:-pi_agent}"
VISIBILITY="--public"
if [[ "${2:-}" == "--private" ]]; then
  VISIBILITY="--private"
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "未检测到 GitHub CLI（gh）。请先安装：https://cli.github.com/"
  echo "或手动在 github.com 新建仓库后执行："
  echo "  git remote add origin https://github.com/<你的用户名>/${NAME}.git"
  echo "  git branch -M main"
  echo "  git push -u origin main"
  exit 1
fi

gh auth status >/dev/null 2>&1 || { echo "请先登录：gh auth login"; exit 1; }

gh repo create "${NAME}" ${VISIBILITY} --source=. --push
echo "✅ 仓库已创建并推送完成。"
