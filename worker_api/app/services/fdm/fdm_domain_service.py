"""
Flux DNS Manager (FDM) Domain Service
Handles domain selection, load balancing, and distribution for FDM deployments
"""

import logging
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.core.constants import SUPPORTED_REGIONS
from app.models import ProtocolInstance
from app.models.fdm import FdmDeployment, FdmDomain

logger = logging.getLogger(__name__)


class FdmDomainService:
    """
    Service for managing FDM domains with load-based selection.

    Handles:
    - Selecting domains for instances based on load
    - Getting multi-region domain distributions
    - Managing domain load counters
    - Generating domain names for deployments
    - Distributing domains evenly across instances
    """

    def __init__(self, db: Session):
        """
        Initialize the FDM Domain Service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def get_available_regions(self) -> List[str]:
        """
        Get list of regions with active FDM deployments.

        Returns:
            List of region codes (e.g., ['us', 'eu', 'ap'])
        """
        regions = (
            self.db.query(FdmDeployment.region)
            .filter(FdmDeployment.is_active == True)
            .distinct()
            .all()
        )
        return [region[0] for region in regions]

    def select_domain_for_instance(
        self, instance: ProtocolInstance, preferred_region: Optional[str] = None
    ) -> Optional[FdmDomain]:
        """
        Select the best domain for a specific instance based on current load.

        Finds healthy domains pointing to this instance with the lowest
        assigned_users_count for load balancing.

        Args:
            instance: Protocol instance to find domain for
            preferred_region: Optional region filter

        Returns:
            FdmDomain with lowest load or None if no suitable domain found
        """
        query = (
            self.db.query(FdmDomain)
            .join(FdmDeployment)
            .filter(
                FdmDeployment.is_active == True,
                FdmDomain.current_instance_id == instance.id,
                FdmDomain.health_status == "healthy",
            )
        )

        if preferred_region:
            query = query.filter(FdmDeployment.region == preferred_region)

        # Select domain with lowest assigned users
        domain = query.order_by(FdmDomain.assigned_users_count.asc()).first()

        if not domain:
            logger.warning(
                f"No healthy domain found for instance {instance.id} "
                f"(preferred_region={preferred_region})"
            )

        return domain

    def get_multi_region_domains(
        self, regions: Optional[List[str]] = None, domains_per_region: int = 2
    ) -> Dict[str, List[FdmDomain]]:
        """
        Get domains from multiple regions with load-based selection.

        Args:
            regions: List of region codes to fetch. If None, uses all available regions.
            domains_per_region: Number of domains to fetch per region (default: 2)

        Returns:
            Dictionary mapping region -> list of domains sorted by load
        """
        if regions is None:
            regions = self.get_available_regions()

        result: Dict[str, List[FdmDomain]] = {}

        for region in regions:
            domains = (
                self.db.query(FdmDomain)
                .join(FdmDeployment)
                .filter(
                    FdmDeployment.is_active == True,
                    FdmDeployment.region == region,
                    FdmDomain.health_status == "healthy",
                )
                .order_by(FdmDomain.assigned_users_count.asc())
                .limit(domains_per_region)
                .all()
            )

            result[region] = domains

        return result

    def increment_domain_load(self, domain: FdmDomain) -> None:
        """
        Increment the assigned users count for a domain.

        Uses atomic UPDATE to prevent race conditions in multi-worker scenarios.

        Args:
            domain: Domain to increment load for

        Raises:
            Exception: If database operation fails
        """
        try:
            stmt = (
                update(FdmDomain)
                .where(FdmDomain.id == domain.id)
                .values(
                    assigned_users_count=FdmDomain.assigned_users_count + 1,
                    updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
            self.db.execute(stmt)
            self.db.commit()
            self.db.refresh(domain)
            logger.debug(
                f"Incremented load for domain {domain.domain_name}: "
                f"{domain.assigned_users_count}"
            )
        except Exception as e:
            self.db.rollback()
            logger.error(
                f"Failed to increment load for domain {domain.domain_name}: {e}"
            )
            raise

    def decrement_domain_load(self, domain: FdmDomain) -> None:
        """
        Decrement the assigned users count for a domain (minimum 0).

        Uses atomic UPDATE with GREATEST to prevent race conditions and
        ensure count never goes below zero in multi-worker scenarios.

        Args:
            domain: Domain to decrement load for

        Raises:
            Exception: If database operation fails
        """
        try:
            # Use GREATEST to ensure count never goes below 0
            stmt = (
                update(FdmDomain)
                .where(FdmDomain.id == domain.id)
                .values(
                    assigned_users_count=(
                        func.greatest(FdmDomain.assigned_users_count - 1, 0)
                    ),
                    updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
            self.db.execute(stmt)
            self.db.commit()
            self.db.refresh(domain)
            logger.debug(
                f"Decremented load for domain {domain.domain_name}: "
                f"{domain.assigned_users_count}"
            )
        except Exception as e:
            self.db.rollback()
            logger.error(
                f"Failed to decrement load for domain {domain.domain_name}: {e}"
            )
            raise

    def get_domain_by_name(self, domain_name: str) -> Optional[FdmDomain]:
        """
        Get a domain by its domain name.

        Args:
            domain_name: Full domain name (e.g., 'us-01-a1.operator6.example.invalid')

        Returns:
            FdmDomain or None if not found
        """
        return (
            self.db.query(FdmDomain)
            .filter(FdmDomain.domain_name == domain_name)
            .first()
        )

    @staticmethod
    def generate_domain_names(
        base_domain: str,
        count: int,
        existing_domain_ids: Optional[set] = None,
    ) -> List[tuple]:
        """
        Generate CDN-style domain names for protocol-agnostic deployments.

        Format: {prefix}-{number}.{base_domain}
        Example: cdn-01.operator4.example.invalid, media-02.operator4.example.invalid

        Args:
            base_domain: Base domain (e.g., 'operator4.example.invalid')
            count: Number of domains to generate
            existing_domain_ids: Set of already-used domain_ids to skip

        Returns:
            List of (domain_name, domain_id) tuples
        """
        from app.core.constants import CDN_PREFIXES

        if existing_domain_ids is None:
            existing_domain_ids = set()

        results = []
        prefix_idx = 0

        for number in range(1, 100):  # 01-99
            number_str = f"{number:02d}"

            prefix = CDN_PREFIXES[prefix_idx % len(CDN_PREFIXES)]
            prefix_idx += 1

            domain_id = f"{prefix}-{number_str}"

            if domain_id in existing_domain_ids:
                continue

            domain_name = f"{domain_id}.{base_domain}"
            results.append((domain_name, domain_id))

            if len(results) >= count:
                break

        return results
