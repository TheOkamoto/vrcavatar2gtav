using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;

namespace Vrc2Gtav.Editor
{
    internal sealed class ProcessStepRequest
    {
        public string StepTitle = string.Empty;
        public ExecutionCommandSpec Command;
    }

    internal sealed class Vrc2GtavProcessRunner : IDisposable
    {
        private const int MaxLogLines = 3500;
        private static readonly Regex ExplicitProgressRegex = new Regex(@"^\[PROGRESS\s+pct=([0-9]+(?:\.[0-9]+)?)\]\s*(.*)$", RegexOptions.Compiled | RegexOptions.CultureInvariant);
        private static readonly Regex StageBannerRegex = new Regex(@"^\[(?:STAGE|ETAPA|段階)\s+(\d+)/(\d+)\][^|]*\|\s*(.+)$", RegexOptions.Compiled);
        private static readonly Regex SubPercentRegex = new Regex(@"(\d{1,3}(?:\.\d+)?)%", RegexOptions.Compiled);
        private static readonly Regex TopLevelStepRegex = new Regex(@"^\s*\[(\d+)/(\d+)\]\s*(.+)$", RegexOptions.Compiled);
        private bool _hasExplicitProgress, _hasSeenBuildProgress;
        private float _deployFloor;
        private int _deployCurStage, _deployTotalStages;
        private string _activeDeployLabel = string.Empty;

        private readonly ConcurrentQueue<string> _pendingLines = new ConcurrentQueue<string>();
        private readonly List<string> _logLines = new List<string>();
        private readonly Queue<ProcessStepRequest> _stepQueue = new Queue<ProcessStepRequest>();
        private readonly object _procLock = new object();

        private Process _activeProcess;
        private Action<bool, int> _onCompleted;
        private Action _onLogChanged;
        private bool _isSubscribed;

        public bool IsRunning { get; private set; }
        public bool WasCancelled { get; private set; }
        public int LastExitCode { get; private set; }
        public float Progress { get; private set; }
        public string StatusLine { get; private set; } = string.Empty;
        public IReadOnlyList<string> LogLines => _logLines;

        public void StartQueue(
            IEnumerable<ProcessStepRequest> steps,
            Action onLogChanged,
            Action<bool, int> onCompleted)
        {
            if (IsRunning) return;

            _stepQueue.Clear();
            foreach (ProcessStepRequest step in steps)
            {
                if (step != null) _stepQueue.Enqueue(step);
            }
            if (_stepQueue.Count == 0) return;

            _onLogChanged = onLogChanged;
            _onCompleted = onCompleted;
            WasCancelled = false;
            LastExitCode = 0;
            Progress = 0.02f;
            _hasExplicitProgress = false;
            _hasSeenBuildProgress = false;
            _deployFloor = 0.04f;
            _deployCurStage = 0;
            _deployTotalStages = 0;
            _activeDeployLabel = string.Empty;
            IsRunning = true;

            EnsureSubscribed();
            LaunchNextStep();
        }

        public void Cancel()
        {
            if (!IsRunning) return;
            WasCancelled = true;
            _stepQueue.Clear();
            EnqueueLog("[CANCEL] Stopping active process...");

            lock (_procLock)
            {
                if (_activeProcess != null)
                {
                    KillProcessTree(_activeProcess);
                }
            }
        }

        public void ClearLogs()
        {
            _logLines.Clear();
            while (_pendingLines.TryDequeue(out _)) { }
            _onLogChanged?.Invoke();
        }

        public string GetCombinedLogs()
        {
            return string.Join(Environment.NewLine, _logLines);
        }

        public void Dispose()
        {
            if (IsRunning) Cancel();
            Unsubscribe();
        }

        private void EnsureSubscribed()
        {
            if (_isSubscribed) return;
            EditorApplication.update += PumpOnMainThread;
            _isSubscribed = true;
        }

        private void Unsubscribe()
        {
            if (!_isSubscribed) return;
            EditorApplication.update -= PumpOnMainThread;
            _isSubscribed = false;
        }

