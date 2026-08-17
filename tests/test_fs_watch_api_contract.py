import unittest

from modal_workspace_mcp.fs_watch_api import router


class FileWatchApiContractTest(unittest.TestCase):
    def test_operation_ids(self):
        operation_ids = {
            route.operation_id
            for route in router.routes
            if getattr(route, "operation_id", None)
        }
        expected = {
            "startWorkspaceFileWatch",
            "listWorkspaceFileWatches",
            "getWorkspaceFileWatchStatus",
            "getWorkspaceFileWatchEvents",
            "cancelWorkspaceFileWatch",
        }
        self.assertTrue(expected.issubset(operation_ids))


if __name__ == "__main__":
    unittest.main()
