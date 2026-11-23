using System.IO;
using UnityEditor;
using UnityEngine;

namespace Vrc2Gtav.Editor
{
    internal sealed class Vrc2GtavLogConsoleWidget
    {
        private const string LogHeightPrefKey = "Vrc2Gtav.Exporter.LogPanelHeight";
        private const float DefaultLogHeight = 185f;
        private const float MinLogHeight = 72f;

        private Vector2 _logScroll;
        private bool _autoScrollLogs = true;
        private int _lastSeenLogCount;
        private float _logHeight = DefaultLogHeight;
        private bool _logHeightLoaded;
        private bool _isResizingLogs;
        private float _dragStartScreenY;
        private float _dragStartHeight;
        private GUIStyle _logAreaStyle;

        public void Draw(
            Vrc2GtavProcessRunner runner,
            UiLanguageMode langMode,
            string repoRoot,
            string statusMessage,
            MessageType statusSeverity,
            bool canStart,
            System.Action onStartClicked,
            float windowHeight = 680f,
            System.Action onRepaintRequested = null)
        {
            if (!_logHeightLoaded)
            {
                _logHeight = Mathf.Max(MinLogHeight, EditorPrefs.GetFloat(LogHeightPrefKey, DefaultLogHeight));
                _logHeightLoaded = true;
            }
            if (_logAreaStyle == null)
            {
                _logAreaStyle = new GUIStyle(EditorStyles.textArea) { wordWrap = false, fontSize = 11 };
            }

            EditorGUILayout.BeginHorizontal();
            using (new EditorGUI.DisabledScope(!canStart))
            {
                Color prevBg = GUI.backgroundColor;
                GUI.backgroundColor = canStart ? new Color(0.28f, 0.72f, 0.42f) : prevBg;
                if (GUILayout.Button(Vrc2GtavLocalization.Get(langMode, "btn.start"), GUILayout.Height(36f)))
                {
                    onStartClicked?.Invoke();
                }
                GUI.backgroundColor = prevBg;
            }
            using (new EditorGUI.DisabledScope(!runner.IsRunning))
            {
                if (GUILayout.Button(Vrc2GtavLocalization.Get(langMode, "btn.cancel"), GUILayout.Width(100f), GUILayout.Height(36f)))
                {
                    runner.Cancel();
                }
            }
            EditorGUILayout.EndHorizontal();

            Rect barRect = GUILayoutUtility.GetRect(0f, 18f, GUILayout.ExpandWidth(true));
            float pct = runner.IsRunning
                ? runner.Progress
                : (runner.LastExitCode == 0 && runner.LogLines.Count > 0 ? 1f : 0f);
            string barText = runner.IsRunning
                ? (runner.StatusLine ?? Vrc2GtavLocalization.Get(langMode, "status.running"))
                : (string.IsNullOrEmpty(statusMessage) ? Vrc2GtavLocalization.Get(langMode, "status.idle") : statusMessage);
            EditorGUI.ProgressBar(barRect, pct, barText);

            if (!string.IsNullOrEmpty(statusMessage))
            {
                EditorGUILayout.HelpBox(statusMessage, statusSeverity);
            }

            float maxLogHeight = Mathf.Max(MinLogHeight + 48f, windowHeight - 250f);
            _logHeight = DrawLogResizeSplitter(maxLogHeight, onRepaintRequested);

            EditorGUILayout.BeginHorizontal();
            EditorGUILayout.LabelField(Vrc2GtavLocalization.Get(langMode, "sec.logs"), EditorStyles.boldLabel, GUILayout.MinWidth(90f));
            GUILayout.FlexibleSpace();
            _autoScrollLogs = GUILayout.Toggle(_autoScrollLogs, "Auto-scroll", GUILayout.Width(84f));
            if (GUILayout.Button(Vrc2GtavLocalization.Get(langMode, "btn.copy_logs"), GUILayout.MaxWidth(95f)))
            {
                EditorGUIUtility.systemCopyBuffer = runner.GetCombinedLogs();
            }
            if (GUILayout.Button(Vrc2GtavLocalization.Get(langMode, "btn.clear_logs"), GUILayout.MaxWidth(72f)))
            {
                runner.ClearLogs();
                _lastSeenLogCount = 0;
            }
            if (GUILayout.Button(Vrc2GtavLocalization.Get(langMode, "btn.open_logs"), GUILayout.MaxWidth(122f)))
            {
                if (Vrc2GtavConfigDiscovery.IsValidRepoRoot(repoRoot))
                {
                    string workRoot = Vrc2GtavConfigDiscovery.GetUnityWorkRootIfBundled(repoRoot);
                    string logsDir = Path.Combine(string.IsNullOrEmpty(workRoot) ? repoRoot : workRoot, "logs");
                    Directory.CreateDirectory(logsDir);
                    EditorUtility.RevealInFinder(logsDir);
                }
            }
            EditorGUILayout.EndHorizontal();

            if (_autoScrollLogs && runner.LogLines.Count != _lastSeenLogCount)
            {
                _lastSeenLogCount = runner.LogLines.Count;
                _logScroll.y = float.MaxValue;
            }

            float clampedHeight = Mathf.Clamp(_logHeight, MinLogHeight, maxLogHeight);
            _logScroll = EditorGUILayout.BeginScrollView(_logScroll, GUILayout.Height(clampedHeight));
            EditorGUILayout.TextArea(runner.GetCombinedLogs(), _logAreaStyle, GUILayout.ExpandHeight(true));
            EditorGUILayout.EndScrollView();
        }

