import hashlib
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch

import yaml

from test_laki import LAKI, load_script, render


class KrakenTests(unittest.TestCase):
    def test_native_mcp_has_full_services_with_confirmation_and_explicit_credentials(self):
        config = yaml.safe_load((LAKI / "config.yaml").read_text())
        kraken = config["mcp_servers"]["kraken"]
        self.assertEqual(kraken["command"], "/opt/data/tools/kraken-mcp")
        self.assertEqual(kraken["args"], ["-s", "market,account,trade,paper,workspace,futures,futures-paper,funding,earn,auth,subaccount"])
        self.assertEqual(kraken["trust"], "untrusted")
        self.assertEqual(kraken["elicitation"], {"enabled": True, "timeout": 300})
        self.assertEqual(kraken["env"], {key: "${" + key + "}" for key in (
            "KRAKEN_API_KEY", "KRAKEN_API_SECRET", "KRAKEN_FUTURES_API_KEY", "KRAKEN_FUTURES_API_SECRET",
        )})
        self.assertNotIn("--allow-dangerous", kraken["args"])
        self.assertNotIn("feedback", kraken["args"][1].split(","))

    def test_optional_secret_is_gateway_only_and_survives_profile_reload(self):
        resources = render(LAKI)
        deployment = next(resource for resource in resources if resource["kind"] == "Deployment")
        pod = deployment["spec"]["template"]["spec"]
        for container in pod["containers"] + pod["initContainers"]:
            references = [entry for entry in container.get("envFrom", [])
                          if entry.get("secretRef", {}).get("name") == "hermes-laki-kraken"]
            self.assertEqual(references, [{"secretRef": {"name": "hermes-laki-kraken", "optional": True}}]
                             if container["name"] == "gateway" else [])
        managed = next(volume for volume in pod["volumes"] if volume["name"] == "managed-env")
        self.assertIn({"secret": {"name": "hermes-laki-kraken", "optional": True}}, managed["projected"]["sources"])
        self.assertNotIn("kraken", yaml.safe_load((LAKI.parent / "samwise/config.yaml").read_text())["mcp_servers"])

    def make_archive(self, module, binary, symlink=False):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w:gz") as archive:
            member = tarfile.TarInfo(module.KRAKEN_MEMBER)
            if symlink:
                member.type = tarfile.SYMTYPE
                member.linkname = "/etc/passwd"
                archive.addfile(member)
            else:
                member.size = len(binary)
                archive.addfile(member, io.BytesIO(binary))
        return stream.getvalue()

    def test_verified_archive_and_binary_are_cached_and_tampering_is_repaired(self):
        module = load_script("operator-init")
        binary = b"verified MCP binary"
        archive = self.make_archive(module, binary)
        fetch = Mock(side_effect=lambda *args, **kwargs: io.BytesIO(archive))
        with tempfile.TemporaryDirectory() as directory, patch.multiple(
            module, KRAKEN_ARCHIVE_SHA256=hashlib.sha256(archive).hexdigest(),
            KRAKEN_BINARY_SHA256=hashlib.sha256(binary).hexdigest(),
        ):
            path = Path(directory)
            module.install_kraken(path, fetch)
            target = path / "kraken-mcp"
            self.assertEqual(target.read_bytes(), binary)
            self.assertEqual(target.stat().st_mode & 0o777, 0o755)
            module.install_kraken(path, fetch)
            self.assertEqual(fetch.call_count, 1)
            target.write_bytes(b"tampered")
            module.install_kraken(path, fetch)
            self.assertEqual(target.read_bytes(), binary)
            self.assertEqual(fetch.call_count, 2)

    def test_bad_archive_bad_binary_and_symlink_do_not_replace_existing_binary(self):
        module = load_script("operator-init")
        binary = b"verified MCP binary"
        archive = self.make_archive(module, binary)
        symlink = self.make_archive(module, binary, symlink=True)
        for data, archive_digest, binary_digest, message in (
            (archive, "0" * 64, hashlib.sha256(binary).hexdigest(), "Kraken archive"),
            (archive, hashlib.sha256(archive).hexdigest(), "0" * 64, "kraken-mcp"),
            (symlink, hashlib.sha256(symlink).hexdigest(), hashlib.sha256(binary).hexdigest(), "regular file"),
        ):
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory, patch.multiple(
                module, KRAKEN_ARCHIVE_SHA256=archive_digest, KRAKEN_BINARY_SHA256=binary_digest,
            ):
                path = Path(directory)
                target = path / "kraken-mcp"
                target.write_bytes(b"previous binary")
                fetch = Mock(return_value=io.BytesIO(data))
                with self.assertRaisesRegex(RuntimeError, message):
                    module.install_kraken(path, fetch)
                self.assertEqual(target.read_bytes(), b"previous binary")



if __name__ == "__main__":
    unittest.main()
