# OCI A1.Flex Auto Grabber

GitHub Actions cron으로 OCI Always Free A1.Flex 인스턴스를 자동으로 잡습니다.
5분마다 자동 실행. 성공 시 Discord 알림 + GitHub Issue 자동 생성.

## 설정

Settings → Secrets and variables → Actions에서 아래 Secrets 등록:

| Secret | 설명 |
|--------|------|
| `OCI_USER_OCID` | OCI 사용자 OCID |
| `OCI_TENANCY_OCID` | OCI Tenancy OCID |
| `OCI_FINGERPRINT` | API Key fingerprint |
| `OCI_REGION` | 리전 (예: us-phoenix-1) |
| `OCI_PRIVATE_KEY` | API Private Key (.pem 전체 내용) |
| `OCI_COMPARTMENT_ID` | Compartment OCID |
| `OCI_SUBNET_ID` | Subnet OCID |
| `OCI_IMAGE_ID` | Ubuntu 22.04 aarch64 이미지 OCID (비워두면 자동 탐지) |
| `OCI_SSH_PUBLIC_KEY` | SSH 공개키 내용 |
| `DISCORD_WEBHOOK_URL` | Discord 웹훅 URL |

## 성공 후

워크플로우 즉시 비활성화: Settings → Actions → Disable workflow
