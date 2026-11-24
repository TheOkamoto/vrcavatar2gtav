using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
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
        private static readonly Regex StepFractionRegex = new Regex(@"\[(\d+)/(\d+)\]", RegexOptions.Compiled);

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
            Match m = StepFractionRegex.Match(line);
            if (m.Success
                && int.TryParse(m.Groups[1].Value, out int cur)
                && int.TryParse(m.Groups[2].Value, out int total)
                && total > 0)
            {
                Progress = Math.Max(Progress, Math.Min(0.96f, (float)cur / total * 0.9f));
                StatusLine = line.Trim();
                return;
            }

            if (line.IndexOf("[RPF]", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                Progress = Math.Max(Progress, 0.85f);
                StatusLine = line.Trim();
            }
            else if (line.IndexOf("[Blender", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                Progress = Math.Max(Progress, 0.55f);
                StatusLine = line.Trim();
            }
            else if (line.IndexOf("[VToon]", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                Progress = Math.Max(Progress, 0.40f);
                StatusLine = line.Trim();
            }
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
