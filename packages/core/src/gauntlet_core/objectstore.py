"""Object storage for exported cassettes (P3-3): S3 compatible (SeaweedFS in compose) and a plain
directory for the CLI and tests. Keys look like `cassettes/<workspace_id>/<episode_id>.jsonl`."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Protocol

__all__ = ["LocalFsObjectStore", "ObjectStore", "S3ObjectStore"]


class ObjectStore(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def url(self, key: str, expires_s: int) -> str: ...


class LocalFsObjectStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError(f"object key escapes the store: {key!r}")
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def url(self, key: str, expires_s: int) -> str:
        return self._path(key).as_uri()


class S3ObjectStore:
    """aiobotocore client per call (cheap, and avoids sharing a session across event loops)."""

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str = "us-east-1",
        public_endpoint_url: str | None = None,
    ) -> None:
        self.bucket, self.region = bucket, region
        self._conn: dict[str, Any] = {
            "endpoint_url": endpoint_url,
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "region_name": region,
        }
        self._public = public_endpoint_url

    def _client(self, **override: Any) -> Any:
        from aiobotocore.config import AioConfig
        from aiobotocore.session import get_session

        config = AioConfig(signature_version="s3v4", s3={"addressing_style": "path"})
        return get_session().create_client("s3", config=config, **{**self._conn, **override})

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        async with self._client() as c:
            await c.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    async def get(self, key: str) -> bytes:
        async with self._client() as c:
            resp = await c.get_object(Bucket=self.bucket, Key=key)
            async with resp["Body"] as body:
                return bytes(await body.read())

    async def url(self, key: str, expires_s: int) -> str:
        """Presigned GET url; signed for `public_endpoint_url` when the browser reaches the
        store under another name than the services do."""
        override = {"endpoint_url": self._public} if self._public else {}
        async with self._client(**override) as c:
            return str(
                await c.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": key},
                    ExpiresIn=expires_s,
                )
            )