        private float DrawLogResizeSplitter(float maxLogHeight, System.Action onRepaintRequested)
        {
            Rect splitRect = GUILayoutUtility.GetRect(0f, 8f, GUILayout.ExpandWidth(true));
            EditorGUIUtility.AddCursorRect(splitRect, MouseCursor.ResizeVertical);
            Event evt = Event.current;
            bool isHover = splitRect.Contains(evt.mousePosition);
            if (evt.type == EventType.Repaint)
            {
                Color lineCol = _isResizingLogs
                    ? new Color(0.35f, 0.68f, 1.0f, 0.95f)
                    : (isHover ? new Color(0.75f, 0.78f, 0.84f, 0.70f) : new Color(0.55f, 0.57f, 0.62f, 0.35f));
                Rect lineRect = new Rect(splitRect.x, splitRect.y + 3f, splitRect.width, 2f);
                EditorGUI.DrawRect(lineRect, lineCol);
                float gripW = Mathf.Min(44f, splitRect.width * 0.25f);
                Rect gripRect = new Rect(splitRect.center.x - gripW * 0.5f, splitRect.y + 2f, gripW, 4f);
                EditorGUI.DrawRect(gripRect, lineCol);
            }

            if (evt.type == EventType.MouseDown && evt.button == 0 && isHover)
            {
                _isResizingLogs = true;
                _dragStartScreenY = GUIUtility.GUIToScreenPoint(evt.mousePosition).y;
                _dragStartHeight = _logHeight;
                evt.Use();
            }
            else if (_isResizingLogs && evt.type == EventType.MouseDrag)
            {
                float curScreenY = GUIUtility.GUIToScreenPoint(evt.mousePosition).y;
                float deltaUp = _dragStartScreenY - curScreenY;
                _logHeight = Mathf.Clamp(_dragStartHeight + deltaUp, MinLogHeight, maxLogHeight);
                onRepaintRequested?.Invoke();
                evt.Use();
            }
            else if (_isResizingLogs && (evt.type == EventType.MouseUp || evt.rawType == EventType.MouseUp))
            {
                _isResizingLogs = false;
                EditorPrefs.SetFloat(LogHeightPrefKey, _logHeight);
                onRepaintRequested?.Invoke();
                if (evt.type == EventType.MouseUp) evt.Use();
            }

            return _logHeight;
        }

