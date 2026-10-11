"""API Gateway Client Wrapper.

Single Gatekeeper for all external HTTP communication.
Features:
- Registry loading from endpoints.yaml
- Timeout controls
- Retry with exponential backoff
- Per-provider rate limiting
- Disk caching
- Raw responses saved to data/raw/
- Mock mode loading from data/fixtures/

Nothing outside backend/apigateway/ may import httpx or requests.
"""

from collections import deque
import hashlib
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, Optional, Tuple

import httpx
import yaml
from dotenv import load_dotenv

# Load local environment configuration
load_dotenv()

logger = logging.getLogger("apigateway")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENDPOINTS_PATH = Path(__file__).resolve().parent / "endpoints.yaml"
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
FIXTURES_DIR = PROJECT_ROOT / "data" / "fixtures"
CACHE_DIR = PROJECT_ROOT / "data" / "cache"


class GatewayError(Exception):
    """Base exception for gateway failures."""
    pass


class RateLimiter:
    """Per-provider sliding window rate limiter."""

    def __init__(self, max_calls: int, period_seconds: float):
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self.timestamps: deque = deque()

    def acquire(self):
        now = time.time()
        # Remove timestamps older than window
        while self.timestamps and (now - self.timestamps[0]) > self.period_seconds:
            self.timestamps.popleft()

        if len(self.timestamps) >= self.max_calls:
            sleep_duration = self.period_seconds - (now - self.timestamps[0]) + 0.05
            if sleep_duration > 0:
                logger.warning("Rate limit hit, pausing for %.2f seconds", sleep_duration)
                time.sleep(sleep_duration)
                now = time.time()
                while self.timestamps and (now - self.timestamps[0]) > self.period_seconds:
                    self.timestamps.popleft()

        self.timestamps.append(time.time())


