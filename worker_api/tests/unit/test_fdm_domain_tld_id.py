"""Phase 4a Task 1: FdmDomain gains a nullable tld_id FK column.

Group A (VM) test — imports app.models.fdm, which pulls app.core.database,
so it runs inside the worker-api container via the _vm_drive runner rather
than locally.
"""


def test_fdm_domain_has_nullable_tld_id_column():
    from app.models.fdm import FdmDomain

    col = FdmDomain.__table__.columns.get("tld_id")
    assert col is not None, "FdmDomain must gain a tld_id column (Phase 4a)"
    assert col.nullable is True, "tld_id must be nullable (legacy rows + 4b transition)"

    # FK must point at registered_tlds.id with ON DELETE SET NULL so a
    # soft-deleted/hard-removed TLD doesn't orphan-cascade the domains.
    fks = list(col.foreign_keys)
    assert len(fks) == 1, f"tld_id must have exactly one FK, got {len(fks)}"
    fk = fks[0]
    assert fk.column.table.name == "registered_tlds"
    assert fk.column.name == "id"
    assert (fk.ondelete or "").upper() == "SET NULL"
