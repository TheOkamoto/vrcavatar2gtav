using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Vrc2Gtav.Editor
{
    internal enum AvatarSourceKind
    {
        None = 0,
        SceneGameObject = 1,
        PrefabAsset = 2,
        ArchiveOrFile = 3
    }

    internal sealed class ResolvedAvatarSource
    {
        public AvatarSourceKind Kind = AvatarSourceKind.None;
        public string AvatarName = string.Empty;
        public string SourcePath = string.Empty;
        public string SceneAssetPath = string.Empty;
        public bool IsSceneDirty;
        public UnityEngine.Object ObjectRef;

        public bool IsValid =>
            Kind != AvatarSourceKind.None
            && !string.IsNullOrWhiteSpace(SourcePath)
            && (File.Exists(SourcePath) || Directory.Exists(SourcePath));
    }

    internal static class Vrc2GtavAvatarResolver
    {
        private static readonly HashSet<string> SupportedExtensions = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            ".zip",
            ".unitypackage",
            ".prefab",
            ".unity"
        };

        public static ResolvedAvatarSource ResolveObject(UnityEngine.Object obj)
        {
            if (obj == null) return new ResolvedAvatarSource();

            if (obj is GameObject go)
            {
                if (EditorUtility.IsPersistent(go))
                {
                    string assetPath = AssetDatabase.GetAssetPath(go);
                    string fullPath = ToAbsoluteProjectPath(assetPath);
                    return new ResolvedAvatarSource
                    {
                        Kind = AvatarSourceKind.PrefabAsset,
                        AvatarName = go.name,
                        SourcePath = fullPath,
                        ObjectRef = go
                    };
                }

                GameObject rootAvatar = WalkToAvatarRoot(go);
                Scene scene = rootAvatar.scene;
                string sceneFullPath = ToAbsoluteProjectPath(scene.path);
                return new ResolvedAvatarSource
                {
                    Kind = AvatarSourceKind.SceneGameObject,
                    AvatarName = rootAvatar.name,
                    SourcePath = sceneFullPath,
                    SceneAssetPath = scene.path,
                    IsSceneDirty = scene.isDirty,
                    ObjectRef = rootAvatar
                };
            }

            if (obj is SceneAsset sceneAsset)
            {
                string assetPath = AssetDatabase.GetAssetPath(sceneAsset);
                return new ResolvedAvatarSource
                {
                    Kind = AvatarSourceKind.ArchiveOrFile,
                    AvatarName = string.Empty,
                    SourcePath = ToAbsoluteProjectPath(assetPath),
                    SceneAssetPath = assetPath,
                    ObjectRef = sceneAsset
                };
            }

            string otherPath = AssetDatabase.GetAssetPath(obj);
            if (!string.IsNullOrEmpty(otherPath))
            {
                return ResolveExternalPath(ToAbsoluteProjectPath(otherPath));
            }

            return new ResolvedAvatarSource();
        }

        public static ResolvedAvatarSource ResolveExternalPath(string path)
        {
            if (string.IsNullOrWhiteSpace(path)) return new ResolvedAvatarSource();
            string fullPath = Path.GetFullPath(path);

            if (fullPath.EndsWith(".prefab", StringComparison.OrdinalIgnoreCase) && File.Exists(fullPath))
            {
                GameObject loaded = TryLoadAssetAtDiskPath<GameObject>(fullPath);
                return new ResolvedAvatarSource
                {
                    Kind = AvatarSourceKind.PrefabAsset,
                    AvatarName = loaded != null ? loaded.name : Path.GetFileNameWithoutExtension(fullPath),
                    SourcePath = fullPath,
                    ObjectRef = loaded
                };
            }

            if (fullPath.EndsWith(".unity", StringComparison.OrdinalIgnoreCase) && File.Exists(fullPath))
            {
                SceneAsset loadedScene = TryLoadAssetAtDiskPath<SceneAsset>(fullPath);
                return new ResolvedAvatarSource
                {
                    Kind = AvatarSourceKind.ArchiveOrFile,
                    AvatarName = Path.GetFileNameWithoutExtension(fullPath),
                    SourcePath = fullPath,
                    SceneAssetPath = ToAssetRelativePath(fullPath),
                    ObjectRef = loadedScene
                };
            }

            string ext = Path.GetExtension(fullPath);
            if (Directory.Exists(fullPath) || (File.Exists(fullPath) && SupportedExtensions.Contains(ext)))
            {
                return new ResolvedAvatarSource
                {
                    Kind = AvatarSourceKind.ArchiveOrFile,
                    AvatarName = Path.GetFileNameWithoutExtension(fullPath),
                    SourcePath = fullPath
                };
            }

            return new ResolvedAvatarSource();
        }

        public static bool CanAcceptDrag(UnityEngine.Object[] refs, string[] paths)
        {
            if (refs != null)
            {
                for (int i = 0; i < refs.Length; i++)
                {
                    if (refs[i] is GameObject || refs[i] is SceneAsset) return true;
                    string assetPath = AssetDatabase.GetAssetPath(refs[i]);
                    if (!string.IsNullOrEmpty(assetPath) && SupportedExtensions.Contains(Path.GetExtension(assetPath)))
                    {
                        return true;
                    }
                }
            }

            if (paths != null)
            {
                for (int i = 0; i < paths.Length; i++)
                {
                    string p = paths[i];
                    if (Directory.Exists(p) || SupportedExtensions.Contains(Path.GetExtension(p))) return true;
                }
            }
            return false;
        }

        public static List<GameObject> FindAvatarsInActiveScenes()
        {
            var avatars = new List<GameObject>();
            var seenIds = new HashSet<int>();
            for (int s = 0; s < SceneManager.sceneCount; s++)
            {
                Scene scene = SceneManager.GetSceneAt(s);
                if (!scene.isLoaded) continue;
                GameObject[] roots = scene.GetRootGameObjects();
                for (int r = 0; r < roots.Length; r++)
                {
                    Animator[] animators = roots[r].GetComponentsInChildren<Animator>(true);
                    if (animators.Length == 0) continue;
                    GameObject candidate = WalkToAvatarRoot(animators[0].gameObject);
                    if (seenIds.Add(candidate.GetInstanceID()))
                    {
                        avatars.Add(candidate);
                    }
                }
            }
            return avatars;
        }

        public static GameObject WalkToAvatarRoot(GameObject go)
        {
            if (go == null) return null;
            Transform current = go.transform;
            Transform topAnimator = null;
            while (current != null)
            {
                if (current.GetComponent<Animator>() != null)
                {
                    topAnimator = current;
                }
                current = current.parent;
            }
            if (topAnimator != null) return topAnimator.gameObject;

            Transform topRoot = go.transform;
            while (topRoot.parent != null) topRoot = topRoot.parent;
            return topRoot.gameObject;
        }

        public static string ToAbsoluteProjectPath(string assetRelativePath)
        {
            if (string.IsNullOrWhiteSpace(assetRelativePath)) return string.Empty;
            string projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
            return Path.GetFullPath(Path.Combine(projectRoot, assetRelativePath));
        }

        public static string ToAssetRelativePath(string fullPath)
        {
            string projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
            string normalizedFull = fullPath.Replace('\\', '/');
            string normalizedRoot = projectRoot.Replace('\\', '/').TrimEnd('/') + "/";
            return normalizedFull.StartsWith(normalizedRoot, StringComparison.OrdinalIgnoreCase)
                ? normalizedFull.Substring(normalizedRoot.Length)
                : string.Empty;
        }

        private static T TryLoadAssetAtDiskPath<T>(string fullPath) where T : UnityEngine.Object
        {
            string rel = ToAssetRelativePath(fullPath);
            return string.IsNullOrEmpty(rel) ? null : AssetDatabase.LoadAssetAtPath<T>(rel);
        }

        public static ResolvedAvatarSource HandleDragAndDrop(Rect dropRect, ResolvedAvatarSource current)
        {
            Event evt = Event.current;
            if (!dropRect.Contains(evt.mousePosition)) return current;
            if (evt.type != EventType.DragUpdated && evt.type != EventType.DragPerform) return current;
            if (!CanAcceptDrag(DragAndDrop.objectReferences, DragAndDrop.paths)) return current;

            DragAndDrop.visualMode = DragAndDropVisualMode.Copy;
            ResolvedAvatarSource updated = current;
            if (evt.type == EventType.DragPerform)
            {
                DragAndDrop.AcceptDrag();
                if (DragAndDrop.objectReferences != null && DragAndDrop.objectReferences.Length > 0)
                    updated = ResolveObject(DragAndDrop.objectReferences[0]);
                else if (DragAndDrop.paths != null && DragAndDrop.paths.Length > 0)
                    updated = ResolveExternalPath(DragAndDrop.paths[0]);
                GUI.changed = true;
            }
            evt.Use();
            return updated;
        }

        public static void ShowSceneAvatarMenu(string emptyLabel, Action<ResolvedAvatarSource> onSelected)
        {
            var menu = new GenericMenu();
            List<GameObject> found = FindAvatarsInActiveScenes();
            if (found.Count == 0) menu.AddDisabledItem(new GUIContent(emptyLabel));
            else
            {
                for (int i = 0; i < found.Count; i++)
                {
                    GameObject go = found[i];
                    menu.AddItem(new GUIContent(go.name + " (" + go.scene.name + ")"), false, () =>
                        onSelected?.Invoke(ResolveObject(go)));
                }
            }
            menu.ShowAsContext();
        }
    }

    [Serializable]
    internal sealed class ProtagonistAvatarSlot
    {
        public string PedModel;
        public string LabelKey;
        public string ShortLabelKey;
        public ResolvedAvatarSource Avatar = new ResolvedAvatarSource();
        public readonly Vrc2GtavSlotProfile Profile = new Vrc2GtavSlotProfile();
        public readonly Vrc2GtavTexturesPanel Textures = new Vrc2GtavTexturesPanel();
    }

    internal static class Vrc2GtavMultiSlotUi
    {
        public static List<ProtagonistAvatarSlot> CreateDefaultSlots()
        {
            return new List<ProtagonistAvatarSlot>
            {
                new ProtagonistAvatarSlot { PedModel = "player_zero", LabelKey = "target.michael", ShortLabelKey = "target.short_michael" },
                new ProtagonistAvatarSlot { PedModel = "player_one", LabelKey = "target.franklin", ShortLabelKey = "target.short_franklin" },
                new ProtagonistAvatarSlot { PedModel = "player_two", LabelKey = "target.trevor", ShortLabelKey = "target.short_trevor" }
            };
        }

        public static bool IsSlotEnabled(Vrc2GtavExportOptions opts, string pedModel)
        {
            if (opts == null) return false;
            if (pedModel == "player_zero") return opts.TargetMichael;
            if (pedModel == "player_one") return opts.TargetFranklin;
            if (pedModel == "player_two") return opts.TargetTrevor;
            return false;
        }

        public static List<ProtagonistAvatarSlot> GetEnabledSlots(
            IList<ProtagonistAvatarSlot> slots, Vrc2GtavExportOptions opts)
        {
            var enabled = new List<ProtagonistAvatarSlot>(3);
            if (slots == null) return enabled;
            for (int i = 0; i < slots.Count; i++)
            {
                ProtagonistAvatarSlot slot = slots[i];
                if (slot != null && IsSlotEnabled(opts, slot.PedModel)) enabled.Add(slot);
            }
            return enabled;
        }

        public static bool AreAllEnabledSlotsValid(
            IList<ProtagonistAvatarSlot> slots, Vrc2GtavExportOptions opts)
        {
            List<ProtagonistAvatarSlot> enabled = GetEnabledSlots(slots, opts);
            if (enabled.Count == 0) return false;
            for (int i = 0; i < enabled.Count; i++)
            {
                if (!enabled[i].Avatar.IsValid) return false;
            }
            return true;
        }


        public static void SaveAllDirtyAvatarScenes(
            ResolvedAvatarSource mainAvatar,
            IList<ProtagonistAvatarSlot> slots,
            bool autoSaveScene)
        {
            if (!autoSaveScene) return;
            var savedScenes = new HashSet<Scene>();
            TrySaveAvatarScene(mainAvatar, savedScenes);
            if (slots != null)
            {
                for (int i = 0; i < slots.Count; i++) TrySaveAvatarScene(slots[i]?.Avatar, savedScenes);
            }
        }

        private static void TrySaveAvatarScene(ResolvedAvatarSource avatar, HashSet<Scene> savedScenes)
        {
            if (avatar == null || avatar.Kind != AvatarSourceKind.SceneGameObject) return;
            if (!(avatar.ObjectRef is GameObject go) || !go.scene.IsValid() || !go.scene.isDirty) return;
            if (savedScenes.Add(go.scene)) EditorSceneManager.SaveScene(go.scene);
            avatar.IsSceneDirty = go.scene.isDirty;
        }

        public static ProtagonistAvatarSlot DrawSlotTabStrip(
            UiLanguageMode langMode,
            Vrc2GtavExportOptions opts,
            IList<ProtagonistAvatarSlot> slots,
            ref string activePedModel,
            Action onStateChanged)
        {
            List<ProtagonistAvatarSlot> enabled = GetEnabledSlots(slots, opts);
            if (enabled.Count == 0) return null;

            int activeIdx = 0;
            for (int i = 0; i < enabled.Count; i++)
            {
                if (string.Equals(enabled[i].PedModel, activePedModel, StringComparison.Ordinal))
                {
                    activeIdx = i;
                    break;
                }
            }

            string emptyTxt = Vrc2GtavLocalization.Get(langMode, "slot.tab_empty");
            var labels = new string[enabled.Count];
            for (int i = 0; i < enabled.Count; i++)
            {
                ProtagonistAvatarSlot sl = enabled[i];
                string shortPed = Vrc2GtavLocalization.Get(langMode, sl.ShortLabelKey);
                string avTitle = sl.Avatar.IsValid
                    ? (!string.IsNullOrWhiteSpace(sl.Profile.AvatarNameOverride) ? sl.Profile.AvatarNameOverride.Trim() : sl.Avatar.AvatarName)
                    : emptyTxt;
                if (avTitle.Length > 18) avTitle = avTitle.Substring(0, 16) + "..";
                labels[i] = (sl.Avatar.IsValid ? "[OK] " : "[!] ") + shortPed + ": " + avTitle;
            }

            int nextIdx = GUILayout.Toolbar(activeIdx, labels, GUILayout.Height(26f));
            ProtagonistAvatarSlot activeSlot = enabled[Mathf.Clamp(nextIdx, 0, enabled.Count - 1)];
            activePedModel = activeSlot.PedModel;

            EditorGUILayout.BeginHorizontal();
            EditorGUILayout.LabelField(
                Vrc2GtavLocalization.Format(langMode, "slot.editing", Vrc2GtavLocalization.Get(langMode, activeSlot.LabelKey)),
                EditorStyles.miniBoldLabel);
            bool hasCopySource = HasOtherConfiguredSlot(enabled, activeSlot);
            using (new EditorGUI.DisabledScope(!hasCopySource))
            {
                if (GUILayout.Button(Vrc2GtavLocalization.Get(langMode, "slot.copy_from"), EditorStyles.miniButton, GUILayout.Width(108f)))
                {
                    ShowCopySlotMenu(langMode, enabled, activeSlot, onStateChanged);
                }
            }
            EditorGUILayout.EndHorizontal();

            var missing = new List<string>();
            for (int i = 0; i < enabled.Count; i++)
            {
                if (!enabled[i].Avatar.IsValid) missing.Add(Vrc2GtavLocalization.Get(langMode, enabled[i].ShortLabelKey));
            }
            if (missing.Count > 0)
            {
                EditorGUILayout.HelpBox(
                    Vrc2GtavLocalization.Format(langMode, "slot.missing_list", string.Join(", ", missing)),
                    MessageType.Warning);
            }
            return activeSlot;
        }

        private static bool HasOtherConfiguredSlot(IList<ProtagonistAvatarSlot> enabled, ProtagonistAvatarSlot current)
        {
            for (int i = 0; i < enabled.Count; i++)
            {
                if (enabled[i] != current && enabled[i].Avatar.IsValid) return true;
            }
            return false;
        }

        private static void ShowCopySlotMenu(
            UiLanguageMode langMode,
            IList<ProtagonistAvatarSlot> enabled,
            ProtagonistAvatarSlot target,
            Action onStateChanged)
        {
            var menu = new GenericMenu();
            for (int i = 0; i < enabled.Count; i++)
            {
                ProtagonistAvatarSlot src = enabled[i];
                if (src == target || !src.Avatar.IsValid) continue;
                string shortPed = Vrc2GtavLocalization.Get(langMode, src.ShortLabelKey);
                ProtagonistAvatarSlot captured = src;
                menu.AddItem(
                    new GUIContent(Vrc2GtavLocalization.Format(langMode, "slot.copy_all_item", shortPed)),
                    false,
                    () =>
                    {
                        target.Avatar = Vrc2GtavMultiSlotSync.CloneSource(captured.Avatar);
                        target.Profile.CopyFrom(captured.Profile);
                        target.Textures.SyncWithAvatar(target.Avatar);
                        target.Textures.CopyOverridesFrom(captured.Textures);
                        onStateChanged?.Invoke();
                    });
                menu.AddItem(
                    new GUIContent(Vrc2GtavLocalization.Format(langMode, "slot.copy_opts_item", shortPed)),
                    false,
                    () =>
                    {
                        target.Profile.CopyFrom(captured.Profile);
                        target.Textures.CopyOverridesFrom(captured.Textures);
                        onStateChanged?.Invoke();
                    });
            }
            menu.ShowAsContext();
        }
    }
}
