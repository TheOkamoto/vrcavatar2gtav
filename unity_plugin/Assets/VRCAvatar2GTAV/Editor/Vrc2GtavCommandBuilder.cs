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
        public bool UserEnabledPerSlotForSingle;
        public bool DeployToMods = true;
        public string LastSingleTargetPed = "player_zero";
        public readonly Vrc2GtavSlotProfile Shared = new Vrc2GtavSlotProfile();
    }

    internal static class Vrc2GtavCommandBuilder
    {
        public static readonly string[] SourceModes = { "auto", "unity", "cfg" };
        public static readonly int[] AtlasResolutions = { 512, 1024, 2048, 4096 };
        public static readonly int[] NormalResolutions = { 0, 64, 256, 512, 1024 };
        public static readonly int[] SecondaryResolutions = { 0, 512, 1024, 2048 };

        public static int GetAtlasResolution(Vrc2GtavSlotProfile prof)
        {
            int idx = prof != null ? prof.AtlasResolutionIdx : 2;
            return AtlasResolutions[Mathf.Clamp(idx, 0, AtlasResolutions.Length - 1)];
        }

        public static int GetNormalResolution(Vrc2GtavSlotProfile prof)
        {
            int idx = prof != null ? prof.NormalResolutionIdx : 0;
            return NormalResolutions[Mathf.Clamp(idx, 0, NormalResolutions.Length - 1)];
        }

        public static int GetSecondaryResolution(Vrc2GtavSlotProfile prof)
        {
            int idx = prof != null ? prof.SecondaryResolutionIdx : 0;
            return SecondaryResolutions[Mathf.Clamp(idx, 0, SecondaryResolutions.Length - 1)];
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

        private static string NormalizeBackendPath(string value, bool useWsl)
        {
            if (string.IsNullOrWhiteSpace(value)) return string.Empty;
            return useWsl
                ? Vrc2GtavIniAndWsl.ToWslPathIfWindows(value)
                : Vrc2GtavIniAndWsl.SanitizePathForWindows(value);
        }

        private static void AppendProfileExportFlags(
            List<string> args,
            Vrc2GtavToolPaths paths,
            Vrc2GtavSlotProfile prof,
            bool deployToMods,
            UiLanguageMode langMode,
            IReadOnlyDictionary<string, string> textureOverrides)
        {
            args.Add("--lang");
            args.Add(Vrc2GtavLocalization.ToCliLanguageArg(langMode));
            args.Add(prof.ImportFaceBlendshapes ? "--import-face-blendshapes" : "--no-import-face-blendshapes");
            args.Add(prof.ImportBodyBlendshapes ? "--import-body-blendshapes" : "--no-import-body-blendshapes");
            args.Add(prof.EyeBlink ? "--eye-blink" : "--no-eye-blink");
            args.Add(prof.BloodDecals ? "--blood-decals" : "--no-blood-decals");
            args.Add("--blendshapes-source");
            args.Add(SourceModes[Mathf.Clamp(prof.BlendshapesSourceIdx, 0, SourceModes.Length - 1)]);
            args.Add("--physbones-source");
            args.Add(SourceModes[Mathf.Clamp(prof.PhysbonesSourceIdx, 0, SourceModes.Length - 1)]);
            args.Add("--atlas-size");
            args.Add(GetAtlasResolution(prof).ToString(CultureInfo.InvariantCulture));
            int normPx = GetNormalResolution(prof);
            if (normPx > 0)
            {
                args.Add("--normal-size");
                args.Add(normPx.ToString(CultureInfo.InvariantCulture));
            }
            int secPx = GetSecondaryResolution(prof);
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
                    string texArg = NormalizeBackendPath(pair.Value, useWsl);
                    args.Add("--texture-override");
                    args.Add(pair.Key + "=" + (string.IsNullOrEmpty(texArg) ? pair.Value : texArg));
                }
            }
            if (!deployToMods) args.Add("--no-deploy");
            if (prof.EyeBlink && prof.EyeBlinkStrength > 0.01f)
            {
                args.Add("--eye-blink-strength");
                args.Add(prof.EyeBlinkStrength.ToString("0.00", CultureInfo.InvariantCulture));
            }
            args.Add("--mouth-open-strength");
            args.Add(Mathf.Clamp01(prof.MouthOpenStrength).ToString("0.00", CultureInfo.InvariantCulture));
            if (prof.PhysbonesMarshmallow) args.Add("--physbones-marshmallow");
            if (prof.ForceReextract) args.Add("--force-reextract");
            if (!string.IsNullOrWhiteSpace(prof.BlendshapesCfg)) { args.Add("--blendshapes-cfg"); args.Add(prof.BlendshapesCfg); }
            if (!string.IsNullOrWhiteSpace(prof.PhysbonesCfg)) { args.Add("--physbones-cfg"); args.Add(prof.PhysbonesCfg); }
        }

        public static ExecutionCommandSpec BuildExportCommand(
            Vrc2GtavToolPaths paths,
            ResolvedAvatarSource avatar,
            Vrc2GtavExportOptions opts,
            UiLanguageMode langMode,
            IReadOnlyDictionary<string, string> textureOverrides = null)
        {
            Vrc2GtavSlotProfile prof = opts.Shared;
            var args = new List<string>
            {
                "--source", avatar.SourcePath ?? string.Empty,
                "--target-ped", BuildTargetPedCsv(opts)
            };
            AppendProfileExportFlags(args, paths, prof, opts.DeployToMods, langMode, textureOverrides);

            string chosenName = !string.IsNullOrWhiteSpace(prof.AvatarNameOverride)
                ? prof.AvatarNameOverride.Trim()
                : avatar.AvatarName;
            if (!string.IsNullOrWhiteSpace(chosenName))
            {
                args.Add("--avatar-name");
                args.Add(chosenName);
            }
            if (!string.IsNullOrWhiteSpace(prof.FaceBlendshapesAnim))
            {
                args.Add("--face-anim");
                args.Add(prof.FaceBlendshapesAnim);
            }

            return BuildExecutionSpec(
                paths, paths.BackendMode, "scripts/common_tools/universal_gtav_builder.py", args);
        }

        private static string BuildSlotJsonEntry(ProtagonistAvatarSlot slot, int sharedSecPx, bool useWsl)
        {
            Vrc2GtavSlotProfile prof = slot.Profile ?? new Vrc2GtavSlotProfile();
            string normSrc = NormalizeBackendPath(slot.Avatar?.SourcePath, useWsl);
            string avName = !string.IsNullOrWhiteSpace(prof.AvatarNameOverride)
                ? prof.AvatarNameOverride.Trim()
                : (slot.Avatar?.AvatarName ?? string.Empty);
            string bsMode = SourceModes[Mathf.Clamp(prof.BlendshapesSourceIdx, 0, SourceModes.Length - 1)];
            string pbMode = SourceModes[Mathf.Clamp(prof.PhysbonesSourceIdx, 0, SourceModes.Length - 1)];

            var fields = new List<string>
            {
                "\"target_ped\": \"" + EscapeJson(slot.PedModel) + "\"",
                "\"source\": \"" + EscapeJson(normSrc) + "\"",
                "\"avatar_name\": \"" + EscapeJson(avName) + "\"",
                "\"atlas_size\": " + GetAtlasResolution(prof).ToString(CultureInfo.InvariantCulture),
                "\"normal_size\": " + GetNormalResolution(prof).ToString(CultureInfo.InvariantCulture),
                "\"secondary_atlas_size\": " + sharedSecPx.ToString(CultureInfo.InvariantCulture),
                "\"import_face_blendshapes\": " + (prof.ImportFaceBlendshapes ? "true" : "false"),
                "\"import_body_blendshapes\": " + (prof.ImportBodyBlendshapes ? "true" : "false"),
                "\"eye_blink\": " + (prof.EyeBlink ? "true" : "false"),
                "\"mouth_open_strength\": " + Mathf.Clamp01(prof.MouthOpenStrength).ToString("0.00", CultureInfo.InvariantCulture),
                "\"blood_decals\": " + (prof.BloodDecals ? "true" : "false"),
                "\"blendshapes_source\": \"" + bsMode + "\"",
                "\"physbones_source\": \"" + pbMode + "\"",
                "\"blendshapes_cfg\": \"" + EscapeJson(NormalizeBackendPath(prof.BlendshapesCfg, useWsl)) + "\"",
                "\"face_anim\": \"" + EscapeJson(NormalizeBackendPath(prof.FaceBlendshapesAnim, useWsl)) + "\"",
                "\"physbones_cfg\": \"" + EscapeJson(NormalizeBackendPath(prof.PhysbonesCfg, useWsl)) + "\"",
                "\"physbones_marshmallow\": " + (prof.PhysbonesMarshmallow ? "true" : "false"),
                "\"force_reextract\": " + (prof.ForceReextract ? "true" : "false")
            };
            if (prof.EyeBlink && prof.EyeBlinkStrength > 0.01f)
            {
                fields.Add("\"eye_blink_strength\": " + prof.EyeBlinkStrength.ToString("0.00", CultureInfo.InvariantCulture));
            }
            var texOvr = slot.Textures?.BuildTextureOverridesMap();
            if (texOvr != null && texOvr.Count > 0)
            {
                var texItems = new List<string>(texOvr.Count);
                foreach (var pair in texOvr)
                {
                    if (string.IsNullOrWhiteSpace(pair.Key) || string.IsNullOrWhiteSpace(pair.Value)) continue;
                    string texArg = NormalizeBackendPath(pair.Value, useWsl);
                    texItems.Add("\"" + EscapeJson(pair.Key) + "\": \"" + EscapeJson(string.IsNullOrEmpty(texArg) ? pair.Value : texArg) + "\"");
                }
                if (texItems.Count > 0) fields.Add("\"texture_overrides\": {" + string.Join(", ", texItems) + "}");
            }
            return "    {" + string.Join(", ", fields) + "}";
        }

        public static ExecutionCommandSpec BuildMultiSlotExportCommand(
            Vrc2GtavToolPaths paths,
            IList<ProtagonistAvatarSlot> activeSlots,
            Vrc2GtavExportOptions opts,
            UiLanguageMode langMode,
            bool writeManifest = false)
        {
            bool useWsl = Vrc2GtavConfigDiscovery.DetermineShouldUseWsl(paths, paths.BackendMode);
            string baseRepo = useWsl ? paths.RepoRoot : Vrc2GtavIniAndWsl.SanitizePathForWindows(paths.RepoRoot);
            string cfgDir = string.IsNullOrWhiteSpace(baseRepo) ? Path.GetTempPath() : Path.Combine(baseRepo, "configs");
            string slotsJsonPath = Path.Combine(cfgDir, "active_multi_slots.json");
            int sharedSecPx = GetSecondaryResolution(opts.Shared);

            if (writeManifest && activeSlots != null && activeSlots.Count > 0)
            {
                var slotRows = new List<string>(activeSlots.Count);
                for (int i = 0; i < activeSlots.Count; i++)
                {
                    slotRows.Add(BuildSlotJsonEntry(activeSlots[i], sharedSecPx, useWsl));
                }
                Directory.CreateDirectory(cfgDir);
                File.WriteAllText(slotsJsonPath, "{\n  \"slots\": [\n" + string.Join(",\n", slotRows) + "\n  ]\n}\n");
            }

            var args = new List<string>
            {
                "--slots-json", slotsJsonPath,
                "--lang", Vrc2GtavLocalization.ToCliLanguageArg(langMode)
            };
            if (sharedSecPx > 0)
            {
                args.Add("--secondary-atlas-size");
                args.Add(sharedSecPx.ToString(CultureInfo.InvariantCulture));
            }
            if (!opts.DeployToMods) args.Add("--no-deploy");
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
                opts.Shared.EyeBlinkStrength = Mathf.Clamp01(EditorPrefs.GetFloat(prefix + "EyeBlinkStrength", 0f));
                opts.Shared.MouthOpenStrength = Mathf.Clamp01(EditorPrefs.GetFloat(prefix + "MouthOpenStrength", 0.70f));
                opts.Shared.FaceBlendshapesAnim = EditorPrefs.GetString(prefix + "FaceBlendshapesAnim", string.Empty);
                opts.Shared.AtlasResolutionIdx = EditorPrefs.GetInt(prefix + "AtlasResIdx", 2);
                opts.Shared.NormalResolutionIdx = EditorPrefs.GetInt(prefix + "NormalResIdx", 0);
                opts.Shared.SecondaryResolutionIdx = EditorPrefs.GetInt(prefix + "SecondaryResIdx", 0);
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
                EditorPrefs.SetFloat(prefix + "EyeBlinkStrength", Mathf.Clamp01(opts.Shared.EyeBlinkStrength));
                EditorPrefs.SetFloat(prefix + "MouthOpenStrength", Mathf.Clamp01(opts.Shared.MouthOpenStrength));
                EditorPrefs.SetString(prefix + "FaceBlendshapesAnim", opts.Shared.FaceBlendshapesAnim ?? string.Empty);
                EditorPrefs.SetInt(prefix + "AtlasResIdx", opts.Shared.AtlasResolutionIdx);
                EditorPrefs.SetInt(prefix + "NormalResIdx", opts.Shared.NormalResolutionIdx);
                EditorPrefs.SetInt(prefix + "SecondaryResIdx", opts.Shared.SecondaryResolutionIdx);
            }
        }
    }
}
