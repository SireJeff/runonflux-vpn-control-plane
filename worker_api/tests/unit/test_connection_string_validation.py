"""Unit tests for connection string IP validation.

Verifies that _get_domains_for_country JOINs protocol_instances so that
domains whose current_ip is not in an active PI row are excluded at the
SQL level.

The query structure (after the fix):
  .query(columns)
  .join(FdmDeployment, ...)             <- first join on query_obj
  .join(ProtocolInstance, ...)          <- second join on first-join result
  .filter(..., ProtocolInstance.is_active == True, ...)
  .order_by(...)
  .all()

IMPORTANT mock-chain detail:
  query_obj.join(A) returns join1_obj.
  join1_obj.join(B) returns join2_obj.
  join2_obj.filter(...) returns filter_obj.

  The second join's call is recorded on join1_obj, NOT on query_obj.
"""
from unittest.mock import MagicMock

from app.services.credentials.connection_string_service import ConnectionStringService

# Import the model class so we can compare by identity in assertions.
from app.models.ip_management import ProtocolInstance as PI


def _setup_mock_query(mock_db, rows=None):
    """Build a mock chain matching the 2-join query and return inspection handles.

    Returns (service, join1_obj) where join1_obj is the result of the first
    .join() call.  The second .join() is recorded on join1_obj, and the
    .filter() is recorded on join2_obj (join1_obj.join.return_value).
    """
    if rows is None:
        rows = []

    query_obj = mock_db.query.return_value
    join1_obj = query_obj.join.return_value  # after .join(FdmDeployment)
    join2_obj = join1_obj.join.return_value  # after .join(ProtocolInstance)
    filter_obj = join2_obj.filter.return_value  # after .filter(...)

    filter_obj.order_by.return_value.all.return_value = rows

    service = ConnectionStringService(mock_db)
    return service, join1_obj, join2_obj


def test_query_joins_protocol_instance():
    """_get_domains_for_country must JOIN ProtocolInstance on ip_address."""
    mock_db = MagicMock()
    service, join1_obj, _ = _setup_mock_query(mock_db)

    service._get_domains_for_country("NL", "ssh")

    assert (
        join1_obj.join.called
    ), "Second .join() should have been called on the first-join result"
    second_join_model = join1_obj.join.call_args[0][0]
    assert (
        second_join_model is PI
    ), f"Second join target should be ProtocolInstance, got {second_join_model}"


def test_filter_includes_protocol_instance_is_active():
    """_get_domains_for_country must filter ProtocolInstance.is_active == True."""
    mock_db = MagicMock()
    service, _, join2_obj = _setup_mock_query(mock_db)

    service._get_domains_for_country("NL", "ssh")

    filter_args = join2_obj.filter.call_args[0] if join2_obj.filter.call_args else ()

    has_pi_active = False
    for arg in filter_args:
        left = getattr(arg, "left", None)
        if left is not None:
            left_str = str(left)
            if "is_active" in left_str and "protocol_instance" in left_str.lower():
                has_pi_active = True
                break

    assert has_pi_active, (
        f"filter() should include ProtocolInstance.is_active == True. "
        f"Filter args: {[str(a) for a in filter_args]}"
    )


def test_join_uses_current_ip_for_on_clause():
    """JOIN ON clause must reference FdmDomain.current_ip (not domain_name or another column).

    This pins the JOIN semantics so a future refactor can't accidentally join
    on the wrong column (e.g., domain_id), which would silently allow stale IPs.
    """
    mock_db = MagicMock()

    service = ConnectionStringService(mock_db)
    try:
        service._get_domains_for_country("NL", "ssh")
    except Exception:
        pass  # We don't care about the return value, only the JOIN clause

    # Second JOIN is called on the result of the first .join(), so navigate one level deeper
    join1_obj = mock_db.query.return_value.join.return_value
    second_join_calls = join1_obj.join.call_args_list
    assert (
        len(second_join_calls) >= 1
    ), f"Expected PI JOIN, got {len(second_join_calls)}"

    # The PI JOIN call args: (ProtocolInstance, ON_clause)
    pi_join_args = second_join_calls[0].args
    assert len(pi_join_args) >= 1, "JOIN must have a model argument"
    assert pi_join_args[0].__name__ == "ProtocolInstance"

    # The ON clause (second arg) should reference FdmDomain.current_ip
    on_clause_str = str(pi_join_args[1])
    assert (
        "current_ip" in on_clause_str.lower()
    ), f"JOIN ON clause must reference current_ip, got: {on_clause_str}"


def test_inactive_protocol_instance_is_filtered():
    """Filter must include `ProtocolInstance.is_active == True` so inactive PI rows don't match.

    This is the complement to the structural JOIN test — verifies the filter
    actually excludes domains whose PI is inactive (zombie IPs).
    """
    mock_db = MagicMock()

    service = ConnectionStringService(mock_db)
    try:
        service._get_domains_for_country("NL", "ssh")
    except Exception:
        pass

    # Find the filter call args
    filter_call = (
        mock_db.query.return_value.join.return_value.join.return_value.filter.call_args
    )
    filter_args = filter_call.args if filter_call.args else []
    # SQLAlchemy filters come through *args
    all_filter_strs = [str(a) for a in filter_args]

    # Look for a clause mentioning both 'is_active' and 'protocol_instance' (case-insensitive)
    found_is_active_filter = False
    for s in all_filter_strs:
        if "is_active" in s.lower() and (
            "protocol_instance" in s.lower() or "protocolinstance" in s.lower()
        ):
            found_is_active_filter = True
            break

    assert (
        found_is_active_filter
    ), f"Filter must include ProtocolInstance.is_active == True. Got filters: {all_filter_strs}"
