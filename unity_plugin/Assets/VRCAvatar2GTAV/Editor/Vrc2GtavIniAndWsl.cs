using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;

namespace Vrc2Gtav.Editor
{
    internal static class Vrc2GtavIniAndWsl
    {
        public static bool IsLinuxStylePath(string path)
        {
            return !string.IsNullOrWhiteSpace(path) && path.TrimStart().StartsWith("/", StringComparison.Ordinal);
        }

        public static bool IsWslMountPath(string path)
        {
            if (string.IsNullOrWhiteSpace(path)) return false;
            string trimmed = path.Trim();
            return trimmed.StartsWith("/mnt/", StringComparison.OrdinalIgnoreCase)
                && trimmed.Length >= 6
                && char.IsLetter(trimmed[5])
                && (trimmed.Length == 6 || trimmed[6] == '/');
        }

        public static string SanitizePathForWindows(string value)
        {
            if (string.IsNullOrWhiteSpace(value)) return string.Empty;
            string trimmed = value.Trim();
            if (IsWslMountPath(trimmed))
            {
                char drive = char.ToUpperInvariant(trimmed[5]);
                string rest = trimmed.Length > 6 ? trimmed.Substring(6).Replace('/', '\\') : "\\";
                return drive + ":" + rest;
            }
            if (IsLinuxStylePath(trimmed) || trimmed.StartsWith("~/", StringComparison.Ordinal))
            {
                return string.Empty;
            }
            return trimmed.Replace('/', '\\');
        }

        public static string NormalizeSlashForBackend(string value, bool useWsl)
        {
            if (string.IsNullOrWhiteSpace(value)) return string.Empty;
            string trimmed = value.Trim();
            if (!useWsl) return SanitizePathForWindows(trimmed);
            return trimmed.StartsWith("/", StringComparison.Ordinal) ? trimmed : trimmed.Replace('/', '\\');
        }

        public static string ToWslPathIfWindows(string value)
        {
            if (string.IsNullOrWhiteSpace(value)) return value;
            string trimmed = value.Trim();
            if (trimmed.StartsWith("/", StringComparison.Ordinal)) return trimmed;
            if (trimmed.Length >= 3 && char.IsLetter(trimmed[0]) && trimmed[1] == ':' && (trimmed[2] == '\\' || trimmed[2] == '/'))
            {
                char drive = char.ToLowerInvariant(trimmed[0]);
                string rest = trimmed.Substring(2).Replace('\\', '/');
                return "/mnt/" + drive + rest;
            }
            return trimmed.Replace('\\', '/');
        }

        public static string ConvertArgPathForWsl(string arg)
        {
            if (string.IsNullOrWhiteSpace(arg)) return arg;
            if (arg.Length >= 3 && char.IsLetter(arg[0]) && arg[1] == ':' && (arg[2] == '\\' || arg[2] == '/'))
            {
                return ToWslPathIfWindows(arg);
            }
            return arg;
        }

        public static string QuoteWindowsArg(string arg)
        {
            if (arg == null) return "\"\"";
            if (arg.Length > 0 && arg.IndexOfAny(new[] { ' ', '\t', '"' }) < 0) return arg;
            return "\"" + arg.Replace("\"", "\\\"") + "\"";
        }

        public static string DetectWslPython(string repoRoot)
        {
            if (!string.IsNullOrWhiteSpace(repoRoot))
            {
                string wslRepo = ToWslPathIfWindows(repoRoot);
                string localVenv = wslRepo.TrimEnd('/') + "/.venv/bin/python3";
                if (ProbeWslFileExists(localVenv)) return localVenv;
            }

            string scratchVenv = ProbeWslCommandOutput(
                "ls \"$HOME/.gemini/antigravity/scratch/vrc-avatar-to-gtav/.venv/bin/python3\" 2>/dev/null || command -v python3");
            return !string.IsNullOrEmpty(scratchVenv) ? scratchVenv : string.Empty;
        }

        public static bool ProbeWslFileExists(string linuxPath)
        {
            if (!IsLinuxStylePath(linuxPath)) return false;
            try
            {
                var info = new ProcessStartInfo
                {
                    FileName = "wsl.exe",
                    Arguments = "-e test -e " + QuoteWindowsArg(linuxPath),
                    UseShellExecute = false,
                    CreateNoWindow = true
                };
                using (Process proc = Process.Start(info))
                {
                    if (proc == null) return false;
                    proc.WaitForExit(3000);
                    return proc.HasExited && proc.ExitCode == 0;
                }
            }
            catch
            {
                return false;
            }
        }

