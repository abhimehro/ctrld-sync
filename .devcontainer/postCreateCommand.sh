#! /usr/bin/env bash
set -euo pipefail

sudo apk add --no-cache bash curl

curl -LsSf https://astral.sh/uv/install.sh | sh
# shellcheck disable=SC1091
source "${HOME}/.local/bin/env" 2>/dev/null || export PATH="${HOME}/.local/bin:${PATH}"

uv sync --all-extras
uv run pre-commit install --install-hooks
