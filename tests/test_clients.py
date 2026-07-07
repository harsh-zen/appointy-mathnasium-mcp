import unittest

from appointy_mathnasium_mcp import clients
from appointy_mathnasium_mcp.errors import AppointyApiError


class AppointyClientConfigTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_surfaces_missing_config_without_name_error(self):
        client = clients.AppointyClient()
        original_base_url = clients.APPOINTY_API_BASE_URL
        original_api_key = clients.APPOINTY_API_KEY
        original_group_id = clients.MATHNASIUM_GROUP_ID
        try:
            clients.APPOINTY_API_BASE_URL = ""
            clients.APPOINTY_API_KEY = None
            clients.MATHNASIUM_GROUP_ID = None
            with self.assertRaises(AppointyApiError) as raised:
                await client._request("GET", "/health")
            self.assertIn("Missing required environment variables", str(raised.exception))
        finally:
            clients.APPOINTY_API_BASE_URL = original_base_url
            clients.APPOINTY_API_KEY = original_api_key
            clients.MATHNASIUM_GROUP_ID = original_group_id


if __name__ == "__main__":
    unittest.main()
