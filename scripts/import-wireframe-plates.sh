#!/usr/bin/env bash
# Build the pinned atlas in isolation using its committed npm lockfile.
set -euo pipefail
source_repo=${1:?Provide the path to a wireframe-3js checkout}
pin=94ed75af8b92fb63064c7fc5bb6c7ddb77acf7c9
destination="$(git rev-parse --show-toplevel)/src/static/wireframe/assets/vendor/plates"
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
git -C "$source_repo" archive "$pin" | tar -x -C "$scratch"
cd "$scratch"
make build
mkdir -p "$destination"
cp dist/wireframe-plate.js dist/posters/{15,25,29}.webp "$destination"
cp node_modules/three/LICENSE "$destination/three-LICENSE.txt"