        public static void DrawStatusBadge(string text, bool ok)
        {
            Color prev = GUI.contentColor;
            GUI.contentColor = ok ? new Color(0.45f, 0.92f, 0.55f) : new Color(1.0f, 0.45f, 0.40f);
            string badgeTxt = "[" + text + "]";
            float calcW = EditorStyles.miniBoldLabel.CalcSize(new GUIContent(badgeTxt)).x + 6f;
            GUILayout.Label(badgeTxt, EditorStyles.miniBoldLabel, GUILayout.Width(Mathf.Clamp(calcW, 42f, 128f)));
            GUI.contentColor = prev;
        }

        public static string DrawPathBrowseRow(
            string label, string current, string badge, bool ok, bool isFolder, string ext, string browseText, string fallbackDir)
        {
            EditorGUILayout.BeginHorizontal();
            string updated = EditorGUILayout.TextField(new GUIContent(label, label), current ?? string.Empty, GUILayout.MinWidth(80f));
            if (!string.IsNullOrEmpty(badge)) DrawStatusBadge(badge, ok);
            if (GUILayout.Button(browseText, GUILayout.Width(72f)))
            {
                string seedDir = string.IsNullOrEmpty(updated) ? fallbackDir : updated;
                string chosen = isFolder
                    ? EditorUtility.OpenFolderPanel(label, updated, string.Empty)
                    : EditorUtility.OpenFilePanel(label, seedDir, ext);
                if (!string.IsNullOrEmpty(chosen)) updated = chosen.Replace('/', '\\');
            }
            EditorGUILayout.EndHorizontal();
            return updated;
        }

        public static string DrawAnimClipOverrideRow(
            string label, string currentPath, ref AnimationClip cachedClip, string browseText, string fallbackDir, GUIStyle wrapMiniStyle)
        {
            if (!string.IsNullOrWhiteSpace(currentPath) && cachedClip == null)
            {
                string rel = Vrc2GtavAvatarResolver.ToAssetRelativePath(currentPath);
                if (!string.IsNullOrEmpty(rel)) cachedClip = AssetDatabase.LoadAssetAtPath<AnimationClip>(rel);
            }
            EditorGUILayout.BeginHorizontal();
            AnimationClip nextClip = (AnimationClip)EditorGUILayout.ObjectField(
                new GUIContent(label, currentPath), cachedClip, typeof(AnimationClip), false, GUILayout.MinWidth(90f));
            if (nextClip != cachedClip)
            {
                cachedClip = nextClip;
                string assetPath = nextClip != null ? AssetDatabase.GetAssetPath(nextClip) : string.Empty;
                currentPath = !string.IsNullOrEmpty(assetPath)
                    ? Vrc2GtavAvatarResolver.ToAbsoluteProjectPath(assetPath).Replace('/', '\\')
                    : string.Empty;
            }
            if (GUILayout.Button(browseText, GUILayout.Width(72f)))
            {
                string seedDir = string.IsNullOrEmpty(currentPath) ? fallbackDir : currentPath;
                string chosen = EditorUtility.OpenFilePanel(label, seedDir, "anim");
                if (!string.IsNullOrEmpty(chosen))
                {
                    currentPath = chosen.Replace('/', '\\');
                    string rel = Vrc2GtavAvatarResolver.ToAssetRelativePath(currentPath);
                    cachedClip = !string.IsNullOrEmpty(rel) ? AssetDatabase.LoadAssetAtPath<AnimationClip>(rel) : null;
                }
            }
            using (new EditorGUI.DisabledScope(string.IsNullOrWhiteSpace(currentPath)))
            {
                if (GUILayout.Button("X", GUILayout.Width(24f)))
                {
                    currentPath = string.Empty;
                    cachedClip = null;
                }
            }
            EditorGUILayout.EndHorizontal();
            if (!string.IsNullOrWhiteSpace(currentPath) && cachedClip == null && wrapMiniStyle != null)
            {
                GUILayout.Label(currentPath, wrapMiniStyle, GUILayout.ExpandWidth(true));
            }
            return currentPath ?? string.Empty;
        }

