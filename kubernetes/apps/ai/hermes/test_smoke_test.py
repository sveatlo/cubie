import os
import ssl
import unittest
from unittest.mock import patch

import smoke_test


class ProxmoxTlsTests(unittest.TestCase):
    def test_verification_enabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            context = smoke_test.proxmox_tls_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def test_opt_out_does_not_change_global_tls_defaults(self):
        with patch.dict(os.environ, {"PROXMOX_VERIFY_TLS": "false"}, clear=True):
            context = smoke_test.proxmox_tls_context()
        self.assertFalse(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_NONE)
        default = ssl.create_default_context()
        self.assertTrue(default.check_hostname)
        self.assertEqual(default.verify_mode, ssl.CERT_REQUIRED)

    def test_invalid_verification_flag_fails_closed(self):
        with patch.dict(os.environ, {"PROXMOX_VERIFY_TLS": "nope"}, clear=True):
            with self.assertRaises(ValueError):
                smoke_test.proxmox_tls_context()


if __name__ == "__main__":
    unittest.main()
