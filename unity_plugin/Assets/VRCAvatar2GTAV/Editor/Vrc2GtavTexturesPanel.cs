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

        public void RefreshFromAvatar(ResolvedAvatarSource avatar, string keyOverride = null)
        {
            _lastAvatarKey = keyOverride ?? ((avatar?.SourcePath ?? string.Empty) + "|" + (avatar?.AvatarName ?? string.Empty));
            var oldOverrides = BuildTextureOverridesMap();
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
            return map;
        }

        public void DrawSection(Vrc2GtavExportOptions opts, UiLanguageMode lang, ResolvedAvatarSource avatar)
        {
            SyncWithAvatar(avatar);
            EditorGUILayout.BeginVertical(EditorStyles.helpBox);
            _foldout = EditorGUILayout.Foldout(_foldout, Vrc2GtavLocalization.Get(lang, "sec.textures_res"), true);
            if (_foldout)
            {
                DrawResolutionControls(opts, lang);
                EditorGUILayout.Space(4f);
                DrawAvatarTextureSlots(lang, avatar);
            }
            EditorGUILayout.EndVertical();
        }

        private void DrawResolutionControls(Vrc2GtavExportOptions opts, UiLanguageMode lang)
        {
            string[] atlasLabels = { "512 px (Low / Smallest RPF)", "1024 px (Medium / Safe)", "2048 px (Standard 2K)", "4096 px (4K Ultra)" };
            EditorGUILayout.BeginHorizontal();
            opts.AtlasResolutionIdx = EditorGUILayout.Popup(
                Vrc2GtavLocalization.Get(lang, "tex.atlas_res"),
                Mathf.Clamp(opts.AtlasResolutionIdx, 0, atlasLabels.Length - 1),
                atlasLabels);
            using (new EditorGUI.DisabledScope(opts.AtlasResolutionIdx <= 0))
            {
                if (GUILayout.Button("-", GUILayout.Width(26f))) opts.AtlasResolutionIdx--;
            }
            using (new EditorGUI.DisabledScope(opts.AtlasResolutionIdx >= atlasLabels.Length - 1))
            {
                if (GUILayout.Button("+", GUILayout.Width(26f))) opts.AtlasResolutionIdx++;
            }
            EditorGUILayout.EndHorizontal();

            string[] normalLabels = { "Auto", "Off (64 px)", "256 px", "512 px", "1024 px" };
            opts.NormalResolutionIdx = EditorGUILayout.Popup(
                Vrc2GtavLocalization.Get(lang, "tex.normal_res"),
                Mathf.Clamp(opts.NormalResolutionIdx, 0, normalLabels.Length - 1),
                normalLabels);

            string[] secLabels = { "Auto (<3.7 GiB Safe RPF)", "512 px (Max RPF Savings)", "1024 px (Balanced)", "2048 px (Full Secondary)" };
            opts.SecondaryResolutionIdx = EditorGUILayout.Popup(
                Vrc2GtavLocalization.Get(lang, "tex.secondary_res"),
                Mathf.Clamp(opts.SecondaryResolutionIdx, 0, secLabels.Length - 1),
                secLabels);

            DrawRpfEstimate(opts, lang);
        }

        private static void DrawRpfEstimate(Vrc2GtavExportOptions opts, UiLanguageMode lang)
        {
            int atlasPx = Vrc2GtavCommandBuilder.GetAtlasResolution(opts);
            int normPx = Vrc2GtavCommandBuilder.GetNormalResolution(opts);
            int secPx = Vrc2GtavCommandBuilder.GetSecondaryResolution(opts);

            float estYtdMb = atlasPx <= 512 ? 0.35f : (atlasPx <= 1024 ? 0.90f : (atlasPx <= 2048 ? 2.10f : 6.80f));
            if (normPx > 0 && normPx <= 64) estYtdMb *= 0.60f;
            else if (normPx >= 1024) estYtdMb += 0.60f;

            int ytdSlots = (opts.TargetMichael ? 181 : 0) + (opts.TargetFranklin ? 318 : 0) + (opts.TargetTrevor ? 242 : 0);
            float secYtdMb = secPx == 512 ? 0.30f : (secPx == 1024 ? 0.70f : (secPx == 2048 ? estYtdMb : Math.Min(estYtdMb, 0.70f)));
            float estTotalMb = ytdSlots > 0 ? (16 * estYtdMb + Mathf.Max(0, ytdSlots - 16) * secYtdMb) : 0f;

            bool heavyRisk = atlasPx >= 4096 || (secPx >= 2048 && estTotalMb > 1400f);
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

        private static void RestoreOverride(AvatarMaterialTextureSlot slot, string diskPath)
        {
            string full = Path.GetFullPath(diskPath);
            string projRoot = Vrc2GtavConfigDiscovery.GetUnityProjectRoot().Replace('\\', '/').TrimEnd('/') + "/";
            string norm = full.Replace('\\', '/');
            if (norm.StartsWith(projRoot, StringComparison.OrdinalIgnoreCase))
            {
                string rel = norm.Substring(projRoot.Length);
                Texture2D asset = AssetDatabase.LoadAssetAtPath<Texture2D>(rel);
                if (asset != null)
                {
                    slot.SelectedTexture = asset;
                    slot.ExternalOverridePath = string.Empty;
                    return;
                }
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

        public static void DrawRestoreVanillaSection(
            UiLanguageMode langMode,
            bool isRunning,
            Action<string, string> onRestoreRequested)
        {
            EditorGUILayout.BeginVertical(EditorStyles.helpBox);
            EditorGUILayout.LabelField(Vrc2GtavLocalization.Get(langMode, "restore.header"), EditorStyles.boldLabel);
            GUILayout.Label(Vrc2GtavLocalization.Get(langMode, "restore.desc"), EditorStyles.wordWrappedMiniLabel);
            EditorGUILayout.Space(3f);

            string btnMichael = Vrc2GtavLocalization.Get(langMode, "restore.michael");
            string btnFranklin = Vrc2GtavLocalization.Get(langMode, "restore.franklin");
            string btnTrevor = Vrc2GtavLocalization.Get(langMode, "restore.trevor");
            string btnAll = Vrc2GtavLocalization.Get(langMode, "restore.all");

            using (new EditorGUI.DisabledScope(isRunning))
            {
                bool narrow = EditorGUIUtility.currentViewWidth < 580f;
                EditorGUILayout.BeginHorizontal();
                if (GUILayout.Button(btnMichael, GUILayout.Height(24f))) onRestoreRequested?.Invoke("player_zero", btnMichael);
                if (GUILayout.Button(btnFranklin, GUILayout.Height(24f))) onRestoreRequested?.Invoke("player_one", btnFranklin);
                if (narrow)
                {
                    EditorGUILayout.EndHorizontal();
                    EditorGUILayout.BeginHorizontal();
                }
                if (GUILayout.Button(btnTrevor, GUILayout.Height(24f))) onRestoreRequested?.Invoke("player_two", btnTrevor);
                if (GUILayout.Button(btnAll, GUILayout.Height(24f))) onRestoreRequested?.Invoke("all", btnAll);
                EditorGUILayout.EndHorizontal();
            }
            EditorGUILayout.EndVertical();
        }

        public static void DrawBlendshapeAndRigOptions(
            Vrc2GtavExportOptions opts,
            UiLanguageMode langMode,
            float baseLabelW,
            ref bool showAdvanced,
            ref AnimationClip faceAnimClip,
            ref bool showCliPreview,
            Vrc2GtavToolPaths paths,
            BackendExecutionMode currentMode,
            GUIStyle wrapMiniLabelStyle,
            Action drawExtraRow,
            Func<ExecutionCommandSpec> buildPreviewSpec,
            Action<BackendExecutionMode> onBackendModeChanged)
        {
            string T(string k) => Vrc2GtavLocalization.Get(langMode, k);
            opts.DeployToMods = EditorGUILayout.ToggleLeft(T("opt.deploy"), opts.DeployToMods);
            opts.ImportFaceBlendshapes = EditorGUILayout.ToggleLeft(T("opt.face_bs"), opts.ImportFaceBlendshapes);
            opts.ImportBodyBlendshapes = EditorGUILayout.ToggleLeft(T("opt.body_bs"), opts.ImportBodyBlendshapes);
            opts.EyeBlink = EditorGUILayout.ToggleLeft(T("opt.eye_blink"), opts.EyeBlink);
            using (new EditorGUI.DisabledScope(!opts.EyeBlink))
                opts.EyeBlinkStrength = EditorGUILayout.Slider(T("opt.eye_strength"), opts.EyeBlinkStrength, 0f, 1f);
            drawExtraRow?.Invoke();
            opts.BloodDecals = EditorGUILayout.ToggleLeft(T("opt.blood_decals"), opts.BloodDecals);

            showAdvanced = EditorGUILayout.Foldout(showAdvanced, T("opt.advanced"), true);
            if (!showAdvanced) return;
            EditorGUI.indentLevel++;
            EditorGUIUtility.labelWidth = baseLabelW + 18f;
            opts.AvatarNameOverride = EditorGUILayout.TextField(T("opt.avatar_override"), opts.AvatarNameOverride);
            opts.BlendshapesSourceIdx = EditorGUILayout.Popup(T("opt.bs_source"), opts.BlendshapesSourceIdx, Vrc2GtavCommandBuilder.SourceModes);
            opts.BlendshapesCfg = Vrc2GtavLogConsoleWidget.DrawPathBrowseRow("Blendshapes .cfg", opts.BlendshapesCfg, string.Empty, true, false, "cfg", T("tools.browse"), paths.RepoRoot);
            opts.FaceBlendshapesAnim = Vrc2GtavLogConsoleWidget.DrawAnimClipOverrideRow(
                T("opt.face_anim"), opts.FaceBlendshapesAnim, ref faceAnimClip,
                T("tools.browse"), Vrc2GtavConfigDiscovery.GetDefaultUnityAssetsPath(), wrapMiniLabelStyle);
            opts.PhysbonesSourceIdx = EditorGUILayout.Popup(T("opt.pb_source"), opts.PhysbonesSourceIdx, Vrc2GtavCommandBuilder.SourceModes);
            opts.PhysbonesCfg = Vrc2GtavLogConsoleWidget.DrawPathBrowseRow("PhysBones .cfg", opts.PhysbonesCfg, string.Empty, true, false, "cfg", T("tools.browse"), paths.RepoRoot);
            opts.PhysbonesMarshmallow = EditorGUILayout.ToggleLeft(T("opt.marshmallow"), opts.PhysbonesMarshmallow);
            opts.ForceReextract = EditorGUILayout.ToggleLeft(T("opt.force_reextract"), opts.ForceReextract);
            string[] backendLabels = { "Auto (Detect Windows / WSL)", "Windows Native", "WSL" };
            EditorGUILayout.BeginHorizontal();
            var nextMode = (BackendExecutionMode)EditorGUILayout.Popup(T("opt.backend_mode"), (int)currentMode, backendLabels);
            Vrc2GtavLogConsoleWidget.DrawStatusBadge(Vrc2GtavConfigDiscovery.DetermineShouldUseWsl(paths, currentMode) ? "WSL" : "Win Native", true);
            EditorGUILayout.EndHorizontal();
            if (nextMode != currentMode) onBackendModeChanged?.Invoke(nextMode);
            showCliPreview = EditorGUILayout.Foldout(showCliPreview, T("opt.cli_preview"), true);
            if (showCliPreview)
            {
                ExecutionCommandSpec previewSpec = buildPreviewSpec();
                if (previewSpec.HasValidationError) EditorGUILayout.HelpBox(previewSpec.ValidationError, MessageType.Error);
                else EditorGUILayout.TextArea(previewSpec.PreviewCommand, EditorStyles.wordWrappedLabel);
            }
            EditorGUIUtility.labelWidth = baseLabelW;
            EditorGUI.indentLevel--;
        }
    }
}