class ApiGatewayClient:
    """Gateway client enforcing all endpoint rules and caching."""

    def __init__(
        self,
        endpoints_config_path: Path = ENDPOINTS_PATH,
        mock_mode: Optional[bool] = None,
        default_timeout: float = 45.0,
    ):
        self.endpoints_config_path = endpoints_config_path
        self.mock_mode = (
            mock_mode
            if mock_mode is not None
            else os.getenv("MOCK_MODE", "0").lower() in ("1", "true", "yes")
        )
        self.default_timeout = default_timeout
        self.endpoints = self._load_registry()
        self.rate_limiters: Dict[str, RateLimiter] = {}
        self._init_rate_limiters()

        RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _load_registry(self) -> Dict[str, Any]:
        if not self.endpoints_config_path.exists():
            raise GatewayError(f"Registry not found: {self.endpoints_config_path}")
        with open(self.endpoints_config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("endpoints", {})

    def _init_rate_limiters(self):
        for name, conf in self.endpoints.items():
            rl = conf.get("rate_limit", {})
            calls = rl.get("calls", 30)
            period = rl.get("period_seconds", 60)
            self.rate_limiters[name] = RateLimiter(calls, period)

    def _get_cache_key(
        self, endpoint_name: str, url: str, params: Optional[Dict], json_body: Optional[Any]
    ) -> str:
        payload = {
            "endpoint": endpoint_name,
            "url": url,
            "params": params or {},
            "body": json_body or {},
        }
        raw_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw_bytes).hexdigest()

    def _save_raw_response(
        self, endpoint_name: str, status_code: int, data: Any, cache_key: str
    ):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{endpoint_name}_{cache_key[:8]}.json"
        raw_path = RAW_DATA_DIR / filename
        try:
            with open(raw_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "endpoint": endpoint_name,
                        "timestamp": timestamp,
                        "status_code": status_code,
                        "cache_key": cache_key,
                        "data": data,
                    },
                    f,
                    indent=2,
                    default=str,
                )
        except Exception as e:
            logger.warning("Failed saving raw response to %s: %s", raw_path, e)

    def load_fixture(self, endpoint_name: str) -> Any:
        endpoint_conf = self.endpoints.get(endpoint_name)
        if not endpoint_conf:
            raise GatewayError(f"Unknown endpoint '{endpoint_name}'")
        rel_path = endpoint_conf.get("fixture_path")
        if not rel_path:
            raise GatewayError(f"No fixture path registered for '{endpoint_name}'")
        fixture_file = PROJECT_ROOT / rel_path
        if not fixture_file.exists():
            raise GatewayError(f"Fixture file does not exist: {fixture_file}")
        with open(fixture_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def request(
        self,
        endpoint_name: str,
        path_params: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        force_refresh: bool = False,
        cache_ttl_seconds: int = 3600,
    ) -> Any:
        """Execute request according to registry contract."""
        if endpoint_name not in self.endpoints:
            raise GatewayError(
                f"Endpoint '{endpoint_name}' is not registered in endpoints.yaml. "
                "Anti-hallucination violation: only registered endpoints may be queried."
            )

        endpoint_conf = self.endpoints[endpoint_name]

        # In mock mode, immediately load saved fixture
        if self.mock_mode:
            return self.load_fixture(endpoint_name)

        # URL construction with path params
        url_template = endpoint_conf["url"]
        url = url_template.format(**(path_params or {}))
        method = endpoint_conf["method"].upper()

        cache_key = self._get_cache_key(endpoint_name, url, params, json_body)
        cache_file = CACHE_DIR / f"{cache_key}.json"

        # Check disk cache
        if not force_refresh and cache_file.exists():
            try:
                mtime = cache_file.stat().st_mtime
                if (time.time() - mtime) < cache_ttl_seconds:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        return json.load(f)
            except Exception as e:
                logger.debug("Cache read failed, proceeding with live call: %s", e)

        # Rate limiter
        limiter = self.rate_limiters.get(endpoint_name)
        if limiter:
            limiter.acquire()

        # Build headers & auth
        req_headers = dict(headers or {})
        auth_conf = endpoint_conf.get("auth", {})
        auth_type = auth_conf.get("type", "none")

        if auth_type == "header":
            key_name = auth_conf.get("key")
            env_var = auth_conf.get("env_var")
            token = os.getenv(env_var, "")
            if token and key_name:
                req_headers[key_name] = token
        elif auth_type == "bearer":
            env_var = auth_conf.get("env_var")
            token = os.getenv(env_var, "")
            if token:
                req_headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "custom_header":
            key_name = auth_conf.get("key")
            env_var = auth_conf.get("env_var")
            val = os.getenv(env_var, "RiskRadarBot/0.1 (compliance-test@example.com)")
            if key_name:
                req_headers[key_name] = val

        # Retry with exponential backoff
        max_retries = 3
        backoff = 1.0
        response_data = None
        last_exception = None

        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=self.default_timeout) as client:
                    resp = client.request(
                        method=method,
                        url=url,
                        params=params,
                        json=json_body,
                        headers=req_headers,
                    )

                    if resp.status_code in (429, 500, 502, 503, 504):
                        logger.warning(
                            "Transient HTTP status %d on %s (attempt %d/%d)",
                            resp.status_code,
                            url,
                            attempt + 1,
                            max_retries,
                        )
                        time.sleep(backoff)
                        backoff *= 2
                        continue

                    resp.raise_for_status()
                    response_data = resp.json()

                    # Save raw response for audit
                    self._save_raw_response(endpoint_name, resp.status_code, response_data, cache_key)

                    # Save to cache
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(response_data, f)

                    return response_data

            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last_exception = exc
                logger.warning(
                    "Network error querying %s: %s (attempt %d/%d)",
                    url,
                    exc,
                    attempt + 1,
                    max_retries,
                )
                time.sleep(backoff)
                backoff *= 2

        raise GatewayError(
            f"Failed calling endpoint '{endpoint_name}' after {max_retries} attempts: {last_exception}"
        )


# Global gateway client instance
gateway_client = ApiGatewayClient()
