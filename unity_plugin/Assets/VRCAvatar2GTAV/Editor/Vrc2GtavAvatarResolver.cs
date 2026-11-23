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

    internal sealed class ProtagonistAvatarSlot
    {
        public string PedModel;
        public string LabelKey;
        public ResolvedAvatarSource Avatar = new ResolvedAvatarSource();
        public string AvatarNameOverride = string.Empty;
        public AnimationClip FaceAnimClip;
        public string FaceBlendshapesAnim = string.Empty;
    }

    internal static class Vrc2GtavMultiSlotUi
    {
        public static List<ProtagonistAvatarSlot> CreateDefaultSlots()
        {
            return new List<ProtagonistAvatarSlot>
            {
                new ProtagonistAvatarSlot { PedModel = "player_zero", LabelKey = "target.michael" },
                new ProtagonistAvatarSlot { PedModel = "player_one", LabelKey = "target.franklin" },
                new ProtagonistAvatarSlot { PedModel = "player_two", LabelKey = "target.trevor" }
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

        public static void SyncFirstSlotFromMain(
            IList<ProtagonistAvatarSlot> slots,
            Vrc2GtavExportOptions opts,
            ResolvedAvatarSource mainAvatar,
            AnimationClip mainFaceAnimClip = null)
        {
            List<ProtagonistAvatarSlot> enabled = GetEnabledSlots(slots, opts);
            if (enabled.Count == 0 || mainAvatar == null || !mainAvatar.IsValid) return;
            ProtagonistAvatarSlot first = enabled[0];
            if (!first.Avatar.IsValid)
            {
                first.Avatar = new ResolvedAvatarSource
                {
                    Kind = mainAvatar.Kind,
                    AvatarName = mainAvatar.AvatarName,
                    SourcePath = mainAvatar.SourcePath,
                    SceneAssetPath = mainAvatar.SceneAssetPath,
                    IsSceneDirty = mainAvatar.IsSceneDirty,
                    ObjectRef = mainAvatar.ObjectRef
                };
            }
            if (string.IsNullOrWhiteSpace(first.AvatarNameOverride) && !string.IsNullOrWhiteSpace(opts?.AvatarNameOverride))
                first.AvatarNameOverride = opts.AvatarNameOverride;
            if (string.IsNullOrWhiteSpace(first.FaceBlendshapesAnim) && !string.IsNullOrWhiteSpace(opts?.FaceBlendshapesAnim))
            {
                first.FaceBlendshapesAnim = opts.FaceBlendshapesAnim;
                first.FaceAnimClip = mainFaceAnimClip;
            }
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

        public static void DrawPerProtagonistSlots(
            UiLanguageMode langMode,
            Vrc2GtavExportOptions opts,
            IList<ProtagonistAvatarSlot> slots,
            ResolvedAvatarSource mainAvatar,
            GUIStyle dropStyle,
            GUIStyle wrapMiniStyle,
            Action onSaveSceneRequested,
            Action onRepaintRequested)
        {
            List<ProtagonistAvatarSlot> enabled = GetEnabledSlots(slots, opts);
            if (enabled.Count == 0) return;

            string emptyLabel = Vrc2GtavLocalization.Get(langMode, "avatar.none");
            string pickScene = Vrc2GtavLocalization.Get(langMode, "avatar.scene_picker");
            string pickFile = Vrc2GtavLocalization.Get(langMode, "avatar.browse_file");
            string copyMain = Vrc2GtavLocalization.Get(langMode, "slot.copy_main");

            for (int i = 0; i < enabled.Count; i++)
            {
                ProtagonistAvatarSlot slot = enabled[i];
                string pedTitle = Vrc2GtavLocalization.Get(langMode, slot.LabelKey);
                EditorGUILayout.BeginVertical(EditorStyles.helpBox);
                EditorGUILayout.BeginHorizontal();
                EditorGUILayout.LabelField(
                    Vrc2GtavLocalization.Format(langMode, "slot.header", pedTitle),
                    EditorStyles.boldLabel);
                if (mainAvatar != null && mainAvatar.IsValid && GUILayout.Button(copyMain, EditorStyles.miniButton, GUILayout.Width(115f)))
                {
                    slot.Avatar = new ResolvedAvatarSource
                    {
                        Kind = mainAvatar.Kind,
                        AvatarName = mainAvatar.AvatarName,
                        SourcePath = mainAvatar.SourcePath,
                        SceneAssetPath = mainAvatar.SceneAssetPath,
                        IsSceneDirty = mainAvatar.IsSceneDirty,
                        ObjectRef = mainAvatar.ObjectRef
                    };
                }
                EditorGUILayout.EndHorizontal();

                Rect dropRect = GUILayoutUtility.GetRect(0f, 28f, GUILayout.ExpandWidth(true));
                GUI.Box(dropRect, Vrc2GtavLocalization.Get(langMode, "avatar.drop_hint"), dropStyle);
                slot.Avatar = Vrc2GtavAvatarResolver.HandleDragAndDrop(dropRect, slot.Avatar);

                UnityEngine.Object picked = EditorGUILayout.ObjectField(
                    Vrc2GtavLocalization.Get(langMode, "avatar.object_field"),
                    slot.Avatar.ObjectRef, typeof(UnityEngine.Object), true);
                if (picked != slot.Avatar.ObjectRef)
                {
                    slot.Avatar = Vrc2GtavAvatarResolver.ResolveObject(picked);
                }

                EditorGUILayout.BeginHorizontal();
                if (GUILayout.Button(pickScene, GUILayout.ExpandWidth(true)))
                {
                    ProtagonistAvatarSlot captured = slot;
                    Vrc2GtavAvatarResolver.ShowSceneAvatarMenu(emptyLabel, selected =>
                    {
                        captured.Avatar = selected;
                        onRepaintRequested?.Invoke();
                    });
                }
                if (GUILayout.Button(pickFile, GUILayout.ExpandWidth(true)))
                {
                    string pickedFile = EditorUtility.OpenFilePanel(
                        pickFile, Vrc2GtavConfigDiscovery.GetUnityProjectRoot(), "zip,unitypackage,prefab,unity");
                    if (!string.IsNullOrEmpty(pickedFile))
                    {
                        slot.Avatar = Vrc2GtavAvatarResolver.ResolveExternalPath(pickedFile);
                    }
                }
                EditorGUILayout.EndHorizontal();

                if (slot.Avatar.Kind == AvatarSourceKind.SceneGameObject && slot.Avatar.ObjectRef is GameObject slotGo)
                {
                    slot.Avatar.IsSceneDirty = slotGo.scene.IsValid() && slotGo.scene.isDirty;
                }
                if (slot.Avatar.IsValid)
                {
                    EditorGUILayout.LabelField(Vrc2GtavLocalization.Get(langMode, "avatar.resolved_name"), slot.Avatar.AvatarName);
                    GUILayout.Label(slot.Avatar.SourcePath, wrapMiniStyle, GUILayout.ExpandWidth(true));
                }
                if (slot.Avatar.Kind == AvatarSourceKind.SceneGameObject && slot.Avatar.IsSceneDirty)
                {
                    EditorGUILayout.BeginHorizontal();
                    EditorGUILayout.HelpBox(Vrc2GtavLocalization.Get(langMode, "avatar.dirty_warning"), MessageType.Warning);
                    if (GUILayout.Button(Vrc2GtavLocalization.Get(langMode, "avatar.save_scene_now"), GUILayout.Width(125f), GUILayout.Height(34f)))
                    {
                        onSaveSceneRequested?.Invoke();
                    }
                    EditorGUILayout.EndHorizontal();
                }

                slot.AvatarNameOverride = EditorGUILayout.TextField(
                    Vrc2GtavLocalization.Get(langMode, "opt.avatar_override"),
                    slot.AvatarNameOverride ?? string.Empty);
                slot.FaceBlendshapesAnim = Vrc2GtavLogConsoleWidget.DrawAnimClipOverrideRow(
                    Vrc2GtavLocalization.Get(langMode, "opt.face_anim"),
                    slot.FaceBlendshapesAnim,
                    ref slot.FaceAnimClip,
                    Vrc2GtavLocalization.Get(langMode, "tools.browse"),
                    Vrc2GtavConfigDiscovery.GetDefaultUnityAssetsPath(),
                    wrapMiniStyle);
                EditorGUILayout.EndVertical();
            }

            if (!AreAllEnabledSlotsValid(slots, opts))
            {
                EditorGUILayout.HelpBox(Vrc2GtavLocalization.Get(langMode, "slot.missing_err"), MessageType.Warning);
            }
        }
    }
}
