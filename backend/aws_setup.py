"""
Sets up the AWS profile for the dashboard straight from the access-key CSV.

Usage (inside backend, venv active, after: python -m pip install -r requirements-aws.txt):
    python aws_setup.py                      # finds *accessKeys*.csv in Downloads
    python aws_setup.py "C:\\path\\to\\file.csv"  # or give the CSV path

What it does (no copy-paste of secrets, nothing secret is printed):
  1. reads the access key ID + secret from the CSV that AWS gave you
  2. writes them to ~/.aws/credentials as profile [devops-ai]
  3. adds [profile devops-ai] region=ap-south-1 to ~/.aws/config (other sections kept)
  4. tests the key with STS, then tests the exact calls the dashboard makes
  5. writes AWS_ENABLED / AWS_REGION / AWS_PROFILE into backend/.env
"""

import configparser
import csv
import glob
import os
import sys

PROFILE = "devops-ai"
REGION = "ap-south-1"
HOME = os.path.expanduser("~")
AWS_DIR = os.path.join(HOME, ".aws")
CRED_PATH = os.path.join(AWS_DIR, "credentials")
CONFIG_PATH = os.path.join(AWS_DIR, "config")
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def find_csv() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    folders = [os.path.join(HOME, "Downloads"), os.path.join(HOME, "OneDrive", "Downloads"),
               os.path.join(HOME, "Desktop"), os.path.join(HOME, "OneDrive", "Desktop")]
    found = [f for d in folders for f in glob.glob(os.path.join(d, "*ccessKeys*.csv"))]
    if not found:
        sys.exit("ERROR: no *accessKeys*.csv found in Downloads or Desktop.\n"
                 "Run again with the path:  python aws_setup.py \"C:\\full\\path\\to\\file.csv\"")
    newest = max(found, key=os.path.getmtime)
    if len(found) > 1:
        print(f"Found {len(found)} key files, using the newest one.")
    return newest


def read_keys(path: str) -> tuple[str, str]:
    if not os.path.isfile(path):
        sys.exit(f"ERROR: file not found: {path}")
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            cells = [c.strip().strip('"').strip() for c in row]
            for i, cell in enumerate(cells[:-1]):
                if cell.startswith(("AKIA", "ASIA")) and len(cell) == 20:
                    secret = cells[i + 1]
                    if len(secret) != 40:
                        sys.exit(f"ERROR: the secret in the CSV has {len(secret)} characters, expected 40. "
                                 "The file is damaged; create a new access key in IAM.")
                    return cell, secret
    sys.exit("ERROR: this CSV does not contain an access key (expected 'AKIA...,<secret>' on line 2).")


def load_ini(path: str) -> configparser.RawConfigParser:
    ini = configparser.RawConfigParser()
    if os.path.exists(path):
        ini.read(path, encoding="utf-8-sig")
    return ini


def save_ini(ini: configparser.RawConfigParser, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        ini.write(f)


def update_env(values: dict[str, str]) -> None:
    """Replace (or add) KEY=value lines, removing duplicates of those keys."""
    lines = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, encoding="utf-8") as f:
            lines = f.read().splitlines()
    kept = [ln for ln in lines if ln.split("=", 1)[0].strip() not in values]
    kept += [f"{k}={v}" for k, v in values.items()]
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + "\n")


def main() -> None:
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        sys.exit("ERROR: boto3 missing. Run: python -m pip install -r requirements-aws.txt")

    csv_path = find_csv()
    key_id, secret = read_keys(csv_path)
    print(f"Using {csv_path}")
    print(f"Access key ID: {key_id}  (secret: 40 characters, not shown)")

    os.makedirs(AWS_DIR, exist_ok=True)

    cred = load_ini(CRED_PATH)
    if not cred.has_section(PROFILE):
        cred.add_section(PROFILE)
    cred.set(PROFILE, "aws_access_key_id", key_id)
    cred.set(PROFILE, "aws_secret_access_key", secret)
    save_ini(cred, CRED_PATH)

    conf = load_ini(CONFIG_PATH)
    for wrong in (PROFILE,):  # a bare [devops-ai] in config is ignored by AWS tools
        if conf.has_section(wrong):
            conf.remove_section(wrong)
    section = f"profile {PROFILE}"
    if not conf.has_section(section):
        conf.add_section(section)
    conf.set(section, "region", REGION)
    save_ini(conf, CONFIG_PATH)
    print(f"Wrote [{PROFILE}] to {CRED_PATH} and [{section}] to {CONFIG_PATH}")

    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    try:
        arn = session.client("sts").get_caller_identity()["Arn"]
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "InvalidClientTokenId":
            sys.exit(f"ERROR: AWS says key {key_id} does not exist or is deactivated. "
                     "Create a new access key in IAM, download its CSV, run this again.")
        if code == "SignatureDoesNotMatch":
            sys.exit("ERROR: the secret in this CSV does not belong to this key. "
                     "Create a new access key in IAM, download its CSV, run this again.")
        sys.exit(f"ERROR: {code}: {exc}")
    print(f"OK  STS identity: {arn}")

    checks = {
        "EC2 describe_instances": lambda: session.client("ec2").describe_instances(MaxResults=5),
        "S3 list_buckets": lambda: session.client("s3").list_buckets(),
        "CloudWatch describe_alarms": lambda: session.client("cloudwatch").describe_alarms(MaxRecords=5),
    }
    for name, call in checks.items():
        try:
            call()
            print(f"OK  {name}")
        except ClientError as exc:
            sys.exit(f"ERROR: {name} denied ({exc.response['Error']['Code']}). "
                     "Attach AdministratorAccess (or ReadOnlyAccess) to the IAM user.")

    update_env({"AWS_ENABLED": "true", "AWS_REGION": REGION, "AWS_PROFILE": PROFILE})
    print(f"OK  saved AWS_ENABLED=true, AWS_REGION={REGION}, AWS_PROFILE={PROFILE} to {ENV_PATH}")
    print("\nDone. Restart the backend (Ctrl+C, then: python -m uvicorn app.main:app --reload --port 8000)")
    print(f"Security: the key is now stored in {CRED_PATH}. Move the CSV out of Downloads"
          " to a safe place (or delete it).")


if __name__ == "__main__":
    main()