        public static string ProbeWslCommandOutput(string bashCmd)
        {
            try
            {
                var info = new ProcessStartInfo
                {
                    FileName = "wsl.exe",
                    Arguments = "-e bash -c " + QuoteWindowsArg(bashCmd),
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true
                };
                using (Process proc = Process.Start(info))
                {
                    if (proc == null) return string.Empty;
                    string output = proc.StandardOutput.ReadLine() ?? string.Empty;
                    proc.WaitForExit(3000);
                    return proc.HasExited && proc.ExitCode == 0 ? output.Trim() : string.Empty;
                }
            }
            catch
            {
                return string.Empty;
            }
        }

        public static Dictionary<string, string> ReadConfigFlat(string repoRoot)
        {
            var dict = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            if (string.IsNullOrWhiteSpace(repoRoot)) return dict;
            string cfgPath = Path.Combine(repoRoot, "vrc2gtav.cfg");
            if (!File.Exists(cfgPath)) return dict;

            string currentSection = string.Empty;
            foreach (string rawLine in File.ReadAllLines(cfgPath, Encoding.UTF8))
            {
                string line = rawLine.Trim();
                if (line.Length == 0 || line.StartsWith("#") || line.StartsWith(";")) continue;
                if (line.StartsWith("[") && line.EndsWith("]"))
                {
                    currentSection = line.Substring(1, line.Length - 2).Trim();
                    continue;
                }
                int eqIdx = line.IndexOf('=');
                if (eqIdx <= 0) continue;
                string key = line.Substring(0, eqIdx).Trim();
                string val = line.Substring(eqIdx + 1).Trim();
                if (!string.IsNullOrEmpty(currentSection) && !string.IsNullOrEmpty(val))
                {
                    dict[currentSection + "." + key] = val;
                }
            }
            return dict;
        }

