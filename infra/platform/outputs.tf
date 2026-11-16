output "argocd_ui" {
  value = "kubectl -n argocd port-forward svc/argocd-server 8080:80   # then http://localhost:8080 (user admin)"
}

output "argocd_password" {
  value = "kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d"
}

output "applications" {
  value = keys(local.applications)
}
