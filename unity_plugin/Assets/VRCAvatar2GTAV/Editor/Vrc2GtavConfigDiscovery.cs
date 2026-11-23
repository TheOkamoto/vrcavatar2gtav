using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using UnityEngine;

namespace Vrc2Gtav.Editor
{
    internal enum BackendExecutionMode
    {
        Auto = 0,
        WindowsNative = 1,
        Wsl = 2
    }

    [Serializable]
    internal sealed class Vrc2GtavToolPaths
    {
        public string RepoRoot = string.Empty;
        public bool RepoRootManualOverride;
        public string GtavRoot = string.Empty;
        public string UnityAssets = string.Empty;
        public string BlenderExe = string.Empty;
        public string RageExe = string.Empty;
        public string PythonExe = string.Empty;
        public BackendExecutionMode BackendMode = BackendExecutionMode.Auto;
    }

    internal struct ExecutionCommandSpec
    {
        public string FileName;
        public string Arguments;
        public string WorkingDirectory;
        public bool UsesWsl;
        public string PreviewCommand;
        public string ValidationError;
        public bool HasValidationError => !string.IsNullOrEmpty(ValidationError);
    }

    internal struct GtavRuntimeStatus
    {
        public bool ValidGtav;
        public bool AsiLoaderOk;
        public bool PhysBonesOk;
        public bool VToonOk;
        public bool ScriptHookVOk;
        public bool ModsReaderOk;
        public string ModsReaderName;
    }

    internal static class Vrc2GtavConfigDiscovery
    {
        private static readonly string[] RequiredRepoMarkers =
        {
            "run_mod_manager.py",
            "scripts/common_tools/universal_gtav_builder.py"
        };

        private static readonly Dictionary<string, bool> ValidationCache =
            new Dictionary<string, bool>(StringComparer.Ordinal);

        public static void ClearValidationCache() => ValidationCache.Clear();
        public static string GetDefaultUnityAssetsPath() => Path.GetFullPath(Application.dataPath);
        public static string GetUnityProjectRoot() => Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
        public static string GetBundledToolchainRoot() =>
            Path.GetFullPath(Path.Combine(GetDefaultUnityAssetsPath(), "VRCAvatar2GTAV", "Toolchain"));

        public static string GetUnityWorkRootIfBundled(string repoRoot)
        {
            if (string.IsNullOrWhiteSpace(repoRoot)) return string.Empty;
            string norm = repoRoot.Replace('\\', '/').TrimEnd('/');
            int idx = norm.IndexOf("/Assets/VRCAvatar2GTAV", StringComparison.OrdinalIgnoreCase);
            if (idx > 0) return Path.GetFullPath(Path.Combine(norm.Substring(0, idx), "VRCAvatar2GTAV_Work"));
            return string.Empty;
        }

        public static bool IsValidRepoRoot(string path)
        {
            if (string.IsNullOrWhiteSpace(path) || Vrc2GtavIniAndWsl.IsLinuxStylePath(path) || !Directory.Exists(path))
                return false;
            for (int i = 0; i < RequiredRepoMarkers.Length; i++)
            {
                if (!File.Exists(Path.Combine(path, RequiredRepoMarkers[i]))) return false;
            }
            return true;
        }

        public static bool IsValidGtavRoot(string path)
        {
            return !string.IsNullOrWhiteSpace(path)
                && !Vrc2GtavIniAndWsl.IsLinuxStylePath(path)
                && Directory.Exists(path)
                && File.Exists(Path.Combine(path, "GTA5.exe"))
                && File.Exists(Path.Combine(path, "x64v.rpf"));
        }

        public static bool IsValidBlender(string path)
        {
            return !string.IsNullOrWhiteSpace(path) && !Vrc2GtavIniAndWsl.IsLinuxStylePath(path) && File.Exists(path);
        }

        public static GtavRuntimeStatus InspectGtavRuntime(string gtavRoot)
        {
            bool valid = IsValidGtavRoot(gtavRoot);
            if (!valid) return new GtavRuntimeStatus();

            string modsReader = File.Exists(Path.Combine(gtavRoot, "OpenIV.asi"))
                ? "OpenIV.asi"
                : (File.Exists(Path.Combine(gtavRoot, "RageOpenV.asi")) ? "RageOpenV.asi" : string.Empty);

            return new GtavRuntimeStatus
            {
                ValidGtav = true,
                AsiLoaderOk = File.Exists(Path.Combine(gtavRoot, "dinput8.dll")),
                PhysBonesOk = File.Exists(Path.Combine(gtavRoot, "GTAVPhysBones.asi"))
                    && File.Exists(Path.Combine(gtavRoot, "GTAVPhysBones.ini")),
                VToonOk = File.Exists(Path.Combine(gtavRoot, "GTAVVToon.asi"))
                    && File.Exists(Path.Combine(gtavRoot, "GTAVVToon.ini")),
                ScriptHookVOk = File.Exists(Path.Combine(gtavRoot, "ScriptHookV.dll")),
                ModsReaderOk = !string.IsNullOrEmpty(modsReader),
                ModsReaderName = modsReader
            };
        }