        public static bool SaveToConfig(string repoRoot, Vrc2GtavToolPaths paths, string cliLanguage, bool useWsl)
        {
            string effectiveRepo = useWsl ? repoRoot : SanitizePathForWindows(repoRoot);
            if (string.IsNullOrWhiteSpace(effectiveRepo) || !Directory.Exists(effectiveRepo)) return false;
            string cfgPath = Path.Combine(effectiveRepo, "vrc2gtav.cfg");
            string examplePath = Path.Combine(effectiveRepo, "vrc2gtav.cfg.example");
            if (!File.Exists(cfgPath) && File.Exists(examplePath))
            {
                File.Copy(examplePath, cfgPath, false);
            }

            List<string> lines = File.Exists(cfgPath)
                ? new List<string>(File.ReadAllLines(cfgPath, Encoding.UTF8))
                : new List<string>();

            string cfgUnityAssets = FormatCfgPath(paths.UnityAssets, useWsl);
            string cfgGtavRoot = FormatCfgPath(paths.GtavRoot, useWsl);
            string cfgBlender = FormatCfgPath(paths.BlenderExe, useWsl);
            string cfgRage = FormatCfgPath(paths.RageExe, useWsl);
            string cfgPython = FormatCfgPath(paths.PythonExe, useWsl);

            var dirUpdates = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
            {
                ["project_root"] = effectiveRepo.Replace('\\', '/'),
                ["unity_assets"] = cfgUnityAssets,
                ["gtav_root"] = cfgGtavRoot
            };
            string workRoot = Vrc2GtavConfigDiscovery.GetUnityWorkRootIfBundled(effectiveRepo);
            if (!string.IsNullOrEmpty(workRoot))
            {
                var existing = ReadConfigFlat(effectiveRepo);
                string cfgWork = FormatCfgPath(workRoot, useWsl);
                if (!string.IsNullOrEmpty(cfgWork))
                {
                    if (!existing.TryGetValue("directories.staging", out string st)
                        || string.IsNullOrEmpty(st)
                        || st.IndexOf("${project_root}", StringComparison.OrdinalIgnoreCase) >= 0
                        || st.IndexOf("/Assets/", StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        dirUpdates["staging"] = cfgWork + "/staging";
                    }
                    if (!existing.TryGetValue("directories.backups", out string bk)
                        || string.IsNullOrEmpty(bk)
                        || bk.IndexOf("${project_root}", StringComparison.OrdinalIgnoreCase) >= 0
                        || bk.IndexOf("/Assets/", StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        dirUpdates["backups"] = cfgWork + "/backups";
                    }
                }
            }

            var updates = new Dictionary<string, Dictionary<string, string>>(StringComparer.OrdinalIgnoreCase)
            {
                ["general"] = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
                {
                    ["language"] = string.IsNullOrWhiteSpace(cliLanguage) ? "auto" : cliLanguage
                },
                ["directories"] = dirUpdates,
                ["executables"] = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
                {
                    ["blender"] = cfgBlender,
                    ["rage"] = cfgRage,
                    ["python"] = cfgPython
                }
            };

            UpsertIniSections(lines, updates);
            File.WriteAllLines(cfgPath, lines, new UTF8Encoding(false));
            return true;
        }

        private static string FormatCfgPath(string value, bool useWsl)
        {
            if (string.IsNullOrWhiteSpace(value)) return string.Empty;
            string trimmed = value.Trim();
            if (!useWsl)
            {
                string win = SanitizePathForWindows(trimmed);
                return string.IsNullOrEmpty(win) ? string.Empty : win.Replace('\\', '/');
            }
            return IsLinuxStylePath(trimmed) ? trimmed : trimmed.Replace('\\', '/');
        }

        private static void UpsertIniSections(
            List<string> lines,
            Dictionary<string, Dictionary<string, string>> updates)
        {
            var pending = new Dictionary<string, Dictionary<string, string>>(StringComparer.OrdinalIgnoreCase);
            foreach (var sec in updates)
            {
                pending[sec.Key] = new Dictionary<string, string>(sec.Value, StringComparer.OrdinalIgnoreCase);
            }

            string currentSec = string.Empty;
            int lastContentLine = -1;
            for (int i = 0; i < lines.Count; i++)
            {
                string trimmed = lines[i].Trim();
                if (trimmed.StartsWith("[") && trimmed.EndsWith("]"))
                {
                    FlushPendingKeysForSection(lines, ref i, currentSec, lastContentLine, pending);
                    currentSec = trimmed.Substring(1, trimmed.Length - 2).Trim();
                    lastContentLine = i;
                    continue;
                }
                if (trimmed.Length > 0 && !trimmed.StartsWith("#") && !trimmed.StartsWith(";"))
                {
                    lastContentLine = i;
                }
                int eqIdx = trimmed.IndexOf('=');
                if (eqIdx <= 0 || trimmed.StartsWith("#") || trimmed.StartsWith(";")) continue;
                string key = trimmed.Substring(0, eqIdx).Trim();
                if (pending.TryGetValue(currentSec, out var secKeys) && secKeys.TryGetValue(key, out string newVal))
                {
                    lines[i] = key + " = " + newVal;
                    secKeys.Remove(key);
                }
            }

            int endIdx = lines.Count;
            FlushPendingKeysForSection(lines, ref endIdx, currentSec, lastContentLine, pending);

            foreach (var leftover in pending)
            {
                if (leftover.Value.Count == 0) continue;
                if (lines.Count > 0 && !string.IsNullOrWhiteSpace(lines[lines.Count - 1])) lines.Add(string.Empty);
                lines.Add("[" + leftover.Key + "]");
                foreach (var kv in leftover.Value)
                {
                    lines.Add(kv.Key + " = " + kv.Value);
                }
            }
        }

        private static void FlushPendingKeysForSection(
            List<string> lines,
            ref int cursorIndex,
            string sectionName,
            int lastContentLine,
            Dictionary<string, Dictionary<string, string>> pending)
        {
            if (string.IsNullOrEmpty(sectionName) || !pending.TryGetValue(sectionName, out var rem) || rem.Count == 0) return;
            int insertAt = lastContentLine >= 0 ? lastContentLine + 1 : cursorIndex;
            var toInsert = new List<string>();
            foreach (var kv in rem)
            {
                toInsert.Add(kv.Key + " = " + kv.Value);
            }
            lines.InsertRange(insertAt, toInsert);
            cursorIndex += toInsert.Count;
            rem.Clear();
        }
    }
}
