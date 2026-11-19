#!/bin/sh
# One-shot: create the bucket. Runs in the minio image, which ships `mc`.
set -e
mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
mc mb --ignore-existing "local/$S3_BUCKET"
