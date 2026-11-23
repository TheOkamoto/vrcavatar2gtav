using System.Collections.Generic;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Vrc2Gtav.Editor
{
    public sealed class Vrc2GtavExporterWindow : EditorWindow
    {
        private const string PrefPrefix = "Vrc2Gtav.Exporter.";

        private readonly Vrc2GtavProcessRunner _runner = new Vrc2GtavProcessRunner();
        private readonly Vrc2GtavLogConsoleWidget _logWidget = new Vrc2GtavLogConsoleWidget();
        private readonly Vrc2GtavTexturesPanel _texturesPanel = new Vrc2GtavTexturesPanel();
        private readonly Vrc2GtavExportOptions _options = new Vrc2GtavExportOptions();
        private Vrc2GtavToolPaths _paths = new Vrc2GtavToolPaths();
        private ResolvedAvatarSource _avatar = new ResolvedAvatarSource();
        private readonly List<ProtagonistAvatarSlot> _protagonistSlots = Vrc2GtavMultiSlotUi.CreateDefaultSlots();
        private GtavRuntimeStatus _runtimeStatus;
        private string _lastRuntimeGtavPath = string.Empty;

        private UiLanguageMode _langMode = UiLanguageMode.Auto;
        private bool _autoSaveScene = true;
        private bool _showAdvanced;
        private bool _showCliPreview;
        private bool _showToolDetails;
        private Vector2 _mainScroll;
        private string _statusMessage = string.Empty;
        private MessageType _statusSeverity = MessageType.Info;
        private GUIStyle _dropBoxStyle;
        private GUIStyle _wrapMiniLabelStyle;
        private GUIStyle _wrapTitleStyle;
        private AnimationClip _faceAnimClip;

        [MenuItem("Tools/VRCAvatar2GTAV/Export Avatar to GTA V")]
        public static void ShowWindow()
        {
            var win = GetWindow<Vrc2GtavExporterWindow>();
            win.minSize = new Vector2(480f, 540f);
            win.titleContent = new GUIContent(Vrc2GtavLocalization.Get(win._langMode, "window.title"));
            win.Show();
        }

        private void OnEnable()
        {
            minSize = new Vector2(480f, 540f);
            LoadPrefs();
            _paths = Vrc2GtavConfigDiscovery.AutoDetectAll(_paths);
            SavePrefs();
            RefreshRuntimeStatus(true);
            UpdateToolDetailsVisibility();
            titleContent = new GUIContent(T("window.title"));
        }

        private void OnFocus() => RefreshRuntimeStatus(true);

        private void OnDisable()
        {
            SavePrefs();
            _runner.Dispose();
        }

        private void OnGUI()
        {
            if (_dropBoxStyle == null)
            {
                _dropBoxStyle = new GUIStyle(EditorStyles.helpBox)
                {
                    alignment = TextAnchor.MiddleCenter,
                    wordWrap = true,
                    fontStyle = FontStyle.Bold
                };
            }
            if (_wrapMiniLabelStyle == null)
            {
                _wrapMiniLabelStyle = new GUIStyle(EditorStyles.miniLabel) { wordWrap = true };
            }
            if (_wrapTitleStyle == null)
            {
                _wrapTitleStyle = new GUIStyle(EditorStyles.boldLabel) { wordWrap = true };
            }

            UiLanguageMode nextLang = Vrc2GtavLogConsoleWidget.DrawHeaderBox(_langMode, _wrapTitleStyle, _wrapMiniLabelStyle);
            if (nextLang != _langMode)
            {
                _langMode = nextLang;
                SavePrefs();
                titleContent = new GUIContent(T("window.title"));
            }

            _mainScroll = EditorGUILayout.BeginScrollView(_mainScroll);
            DrawAvatarSection();
            EditorGUILayout.Space(6f);
            DrawTargetsSection();
            EditorGUILayout.Space(6f);
            float prevLabelWidth = EditorGUIUtility.labelWidth;
            float baseLabelW = Mathf.Clamp(Mathf.Max(340f, position.width - 36f) * 0.44f, 185f, 250f);
            EditorGUIUtility.labelWidth = baseLabelW;
            _texturesPanel.DrawSection(_options, _langMode, _avatar);
            EditorGUILayout.Space(6f);
            DrawOptionsSection(baseLabelW);
            EditorGUILayout.Space(6f);
            DrawToolsSection(baseLabelW);
            EditorGUILayout.Space(4f);
            Vrc2GtavTexturesPanel.DrawRestoreVanillaSection(_langMode, _runner.IsRunning, StartRestoreVanilla);
            EditorGUIUtility.labelWidth = prevLabelWidth;
            EditorGUILayout.EndScrollView();

            EditorGUILayout.Space(6f);
            bool sourceOk = _options.PerProtagonistSlots
                ? Vrc2GtavMultiSlotUi.AreAllEnabledSlotsValid(_protagonistSlots, _options)
                : _avatar.IsValid;
            ExecutionCommandSpec previewSpec = sourceOk ? BuildCurrentExportSpec(false) : default(ExecutionCommandSpec);
            bool hasExportError = sourceOk && previewSpec.HasValidationError;
            bool canStart = !_runner.IsRunning
                && sourceOk
                && !hasExportError
                && Vrc2GtavCommandBuilder.HasAnyTarget(_options)
                && Vrc2GtavConfigDiscovery.IsValidRepoRoot(_paths.RepoRoot)
                && Vrc2GtavConfigDiscovery.IsValidGtavRoot(_paths.GtavRoot)
                && Vrc2GtavConfigDiscovery.IsValidPython(_paths.PythonExe, _paths.BackendMode, out _);

            _logWidget.Draw(
                _runner,
                _langMode,
                _paths.RepoRoot,
                _statusMessage,
                _statusSeverity,
                canStart,
                StartAvatarExport);
        }

        private void DrawAvatarSection()
        {
            EditorGUILayout.BeginVertical(EditorStyles.helpBox);
            EditorGUILayout.LabelField(T("sec.avatar"), EditorStyles.boldLabel);

            Rect dropRect = GUILayoutUtility.GetRect(0f, 44f, GUILayout.ExpandWidth(true));
            GUI.Box(dropRect, T("avatar.drop_hint"), _dropBoxStyle);
            _avatar = Vrc2GtavAvatarResolver.HandleDragAndDrop(dropRect, _avatar);

            UnityEngine.Object picked = EditorGUILayout.ObjectField(
                T("avatar.object_field"), _avatar.ObjectRef, typeof(UnityEngine.Object), true);
            if (picked != _avatar.ObjectRef)
            {
                _avatar = Vrc2GtavAvatarResolver.ResolveObject(picked);
            }
            EditorGUILayout.BeginHorizontal();
            if (GUILayout.Button(T("avatar.scene_picker"), GUILayout.ExpandWidth(true)))
            {
                Vrc2GtavAvatarResolver.ShowSceneAvatarMenu(T("avatar.none"), selected =>
                {
                    _avatar = selected;
                    Repaint();
                });
            }
            if (GUILayout.Button(T("avatar.browse_file"), GUILayout.ExpandWidth(true)))
            {
                string pickedFile = EditorUtility.OpenFilePanel(
                    T("avatar.browse_file"), Vrc2GtavConfigDiscovery.GetUnityProjectRoot(), "zip,unitypackage,prefab,unity");
                if (!string.IsNullOrEmpty(pickedFile)) _avatar = Vrc2GtavAvatarResolver.ResolveExternalPath(pickedFile);
            }
            EditorGUILayout.EndHorizontal();

            if (_avatar.Kind == AvatarSourceKind.SceneGameObject && _avatar.ObjectRef is GameObject go)
            {
                _avatar.IsSceneDirty = go.scene.IsValid() && go.scene.isDirty;
            }

            if (_avatar.IsValid)
            {
                EditorGUILayout.LabelField(T("avatar.resolved_name"), _avatar.AvatarName);
                GUILayout.Label(T("avatar.resolved_source") + ": " + _avatar.SourcePath, _wrapMiniLabelStyle, GUILayout.ExpandWidth(true));
            }
            else
            {
                EditorGUILayout.HelpBox(T("avatar.none"), MessageType.None);
            }

            if (_avatar.Kind == AvatarSourceKind.SceneGameObject)
            {
                _autoSaveScene = EditorGUILayout.ToggleLeft(T("avatar.autosave_scene"), _autoSaveScene);
                if (_avatar.IsSceneDirty)
                {
                    EditorGUILayout.BeginHorizontal();
                    EditorGUILayout.HelpBox(T("avatar.dirty_warning"), MessageType.Warning);
                    if (GUILayout.Button(T("avatar.save_scene_now"), GUILayout.Width(135f), GUILayout.Height(36f)))
                    {
                        Vrc2GtavMultiSlotUi.SaveAllDirtyAvatarScenes(_avatar, _protagonistSlots, true);
                    }
                    EditorGUILayout.EndHorizontal();
                }
            }
            EditorGUILayout.EndVertical();
        }

        private void DrawTargetsSection()
        {
            EditorGUILayout.BeginVertical(EditorStyles.helpBox);
            EditorGUILayout.LabelField(T("sec.targets"), EditorStyles.boldLabel);
            _options.TargetMichael = EditorGUILayout.ToggleLeft(T("target.michael"), _options.TargetMichael);
            _options.TargetFranklin = EditorGUILayout.ToggleLeft(T("target.franklin"), _options.TargetFranklin);
            _options.TargetTrevor = EditorGUILayout.ToggleLeft(T("target.trevor"), _options.TargetTrevor);
            int targetCount = Vrc2GtavCommandBuilder.CountSelectedTargets(_options);
            if (targetCount <= 1) _options.UserDisabledPerSlotForMulti = false;
            else if (!_options.PerProtagonistSlots && !_options.UserDisabledPerSlotForMulti)
            {
                _options.PerProtagonistSlots = true;
            }
            bool nextPerSlot = EditorGUILayout.ToggleLeft(T("target.per_slot_toggle"), _options.PerProtagonistSlots);
            if (!nextPerSlot && targetCount >= 2) _options.UserDisabledPerSlotForMulti = true;
            else if (nextPerSlot) _options.UserDisabledPerSlotForMulti = false;
            _options.PerProtagonistSlots = nextPerSlot;
            if (_options.PerProtagonistSlots)
            {
                Vrc2GtavMultiSlotUi.SyncFirstSlotFromMain(_protagonistSlots, _options, _avatar, _faceAnimClip);
                Vrc2GtavMultiSlotUi.DrawPerProtagonistSlots(
                    _langMode, _options, _protagonistSlots, _avatar, _dropBoxStyle, _wrapMiniLabelStyle,
                    () => Vrc2GtavMultiSlotUi.SaveAllDirtyAvatarScenes(_avatar, _protagonistSlots, true), Repaint);
            }
            if (!Vrc2GtavCommandBuilder.HasAnyTarget(_options))
                EditorGUILayout.HelpBox(T("target.none_err"), MessageType.Error);
            EditorGUILayout.EndVertical();
        }

        private void DrawOptionsSection(float baseLabelW)
        {
            EditorGUILayout.BeginVertical(EditorStyles.helpBox);
            EditorGUILayout.LabelField(T("sec.options"), EditorStyles.boldLabel);
            Vrc2GtavTexturesPanel.DrawBlendshapeAndRigOptions(
                _options, _langMode, baseLabelW, ref _showAdvanced, ref _faceAnimClip, ref _showCliPreview,
                _paths, _paths.BackendMode, _wrapMiniLabelStyle, DrawMouthOpenRow, () => BuildCurrentExportSpec(false), OnBackendModeChanged);
            EditorGUILayout.EndVertical();
        }

        private void DrawMouthOpenRow()
        {
            EditorGUILayout.BeginHorizontal();
            float nextMouthOpen = EditorGUILayout.Slider(T("opt.mouth_open"), _options.MouthOpenStrength, 0f, 1f);
            _options.MouthOpenStrength = Mathf.Round(Mathf.Clamp01(nextMouthOpen) * 100f) / 100f;
            if (GUILayout.Button("0.35", GUILayout.Width(44f))) _options.MouthOpenStrength = 0.35f;
            EditorGUILayout.EndHorizontal();
        }

        private void DrawToolsSection(float baseLabelW)
        {
            EditorGUILayout.BeginVertical(EditorStyles.helpBox);
            EditorGUILayout.LabelField(T("sec.tools"), EditorStyles.boldLabel);

            bool gtavOk = Vrc2GtavConfigDiscovery.IsValidGtavRoot(_paths.GtavRoot);
            bool repoOk = Vrc2GtavConfigDiscovery.IsValidRepoRoot(_paths.RepoRoot);
            bool blenderOk = Vrc2GtavConfigDiscovery.IsValidBlender(_paths.BlenderExe);
            bool sollumzOk = Vrc2GtavConfigDiscovery.HasSollumzInstalled(_paths.BlenderExe);
            bool rageOk = Vrc2GtavConfigDiscovery.IsValidRage(_paths.RageExe, _paths.BackendMode);
            bool pythonOk = Vrc2GtavConfigDiscovery.IsValidPython(_paths.PythonExe, _paths.BackendMode, out _);

            _paths.GtavRoot = DrawPathBrowseRow(T("tools.gtav_root"), _paths.GtavRoot, gtavOk ? T("tools.status_ok") : T("tools.status_missing"), gtavOk, true, string.Empty);
            RefreshRuntimeStatus(false);
            string bundledRepo = Vrc2GtavConfigDiscovery.GetBundledToolchainRoot();
            string nextRepoRoot = DrawPathBrowseRow(T("tools.repo_root"), _paths.RepoRoot, repoOk ? T("tools.status_ok") : T("tools.status_missing"), repoOk, true, string.Empty);
            if (!string.Equals(nextRepoRoot?.TrimEnd('\\', '/'), _paths.RepoRoot?.TrimEnd('\\', '/'), System.StringComparison.OrdinalIgnoreCase))
            {
                _paths.RepoRoot = nextRepoRoot;
                _paths.RepoRootManualOverride = !string.Equals(nextRepoRoot?.TrimEnd('\\', '/'), bundledRepo.TrimEnd('\\', '/'), System.StringComparison.OrdinalIgnoreCase);
                Vrc2GtavConfigDiscovery.ClearValidationCache();
                SavePrefs();
            }
            if (Vrc2GtavConfigDiscovery.IsValidRepoRoot(bundledRepo)
                && !string.Equals(_paths.RepoRoot?.TrimEnd('\\', '/'), bundledRepo.TrimEnd('\\', '/'), System.StringComparison.OrdinalIgnoreCase))
            {
                if (GUILayout.Button(new GUIContent(T("tools.use_bundled"), bundledRepo), EditorStyles.miniButton))
                {
                    _paths.RepoRootManualOverride = false;
                    _paths.RepoRoot = bundledRepo;
                    _paths.RageExe = string.Empty;
                    Vrc2GtavConfigDiscovery.ClearValidationCache();
                    _paths = Vrc2GtavConfigDiscovery.AutoDetectAll(_paths);
                    SavePrefs();
                }
            }
            Vrc2GtavLogConsoleWidget.DrawGtavRuntimeStatusBox(_runtimeStatus, _langMode);

            _showToolDetails = EditorGUILayout.Foldout(_showToolDetails, T("tools.details"), true);
            if (_showToolDetails)
            {
                EditorGUI.indentLevel++;
                EditorGUIUtility.labelWidth = baseLabelW + 18f;
                string blenderBadge = !blenderOk ? T("tools.status_missing") : (sollumzOk ? "Sollumz OK" : T("tools.status_no_sollumz"));
                _paths.BlenderExe = DrawPathBrowseRow(T("tools.blender"), _paths.BlenderExe, blenderBadge, blenderOk && sollumzOk, false, "exe");
                _paths.RageExe = DrawPathBrowseRow(T("tools.rage"), _paths.RageExe, rageOk ? T("tools.status_ok") : T("tools.status_missing"), rageOk, false, "exe");
                _paths.PythonExe = DrawPathBrowseRow(T("tools.python"), _paths.PythonExe, pythonOk ? T("tools.status_ok") : T("tools.status_missing"), pythonOk, false, "exe");
                GUILayout.Label("Unity Assets: " + Vrc2GtavConfigDiscovery.GetDefaultUnityAssetsPath(), _wrapMiniLabelStyle, GUILayout.ExpandWidth(true));
                EditorGUIUtility.labelWidth = baseLabelW;
                EditorGUI.indentLevel--;
            }

            Vrc2GtavLogConsoleWidget.DrawToolActionBar(
                _runner.IsRunning,
                _langMode,
                () =>
                {
                    Vrc2GtavConfigDiscovery.ClearValidationCache();
                    _paths = Vrc2GtavConfigDiscovery.AutoDetectAll(new Vrc2GtavToolPaths
                    {
                        BackendMode = _paths.BackendMode
                    });
                    SavePrefs();
                    UpdateToolDetailsVisibility();
                },
                StartDownloadAndSetup,
                StartCheckEnv);
            EditorGUILayout.EndVertical();
        }

        private ExecutionCommandSpec BuildCurrentExportSpec(bool writeManifest)
        {
            var texOverrides = _texturesPanel.BuildTextureOverridesMap();
            if (_options.PerProtagonistSlots)
            {
                var enabled = Vrc2GtavMultiSlotUi.GetEnabledSlots(_protagonistSlots, _options);
                return Vrc2GtavCommandBuilder.BuildMultiSlotExportCommand(_paths, enabled, _options, _langMode, texOverrides, writeManifest);
            }
            return Vrc2GtavCommandBuilder.BuildExportCommand(_paths, _avatar, _options, _langMode, texOverrides);
        }

        private void StartAvatarExport()
        {
            SaveAllDirtyAvatarScenes();
            SavePrefs();
            Vrc2GtavConfigDiscovery.SaveToConfig(_paths.RepoRoot, _paths, Vrc2GtavLocalization.ToCliLanguageArg(_langMode));
            var step = new ProcessStepRequest
            {
                StepTitle = T("btn.start") + " (" + Vrc2GtavCommandBuilder.BuildTargetPedCsv(_options) + ")",
                Command = BuildCurrentExportSpec(true)
            };
            LaunchQueue(new[] { step }, false);
        }

        private void StartRestoreVanilla(string pedCsvOrAll, string btnLabel)
        {
            if (!Vrc2GtavConfigDiscovery.IsValidRepoRoot(_paths.RepoRoot) || !Vrc2GtavConfigDiscovery.IsValidGtavRoot(_paths.GtavRoot)
                || !Vrc2GtavConfigDiscovery.IsValidPython(_paths.PythonExe, _paths.BackendMode, out _))
            {
                SetStatus(T("tools.gtav_root") + ": " + T("tools.status_missing"), MessageType.Error);
                return;
            }
            if (!EditorUtility.DisplayDialog(T("restore.confirm_title"), Vrc2GtavLocalization.Format(_langMode, "restore.confirm_msg", btnLabel), btnLabel, T("btn.cancel")))
                return;
            SavePrefs();
            Vrc2GtavConfigDiscovery.SaveToConfig(_paths.RepoRoot, _paths, Vrc2GtavLocalization.ToCliLanguageArg(_langMode));
            var step = new ProcessStepRequest { StepTitle = btnLabel, Command = Vrc2GtavCommandBuilder.BuildRestoreCommand(_paths, _langMode, pedCsvOrAll) };
            LaunchQueue(new[] { step }, false);
        }

        private void StartCheckEnv()
        {
            if (!Vrc2GtavConfigDiscovery.IsValidRepoRoot(_paths.RepoRoot))
            {
                SetStatus(T("tools.repo_root") + ": " + T("tools.status_missing"), MessageType.Error);
                return;
            }
            SavePrefs();
            var args = new List<string> { "--check-env", "--lang", Vrc2GtavLocalization.ToCliLanguageArg(_langMode) };
            var step = new ProcessStepRequest
            {
                StepTitle = T("tools.check_env"),
                Command = Vrc2GtavCommandBuilder.BuildExecutionSpec(_paths, _paths.BackendMode, "run_mod_manager.py", args)
            };
            LaunchQueue(new[] { step }, false);
        }

        private void StartDownloadAndSetup()
        {
            if (!Vrc2GtavConfigDiscovery.IsValidRepoRoot(_paths.RepoRoot))
            {
                SetStatus(T("tools.repo_root") + ": " + T("tools.status_missing"), MessageType.Error);
                return;
            }
            SavePrefs();
            bool hasGtav = Vrc2GtavConfigDiscovery.IsValidGtavRoot(_paths.GtavRoot);
            if (!hasGtav && !EditorUtility.DisplayDialog(T("tools.download_setup"), T("err.need_gtav_for_setup"), T("tools.download_setup"), T("btn.cancel")))
            {
                return;
            }
            LaunchQueue(Vrc2GtavCommandBuilder.BuildDownloadAndSetupSteps(_paths, _langMode, hasGtav), true);
        }

        private void LaunchQueue(IEnumerable<ProcessStepRequest> steps, bool refreshToolsOnComplete)
        {
            var stepList = new List<ProcessStepRequest>(steps);
            for (int i = 0; i < stepList.Count; i++)
            {
                if (stepList[i] != null && stepList[i].Command.HasValidationError)
                {
                    SetStatus(stepList[i].Command.ValidationError, MessageType.Error);
                    return;
                }
            }

            SetStatus(T("status.running"), MessageType.Info);
            _runner.StartQueue(
                stepList,
                () => Repaint(),
                (ok, code) =>
                {
                    if ((refreshToolsOnComplete || !Vrc2GtavConfigDiscovery.IsValidRage(_paths.RageExe, _paths.BackendMode)) && ok)
                    {
                        Vrc2GtavConfigDiscovery.ClearValidationCache();
                        _paths = Vrc2GtavConfigDiscovery.AutoDetectAll(_paths);
                        SavePrefs();
                        UpdateToolDetailsVisibility();
                    }
                    RefreshRuntimeStatus(true);
                    if (_runner.WasCancelled) SetStatus(T("status.cancelled"), MessageType.Warning);
                    else if (ok) SetStatus(T("status.done_ok"), MessageType.Info);
                    else SetStatus(Vrc2GtavLocalization.Format(_langMode, "status.done_err", code), MessageType.Error);
                    Repaint();
                });
        }

        private void SaveAllDirtyAvatarScenes() =>
            Vrc2GtavMultiSlotUi.SaveAllDirtyAvatarScenes(_avatar, _protagonistSlots, _autoSaveScene);

        private string DrawPathBrowseRow(string label, string current, string badge, bool ok, bool isFolder, string ext)
        {
            string updated = Vrc2GtavLogConsoleWidget.DrawPathBrowseRow(label, current, badge, ok, isFolder, ext, T("tools.browse"), _paths.RepoRoot);
            if (updated != (current ?? string.Empty)) SavePrefs();
            return updated;
        }

        private void OnBackendModeChanged(BackendExecutionMode nextMode)
        {
            _paths.BackendMode = nextMode;
            Vrc2GtavConfigDiscovery.ClearValidationCache();
            Vrc2GtavConfigDiscovery.SanitizeToolPathsForMode(_paths);
            if (nextMode == BackendExecutionMode.WindowsNative)
            {
                _options.BlendshapesCfg = Vrc2GtavIniAndWsl.SanitizePathForWindows(_options.BlendshapesCfg);
                _options.FaceBlendshapesAnim = Vrc2GtavIniAndWsl.SanitizePathForWindows(_options.FaceBlendshapesAnim);
                _options.PhysbonesCfg = Vrc2GtavIniAndWsl.SanitizePathForWindows(_options.PhysbonesCfg);
            }
            _paths = Vrc2GtavConfigDiscovery.AutoDetectAll(_paths);
            SavePrefs();
            UpdateToolDetailsVisibility();
        }

        private void RefreshRuntimeStatus(bool force)
        {
            string cur = _paths.GtavRoot ?? string.Empty;
            if (!force && string.Equals(cur, _lastRuntimeGtavPath, System.StringComparison.Ordinal)) return;
            _lastRuntimeGtavPath = cur;
            _runtimeStatus = Vrc2GtavConfigDiscovery.InspectGtavRuntime(cur);
        }

        private void UpdateToolDetailsVisibility()
        {
            bool allReady = Vrc2GtavConfigDiscovery.IsValidBlender(_paths.BlenderExe)
                && Vrc2GtavConfigDiscovery.HasSollumzInstalled(_paths.BlenderExe)
                && Vrc2GtavConfigDiscovery.IsValidRage(_paths.RageExe, _paths.BackendMode)
                && Vrc2GtavConfigDiscovery.IsValidPython(_paths.PythonExe, _paths.BackendMode, out _);
            if (!allReady) _showToolDetails = true;
        }

        private void SetStatus(string msg, MessageType severity)
        {
            _statusMessage = msg;
            _statusSeverity = severity;
        }

        private string T(string key) => Vrc2GtavLocalization.Get(_langMode, key);

        private void LoadPrefs() => Vrc2GtavCommandBuilder.LoadEditorState(PrefPrefix, _paths, out _langMode, out _autoSaveScene, _options);
        private void SavePrefs() => Vrc2GtavCommandBuilder.SaveEditorState(PrefPrefix, _paths, _langMode, _autoSaveScene, _options);
    }
}
