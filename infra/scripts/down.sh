#!/usr/bin/env bash
# End a work session: remove everything that is billed by the hour.
#
#   export PROJECT=<project-id>; infra/scripts/down.sh
#
# Order matters:
#   1. Remove ArgoCD first, otherwise it would recreate what step 2 deletes.
#   2. Delete the app namespaces while the cluster still exists. GKE removes the Ingress's
#      load balancer and the PersistentVolumeClaims' disks only when their Kubernetes objects
#      are deleted; destroying the cluster directly would leave both behind, still billed.
#   3. Destroy GKE and Dataproc.
set -euo pipefail
: "${PROJECT:?export PROJECT=<project-id> first}"
cd "$(dirname "$0")/.."

for stack in platform cluster; do
  terraform -chdir="$stack" init -input=false -backend-config="bucket=$PROJECT-tfstate" >/dev/null
done

eval "$(terraform -chdir=cluster output -raw get_credentials)"

echo "=== 1. ArgoCD"
terraform -chdir=platform destroy

echo "=== 2. app namespaces (load balancer, disks)"
kubectl delete namespace s1 monitoring --ignore-not-found --wait=true --timeout=10m

echo "=== 3. GKE + Dataproc"
terraform -chdir=cluster destroy

echo
echo "Left running: Cloud SQL (set sql_activation_policy=NEVER in foundation to stop it), Firestore, buckets, Aiven."
echo "Check Billing > Reports tomorrow."
