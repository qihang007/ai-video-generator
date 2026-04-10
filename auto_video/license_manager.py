# -*- coding: utf-8 -*-
"""
License Manager - 卡密授权模块
"""
import hashlib
import uuid
import json
import time
import platform
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests

# ==================== Supabase 配置（硬编码，不写在配置文件）====================
_SUPABASE_URL = "https://lhbzjbzbzyoippyoasmd.supabase.co"
_SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxoYnpqYnpienlvaXBweW9hc21kIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ2ODYwMDUsImV4cCI6MjA5MDI2MjAwNX0._QwBOpJ_M_s_pBevOFNqZ3seKyXnW8ruza8Rv6_O7cY"

# ==================== 卡密类型常量 ====================
class LicenseType:
    TRIAL     = "trial"      # 试用码，5天，只能激活一次
    MONTH     = "month"      # 月卡，30天
    QUARTER   = "quarter"    # 季卡，90天
    YEAR      = "year"       # 年卡，365天
    PERMANENT = "permanent"  # 永久卡

LICENSE_DAYS = {
    LicenseType.TRIAL:     5,
    LicenseType.MONTH:     30,
    LicenseType.QUARTER:   90,
    LicenseType.YEAR:      365,
    LicenseType.PERMANENT: -1,  # -1 表示永久
}

REWARD_DAYS = 5  # 每邀请一人奖励天数

LICENSE_STATE_FILE = Path(__file__).parent.parent / "license_state.json"


# ==================== 机器码 ====================
def get_machine_id() -> str:
    """获取本机唯一机器码（CPU/主板序列号 → MD5）"""
    raw = _get_raw_machine_id()
    return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()


def _get_raw_machine_id() -> str:
    """获取原始机器标识（跨平台）"""
    system = platform.system()

    if system == "Windows":
        try:
            # 主板序列号
            result = subprocess.run(
                ["wmic", "baseboard", "get", "SerialNumber"],
                capture_output=True, text=True, timeout=10
            )
            board_id = result.stdout.strip().split("\n")[-1].strip()
            if board_id and board_id not in ("", "SerialNumber"):
                return f"BOARD:{board_id}"
        except Exception:
            pass

        try:
            # CPU ID
            result = subprocess.run(
                ["wmic", "cpu", "get", "ProcessorId"],
                capture_output=True, text=True, timeout=10
            )
            cpu_id = result.stdout.strip().split("\n")[-1].strip()
            if cpu_id and cpu_id not in ("", "ProcessorId"):
                return f"CPU:{cpu_id}"
        except Exception:
            pass

        # 兜底：随机 UUID（首次生成后应持久化）
        return f"UUID:{uuid.getnode()}"

    elif system == "Darwin":
        result = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            if "IOPlatformSerialNumber" in line:
                parts = line.split('"')
                if len(parts) >= 4:
                    return f"SN:{parts[3]}"
        return f"UUID:{uuid.getnode()}"

    else:  # Linux
        for path in [
            "/sys/class/dmi/id/board_serial",
            "/sys/class/dmi/id/product_uuid",
            "/sys/class/dmi/id/chassis_serial",
        ]:
            try:
                sn = Path(path).read_text().strip()
                if sn:
                    return f"{path}:{sn}"
            except Exception:
                pass
        return f"UUID:{uuid.getnode()}"


# ==================== 本地授权状态 ====================
def load_state() -> dict:
    """从 license_state.json 加载本地授权状态"""
    if LICENSE_STATE_FILE.exists():
        try:
            with open(LICENSE_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"activated": False}


def save_state(state: dict):
    """保存授权状态到 license_state.json"""
    LICENSE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LICENSE_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ==================== Supabase 接口 ====================
def _get_db_expire_at(code: str) -> Optional[str]:
    """从数据库查询卡密的真实到期时间（3秒超时）"""
    if not _SUPABASE_URL or not _SUPABASE_KEY or not code:
        return None
    headers = _get_supabase_headers()
    url = f"{_SUPABASE_URL}/rest/v1/licenses?code=eq.{code.upper()}&select=expire_at,is_used"
    try:
        resp = requests.get(url, headers=headers, timeout=3)
        if resp.status_code == 200 and resp.json():
            row = resp.json()[0]
            if row.get("is_used"):
                return row.get("expire_at")
    except Exception:
        pass
    return None


