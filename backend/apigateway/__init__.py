"""API Gateway Package.

The single gatekeeper through which all external network calls must flow.
No external network libraries (requests, httpx) may be imported outside this package.
"""
from backend.apigateway.client import ApiGatewayClient, GatewayError, gateway_client
from backend.apigateway.adapters import FinnhubAdapter, CFPBAdapter, EdgarAdapter, LLMAdapter

__all__ = [
    "ApiGatewayClient",
    "GatewayError",
    "gateway_client",
    "FinnhubAdapter",
    "CFPBAdapter",
    "EdgarAdapter",
    "LLMAdapter",
]
