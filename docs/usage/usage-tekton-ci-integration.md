# Usage - Tekton CI/CD Integration

## Prerequisites

- Tekton CLI
- Kubectl CLI
- Kubernetes Cluster
- [Tekton Pipeline installed in the Kubernetes Cluster](https://tekton.dev/docs/installation/)
- [Tekton Dashboard installed in the Kubernetes Cluster](https://tekton.dev/docs/dashboard/install/)
- Gemini API key(GEMINI_API_KEY) should be set in the environment variables.
- Prepared MCP server source code for MCP Probe. See [Preparing MCP Server Source Code](prepare-mcp-server.md) for more details.

## Setup

### 1. Create Tekton Tasks

Update the mcp-probe-pilot/ci-integration/tasks.yaml to use an image with environment image and variables required by your server.
```yaml
apiVersion: tekton.dev/v1beta1
kind: Task
metadata:
  name: run-mcp-probe-pilot
spec:
  steps:
    - name: run-mcp-probe-pilot
      image: <IMAGE_NAME>
      ...
```

Apply the tasks.yaml file to the cluster with the command:
```sh
kubectl apply --filename mcp-probe-pilot/ci-integration/tasks.yaml
```

### 2. Apply Tekton Pipeline

```sh
kubectl apply --filename mcp-probe-pilot/ci-integration/pipeline.yaml
```

### 3. Create Gemini API Key Secret

Create the mcp-probe-pilot/ci-integration/secrets.yaml file with the following content:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: gemini-api-key
stringData:
  GEMINI_API_KEY: <your-gemini-api-key>
```

Create it in the cluster with the command:

```sh
kubectl apply --filename mcp-probe-pilot/ci-integration/secrets.yaml
```

### 4. Set Up the MCP Probe Service

```sh
kubectl apply --filename mcp-probe-pilot/ci-integration/mcp-probe-service.yaml
```

## Executing the Pipeline

### 1. Add your **public** repository URL to the `repo-url` parameter in the `pipelinerun.yaml` file.

### 2. Execute the Pipeline

```sh
kubectl create --filename mcp-probe-pilot/ci-integration/pipelinerun/pipelinerun.yaml
```

### 3. Monitor the Pipeline Run with the Dashboard

```sh
kubectl port-forward svc/tekton-dashboard -n tekton-pipelines 9097:9097 > /dev/null 2>&1 &
```

Open the Dashboard in your browser on [http://localhost:9097](http://localhost:9097)

### 4. Port Forward Dashboard to Local Machine from Kubernetes Cluster

```sh
kubectl port-forward svc/mcp-probe-service 8080:8080 > /dev/null 2>&1 &
```

## Stop Services

```sh
pkill -f "port-forward svc/mcp-probe-service"
```

```sh
pkill -f "port-forward svc/tekton-dashboard"
```

