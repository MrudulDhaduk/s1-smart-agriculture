#!/usr/bin/env bash
# Build service images, push them to Artifact Registry tagged with the git commit, and point
# k8s/gke at the new tags. Deploying is then a Git change like any other: commit
# k8s/gke/kustomization.yaml, open a PR, and ArgoCD rolls it out once it is merged.
#
#   one-time:  gcloud auth configure-docker us-central1-docker.pkg.dev
#   usage:     tools/build_push.sh farm-registry sensor-registry ...
#
# Works for every service whose image has a line in k8s/gke/kustomization.yaml.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
KUSTOMIZATION=k8s/gke/kustomization.yaml

[ $# -gt 0 ] || { echo "usage: $0 <service> [service...]"; exit 1; }

for svc in "$@"; do
  line=$(grep -E "name: s1/$svc," "$KUSTOMIZATION") || { echo "no image line for s1/$svc in $KUSTOMIZATION"; exit 1; }
  repo=$(sed -E 's/.*newName: ([^,]+),.*/\1/' <<<"$line")

  # The tag must say exactly which code is inside, so uncommitted changes are refused.
  if [ -n "$(git status --porcelain -- "services/$svc" services/web-common contracts tools/gen_protos.py)" ]; then
    echo "services/$svc (or contracts/, web-common/) has uncommitted changes: commit first"; exit 1
  fi
  tag=$(git rev-parse --short=10 HEAD)

  docker build -f "services/$svc/Dockerfile" -t "$repo:$tag" .
  docker push "$repo:$tag"
  sed -i -E "s|(name: s1/$svc, newName: [^,]+, newTag: )\"[^\"]*\"|\1\"$tag\"|" "$KUSTOMIZATION"
  echo "$svc -> $repo:$tag"
done

echo
echo "Next: git add $KUSTOMIZATION && git commit -m 'Deploy ...' && open a PR. ArgoCD deploys after merge."
