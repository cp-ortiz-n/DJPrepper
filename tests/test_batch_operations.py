from __future__ import annotations

import threading
import time
import unittest

from audioextender.infrastructure.batch_operations import BatchContext, BatchOperationRegistry


def wait_for_terminal(registry: BatchOperationRegistry, batch_id: str) -> dict:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        state = registry.status(batch_id)
        if state["status"] in {"complete", "failed", "canceled"}:
            return state
        time.sleep(0.005)
    raise AssertionError("batch did not finish")


class BatchOperationRegistryTests(unittest.TestCase):
    def test_batch_publishes_consistent_progress_result_and_error_model(self) -> None:
        registry = BatchOperationRegistry()

        def worker(context: BatchContext, items: list[dict]) -> dict:
            for index, item in enumerate(items, 1):
                context.progress(
                    processed=index,
                    counters={"updated": index - 1, "failed": 1, "succeeded": index - 1},
                    error={"id": item["id"], "error": "bad metadata"} if item["id"] == 2 else None,
                )
            return {"updated": 1, "stage": "Metadata complete"}

        started = registry.start("metadata", [{"id": 1}, {"id": 2}], worker, stage="Starting")
        result = wait_for_terminal(registry, started["batch_id"])

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["progress"], 100)
        self.assertEqual(result["processed"], result["total"])
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["errors"], [{"id": 2, "error": "bad metadata"}])
        self.assertEqual(result["result"], {"updated": 1})
        self.assertTrue(result["retryable"])
        self.assertEqual(result["stage"], "Metadata complete")


    def test_batch_cancel_is_cooperative_and_retry_keeps_the_original_link(self) -> None:
        registry = BatchOperationRegistry()
        reached_first = threading.Event()
        continue_work = threading.Event()

        def worker(context: BatchContext, items: list[int]) -> dict:
            for index, _item in enumerate(items, 1):
                context.check_canceled()
                context.progress(processed=index)
                reached_first.set()
                continue_work.wait(timeout=1)
            return {}

        started = registry.start("genre", [1, 2], worker, stage="Moving")
        self.assertTrue(reached_first.wait(timeout=1))
        canceling = registry.cancel(started["batch_id"])
        self.assertEqual(canceling["status"], "canceling")
        continue_work.set()
        canceled = wait_for_terminal(registry, started["batch_id"])
        self.assertEqual(canceled["status"], "canceled")
        self.assertTrue(canceled["retryable"])

        retried = registry.retry(started["batch_id"])
        continue_work.set()
        complete = wait_for_terminal(registry, retried["batch_id"])
        self.assertEqual(complete["status"], "complete")
        self.assertEqual(complete["retry_of"], started["batch_id"])


    def test_unknown_batch_operations_are_rejected(self) -> None:
        registry = BatchOperationRegistry()
        with self.assertRaisesRegex(KeyError, "not found"):
            registry.status("missing")
        with self.assertRaisesRegex(KeyError, "not found"):
            registry.cancel("missing")


if __name__ == "__main__":
    unittest.main()