        public static bool HasSollumzInstalled(string blenderExe)
        {
            if (!IsValidBlender(blenderExe)) return false;
            string blenderDir = Path.GetDirectoryName(blenderExe);
            if (string.IsNullOrEmpty(blenderDir)) return false;

            try
            {
                foreach (string verDir in Directory.GetDirectories(blenderDir, "4.*"))
                {
                    string addonsDir = Path.Combine(verDir, "scripts", "addons");
                    if (!Directory.Exists(addonsDir)) continue;
                    if (File.Exists(Path.Combine(addonsDir, "sollumz", "__init__.py"))) return true;
                    foreach (string sub in Directory.GetDirectories(addonsDir, "*sollumz*"))
                    {
                        if (File.Exists(Path.Combine(sub, "__init__.py"))) return true;
                    }
                }
            }
            catch { }

            string appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
            return File.Exists(Path.Combine(appData, "Blender Foundation", "Blender", "4.0", "scripts", "addons", "sollumz", "__init__.py"));
        }

        public static bool IsValidRage(string path, BackendExecutionMode mode)
        {
            if (string.IsNullOrWhiteSpace(path)) return false;
            bool isLinux = Vrc2GtavIniAndWsl.IsLinuxStylePath(path);
            if (isLinux) return mode != BackendExecutionMode.WindowsNative && CachedProbeWsl("rage:" + path, path);
            return File.Exists(path);
        }

        public static bool IsValidPython(string path, BackendExecutionMode mode, out bool isWsl)
        {
            isWsl = Vrc2GtavIniAndWsl.IsLinuxStylePath(path);
            if (string.IsNullOrWhiteSpace(path)) return false;
            if (isWsl)
            {
                if (mode == BackendExecutionMode.WindowsNative)
                {
                    isWsl = false;
                    return false;
                }
                return CachedProbeWsl("python:" + path, path);
            }
            string cacheKey = "winpy:" + path;
            if (ValidationCache.TryGetValue(cacheKey, out bool cached)) return cached;
            bool ok = File.Exists(path) && TestWindowsPythonBinary(path);
            ValidationCache[cacheKey] = ok;
            return ok;
        }

        private static bool CachedProbeWsl(string cacheKey, string linuxPath)
        {
            if (ValidationCache.TryGetValue(cacheKey, out bool cached)) return cached;
            bool ok = Vrc2GtavIniAndWsl.ProbeWslFileExists(linuxPath);
            ValidationCache[cacheKey] = ok;
            return ok;
        }

        public static void SanitizeToolPathsForMode(Vrc2GtavToolPaths paths)
        {
            if (paths == null || paths.BackendMode != BackendExecutionMode.WindowsNative) return;
            paths.RepoRoot = Vrc2GtavIniAndWsl.SanitizePathForWindows(paths.RepoRoot);
            paths.GtavRoot = Vrc2GtavIniAndWsl.SanitizePathForWindows(paths.GtavRoot);
            paths.UnityAssets = Vrc2GtavIniAndWsl.SanitizePathForWindows(paths.UnityAssets);
            paths.BlenderExe = Vrc2GtavIniAndWsl.SanitizePathForWindows(paths.BlenderExe);
            paths.RageExe = Vrc2GtavIniAndWsl.SanitizePathForWindows(paths.RageExe);
            paths.PythonExe = Vrc2GtavIniAndWsl.SanitizePathForWindows(paths.PythonExe);
        }

