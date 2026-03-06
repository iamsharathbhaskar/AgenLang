# AgenLang Deployment Guide

This directory contains production-ready Docker and Kubernetes deployment configurations for AgenLang.

## Quick Start

### Local Development with Docker Compose

```bash
# Build and start services
docker-compose up --build

# With Redis and PostgreSQL
docker-compose --profile full up --build

# With monitoring (Prometheus + Grafana)
docker-compose --profile monitoring up --build
```

### Kubernetes Deployment

```bash
# Using kubectl directly
kubectl apply -k k8s/

# Using kustomize
kustomize build k8s/ | kubectl apply -f -

# Verify deployment
kubectl get pods -n agenlang
kubectl logs -n agenlang -l app.kubernetes.io/component=server
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENLANG_HOST` | Server bind address | 0.0.0.0 |
| `AGENLANG_PORT` | Server port | 8000 |
| `AGENLANG_DATA_DIR` | Data persistence directory | /data/agenlang |
| `AGENLANG_KEY_PATH` | Path to ECDSA keys | /data/agenlang/keys.pem |
| `AGENLANG_LOG_LEVEL` | Logging level | INFO |
| `AGENLANG_REDIS_ENABLED` | Enable Redis backend | true |
| `REDIS_URL` | Redis connection URL | redis://redis:6379/0 |
| `DATABASE_URL` | PostgreSQL URL (optional) | - |
| `RATE_LIMIT_ENABLED` | Enable rate limiting | true |

### API Keys (Secrets)

Set these in environment or Kubernetes secrets:
- `TAVILY_API_KEY` - Tavily search API
- `OPENAI_API_KEY` - OpenAI API
- `ANTHROPIC_API_KEY` - Anthropic API
- `XAI_API_KEY` - XAI API
- `LLM_API_KEY` - Generic LLM provider API

## Security Features

- **Non-root container** (UID 1000)
- **Read-only root filesystem** (with data volumes for writes)
- **Network policies** restricting pod-to-pod communication
- **Security headers** via ingress annotations
- **TLS via cert-manager** or cloud provider
- **Secrets mounted** as environment variables, not in image

## Scaling

### Horizontal Pod Autoscaler

Configured for:
- CPU target: 70%
- Memory target: 80%
- Custom metric: executions per second
- Min replicas: 3
- Max replicas: 20

### Vertical Pod Autoscaler (optional)

Adjusts CPU/memory requests based on actual usage.

## Monitoring

### Prometheus Metrics

- `/metrics/prometheus` - Standard Prometheus metrics
- Execution count, duration, errors
- Joule consumption tracking

### Grafana Dashboards

Import the dashboard from `k8s/monitoring.yaml` ConfigMap.

## Troubleshooting

### Check server health
```bash
curl http://localhost:8000/health
```

### View logs
```bash
# Docker
docker-compose logs -f agenlang-server

# Kubernetes
kubectl logs -n agenlang -f deployment/agenlang-server
```

### Check A2A endpoints
```bash
# Health check
curl http://localhost:8000/health

# Agent discovery
curl http://localhost:8000/.well-known/agent.json

# Execute contract
curl -X POST http://localhost:8000/a2a \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"agenlang/execute","params":{}}'
```

## Production Checklist

- [ ] Set real TLS certificates
- [ ] Configure external PostgreSQL/Redis
- [ ] Set all API keys in secrets
- [ ] Configure log aggregation (e.g., Fluentd)
- [ ] Set up external DNS
- [ ] Configure backup for data volumes
- [ ] Review resource limits
- [ ] Enable pod disruption budgets