        public static UiLanguageMode DrawHeaderBox(
            UiLanguageMode langMode,
            GUIStyle wrapTitleStyle,
            GUIStyle wrapMiniStyle)
        {
            EditorGUILayout.BeginVertical(EditorStyles.helpBox);
            EditorGUILayout.BeginHorizontal();
            EditorGUILayout.BeginVertical(GUILayout.ExpandWidth(true));
            GUILayout.Label(Vrc2GtavLocalization.Get(langMode, "window.title"), wrapTitleStyle, GUILayout.ExpandWidth(true));
            GUILayout.Label(Vrc2GtavLocalization.Get(langMode, "window.subtitle"), wrapMiniStyle, GUILayout.ExpandWidth(true));
            EditorGUILayout.EndVertical();

            EditorGUILayout.BeginHorizontal(GUILayout.Width(172f));
            GUILayout.Label(Vrc2GtavLocalization.Get(langMode, "lang.label"), GUILayout.Width(58f));
            string[] langNames = { Vrc2GtavLocalization.Get(langMode, "lang.auto"), "Português", "English", "日本語" };
            var nextLang = (UiLanguageMode)EditorGUILayout.Popup((int)langMode, langNames, GUILayout.Width(106f));
            EditorGUILayout.EndHorizontal();
            EditorGUILayout.EndHorizontal();
            EditorGUILayout.EndVertical();
            return nextLang;
        }

        public static void DrawToolActionBar(
            bool isRunning,
            UiLanguageMode langMode,
            System.Action onAutoDetect,
            System.Action onDownloadSetup,
            System.Action onCheckEnv)
        {
            EditorGUILayout.Space(4f);
            using (new EditorGUI.DisabledScope(isRunning))
            {
                bool narrow = EditorGUIUtility.currentViewWidth < 560f;
                EditorGUILayout.BeginHorizontal();
                if (GUILayout.Button(Vrc2GtavLocalization.Get(langMode, "tools.autodetect"), GUILayout.Height(26f)))
                {
                    onAutoDetect?.Invoke();
                }
                if (!narrow && GUILayout.Button(Vrc2GtavLocalization.Get(langMode, "tools.download_setup"), GUILayout.Height(26f)))
                {
                    onDownloadSetup?.Invoke();
                }
                if (GUILayout.Button(Vrc2GtavLocalization.Get(langMode, "tools.check_env"), GUILayout.Height(26f)))
                {
                    onCheckEnv?.Invoke();
                }
                EditorGUILayout.EndHorizontal();
                if (narrow && GUILayout.Button(Vrc2GtavLocalization.Get(langMode, "tools.download_setup"), GUILayout.Height(26f)))
                {
                    onDownloadSetup?.Invoke();
                }
            }
        }

