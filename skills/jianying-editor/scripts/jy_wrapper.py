"""
JianYing Editor Skill - High Level Wrapper (Mixin Based)
旨在解决路径依赖、API 复杂度及严格校验问题。
"""

import os
import sys
import uuid
from typing import Union, Optional

# 环境初始化
from utils.env_setup import setup_env
setup_env()

# 导入工具函数
from utils.constants import SYNONYMS
from utils.formatters import (
    resolve_enum_with_synonyms, format_srt_time, safe_tim, 
    get_duration_ffprobe_cached, get_default_drafts_root, get_all_drafts
)

# 导入基类与 Mixins
from core.project_base import JyProjectBase
from core.media_ops import MediaOpsMixin
from core.text_ops import TextOpsMixin
from core.vfx_ops import VfxOpsMixin
from core.mocking_ops import MockingOpsMixin

try:
    import pyJianYingDraft as draft
    from pyJianYingDraft import VideoSceneEffectType, TransitionType
except ImportError:
    draft = None

class JyProject(JyProjectBase, MediaOpsMixin, TextOpsMixin, VfxOpsMixin, MockingOpsMixin):
    """
    高层封装工程类。通过多重继承 Mixins 实现功能解耦。
    """
    def _resolve_enum(self, enum_cls, name: str):
        return resolve_enum_with_synonyms(enum_cls, name, SYNONYMS)

    def add_clip(self, media_path: str, source_start: Union[str, int], duration: Union[str, int], 
                 target_start: Union[str, int] = None, track_name: str = "VideoTrack", **kwargs):
        """高层剪辑接口：从媒体指定位置裁剪指定长度，并放入轨道。"""
        if target_start is None:
            target_start = self.get_track_duration(track_name)
        return self.add_media_safe(media_path, target_start, duration, track_name, source_start=source_start, **kwargs)

    def save(self):
        """保存并执行质检报告。"""
        print(f"[DEBUG] JyProject.save() called, _cloud_audio_patches: {dict(self._cloud_audio_patches)}")
        self.script.save()

        # 直接内联执行 patch 逻辑，避免 mixin 调用问题
        self._do_patch_cloud_materials()
        self._force_activate_adjustments()

        draft_path = os.path.join(self.root, self.name)
        if os.path.exists(draft_path):
            os.utime(draft_path, None)
        print(f"✅ Project '{self.name}' saved and patched.")
        return {"status": "SUCCESS", "draft_path": draft_path}

    def _do_patch_cloud_materials(self):
        """直接执行云端素材补丁"""
        import json as _json
        print(f"[Mock] _do_patch_cloud_materials called")
        print(f"[Mock] _cloud_audio_patches = {dict(self._cloud_audio_patches)}")

        if not self._cloud_audio_patches and not self._cloud_text_patches:
            print("[Mock] No patches to apply")
            return

        content_path = os.path.join(self.root, self.name, "draft_content.json")
        if not os.path.exists(content_path):
            print(f"[Mock] draft_content.json not found: {content_path}")
            return

        try:
            with open(content_path, "r", encoding="utf-8") as f:
                data = _json.load(f)

            has_modified = False
            materials = data.get("materials", {})
            audios = materials.get("audios", [])

            print(f"[Mock] Found {len(audios)} audio materials")

            # 构建 id -> patch_info 的映射
            id_to_patch = {v["id"]: v for v in self._cloud_audio_patches.values()}

            for mat in audios:
                mat_id = mat.get("id", "")
                mat_path = mat.get("path", "")

                # 方式1: 通过path匹配
                matched_patch = None
                for dummy_path, patch_info in self._cloud_audio_patches.items():
                    if dummy_path in mat_path:
                        matched_patch = patch_info
                        print(f"[Mock] Matched by path: {mat_id}")
                        break

                # 方式2: 通过id匹配
                if not matched_patch and mat_id in id_to_patch:
                    matched_patch = id_to_patch[mat_id]
                    print(f"[Mock] Matched by id: {mat_id}")

                if matched_patch:
                    patch_type = matched_patch.get("type", "music")
                    patch_id = matched_patch.get("id", "")

                    mat["local_material_id"] = patch_id
                    mat["path"] = ""
                    mat["source_platform"] = 1
                    mat["is_ugc"] = False

                    if patch_type == "sound_effect":
                        mat["type"] = "sound"
                        mat["effect_id"] = patch_id
                        mat["music_id"] = ""
                        print(f"[Mock] Patched sound effect: {patch_id}")
                    else:
                        mat["type"] = "extract_music"
                        mat["music_id"] = patch_id
                        mat["effect_id"] = ""
                        print(f"[Mock] Patched music: {patch_id}")

                    has_modified = True

            if has_modified:
                with open(content_path, "w", encoding="utf-8") as f:
                    _json.dump(data, f, ensure_ascii=False)
                print(f"[Mock] Saved {len([m for m in audios if m.get('type') == 'sound'])} sound effects")
        except Exception as e:
            print(f"⚠️ Patch failed: {e}")
            import traceback
            traceback.print_exc()

# 导出工具函数以便向下兼容
__all__ = ["JyProject", "get_default_drafts_root", "get_all_drafts", "safe_tim", "format_srt_time"]

if __name__ == "__main__":
    # 测试代码
    try:
        project = JyProject("Refactor_Test_Project", overwrite=True)
        print("🚀 Refactored JyProject initialized successfully.")
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
