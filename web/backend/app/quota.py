import asyncio
import hashlib
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Settings


@dataclass(frozen=True)
class QuotaSnapshot:
    date: str
    per_ip_limit: int
    per_ip_used: int
    per_ip_remaining: int
    global_limit: int
    global_used: int
    global_remaining: int

    def public_dict(self) -> dict[str, int | str]:
        return asdict(self)


class QuotaExceeded(RuntimeError):
    def __init__(self, message: str, snapshot: QuotaSnapshot):
        super().__init__(message)
        self.snapshot = snapshot


class DailyQuota:
    def __init__(self, settings: Settings):
        self.settings = settings
        try:
            self._timezone = ZoneInfo(settings.quota_timezone)
        except ZoneInfoNotFoundError:
            if settings.quota_timezone != "Asia/Shanghai":
                raise
            # Windows 和精简容器可能未安装 IANA 时区库。中国标准时间没有
            # 夏令时切换，可安全降级为固定 UTC+8。
            self._timezone = timezone(timedelta(hours=8))
        self._date = ""
        self._per_ip: dict[str, int] = {}
        self._global_used = 0
        self._lock = asyncio.Lock()
        self._db_path = settings.quota_db_path
        if self._db_path:
            database_path = Path(self._db_path)
            database_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(database_path) as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS daily_quota (
                        quota_date TEXT NOT NULL,
                        ip_address TEXT NOT NULL,
                        resume_count INTEGER NOT NULL,
                        PRIMARY KEY (quota_date, ip_address)
                    )
                    """
                )

    def _today(self) -> str:
        return datetime.now(self._timezone).date().isoformat()

    @staticmethod
    def _ip_key(ip_address: str) -> str:
        return hashlib.sha256(ip_address.encode()).hexdigest()

    def _reset_if_needed(self) -> None:
        today = self._today()
        if self._date != today:
            self._date = today
            self._per_ip.clear()
            self._global_used = 0
            if self._db_path:
                with sqlite3.connect(self._db_path) as connection:
                    connection.execute(
                        "DELETE FROM daily_quota WHERE quota_date <> ?",
                        (today,),
                    )
                    rows = connection.execute(
                        """
                        SELECT ip_address, resume_count
                        FROM daily_quota
                        WHERE quota_date = ?
                        """,
                        (today,),
                    ).fetchall()
                self._per_ip = {ip: count for ip, count in rows}
                self._global_used = sum(self._per_ip.values())

    def _persist_ip(self, ip_key: str) -> None:
        if not self._db_path:
            return
        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                """
                INSERT INTO daily_quota (quota_date, ip_address, resume_count)
                VALUES (?, ?, ?)
                ON CONFLICT(quota_date, ip_address)
                DO UPDATE SET resume_count = excluded.resume_count
                """,
                (self._date, ip_key, self._per_ip[ip_key]),
            )

    def _snapshot(self, ip_address: str) -> QuotaSnapshot:
        used_by_ip = self._per_ip.get(self._ip_key(ip_address), 0)
        return QuotaSnapshot(
            date=self._date,
            per_ip_limit=self.settings.per_ip_daily_resume_limit,
            per_ip_used=used_by_ip,
            per_ip_remaining=max(
                0, self.settings.per_ip_daily_resume_limit - used_by_ip
            ),
            global_limit=self.settings.global_daily_resume_limit,
            global_used=self._global_used,
            global_remaining=max(
                0, self.settings.global_daily_resume_limit - self._global_used
            ),
        )

    async def current(self, ip_address: str) -> QuotaSnapshot:
        async with self._lock:
            self._reset_if_needed()
            return self._snapshot(ip_address)

    async def reserve(self, ip_address: str, resume_count: int) -> QuotaSnapshot:
        async with self._lock:
            self._reset_if_needed()
            before = self._snapshot(ip_address)
            if resume_count > before.per_ip_remaining:
                raise QuotaExceeded(
                    f"当前 IP 今日最多还可评估 {before.per_ip_remaining} 份简历",
                    before,
                )
            if resume_count > before.global_remaining:
                raise QuotaExceeded(
                    f"本站今日最多还可评估 {before.global_remaining} 份简历",
                    before,
                )
            ip_key = self._ip_key(ip_address)
            self._per_ip[ip_key] = before.per_ip_used + resume_count
            self._global_used += resume_count
            self._persist_ip(ip_key)
            return self._snapshot(ip_address)
