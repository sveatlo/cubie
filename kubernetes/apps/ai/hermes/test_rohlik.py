from pathlib import Path
import unittest

import yaml


class RohlikTests(unittest.TestCase):
    def test_oauth_connection_and_telegram_toolset(self):
        config = yaml.safe_load((Path(__file__).parent / "instances/samwise/config.yaml").read_text())
        self.assertEqual(config["mcp_servers"]["rohlik-mcp"], {
            "url": "https://mcp.rohlik.cz/mcp",
            "auth": "oauth",
        })
        self.assertIn("mcp-rohlik-mcp", config["platform_toolsets"]["telegram"])


if __name__ == "__main__":
    unittest.main()