        private void LaunchNextStep()
        {
            if (WasCancelled || _stepQueue.Count == 0)
            {
                FinishQueue(LastExitCode == 0 && !WasCancelled, LastExitCode);
                return;
            }

            ProcessStepRequest next = _stepQueue.Dequeue();
            StatusLine = next.StepTitle;
            EnqueueLog("=== " + next.StepTitle + " ===");
            EnqueueLog("> " + next.Command.PreviewCommand);

            var startInfo = new ProcessStartInfo
            {
                FileName = next.Command.FileName,
                Arguments = next.Command.Arguments,
                WorkingDirectory = string.IsNullOrEmpty(next.Command.WorkingDirectory)
                    ? Directory.GetCurrentDirectory()
                    : next.Command.WorkingDirectory,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8
            };

            startInfo.EnvironmentVariables["PYTHONUTF8"] = "1";
            startInfo.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
            startInfo.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";
            if (next.Command.UsesWsl)
            {
                string existingWslEnv = startInfo.EnvironmentVariables["WSLENV"] ?? string.Empty;
                const string wslAdditions = "PYTHONUTF8/u:PYTHONIOENCODING/u:PYTHONUNBUFFERED/u";
                startInfo.EnvironmentVariables["WSLENV"] = string.IsNullOrEmpty(existingWslEnv)
                    ? wslAdditions
                    : existingWslEnv + ":" + wslAdditions;
            }

            try
            {
                var proc = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
                proc.OutputDataReceived += (_, e) => { if (e.Data != null) EnqueueLog(e.Data); };
                proc.ErrorDataReceived += (_, e) => { if (e.Data != null) EnqueueLog("[ERR] " + e.Data); };

                lock (_procLock)
                {
                    _activeProcess = proc;
                }

                if (!proc.Start())
                {
                    LastExitCode = -1;
                    EnqueueLog("[ERROR] Failed to start: " + next.Command.FileName);
                    FinishQueue(false, -1);
                    return;
                }

                proc.BeginOutputReadLine();
                proc.BeginErrorReadLine();
            }
            catch (Exception ex)
            {
                LastExitCode = -1;
                EnqueueLog("[ERROR] Exception launching process: " + ex.Message);
                FinishQueue(false, -1);
            }
        }

        private void PumpOnMainThread()
        {
            bool changed = false;
            int drained = 0;
            while (drained < 200 && _pendingLines.TryDequeue(out string line))
            {
                drained++;
                changed = true;
                _logLines.Add(line);
                if (_logLines.Count > MaxLogLines)
                {
                    _logLines.RemoveAt(0);
                }
                UpdateProgressFromLogLine(line);
            }

            Process finishedProc = null;
            lock (_procLock)
            {
                if (_activeProcess != null && _activeProcess.HasExited)
                {
                    _activeProcess.WaitForExit();
                    LastExitCode = _activeProcess.ExitCode;
                    finishedProc = _activeProcess;
                    _activeProcess.Dispose();
                    _activeProcess = null;
                }
            }

            if (finishedProc != null)
            {
                while (_pendingLines.TryDequeue(out string tailLine))
                {
                    changed = true;
                    _logLines.Add(tailLine);
                    if (_logLines.Count > MaxLogLines) _logLines.RemoveAt(0);
                }

                if (WasCancelled || LastExitCode != 0)
                {
                    FinishQueue(false, LastExitCode);
                    changed = true;
                }
                else
                {
                    LaunchNextStep();
                    changed = true;
                }
            }

            if (changed)
            {
                _onLogChanged?.Invoke();
            }
        }

        private void FinishQueue(bool success, int exitCode)
        {
            IsRunning = false;
            Progress = success ? 1.0f : Progress;
            Unsubscribe();
            _onCompleted?.Invoke(success, exitCode);
            _onLogChanged?.Invoke();
        }

        private void EnqueueLog(string line)
        {
            _pendingLines.Enqueue(line ?? string.Empty);
        }

