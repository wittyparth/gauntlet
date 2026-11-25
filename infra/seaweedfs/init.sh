#!/bin/sh
# One-shot: create the bucket via `weed shell`. Idempotent: "already exists" counts as success.
out="$(echo "s3.bucket.create -name $S3_BUCKET" | weed shell -master=seaweedfs:9333 2>&1)" || true
echo "$out"
echo "$out" | grep -qE "created bucket|already exists"
