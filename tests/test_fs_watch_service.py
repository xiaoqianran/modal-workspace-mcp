import unittest
from unittest.mock import patch

from modal_workspace_mcp.fs_watch_service import (
    append_watch_event,
    new_watch_state,
    normalize_event_types,
    slice_watch_events,
    validate_watch_id,
    validate_watch_path,
)


class FileWatchHelpersTest(unittest.TestCase):
    def make_state(self):
        return new_watch_state(
            watch_id="fw-" + "a" * 32,
            workspace_id="ws-" + "b" * 32,
            sandbox_id="sb-test",
            path="/workspace/repo",
            recursive=True,
            event_types=["create", "modify", "remove"],
            timeout_seconds=60,
        )

    def test_watch_id_validation(self):
        self.assertEqual(validate_watch_id("fw-" + "1" * 32), "fw-" + "1" * 32)
        for bad in ("fw-x", "ws-" + "1" * 32, "fw-" + "G" * 32):
            with self.assertRaises(ValueError):
                validate_watch_id(bad)

    def test_watch_path_is_workspace_scoped(self):
        self.assertEqual(validate_watch_path("/workspace"), "/workspace")
        self.assertEqual(validate_watch_path("/workspace/repo/src"), "/workspace/repo/src")
        for bad in ("/", "/tmp", "/workspace/../etc", "relative/path"):
            with self.assertRaises(ValueError):
                validate_watch_path(bad)

    def test_event_type_normalization(self):
        self.assertEqual(normalize_event_types(None), ["create", "modify", "remove"])
        self.assertEqual(
            normalize_event_types(["Modify", "create", "modify"]),
            ["modify", "create"],
        )
        with self.assertRaises(ValueError):
            normalize_event_types(["chmod"])
        with self.assertRaises(ValueError):
            normalize_event_types([])

    def test_cursor_is_incremental(self):
        state = self.make_state()
        append_watch_event(state, event_type="create", paths=["/workspace/repo/a.py"])
        append_watch_event(state, event_type="modify", paths=["/workspace/repo/a.py"])
        first = slice_watch_events(state, cursor=0, max_events=1)
        self.assertEqual([event["seq"] for event in first["events"]], [0])
        self.assertEqual(first["next_cursor"], 1)
        self.assertTrue(first["has_more"])
        second = slice_watch_events(state, cursor=first["next_cursor"], max_events=10)
        self.assertEqual([event["seq"] for event in second["events"]], [1])
        self.assertEqual(second["next_cursor"], 2)
        self.assertFalse(second["has_more"])

    def test_ring_buffer_reports_expired_cursor(self):
        state = self.make_state()
        with patch("modal_workspace_mcp.fs_watch_service.MAX_WATCH_EVENTS", 3):
            for index in range(5):
                append_watch_event(
                    state,
                    event_type="modify",
                    paths=[f"/workspace/repo/{index}.py"],
                )
        self.assertEqual(state["base_cursor"], 2)
        self.assertEqual(state["next_cursor"], 5)
        self.assertEqual(state["dropped_events"], 2)
        batch = slice_watch_events(state, cursor=0, max_events=10)
        self.assertTrue(batch["cursor_expired"])
        self.assertEqual([event["seq"] for event in batch["events"]], [2, 3, 4])
        self.assertEqual(batch["next_cursor"], 5)

    def test_future_cursor_is_rejected(self):
        state = self.make_state()
        with self.assertRaises(ValueError):
            slice_watch_events(state, cursor=1, max_events=10)


if __name__ == "__main__":
    unittest.main()
