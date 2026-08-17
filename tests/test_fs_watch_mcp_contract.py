import unittest

from fastmcp import FastMCP

from modal_workspace_mcp.fs_watch_mcp import register_fs_watch_tools


class FileWatchMcpContractTest(unittest.TestCase):
    def test_tools_register_with_fastmcp(self):
        mcp = FastMCP("fs-watch-contract")
        register_fs_watch_tools(mcp)
        self.assertTrue(callable(mcp.http_app))


if __name__ == "__main__":
    unittest.main()
