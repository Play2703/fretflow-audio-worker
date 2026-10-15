---
title: Fretflow Audio Extractor
emoji: 🎸
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# FretFlow Audio Extractor Service (Free Hugging Face Space)

Microserviço em FastAPI + yt-dlp de alta performance para extrair áudio de vídeos do YouTube diretamente para o FretFlow sem limitações de IP de datacenters serverless.

## Endpoints:
- `GET /health` - Verificação de status
- `GET /metadata?url=...` - Retorna título, artista, duração e thumbnail
- `GET /extract?url=...` - Faz stream do áudio puro (m4a/aac) com CORS habilitado (`Access-Control-Allow-Origin: *`)
