"""
OCI A1.Flex Grabber - GitHub Actions 버전
AD 한 바퀴 순회 후 종료. cron이 재호출 담당.
이미지 OCID가 없으면 최신 Ubuntu 22.04 aarch64 이미지를 자동 탐지.
"""

import os
import sys
import logging
from datetime import datetime
from typing import Optional

import oci
import requests

OCI_USER_OCID = os.getenv("OCI_USER_OCID")
OCI_TENANCY_OCID = os.getenv("OCI_TENANCY_OCID")
OCI_FINGERPRINT = os.getenv("OCI_FINGERPRINT")
OCI_REGION = os.getenv("OCI_REGION", "us-phoenix-1")
OCI_PRIVATE_KEY = os.getenv("OCI_PRIVATE_KEY")

COMPARTMENT_ID = os.getenv("OCI_COMPARTMENT_ID")
SUBNET_ID = os.getenv("OCI_SUBNET_ID")
IMAGE_ID = os.getenv("OCI_IMAGE_ID", "")
SSH_PUBLIC_KEY = os.getenv("OCI_SSH_PUBLIC_KEY")
DISPLAY_NAME = os.getenv("OCI_DISPLAY_NAME", "a1-flex-server")

OCPUS = float(os.getenv("OCI_OCPUS", "2"))
MEMORY_GB = float(os.getenv("OCI_MEMORY_GB", "12"))
BOOT_VOLUME_GB = int(os.getenv("OCI_BOOT_VOLUME_GB", "50"))

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPOSITORY", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def build_oci_config() -> dict:
    if not OCI_PRIVATE_KEY:
        raise ValueError("OCI_PRIVATE_KEY 비어있음")
    key_path = "/tmp/oci_api_key.pem"
    with open(key_path, "w") as f:
        f.write(OCI_PRIVATE_KEY)
    os.chmod(key_path, 0o600)
    return {
        "user": OCI_USER_OCID,
        "tenancy": OCI_TENANCY_OCID,
        "fingerprint": OCI_FINGERPRINT,
        "region": OCI_REGION,
        "key_file": key_path,
    }


def get_latest_ubuntu_image(compute_client) -> str:
    """Ubuntu 22.04 aarch64 최신 이미지 OCID 자동 탐지."""
    log.info("OCI_IMAGE_ID 미설정 → Ubuntu 22.04 aarch64 최신 이미지 자동 탐지 중...")
    images = compute_client.list_images(
        compartment_id=COMPARTMENT_ID,
        operating_system="Canonical Ubuntu",
        operating_system_version="22.04",
        shape="VM.Standard.A1.Flex",
        sort_by="TIMECREATED",
        sort_order="DESC",
        limit=1,
    ).data
    if not images:
        raise RuntimeError("Ubuntu 22.04 aarch64 이미지를 찾을 수 없습니다.")
    image_id = images[0].id
    log.info(f"탐지된 이미지: {images[0].display_name}")
    log.info(f"이미지 OCID: {image_id}")
    return image_id


def notify_discord(message: str, success: bool = False):
    if not DISCORD_WEBHOOK:
        return
    try:
        emoji = "🎉" if success else "ℹ️"
        requests.post(
            DISCORD_WEBHOOK,
            json={"content": f"{emoji} **OCI A1 Grabber**\n{message}"},
            timeout=10,
        )
    except Exception as e:
        log.warning(f"Discord 알림 실패: {e}")


def notify_github_issue(title: str, body: str):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
        }
        requests.post(
            url,
            headers=headers,
            json={"title": title, "body": body, "labels": ["oci-grabber"]},
            timeout=10,
        )
    except Exception as e:
        log.warning(f"GitHub Issue 생성 실패: {e}")