        private void UpdateProgressFromLogLine(string line)
        {
            if (string.IsNullOrEmpty(line)) return;
            string trimmed = line.Trim();

            Match pm = ExplicitProgressRegex.Match(trimmed);
            if (pm.Success && float.TryParse(pm.Groups[1].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out float rawPct))
            {
                _hasExplicitProgress = true;
                if (rawPct < 82.0f) _hasSeenBuildProgress = true;
                Progress = Math.Max(Progress, Math.Max(0.01f, Math.Min(0.995f, rawPct / 100f)));
                string statusText = pm.Groups[2].Value.Trim();
                if (!string.IsNullOrEmpty(statusText)) StatusLine = statusText;
                return;
            }

            Match sm = StageBannerRegex.Match(trimmed);
            if (sm.Success && int.TryParse(sm.Groups[1].Value, out int stCur) && int.TryParse(sm.Groups[2].Value, out int stTotal) && stTotal > 0)
            {
                if (_deployTotalStages != stTotal || _deployCurStage == 0) _deployFloor = _hasSeenBuildProgress ? 0.82f : Math.Max(0.04f, Progress);
                _deployCurStage = stCur;
                _deployTotalStages = stTotal;
                string title = sm.Groups[3].Value.Trim();
                int pIdx = title.LastIndexOf('(');
                if (pIdx > 2 && title.EndsWith(")", StringComparison.Ordinal)) title = title.Substring(0, pIdx).Trim();
                _activeDeployLabel = title;
                Progress = Math.Max(Progress, Math.Min(0.985f, _deployFloor + ((float)(stCur - 1) / stTotal) * (0.99f - _deployFloor)));
                StatusLine = title;
                return;
            }

            if (trimmed.StartsWith("[PROGRESS", StringComparison.OrdinalIgnoreCase) || trimmed.StartsWith("[PROGRESSO", StringComparison.OrdinalIgnoreCase) || trimmed.StartsWith("[進捗", StringComparison.Ordinal))
            {
                Progress = Math.Max(Progress, 0.99f);
                StatusLine = trimmed;
                return;
            }

            if (_deployTotalStages > 0)
            {
                Match subM = SubPercentRegex.Match(trimmed);
                if (subM.Success && float.TryParse(subM.Groups[1].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out float subPct))
                {
                    float span = 0.99f - _deployFloor;
                    float s0 = _deployFloor + ((float)(_deployCurStage - 1) / _deployTotalStages) * span;
                    float s1 = _deployFloor + ((float)_deployCurStage / _deployTotalStages) * span;
                    Progress = Math.Max(Progress, Math.Min(0.99f, s0 + Math.Max(0f, Math.Min(1f, subPct / 100f)) * (s1 - s0)));
                    if (!string.IsNullOrEmpty(_activeDeployLabel)) StatusLine = _activeDeployLabel + " (" + ((int)Math.Round(subPct)).ToString(CultureInfo.InvariantCulture) + "%)";
                    return;
                }
            }

            Match m = TopLevelStepRegex.Match(trimmed);
            if (m.Success && int.TryParse(m.Groups[1].Value, out int cur) && int.TryParse(m.Groups[2].Value, out int total) && total > 0)
            {
                if (!_hasExplicitProgress) { Progress = Math.Max(Progress, Math.Min(0.96f, (float)cur / total * 0.9f)); StatusLine = trimmed; }
                return;
            }

            if (trimmed.IndexOf("[RPF]", StringComparison.OrdinalIgnoreCase) >= 0) { Progress = Math.Max(Progress, _hasSeenBuildProgress ? 0.85f : 0.70f); StatusLine = trimmed; }
            else if (trimmed.StartsWith("--- ", StringComparison.Ordinal) && trimmed.IndexOf("RPF7", StringComparison.OrdinalIgnoreCase) >= 0) { Progress = Math.Max(Progress, Math.Min(0.98f, Math.Max(_hasSeenBuildProgress ? 0.84f : 0.65f, Progress + 0.02f))); StatusLine = trimmed.Trim('-', ' '); }
            else if (trimmed.IndexOf("INFO: Starting export", StringComparison.OrdinalIgnoreCase) >= 0) { if (!_hasExplicitProgress) Progress = Math.Max(Progress, 0.72f); if (string.IsNullOrEmpty(StatusLine) || StatusLine.IndexOf("[VToon]", StringComparison.OrdinalIgnoreCase) >= 0 || StatusLine.IndexOf("[4/4]", StringComparison.OrdinalIgnoreCase) >= 0) StatusLine = "Exporting .ydd mesh via Sollumz..."; }
            else if (trimmed.IndexOf("[YFT]", StringComparison.OrdinalIgnoreCase) >= 0 || (trimmed.IndexOf("[PhysBones]", StringComparison.OrdinalIgnoreCase) >= 0 && trimmed.IndexOf("Merged", StringComparison.OrdinalIgnoreCase) >= 0)) { if (!_hasExplicitProgress) { Progress = Math.Max(Progress, 0.80f); StatusLine = trimmed; } }
            else if (!_hasExplicitProgress && trimmed.IndexOf("[Blender", StringComparison.OrdinalIgnoreCase) >= 0) { Progress = Math.Max(Progress, 0.55f); StatusLine = trimmed; }
        }

        private static void KillProcessTree(Process proc)
        {
            try
            {
                if (proc.HasExited) return;
                int pid = proc.Id;
                var taskKill = new ProcessStartInfo
                {
                    FileName = "taskkill",
                    Arguments = "/PID " + pid + " /T /F",
                    UseShellExecute = false,
                    CreateNoWindow = true
                };
                using (Process tk = Process.Start(taskKill))
                {
                    tk?.WaitForExit(3000);
                }
            }
            catch { }

            try
            {
                if (!proc.HasExited) proc.Kill();
            }
            catch { }
        }
    }

