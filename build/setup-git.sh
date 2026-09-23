#!/bin/sh
# Run once per clone so `git diff` shows contract wording, not "binary files differ".
cd "$(dirname "$0")/.." || exit 1
git config diff.docx.textconv "python3 $(pwd)/build/docxtext.py"
git config diff.docx.cachetextconv true
echo "docx diffs enabled - try: git log -p template/atp-website.docx"
