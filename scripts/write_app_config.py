#!/usr/bin/env python3
"""Create the API token (if needed) and write app/config.local.json for building the APK.

  python scripts/write_app_config.py            # keep the existing token
  python scripts/write_app_config.py --rotate   # new token: rebuild and reinstall the APK

The token is stored as an SSM SecureString at /<stack>/api-token. The API URL comes from the
stack outputs. Neither is ever printed; app/config.local.json is gitignored.
"""

import argparse
import json
import os
import secrets
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "app" / "config.example.json"
LOCAL = ROOT / "app" / "config.local.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stack", default="release-tracker")
    parser.add_argument("--rotate", action="store_true", help="replace the token with a new one")
    args = parser.parse_args()

    session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE", "release-tracker"))
    ssm = session.client("ssm")
    outputs = session.client("cloudformation").describe_stacks(StackName=args.stack)["Stacks"][0]["Outputs"]
    api_url = next(o["OutputValue"] for o in outputs if o["OutputKey"] == "ApiUrl")
    param = f"/{args.stack}/api-token"

    token = None
    if not args.rotate:
        try:
            token = ssm.get_parameter(Name=param, WithDecryption=True)["Parameter"]["Value"]
        except ssm.exceptions.ParameterNotFound:
            pass
    created = token is None
    if created:
        token = secrets.token_urlsafe(32)
        ssm.put_parameter(Name=param, Value=token, Type="SecureString", Overwrite=True,
                          Description="Bearer token for the release-tracker API")

    config = json.loads(EXAMPLE.read_text())
    if LOCAL.exists():
        config.update(json.loads(LOCAL.read_text()))  # keep local edits such as POLL_TIMES_UTC
    config.update({"API_BASE_URL": api_url, "API_TOKEN": token})
    LOCAL.touch(mode=0o600, exist_ok=True)
    LOCAL.write_text(json.dumps(config, indent=2) + "\n")
    LOCAL.chmod(0o600)

    print(f"{'Created a new' if created else 'Reused the existing'} token in SSM {param}")
    print(f"Wrote API URL and token to {LOCAL.relative_to(ROOT)} (gitignored)")
    if created and args.rotate:
        print("The API accepts the new token within 5 minutes; rebuild and reinstall the APK.")


if __name__ == "__main__":
    main()
