"""
IP Management Tasks

Background tasks for processing user IP/location change requests.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, cast

from celery import shared_task
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import Credential, IPChangeRequest, ProtocolInstance

logger = logging.getLogger(__name__)


def _is_credential_active(credential: Credential) -> bool:
    data: Dict[str, Any] = cast(Dict[str, Any], credential.credential_data or {})
    if not isinstance(data, dict):
        return True
    return bool(data.get("is_active", True))


def _credential_instance_id(credential: Credential) -> Optional[int]:
    data: Dict[str, Any] = cast(Dict[str, Any], credential.credential_data or {})
    if not isinstance(data, dict):
        return None
    value = data.get("instance_id")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _calculate_instance_load(
    credentials: List[Credential], instance_id: int, protocol_id: int
) -> int:
    load = 0
    for credential in credentials:
        if credential.protocol_id != protocol_id:
            continue
        if not _is_credential_active(credential):
            continue
        if _credential_instance_id(credential) == instance_id:
            load += 1
    return load


def _find_available_instance(
    db: Session,
    protocol_id: int,
    preferred_country: Optional[str] = None,
    exclude_instance_id: Optional[int] = None,
) -> Optional[ProtocolInstance]:
    """
    Find a healthy instance for the target protocol, preferring:
    1. requested country
    2. least active credential load
    """
    base_query = db.query(ProtocolInstance).filter(
        ProtocolInstance.protocol_id == protocol_id,
        ProtocolInstance.is_active == True,
        ProtocolInstance.health_status.in_(["healthy", "degraded"]),
    )

    if exclude_instance_id is not None:
        base_query = base_query.filter(ProtocolInstance.id != exclude_instance_id)

    all_credentials = (
        db.query(Credential).filter(Credential.protocol_id == protocol_id).all()
    )

    def pick_least_loaded(
        candidates: List[ProtocolInstance],
    ) -> Optional[ProtocolInstance]:
        if not candidates:
            return None
        ranked = sorted(
            candidates,
            key=lambda instance: (
                _calculate_instance_load(
                    all_credentials, cast(int, instance.id), protocol_id
                ),
                instance.id,
            ),
        )
        return ranked[0]

    if preferred_country:
        country_code = preferred_country.upper()
        preferred_instances = (
            base_query.filter(ProtocolInstance.country_code == country_code)
            .order_by(ProtocolInstance.id.asc())
            .all()
        )
        selected = pick_least_loaded(preferred_instances)
        if selected is not None:
            return selected

    fallback_instances = base_query.order_by(ProtocolInstance.id.asc()).all()
    return pick_least_loaded(fallback_instances)


def _mark_request_failed(
    ip_request: IPChangeRequest,
    reason: str,
    status: str = "failed",
) -> None:
    ip_request_obj = cast(Any, ip_request)
    ip_request_obj.status = status
    ip_request_obj.denial_reason = reason
    ip_request_obj.processed_at = datetime.now(timezone.utc).replace(tzinfo=None)


@shared_task(name="ip.process_ip_change")
def process_ip_change(ip_request_id: int) -> Dict[str, Any]:
    """
    Process a pending IP change request and migrate the user's credential
    to a new protocol instance.
    """
    db = SessionLocal()
    try:
        ip_request = db.query(IPChangeRequest).filter_by(id=ip_request_id).first()
        if not ip_request or ip_request.status != "pending":
            return {
                "success": False,
                "status": "error",
                "error": "IP request not found or not pending",
            }

        credential = (
            db.query(Credential)
            .filter(
                Credential.user_id == ip_request.user_id,
                Credential.subscription_id == ip_request.subscription_id,
                Credential.protocol_id == ip_request.protocol_id,
            )
            .order_by(Credential.id.asc())
            .first()
        )

        if not credential:
            _mark_request_failed(
                ip_request,
                "No credential found for this subscription/protocol",
            )
            db.commit()
            return {
                "success": False,
                "status": "error",
                "error": "No credential found for request",
            }

        previous_instance_id = _credential_instance_id(credential)
        selected_instance = _find_available_instance(
            db=db,
            protocol_id=cast(int, ip_request.protocol_id),
            preferred_country=cast(Optional[str], ip_request.requested_country_code),
            exclude_instance_id=previous_instance_id,
        )

        if selected_instance is None:
            _mark_request_failed(ip_request, "No available instances found")
            db.commit()
            return {
                "success": False,
                "status": "no_instances_available",
                "error": "No available instances found",
            }

        new_ip = str(selected_instance.ip_address)
        credential_data = dict(credential.credential_data or {})
        credential_data["instance_id"] = selected_instance.id
        credential_data["server"] = new_ip
        credential_data["server_ip"] = new_ip
        credential_data["country_code"] = selected_instance.country_code
        credential_data["is_active"] = bool(credential_data.get("is_active", True))
        credential_obj = cast(Any, credential)
        credential_obj.credential_data = credential_data
        credential_obj.server_location = (
            f"{selected_instance.country_name} ({selected_instance.country_code})"
        )

        ip_request_obj = cast(Any, ip_request)
        ip_request_obj.old_instance_id = previous_instance_id
        ip_request_obj.new_instance_id = selected_instance.id
        ip_request_obj.status = "completed"
        ip_request_obj.denial_reason = None
        ip_request_obj.processed_at = datetime.now(timezone.utc).replace(tzinfo=None)

        db.commit()

        return {
            "success": True,
            "status": "success",
            "request_id": ip_request.id,
            "new_instance_id": selected_instance.id,
            "new_ip": new_ip,
        }
    except Exception as exc:
        logger.exception("Error processing IP change request %s", ip_request_id)
        db.rollback()
        return {"success": False, "status": "error", "error": str(exc)}
    finally:
        db.close()


@shared_task(name="ip.cleanup_old_ip_requests")
def cleanup_old_ip_requests() -> Dict[str, Any]:
    """
    Mark stale pending requests as denied after 30 days.
    """
    db = SessionLocal()
    try:
        expiration_threshold = datetime.now(timezone.utc).replace(
            tzinfo=None
        ) - timedelta(days=30)
        stale_requests = (
            db.query(IPChangeRequest)
            .filter(
                and_(
                    IPChangeRequest.status == "pending",
                    IPChangeRequest.created_at < expiration_threshold,
                )
            )
            .all()
        )

        processed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        for request in stale_requests:
            request_obj = cast(Any, request)
            request_obj.status = "denied"
            request_obj.denial_reason = (
                "Request expired after 30 days in pending status"
            )
            request_obj.processed_at = processed_at

        db.commit()
        return {
            "success": True,
            "status": "success",
            "cleaned_count": len(stale_requests),
        }
    except Exception as exc:
        logger.exception("Error cleaning old IP change requests")
        db.rollback()
        return {"success": False, "status": "error", "error": str(exc)}
    finally:
        db.close()
