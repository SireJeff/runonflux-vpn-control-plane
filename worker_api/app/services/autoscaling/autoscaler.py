"""
FluxVPN Auto-scaling Service

Automatically scales protocol instances based on:
- Connection load per instance
- Health check failures
- Time-based patterns (peak hours)
- Active user count

Uses Redis for configuration persistence and coordination.
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from inspect import isawaitable
from typing import Any, Dict, List, Optional, cast

from sqlalchemy.orm import Session

from app.core.redis_client import get_redis
from app.models import Protocol, ProtocolInstance, Subscription
from app.services.flux.node_manager import FluxNodeManager, NodeDeploymentError

logger = logging.getLogger(__name__)


class ScalingAction(Enum):
    """Types of scaling actions"""

    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    NO_ACTION = "no_action"


@dataclass
class ScalingRule:
    """Configuration for auto-scaling behavior"""

    enabled: bool = True
    min_instances: int = 5
    max_instances: int = 50

    # Thresholds (0.0 to 1.0)
    scale_up_threshold: float = 0.8  # Scale up when load > 80%
    scale_down_threshold: float = 0.3  # Scale down when load < 30%

    # Connections per instance
    target_connections_per_instance: int = 100
    max_connections_per_instance: int = 150

    # Timing
    cooldown_minutes: int = 5  # Min time between scaling actions
    health_check_failures_threshold: int = 3  # Failed checks before action

    # Scale amounts
    scale_up_count: int = 2  # Instances to add when scaling up
    scale_down_count: int = 1  # Instances to remove when scaling down


@dataclass
class ScalingDecision:
    """Result of a scaling evaluation"""

    protocol_name: str
    action: ScalingAction
    reason: str
    current_instances: int
    target_instances: int
    current_load: float
    timestamp: datetime


class AutoScaler:
    """
    Automatic scaling manager for FluxVPN protocol instances

    Features:
    - Load-based scaling (connections per instance)
    - Health-based scaling (replace unhealthy instances)
    - Time-based scaling (peak hours support)
    - Cooldown periods to prevent thrashing
    - Per-protocol configuration
    """

    REDIS_CONFIG_KEY = "fluxvpn:autoscaling:config"
    REDIS_STATE_KEY = "fluxvpn:autoscaling:state"
    REDIS_HISTORY_KEY = "fluxvpn:autoscaling:history"

    def __init__(self):
        """Initialize the auto-scaler"""
        self.node_manager: Optional[FluxNodeManager] = None
        self._load_config()

    def _load_config(self):
        """Load configuration from Redis or use defaults"""
        try:
            redis = get_redis()
            if redis is None:
                self.global_rule = ScalingRule()
                self.protocol_rules = {}
                return
            config_json = redis.get(self.REDIS_CONFIG_KEY)
            if config_json:
                config_data = json.loads(config_json)
                self.global_rule = ScalingRule(**config_data.get("global", {}))
                self.protocol_rules: Dict[str, ScalingRule] = {
                    name: ScalingRule(**rule_data)
                    for name, rule_data in config_data.get("protocols", {}).items()
                }
            else:
                self.global_rule = ScalingRule()
                self.protocol_rules = {}
        except Exception as e:
            logger.warning(f"Failed to load autoscaling config from Redis: {e}")
            self.global_rule = ScalingRule()
            self.protocol_rules = {}

    def _save_config(self):
        """Save configuration to Redis"""
        try:
            redis = get_redis()
            if redis is None:
                logger.warning("Redis not available - cannot save autoscaling config")
                return
            config_data = {
                "global": asdict(self.global_rule),
                "protocols": {
                    name: asdict(rule) for name, rule in self.protocol_rules.items()
                },
            }
            redis.set(self.REDIS_CONFIG_KEY, json.dumps(config_data))
        except Exception as e:
            logger.error(f"Failed to save autoscaling config: {e}")

    def _get_state(self) -> Dict[str, Any]:
        """Get current autoscaling state from Redis"""
        try:
            redis = get_redis()
            if redis is None:
                return {}
            state_json = redis.get(self.REDIS_STATE_KEY)
            if isawaitable(state_json):
                return {}
            if state_json:
                return json.loads(cast(str, state_json))
        except Exception as e:
            logger.warning(f"Failed to load autoscaling state: {e}")
        return {}

    def _save_state(self, state: Dict[str, Any]):
        """Save autoscaling state to Redis"""
        try:
            redis = get_redis()
            if redis is None:
                return
            redis.set(self.REDIS_STATE_KEY, json.dumps(state))
        except Exception as e:
            logger.error(f"Failed to save autoscaling state: {e}")

    def _record_action(self, decision: ScalingDecision):
        """Record scaling action to history"""
        try:
            redis = get_redis()
            if redis is None:
                return
            history_entry = {
                "protocol": decision.protocol_name,
                "action": decision.action.value,
                "reason": decision.reason,
                "current_instances": decision.current_instances,
                "target_instances": decision.target_instances,
                "load": decision.current_load,
                "timestamp": decision.timestamp.isoformat(),
            }
            # Keep last 100 actions
            redis.lpush(self.REDIS_HISTORY_KEY, json.dumps(history_entry))
            redis.ltrim(self.REDIS_HISTORY_KEY, 0, 99)
        except Exception as e:
            logger.error(f"Failed to record scaling action: {e}")

    def get_config(self) -> Dict[str, Any]:
        """Get current configuration"""
        state = self._get_state()
        return {
            "enabled": self.global_rule.enabled,
            "rules": {
                "global": asdict(self.global_rule),
                "protocols": {
                    name: asdict(rule) for name, rule in self.protocol_rules.items()
                },
            },
            "last_action": state.get("last_action"),
            "next_check": state.get("next_check"),
        }

    def update_config(
        self,
        enabled: bool = True,
        min_instances: int = 5,
        max_instances: int = 50,
        scale_up_threshold: float = 0.8,
        scale_down_threshold: float = 0.3,
        cooldown_minutes: int = 5,
        protocol_name: Optional[str] = None,
    ):
        """
        Update auto-scaling configuration

        Args:
            protocol_name: If provided, update only this protocol's rule
        """
        rule = ScalingRule(
            enabled=enabled,
            min_instances=min_instances,
            max_instances=max_instances,
            scale_up_threshold=scale_up_threshold,
            scale_down_threshold=scale_down_threshold,
            cooldown_minutes=cooldown_minutes,
        )

        if protocol_name:
            self.protocol_rules[protocol_name] = rule
        else:
            self.global_rule = rule

        self._save_config()
        logger.info(
            f"Updated autoscaling config: enabled={enabled}, min={min_instances}, max={max_instances}"
        )

    def get_rule_for_protocol(self, protocol_name: str) -> ScalingRule:
        """Get the scaling rule for a specific protocol"""
        return self.protocol_rules.get(protocol_name, self.global_rule)

    def _can_scale(self, protocol_name: str) -> bool:
        """Check if we're outside the cooldown period"""
        state = self._get_state()
        last_action_time = state.get(f"last_action_{protocol_name}")

        if not last_action_time:
            return True

        rule = self.get_rule_for_protocol(protocol_name)
        last_action = datetime.fromisoformat(last_action_time)
        cooldown_end = last_action + timedelta(minutes=rule.cooldown_minutes)

        return datetime.now(timezone.utc).replace(tzinfo=None) > cooldown_end

    def _calculate_load(
        self, db: Session, protocol: Protocol, instances: List[ProtocolInstance]
    ) -> float:
        """
        Calculate current load for a protocol

        Load is based on:
        - Active connections per instance
        - Number of active credentials assigned
        """
        if not instances:
            return 0.0

        active_instances = [i for i in instances if i.is_active]
        if not active_instances:
            return 1.0  # All instances down = max load

        protocol_name = cast(str, protocol.name)
        rule = self.get_rule_for_protocol(protocol_name)

        # Method 1: Connection-based load (the only working method).
        # Method 2 (credential-count via UserCredential.is_active) was removed
        # because UserCredential is a legacy model — UserCredentialV2 has no
        # is_active column. Connection-based load is sufficient for scaling
        # decisions and avoids the AttributeError that was firing every 5 min.
        total_connections = sum(i.current_connections or 0 for i in active_instances)
        max_capacity = len(active_instances) * rule.target_connections_per_instance
        connection_load = total_connections / max_capacity if max_capacity > 0 else 0

        return connection_load

    def _evaluate_protocol(
        self, db: Session, protocol: Protocol, instances: List[ProtocolInstance]
    ) -> ScalingDecision:
        """
        Evaluate scaling needs for a single protocol

        Returns a ScalingDecision with recommended action.
        """
        protocol_name = cast(str, protocol.name)
        rule = self.get_rule_for_protocol(protocol_name)
        active_instances = [i for i in instances if i.is_active]
        current_count = len(active_instances)
        current_load = self._calculate_load(db, protocol, instances)

        # Default: no action
        action = ScalingAction.NO_ACTION
        target_count = current_count
        reason = "Load within acceptable range"

        # Check if scaling is enabled
        if not rule.enabled:
            reason = "Auto-scaling disabled for this protocol"

        # Check cooldown
        elif not self._can_scale(protocol_name):
            reason = "In cooldown period"

        # Scale UP check
        elif current_load > rule.scale_up_threshold:
            if current_count < rule.max_instances:
                action = ScalingAction.SCALE_UP
                target_count = min(
                    current_count + rule.scale_up_count, rule.max_instances
                )
                reason = f"Load {current_load:.1%} exceeds threshold {rule.scale_up_threshold:.1%}"
            else:
                reason = f"At max instances ({rule.max_instances}), cannot scale up"

        # Scale DOWN check
        elif current_load < rule.scale_down_threshold:
            if current_count > rule.min_instances:
                action = ScalingAction.SCALE_DOWN
                target_count = max(
                    current_count - rule.scale_down_count, rule.min_instances
                )
                reason = f"Load {current_load:.1%} below threshold {rule.scale_down_threshold:.1%}"
            else:
                reason = f"At min instances ({rule.min_instances}), cannot scale down"

        # Health check: ensure minimum instances
        elif current_count < rule.min_instances:
            action = ScalingAction.SCALE_UP
            target_count = rule.min_instances
            reason = f"Below minimum instances ({current_count} < {rule.min_instances})"

        return ScalingDecision(
            protocol_name=protocol_name,
            action=action,
            reason=reason,
            current_instances=current_count,
            target_instances=target_count,
            current_load=current_load,
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        )

    async def check_and_scale(self, db: Session) -> Dict[str, Any]:
        """
        Main entry point: check all protocols and scale as needed

        Returns summary of actions taken.
        """
        if not self.global_rule.enabled:
            return {
                "success": False,
                "message": "Auto-scaling is globally disabled",
                "actions": [],
                "protocols_checked": 0,
                "decisions": {},
            }

        logger.info("Starting auto-scaling check...")

        # Get all protocols
        protocols = db.query(Protocol).filter(Protocol.is_active == True).all()

        actions_taken = []
        decisions = {}

        # Initialize node manager
        self.node_manager = FluxNodeManager()

        try:
            for protocol in protocols:
                # Get instances for this protocol
                instances = (
                    db.query(ProtocolInstance)
                    .filter(ProtocolInstance.protocol_id == protocol.id)
                    .all()
                )

                # Evaluate scaling need
                decision = self._evaluate_protocol(db, protocol, instances)
                decisions[protocol.name] = {
                    "action": decision.action.value,
                    "reason": decision.reason,
                    "current": decision.current_instances,
                    "target": decision.target_instances,
                    "load": f"{decision.current_load:.1%}",
                }

                # Execute scaling action if needed
                if decision.action != ScalingAction.NO_ACTION:
                    try:
                        if decision.action == ScalingAction.SCALE_UP:
                            added, _ = await self.node_manager.scale_protocol(
                                db=db,
                                protocol=protocol,
                                target_count=decision.target_instances,
                            )
                            actions_taken.append(
                                {
                                    "protocol": protocol.name,
                                    "action": "scale_up",
                                    "instances_added": len(added),
                                }
                            )

                        elif decision.action == ScalingAction.SCALE_DOWN:
                            _, removed = await self.node_manager.scale_protocol(
                                db=db,
                                protocol=protocol,
                                target_count=decision.target_instances,
                            )
                            actions_taken.append(
                                {
                                    "protocol": protocol.name,
                                    "action": "scale_down",
                                    "instances_removed": len(removed),
                                }
                            )

                        # Record the action
                        self._record_action(decision)

                        # Update cooldown state
                        state = self._get_state()
                        state[f"last_action_{protocol.name}"] = (
                            datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
                        )
                        state["last_action"] = (
                            datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
                        )
                        self._save_state(state)

                        logger.info(
                            f"Scaled {protocol.name}: {decision.action.value} "
                            f"({decision.current_instances} -> {decision.target_instances})"
                        )

                    except NodeDeploymentError as e:
                        logger.error(f"Failed to scale {protocol.name}: {e}")
                        actions_taken.append(
                            {
                                "protocol": protocol.name,
                                "action": "error",
                                "error": str(e),
                            }
                        )

        finally:
            await self.node_manager.close()
            self.node_manager = None

        return {
            "success": True,
            "actions": actions_taken,
            "protocols_checked": len(protocols),
            "decisions": decisions,
        }

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent scaling action history"""
        try:
            redis = get_redis()
            if redis is None:
                return []
            history_json = redis.lrange(self.REDIS_HISTORY_KEY, 0, limit - 1)
            if isawaitable(history_json):
                logger.warning(
                    "Async redis client returned awaitable in sync get_history path"
                )
                return []
            return [json.loads(h) for h in cast(List[Any], history_json)]
        except Exception as e:
            logger.error(f"Failed to get scaling history: {e}")
            return []


# =============================================================================
# BACKGROUND TASK SCHEDULER
# =============================================================================


async def run_autoscaling_check(db: Session):
    """
    Background task to run auto-scaling checks periodically

    Should be called by a scheduler (e.g., APScheduler, Celery beat)
    """
    autoscaler = AutoScaler()
    result = await autoscaler.check_and_scale(db)
    logger.info(
        f"Auto-scaling check complete: {len(result.get('actions', []))} actions taken"
    )
    return result