def _get_supabase_headers() -> dict:
    """构造 Supabase 请求头"""
    return {
        "apikey":        _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


def _parse_license_type(code: str) -> Optional[str]:
    """根据卡密前缀识别类型（通用兼容，线下生成时统一前缀）"""
    code_upper = code.upper()
    if code_upper.startswith("TRIAL"):
        return LicenseType.TRIAL
    if code_upper.startswith("MONTH"):
        return LicenseType.MONTH
    if code_upper.startswith("QUARTER"):
        return LicenseType.QUARTER
    if code_upper.startswith("YEAR"):
        return LicenseType.YEAR
    if code_upper.startswith("PERM"):
        return LicenseType.PERMANENT
    return None


def validate_license_code(code: str, device_id: str) -> dict:
    """
    验证并激活卡密（核心方法）

    返回 dict:
        ok: bool
        error: str（仅 ok=False 时）
        expire_at: str（ISO，ok=True 时）
        is_permanent: bool
        days_rewarded: int（本次奖励天数，ok=True 时）
    """
    code = code.strip().upper()
    device_id = device_id.upper()

    # 解析类型
    lic_type = _parse_license_type(code)

    # ========== 核心保护：TRIAL 只能新设备使用一次 ==========
    # 如果本机已有激活的卡密（来自本地状态），不能再激活 TRIAL 码
    if lic_type == LicenseType.TRIAL:
        local = load_state()
        if local.get("activated") and local.get("device_id") == device_id:
            return {
                "ok": False,
                "error": "试用机会每位用户仅限一次，请购买正式授权码继续使用",
            }

    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return {"ok": False, "error": "Supabase 未配置，请联系管理员"}

    headers = _get_supabase_headers()
    table_url = f"{_SUPABASE_URL}/rest/v1/licenses?code=eq.{code}"

    # 查询卡密记录
    resp = requests.get(table_url, headers=headers, timeout=15)
    if resp.status_code != 200:
        return {"ok": False, "error": f"网络错误: {resp.status_code}"}

    rows = resp.json()
    if not rows:
        return {"ok": False, "error": "卡密不存在"}

    row = rows[0]

    # 判断类型
    lic_type = _parse_license_type(code)
    if lic_type is None:
        return {"ok": False, "error": "无法识别卡密类型"}

    # 规则校验
    if row.get("is_used") and row.get("device_id") and row["device_id"] != device_id:
        return {"ok": False, "error": "该卡密已被其他设备绑定"}

    # 试用码只能激活一次（device_id 为 NULL 才算未使用）
    if lic_type == LicenseType.TRIAL:
        if row.get("is_used"):
            return {"ok": False, "error": "试用码已被使用，无法重复激活"}

    # 已到期检测（永久卡例外）
    if lic_type != LicenseType.PERMANENT and row.get("expire_at"):
        expire_dt = datetime.fromisoformat(row["expire_at"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > expire_dt:
            return {"ok": False, "error": "卡密已过期"}

    # 计算到期时间
    days = LICENSE_DAYS.get(lic_type, 30)
    if lic_type == LicenseType.PERMANENT:
        expire_at = None
    else:
        start = datetime.now(timezone.utc)
        expire_at = (start + timedelta(days=days)).isoformat().replace("+00:00", "Z")

    # 更新记录
    update_payload = {
        "is_used":   True,
        "device_id": device_id,
    }
    if expire_at:
        update_payload["expire_at"] = expire_at

    # ====== 续期逻辑 ======
    # 情况1：卡密已激活过且是本机 → 续期（在原到期时间上叠加）
    if row.get("is_used") and row.get("device_id") == device_id:
        current_expire = row.get("expire_at")
        if lic_type == LicenseType.TRIAL:
            return {"ok": False, "error": "试用码不支持续期"}
        if current_expire:
            cur_dt = datetime.fromisoformat(current_expire.replace("Z", "+00:00"))
            new_expire = (cur_dt + timedelta(days=days)).isoformat().replace("+00:00", "Z")
            update_payload["expire_at"] = new_expire
            expire_at = new_expire

    # 情况2：卡密新，但本机之前激活过其他卡密（从原到期时间叠加）
    # 例如：TRIAL 过期 → 买 MONTH → 在 TRIAL 到期时间上叠加
    elif lic_type != LicenseType.TRIAL:
        # 查询本设备之前激活的卡密的到期时间
        device_url = (
            f"{_SUPABASE_URL}/rest/v1/licenses?device_id=eq.{device_id}"
            f"&order=expire_at.desc&limit=1&select=expire_at"
        )
        dev_resp = requests.get(device_url, headers=headers, timeout=15)
        if dev_resp.status_code == 200 and dev_resp.json():
            prev_expire = dev_resp.json()[0].get("expire_at")
            if prev_expire:
                prev_dt = datetime.fromisoformat(prev_expire.replace("Z", "+00:00"))
                # 从较早的到期时间开始叠加
                base_dt = max(prev_dt, datetime.now(timezone.utc))
                new_expire = (base_dt + timedelta(days=days)).isoformat().replace("+00:00", "Z")
                update_payload["expire_at"] = new_expire
                expire_at = new_expire

    update_url = f"{_SUPABASE_URL}/rest/v1/licenses?code=eq.{code}"
    upd_resp = requests.patch(update_url, headers=headers, json=update_payload, timeout=15)
    if upd_resp.status_code not in (200, 204):
        return {"ok": False, "error": f"激活失败: {upd_resp.status_code}"}

    # 如果有父码，给父码 +5 天
    days_rewarded = 0
    parent_code = row.get("parent_code")
    if parent_code:
        days_rewarded = _reward_parent(parent_code, REWARD_DAYS)

    return {
        "ok": True,
        "expire_at": expire_at or "2099-12-31T23:59:59Z",
        "is_permanent": lic_type == LicenseType.PERMANENT,
        "days_rewarded": days_rewarded,
    }


def _reward_parent(parent_code: str, days: int) -> int:
    """给父码增加奖励天数"""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return 0

    headers = _get_supabase_headers()

    # 查询父码
    parent_upper = parent_code.upper()
    get_url = f"{_SUPABASE_URL}/rest/v1/licenses?code=eq.{parent_upper}"
    resp = requests.get(get_url, headers=headers, timeout=15)
    if resp.status_code != 200 or not resp.json():
        return 0

    parent_row = resp.json()[0]
    current_reward = parent_row.get("reward_days", 0)
    current_expire = parent_row.get("expire_at")

    new_reward = current_reward + days

    if current_expire:
        cur_dt = datetime.fromisoformat(current_expire.replace("Z", "+00:00"))
        new_expire = (cur_dt + timedelta(days=days)).isoformat().replace("+00:00", "Z")
        patch = {"reward_days": new_reward, "expire_at": new_expire}
    else:
        patch = {"reward_days": new_reward}

    patch_url = f"{_SUPABASE_URL}/rest/v1/licenses?code=eq.{parent_upper}"
    requests.patch(patch_url, headers=headers, json=patch, timeout=15)
    return days


def check_local_license() -> dict:
    """
    启动时检查本地授权状态（以数据库到期时间为准，防止本地篡改）。

    返回 dict:
        activated: bool
        device_id: str
        expire_at: str | None
        is_permanent: bool
        remaining_days: int
    """
    state = load_state()
    device_id = get_machine_id()

    # 未激活
    if not state.get("activated"):
        return {"activated": False, "device_id": device_id}

    # 已激活但设备码不一致 → 强制重新授权
    if state.get("device_id") != device_id:
        return {"activated": False, "device_id": device_id, "reason": "设备变更，请重新激活"}

    is_permanent = state.get("is_permanent", False)
    local_expire = state.get("expire_at")

    # 从数据库查询真实到期时间（以数据库为准，防止本地篡改）
    db_expire = _get_db_expire_at(state.get("code", ""))
    expire_at = db_expire or local_expire

    # 如果数据库时间和本地不一致，以数据库为准，并同步本地文件
    if db_expire and db_expire != local_expire:
        state["expire_at"] = db_expire
        save_state(state)
        local_expire = db_expire  # 更新后续计算用

    remaining_days = 0

    if expire_at and not is_permanent:
        expire_dt = datetime.fromisoformat(expire_at.replace("Z", "+00:00"))
        delta = expire_dt - datetime.now(timezone.utc)
        remaining_days = delta.days
        if remaining_days < 0:
            return {"activated": False, "device_id": device_id, "reason": "已过期"}

    return {
        "activated": True,
        "device_id": device_id,
        "expire_at": expire_at,
        "is_permanent": is_permanent,
        "remaining_days": remaining_days,
    }


def activate_license(code: str) -> dict:
    """
    激活卡密：验证后写入本地状态 + 更新数据库。
    """
    device_id = get_machine_id()
    result = validate_license_code(code, device_id)

    if not result["ok"]:
        return {"success": False, "error": result["error"]}

    state = {
        "activated":   True,
        "device_id":   device_id,
        "expire_at":   result["expire_at"],
        "is_permanent": result.get("is_permanent", False),
        "activated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "code":        code.upper(),
    }
    save_state(state)

    return {
        "success":      True,
        "expire_at":    result["expire_at"],
        "is_permanent": result.get("is_permanent", False),
        "days_rewarded": result.get("days_rewarded", 0),
    }


def get_child_codes(parent_code: str) -> list:
    """获取某卡密下所有已生成的子码列表"""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return []
    headers = _get_supabase_headers()
    parent_upper = parent_code.upper()
    url = f"{_SUPABASE_URL}/rest/v1/licenses?parent_code=eq.{parent_upper}&order=created_at.asc&select=code,is_used"
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code != 200:
            return []
        return resp.json()
    except Exception:
        return []


def get_invite_count(code: str) -> int:
    """查询某卡密已生成多少个子码"""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return 0
    headers = _get_supabase_headers()
    parent_upper = code.upper()
    count_url = f"{_SUPABASE_URL}/rest/v1/licenses?parent_code=eq.{parent_upper}&select=code"
    resp = requests.get(count_url, headers=headers, timeout=15)
    if resp.status_code != 200:
        return 0
    return len(resp.json())


def generate_invite_codes(parent_code: str, count: int = 5) -> tuple:
    """
    在数据库中生成子码（每个卡密最多 5 个）。
    返回 (codes_list, error_message)，codes 为空表示失败。
    """
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return [], "Supabase 未配置"

    headers = _get_supabase_headers()
    parent_upper = parent_code.upper()

    # 检查父码是否存在
    get_url = f"{_SUPABASE_URL}/rest/v1/licenses?code=eq.{parent_upper}"
    resp = requests.get(get_url, headers=headers, timeout=15)
    if resp.status_code != 200 or not resp.json():
        return [], "父码不存在"

    # 查询已生成的子码数量
    existing_count = get_invite_count(parent_upper)
    remaining = 5 - existing_count

    if remaining <= 0:
        return [], "该邀请码已生成过 5 个子码，无法继续生成"

    # 实际可生成的数量
    actual_count = min(count, remaining)
    codes = []

    for _ in range(actual_count):
        suffix = hashlib.sha1(uuid.uuid4().bytes).hexdigest()[:8].upper()
        child_code = f"TRIAL{suffix}"

        payload = {
            "code":        child_code,
            "parent_code": parent_upper,
            "reward_days": 0,
            "is_used":     False,
            "created_at":  datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

        insert_url = f"{_SUPABASE_URL}/rest/v1/licenses"
        ins_resp = requests.post(insert_url, headers=headers, json=payload, timeout=15)
        if ins_resp.status_code in (200, 201):
            codes.append(child_code)

    return codes, ""
