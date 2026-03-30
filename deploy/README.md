# Deployment Configuration
# Docker, Kubernetes, and CI/CD configurations

This directory will contain:
- `Dockerfile` — Multi-stage build for production
- `docker-compose.yml` — Local development stack (PostgreSQL, Redis, Ollama)
- `k8s/` — Kubernetes manifests (when ready for cloud deployment)
- `.github/workflows/` — CI/CD pipeline (lint → test → build → deploy)
