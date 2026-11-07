# k8s/ (shared)

Kubernetes manifests (YAML files describing the desired state of the app).

```
k8s/
├── base/     the real app: what ArgoCD deploys on GKE (point ArgoCD at k8s/base)
│   ├── namespace.yaml                 namespace "s1"
│   ├── sensor-store/                  StatefulSet (4 ring nodes, 1 disk each) + headless Service
│   ├── partition-manager/             Deployment + Service + HPA (2-6 pods, 50% CPU)
│   └── telemetry-ingestion/hpa.yaml   HPA #2, enabled once Person 2's Deployment exists
└── local/    laptop version for Docker Desktop: base + metrics-server + localhost entry + file membership
```

Each person adds their own services under `base/<service>/` and lists them in `base/kustomization.yaml`.

## Run on the laptop (Docker Desktop Kubernetes)

```powershell
docker compose build sensor-store-0 partition-manager   # images (Kubernetes uses the same local images)
kubectl apply -k k8s/local                              # create everything
kubectl get pods -n s1 -w                               # watch them start (Ctrl+C to stop watching)
kubectl get hpa -n s1                                   # CPU % vs target, current pods
```

Load test (makes the HPA scale out): `k6 run loadtest/pm-write.js`

Clean up: `kubectl delete -k k8s/local`
