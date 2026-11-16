"""
MVP Endpoints - Simplified API for quick deployments

Public endpoints for the MVP landing page that don't require admin authentication.
These are designed for initial testing and demonstration.
"""

import logging
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth.jwt import verify_token
from app.core.config import settings
from app.core.database import get_db
from app.models import Protocol, ProtocolInstance, User, UserCredential
from app.services.auth.deployment_tokens import DeploymentTokenService
from app.services.flux.node_manager import FluxNodeManager, NodeDeploymentError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mvp", tags=["MVP"])
security = HTTPBearer(auto_error=False)


async def verify_mvp_access(
    x_internal_api_key: Optional[str] = Header(None, alias="X-Internal-API-Key"),
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
):
    """
    Verify access to MVP endpoints.
    Allows access if:
    1. ENABLE_MVP_PUBLIC_DEPLOY is True
    2. Valid X-Internal-API-Key is provided
    3. Valid Admin JWT is provided
    """
    # 1. Public access enabled
    if settings.ENABLE_MVP_PUBLIC_DEPLOY:
        return

    # 2. Internal API Key
    if (
        x_internal_api_key
        and settings.INTERNAL_API_KEY
        and x_internal_api_key == settings.INTERNAL_API_KEY
    ):
        return

    # 3. Admin JWT
    if auth:
        try:
            payload = verify_token(auth.credentials)
            user_id = payload.get("sub")
            if user_id:
                user = db.query(User).filter(User.id == int(user_id)).first()
                if user and user.is_admin:
                    return
        except Exception as e:
            logger.warning(f"MVP Auth failed: {e}")
            pass

    # 4. Fail
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Public MVP deployment is disabled. Authentication required.",
    )


# =============================================================================
# SCHEMAS
# =============================================================================


class MVPDeployRequest(BaseModel):
    """MVP deployment request - simplified for landing page"""

    protocol: str = Field(
        ...,
        description="Protocol name: shadowsocks, ssh, http-proxy, vless, trojan, outline",
    )
    instance_count: int = Field(
        default=3, ge=3, le=10, description="Number of instances (3-10)"
    )


class MVPDeployResponse(BaseModel):
    """MVP deployment response"""

    success: bool
    message: str
    protocol: str
    instance_count: int
    credentials: Optional[str] = None
    instances: list = []


class ProtocolInfo(BaseModel):
    """Protocol information for display"""

    name: str
    display_name: str
    price_monthly: float
    description: str
    best_for: str


# =============================================================================
# PROTOCOL INFO
# =============================================================================

PROTOCOL_INFO = {
    "http-proxy": {
        "display_name": "HTTP Proxy",
        "price_monthly": 3.0,
        "description": "Simple HTTP/HTTPS proxy for web browsing",
        "best_for": "Entry-level users, basic web browsing",
        "ports": [3128],
        "docker_image": "fluxvpn/http-proxy:latest",
    },
    "ssh": {
        "display_name": "SSH Tunnel",
        "price_monthly": 5.0,
        "description": "Secure SSH tunnel with SOCKS5 proxy",
        "best_for": "Technical users, Linux/macOS",
        "ports": [22, 2222],
        "docker_image": "fluxvpn/ssh:latest",
    },
    "shadowsocks": {
        "display_name": "Shadowsocks",
        "price_monthly": 8.0,
        "description": "Fast encrypted proxy with mobile apps",
        "best_for": "Mobile users, good stealth",
        "ports": [8388],
        "docker_image": "fluxvpn/shadowsocks:latest",
    },
    "outline": {
        "display_name": "Outline VPN",
        "price_monthly": 9.0,
        "description": "Easy-to-use VPN with Outline app",
        "best_for": "Non-technical users, organizations",
        "ports": [443, 8081],
        "docker_image": "fluxvpn/outline:latest",
    },
    "vless": {
        "display_name": "VLESS/V2Ray",
        "price_monthly": 12.0,
        "description": "Advanced protocol with WebSocket+TLS",
        "best_for": "Advanced users, high performance",
        "ports": [443, 80],
        "docker_image": "fluxvpn/vless:latest",
    },
    "trojan": {
        "display_name": "Trojan",
        "price_monthly": 15.0,
        "description": "Maximum stealth, looks like HTTPS",
        "best_for": "Restrictive networks, premium users",
        "ports": [443],
        "docker_image": "fluxvpn/trojan:latest",
    },
}


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get("/protocols")
async def list_protocols():
    """
    List all available protocols with pricing and info

    Public endpoint - no authentication required.
    """
    return [
        ProtocolInfo(
            name=name,
            display_name=info["display_name"],
            price_monthly=info["price_monthly"],
            description=info["description"],
            best_for=info["best_for"],
        )
        for name, info in PROTOCOL_INFO.items()
    ]


