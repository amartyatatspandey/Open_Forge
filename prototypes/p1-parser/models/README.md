# Offline Model Weights

Model weights are **not stored in git**. Transfer them separately for air-gapped deployment.

## Required Models

| Phase | Model | Path |
|-------|-------|------|
| Phase 1 DLA | YOLOv8n fine-tuned on DocLayNet | `models/yolov8_doclaynets.pt` |
| Phase 2 Path B | Qwen2-VL-7B-Instruct | `models/Qwen2-VL-7B-Instruct/` |
| Phase 3 Extraction | Qwen2.5-7B-Instruct | `models/Qwen2.5-7B-Instruct/` |

## Air-Gapped Transfer Procedure

### On internet-connected build machine

1. Download weights into this `models/` directory:

```bash
# YOLO only (~7 MB)
python scripts/download_models.py --yolo-only

# All models (~30+ GB)
python scripts/download_models.py --all

# Qwen models only
python scripts/download_models.py --qwen-only
```

Logs are written to `logs/download.log`.
2. Build the Docker image: `bash docker/build_airgapped_image.sh`
3. Export: `docker save p1-parser:v1.0 | gzip > p1-parser-v1.0.tar.gz`
4. Transfer the archive via approved media.

### On air-gapped machine

```bash
docker load < p1-parser-v1.0.tar.gz
docker run --gpus all -v /data/datasheets:/input -v /data/output:/output \
    p1-parser:v1.0 python -m src.pipeline --input /input --output /output
```

## Hardware Requirements

- **Minimum (CPU-only):** 8-core, 32 GB RAM — VLM inference ~60–120 s/page
- **Recommended:** NVIDIA RTX 3090/A5000 (24 GB VRAM), 64 GB RAM

## Poppler Dependency

`pdf2image` requires Poppler (`poppler-utils` on Ubuntu). Include `.deb` packages in Docker build context for offline install.
