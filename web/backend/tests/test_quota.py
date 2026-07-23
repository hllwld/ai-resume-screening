import asyncio

import pytest

from app.config import Settings
from app.quota import DailyQuota, QuotaExceeded


def test_daily_quota_is_atomic_and_all_or_nothing():
    quota = DailyQuota(
        Settings(
            per_ip_daily_resume_limit=10,
            global_daily_resume_limit=50,
        )
    )

    async def scenario():
        first = await quota.reserve("192.0.2.1", 8)
        assert first.per_ip_remaining == 2
        assert first.global_remaining == 42

        with pytest.raises(QuotaExceeded):
            await quota.reserve("192.0.2.1", 3)

        unchanged = await quota.current("192.0.2.1")
        assert unchanged.per_ip_used == 8
        assert unchanged.global_used == 8

    asyncio.run(scenario())


def test_global_limit_applies_across_ips():
    quota = DailyQuota(
        Settings(
            per_ip_daily_resume_limit=50,
            global_daily_resume_limit=50,
        )
    )
    async def scenario():
        await quota.reserve("192.0.2.1", 30)
        await quota.reserve("192.0.2.2", 20)

        with pytest.raises(QuotaExceeded):
            await quota.reserve("192.0.2.3", 1)

    asyncio.run(scenario())


def test_quota_survives_restart(tmp_path):
    database = tmp_path / "quota.sqlite3"
    settings = Settings(
        per_ip_daily_resume_limit=10,
        global_daily_resume_limit=50,
        quota_db_path=str(database),
    )

    asyncio.run(DailyQuota(settings).reserve("192.0.2.10", 4))
    restored = asyncio.run(DailyQuota(settings).current("192.0.2.10"))

    assert restored.per_ip_used == 4
    assert restored.global_used == 4