        public static Vrc2GtavToolPaths AutoDetectAll(Vrc2GtavToolPaths seed)
        {
            Vrc2GtavToolPaths result = seed ?? new Vrc2GtavToolPaths();
            SanitizeToolPathsForMode(result);
            result.UnityAssets = GetDefaultUnityAssetsPath();

            if (!result.RepoRootManualOverride && IsValidRepoRoot(GetBundledToolchainRoot()))
            {
                result.RepoRoot = GetBundledToolchainRoot();
            }
            else if (!IsValidRepoRoot(result.RepoRoot))
            {
                result.RepoRoot = DetectRepoRoot();
            }

            bool allowWslCfg = result.BackendMode != BackendExecutionMode.WindowsNative;
            Dictionary<string, string> cfgValues = Vrc2GtavIniAndWsl.ReadConfigFlat(result.RepoRoot);
            if (string.IsNullOrWhiteSpace(result.GtavRoot) && cfgValues.TryGetValue("directories.gtav_root", out string cfgGtav))
                result.GtavRoot = Vrc2GtavIniAndWsl.NormalizeSlashForBackend(cfgGtav, allowWslCfg);
            if (string.IsNullOrWhiteSpace(result.BlenderExe) && cfgValues.TryGetValue("executables.blender", out string cfgBlender))
                result.BlenderExe = Vrc2GtavIniAndWsl.NormalizeSlashForBackend(cfgBlender, allowWslCfg);
            if (string.IsNullOrWhiteSpace(result.RageExe) && cfgValues.TryGetValue("executables.rage", out string cfgRage))
                result.RageExe = Vrc2GtavIniAndWsl.NormalizeSlashForBackend(cfgRage, allowWslCfg);
            if (string.IsNullOrWhiteSpace(result.PythonExe) && cfgValues.TryGetValue("executables.python", out string cfgPy))
                result.PythonExe = Vrc2GtavIniAndWsl.NormalizeSlashForBackend(cfgPy, allowWslCfg);

            if (!IsValidGtavRoot(result.GtavRoot))
            {
                string detected = DetectGtavRoot();
                if (!string.IsNullOrEmpty(detected)) result.GtavRoot = detected;
            }
            if (!IsValidBlender(result.BlenderExe))
            {
                string detected = DetectBlender(result.RepoRoot);
                if (!string.IsNullOrEmpty(detected)) result.BlenderExe = detected;
            }
            if (!IsValidRage(result.RageExe, result.BackendMode))
            {
                string detected = DetectRage(result.RepoRoot, result.BackendMode);
                result.RageExe = !string.IsNullOrEmpty(detected) ? detected : string.Empty;
            }
            if (!IsValidPython(result.PythonExe, result.BackendMode, out _))
            {
                string detected = DetectPython(result.RepoRoot, result.BackendMode, Vrc2GtavIniAndWsl.IsLinuxStylePath(result.RageExe));
                result.PythonExe = !string.IsNullOrEmpty(detected) ? detected : string.Empty;
            }
            SanitizeToolPathsForMode(result);
            return result;
        }

        public static string DetectRepoRoot()
        {
            string bundled = GetBundledToolchainRoot();
            if (IsValidRepoRoot(bundled)) return Path.GetFullPath(bundled);

            var candidates = new List<string>();
            string current = GetUnityProjectRoot();
            for (int depth = 0; depth < 4 && !string.IsNullOrEmpty(current); depth++)
            {
                candidates.Add(current);
                candidates.Add(Path.Combine(current, "vrc2gtav"));
                candidates.Add(Path.Combine(current, "vrc-avatar-to-gtav"));
                DirectoryInfo parent = Directory.GetParent(current);
                current = parent != null ? parent.FullName : null;
            }

            string userProfile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            candidates.Add(Path.Combine(userProfile, "vrc2gtav"));
            candidates.Add(Path.Combine(userProfile, "Downloads", "vrc2gtav"));
            candidates.Add(Path.Combine(userProfile, "Documents", "vrc2gtav"));

            foreach (DriveInfo drive in DriveInfo.GetDrives())
            {
                if (drive.DriveType != DriveType.Fixed && drive.DriveType != DriveType.Network) continue;
                string root = drive.RootDirectory.FullName;
                candidates.Add(Path.Combine(root, "vrc2gtav"));
                candidates.Add(Path.Combine(root, "New Google Drive", "vrc2gtav"));
                candidates.Add(Path.Combine(root, "Google Drive", "vrc2gtav"));
            }

            // Fallback only when bundled Assets/VRCAvatar2GTAV/Toolchain is absent: prefer an external folder with vrc2gtav.cfg
            for (int i = 0; i < candidates.Count; i++)
            {
                if (IsValidRepoRoot(candidates[i]) && File.Exists(Path.Combine(candidates[i], "vrc2gtav.cfg")))
                    return Path.GetFullPath(candidates[i]);
            }
            for (int i = 0; i < candidates.Count; i++)
            {
                if (IsValidRepoRoot(candidates[i])) return Path.GetFullPath(candidates[i]);
            }
            return string.Empty;
        }

