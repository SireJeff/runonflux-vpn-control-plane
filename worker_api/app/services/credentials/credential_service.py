"""
Credential Service
Main service class for credential generation and management
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, cast

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    ConnectionLog,
    FdmDomain,
    Protocol,
    ProtocolInstance,
    Subscription,
    User,
    UserCredential,
)
from app.services.fdm import FdmDomainService

from .generators import GENERATORS, get_credential_generator

logger = logging.getLogger(__name__)


class CredentialService:
    """
    Service for generating and managing VPN credentials.
    """

    def __init__(self, db: Session):
        self.db = db

    def generate_credential(
        self,
        user: User,
        subscription: Subscription,
        preferred_country: Optional[str] = None,
        **kwargs,
    ) -> UserCredential:
        """Generate a new credential for a subscription."""
        if not subscription.is_active:
            raise ValueError("Subscription is not active")

        expires_at = getattr(subscription, "expires_at", None)
        if expires_at and expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
            raise ValueError("Subscription has expired")

        # Check max_connections limit from subscription plan
        if subscription.plan and subscription.plan.max_connections:
            current_credential_count = (
                self.db.query(UserCredential)
                .filter(
                    UserCredential.user_id == user.id,
                    UserCredential.subscription_id == subscription.id,
                )
                .count()
            )
            if current_credential_count >= subscription.plan.max_connections:
                raise ValueError(
                    f"Connection limit reached ({current_credential_count}/{subscription.plan.max_connections}). "
                    "Delete an existing credential before creating a new one."
                )

        protocol = self._resolve_protocol(
            subscription=subscription,
            explicit_protocol_id=kwargs.get("protocol_id"),
        )
        if not protocol:
            raise ValueError("No active protocol available")

        existing = (
            self.db.query(UserCredential)
            .filter_by(
                user_id=user.id,
                subscription_id=subscription.id,
                protocol_id=protocol.id,
            )
            .first()
        )
        if existing:
            raise ValueError(
                "You already have a credential for this subscription and protocol. "
                "Use IP change to get a new server or delete the existing credential first."
            )

        instance = self._select_instance(cast(int, protocol.id), preferred_country)
        if not instance:
            raise ValueError(f"No available instances for protocol {protocol.name}")

        try:
            generator = get_credential_generator(cast(str, protocol.name))
        except ValueError as exc:
            logger.error("No generator for protocol %s: %s", protocol.name, exc)
            raise ValueError(f"Protocol {protocol.name} is not supported yet")

        port = int(protocol.default_port or generator.default_ports[0])
        server_ip = str(instance.ip_address)

        # Try to get FDM domain for this instance
        try:
            fdm_service = FdmDomainService(self.db)
            fdm_domain = fdm_service.select_domain_for_instance(instance)
            if fdm_domain:
                # Use FDM domain as server address
                server_address = fdm_domain.domain_name
                try:
                    fdm_service.increment_domain_load(fdm_domain)
                except Exception as exc:
                    logger.warning(
                        "Failed to increment domain load for %s (id=%s): %s",
                        fdm_domain.domain_name,
                        fdm_domain.id,
                        exc,
                    )
                logger.info(
                    "Using FDM domain %s (id=%s) for instance %s",
                    fdm_domain.domain_name,
                    fdm_domain.id,
                    instance.id,
                )
            else:
                # Fall back to IP address
                server_address = server_ip
                logger.debug(
                    "No FDM domain available for instance %s, using IP address",
                    instance.id,
                )
        except Exception as exc:
            logger.warning(
                "FDM domain selection failed for instance %s, falling back to IP: %s",
                instance.id,
                exc,
            )
            fdm_domain = None
            server_address = server_ip

        credential_data = generator.generate(
            server_ip=server_ip,
            port=port,
            user_id=cast(int, user.id),
            subscription_id=cast(int, subscription.id),
            country_code=cast(str, instance.country_code),
            **{k: v for k, v in kwargs.items() if k != "protocol_id"},
        )

        credential_data["instance_id"] = instance.id
        credential_data["flux_app_name"] = instance.flux_app_name
        credential_data["server_domain"] = (
            fdm_domain.domain_name
            if fdm_domain
            else f"{instance.flux_app_name}.runonflux.io"
        )
        credential_data.setdefault("server_ip", server_ip)
        credential_data.setdefault("server", server_address)
        credential_data.setdefault("country_code", instance.country_code)
        credential_data["is_active"] = True
        if fdm_domain:
            credential_data["fdm_domain_id"] = fdm_domain.id

        credential = UserCredential(
            user_id=user.id,
            subscription_id=subscription.id,
            protocol_id=protocol.id,
            credential_data=credential_data,
            server_location=f"{instance.country_name} ({instance.country_code})",
        )

        self.db.add(credential)
        self.db.commit()
        self.db.refresh(credential)

        logger.info(
            "Generated %s credential %s for user %s on instance %s",
            protocol.name,
            credential.id,
            user.id,
            instance.id,
        )

        return credential

    def get_credential_with_details(self, credential: UserCredential) -> Dict[str, Any]:
        """Get credential data plus connection-oriented details."""
        protocol = self.db.query(Protocol).filter_by(id=credential.protocol_id).first()
        if not protocol:
            raise ValueError("Protocol not found")

        cred_data: Dict[str, Any] = cast(
            Dict[str, Any], credential.credential_data or {}
        )
        if not isinstance(cred_data, dict):
            cred_data = {}

        protocol_name = cast(str, protocol.name)
        try:
            generator = get_credential_generator(protocol_name)
        except ValueError:
            return {
                "id": credential.id,
                "user_id": credential.user_id,
                "subscription_id": credential.subscription_id,
                "protocol_id": credential.protocol_id,
                "protocol_name": protocol_name,
                "server": cred_data.get("server") or cred_data.get("server_ip"),
                "port": cred_data.get("port") or protocol.default_port or 0,
                "server_domain": cred_data.get("server_domain"),
                "server_location": credential.server_location,
                "country_code": cred_data.get("country_code"),
                "credential_data": cred_data,
                "connection_uri": cred_data.get("connection_uri"),
                "qr_code_data": "",
                "download_links": {},
                "created_at": credential.created_at,
                "updated_at": credential.updated_at,
            }

        connection_uri = cred_data.get("connection_uri")
        if not connection_uri:
            try:
                connection_uri = generator.build_connection_uri(cred_data)
            except Exception as exc:
                logger.warning(
                    "Failed to build connection URI for credential %s: %s",
                    credential.id,
                    exc,
                )
                connection_uri = ""

        qr_code_data = ""
        if connection_uri:
            try:
                qr_code_data = generator.generate_qr_code(cred_data)
            except Exception as exc:
                logger.warning(
                    "Failed to generate QR code for credential %s: %s",
                    credential.id,
                    exc,
                )

        return {
            "id": credential.id,
            "user_id": credential.user_id,
            "subscription_id": credential.subscription_id,
            "protocol_id": credential.protocol_id,
            "protocol_name": protocol_name,
            "server": cred_data.get("server") or cred_data.get("server_ip"),
            "port": cred_data.get("port") or protocol.default_port or 0,
            "server_domain": cred_data.get("server_domain"),
            "server_location": credential.server_location,
            "country_code": cred_data.get("country_code"),
            "credential_data": cred_data,
            "connection_uri": connection_uri,
            "qr_code_data": qr_code_data,
            "download_links": generator.get_download_links(),
            "created_at": credential.created_at,
            "updated_at": credential.updated_at,
        }

    def get_config_file(
        self, credential: UserCredential, config_type: str = "default"
    ) -> str:
        """Generate configuration file text for a credential."""
        protocol = self.db.query(Protocol).filter_by(id=credential.protocol_id).first()
        if not protocol:
            raise ValueError("Protocol not found")

        generator = get_credential_generator(cast(str, protocol.name))
        data: Dict[str, Any] = cast(Dict[str, Any], credential.credential_data or {})
        if not isinstance(data, dict):
            data = {}

        try:
            return generator.build_config_file(data, config_type)
        except Exception as exc:
            logger.warning(
                "Falling back to URI for credential %s config %s: %s",
                credential.id,
                config_type,
                exc,
            )
            if data.get("connection_uri"):
                return str(data["connection_uri"])
            try:
                return generator.build_connection_uri(data)
            except Exception:
                raise ValueError("Unable to build config for this credential")

    def get_connection_guide(
        self, credential: UserCredential, platform: str
    ) -> Dict[str, Any]:
        """Get connection guide for a platform."""
        protocol = self.db.query(Protocol).filter_by(id=credential.protocol_id).first()
        if not protocol:
            raise ValueError("Protocol not found")

        generator = get_credential_generator(cast(str, protocol.name))
        guide = generator.get_connection_guide(platform)

        return {
            "credential_id": credential.id,
            "protocol": protocol.name,
            "platform": platform,
            **guide,
        }

    def change_server(
        self, credential: UserCredential, new_country: Optional[str] = None
    ) -> UserCredential:
        """Change the backing protocol instance for an existing credential."""
        protocol = self.db.query(Protocol).filter_by(id=credential.protocol_id).first()
        if not protocol:
            raise ValueError("Protocol not found")

        cred_data: Dict[str, Any] = cast(
            Dict[str, Any], credential.credential_data or {}
        )
        if not isinstance(cred_data, dict):
            cred_data = {}

        current_instance_id = cred_data.get("instance_id")

        instance = self._select_instance(
            cast(int, protocol.id),
            new_country,
            exclude_instance_id=int(current_instance_id)
            if current_instance_id
            else None,
        )
        if not instance:
            raise ValueError("No alternative instances available")

        generator = get_credential_generator(cast(str, protocol.name))
        port = int(protocol.default_port or generator.default_ports[0])
        server_ip = str(instance.ip_address)

        # Decrement load for old FDM domain if exists
        old_fdm_domain_id = cred_data.get("fdm_domain_id")
        if old_fdm_domain_id:
            try:
                domain_id = int(old_fdm_domain_id)
            except (ValueError, TypeError):
                logger.warning(
                    "Invalid fdm_domain_id value: %s",
                    old_fdm_domain_id,
                )
                domain_id = None

            if domain_id is not None:
                old_fdm_domain = (
                    self.db.query(FdmDomain).filter_by(id=domain_id).first()
                )
                if old_fdm_domain:
                    fdm_service = FdmDomainService(self.db)
                    try:
                        fdm_service.decrement_domain_load(old_fdm_domain)
                        logger.info(
                            "Decremented load for old FDM domain %s (id=%s) on server change",
                            old_fdm_domain.domain_name,
                            old_fdm_domain.id,
                        )
                    except Exception as exc:
                        logger.error(
                            "Failed to decrement load for old FDM domain %s (id=%s): %s",
                            old_fdm_domain.domain_name,
                            old_fdm_domain.id,
                            exc,
                        )

        # Try to get FDM domain for new instance
        try:
            fdm_service = FdmDomainService(self.db)
            fdm_domain = fdm_service.select_domain_for_instance(instance)
            if fdm_domain:
                # Use FDM domain as server address
                server_address = fdm_domain.domain_name
                try:
                    fdm_service.increment_domain_load(fdm_domain)
                except Exception as exc:
                    logger.warning(
                        "Failed to increment domain load for %s (id=%s): %s",
                        fdm_domain.domain_name,
                        fdm_domain.id,
                        exc,
                    )
                logger.info(
                    "Using FDM domain %s (id=%s) for new instance %s on server change",
                    fdm_domain.domain_name,
                    fdm_domain.id,
                    instance.id,
                )
            else:
                # Fall back to IP address
                server_address = server_ip
                logger.debug(
                    "No FDM domain available for new instance %s, using IP address",
                    instance.id,
                )
        except Exception as exc:
            logger.warning(
                "FDM domain selection failed for new instance %s, falling back to IP: %s",
                instance.id,
                exc,
            )
            fdm_domain = None
            server_address = server_ip

        new_cred_data = generator.generate(
            server_ip=server_ip,
            port=port,
            user_id=cast(int, credential.user_id),
            subscription_id=cast(int, credential.subscription_id),
            country_code=cast(str, instance.country_code),
        )

        new_cred_data["instance_id"] = instance.id
        new_cred_data["flux_app_name"] = instance.flux_app_name
        new_cred_data["server_domain"] = (
            fdm_domain.domain_name
            if fdm_domain
            else f"{instance.flux_app_name}.runonflux.io"
        )
        new_cred_data.setdefault("server_ip", server_ip)
        new_cred_data.setdefault("server", server_address)
        new_cred_data.setdefault("country_code", instance.country_code)
        new_cred_data["is_active"] = True
        if fdm_domain:
            new_cred_data["fdm_domain_id"] = fdm_domain.id
        elif "fdm_domain_id" in new_cred_data:
            # Remove old fdm_domain_id if no new domain selected
            del new_cred_data["fdm_domain_id"]

        credential_obj = cast(Any, credential)
        credential_obj.credential_data = new_cred_data
        credential_obj.server_location = (
            f"{instance.country_name} ({instance.country_code})"
        )

        self.db.commit()
        self.db.refresh(credential)

        logger.info(
            "Changed server for credential %s to instance %s (%s)",
            credential.id,
            instance.id,
            instance.country_code,
        )

        return credential

    def delete_credential(self, credential: UserCredential) -> bool:
        """Delete a credential row."""
        # Check if credential has an FDM domain and decrement load
        cred_data: Dict[str, Any] = cast(
            Dict[str, Any], credential.credential_data or {}
        )
        if not isinstance(cred_data, dict):
            cred_data = {}

        fdm_domain_id = cred_data.get("fdm_domain_id")
        if fdm_domain_id:
            try:
                domain_id = int(fdm_domain_id)
            except (ValueError, TypeError):
                logger.warning(
                    "Invalid fdm_domain_id value: %s",
                    fdm_domain_id,
                )
                domain_id = None

            if domain_id is not None:
                fdm_domain = self.db.query(FdmDomain).filter_by(id=domain_id).first()
                if fdm_domain:
                    fdm_service = FdmDomainService(self.db)
                    try:
                        fdm_service.decrement_domain_load(fdm_domain)
                        logger.info(
                            "Decremented load for FDM domain %s (id=%s) on credential deletion",
                            fdm_domain.domain_name,
                            fdm_domain.id,
                        )
                    except Exception as exc:
                        logger.error(
                            "Failed to decrement load for FDM domain %s (id=%s): %s",
                            fdm_domain.domain_name,
                            fdm_domain.id,
                            exc,
                        )

        self.db.delete(credential)
        self.db.commit()
        logger.info("Deleted credential %s", credential.id)
        return True

    def _resolve_protocol(
        self,
        subscription: Subscription,
        explicit_protocol_id: Optional[int] = None,
    ) -> Optional[Protocol]:
        if explicit_protocol_id:
            protocol = (
                self.db.query(Protocol)
                .filter_by(id=int(explicit_protocol_id), is_active=True)
                .first()
            )
            if protocol:
                return protocol

        legacy_protocol_id = getattr(subscription, "protocol_id", None)
        if legacy_protocol_id:
            protocol = (
                self.db.query(Protocol)
                .filter_by(id=int(legacy_protocol_id), is_active=True)
                .first()
            )
            if protocol:
                return protocol

        existing = (
            self.db.query(UserCredential)
            .filter_by(subscription_id=subscription.id)
            .order_by(UserCredential.id.asc())
            .first()
        )
        if existing:
            protocol = (
                self.db.query(Protocol).filter_by(id=existing.protocol_id).first()
            )
            if protocol and protocol.is_active:
                return protocol

        return (
            self.db.query(Protocol)
            .filter_by(is_active=True)
            .order_by(Protocol.id.asc())
            .first()
        )

    def _select_instance(
        self,
        protocol_id: int,
        preferred_country: Optional[str] = None,
        exclude_instance_id: Optional[int] = None,
    ) -> Optional[ProtocolInstance]:
        """Select best available protocol instance."""
        query = (
            self.db.query(ProtocolInstance)
            .filter_by(protocol_id=protocol_id, is_active=True)
            .filter(ProtocolInstance.health_status.in_(["healthy", "degraded"]))
        )

        if exclude_instance_id:
            query = query.filter(ProtocolInstance.id != exclude_instance_id)

        if preferred_country:
            country_instances = query.filter_by(
                country_code=preferred_country.upper()
            ).all()
            if country_instances:
                return self._select_weighted_instance(
                    country_instances, preferred_country
                )

        instances = query.all()
        if not instances:
            return None
        return self._select_weighted_instance(instances, preferred_country)

    def _select_weighted_instance(
        self,
        instances: List[ProtocolInstance],
        preferred_country: Optional[str],
    ) -> ProtocolInstance:
        instance_ids = [cast(int, instance.id) for instance in instances]
        live_load_map = self._get_live_load_map(instance_ids)

        ranked = sorted(
            instances,
            key=lambda inst: self._instance_rank_tuple(
                inst,
                live_load_map.get(cast(int, inst.id), 0),
                preferred_country,
            ),
            reverse=True,
        )
        return ranked[0]

    def _instance_rank_tuple(
        self,
        instance: ProtocolInstance,
        current_load: int,
        preferred_country: Optional[str],
    ) -> tuple:
        health_rank_map = {"healthy": 2, "degraded": 1}
        health_rank = health_rank_map.get((instance.health_status or "").lower(), 0)
        capacity = self._estimate_instance_capacity(instance)
        utilization = min(current_load / max(capacity, 1), 1.5)

        country_bonus = 0.25
        if preferred_country and instance.country_code == preferred_country.upper():
            country_bonus = 1.0

        score = (
            (health_rank * 10.0) + (country_bonus * 4.0) + ((1.0 - utilization) * 6.0)
        )

        return (
            score,
            -current_load,
            -instance.id,
        )

    def _estimate_instance_capacity(self, instance: ProtocolInstance) -> int:
        if instance.health_status == "healthy":
            return 200
        if instance.health_status == "degraded":
            return 100
        return 50

    def _get_live_load_map(self, instance_ids: List[int]) -> Dict[int, int]:
        if not instance_ids:
            return {}

        five_minutes_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            minutes=5
        )

        rows = (
            self.db.query(
                ConnectionLog.instance_id,
                func.count(ConnectionLog.id).label("count"),
            )
            .filter(
                ConnectionLog.instance_id.in_(instance_ids),
                ConnectionLog.connected_at >= five_minutes_ago,
                ConnectionLog.disconnected_at.is_(None),
            )
            .group_by(ConnectionLog.instance_id)
            .all()
        )

        return {
            cast(int, row.instance_id): cast(int, row.count)
            for row in rows
            if row.instance_id is not None
        }

    @staticmethod
    def get_supported_protocols() -> List[str]:
        """Get list of supported protocols."""
        return list(GENERATORS.keys())

    @staticmethod
    def is_protocol_supported(protocol_name: str) -> bool:
        """Check if a protocol is supported."""
        return protocol_name.lower().replace("-", "_") in GENERATORS