@router.post(
    "/deploy",
    response_model=MVPDeployResponse,
    dependencies=[Depends(verify_mvp_access)],
)
async def mvp_deploy(request: MVPDeployRequest, db: Session = Depends(get_db)):
    """
    MVP Deployment Endpoint

    Simplified deployment for the landing page. Deploys VPN instances
    to FluxCloud.

    Requires authentication if ENABLE_MVP_PUBLIC_DEPLOY is False.
    """
    protocol_name = request.protocol.lower().replace("_", "-")

    # Validate protocol
    if protocol_name not in PROTOCOL_INFO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid protocol: {protocol_name}. Valid options: {list(PROTOCOL_INFO.keys())}",
        )

    protocol_config = PROTOCOL_INFO[protocol_name]

    logger.info(f"MVP Deploy: {request.instance_count} instances of {protocol_name}")

    # Get or create protocol in database
    protocol = db.query(Protocol).filter(Protocol.name == protocol_name).first()

    if not protocol:
        protocol = Protocol(
            name=protocol_name,
            display_name=protocol_config["display_name"],
            description=protocol_config["description"],
            price_monthly=protocol_config["price_monthly"],
            is_active=True,
        )
        db.add(protocol)
        db.commit()
        db.refresh(protocol)

    try:
        # Initialize FluxCloud node manager
        node_manager = FluxNodeManager()

        # Deploy instances
        instances = await node_manager.deploy_protocol_instances(
            db=db, protocol=protocol, count=request.instance_count
        )

        await node_manager.close()

        # Generate credentials for the protocol
        credentials = generate_mvp_credentials(protocol_name, instances)

        return MVPDeployResponse(
            success=True,
            message=f"Successfully deployed {len(instances)} {protocol_config['display_name']} instances",
            protocol=protocol_name,
            instance_count=len(instances),
            credentials=credentials,
            instances=[
                {
                    "name": f"{protocol_name}-{i.instance_number}",
                    "ip": i.ip_address or "pending",
                    "country": i.country_code or "auto",
                    "status": "running" if i.is_active else "starting",
                }
                for i in instances
            ],
        )

    except NodeDeploymentError as e:
        logger.error(f"MVP deployment failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Deployment failed: {str(e)}",
        )
    except Exception as e:
        logger.error(f"MVP deployment unexpected error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}",
        )


@router.get("/status/{deployment_id}")
async def get_deployment_status(deployment_id: str, db: Session = Depends(get_db)):
    """
    Check deployment status

    Returns the current status of instances in a deployment.
    """
    # For MVP, we'll search by app name prefix
    instances = (
        db.query(ProtocolInstance)
        .filter(ProtocolInstance.flux_app_name.like(f"%{deployment_id}%"))
        .all()
    )

    if not instances:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found"
        )

    all_active = all(i.is_active for i in instances)

    return {
        "deployment_id": deployment_id,
        "status": "running" if all_active else "deploying",
        "instances": [
            {
                "name": i.flux_app_name,
                "ip": i.ip_address,
                "status": "running" if i.is_active else "starting",
                "country": i.country_code,
            }
            for i in instances
        ],
        "total": len(instances),
        "active": sum(1 for i in instances if i.is_active),
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def generate_mvp_credentials(protocol: str, instances: list) -> str:
    """
    Generate credentials string based on protocol type

    Returns a formatted string that users can use to connect.
    """
    if not instances:
        return "No instances available yet. Check status in a few minutes."

    # Use first active instance
    instance = next((i for i in instances if i.is_active and i.ip_address), None)

    if not instance:
        instance = instances[0]
        if not instance.ip_address:
            return "Instances are still starting. Please refresh in 1-2 minutes."

    # Generate protocol-specific credentials
    password = secrets.token_urlsafe(16)

    if protocol == "shadowsocks":
        # ss://method:password@server:port
        return f"""Shadowsocks Configuration:
Server: {instance.ip_address}
Port: 8388
Password: {password}
Method: chacha20-ietf-poly1305

SS URL: ss://Y2hhY2hhMjAtaWV0Zi1wb2x5MTMwNTp{password}@{instance.ip_address}:8388

Import this URL in your Shadowsocks app."""

    elif protocol == "ssh":
        username = f"vpn{secrets.token_hex(4)}"
        return f"""SSH Tunnel Configuration:
Host: {instance.ip_address}
Port: 22
Username: {username}
Password: {password}

Connect with:
ssh -D 1080 -N {username}@{instance.ip_address}

Then configure your browser to use SOCKS5 proxy: localhost:1080"""

    elif protocol == "http-proxy":
        username = f"user{secrets.token_hex(4)}"
        return f"""HTTP Proxy Configuration:
Host: {instance.ip_address}
Port: 3128
Username: {username}
Password: {password}

Browser Proxy Settings:
HTTP Proxy: {instance.ip_address}:3128
HTTPS Proxy: {instance.ip_address}:3128"""

    elif protocol == "vless":
        uuid = secrets.token_hex(16)
        uuid = f"{uuid[:8]}-{uuid[8:12]}-{uuid[12:16]}-{uuid[16:20]}-{uuid[20:]}"
        return f"""VLESS Configuration:
Address: {instance.ip_address}
Port: 443
UUID: {uuid}
Transport: WebSocket
Path: /vless

V2Ray URL:
vless://{uuid}@{instance.ip_address}:443?type=ws&path=%2Fvless&security=tls"""

    elif protocol == "trojan":
        return f"""Trojan Configuration:
Server: {instance.ip_address}
Port: 443
Password: {password}

Trojan URL:
trojan://{password}@{instance.ip_address}:443"""

    elif protocol == "outline":
        return f"""Outline VPN:
1. Download Outline app from https://getoutline.org/
2. Use this access key:

ss://Y2hhY2hhMjAtaWV0Zi1wb2x5MTMwNTp{password}@{instance.ip_address}:443/?outline=1

Server: {instance.ip_address}
Port: 443"""

    else:
        return f"Protocol: {protocol}\nServer: {instance.ip_address}\nCredentials will be emailed."