def try_launch(compute_client, launch_details, ad: str) -> Optional[str]:
    launch_details.availability_domain = ad
    try:
        response = compute_client.launch_instance(launch_details)
        return response.data.id
    except oci.exceptions.ServiceError as e:
        msg = (e.message or "").lower()
        if "out of capacity" in msg or e.status == 500:
            log.info(f"  └─ {ad}: capacity 부족")
            return None
        if "limitexceeded" in (e.code or "").lower() or "limit" in msg:
            log.error(f"❌ Service limit 초과: {e.message}")
            notify_discord(f"한도 초과: {e.message}")
            notify_github_issue(
                "⚠️ OCI Grabber: Service Limit 초과",
                f"```\n{e.message}\n```\n\n기존 A1 인스턴스 확인 필요. 워크플로우 비활성화 권장.",
            )
            sys.exit(2)
        log.warning(f"  └─ {ad}: {e.code} - {e.message}")
        return None
    except Exception as e:
        log.error(f"  └─ {ad}: {type(e).__name__}: {e}")
        return None


def main():
    required = {
        "OCI_USER_OCID": OCI_USER_OCID,
        "OCI_TENANCY_OCID": OCI_TENANCY_OCID,
        "OCI_FINGERPRINT": OCI_FINGERPRINT,
        "OCI_PRIVATE_KEY": OCI_PRIVATE_KEY,
        "OCI_COMPARTMENT_ID": COMPARTMENT_ID,
        "OCI_SUBNET_ID": SUBNET_ID,
        "OCI_SSH_PUBLIC_KEY": SSH_PUBLIC_KEY,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        log.error(f"필수 Secrets 누락: {missing}")
        sys.exit(1)

    config = build_oci_config()
    compute_client = oci.core.ComputeClient(config)
    identity_client = oci.identity.IdentityClient(config)

    image_id = IMAGE_ID if IMAGE_ID else get_latest_ubuntu_image(compute_client)

    ads = identity_client.list_availability_domains(COMPARTMENT_ID).data
    ad_names = [ad.name for ad in ads]

    log.info("=" * 60)
    log.info(f"OCI A1.Flex Grab | {OCPUS} OCPU / {MEMORY_GB} GB")
    log.info(f"리전: {OCI_REGION} | AD: {ad_names}")
    log.info("=" * 60)

    launch_details = oci.core.models.LaunchInstanceDetails(
        compartment_id=COMPARTMENT_ID,
        display_name=DISPLAY_NAME,
        shape="VM.Standard.A1.Flex",
        shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
            ocpus=OCPUS, memory_in_gbs=MEMORY_GB,
        ),
        source_details=oci.core.models.InstanceSourceViaImageDetails(
            source_type="image",
            image_id=image_id,
            boot_volume_size_in_gbs=BOOT_VOLUME_GB,
        ),
        create_vnic_details=oci.core.models.CreateVnicDetails(
            subnet_id=SUBNET_ID, assign_public_ip=True,
        ),
        metadata={"ssh_authorized_keys": SSH_PUBLIC_KEY},
    )

    for ad in ad_names:
        instance_id = try_launch(compute_client, launch_details, ad)
        if instance_id:
            msg = (
                f"인스턴스 생성 성공!\n"
                f"AD: `{ad}`\n"
                f"OCID: `{instance_id}`\n"
                f"스펙: {OCPUS} OCPU / {MEMORY_GB} GB\n"
                f"시각: {datetime.utcnow().isoformat()}Z"
            )
            log.info("🎉 " + msg.replace("\n", " | "))
            notify_discord(msg, success=True)
            notify_github_issue(
                "🎉 OCI A1.Flex 생성 성공",
                f"{msg}\n\n**워크플로우 즉시 비활성화 필요.**\nSettings → Actions → Disable workflow",
            )
            github_output = os.getenv("GITHUB_OUTPUT")
            if github_output:
                with open(github_output, "a") as f:
                    f.write(f"instance_id={instance_id}\n")
                    f.write(f"availability_domain={ad}\n")
            sys.exit(0)

    log.info("이번 사이클 capacity 부족. 다음 cron 대기.")
    sys.exit(0)


if __name__ == "__main__":
    main()
