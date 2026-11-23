#!/usr/bin/env bash
# Clone the public repositories the evaluation reads, at the commits used in the paper. Nothing of them is
# redistributed here. Usage:
#   bash scripts/setup_external.sh            # InterA11y (D2) and rampa-cli (D3, D6): enough for `python -m eval.reproduce`
#   bash scripts/setup_external.sh --d5-apps  # also the ten D5 apps (only needed to re-run D5)
# Location: $ACCESSGRAPH_EXTERNAL (default ~/w4a-external), as in eval/paths.py.
set -euo pipefail
BASE="${ACCESSGRAPH_EXTERNAL:-$HOME/w4a-external}"
mkdir -p "$BASE"

clone_at() {  # url, folder, commit
  local url="$1" dir="$BASE/$2" commit="$3"
  if [ ! -d "$dir/.git" ]; then git clone --quiet "$url" "$dir"; fi
  git -C "$dir" fetch --quiet origin "$commit" 2>/dev/null || git -C "$dir" fetch --quiet --all
  git -C "$dir" checkout --quiet "$commit"
  echo "$2 at $(git -C "$dir" rev-parse --short=7 HEAD)"
}

clone_at https://github.com/jszh/InterA11y.git InterA11y 8dcf06e
clone_at https://github.com/guilhermebsantiago/rampa-cli.git rampa-cli df32363

if [ "${1:-}" = "--d5-apps" ]; then
  mkdir -p "$BASE/d5-apps"
  BASE="$BASE/d5-apps"
  clone_at https://github.com/trungvose/jira-clone-angular.git jira-clone-angular 20b50e9
  clone_at https://github.com/realworld-apps/angular-realworld-example-app.git angular-realworld-example-app d426ec8
  clone_at https://github.com/tomalaforge/angular-challenges.git angular-challenges 0deb691
  clone_at https://github.com/angular-university/angular-ssr-course.git angular-ssr-course 0ac05b4
  clone_at https://github.com/angular-university/angular-course.git angular-course 53d20ad
  clone_at https://github.com/epicmaxco/vuestic-admin.git vuestic-admin 9c5b44f
  clone_at https://github.com/themesberg/flowbite-svelte-admin-dashboard.git flowbite-svelte-admin-dashboard 171b17e
  clone_at https://github.com/marmelab/react-admin.git react-admin a44d692
  echo "Install each app as listed in eval/d5_apps.yaml (install:), with install scripts disabled."
fi
