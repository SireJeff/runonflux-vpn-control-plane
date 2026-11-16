"""
FluxCloud API Resilience Module

Provides retry logic with exponential backoff and circuit breaker pattern
to handle transient FluxCloud API failures (502, 503, 504, 429).

Circuit Breaker States:
    CLOSED: Normal operation, requests go through
    OPEN: API is down, fail fast without making requests
    HALF_OPEN: Testing if API recovered, limited requests allowed

Usage:
    from app.services.flux.resilience import (
        create_retry_decorator,
        AsyncCircuitBreaker,
        RetryConfig,
        CircuitBreakerConfig,
    )

    circuit_breaker = AsyncCircuitBreaker(CircuitBreakerConfig())
    retry_decorator = create_retry_decorator(RetryConfig())

    @retry_decorator
    async def make_request():
        await circuit_breaker.check()
        try:
            result = await do_request()
            await circuit_breaker.record_success()
            return result
        except Exception as e:
            await circuit_breaker.record_failure()
            raise
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Set

from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


# HTTP status codes that indicate transient failures worth retrying
RETRYABLE_STATUS_CODES: Set[int] = {502, 503, 504, 429}

# Status codes that should NOT be retried (client errors, auth issues)
NON_RETRYABLE_STATUS_CODES: Set[int] = {400, 401, 403, 404, 409}


class CircuitState(Enum):
    """Circuit breaker states"""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing fast, API is down
    HALF_OPEN = "half_open"  # Testing recovery


class FluxAPITransientError(Exception):
    """
    Raised for transient API errors that should be retried.

    These include:
    - HTTP 502 Bad Gateway
    - HTTP 503 Service Unavailable
    - HTTP 504 Gateway Timeout
    - HTTP 429 Too Many Requests
    - Connection timeouts
    - Connection errors
    """

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class FluxAPICircuitOpenError(Exception):
    """
    Raised when circuit breaker is open (API is known to be down).

    Fail fast without making actual requests to avoid wasting time
    and resources when the API is experiencing issues.
    """

    def __init__(self, recovery_time: float):
        self.recovery_time = recovery_time
        super().__init__(
            f"FluxCloud API circuit breaker is OPEN. "
            f"Will retry in {recovery_time:.0f} seconds."
        )


@dataclass
class RetryConfig:
    """Configuration for retry behavior"""

    max_attempts: int = 3
    min_wait_seconds: float = 2.0
    max_wait_seconds: float = 60.0

    def __post_init__(self):
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.min_wait_seconds <= 0:
            raise ValueError("min_wait_seconds must be positive")
        if self.max_wait_seconds < self.min_wait_seconds:
            raise ValueError("max_wait_seconds must be >= min_wait_seconds")


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior"""

    failure_threshold: int = 5  # Failures before opening circuit
    recovery_timeout: float = 120.0  # Seconds to wait before trying again
    half_open_max_calls: int = 3  # Test calls allowed in half-open state

    def __post_init__(self):
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if self.recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be positive")
        if self.half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be at least 1")


@dataclass
class CircuitBreakerStatus:
    """Status information for monitoring"""

    state: CircuitState
    failure_count: int
    last_failure_time: Optional[float]
    time_until_recovery: Optional[float]
    half_open_calls: int


