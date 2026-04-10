import os
import json
import uuid
import pyJianYingDraft as draft

class MockVideoMaterial(draft.VideoMaterial):
    def __init__(self, material_id, duration, name, path):
        self.material_id = material_id
        self.duration = duration
        self.material_name = name
        self.path = path
    def serialize(self):
        return {
            "id": self.material_id, "type": "video", "name": self.material_name, "path": self.path,
            "duration": self.duration, "material_id": self.material_id
        }

class MockAudioMaterial(draft.AudioMaterial):
    def __init__(self, material_id, duration, name, path):
        self.material_id = material_id
        self.duration = duration
        self.material_name = name
        self.path = path

    def export_json(self):
        """导出JSON，使用与云端音频素材兼容的格式"""
        return {
            "app_id": 0,
            "category_id": "",
            "category_name": "",
            "check_flag": 3,
            "copyright_limit_type": "none",
            "duration": self.duration,
            "effect_id": "",
            "formula_id": "",
            "id": self.material_id,
            "local_material_id": self.material_id,
            "music_id": "",
            "name": self.material_name,
            "path": self.path,
            "source_platform": 1,  # 云端素材
            "type": "sound",  # 默认为音效类型，会在patch阶段被修改
            "wave_points": [],
            "is_ugc": False
        }

    def serialize(self):
        return {
            "id": self.material_id, "type": "audio", "name": self.material_name, "path": self.path,
            "duration": self.duration, "material_id": self.material_id
        }

class CompoundSegment:
    def __init__(self, material_id, target_timerange):
        self.material_id = material_id
        self.target_timerange = target_timerange
    def serialize(self):
        return {
             "id": str(uuid.uuid4()).upper(), "material_id": self.material_id,
             "target_timerange": self.target_timerange.serialize(),
             "render_index": 0, "type": "video"
        }

class MockingOpsMixin:
    """
    JyProject 的协议补丁与伪物料 Mixin。
    """
    def _force_activate_adjustments(self):
        content_path = os.path.join(self.root, self.name, "draft_content.json")
        if not os.path.exists(content_path): return

        try:
            with open(content_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            has_modified = False
            materials = data.setdefault("materials", {})
            all_effects = materials.setdefault("effects", [])

            PROP_MAP = {"KFTypeBrightness": "brightness", "KFTypeContrast": "contrast", "KFTypeSaturation": "saturation"}
            jy_res_path = "C:/Program Files/JianyingPro/5.9.0.11632/Resources/DefaultAdjustBundle/combine_adjust"

            for track in data.get("tracks", []):
                for seg in track.get("segments", []):
                    kfs = seg.get("common_keyframes", [])
                    active_props = [kf.get("property_type") for kf in kfs if kf.get("property_type") in PROP_MAP]

                    if active_props:
                        seg["enable_adjust"] = True
                        seg["enable_color_correct_adjust"] = True
                        refs = seg.setdefault("extra_material_refs", [])

                        for prop in active_props:
                            mat_type = PROP_MAP[prop]
                            if not any(m.get("type") == mat_type and m["id"] in refs for m in all_effects):
                                new_id = str(uuid.uuid4()).upper()
                                shadow_mat = {
                                    "type": mat_type, "value": 0.0, "path": jy_res_path, "id": new_id,
                                    "apply_target_type": 0, "platform": "all", "source_platform": 0, "version": "v2"
                                }
                                all_effects.append(shadow_mat)
                                refs.append(new_id)
                                has_modified = True

            if has_modified:
                with open(content_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Force activation failed: {e}")

    def _patch_cloud_material_ids(self):
        print(f"[Mock] _patch_cloud_material_ids called")
        print(f"[Mock] self._cloud_audio_patches id: {id(self._cloud_audio_patches)}")
        print(f"[Mock] _cloud_audio_patches = {dict(self._cloud_audio_patches)}")
        print(f"[Mock] _cloud_text_patches = {dict(self._cloud_text_patches)}")

        if not self._cloud_audio_patches and not self._cloud_text_patches:
            print("[Mock] No cloud audio patches to apply")
            return
        content_path = os.path.join(self.root, self.name, "draft_content.json")
        if not os.path.exists(content_path): return

        print(f"[Mock] Patches to apply: {list(self._cloud_audio_patches.keys())}")

        try:
            with open(content_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            has_modified = False
            materials = data.get("materials", {})
            audios = materials.get("audios", [])

            # 构建 effect_id -> patch_info 的映射
            effect_id_to_patch = {v["id"]: v for v in self._cloud_audio_patches.values()}
            print(f"[Mock] Effect ID map: {list(effect_id_to_patch.keys())}")

            for mat in audios:
                mat_id = mat.get("id", "")
                mat_path = mat.get("path", "")

                # 方式1: 通过path匹配（原始方式）
                matched_patch = None
                for dummy_path, patch_info in self._cloud_audio_patches.items():
                    if dummy_path in mat_path:
                        matched_patch = patch_info
                        print(f"[Mock] Matched by path: {mat_id}")
                        break

                # 方式2: 通过id匹配（更可靠）
                if not matched_patch and mat_id in effect_id_to_patch:
                    matched_patch = effect_id_to_patch[mat_id]
                    print(f"[Mock] Matched by id: {mat_id}")

                if matched_patch:
                    patch_type = matched_patch.get("type", "music")
                    patch_id = matched_patch.get("id", "")

                    # 设置通用字段
                    mat["local_material_id"] = patch_id
                    # 清空 path，让剪映从云端获取
                    mat["path"] = ""
                    # 标记为云端素材
                    mat["source_platform"] = 1
                    mat["is_ugc"] = False

                    if patch_type == "sound_effect":
                        # 音效: type="sound", 使用 effect_id 字段
                        mat["type"] = "sound"
                        mat["effect_id"] = patch_id
                        mat["music_id"] = ""
                        print(f"[Mock] Patched cloud sound effect: {patch_id}")
                    else:
                        # 音乐: type="extract_music", 使用 music_id 字段
                        mat["type"] = "extract_music"
                        mat["music_id"] = patch_id
                        mat["effect_id"] = ""
                        print(f"[Mock] Patched cloud music: {patch_id}")

                    has_modified = True

            if has_modified:
                with open(content_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                print(f"[Mock] Draft saved with {len([m for m in audios if m.get('type') == 'sound'])} sound effects")
        except Exception as e:
            print(f"⚠️ Patch cloud material IDs failed: {e}")
            import traceback
            traceback.print_exc()
