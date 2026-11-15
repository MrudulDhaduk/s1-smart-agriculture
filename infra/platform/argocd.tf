# GitOps (task d). Terraform installs ArgoCD and tells it which Git paths to follow; from then
# on every Kubernetes change is a commit on main, and ArgoCD applies it. Nobody runs kubectl apply.
resource "helm_release" "argocd" {
  name             = "argocd"
  namespace        = "argocd"
  create_namespace = true
  # OCI copy of the Argo charts on GitHub Container Registry: the classic chart repository serves
  # its files from GitHub release assets, which reset connections repeatedly from our network.
  repository = "oci://ghcr.io/argoproj/argo-helm"
  chart      = "argo-cd"
  version    = "10.11.1" # ArgoCD v3.5.6

  values = [yamlencode({
    dex           = { enabled = false } # no SSO: log in as admin through kubectl port-forward
    notifications = { enabled = false }
    configs = {
      params = { "server.insecure" = true }         # TLS is unnecessary behind port-forward
      cm     = { "timeout.reconciliation" = "60s" } # poll Git every minute (default 3 min)
    }
  })]
}

locals {
  automated_sync = {
    automated = { prune = true, selfHeal = true } # git is the truth: drift is reverted
    retry = {
      limit   = 10 # first sync can race CRDs (ServiceMonitor, ExternalSecret) being installed
      backoff = { duration = "15s", factor = 2, maxDuration = "3m" }
    }
  }

  applications = {
    # The app itself: everything under k8s/gke (= k8s/base + GKE-only settings).
    s1 = {
      namespace = "argocd"
      project   = "default"
      source = {
        repoURL        = var.repo_url
        targetRevision = var.repo_revision
        path           = "k8s/gke"
      }
      destination = { server = "https://kubernetes.default.svc", namespace = "s1" }
      syncPolicy = merge(local.automated_sync, {
        syncOptions = ["CreateNamespace=true", "RespectIgnoreDifferences=true"]
      })
      # The HPAs own the replica count. Without this, selfHeal would reset every scale-out
      # back to the number in Git and fight the autoscaler.
      ignoreDifferences = [{ group = "apps", kind = "Deployment", jsonPointers = ["/spec/replicas"] }]
    }

    # Copies Secret Manager secrets (Kafka credentials, runtime config) into Kubernetes Secrets.
    external-secrets = {
      namespace = "argocd"
      project   = "default"
      source = {
        repoURL        = "https://charts.external-secrets.io"
        chart          = "external-secrets"
        targetRevision = "2.14.0"
        helm = {
          releaseName = "external-secrets" # => service account external-secrets/external-secrets
          valuesObject = {
            installCRDs = true
            serviceAccount = {
              annotations = { "iam.gke.io/gcp-service-account" = local.sa_email["external-secrets"] }
            }
          }
        }
      }
      destination = { server = "https://kubernetes.default.svc", namespace = "external-secrets" }
      syncPolicy = merge(local.automated_sync, {
        syncOptions = ["CreateNamespace=true", "ServerSideApply=true"] # CRDs exceed the client-side apply size limit
      })
    }

    # Prometheus + Grafana (task h, Person 3's values file) with GKE-only overrides on top.
    monitoring = {
      namespace = "argocd"
      project   = "default"
      sources = [
        {
          repoURL        = "https://prometheus-community.github.io/helm-charts"
          chart          = "kube-prometheus-stack"
          targetRevision = "92.14.1"
          helm = {
            releaseName = "monitoring" # => Grafana service account monitoring/monitoring-grafana
            valueFiles  = ["$values/observability/kube-prometheus-stack-values.yaml"]
            # valuesObject wins over the values file: no public LoadBalancers on GKE, and Grafana
            # reads Cloud Logging as its own Google service account (Workload Identity).
            valuesObject = {
              prometheus = { service = { type = "ClusterIP" } }
              grafana = {
                service        = { type = "ClusterIP" }
                serviceAccount = { annotations = { "iam.gke.io/gcp-service-account" = local.sa_email["grafana"] } }
              }
            }
          }
        },
        { repoURL = var.repo_url, targetRevision = var.repo_revision, ref = "values" },
      ]
      destination = { server = "https://kubernetes.default.svc", namespace = "monitoring" }
      syncPolicy = merge(local.automated_sync, {
        syncOptions = ["CreateNamespace=true", "ServerSideApply=true"]
      })
    }

    # ServiceMonitors + the Grafana dashboard ConfigMap (Person 3's files).
    observability = {
      namespace = "argocd"
      project   = "default"
      source = {
        repoURL        = var.repo_url
        targetRevision = var.repo_revision
        path           = "observability"
        directory = {
          recurse = true
          include = "{servicemonitors.yaml,dashboards/*.yaml}" # skip the Helm values file and scripts
        }
      }
      destination = { server = "https://kubernetes.default.svc", namespace = "monitoring" }
      syncPolicy = merge(local.automated_sync, {
        syncOptions = ["SkipDryRunOnMissingResource=true"] # ServiceMonitor CRD arrives with "monitoring"
      })
    }
  }
}

# The Application objects, through the argocd-apps chart: a plain kubernetes_manifest would fail
# at plan time because the Application CRD does not exist until ArgoCD is installed.
resource "helm_release" "applications" {
  name       = "argocd-apps"
  namespace  = "argocd"
  repository = "oci://ghcr.io/argoproj/argo-helm"
  chart      = "argocd-apps"
  version    = "2.0.7"

  values = [yamlencode({ applications = local.applications })]

  depends_on = [helm_release.argocd]
}
