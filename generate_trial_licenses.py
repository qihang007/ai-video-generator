# -*- coding: utf-8 -*-
"""生成试用卡卡密"""
import hashlib
import uuid
import requests
from datetime import datetime, timezone

_SUPABASE_URL = "https://lhbzjbzbzyoippyoasmd.supabase.co"
_SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxoYnpqYnpienlvaXBweW9hc21kIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ2ODYwMDUsImV4cCI6MjA5MDI2MjAwNX0._QwBOpJ_M_s_pBevOFNqZ3seKyXnW8ruza8Rv6_O7cY"

OUTPUT_FILE = "trial_licenses_generated.txt"


def generate_code() -> str:
    suffix = hashlib.sha1(uuid.uuid4().bytes).hexdigest()[:8].upper()
    return f"TRIAL{suffix}"


def get_headers():
    return {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def batch_insert(codes: list) -> tuple:
    payload = [
        {
            "code": code,
            "reward_days": 0,
            "is_used": False,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        for code in codes
    ]
    try:
        resp = requests.post(
            f"{_SUPABASE_URL}/rest/v1/licenses",
            headers=get_headers(),
            json=payload,
            timeout=30
        )
        if resp.status_code in (200, 201):
            return codes, []
        return [], codes
    except:
        return [], codes


def retry_failed(failed_codes: list) -> list:
    success = []
    for code in failed_codes:
        try:
            resp = requests.post(
                f"{_SUPABASE_URL}/rest/v1/licenses",
                headers=get_headers(),
                json={
                    "code": code,
                    "reward_days": 0,
                    "is_used": False,
                    "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                },
                timeout=15
            )
            if resp.status_code in (200, 201):
                success.append(code)
        except:
            pass
    return success


if __name__ == "__main__":
    count = 30
    print(f"正在生成 {count} 个试用卡...")

    codes = [generate_code() for _ in range(count)]

    print(f"正在批量插入 {len(codes)} 个试用卡...")
    success, failed = batch_insert(codes)

    for code in success:
        print(f"  ✓ {code}")

    if failed:
        print(f"重试 {len(failed)} 个失败项...")
        retry_success = retry_failed(failed)
        for code in retry_success:
            print(f"  ✓ 重试成功: {code}")
        success.extend(retry_success)

    # 追加到文件
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        f.write("=" * 50 + "\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"类型: TRIAL (5天试用卡)\n")
        f.write("=" * 50 + "\n")
        for code in success:
            f.write(f"  {code}\n")
        f.write("\n")

    print(f"\n成功 {len(success)}/{count} 个")
    print(f"已追加到 {OUTPUT_FILE}")