class AsyncCircuitBreaker:
    """
    Async-safe circuit breaker implementation.

    Prevents cascading failures by "opening" the circuit when too many
    consecutive failures occur, failing fast instead of trying requests
    that are likely to fail.

    State transitions:
        CLOSED -> OPEN: After failure_threshold consecutive failures
        OPEN -> HALF_OPEN: After recovery_timeout seconds
        HALF_OPEN -> CLOSED: After half_open_max_calls successes
        HALF_OPEN -> OPEN: On any failure
    """

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Current circuit state"""
        return self._state

    def get_status(self) -> CircuitBreakerStatus:
        """Get current circuit breaker status for monitoring"""
        time_until_recovery = None
        if self._state == CircuitState.OPEN and self._last_failure_time:
            elapsed = time.time() - self._last_failure_time
            remaining = self.config.recovery_timeout - elapsed
            time_until_recovery = max(0, remaining)

        return CircuitBreakerStatus(
            state=self._state,
            failure_count=self._failure_count,
            last_failure_time=self._last_failure_time,
            time_until_recovery=time_until_recovery,
            half_open_calls=self._half_open_calls,
        )

    async def check(self) -> None:
        """
        Check if request should proceed.

        Raises:
            FluxAPICircuitOpenError: If circuit is open
        """
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return

            if self._state == CircuitState.OPEN:
                # Check if enough time has passed to try again
                if self._last_failure_time:
                    elapsed = time.time() - self._last_failure_time
                    if elapsed >= self.config.recovery_timeout:
                        # Transition to half-open
                        logger.info(
                            "FluxCloud circuit breaker transitioning from OPEN to HALF_OPEN "
                            f"after {elapsed:.0f}s recovery timeout"
                        )
                        self._state = CircuitState.HALF_OPEN
                        self._half_open_calls = 0
                    else:
                        # Still in recovery period
                        remaining = self.config.recovery_timeout - elapsed
                        raise FluxAPICircuitOpenError(remaining)

            if self._state == CircuitState.HALF_OPEN:
                # Allow limited test calls
                if self._half_open_calls >= self.config.half_open_max_calls:
                    # Waiting for results before allowing more calls
                    raise FluxAPICircuitOpenError(5.0)
                self._half_open_calls += 1

    async def record_success(self) -> None:
        """Record a successful request"""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                # Successful test calls close the circuit
                if self._half_open_calls >= self.config.half_open_max_calls:
                    logger.info(
                        "FluxCloud circuit breaker CLOSING after "
                        f"{self._half_open_calls} successful test calls"
                    )
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._last_failure_time = None
                    self._half_open_calls = 0
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0

    async def record_failure(self) -> None:
        """Record a failed request"""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open immediately opens circuit
                logger.warning(
                    "FluxCloud circuit breaker OPENING from HALF_OPEN after failure"
                )
                self._state = CircuitState.OPEN
                self._half_open_calls = 0

            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.config.failure_threshold:
                    logger.warning(
                        f"FluxCloud circuit breaker OPENING after "
                        f"{self._failure_count} consecutive failures"
                    )
                    self._state = CircuitState.OPEN

    async def reset(self) -> None:
        """Manually reset the circuit breaker to closed state"""
        async with self._lock:
            logger.info("FluxCloud circuit breaker manually RESET to CLOSED")
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None
            self._half_open_calls = 0


def create_retry_decorator(config: Optional[RetryConfig] = None) -> Callable:
    """
    Create a tenacity retry decorator with the specified configuration.

    Args:
        config: Retry configuration (uses defaults if None)

    Returns:
        A decorator that can be applied to async functions

    Usage:
        retry = create_retry_decorator(RetryConfig(max_attempts=3))

        @retry
        async def make_request():
            ...
    """
    cfg = config or RetryConfig()

    def decorator(func: Callable) -> Callable:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None

            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(cfg.max_attempts),
                wait=wait_exponential(
                    min=cfg.min_wait_seconds,
                    max=cfg.max_wait_seconds,
                ),
                retry=retry_if_exception_type(FluxAPITransientError),
                reraise=True,
            ):
                with attempt:
                    try:
                        return await func(*args, **kwargs)
                    except FluxAPITransientError as e:
                        last_exception = e
                        attempt_num = attempt.retry_state.attempt_number
                        logger.warning(
                            f"FluxCloud API transient error (attempt {attempt_num}/{cfg.max_attempts}): {e}"
                        )
                        raise

            # If we get here, all retries failed
            if last_exception:
                raise last_exception

        return wrapper

    return decorator


def is_retryable_status_code(status_code: int) -> bool:
    """Check if an HTTP status code indicates a retryable error"""
    return status_code in RETRYABLE_STATUS_CODES


def is_non_retryable_status_code(status_code: int) -> bool:
    """Check if an HTTP status code should NOT be retried"""
    return status_code in NON_RETRYABLE_STATUS_CODES