        public static void DrawGtavRuntimeStatusBox(GtavRuntimeStatus status, UiLanguageMode langMode)
        {
            if (!status.ValidGtav) return;

            EditorGUILayout.Space(3f);
            EditorGUILayout.LabelField(Vrc2GtavLocalization.Get(langMode, "runtime.header"), EditorStyles.miniBoldLabel);
            bool narrow = EditorGUIUtility.currentViewWidth < 540f;
            EditorGUILayout.BeginHorizontal();
            DrawCompactPill("dinput8.dll", status.AsiLoaderOk);
            DrawCompactPill("PhysBones.asi", status.PhysBonesOk);
            DrawCompactPill("VToon.asi", status.VToonOk);
            if (narrow)
            {
                EditorGUILayout.EndHorizontal();
                EditorGUILayout.BeginHorizontal();
            }
            DrawCompactPill("ScriptHookV.dll", status.ScriptHookVOk);
            DrawCompactPill(status.ModsReaderOk ? status.ModsReaderName : "OpenIV.asi", status.ModsReaderOk);
            EditorGUILayout.EndHorizontal();

            if (!status.AsiLoaderOk || !status.PhysBonesOk || !status.VToonOk)
            {
                EditorGUILayout.HelpBox(Vrc2GtavLocalization.Get(langMode, "runtime.missing_auto"), MessageType.Info);
            }

            if (!status.ScriptHookVOk || !status.ModsReaderOk)
            {
                EditorGUILayout.HelpBox(Vrc2GtavLocalization.Get(langMode, "runtime.missing_thirdparty"), MessageType.Warning);
                EditorGUILayout.BeginHorizontal();
                if (!status.ScriptHookVOk
                    && GUILayout.Button(Vrc2GtavLocalization.Get(langMode, "runtime.get_scripthookv"), GUILayout.Height(22f)))
                {
                    Application.OpenURL("https://www.dev-c.com/gtav/scripthookv/");
                }
                if (!status.ModsReaderOk
                    && GUILayout.Button(Vrc2GtavLocalization.Get(langMode, "runtime.get_openiv"), GUILayout.Height(22f)))
                {
                    Application.OpenURL("https://openiv.com/");
                }
                EditorGUILayout.EndHorizontal();
            }
        }

        private static void DrawCompactPill(string label, bool ok)
        {
            Color prev = GUI.contentColor;
            GUI.contentColor = ok ? new Color(0.45f, 0.92f, 0.55f) : new Color(1.0f, 0.55f, 0.40f);
            GUILayout.Label((ok ? "[OK] " : "[!] ") + label, EditorStyles.miniLabel);
            GUI.contentColor = prev;
        }
    }

    internal static class Vrc2GtavMultiSlotSync
    {
        public static ResolvedAvatarSource CloneSource(ResolvedAvatarSource src)
        {
            if (src == null) return new ResolvedAvatarSource();
            return new ResolvedAvatarSource
            {
                Kind = src.Kind,
                AvatarName = src.AvatarName,
                SourcePath = src.SourcePath,
                SceneAssetPath = src.SceneAssetPath,
                IsSceneDirty = src.IsSceneDirty,
                ObjectRef = src.ObjectRef
            };
        }

        public static void SyncFirstSlotFromMain(
            System.Collections.Generic.IList<ProtagonistAvatarSlot> slots,
            Vrc2GtavExportOptions opts,
            ResolvedAvatarSource mainAvatar,
            AnimationClip mainFaceAnimClip = null)
        {
            var enabled = Vrc2GtavMultiSlotUi.GetEnabledSlots(slots, opts);
            if (enabled.Count == 0 || mainAvatar == null || !mainAvatar.IsValid) return;
            ProtagonistAvatarSlot first = enabled[0];
            if (!first.Avatar.IsValid) first.Avatar = CloneSource(mainAvatar);
            if (string.IsNullOrWhiteSpace(first.AvatarNameOverride) && !string.IsNullOrWhiteSpace(opts?.AvatarNameOverride))
                first.AvatarNameOverride = opts.AvatarNameOverride;
            if (string.IsNullOrWhiteSpace(first.FaceBlendshapesAnim) && !string.IsNullOrWhiteSpace(opts?.FaceBlendshapesAnim))
            {
                first.FaceBlendshapesAnim = opts.FaceBlendshapesAnim;
                first.FaceAnimClip = mainFaceAnimClip;
            }
        }