        public static string DetectGtavRoot()
        {
            var steamRoots = new List<string> { @"C:\Program Files (x86)\Steam", @"C:\Program Files\Steam" };
            var directCandidates = new List<string>();

            foreach (DriveInfo drive in DriveInfo.GetDrives())
            {
                if (drive.DriveType != DriveType.Fixed) continue;
                string r = drive.RootDirectory.FullName;
                steamRoots.Add(Path.Combine(r, "Steam"));
                steamRoots.Add(Path.Combine(r, "SteamLibrary"));
                steamRoots.Add(Path.Combine(r, "Games", "SteamLibrary"));
                directCandidates.Add(Path.Combine(r, "Program Files", "Rockstar Games", "Grand Theft Auto V"));
                directCandidates.Add(Path.Combine(r, "Program Files", "Epic Games", "GTAV"));
                directCandidates.Add(Path.Combine(r, "Rockstar Games", "Grand Theft Auto V"));
                directCandidates.Add(Path.Combine(r, "Games", "Grand Theft Auto V"));
            }

            foreach (string libRoot in steamRoots)
            {
                directCandidates.Add(Path.Combine(libRoot, "steamapps", "common", "Grand Theft Auto V"));
                directCandidates.Add(Path.Combine(libRoot, "steamapps", "common", "Grand Theft Auto V Legacy"));
                string vdf = Path.Combine(libRoot, "steamapps", "libraryfolders.vdf");
                if (!File.Exists(vdf)) continue;
                foreach (string parsedLib in ParseSteamLibraryFolders(vdf))
                {
                    directCandidates.Add(Path.Combine(parsedLib, "steamapps", "common", "Grand Theft Auto V"));
                    directCandidates.Add(Path.Combine(parsedLib, "steamapps", "common", "Grand Theft Auto V Legacy"));
                }
            }

            for (int i = 0; i < directCandidates.Count; i++)
            {
                if (IsValidGtavRoot(directCandidates[i])) return Path.GetFullPath(directCandidates[i]);
            }
            return string.Empty;
        }

        public static string DetectBlender(string repoRoot)
        {
            var candidates = new List<string>
            {
                Path.Combine(GetUnityProjectRoot(), "BlenderTools", "blender-4.0.2-windows-x64", "blender.exe")
            };
            string workRoot = GetUnityWorkRootIfBundled(repoRoot);
            if (!string.IsNullOrWhiteSpace(workRoot)) AddBlenderToolDirCandidates(candidates, Path.Combine(workRoot, "tools"));
            if (!string.IsNullOrWhiteSpace(repoRoot)) AddBlenderToolDirCandidates(candidates, Path.Combine(repoRoot, "tools"));
            candidates.Add(@"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe");
            candidates.Add(@"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe");
            candidates.Add(@"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe");

            for (int i = 0; i < candidates.Count; i++)
            {
                if (File.Exists(candidates[i])) return Path.GetFullPath(candidates[i]);
            }
            return FindOnWindowsPath("blender.exe");
        }

        private static void AddBlenderToolDirCandidates(List<string> candidates, string toolsDir)
        {
            candidates.Add(Path.Combine(toolsDir, "blender-4.0.2-windows-x64", "blender.exe"));
            candidates.Add(Path.Combine(toolsDir, "blender", "blender.exe"));
            if (!Directory.Exists(toolsDir)) return;
            try
            {
                foreach (string dir in Directory.GetDirectories(toolsDir, "blender*")) candidates.Add(Path.Combine(dir, "blender.exe"));
            }
            catch { }
        }

        public static string DetectRage(string repoRoot, BackendExecutionMode mode)
        {
            string workRoot = GetUnityWorkRootIfBundled(repoRoot);
            foreach (string baseDir in new[] { workRoot, repoRoot })
            {
                if (string.IsNullOrWhiteSpace(baseDir)) continue;
                foreach (string rel in new[] { @"tools\rage.exe", @"tools\rage-windows-x86_64.exe", "rage.exe" })
                {
                    string cand = Path.Combine(baseDir, rel);
                    if (File.Exists(cand)) return Path.GetFullPath(cand);
                }
            }
            string fromPath = FindOnWindowsPath("rage.exe");
            if (!string.IsNullOrEmpty(fromPath)) return fromPath;
            if (mode == BackendExecutionMode.WindowsNative) return string.Empty;

            string wslRage = Vrc2GtavIniAndWsl.ProbeWslCommandOutput(
                "command -v rage || ls \"$HOME/.gemini/antigravity/scratch/gtav_tools/rage\" 2>/dev/null");
            return !string.IsNullOrEmpty(wslRage) && Vrc2GtavIniAndWsl.ProbeWslFileExists(wslRage) ? wslRage : string.Empty;
        }

