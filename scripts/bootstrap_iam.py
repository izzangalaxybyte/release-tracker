#!/usr/bin/env python3
"""One-time (re-runnable) IAM setup, run with an admin profile:

  python scripts/bootstrap_iam.py --admin-profile default --create-access-key

Creates or updates:
  * <stack>-boundary   managed policy: the most any function role in the stack may ever do
  * <stack>-deployer   managed policy: what `sam deploy` and the scripts need, scoped to this stack
  * <stack>-deployer   IAM user with that policy attached
and with --create-access-key writes an access key for that user into the local AWS CLI
profile named by --profile-name (never printed).

The deployer can only create IAM roles named <stack>-* that carry the boundary policy, so
it cannot grant itself (or a Lambda) more than the boundary allows.
"""

import argparse
import configparser
import json
import os
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

IAM_DIR = Path(__file__).resolve().parent.parent / "iam"


def render(name: str, account_id: str, region: str, stack: str) -> str:
    text = (IAM_DIR / name).read_text()
    for key, value in {"ACCOUNT_ID": account_id, "REGION": region, "STACK": stack}.items():
        text = text.replace("{{" + key + "}}", value)
    return json.dumps(json.loads(text), separators=(",", ":"))


def upsert_policy(iam, account_id: str, name: str, document: str, description: str) -> str:
    arn = f"arn:aws:iam::{account_id}:policy/{name}"
    try:
        iam.get_policy(PolicyArn=arn)
    except iam.exceptions.NoSuchEntityException:
        iam.create_policy(PolicyName=name, PolicyDocument=document, Description=description)
        print(f"created policy {name}")
        return arn

    versions = iam.list_policy_versions(PolicyArn=arn)["Versions"]
    current = next(v for v in versions if v["IsDefaultVersion"])
    current_doc = iam.get_policy_version(PolicyArn=arn, VersionId=current["VersionId"])["PolicyVersion"]["Document"]
    if json.dumps(current_doc, sort_keys=True) == json.dumps(json.loads(document), sort_keys=True):
        print(f"policy {name} up to date")
        return arn
    if len(versions) >= 5:  # IAM keeps at most 5 versions
        oldest = min((v for v in versions if not v["IsDefaultVersion"]), key=lambda v: v["CreateDate"])
        iam.delete_policy_version(PolicyArn=arn, VersionId=oldest["VersionId"])
    iam.create_policy_version(PolicyArn=arn, PolicyDocument=document, SetAsDefault=True)
    print(f"updated policy {name}")
    return arn


def write_profile(profile: str, key_id: str, secret: str, region: str) -> None:
    """Add a profile to the AWS CLI credentials/config files (same files `aws configure` uses)."""
    aws_dir = Path.home() / ".aws"
    credentials = Path(os.environ.get("AWS_SHARED_CREDENTIALS_FILE", aws_dir / "credentials"))
    config = Path(os.environ.get("AWS_CONFIG_FILE", aws_dir / "config"))
    for path, section, values in (
        (credentials, profile, {"aws_access_key_id": key_id, "aws_secret_access_key": secret}),
        (config, f"profile {profile}", {"region": region}),
    ):
        parser = configparser.RawConfigParser()
        parser.read(path)
        path.parent.mkdir(mode=0o700, exist_ok=True)
        if parser.has_section(section):
            # Rewriting would drop comments in the user's file; make them choose.
            raise SystemExit(f"[{section}] already exists in {path}; remove it and re-run")
        block = f"\n[{section}]\n" + "".join(f"{k} = {v}\n" for k, v in values.items())
        with open(path, "a") as f:  # append only: other profiles are left untouched
            f.write(block)
        path.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--admin-profile", default=None, help="AWS profile with IAM admin rights")
    parser.add_argument("--stack", default="release-tracker")
    parser.add_argument("--region", default=None, help="defaults to the admin profile's region")
    parser.add_argument("--profile-name", default="release-tracker", help="local AWS CLI profile to write")
    parser.add_argument("--create-access-key", action="store_true")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.admin_profile)
    region = args.region or session.region_name
    if not region:
        parser.error("no region: pass --region or set one on the admin profile")
    account_id = session.client("sts").get_caller_identity()["Account"]
    iam = session.client("iam")
    user = f"{args.stack}-deployer"

    upsert_policy(iam, account_id, f"{args.stack}-boundary", render("boundary-policy.json", account_id, region, args.stack),
                  f"Permissions boundary for {args.stack} Lambda roles")
    deployer_arn = upsert_policy(iam, account_id, f"{args.stack}-deployer",
                                 render("deployer-policy.json", account_id, region, args.stack),
                                 f"Deploy and operate the {args.stack} SAM stack")

    try:
        iam.create_user(UserName=user, Tags=[{"Key": "project", "Value": args.stack}])
        print(f"created user {user}")
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"user {user} exists")
    iam.attach_user_policy(UserName=user, PolicyArn=deployer_arn)

    if args.create_access_key:
        if iam.list_access_keys(UserName=user)["AccessKeyMetadata"]:
            print(f"{user} already has an access key; not creating another (delete it in IAM to rotate)")
        else:
            key = iam.create_access_key(UserName=user)["AccessKey"]
            try:
                write_profile(args.profile_name, key["AccessKeyId"], key["SecretAccessKey"], region)
            except Exception:
                iam.delete_access_key(UserName=user, AccessKeyId=key["AccessKeyId"])  # secret would be lost
                raise
            print(f"wrote access key for {user} to AWS CLI profile '{args.profile_name}' ({region})")


if __name__ == "__main__":
    try:
        main()
    except ClientError as e:
        raise SystemExit(f"AWS error: {e}")
