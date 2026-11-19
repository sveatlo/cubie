import os
import sys


def credential(request, token):
    if token and request.get("protocol") == "https" and request.get("host") == "github.com":
        return f"username=x-access-token\npassword={token}\n\n"
    return ""


if __name__ == "__main__" and sys.argv[1:] == ["get"]:
    request = dict(line.rstrip("\n").split("=", 1) for line in sys.stdin if "=" in line)
    sys.stdout.write(credential(request, os.environ.get("GITHUB_TOKEN")))