        public static ResolvedAvatarSource SyncMainFromFirstValidSlot(
            System.Collections.Generic.IList<ProtagonistAvatarSlot> slots,
            Vrc2GtavExportOptions opts,
            ResolvedAvatarSource mainAvatar,
            ref AnimationClip mainFaceAnimClip)
        {
            var enabled = Vrc2GtavMultiSlotUi.GetEnabledSlots(slots, opts);
            for (int i = 0; i < enabled.Count; i++)
            {
                if (!enabled[i].Avatar.IsValid) continue;
                ProtagonistAvatarSlot slot = enabled[i];
                if (opts != null)
                {
                    if (!string.IsNullOrWhiteSpace(slot.AvatarNameOverride)) opts.AvatarNameOverride = slot.AvatarNameOverride;
                    if (!string.IsNullOrWhiteSpace(slot.FaceBlendshapesAnim))
                    {
                        opts.FaceBlendshapesAnim = slot.FaceBlendshapesAnim;
                        mainFaceAnimClip = slot.FaceAnimClip;
                    }
                }
                return CloneSource(slot.Avatar);
            }
            return mainAvatar ?? new ResolvedAvatarSource();
        }

        public static ResolvedAvatarSource ResolvePreviewAvatar(
            System.Collections.Generic.IList<ProtagonistAvatarSlot> slots,
            Vrc2GtavExportOptions opts,
            ResolvedAvatarSource mainAvatar)
        {
            if (opts == null || !opts.PerProtagonistSlots) return mainAvatar;
            var enabled = Vrc2GtavMultiSlotUi.GetEnabledSlots(slots, opts);
            for (int i = 0; i < enabled.Count; i++)
                if (enabled[i].Avatar.IsValid) return enabled[i].Avatar;
            return mainAvatar;
        }

        public static bool HasAnySceneSlot(
            System.Collections.Generic.IList<ProtagonistAvatarSlot> slots,
            Vrc2GtavExportOptions opts)
        {
            var enabled = Vrc2GtavMultiSlotUi.GetEnabledSlots(slots, opts);
            for (int i = 0; i < enabled.Count; i++)
                if (enabled[i].Avatar.Kind == AvatarSourceKind.SceneGameObject) return true;
            return false;
        }

        public static void SyncTargetModeAuto(
            int targetCount,
            Vrc2GtavExportOptions opts,
            System.Collections.Generic.IList<ProtagonistAvatarSlot> slots,
            ref ResolvedAvatarSource mainAvatar,
            ref AnimationClip mainFaceAnimClip)
        {
            if (opts == null) return;
            if (targetCount <= 1)
            {
                opts.UserDisabledPerSlotForMulti = false;
                if (opts.PerProtagonistSlots && !opts.UserEnabledPerSlotForSingle)
                {
                    mainAvatar = SyncMainFromFirstValidSlot(slots, opts, mainAvatar, ref mainFaceAnimClip);
                    opts.PerProtagonistSlots = false;
                }
            }
            else if (!opts.PerProtagonistSlots && !opts.UserDisabledPerSlotForMulti)
            {
                SyncFirstSlotFromMain(slots, opts, mainAvatar, mainFaceAnimClip);
                opts.PerProtagonistSlots = true;
            }
        }

        public static void ApplyPerSlotToggle(
            bool nextPerSlot,
            int targetCount,
            Vrc2GtavExportOptions opts,
            System.Collections.Generic.IList<ProtagonistAvatarSlot> slots,
            ref ResolvedAvatarSource mainAvatar,
            ref AnimationClip mainFaceAnimClip)
        {
            if (opts == null) return;
            if (nextPerSlot != opts.PerProtagonistSlots)
            {
                if (nextPerSlot)
                {
                    SyncFirstSlotFromMain(slots, opts, mainAvatar, mainFaceAnimClip);
                    opts.UserDisabledPerSlotForMulti = false;
                    if (targetCount <= 1) opts.UserEnabledPerSlotForSingle = true;
                }
                else
                {
                    mainAvatar = SyncMainFromFirstValidSlot(slots, opts, mainAvatar, ref mainFaceAnimClip);
                    opts.UserEnabledPerSlotForSingle = false;
                    if (targetCount >= 2) opts.UserDisabledPerSlotForMulti = true;
                }
            }
            opts.PerProtagonistSlots = nextPerSlot;
        }
    }
}
