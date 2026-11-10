"""
AWS integration (EC2, S3, CloudWatch) - optional.

boto3 is imported LAZILY, only when AWS_ENABLED=true. If you never use AWS,
boto3 does not need to be installed and costs no RAM.

Credentials come from the standard AWS chain (never from our code):
  1. environment variables AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
  2. ~/.aws/credentials (profile chosen by AWS_PROFILE; created by aws_setup.py)
  3. the IAM role attached to the EC2 instance (created by terraform/)
Use a read-only IAM policy (see terraform/iam.tf).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from ..errors import IntegrationError, status_payload
from ..utils.cache import ttl_cache

HINT = ("pip install -r requirements-aws.txt, then run 'python aws_setup.py' with the IAM user's "
        "access-key CSV in Downloads (sets AWS_ENABLED, AWS_REGION, AWS_PROFILE in backend/.env).")


class AWSService:
    name = "aws"
    label = "AWS"

    def __init__(self, enabled: bool, region: str) -> None:
        self.enabled = enabled
        self.region = region
        self._session = None

    def _boto(self):
        if not self.enabled:
            raise IntegrationError("AWS integration is disabled", 503, HINT)
        if self._session is None:
            try:
                import boto3  # noqa: WPS433 (lazy import on purpose)
            except ImportError as exc:
                raise IntegrationError("boto3 is not installed", 503, HINT) from exc
            self._session = boto3.session.Session(region_name=self.region)
        return self._session

    async def _call(self, fn):
        try:
            return await asyncio.to_thread(fn)
        except IntegrationError:
            raise
        except Exception as exc:  # botocore raises many error types
            raise IntegrationError(f"AWS: {exc}", 502, HINT) from exc

    async def status(self) -> dict[str, Any]:
        if not self.enabled:
            return status_payload(self.name, self.label, False, False, "Disabled", HINT)
        try:
            ident = await self._call(lambda: self._boto().client("sts").get_caller_identity())
            return status_payload(self.name, self.label, True, True,
                                  f"Account {ident['Account']} ({self.region})")
        except IntegrationError as exc:
            return status_payload(self.name, self.label, True, False, exc.message, HINT)

    @ttl_cache(ttl=60)
    async def summary(self) -> dict[str, Any]:
        def collect() -> dict[str, Any]:
            session = self._boto()
            ec2 = session.client("ec2")
            cw = session.client("cloudwatch")
            s3 = session.client("s3")
            instances = []
            for reservation in ec2.describe_instances().get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    name = next((t["Value"] for t in inst.get("Tags", []) if t["Key"] == "Name"), "")
                    instances.append({
                        "id": inst["InstanceId"],
                        "name": name,
                        "type": inst.get("InstanceType"),
                        "state": inst.get("State", {}).get("Name"),
                        "public_ip": inst.get("PublicIpAddress"),
                        "az": inst.get("Placement", {}).get("AvailabilityZone"),
                        "launched": inst.get("LaunchTime").isoformat() if inst.get("LaunchTime") else None,
                        "cpu_percent": None,
                    })
            end = datetime.now(timezone.utc)
            for inst in instances:
                if inst["state"] != "running":
                    continue
                stats = cw.get_metric_statistics(
                    Namespace="AWS/EC2", MetricName="CPUUtilization",
                    Dimensions=[{"Name": "InstanceId", "Value": inst["id"]}],
                    StartTime=end - timedelta(minutes=30), EndTime=end,
                    Period=300, Statistics=["Average"])
                points = sorted(stats.get("Datapoints", []), key=lambda p: p["Timestamp"])
                if points:
                    inst["cpu_percent"] = round(points[-1]["Average"], 1)
            buckets = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
            alarms = cw.describe_alarms(StateValue="ALARM").get("MetricAlarms", [])
            return {
                "region": self.region,
                "instances": instances,
                "buckets": buckets,
                "alarms": [{"name": a["AlarmName"], "reason": a.get("StateReason")} for a in alarms],
            }

        return await self._call(collect)
