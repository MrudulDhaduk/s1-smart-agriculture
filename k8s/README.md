# k8s/ (shared)

Kubernetes manifests (YAML files describing the desired state of the app).

```
k8s/
├── base/     the app, environment-neutral (each person's services, listed in base/kustomization.yaml)
│   ├── namespace.yaml                 namespace "s1"
│   ├── sensor-store/                  StatefulSet (4 ring nodes, 1 disk each) + headless Service + PodDisruptionBudget + NetworkPolicy   (P3)
│   ├── partition-manager/             Deployment + Service + HPA (2-6 pods, 50% CPU) + PodDisruptionBudget + ServiceAccount     (P3)
│   ├── telemetry-ingestion/           Deployment + Service (P2) + HPA #2 (2-6 pods, 50% CPU, P3)
│   ├── farm-analytics/                Deployment + Service (P2)
│   └── farm-registry/, sensor-registry/, irrigation-controller/   (P1)
├── gke/      what ArgoCD deploys on GKE (Application "s1", from main): base + Artifact Registry image tags,
│             Workload Identity, Secrets from Secret Manager, and the public Ingress (P1)
└── local/    laptop version for Docker Desktop: base + metrics-server + localhost entry + file membership on a small disk (P3)
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
