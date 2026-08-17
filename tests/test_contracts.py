import inspect
import unittest

import modal
from fastmcp import FastMCP

from modal_workspace_mcp.server import make_mcp_server


class ModalContractTest(unittest.TestCase):
    def test_sandbox_create_contract(self):
        params = inspect.signature(modal.Sandbox.create).parameters
        for name in (
            "app",
            "image",
            "cpu",
            "memory",
            "block_network",
            "outbound_cidr_allowlist",
            "outbound_domain_allowlist",
            "inbound_cidr_allowlist",
            "volumes",
        ):
            self.assertIn(name, params)

    def test_snapshot_contract(self):
        params = inspect.signature(modal.Sandbox.snapshot_filesystem).parameters
        self.assertIn("ttl", params)
        self.assertIn("timeout", params)

    def test_image_contract(self):
        self.assertTrue(callable(modal.Image.from_name))
        self.assertTrue(callable(modal.Image.from_id))
        self.assertTrue(callable(modal.Image.publish))

    def test_function_call_contract(self):
        self.assertTrue(callable(modal.FunctionCall.from_id))
        self.assertIn("timeout", inspect.signature(modal.FunctionCall.get).parameters)
        self.assertIn("terminate_containers", inspect.signature(modal.FunctionCall.cancel).parameters)

    def test_fastmcp_contract(self):
        server = make_mcp_server()
        self.assertIsInstance(server, FastMCP)
        self.assertTrue(callable(server.http_app))


if __name__ == "__main__":
    unittest.main()
