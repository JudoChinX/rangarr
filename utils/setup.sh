#!/bin/bash
set -e
cd "$(git rev-parse --show-toplevel)"

cp utils/pre-push.sh .git/hooks/pre-push
chmod +x .git/hooks/pre-push
echo "pre-push hook installed successfully!"