        public static string DetectPython(string repoRoot, BackendExecutionMode mode, bool wslRageHint)
        {
            if (mode == BackendExecutionMode.Wsl || (mode == BackendExecutionMode.Auto && wslRageHint))
            {
                string wsl = Vrc2GtavIniAndWsl.DetectWslPython(repoRoot);
                if (!string.IsNullOrEmpty(wsl)) return wsl;
                if (mode == BackendExecutionMode.Wsl) return string.Empty;
            }

            var winCandidates = new List<string>();
            if (!string.IsNullOrWhiteSpace(repoRoot) && !Vrc2GtavIniAndWsl.IsLinuxStylePath(repoRoot))
            {
                winCandidates.Add(Path.Combine(repoRoot, ".venv", "Scripts", "python.exe"));
            }
            string localApp = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            AddPythonDirs(winCandidates, Path.Combine(localApp, "Programs", "Python"));
            AddPythonDirs(winCandidates, @"C:\Program Files");
            winCandidates.Add(Path.Combine(localApp, "Microsoft", "WindowsApps", "python.exe"));
            string wherePy = FindOnWindowsPath("python.exe");
            if (!string.IsNullOrEmpty(wherePy)) winCandidates.Add(wherePy);

            for (int i = 0; i < winCandidates.Count; i++)
            {
                if (File.Exists(winCandidates[i]) && TestWindowsPythonBinary(winCandidates[i]))
                {
                    return Path.GetFullPath(winCandidates[i]);
                }
            }
            return mode == BackendExecutionMode.WindowsNative ? string.Empty : Vrc2GtavIniAndWsl.DetectWslPython(repoRoot);
        }

        public static bool DetermineShouldUseWsl(Vrc2GtavToolPaths paths, BackendExecutionMode mode)
        {
            if (mode == BackendExecutionMode.Wsl) return true;
            if (mode == BackendExecutionMode.WindowsNative) return false;
            return Vrc2GtavIniAndWsl.IsLinuxStylePath(paths.RageExe) || Vrc2GtavIniAndWsl.IsLinuxStylePath(paths.PythonExe);
        }

        public static bool SaveToConfig(string repoRoot, Vrc2GtavToolPaths paths, string cliLanguage)
        {
            bool useWsl = DetermineShouldUseWsl(paths, paths.BackendMode);
            string safeRepo = useWsl ? repoRoot : Vrc2GtavIniAndWsl.SanitizePathForWindows(repoRoot);
            return IsValidRepoRoot(safeRepo) && Vrc2GtavIniAndWsl.SaveToConfig(safeRepo, paths, cliLanguage, useWsl);
        }

        private static IEnumerable<string> ParseSteamLibraryFolders(string vdfPath)
        {
            var libs = new List<string>();
            try
            {
                string content = File.ReadAllText(vdfPath, Encoding.UTF8);
                foreach (Match m in Regex.Matches(content, "\"path\"\\s+\"([^\"]+)\""))
                {
                    string raw = m.Groups[1].Value.Replace(@"\\", @"\");
                    if (Directory.Exists(raw)) libs.Add(raw);
                }
            }
            catch { }
            return libs;
        }

        private static void AddPythonDirs(List<string> targets, string baseDir)
        {
            if (!Directory.Exists(baseDir)) return;
            try
            {
                foreach (string dir in Directory.GetDirectories(baseDir, "Python3*"))
                {
                    targets.Add(Path.Combine(dir, "python.exe"));
                }
            }
            catch { }
        }

        private static string FindOnWindowsPath(string exeName)
        {
            string pathEnv = Environment.GetEnvironmentVariable("PATH") ?? string.Empty;
            foreach (string dirRaw in pathEnv.Split(Path.PathSeparator))
            {
                string dir = dirRaw.Trim();
                if (string.IsNullOrEmpty(dir)) continue;
                string full = Path.Combine(dir, exeName);
                if (!File.Exists(full)) continue;
                if (exeName.Equals("python.exe", StringComparison.OrdinalIgnoreCase) && !TestWindowsPythonBinary(full)) continue;
                return full;
            }
            return string.Empty;
        }

        private static bool TestWindowsPythonBinary(string pythonExe)
        {
            try
            {
                var info = new ProcessStartInfo
                {
                    FileName = pythonExe,
                    Arguments = "--version",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true
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
    }
}
