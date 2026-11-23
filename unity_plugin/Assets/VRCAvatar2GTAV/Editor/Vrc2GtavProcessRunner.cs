using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using UnityEditor;

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
}
