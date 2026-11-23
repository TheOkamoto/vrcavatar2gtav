using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace Vrc2Gtav.Editor
{
    internal enum UiLanguageMode
    {
        Auto = 0,
        Portuguese = 1,
        English = 2,
        Japanese = 3
    }

    internal static class Vrc2GtavLocalization
    {
        private static readonly Dictionary<string, string[]> Catalog =
            new Dictionary<string, string[]>(StringComparer.Ordinal)
        {
            // Columns: [0]=en, [1]=pt, [2]=ja
            ["window.title"] = new[]
            {
                "VRCAvatar2GTAV Exporter",
                "Exportador VRCAvatar2GTAV",
                "VRCAvatar2GTAV エクスポーター"
            },
            ["window.subtitle"] = new[]
            {
                "Export VRChat / Unity avatars directly to GTA V protagonists.",
                "Exporte avatares VRChat / Unity diretamente para os protagonistas do GTA V.",
                "VRChat / Unity アバターを GTA V 主人公スロットへ直接エクスポートします。"
            },
            ["lang.label"] = new[] { "Language", "Idioma", "言語" },
            ["lang.auto"] = new[] { "Auto", "Auto", "自動 (Auto)" },

            ["sec.avatar"] = new[]
            {
                "1. Avatar Source (Drag & Drop or Browse)",
                "1. Avatar de Origem (Arraste e Solte ou Selecione)",
                "1. アバター選択（ドラッグ＆ドロップ または 参照）"
            },
            ["avatar.drop_hint"] = new[]
            {
                "Drag an Avatar GameObject from Hierarchy, a .prefab, .unity scene, .zip or .unitypackage here",
                "Arraste um Avatar da Hierarchy, um .prefab, cena .unity, .zip ou .unitypackage aqui",
                "Hierarchy のアバター、.prefab、.unity シーン、.zip、.unitypackage をここへドロップ"
            },
            ["avatar.object_field"] = new[] { "Unity Object", "Objeto Unity", "Unity オブジェクト" },
            ["avatar.scene_picker"] = new[] { "Scene Avatars...", "Avatares da Cena...", "シーン内のアバター..." },
            ["avatar.browse_file"] = new[] { "Browse Archive/Scene...", "Procurar Arquivo...", "ファイル参照..." },
            ["avatar.resolved_name"] = new[] { "Avatar Name", "Nome do Avatar", "アバター名" },
            ["avatar.resolved_source"] = new[] { "Source Path", "Caminho", "ソースパス" },
            ["avatar.dirty_warning"] = new[]
            {
                "The active scene has unsaved changes. Save it so Python/Blender reads the latest Hierarchy setup.",
                "A cena atual tem alterações não salvas. Salve para que o Python/Blender leia o estado mais recente.",
                "現在のシーンに未保存の変更があります。Python/Blender に反映するため保存してください。"
            },
            ["avatar.save_scene_now"] = new[] { "Save Scene Now", "Salvar Cena Agora", "今すぐシーン保存" },
            ["avatar.autosave_scene"] = new[]
            {
                "Auto-save scene before Start",
                "Salvar cena automaticamente antes de Iniciar",
                "開始前にシーンを自動保存する"
            },
            ["avatar.none"] = new[]
            {
                "No avatar selected yet.",
                "Nenhum avatar selecionado ainda.",
                "アバターがまだ選択されていません。"
            },

            ["sec.targets"] = new[]
            {
                "2. GTA V Protagonist Destinations",
                "2. Destinos no GTA V (Protagonistas)",
                "2. GTA V 出力先（主人公スロット）"
            },
            ["target.michael"] = new[]
            {
                "Michael De Santa (player_zero)",
                "Michael De Santa (player_zero)",
                "マイケル・デサンタ (player_zero)"
            },
            ["target.franklin"] = new[]
            {
                "Franklin Clinton (player_one)",
                "Franklin Clinton (player_one)",
                "フランクリン・クリントン (player_one)"
            },
            ["target.trevor"] = new[]
            {
                "Trevor Philips (player_two)",
                "Trevor Philips (player_two)",
                "トレバー・フィリップス (player_two)"
            },
            ["target.none_err"] = new[]
            {
                "Select at least one GTA V protagonist slot.",
                "Selecione pelo menos um protagonista do GTA V.",
                "少なくとも 1 つの GTA V 主人公を選択してください。"
            },

            ["sec.options"] = new[]
            {
                "3. Export Options",
                "3. Opções de Exportação",
                "3. エクスポート設定"
            },
            ["opt.deploy"] = new[]
            {
                "Deploy built RPFs to GTA V mods/ folder",
                "Instalar RPFs gerados na pasta mods/ do GTA V",
                "ビルド済み RPF を GTA V mods/ フォルダへ自動配置"
            },
            ["opt.face_bs"] = new[]
            {
                "Import Face Blendshapes from Unity",
                "Importar Blendshapes Faciais do Unity",
                "Unity から表情シェイプキーをインポート"
            },
            ["opt.body_bs"] = new[]
            {
                "Import Body / Outfit Blendshapes from Unity",
                "Importar Blendshapes de Corpo/Roupa do Unity",
                "Unity から体型/衣装シェイプキーをインポート"
            },
            ["opt.eye_blink"] = new[]
            {
                "Natural Eye Blinking (GTA V Eyelids)",
                "Piscar Natural dos Olhos (Pálpebras GTA V)",
                "自然なまばたき（GTA V まぶたボーン）"
            },
            ["opt.eye_strength"] = new[]
            {
                "Blink Strength (0 = Auto)",
                "Força do Piscar (0 = Auto)",
                "まばたき強度 (0 = 自動)"
            },
            ["opt.mouth_open"] = new[]
            {
                "Mouth Opening (0 = Shut)",
                "Abertura da Boca (0 = Fechada)",
                "口の開き (0 = 閉じる)"
            },
            ["opt.blood_decals"] = new[]
            {
                "Enable GTA V Blood / Wound Decals",
                "Ativar Marcas de Sangue / Dano do GTA V",
                "GTA V 血液・ダメージデカールを有効化"
            },
            ["opt.advanced"] = new[]
            {
                "Advanced Options & Command Line",
                "Opções Avançadas e Linha de Comando",
                "詳細オプション・CLI プレビュー"
            },
            ["opt.avatar_override"] = new[]
            {
                "Avatar Name Override",
                "Nome do Avatar (Override)",
                "アバター名上書き (任意)"
            },
            ["opt.bs_source"] = new[] { "Blendshapes Priority", "Prioridade Blendshapes", "Blendshape 取得元" },
            ["opt.face_anim"] = new[]
            {
                "Face Blendshapes .anim",
                "Blendshapes Faciais (.anim)",
                "顔表情上書き (.anim)"
            },
            ["opt.pb_source"] = new[] { "PhysBones Priority", "Prioridade PhysBones", "PhysBones 取得元" },
            ["opt.marshmallow"] = new[]
            {
                "Enable Marshmallow PB Breast Override",
                "Ativar Marshmallow PB (Física Opcional)",
                "Marshmallow PB 物理上書きを有効化"
            },
            ["opt.force_reextract"] = new[]
            {
                "Force Re-extract Vanilla Ped Files",
                "Forçar Re-extração dos Arquivos Originais",
                "バニラ Ped データを強制再展開"
            },
            ["opt.backend_mode"] = new[]
            {
                "Execution Backend",
                "Modo de Execução",
                "実行バックエンド"
            },
            ["opt.cli_preview"] = new[]
            {
                "Generated Command Preview",
                "Prévia do Comando Gerado",
                "生成されるコマンドのプレビュー"
            },

            ["sec.tools"] = new[]
            {
                "4. Folders & Required Tools",
                "4. Pastas e Ferramentas Necessárias",
                "4. フォルダ設定と必須ツール"
            },
            ["tools.gtav_root"] = new[] { "GTA V Legacy Folder", "Pasta do GTA V Legacy", "GTA V フォルダ" },
            ["tools.repo_root"] = new[] { "Scripts / Toolchain Folder", "Pasta dos Scripts", "スクリプトフォルダ" },
            ["tools.blender"] = new[] { "Blender 4.0.x Path", "Executável Blender 4.0.x", "Blender 4.0.x パス" },
            ["tools.rage"] = new[] { "RAGE CLI (rage / rage.exe)", "RAGE CLI (rage / rage.exe)", "RAGE CLI (rage / rage.exe)" },
            ["tools.python"] = new[] { "Python 3 Executable", "Executável Python 3", "Python 3 実行ファイル" },
            ["tools.details"] = new[]
            {
                "Detected Tool Paths (Manual Override)",
                "Caminhos Detectados (Ajuste Manual)",
                "検出されたツールパス（手動指定可）"
            },
            ["tools.autodetect"] = new[] { "Auto-Detect All", "Detectar Tudo", "自動検出" },
            ["tools.download_setup"] = new[]
            {
                "Download Required Tools & Setup",
                "Baixar o Necessário e Configurar",
                "必須ツールをダウンロード・初期設定"
            },
            ["tools.check_env"] = new[] { "Check Environment", "Verificar Ambiente", "環境チェック" },
            ["tools.browse"] = new[] { "Browse...", "Procurar...", "参照..." },
            ["tools.status_ok"] = new[] { "Ready", "OK", "準備完了" },
            ["tools.status_missing"] = new[] { "Missing", "Faltando", "未検出" },
            ["tools.status_no_sollumz"] = new[] { "No Sollumz", "Sem Sollumz", "Sollumz 未導入" },

            ["btn.start"] = new[] { "Start", "Iniciar", "スタート" },
            ["btn.cancel"] = new[] { "Cancel", "Cancelar", "中止" },
            ["sec.logs"] = new[] { "Execution Logs", "Logs de Execução", "実行ログ" },
            ["btn.copy_logs"] = new[] { "Copy Logs", "Copiar Logs", "ログをコピー" },
            ["btn.clear_logs"] = new[] { "Clear", "Limpar", "クリア" },
            ["btn.open_logs"] = new[] { "Open Logs Folder", "Abrir Pasta Logs", "ログフォルダを開く" },

            ["status.idle"] = new[] { "Ready.", "Pronto.", "待機中" },
            ["status.running"] = new[] { "Running...", "Executando...", "実行中..." },
            ["status.done_ok"] = new[] { "Completed successfully.", "Concluído com sucesso.", "正常に完了しました。" },
            ["status.done_err"] = new[] { "Finished with errors (exit code {0}).", "Finalizado com erro (código {0}).", "エラーで終了しました（終了コード {0}）。" },
            ["status.cancelled"] = new[] { "Cancelled by user.", "Cancelado pelo usuário.", "ユーザーによりキャンセルされました。" },
            ["err.need_gtav_for_setup"] = new[]
            {
                "Select a valid GTA V folder (containing GTA5.exe) or let Auto-Detect find it before full setup, or continue with tools download only.",
                "Selecione uma pasta válida do GTA V (com GTA5.exe) antes do setup completo, ou baixe apenas Blender/rage/pip.",
                "GTA5.exe を含む GTA V フォルダを選択してください（未選択でもツール単体のダウンロードは可能です）。"
            },
            ["runtime.header"] = new[]
            {
                "GTA V Runtime Plugins",
                "Plugins de Runtime no GTA V",
                "GTA V ランタイムプラグイン"
            },
            ["runtime.missing_auto"] = new[]
            {
                "Click 'Download Required Tools & Setup' to auto-install dinput8.dll, GTAVPhysBones.asi, and GTAVVToon.asi into GTA V.",
                "Clique em 'Baixar o Necessário e Configurar' para instalar automaticamente dinput8.dll, GTAVPhysBones.asi e GTAVVToon.asi no GTA V.",
                "「必須ツールをダウンロード・初期設定」を押すと dinput8.dll / GTAVPhysBones.asi / GTAVVToon.asi が GTA V へ自動導入されます。"
            },
            ["runtime.missing_thirdparty"] = new[]
            {
                "Third-party requirement(s) missing in GTA V folder (ScriptHookV.dll and/or OpenIV.asi / RageOpenV.asi for mods/ folder). Install them to run mods in-game.",
                "Dependência externa faltando na pasta do GTA V (ScriptHookV.dll e/ou OpenIV.asi / RageOpenV.asi para ler a pasta mods/). Instale-os para os mods funcionarem no jogo.",
                "GTA V フォルダに外部必須ファイル (ScriptHookV.dll または mods/ 用 OpenIV.asi / RageOpenV.asi) がありません。導入してください。"
            },
            ["runtime.get_scripthookv"] = new[] { "Get ScriptHookV.dll", "Baixar ScriptHookV.dll", "ScriptHookV 入手先" },
            ["runtime.get_openiv"] = new[] { "Get OpenIV (mods/ loader)", "Baixar OpenIV (mods/)", "OpenIV 入手先" },
            ["tools.use_bundled"] = new[] { "Use Bundled", "Usar Interno", "同梱版を使う" },

            ["sec.textures_res"] = new[]
            {
                "3. Avatar Textures & Resolution (RPF Budget)",
                "3. Texturas do Avatar e Resolução (Limite RPF)",
                "3. アバターテクスチャと解像度（RPF 上限管理）"
            },
            ["tex.atlas_res"] = new[] { "Texture Atlas Resolution", "Resolução do Atlas", "テクスチャ解像度" },
            ["tex.normal_res"] = new[] { "Normal Map Resolution", "Resolução do Normal Map", "ノーマルマップ解像度" },
            ["tex.secondary_res"] = new[] { "Secondary Outfits (x64v RPF)", "Roupas Secundárias (x64v RPF)", "サブ衣装解像度 (x64v RPF)" },
            ["tex.mat_list"] = new[] { "Avatar Material Textures (Swap / Choose)", "Texturas do Avatar (Escolher / Trocar)", "アバターマテリアル（選択・変更）" },
            ["tex.no_renderers"] = new[]
            {
                "Tip: Select an avatar from Scene or Prefab above to inspect & swap individual materials, or pick a global texture override below.",
                "Dica: Selecione um avatar na Cena ou Prefab acima para escolher cada material, ou defina uma textura global abaixo.",
                "ヒント: シーンまたは Prefab を選択すると各マテリアルのテクスチャを個別変更できます。"
            },
            ["tex.refresh"] = new[] { "Refresh", "Atualizar", "再読込" },
            ["tex.reset_all"] = new[] { "Reset All", "Resetar Tudo", "全リセット" },
            ["tex.reset_one"] = new[] { "Reset", "Reset", "戻す" },
            ["tex.global_override"] = new[] { "Global Texture Override", "Textura Global (Opcional)", "全体テクスチャ上書き" },
            ["tex.rpf_safe"] = new[]
            {
                "Estimated atlas .ytd: ~{0} MiB (x64v.rpf texture budget ~{1} MiB). Safe for RPF7 (<= 16 MiB/file, <= 4.00 GiB archive).",
                "Tamanho estimado do .ytd: ~{0} MiB (slots no x64v.rpf ~{1} MiB). Seguro para o RPF7 (<= 16 MiB/arquivo, <= 4.00 GiB).",
                "推定 .ytd サイズ: 約 {0} MiB (x64v.rpf 合計 約 {1} MiB)。RPF7 上限内です。"
            },
            ["tex.rpf_warn"] = new[]
            {
                "High resolution (~{0} MiB/ytd, ~{1} MiB slots). Automatic RPF7 budgeter will compact secondary slots if x64v.rpf nears 4.00 GiB.",
                "Resolução alta (~{0} MiB/ytd, ~{1} MiB total). Para não estourar 4.00 GiB no RPF7, o budget automático compactará slots secundários.",
                "高解像度設定 (約 {0} MiB/ytd, 合計 約 {1} MiB)。4.00 GiB 超過時は RPF7 保護機能が自動圧縮します。"
            },

            ["target.per_slot_toggle"] = new[]
            {
                "Separate Avatar Slot per Protagonist (+1 Scene/File slot per checked character)",
                "Um Avatar por Personagem (+1 slot na Scene/Arquivo para cada personagem marcado)",
                "キャラ別アバタースロット（チェックした主人公ごとに1スロット追加）"
            },
            ["slot.header"] = new[] { "Avatar Slot for {0}", "Slot de Avatar: {0}", "{0} 用アバタースロット" },
            ["slot.copy_main"] = new[] { "Use Main Source", "Copiar Principal", "メインからコピー" },
            ["slot.missing_err"] = new[]
            {
                "Assign an avatar for every checked protagonist slot.",
                "Selecione um avatar para cada personagem marcado nos slots.",
                "チェック済みの全キャラクターにアバターを設定してください。"
            },

            ["restore.header"] = new[]
            {
                "Restore Protagonists / NPCs to Rockstar Vanilla",
                "Restaurar Personagens para o Original (Vanilla)",
                "キャラクターを GTA V バニラ（純正）に戻す"
            },
            ["restore.desc"] = new[]
            {
                "Restores ONLY the selected character from vanilla GTA V archives without reverting other modded characters.",
                "Restaura APENAS o personagem escolhido dos arquivos originais do GTA V, mantendo outros personagens com mod intactos.",
                "選択したキャラクターのみバニラへ戻し、他のキャラの Mod は維持します。"
            },
            ["restore.michael"] = new[] { "Restore Michael", "Restaurar Michael", "マイケルを戻す" },
            ["restore.franklin"] = new[] { "Restore Franklin", "Restaurar Franklin", "フランクリンを戻す" },
            ["restore.trevor"] = new[] { "Restore Trevor", "Restaurar Trevor", "トレバーを戻す" },
            ["restore.all"] = new[] { "Restore All", "Restaurar Todos", "全てバニラに戻す" },
            ["restore.confirm_title"] = new[] { "Confirm Vanilla Restore", "Confirmar Restauração Vanilla", "バニラ復元の確認" },
            ["restore.confirm_msg"] = new[]
            {
                "Restore {0} to original GTA V Rockstar files and remove its GTAVPhysBones / GTAVVToon config entries?",
                "Restaurar {0} para os arquivos originais do GTA V e remover apenas as entradas dele no GTAVPhysBones / GTAVVToon?",
                "{0} をバニラへ戻し、GTAVPhysBones / GTAVVToon の該当エントリを削除しますか？"
            }
        };

        public static string ResolveLanguageCode(UiLanguageMode mode)
        {
            if (mode == UiLanguageMode.Portuguese) return "pt";
            if (mode == UiLanguageMode.English) return "en";
            if (mode == UiLanguageMode.Japanese) return "ja";

            string iso = CultureInfo.CurrentUICulture.TwoLetterISOLanguageName.ToLowerInvariant();
            if (iso == "pt") return "pt";
            if (iso == "ja") return "ja";

            switch (Application.systemLanguage)
            {
                case SystemLanguage.Portuguese:
                    return "pt";
                case SystemLanguage.Japanese:
                    return "ja";
                default:
                    return "en";
            }
        }

        public static string ToCliLanguageArg(UiLanguageMode mode)
        {
            switch (mode)
            {
                case UiLanguageMode.Portuguese: return "pt";
                case UiLanguageMode.English: return "en";
                case UiLanguageMode.Japanese: return "ja";
                default: return "auto";
            }
        }

        public static string Get(UiLanguageMode mode, string key)
        {
            if (!Catalog.TryGetValue(key, out string[] variants) || variants.Length < 3)
            {
                return key;
            }
            string lang = ResolveLanguageCode(mode);
            if (lang == "pt") return variants[1];
            if (lang == "ja") return variants[2];
            return variants[0];
        }

        public static string Format(UiLanguageMode mode, string key, params object[] args)
        {
            string pattern = Get(mode, key);
            return string.Format(CultureInfo.InvariantCulture, pattern, args);
        }
    }
}
