# Deploying to Minikube

```bash
minikube start --memory=2200 --cpus=2          # small enough for an 8 GB laptop
minikube addons enable metrics-server          # pod CPU/memory on the Containers page

# Build the images INSIDE minikube so no registry is needed
minikube image build -t devops-ai-backend:latest ../backend
minikube image build -t devops-ai-frontend:latest ../frontend

kubectl apply -f 00-namespace.yaml -f 01-rbac.yaml -f 02-configmap.yaml
kubectl -n devops-ai create secret generic devops-ai-secrets --from-literal=GEMINI_API_KEY=your-key
kubectl apply -f 10-backend.yaml -f 20-frontend.yaml

kubectl -n devops-ai rollout status deployment/devops-backend
minikube service devops-frontend -n devops-ai  # opens the dashboard
```

Inside the cluster the backend detects the ServiceAccount token and calls the
Kubernetes API directly (mode "in-cluster"); on your laptop it uses `kubectl`.

Clean up: `kubectl delete namespace devops-ai` and `kubectl delete clusterrole,clusterrolebinding devops-ai-reader`.
