import os
import sys

if sys.argv[1:] == ["get"]:
    request = dict(line.rstrip("\n").split("=", 1) for line in sys.stdin if "=" in line)
    token = os.environ.get("GITHUB_TOKEN")
    if token and request.get("protocol") == "https" and request.get("host") == "github.com":
        sys.stdout.write(f"username=x-access-token\npassword={token}\n\n")
