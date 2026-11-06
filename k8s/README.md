# k8s/ (shared)

Kubernetes manifests. ArgoCD watches this folder on `main` and deploys whatever it finds. Direct `kubectl apply` is not allowed for service deployment (task d).

One subfolder per service, added by its owner, e.g. `k8s/partition-manager/`, `k8s/sensor-store/`.
