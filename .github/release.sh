#!/usr/bin/env bash
# Decide whether the commits pushed since the last release make a new one, and how big.
# Rules (README "Versions and releases"):
#   1. A commit's `Release: major|minor|patch|none` trailer wins.
#   2. Without one: a subject starting "Stage <n>" that touches app files -> minor;
#      any other commit that touches app files -> patch; docs, tests, backtest/ and .github/ only -> none.
#   3. The biggest level among the commits is the release. "none" everywhere -> no release.
# Usage: release.sh [--dry-run]
set -euo pipefail

last=$(git describe --tags --abbrev=0 --match 'v[0-9]*' 2>/dev/null || echo v0.0.0)
range="$last..HEAD"
[ "$last" = v0.0.0 ] && range=HEAD
commits=$(git rev-list --reverse "$range")
[ -z "$commits" ] && { echo "No commits since $last."; exit 0; }

# Paths that change what the app does. Everything else (docs/, tests/, backtest/, .github/, *.md) doesn't.
is_app() { grep -Eq '^(stockreport/|bridge/|launchd/|config\.toml$|pyproject\.toml$|uv\.lock$)'; }
rank() { case $1 in major) echo 3;; minor) echo 2;; patch) echo 1;; *) echo 0;; esac; }

level=none
notes=""
for c in $commits; do
  subject=$(git log -1 --format=%s "$c")
  trailer=$(git log -1 --format=%B "$c" | sed -nE 's/^[Rr]elease:[[:space:]]*([A-Za-z]+)[[:space:]]*$/\1/p' | tail -1 | tr '[:upper:]' '[:lower:]')
  if [[ $trailer =~ ^(major|minor|patch|none)$ ]]; then
    l=$trailer
  elif git diff-tree --no-commit-id --name-only -r "$c" | is_app; then
    if [[ $subject =~ ^Stage\ [0-9]+ ]]; then l=minor; else l=patch; fi
  else
    l=none
  fi
  [ "$(rank "$l")" -gt "$(rank "$level")" ] && level=$l
  [ "$l" != none ] && notes+="- $subject (${c:0:7})"$'\n'
done

echo "Since $last: $level"
[ "$level" = none ] && exit 0

IFS=. read -r major minor patch <<<"${last#v}"
case $level in
  major) next="v$((major + 1)).0.0" ;;
  minor) next="v$major.$((minor + 1)).0" ;;
  patch) next="v$major.$minor.$((patch + 1))" ;;
esac

body="Changes since $last ($level release):"$'\n\n'"$notes"
if [ "${1:-}" = --dry-run ]; then
  echo "Would release $next"; echo "$body"; exit 0
fi
gh release create "$next" --target "$(git rev-parse HEAD)" --title "$next" --notes "$body"
echo "Released $next"
