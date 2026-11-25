import os

import pytest
from gauntlet_core.objectstore import LocalFsObjectStore, S3ObjectStore


async def test_local_fs_put_get_url_and_key_escape(tmp_path):
    store = LocalFsObjectStore(tmp_path)
    await store.put("cassettes/ws/ep.jsonl", b"hello\n", "application/x-ndjson")
    assert await store.get("cassettes/ws/ep.jsonl") == b"hello\n"
    assert (tmp_path / "cassettes" / "ws" / "ep.jsonl").read_bytes() == b"hello\n"
    assert (await store.url("cassettes/ws/ep.jsonl", 3600)).startswith("file://")
    with pytest.raises(ValueError, match="escapes"):
        await store.put("a/../../outside", b"x", "text/plain")
    with pytest.raises(FileNotFoundError):
        await store.get("cassettes/ws/missing.jsonl")


@pytest.mark.integration
async def test_s3_round_trip_against_compose_s3():
    store = S3ObjectStore(
        os.environ.get("TEST_S3_BUCKET", "gauntlet"),
        endpoint_url=os.environ.get("TEST_S3_ENDPOINT", "http://localhost:9000"),
        access_key=os.environ.get("S3_ACCESS_KEY", "minio-dev"),
        secret_key=os.environ.get("S3_SECRET_KEY", "minio-dev-secret"),
    )
    key = "cassettes/test_ws/objectstore-test.jsonl"
    await store.put(key, b'{"t":"header"}\n', "application/x-ndjson")
    assert await store.get(key) == b'{"t":"header"}\n'
    url = await store.url(key, 60)
    assert url.startswith("http") and "X-Amz-Signature" in url
