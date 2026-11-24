using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace Vrc2Gtav.Editor
{
    internal sealed class AvatarMaterialTextureSlot
    {
        public string MaterialName = string.Empty;
        public Texture2D DefaultTexture;
        public Texture2D SelectedTexture;
        public string ExternalOverridePath = string.Empty;

        public bool IsOverridden =>
            !string.IsNullOrWhiteSpace(ExternalOverridePath)
            || (SelectedTexture != null && SelectedTexture != DefaultTexture);

        public string ResolveOverrideDiskPath()
        {
            if (!string.IsNullOrWhiteSpace(ExternalOverridePath) && File.Exists(ExternalOverridePath))
            {
                return Path.GetFullPath(ExternalOverridePath);
            }
            if (SelectedTexture != null && SelectedTexture != DefaultTexture)
            {
                string assetPath = AssetDatabase.GetAssetPath(SelectedTexture);
                if (!string.IsNullOrEmpty(assetPath))
                {
                    string absPath = Vrc2GtavAvatarResolver.ToAbsoluteProjectPath(assetPath);
                    if (File.Exists(absPath)) return absPath;
                }
            }
            return string.Empty;
        }
    }

    internal sealed class Vrc2GtavTexturesPanel
    {
        private readonly List<AvatarMaterialTextureSlot> _slots = new List<AvatarMaterialTextureSlot>();
        private readonly Dictionary<string, string> _pendingOverrides = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        private string _lastAvatarKey = string.Empty;
        private bool _foldout = true;
        private Vector2 _slotsScroll;
        private Texture2D _globalOverrideTex;
        private string _globalOverrideExternal = string.Empty;

        public void SyncWithAvatar(ResolvedAvatarSource avatar)
        {
            string key = (avatar?.SourcePath ?? string.Empty) + "|" + (avatar?.AvatarName ?? string.Empty) + "|" +
                (avatar?.ObjectRef != null ? avatar.ObjectRef.GetInstanceID().ToString() : "0");
            if (string.Equals(key, _lastAvatarKey, StringComparison.Ordinal)) return;
            RefreshFromAvatar(avatar, key);
        }

        public void CopyOverridesFrom(Vrc2GtavTexturesPanel other) =>
            ApplyTextureOverridesMap(other?.BuildTextureOverridesMap());

        public void ApplyTextureOverridesMap(IReadOnlyDictionary<string, string> overrides)
        {
            ResetAllOverrides();
            _pendingOverrides.Clear();
            if (overrides == null || overrides.Count == 0) return;
            foreach (var pair in overrides)
            {
                if (!string.IsNullOrWhiteSpace(pair.Key) && !string.IsNullOrWhiteSpace(pair.Value))
                    _pendingOverrides[pair.Key] = pair.Value;
            }
            if (_pendingOverrides.TryGetValue("*", out string starPath)) RestoreGlobalOverride(starPath);
            for (int i = 0; i < _slots.Count; i++)
            {
                if (_pendingOverrides.TryGetValue(_slots[i].MaterialName, out string slotPath))
                    RestoreOverride(_slots[i], slotPath);
            }
        }

        public void RefreshFromAvatar(ResolvedAvatarSource avatar, string keyOverride = null)
        {
            _lastAvatarKey = keyOverride ?? ((avatar?.SourcePath ?? string.Empty) + "|" + (avatar?.AvatarName ?? string.Empty));
            var oldOverrides = BuildTextureOverridesMap();
            foreach (var kv in _pendingOverrides)
            {
                if (!oldOverrides.ContainsKey(kv.Key)) oldOverrides[kv.Key] = kv.Value;
            }
            _pendingOverrides.Clear();
            _slots.Clear();

            if (avatar?.ObjectRef is GameObject go)
            {
                bool isSceneObj = avatar.Kind == AvatarSourceKind.SceneGameObject;
                var seenMats = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                Renderer[] renderers = go.GetComponentsInChildren<Renderer>(true);
                for (int r = 0; r < renderers.Length; r++)
                {
                    Renderer ren = renderers[r];
                    if (ren == null) continue;
                    bool isActive = isSceneObj ? ren.gameObject.activeInHierarchy : ren.gameObject.activeSelf;
                    if (!isActive) continue;

                    Material[] mats = ren.sharedMaterials;
                    if (mats == null) continue;
                    for (int m = 0; m < mats.Length; m++)
                    {
                        Material mat = mats[m];
                        if (mat == null) continue;
                        string cleanName = StripInstanceSuffix(mat.name);
                        if (string.IsNullOrEmpty(cleanName) || !seenMats.Add(cleanName)) continue;

                        Texture2D mainTex = mat.HasProperty("_MainTex")
                            ? mat.GetTexture("_MainTex") as Texture2D
                            : mat.mainTexture as Texture2D;

                        var slot = new AvatarMaterialTextureSlot
                        {
                            MaterialName = cleanName,
                            DefaultTexture = mainTex,
                            SelectedTexture = mainTex
                        };
                        if (oldOverrides.TryGetValue(cleanName, out string prevPath))
                        {
                            RestoreOverride(slot, prevPath);
                        }
                        _slots.Add(slot);
                    }
                }
            }
        }

        public Dictionary<string, string> BuildTextureOverridesMap()
        {
            var map = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            if (_slots.Count > 0)
            {
                for (int i = 0; i < _slots.Count; i++)
                {
                    string path = _slots[i].ResolveOverrideDiskPath();
                    if (!string.IsNullOrEmpty(path)) map[_slots[i].MaterialName] = path;
                }
            }
            string globalPath = ResolveTextureOrExternalPath(_globalOverrideTex, _globalOverrideExternal);
            if (!string.IsNullOrEmpty(globalPath))
            {
                map["*"] = globalPath;
            }
            foreach (var kv in _pendingOverrides)
            {
                if (!string.IsNullOrWhiteSpace(kv.Value) && !map.ContainsKey(kv.Key)) map[kv.Key] = kv.Value;
            }
            return map;
        }

        public void DrawSection(
            Vrc2GtavSlotProfile profile,
            Vrc2GtavExportOptions globalOpts,
            UiLanguageMode lang,
            ResolvedAvatarSource avatar,
            IList<ProtagonistAvatarSlot> allSlots = null,
            string sectionTitle = null)
        {
            SyncWithAvatar(avatar);
            EditorGUILayout.BeginVertical(EditorStyles.helpBox);
            string title = string.IsNullOrEmpty(sectionTitle) ? Vrc2GtavLocalization.Get(lang, "sec.textures_res") : sectionTitle;
            _foldout = EditorGUILayout.Foldout(_foldout, title, true);
            if (_foldout)
            {
                DrawResolutionControls(profile, globalOpts, lang, allSlots);
                EditorGUILayout.Space(4f);
                DrawAvatarTextureSlots(lang, avatar);
            }
            EditorGUILayout.EndVertical();
        }

        private static void DrawResolutionControls(
            Vrc2GtavSlotProfile profile, Vrc2GtavExportOptions globalOpts, UiLanguageMode lang, IList<ProtagonistAvatarSlot> allSlots)
        {
            string[] atlasLabels = { "512 px (Low / Smallest RPF)", "1024 px (Medium / Safe)", "2048 px (Standard 2K)", "4096 px (4K Ultra)" };
            EditorGUILayout.BeginHorizontal();
            profile.AtlasResolutionIdx = EditorGUILayout.Popup(
                Vrc2GtavLocalization.Get(lang, "tex.atlas_res"),
                Mathf.Clamp(profile.AtlasResolutionIdx, 0, atlasLabels.Length - 1),
                atlasLabels);
            using (new EditorGUI.DisabledScope(profile.AtlasResolutionIdx <= 0))
            {
                if (GUILayout.Button("-", GUILayout.Width(26f))) profile.AtlasResolutionIdx--;
            }
            using (new EditorGUI.DisabledScope(profile.AtlasResolutionIdx >= atlasLabels.Length - 1))
            {
                if (GUILayout.Button("+", GUILayout.Width(26f))) profile.AtlasResolutionIdx++;
            }
            EditorGUILayout.EndHorizontal();

            string[] normalLabels = { "Auto", "Off (64 px)", "256 px", "512 px", "1024 px" };
            profile.NormalResolutionIdx = EditorGUILayout.Popup(
                Vrc2GtavLocalization.Get(lang, "tex.normal_res"),
                Mathf.Clamp(profile.NormalResolutionIdx, 0, normalLabels.Length - 1),
                normalLabels);

            string[] secLabels = { "Auto (<3.7 GiB Safe RPF)", "512 px (Max RPF Savings)", "1024 px (Balanced)", "2048 px (Full Secondary)" };
            string secKey = globalOpts.PerProtagonistSlots ? "tex.secondary_res_shared" : "tex.secondary_res";
            globalOpts.Shared.SecondaryResolutionIdx = EditorGUILayout.Popup(
                Vrc2GtavLocalization.Get(lang, secKey),
                Mathf.Clamp(globalOpts.Shared.SecondaryResolutionIdx, 0, secLabels.Length - 1),
                secLabels);

            DrawRpfEstimate(profile, globalOpts, lang, allSlots);
        }

        private static float CalcPrimaryYtdMb(int atlasPx, int normPx)
        {
            float estYtdMb = atlasPx <= 512 ? 0.35f : (atlasPx <= 1024 ? 0.90f : (atlasPx <= 2048 ? 2.10f : 6.80f));
            if (normPx > 0 && normPx <= 64) estYtdMb *= 0.60f;
            else if (normPx >= 1024) estYtdMb += 0.60f;
            return estYtdMb;
        }

        private static void DrawRpfEstimate(
            Vrc2GtavSlotProfile profile, Vrc2GtavExportOptions globalOpts, UiLanguageMode lang, IList<ProtagonistAvatarSlot> allSlots)
        {
            int atlasPx = Vrc2GtavCommandBuilder.GetAtlasResolution(profile);
            float estYtdMb = CalcPrimaryYtdMb(atlasPx, Vrc2GtavCommandBuilder.GetNormalResolution(profile));
            int secPx = Vrc2GtavCommandBuilder.GetSecondaryResolution(globalOpts.Shared);
            float estTotalMb = 0f;
            bool heavyRisk = atlasPx >= 4096;

            if (globalOpts.PerProtagonistSlots && allSlots != null)
            {
                List<ProtagonistAvatarSlot> enabled = Vrc2GtavMultiSlotUi.GetEnabledSlots(allSlots, globalOpts);
                for (int i = 0; i < enabled.Count; i++)
                {
                    Vrc2GtavSlotProfile sp = enabled[i].Profile;
                    int sAtlas = Vrc2GtavCommandBuilder.GetAtlasResolution(sp);
                    float sYtd = CalcPrimaryYtdMb(sAtlas, Vrc2GtavCommandBuilder.GetNormalResolution(sp));
                    float sSec = secPx == 512 ? 0.30f : (secPx == 1024 ? 0.70f : (secPx == 2048 ? sYtd : Math.Min(sYtd, 0.70f)));
                    int slots = enabled[i].PedModel == "player_zero" ? 181 : (enabled[i].PedModel == "player_one" ? 318 : 242);
                    estTotalMb += 5f * sYtd + Mathf.Max(0, slots - 5) * sSec;
                    if (sAtlas >= 4096) heavyRisk = true;
                }
            }
            else
            {
                int ytdSlots = (globalOpts.TargetMichael ? 181 : 0) + (globalOpts.TargetFranklin ? 318 : 0) + (globalOpts.TargetTrevor ? 242 : 0);
                float secYtdMb = secPx == 512 ? 0.30f : (secPx == 1024 ? 0.70f : (secPx == 2048 ? estYtdMb : Math.Min(estYtdMb, 0.70f)));
                estTotalMb = ytdSlots > 0 ? (16 * estYtdMb + Mathf.Max(0, ytdSlots - 16) * secYtdMb) : 0f;
            }
            if ((secPx >= 2048 && estTotalMb > 1400f) || estTotalMb > 3200f) heavyRisk = true;

            string msg = string.Format(
                Vrc2GtavLocalization.Get(lang, heavyRisk ? "tex.rpf_warn" : "tex.rpf_safe"),
                estYtdMb.ToString("0.0"),
                estTotalMb.ToString("0"));
            EditorGUILayout.HelpBox(msg, heavyRisk ? MessageType.Warning : MessageType.Info);
        }

        private void DrawAvatarTextureSlots(UiLanguageMode lang, ResolvedAvatarSource avatar)
        {
            EditorGUILayout.BeginHorizontal();
            EditorGUILayout.LabelField(Vrc2GtavLocalization.Get(lang, "tex.mat_list"), EditorStyles.boldLabel);
            GUILayout.FlexibleSpace();
            if (GUILayout.Button(Vrc2GtavLocalization.Get(lang, "tex.refresh"), GUILayout.Width(85f)))
            {
                RefreshFromAvatar(avatar, string.Empty);
            }
            if (GUILayout.Button(Vrc2GtavLocalization.Get(lang, "tex.reset_all"), GUILayout.Width(95f)))
            {
                ResetAllOverrides();
            }
            EditorGUILayout.EndHorizontal();

            if (_slots.Count == 0)
            {
                EditorGUILayout.LabelField(Vrc2GtavLocalization.Get(lang, "tex.no_renderers"), EditorStyles.miniLabel);
                DrawGlobalOverrideRow(lang);
                return;
            }

            float height = Mathf.Min(165f, 24f * _slots.Count + 6f);
            _slotsScroll = EditorGUILayout.BeginScrollView(_slotsScroll, GUILayout.Height(height));
            for (int i = 0; i < _slots.Count; i++)
            {
                DrawSingleMaterialSlot(_slots[i], lang);
            }
            EditorGUILayout.EndScrollView();
        }

        private static void DrawSingleMaterialSlot(AvatarMaterialTextureSlot slot, UiLanguageMode lang)
        {
            EditorGUILayout.BeginHorizontal();
            float nameW = Mathf.Clamp(EditorGUIUtility.currentViewWidth * 0.28f, 90f, 155f);
            EditorGUILayout.LabelField(new GUIContent(slot.MaterialName, slot.MaterialName), GUILayout.Width(nameW));
            Texture2D nextTex = (Texture2D)EditorGUILayout.ObjectField(slot.SelectedTexture, typeof(Texture2D), false, GUILayout.MinWidth(60f));
            if (nextTex != slot.SelectedTexture)
            {
                slot.SelectedTexture = nextTex;
                slot.ExternalOverridePath = string.Empty;
            }
            if (GUILayout.Button("...", GUILayout.Width(28f)))
            {
                string picked = EditorUtility.OpenFilePanel(slot.MaterialName, Vrc2GtavConfigDiscovery.GetDefaultUnityAssetsPath(), "png,jpg,jpeg,tga,psd,webp");
                if (!string.IsNullOrEmpty(picked)) RestoreOverride(slot, picked);
            }
            using (new EditorGUI.DisabledScope(!slot.IsOverridden))
            {
                if (GUILayout.Button(Vrc2GtavLocalization.Get(lang, "tex.reset_one"), GUILayout.Width(52f)))
                {
                    slot.SelectedTexture = slot.DefaultTexture;
                    slot.ExternalOverridePath = string.Empty;
                }
            }
            EditorGUILayout.EndHorizontal();
        }

        private void DrawGlobalOverrideRow(UiLanguageMode lang)
        {
            EditorGUILayout.BeginHorizontal();
            _globalOverrideTex = (Texture2D)EditorGUILayout.ObjectField(
                Vrc2GtavLocalization.Get(lang, "tex.global_override"),
                _globalOverrideTex,
                typeof(Texture2D),
                false);
            if (GUILayout.Button("...", GUILayout.Width(28f)))
            {
                string picked = EditorUtility.OpenFilePanel(
                    Vrc2GtavLocalization.Get(lang, "tex.global_override"),
                    Vrc2GtavConfigDiscovery.GetDefaultUnityAssetsPath(),
                    "png,jpg,jpeg,tga,psd,webp");
                if (!string.IsNullOrEmpty(picked)) _globalOverrideExternal = Path.GetFullPath(picked);
            }
            EditorGUILayout.EndHorizontal();
            if (!string.IsNullOrEmpty(_globalOverrideExternal))
            {
                EditorGUILayout.LabelField(_globalOverrideExternal, EditorStyles.miniLabel);
            }
        }

        private void ResetAllOverrides()
        {
            for (int i = 0; i < _slots.Count; i++)
            {
                _slots[i].SelectedTexture = _slots[i].DefaultTexture;
                _slots[i].ExternalOverridePath = string.Empty;
            }
            _globalOverrideTex = null;
            _globalOverrideExternal = string.Empty;
        }

        private static Texture2D TryLoadProjectTexture(string fullPath)
        {
            string projRoot = Vrc2GtavConfigDiscovery.GetUnityProjectRoot().Replace('\\', '/').TrimEnd('/') + "/";
            string norm = fullPath.Replace('\\', '/');
            if (!norm.StartsWith(projRoot, StringComparison.OrdinalIgnoreCase)) return null;
            return AssetDatabase.LoadAssetAtPath<Texture2D>(norm.Substring(projRoot.Length));
        }

        private void RestoreGlobalOverride(string diskPath)
        {
            string full = Path.GetFullPath(diskPath);
            Texture2D asset = TryLoadProjectTexture(full);
            if (asset != null)
            {
                _globalOverrideTex = asset;
                _globalOverrideExternal = string.Empty;
            }
            else
            {
                _globalOverrideTex = null;
                _globalOverrideExternal = full;
            }
        }

        private static void RestoreOverride(AvatarMaterialTextureSlot slot, string diskPath)
        {
            string full = Path.GetFullPath(diskPath);
            Texture2D asset = TryLoadProjectTexture(full);
            if (asset != null)
            {
                slot.SelectedTexture = asset;
                slot.ExternalOverridePath = string.Empty;
                return;
            }
            slot.ExternalOverridePath = full;
        }

        private static string ResolveTextureOrExternalPath(Texture2D tex, string extPath)
        {
            if (!string.IsNullOrWhiteSpace(extPath) && File.Exists(extPath)) return Path.GetFullPath(extPath);
            if (tex != null)
            {
                string rel = AssetDatabase.GetAssetPath(tex);
                if (!string.IsNullOrEmpty(rel))
                {
                    string abs = Vrc2GtavAvatarResolver.ToAbsoluteProjectPath(rel);
                    if (File.Exists(abs)) return abs;
                }
            }
            return string.Empty;
        }

        private static string StripInstanceSuffix(string name)
        {
            if (string.IsNullOrWhiteSpace(name)) return string.Empty;
            const string inst = " (Instance)";
            return name.EndsWith(inst, StringComparison.OrdinalIgnoreCase)
                ? name.Substring(0, name.Length - inst.Length).Trim()
                : name.Trim();
        }
    }
}
