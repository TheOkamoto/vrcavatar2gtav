using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace Vrc2Gtav.Editor
{
    [Serializable]
    internal sealed class Vrc2GtavExportOptions
    {
        public bool TargetMichael = true;
        public bool TargetFranklin;
        public bool TargetTrevor;
        public bool PerProtagonistSlots;
        public bool UserDisabledPerSlotForMulti;

        public bool DeployToMods = true;
        public bool ImportFaceBlendshapes = true;
        public bool ImportBodyBlendshapes = true;
        public bool EyeBlink = true;
        public float EyeBlinkStrength;
        public float MouthOpenStrength = 0.35f;
        public bool BloodDecals = true;

        public string AvatarNameOverride = string.Empty;
        public int BlendshapesSourceIdx;
        public int PhysbonesSourceIdx;
        public string BlendshapesCfg = string.Empty;
        public string FaceBlendshapesAnim = string.Empty;
        public string PhysbonesCfg = string.Empty;
        public bool PhysbonesMarshmallow;
        public bool ForceReextract;

        public int AtlasResolutionIdx = 2;
        public int NormalResolutionIdx = 0;
        public int SecondaryResolutionIdx = 0;
    }

    internal static class Vrc2GtavCommandBuilder
    {
        public static readonly string[] SourceModes = { "auto", "unity", "cfg" };
        public static readonly int[] AtlasResolutions = { 512, 1024, 2048, 4096 };
        public static readonly int[] NormalResolutions = { 0, 64, 256, 512, 1024 };
        public static readonly int[] SecondaryResolutions = { 0, 512, 1024, 2048 };

        public static int GetAtlasResolution(Vrc2GtavExportOptions opts)
        {
            return AtlasResolutions[Mathf.Clamp(opts.AtlasResolutionIdx, 0, AtlasResolutions.Length - 1)];
        }

        public static int GetNormalResolution(Vrc2GtavExportOptions opts)
        {
            return NormalResolutions[Mathf.Clamp(opts.NormalResolutionIdx, 0, NormalResolutions.Length - 1)];
        }

        public static int GetSecondaryResolution(Vrc2GtavExportOptions opts)
        {
            return SecondaryResolutions[Mathf.Clamp(opts.SecondaryResolutionIdx, 0, SecondaryResolutions.Length - 1)];
        }

        public static string BuildTargetPedCsv(Vrc2GtavExportOptions opts)
        {
            var slots = new List<string>(3);
            if (opts.TargetMichael) slots.Add("player_zero");
            if (opts.TargetFranklin) slots.Add("player_one");
            if (opts.TargetTrevor) slots.Add("player_two");
            return string.Join(",", slots);
        }

        public static bool HasAnyTarget(Vrc2GtavExportOptions opts)
        {
            return opts.TargetMichael || opts.TargetFranklin || opts.TargetTrevor;
        }

        public static int CountSelectedTargets(Vrc2GtavExportOptions opts)
        {
            if (opts == null) return 0;
            return (opts.TargetMichael ? 1 : 0) + (opts.TargetFranklin ? 1 : 0) + (opts.TargetTrevor ? 1 : 0);
        }

        private static string EscapeJson(string value)
        {
            if (string.IsNullOrEmpty(value)) return string.Empty;
            return value.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", "").Replace("\n", "");
        }

        private static void AppendSharedExportFlags(
            List<string> args,
            Vrc2GtavToolPaths paths,
            Vrc2GtavExportOptions opts,
            UiLanguageMode langMode,
            IReadOnlyDictionary<string, string> textureOverrides)
        {
            args.Add("--lang");
            args.Add(Vrc2GtavLocalization.ToCliLanguageArg(langMode));
            args.Add(opts.ImportFaceBlendshapes ? "--import-face-blendshapes" : "--no-import-face-blendshapes");
            args.Add(opts.ImportBodyBlendshapes ? "--import-body-blendshapes" : "--no-import-body-blendshapes");
            args.Add(opts.EyeBlink ? "--eye-blink" : "--no-eye-blink");
            args.Add(opts.BloodDecals ? "--blood-decals" : "--no-blood-decals");
            args.Add("--blendshapes-source");
            args.Add(SourceModes[Mathf.Clamp(opts.BlendshapesSourceIdx, 0, SourceModes.Length - 1)]);
            args.Add("--physbones-source");
            args.Add(SourceModes[Mathf.Clamp(opts.PhysbonesSourceIdx, 0, SourceModes.Length - 1)]);
            args.Add("--atlas-size");
            args.Add(GetAtlasResolution(opts).ToString(CultureInfo.InvariantCulture));
            int normPx = GetNormalResolution(opts);
            if (normPx > 0)
            {
                args.Add("--normal-size");
                args.Add(normPx.ToString(CultureInfo.InvariantCulture));
            }
            int secPx = GetSecondaryResolution(opts);
            if (secPx > 0)
            {
                args.Add("--secondary-atlas-size");
                args.Add(secPx.ToString(CultureInfo.InvariantCulture));
            }
            if (textureOverrides != null && textureOverrides.Count > 0)
            {
                bool useWsl = Vrc2GtavConfigDiscovery.DetermineShouldUseWsl(paths, paths.BackendMode);
                foreach (var pair in textureOverrides)
                {
                    if (string.IsNullOrWhiteSpace(pair.Key) || string.IsNullOrWhiteSpace(pair.Value)) continue;
                    string texArg = useWsl
                        ? Vrc2GtavIniAndWsl.ToWslPathIfWindows(pair.Value)
                        : Vrc2GtavIniAndWsl.SanitizePathForWindows(pair.Value);
                    args.Add("--texture-override");
                    args.Add(pair.Key + "=" + (string.IsNullOrEmpty(texArg) ? pair.Value : texArg));
                }
            }
            if (!opts.DeployToMods) args.Add("--no-deploy");
            if (opts.EyeBlink && opts.EyeBlinkStrength > 0.01f)
            {
                args.Add("--eye-blink-strength");
                args.Add(opts.EyeBlinkStrength.ToString("0.00", CultureInfo.InvariantCulture));
            }
            args.Add("--mouth-open-strength");
            args.Add(Mathf.Clamp01(opts.MouthOpenStrength).ToString("0.00", CultureInfo.InvariantCulture));
            if (opts.PhysbonesMarshmallow) args.Add("--physbones-marshmallow");
            if (opts.ForceReextract) args.Add("--force-reextract");
            if (!string.IsNullOrWhiteSpace(opts.BlendshapesCfg)) { args.Add("--blendshapes-cfg"); args.Add(opts.BlendshapesCfg); }
            if (!string.IsNullOrWhiteSpace(opts.PhysbonesCfg)) { args.Add("--physbones-cfg"); args.Add(opts.PhysbonesCfg); }
        }

        public static ExecutionCommandSpec BuildExportCommand(
            Vrc2GtavToolPaths paths,
            ResolvedAvatarSource avatar,
            Vrc2GtavExportOptions opts,
            UiLanguageMode langMode,
            IReadOnlyDictionary<string, string> textureOverrides = null)
        {
            var args = new List<string>
            {
                "--source", avatar.SourcePath ?? string.Empty,
                "--target-ped", BuildTargetPedCsv(opts)
            };
            AppendSharedExportFlags(args, paths, opts, langMode, textureOverrides);

            string chosenName = !string.IsNullOrWhiteSpace(opts.AvatarNameOverride)
                ? opts.AvatarNameOverride.Trim()
                : avatar.AvatarName;
            if (!string.IsNullOrWhiteSpace(chosenName))
            {
                args.Add("--avatar-name");
                args.Add(chosenName);
            }
            if (!string.IsNullOrWhiteSpace(opts.FaceBlendshapesAnim))
            {
                args.Add("--face-anim");
                args.Add(opts.FaceBlendshapesAnim);
            }

            return BuildExecutionSpec(
                paths, paths.BackendMode, "scripts/common_tools/universal_gtav_builder.py", args);
        }

        public static ExecutionCommandSpec BuildMultiSlotExportCommand(
            Vrc2GtavToolPaths paths,
            IList<ProtagonistAvatarSlot> activeSlots,
            Vrc2GtavExportOptions opts,
            UiLanguageMode langMode,
            IReadOnlyDictionary<string, string> textureOverrides = null,
            bool writeManifest = false)
        {
            bool useWsl = Vrc2GtavConfigDiscovery.DetermineShouldUseWsl(paths, paths.BackendMode);
            string baseRepo = useWsl ? paths.RepoRoot : Vrc2GtavIniAndWsl.SanitizePathForWindows(paths.RepoRoot);
            string cfgDir = string.IsNullOrWhiteSpace(baseRepo) ? Path.GetTempPath() : Path.Combine(baseRepo, "configs");
            string slotsJsonPath = Path.Combine(cfgDir, "active_multi_slots.json");

            if (writeManifest && activeSlots != null && activeSlots.Count > 0)
            {
                var slotRows = new List<string>(activeSlots.Count);
                for (int i = 0; i < activeSlots.Count; i++)
                {
                    ProtagonistAvatarSlot slot = activeSlots[i];
                    string src = slot.Avatar.SourcePath ?? string.Empty;
                    string normSrc = useWsl ? Vrc2GtavIniAndWsl.ToWslPathIfWindows(src) : Vrc2GtavIniAndWsl.SanitizePathForWindows(src);
                    string avName = !string.IsNullOrWhiteSpace(slot.AvatarNameOverride) ? slot.AvatarNameOverride.Trim() : slot.Avatar.AvatarName;
                    string faceAnim = slot.FaceBlendshapesAnim ?? string.Empty;
                    string normAnim = string.IsNullOrWhiteSpace(faceAnim) ? string.Empty
                        : (useWsl ? Vrc2GtavIniAndWsl.ToWslPathIfWindows(faceAnim) : Vrc2GtavIniAndWsl.SanitizePathForWindows(faceAnim));
                    slotRows.Add("    {\"target_ped\": \"" + EscapeJson(slot.PedModel) + "\", \"source\": \"" + EscapeJson(normSrc)
                        + "\", \"avatar_name\": \"" + EscapeJson(avName) + "\", \"face_anim\": \"" + EscapeJson(normAnim) + "\"}");
                }
                Directory.CreateDirectory(cfgDir);
                File.WriteAllText(slotsJsonPath, "{\n  \"slots\": [\n" + string.Join(",\n", slotRows) + "\n  ]\n}\n");
            }

            var args = new List<string> { "--slots-json", slotsJsonPath };
            AppendSharedExportFlags(args, paths, opts, langMode, textureOverrides);
            return BuildExecutionSpec(paths, paths.BackendMode, "scripts/common_tools/universal_gtav_builder.py", args);
        }

        public static ExecutionCommandSpec BuildRestoreCommand(
            Vrc2GtavToolPaths paths, UiLanguageMode langMode, string pedCsvOrAll)
        {
            var args = new List<string> { "--lang", Vrc2GtavLocalization.ToCliLanguageArg(langMode) };
            if (string.Equals(pedCsvOrAll, "all", StringComparison.OrdinalIgnoreCase)) args.Add("--restore-all");
            else { args.Add("--restore-peds"); args.Add(pedCsvOrAll ?? string.Empty); }
            return BuildExecutionSpec(paths, paths.BackendMode, "scripts/common_tools/universal_gtav_builder.py", args);
        }

        public static ExecutionCommandSpec BuildExecutionSpec(
            Vrc2GtavToolPaths paths, BackendExecutionMode mode, string scriptRelativeToRepo, IReadOnlyList<string> args)
        {
            bool useWsl = Vrc2GtavConfigDiscovery.DetermineShouldUseWsl(paths, mode);
            string winRepo = useWsl ? paths.RepoRoot : Vrc2GtavIniAndWsl.SanitizePathForWindows(paths.RepoRoot);
            string winScript = string.IsNullOrWhiteSpace(winRepo)
                ? scriptRelativeToRepo
                : Path.GetFullPath(Path.Combine(winRepo, scriptRelativeToRepo));
            string scriptArg = useWsl ? Vrc2GtavIniAndWsl.ToWslPathIfWindows(winScript) : winScript;

            var fullArgs = new List<string> { "-u", scriptArg };
            if (args != null)
            {
                for (int i = 0; i < args.Count; i++) fullArgs.Add(args[i]);
            }
            return BuildPythonCommandSpec(paths, mode, fullArgs);
        }

        public static ExecutionCommandSpec BuildPythonCommandSpec(
            Vrc2GtavToolPaths paths, BackendExecutionMode mode, IReadOnlyList<string> pythonArgs)
        {
            bool useWsl = Vrc2GtavConfigDiscovery.DetermineShouldUseWsl(paths, mode);
            if (!useWsl)
            {
                string winRepo = Vrc2GtavIniAndWsl.SanitizePathForWindows(paths.RepoRoot);
                string pyExe = Vrc2GtavIniAndWsl.SanitizePathForWindows(paths.PythonExe);
                if (string.IsNullOrWhiteSpace(pyExe))
                {
                    pyExe = Vrc2GtavConfigDiscovery.DetectPython(winRepo, BackendExecutionMode.WindowsNative, false);
                }
                if (string.IsNullOrWhiteSpace(pyExe)) pyExe = "python";

                string errMsg = string.Empty;
                var quoted = new List<string>(pythonArgs.Count);
                for (int i = 0; i < pythonArgs.Count; i++)
                {
                    string raw = pythonArgs[i] ?? string.Empty;
                    string argVal = raw;
                    if (Vrc2GtavIniAndWsl.IsWslMountPath(raw))
                    {
                        argVal = Vrc2GtavIniAndWsl.SanitizePathForWindows(raw);
                    }
                    else if (Vrc2GtavIniAndWsl.IsLinuxStylePath(raw))
                    {
                        errMsg = "Windows Native command cannot include Linux path: " + raw;
                        argVal = string.Empty;
                    }
                    else
                    {
                        int eqIdx = raw.IndexOf('=');
                        if (eqIdx > 0)
                        {
                            string rhs = raw.Substring(eqIdx + 1);
                            if (Vrc2GtavIniAndWsl.IsWslMountPath(rhs))
                                argVal = raw.Substring(0, eqIdx + 1) + Vrc2GtavIniAndWsl.SanitizePathForWindows(rhs);
                            else if (Vrc2GtavIniAndWsl.IsLinuxStylePath(rhs))
                            {
                                errMsg = "Windows Native command cannot include Linux path: " + rhs;
                                argVal = string.Empty;
                            }
                        }
                    }
                    quoted.Add(Vrc2GtavIniAndWsl.QuoteWindowsArg(argVal));
                }
                string joinedArgs = string.Join(" ", quoted);
                return new ExecutionCommandSpec
                {
                    FileName = pyExe,
                    Arguments = joinedArgs,
                    WorkingDirectory = winRepo,
                    UsesWsl = false,
                    PreviewCommand = Vrc2GtavIniAndWsl.QuoteWindowsArg(pyExe) + " " + joinedArgs,
                    ValidationError = errMsg
                };
            }

            string wslPy = Vrc2GtavIniAndWsl.IsLinuxStylePath(paths.PythonExe)
                ? paths.PythonExe
                : Vrc2GtavIniAndWsl.DetectWslPython(paths.RepoRoot);
            if (string.IsNullOrEmpty(wslPy)) wslPy = "python3";

            var wslParts = new List<string> { "-e", Vrc2GtavIniAndWsl.QuoteWindowsArg(wslPy) };
            for (int i = 0; i < pythonArgs.Count; i++)
            {
                wslParts.Add(Vrc2GtavIniAndWsl.QuoteWindowsArg(Vrc2GtavIniAndWsl.ConvertArgPathForWsl(pythonArgs[i])));
            }
            string wslArgs = string.Join(" ", wslParts);
            return new ExecutionCommandSpec
            {
                FileName = "wsl.exe",
                Arguments = wslArgs,
                WorkingDirectory = paths.RepoRoot,
                UsesWsl = true,
                PreviewCommand = "wsl.exe " + wslArgs,
                ValidationError = string.Empty
            };
        }

        public static List<ProcessStepRequest> BuildDownloadAndSetupSteps(
            Vrc2GtavToolPaths paths,
            UiLanguageMode langMode,
            bool fullSetupWithGtav)
        {
            var steps = new List<ProcessStepRequest>();
            bool useWsl = Vrc2GtavConfigDiscovery.DetermineShouldUseWsl(paths, paths.BackendMode);
            string safeRepo = useWsl ? paths.RepoRoot : Vrc2GtavIniAndWsl.SanitizePathForWindows(paths.RepoRoot);
            string reqPath = Path.Combine(safeRepo, "requirements.txt");
            if (File.Exists(reqPath))
            {
                var pipArgs = new List<string> { "-m", "pip", "install", "--disable-pip-version-check", "-r", reqPath };
                steps.Add(new ProcessStepRequest
                {
                    StepTitle = "Python packages (requirements.txt)",
                    Command = BuildPythonCommandSpec(paths, paths.BackendMode, pipArgs)
                });
            }

            string cliLang = Vrc2GtavLocalization.ToCliLanguageArg(langMode);
            if (fullSetupWithGtav)
            {
                Vrc2GtavConfigDiscovery.SaveToConfig(safeRepo, paths, cliLang);
                var setupArgs = new List<string>
                {
                    "--setup", "--non-interactive",
                    "--download-blender", "--download-rage",
                    "--lang", cliLang,
                    "--gtav-root", useWsl ? paths.GtavRoot : Vrc2GtavIniAndWsl.SanitizePathForWindows(paths.GtavRoot),
                    "--unity-assets", Vrc2GtavConfigDiscovery.GetDefaultUnityAssetsPath()
                };
                if (Vrc2GtavConfigDiscovery.IsValidBlender(paths.BlenderExe))
                {
                    setupArgs.Add("--blender");
                    setupArgs.Add(paths.BlenderExe);
                }
                if (Vrc2GtavConfigDiscovery.IsValidRage(paths.RageExe, paths.BackendMode))
                {
                    setupArgs.Add("--rage");
                    setupArgs.Add(paths.RageExe);
                }
                if (!useWsl && Vrc2GtavConfigDiscovery.IsValidPython(paths.PythonExe, paths.BackendMode, out _))
                {
                    setupArgs.Add("--python");
                    setupArgs.Add(paths.PythonExe);
                }
                steps.Add(new ProcessStepRequest
                {
                    StepTitle = Vrc2GtavLocalization.Get(langMode, "tools.download_setup"),
                    Command = BuildExecutionSpec(paths, paths.BackendMode, "run_mod_manager.py", setupArgs)
                });
            }
            else
            {
                var toolsOnlyPy = new List<string>
                {
                    "-c",
                    "from scripts.common_tools import avatar_archive_helper as a; a.download_and_install_blender(); a.download_and_install_rage()"
                };
                steps.Add(new ProcessStepRequest
                {
                    StepTitle = "Download Blender + rage-cli",
                    Command = BuildPythonCommandSpec(paths, paths.BackendMode, toolsOnlyPy)
                });
            }
            return steps;
        }

        public static void LoadEditorState(
            string prefix, Vrc2GtavToolPaths paths, out UiLanguageMode lang, out bool autoSave, Vrc2GtavExportOptions opts = null)
        {
            lang = (UiLanguageMode)EditorPrefs.GetInt(prefix + "Language", 0);
            autoSave = EditorPrefs.GetBool(prefix + "AutoSave", true);
            paths.RepoRoot = EditorPrefs.GetString(prefix + "RepoRoot", string.Empty);
            paths.RepoRootManualOverride = EditorPrefs.GetBool(prefix + "RepoRootManual", false);
            paths.GtavRoot = EditorPrefs.GetString(prefix + "GtavRoot", string.Empty);
            paths.BlenderExe = EditorPrefs.GetString(prefix + "BlenderExe", string.Empty);
            paths.RageExe = EditorPrefs.GetString(prefix + "RageExe", string.Empty);
            paths.PythonExe = EditorPrefs.GetString(prefix + "PythonExe", string.Empty);
            paths.BackendMode = (BackendExecutionMode)EditorPrefs.GetInt(prefix + "BackendMode", 0);

            string bundledToolchain = Vrc2GtavConfigDiscovery.GetBundledToolchainRoot();
            bool migratedToBundled = EditorPrefs.GetBool(prefix + "PreferBundledToolchain", false);
            if ((!migratedToBundled || !paths.RepoRootManualOverride) && Vrc2GtavConfigDiscovery.IsValidRepoRoot(bundledToolchain))
            {
                paths.RepoRootManualOverride = false;
                if (!string.Equals(paths.RepoRoot?.TrimEnd('\\', '/'), bundledToolchain.TrimEnd('\\', '/'), StringComparison.OrdinalIgnoreCase))
                {
                    paths.RepoRoot = bundledToolchain;
                    paths.RageExe = string.Empty;
                }
                EditorPrefs.SetBool(prefix + "PreferBundledToolchain", true);
            }
            if (opts != null)
            {
                opts.PerProtagonistSlots = EditorPrefs.GetBool(prefix + "PerProtagonistSlots", false);
                opts.EyeBlinkStrength = Mathf.Clamp01(EditorPrefs.GetFloat(prefix + "EyeBlinkStrength", 0f));
                opts.MouthOpenStrength = Mathf.Clamp01(EditorPrefs.GetFloat(prefix + "MouthOpenStrength", 0.35f));
                opts.FaceBlendshapesAnim = EditorPrefs.GetString(prefix + "FaceBlendshapesAnim", string.Empty);
                opts.AtlasResolutionIdx = EditorPrefs.GetInt(prefix + "AtlasResIdx", 2);
                opts.NormalResolutionIdx = EditorPrefs.GetInt(prefix + "NormalResIdx", 0);
                opts.SecondaryResolutionIdx = EditorPrefs.GetInt(prefix + "SecondaryResIdx", 0);
            }
        }

        public static void SaveEditorState(
            string prefix, Vrc2GtavToolPaths paths, UiLanguageMode lang, bool autoSave, Vrc2GtavExportOptions opts = null)
        {
            EditorPrefs.SetInt(prefix + "Language", (int)lang);
            EditorPrefs.SetBool(prefix + "AutoSave", autoSave);
            EditorPrefs.SetString(prefix + "RepoRoot", paths.RepoRoot ?? string.Empty);
            EditorPrefs.SetBool(prefix + "RepoRootManual", paths.RepoRootManualOverride);
            EditorPrefs.SetString(prefix + "GtavRoot", paths.GtavRoot ?? string.Empty);
            EditorPrefs.SetString(prefix + "BlenderExe", paths.BlenderExe ?? string.Empty);
            EditorPrefs.SetString(prefix + "RageExe", paths.RageExe ?? string.Empty);
            EditorPrefs.SetString(prefix + "PythonExe", paths.PythonExe ?? string.Empty);
            EditorPrefs.SetInt(prefix + "BackendMode", (int)paths.BackendMode);
            if (opts != null)
            {
                EditorPrefs.SetBool(prefix + "PerProtagonistSlots", opts.PerProtagonistSlots);
                EditorPrefs.SetFloat(prefix + "EyeBlinkStrength", Mathf.Clamp01(opts.EyeBlinkStrength));
                EditorPrefs.SetFloat(prefix + "MouthOpenStrength", Mathf.Clamp01(opts.MouthOpenStrength));
                EditorPrefs.SetString(prefix + "FaceBlendshapesAnim", opts.FaceBlendshapesAnim ?? string.Empty);
                EditorPrefs.SetInt(prefix + "AtlasResIdx", opts.AtlasResolutionIdx);
                EditorPrefs.SetInt(prefix + "NormalResIdx", opts.NormalResolutionIdx);
                EditorPrefs.SetInt(prefix + "SecondaryResIdx", opts.SecondaryResolutionIdx);
            }
        }
    }
}
