import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from .config import Settings
from .dify import DifyClient
from .models import (
    BatchCreate,
    BatchItem,
    BatchStatus,
    BatchTask,
    ItemStatus,
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class TaskStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.tasks: dict[str, BatchTask] = {}
        self._runners: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        request: BatchCreate,
        client: DifyClient,
        owner_id: str,
    ) -> BatchTask:
        task_id = str(uuid4())
        timestamp = now_iso()
        task = BatchTask(
            task_id=task_id,
            owner_id=owner_id,
            job_description=request.job_description,
            custom_instructions=request.custom_instructions,
            items=[
                BatchItem(
                    item_id=str(uuid4()),
                    client_id=item.client_id,
                    file_name=item.file_name,
                )
                for item in request.candidates
            ],
            created_at=timestamp,
            updated_at=timestamp,
        )
        async with self._lock:
            self.tasks[task_id] = task
        self._runners[task_id] = asyncio.create_task(self._run(task, request, client))
        return task

    def get(self, task_id: str) -> BatchTask | None:
        return self.tasks.get(task_id)

    def get_owned(self, task_id: str, owner_id: str) -> BatchTask | None:
        task = self.tasks.get(task_id)
        return task if task and task.owner_id == owner_id else None

    async def _run(self, task: BatchTask, request: BatchCreate, client: DifyClient) -> None:
        task.status = BatchStatus.running
        task.updated_at = now_iso()
        semaphore = asyncio.Semaphore(max(1, self.settings.dify_concurrency))
        inputs = {item.client_id: item for item in request.candidates}

        async def run_item(batch_item: BatchItem) -> None:
            async with semaphore:
                if task.cancelled:
                    batch_item.status = ItemStatus.cancelled
                    return
                batch_item.status = ItemStatus.running
                batch_item.attempts += 1
                task.updated_at = now_iso()
                source = inputs[batch_item.client_id]
                try:
                    batch_item.result = await client.evaluate(
                        source.resume_text,
                        request.job_description,
                        request.custom_instructions,
                        f"resume-web-{task.task_id}",
                    )
                    batch_item.status = ItemStatus.success
                    batch_item.error = None
                except Exception as exc:
                    batch_item.status = ItemStatus.failed
                    batch_item.error = str(exc)[:500]
                finally:
                    task.updated_at = now_iso()

        await asyncio.gather(*(run_item(item) for item in task.items))
        task.status = BatchStatus.cancelled if task.cancelled else BatchStatus.completed
        task.updated_at = now_iso()

    def cancel(self, task_id: str) -> BatchTask:
        task = self.tasks[task_id]
        task.cancelled = True
        for item in task.items:
            if item.status == ItemStatus.pending:
                item.status = ItemStatus.cancelled
        task.updated_at = now_iso()
        return task

    async def delete(self, task_id: str) -> None:
        async with self._lock:
            task = self.tasks.pop(task_id, None)
            runner = self._runners.pop(task_id, None)
        if task:
            task.cancelled = True
        if runner and not runner.done():
            runner.cancel()
            with suppress(asyncio.CancelledError):
                await runner

    def cleanup(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(seconds=self.settings.task_ttl_seconds)
        expired = [
            key
            for key, task in self.tasks.items()
            if datetime.fromisoformat(task.updated_at) < cutoff
        ]
        for key in expired:
            self.tasks.pop(key, None)
            runner = self._runners.pop(key, None)
            if runner and not runner.done():
                runner.cancel()
