#!/usr/bin/env bash
# Start a work session: GKE + Dataproc (cluster stack), then ArgoCD and its apps (platform stack).
# The persistent stacks (bootstrap, foundation, kafka, serverless) stay up between sessions.
# Every apply prints its plan and waits for "yes".
#
#   export PROJECT=<project-id>; time infra/scripts/up.sh
set -euo pipefail
: "${PROJECT:?export PROJECT=<project-id> first}"
cd "$(dirname "$0")/.."

for stack in cluster platform; do
  echo "=== $stack"
  terraform -chdir="$stack" init -input=false -backend-config="bucket=$PROJECT-tfstate" >/dev/null
  terraform -chdir="$stack" apply
done

eval "$(terraform -chdir=cluster output -raw get_credentials)"
echo
echo "ArgoCD UI:       $(terraform -chdir=platform output -raw argocd_ui)"
echo "ArgoCD password: $(terraform -chdir=platform output -raw argocd_password)"
echo "Public URL:      kubectl -n s1 get ingress s1-public   (address appears after ~5 min)"