    internal static class Vrc2GtavOptionsUi
    {
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
            Vrc2GtavSlotProfile profile,
            Vrc2GtavExportOptions globalOpts,
            UiLanguageMode langMode,
            float baseLabelW,
            ref bool showAdvanced,
            ref bool showCliPreview,
            Vrc2GtavToolPaths paths,
            BackendExecutionMode currentMode,
            GUIStyle wrapMiniLabelStyle,
            Action drawMouthOpenRow,
            Func<ExecutionCommandSpec> buildPreviewSpec,
            Action<BackendExecutionMode> onBackendModeChanged)
        {
            string T(string k) => Vrc2GtavLocalization.Get(langMode, k);
            if (!globalOpts.PerProtagonistSlots)
            {
                globalOpts.DeployToMods = EditorGUILayout.ToggleLeft(T("opt.deploy"), globalOpts.DeployToMods);
            }
            profile.ImportFaceBlendshapes = EditorGUILayout.ToggleLeft(T("opt.face_bs"), profile.ImportFaceBlendshapes);
            profile.ImportBodyBlendshapes = EditorGUILayout.ToggleLeft(T("opt.body_bs"), profile.ImportBodyBlendshapes);
            profile.EyeBlink = EditorGUILayout.ToggleLeft(T("opt.eye_blink"), profile.EyeBlink);
            using (new EditorGUI.DisabledScope(!profile.EyeBlink))
                profile.EyeBlinkStrength = EditorGUILayout.Slider(T("opt.eye_strength"), profile.EyeBlinkStrength, 0f, 1f);
            drawMouthOpenRow?.Invoke();
            profile.BloodDecals = EditorGUILayout.ToggleLeft(T("opt.blood_decals"), profile.BloodDecals);

            showAdvanced = EditorGUILayout.Foldout(showAdvanced, T("opt.advanced"), true);
            if (!showAdvanced) return;
            EditorGUI.indentLevel++;
            EditorGUIUtility.labelWidth = baseLabelW + 18f;
            profile.AvatarNameOverride = EditorGUILayout.TextField(T("opt.avatar_override"), profile.AvatarNameOverride);
            profile.BlendshapesSourceIdx = EditorGUILayout.Popup(T("opt.bs_source"), profile.BlendshapesSourceIdx, Vrc2GtavCommandBuilder.SourceModes);
            profile.BlendshapesCfg = Vrc2GtavLogConsoleWidget.DrawPathBrowseRow("Blendshapes .cfg", profile.BlendshapesCfg, string.Empty, true, false, "cfg", T("tools.browse"), paths.RepoRoot);
            profile.FaceBlendshapesAnim = Vrc2GtavLogConsoleWidget.DrawAnimClipOverrideRow(
                T("opt.face_anim"), profile.FaceBlendshapesAnim, ref profile.FaceAnimClip,
                T("tools.browse"), Vrc2GtavConfigDiscovery.GetDefaultUnityAssetsPath(), wrapMiniLabelStyle);
            profile.PhysbonesSourceIdx = EditorGUILayout.Popup(T("opt.pb_source"), profile.PhysbonesSourceIdx, Vrc2GtavCommandBuilder.SourceModes);
            profile.PhysbonesCfg = Vrc2GtavLogConsoleWidget.DrawPathBrowseRow("PhysBones .cfg", profile.PhysbonesCfg, string.Empty, true, false, "cfg", T("tools.browse"), paths.RepoRoot);
            profile.PhysbonesMarshmallow = EditorGUILayout.ToggleLeft(T("opt.marshmallow"), profile.PhysbonesMarshmallow);
            profile.ForceReextract = EditorGUILayout.ToggleLeft(T("opt.force_reextract"), profile.ForceReextract);
            if (!globalOpts.PerProtagonistSlots)
            {
                DrawBackendAndCliPreview(langMode, paths, currentMode, ref showCliPreview, buildPreviewSpec, onBackendModeChanged);
            }
            EditorGUIUtility.labelWidth = baseLabelW;
            EditorGUI.indentLevel--;
        }

        public static void DrawGlobalBatchOptions(
            Vrc2GtavExportOptions globalOpts,
            UiLanguageMode langMode,
            Vrc2GtavToolPaths paths,
            BackendExecutionMode currentMode,
            ref bool showCliPreview,
            Func<ExecutionCommandSpec> buildPreviewSpec,
            Action<BackendExecutionMode> onBackendModeChanged)
        {
            string T(string k) => Vrc2GtavLocalization.Get(langMode, k);
            EditorGUILayout.BeginVertical(EditorStyles.helpBox);
            EditorGUILayout.LabelField(T("sec.global"), EditorStyles.boldLabel);
            globalOpts.DeployToMods = EditorGUILayout.ToggleLeft(T("opt.deploy"), globalOpts.DeployToMods);
            DrawBackendAndCliPreview(langMode, paths, currentMode, ref showCliPreview, buildPreviewSpec, onBackendModeChanged);
            EditorGUILayout.EndVertical();
        }

        private static void DrawBackendAndCliPreview(
            UiLanguageMode langMode,
            Vrc2GtavToolPaths paths,
            BackendExecutionMode currentMode,
            ref bool showCliPreview,
            Func<ExecutionCommandSpec> buildPreviewSpec,
            Action<BackendExecutionMode> onBackendModeChanged)
        {
            string T(string k) => Vrc2GtavLocalization.Get(langMode, k);
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
        }
    }
}
