import asyncio
from types import SimpleNamespace
from app.services.free_config.membership_verifier import MembershipVerifier, VerificationResult


class _FakeMember:
    def __init__(self, status, is_member=None):
        self.status = status
        self.is_member = is_member


class _FakeBot:
    def __init__(self, mapping=None, raise_for=None):
        self._mapping = mapping or {}
        self._raise_for = raise_for or set()

    async def get_chat_member(self, chat_id, user_id):
        if chat_id in self._raise_for:
            raise RuntimeError("bot is not an admin")
        return self._mapping.get(chat_id, _FakeMember("left"))


def _chan(chat_id=None, username=None):
    return SimpleNamespace(chat_id=chat_id, username=username, title="t", invite_url=None)


def test_all_joined_is_ok():
    bot = _FakeBot({1: _FakeMember("member"), 2: _FakeMember("administrator")})
    v = MembershipVerifier(bot)
    res = asyncio.run(v.check(99, [_chan(chat_id=1), _chan(chat_id=2)]))
    assert res.ok and not res.missing and not res.unverifiable


def test_left_channel_is_missing_not_ok():
    bot = _FakeBot({1: _FakeMember("member"), 2: _FakeMember("left")})
    res = asyncio.run(MembershipVerifier(bot).check(99, [_chan(chat_id=1), _chan(chat_id=2)]))
    assert res.ok is False
    assert len(res.missing) == 1 and not res.unverifiable


def test_restricted_non_member_is_missing():
    bot = _FakeBot({1: _FakeMember("restricted", is_member=False)})
    res = asyncio.run(MembershipVerifier(bot).check(99, [_chan(chat_id=1)]))
    assert res.ok is False and len(res.missing) == 1


def test_restricted_member_counts_as_joined():
    bot = _FakeBot({1: _FakeMember("restricted", is_member=True)})
    res = asyncio.run(MembershipVerifier(bot).check(99, [_chan(chat_id=1)]))
    assert res.ok is True


def test_exception_is_unverifiable_and_fails_closed():
    bot = _FakeBot({1: _FakeMember("member")}, raise_for={2})
    res = asyncio.run(MembershipVerifier(bot).check(99, [_chan(chat_id=1), _chan(chat_id=2)]))
    assert res.ok is False
    assert len(res.unverifiable) == 1 and not res.missing


class _MsgRaisingBot:
    """Raises an exception with a specific message for a given chat_id."""

    def __init__(self, raises=None):
        # raises: {chat_id: exception_message}
        self._raises = raises or {}

    async def get_chat_member(self, chat_id, user_id):
        if chat_id in self._raises:
            raise Exception(self._raises[chat_id])
        return _FakeMember("member")


def test_participant_id_invalid_is_missing_not_unverifiable():
    # Telegram raises "Participant_id_invalid" from getChatMember for a NON-member
    # of a broadcast channel (members resolve cleanly). This must be treated as
    # "not joined" (-> join screen), NOT as an infra failure (-> fail closed).
    bot = _MsgRaisingBot({1: "Participant_id_invalid"})
    res = asyncio.run(MembershipVerifier(bot).check(99, [_chan(chat_id=1)]))
    assert res.ok is False
    assert len(res.missing) == 1 and not res.unverifiable


def test_user_not_participant_is_missing():
    bot = _MsgRaisingBot({1: "USER_NOT_PARTICIPANT"})
    res = asyncio.run(MembershipVerifier(bot).check(99, [_chan(chat_id=1)]))
    assert res.ok is False
    assert len(res.missing) == 1 and not res.unverifiable


def test_bot_not_admin_stays_unverifiable():
    # Genuine infra failures (bot not admin, chat not found, network) must STILL
    # fail closed as unverifiable — the fix must not over-broaden.
    bot = _MsgRaisingBot({1: "Chat admin required"})
    res = asyncio.run(MembershipVerifier(bot).check(99, [_chan(chat_id=1)]))
    assert res.ok is False
    assert len(res.unverifiable) == 1 and not res.missing
