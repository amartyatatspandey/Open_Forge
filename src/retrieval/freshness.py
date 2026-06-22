from __future__ import annotations

import hashlib
import logging
from typing import Literal, Optional

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class FreshnessResult(BaseModel):
    component_id: str
    is_stale: bool
    signal_used: Literal["etag", "content_length", "cover_sha256", "unknown"]
    new_etag: Optional[str] = None
    new_content_length: Optional[int] = None
    new_cover_sha256: Optional[str] = None
    error: Optional[str] = None


class DatasheetFreshnessChecker:
    """
    Multi-signal freshness check (GLM 5.1).
    Signal priority: ETag → Content-Length → SHA-256 of first 4KB.
    """

    def check_for_updates(
        self,
        component_id: str,
        url: str,
        stored_etag: Optional[str],
        stored_content_length: Optional[int],
        stored_cover_sha256: Optional[str],
    ) -> FreshnessResult:
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.head(url, follow_redirects=True)

                etag = response.headers.get("ETag")
                if etag is not None and stored_etag is not None:
                    is_stale = etag != stored_etag
                    return FreshnessResult(
                        component_id=component_id,
                        is_stale=is_stale,
                        signal_used="etag",
                        new_etag=etag,
                    )

                content_length_header = response.headers.get("Content-Length")
                if content_length_header is not None and stored_content_length is not None:
                    new_len = int(content_length_header)
                    is_stale = new_len != stored_content_length
                    return FreshnessResult(
                        component_id=component_id,
                        is_stale=is_stale,
                        signal_used="content_length",
                        new_content_length=new_len,
                    )

                if stored_cover_sha256 is not None:
                    get_response = client.get(
                        url,
                        headers={"Range": "bytes=0-4095"},
                        follow_redirects=True,
                    )
                    body = get_response.content
                    new_hash = hashlib.sha256(body).hexdigest()
                    is_stale = new_hash != stored_cover_sha256
                    return FreshnessResult(
                        component_id=component_id,
                        is_stale=is_stale,
                        signal_used="cover_sha256",
                        new_cover_sha256=new_hash,
                    )

                logger.warning(
                    "No freshness signal available for component_id=%s url=%s",
                    component_id,
                    url,
                )
                return FreshnessResult(
                    component_id=component_id,
                    is_stale=False,
                    signal_used="unknown",
                )
        except Exception as exc:
            return FreshnessResult(
                component_id=component_id,
                is_stale=False,
                signal_used="unknown",
                error=str(exc),
            )
