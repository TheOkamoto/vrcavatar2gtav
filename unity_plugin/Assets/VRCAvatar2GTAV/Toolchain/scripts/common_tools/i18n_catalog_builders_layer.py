"""
i18n_catalog_builders_layer.py
==============================
Layer 2 of 3 for the VRC2GTAV trilingual translation catalog.

Contains atlas generators, Blender character builders, hair porting,
blendshape presets, and ped damage strings.
"""

from typing import Dict


# Ordered subset of the trilingual ("en", "ja", "pt") catalog consumed by
# vrc2gtav_i18n.py to keep catalog files concise and maintainable.
BUILDERS_TRANSLATION_CATALOG: Dict[str, Dict[str, str]] = {
    "repack.copy_zero_done": {
        "en": "  [PROGRESS] {bar} 100.0% (0.0/0.0 MB)",
        "ja": "  [進捗] {bar} 100.0% (0.0/0.0 MB)",
        "pt": "  [PROGRESSO] {bar} 100.0% (0.0/0.0 MB)",
    },
    "repack.copy_progress": {
        "en": "  [PROGRESS] {bar} {percent:5.1f}% ({copied_mb:.1f}/{total_mb:.1f} MB | {rate_mbs:.1f} MB/s | ETA {eta_sec:.0f}s)",
        "ja": "  [進捗] {bar} {percent:5.1f}% ({copied_mb:.1f}/{total_mb:.1f} MB | {rate_mbs:.1f} MB/s | 残り {eta_sec:.0f}秒)",
        "pt": "  [PROGRESSO] {bar} {percent:5.1f}% ({copied_mb:.1f}/{total_mb:.1f} MB | {rate_mbs:.1f} MB/s | ETA {eta_sec:.0f}s)",
    },
    "repack.copy_done": {
        "en": "  [PROGRESS] {bar} 100.0% ({total_mb:.1f}/{total_mb:.1f} MB | {rate_mbs:.1f} MB/s | {elapsed:.1f}s)",
        "ja": "  [進捗] {bar} 100.0% ({total_mb:.1f}/{total_mb:.1f} MB | {rate_mbs:.1f} MB/s | {elapsed:.1f}秒)",
        "pt": "  [PROGRESSO] {bar} 100.0% ({total_mb:.1f}/{total_mb:.1f} MB | {rate_mbs:.1f} MB/s | {elapsed:.1f}s)",
    },
    "repack.installed_ok": {
        "en": "{label} installed successfully.",
        "ja": "{label} のインストールが完了しました。",
        "pt": "{label} instalado com sucesso.",
    },
    "repack.create_start": {
        "en": "--- {description} ({expected_mb:.1f} MB input) ---",
        "ja": "--- {description} (入力 {expected_mb:.1f} MB) ---",
        "pt": "--- {description} ({expected_mb:.1f} MB de entrada) ---",
    },
    "repack.reading_files": {
        "en": "  [PROGRESS] {bar} Reading files... ({elapsed:.1f}s | ~{expected_mb:.1f} MB)",
        "ja": "  [進捗] {bar} ファイル読込中... ({elapsed:.1f}秒 | ~{expected_mb:.1f} MB)",
        "pt": "  [PROGRESSO] {bar} Lendo arquivos... ({elapsed:.1f}s | ~{expected_mb:.1f} MB)",
    },
    "repack.writing_rpf": {
        "en": "  [PROGRESS] {bar} {percent:5.1f}% Writing RPF ({written_mb:.1f}/{expected_mb:.1f} MB | {elapsed:.1f}s)",
        "ja": "  [進捗] {bar} {percent:5.1f}% RPF 書込中 ({written_mb:.1f}/{expected_mb:.1f} MB | {elapsed:.1f}秒)",
        "pt": "  [PROGRESSO] {bar} {percent:5.1f}% Gravando RPF ({written_mb:.1f}/{expected_mb:.1f} MB | {elapsed:.1f}s)",
    },
    "repack.cmd_failed": {
        "en": "[ERROR] Execution failed: {description}",
        "ja": "[エラー] 実行に失敗しました: {description}",
        "pt": "[ERRO] Falha ao executar: {description}",
    },
    "repack.return_code": {
        "en": "Return code: {returncode}",
        "ja": "終了コード: {returncode}",
        "pt": "Código de retorno: {returncode}",
    },
    "repack.process_output": {
        "en": "Process output:",
        "ja": "プロセス出力:",
        "pt": "Saída do processo:",
    },
    "repack.create_done": {
        "en": "  [PROGRESS] {bar} 100.0% ({final_mb:.1f} MB) Finished in {elapsed:.1f}s",
        "ja": "  [進捗] {bar} 100.0% ({final_mb:.1f} MB) {elapsed:.1f}秒で完了",
        "pt": "  [PROGRESSO] {bar} 100.0% ({final_mb:.1f} MB) Concluído em {elapsed:.1f}s",
    },
    "repack.banner": {
        "en": "=== GTA V MOD REPACK & DEPLOY PIPELINE ===",
        "ja": "=== GTA V MOD RPF 再パック＆デプロイパイプライン ===",
        "pt": "=== GTA V MOD REPACK & DEPLOY PIPELINE ===",
    },
    "repack.gtav_dest": {
        "en": "GTA V Dest:      {path}",
        "ja": "GTA V 出力先:    {path}",
        "pt": "Destino GTA V:   {path}",
    },
    "repack.staging_missing": {
        "en": "[ERROR] Staging directory not found: {path}",
        "ja": "[エラー] ステージングディレクトリが見つかりません: {path}",
        "pt": "[ERRO] Diretório de staging não encontrado: {path}",
    },
    "repack.stage_repacking": {
        "en": "Repacking {name}",
        "ja": "{name} を再パック中",
        "pt": "Repacotando {name}",
    },
    "repack.stage_installing": {
        "en": "Installing {name}",
        "ja": "{name} をインストール中",
        "pt": "Instalando {name}",
    },
    "repack.stage_verifying": {
        "en": "Verifying installed RPFs (OPEN and f_size=0)",
        "ja": "インストール済み RPF を検証中 (OPEN と f_size=0)",
        "pt": "Verificando RPFs instalados (OPEN e f_size=0)",
    },
    "repack.props_missing_skip": {
        "en": "[WARNING] streamedpedprops_extracted folder missing ({path}); skipping props repack.",
        "ja": "[警告] streamedpedprops_extracted フォルダがないため ({path})、プロップの再パックをスキップします。",
        "pt": "[AVISO] Diretório streamedpedprops_extracted ausente ({path}); pulando repack de props.",
    },
    "repack.verifying_header": {
        "en": "\n=== VERIFYING INSTALLED FILES ===",
        "ja": "\n=== インストール済みファイルを検証中 ===",
        "pt": "\n=== VERIFICANDO ARQUIVOS INSTALADOS ===",
    },
    "repack.verify_dlc_header": {
        "en": "dlc.rpf encryption header:   {flag} (expected b'OPEN')",
        "ja": "dlc.rpf 暗号化ヘッダー:      {flag} (期待値 b'OPEN')",
        "pt": "dlc.rpf cabeçalho de criptografia:  {flag} (esperado b'OPEN')",
    },
    "repack.verify_x64v_header": {
        "en": "x64v.rpf encryption header:  {flag} (expected b'OPEN')",
        "ja": "x64v.rpf 暗号化ヘッダー:     {flag} (期待値 b'OPEN')",
        "pt": "x64v.rpf cabeçalho de criptografia: {flag} (esperado b'OPEN')",
    },
    "repack.verify_dlc_compressed": {
        "en": "Compressed binary entries in dlc.rpf:  {count} (expected 0)",
        "ja": "dlc.rpf 内の圧縮バイナリエントリ数:  {count} (期待値 0)",
        "pt": "Entradas binárias comprimidas em dlc.rpf:  {count} (esperado 0)",
    },
    "repack.verify_x64v_compressed": {
        "en": "Compressed binary entries in x64v.rpf: {count} (expected 0)",
        "ja": "x64v.rpf 内の圧縮バイナリエントリ数: {count} (期待値 0)",
        "pt": "Entradas binárias comprimidas em x64v.rpf: {count} (esperado 0)",
    },
    "repack.verify_passed": {
        "en": "\n[VERIFICATION PASSED] All archives installed successfully with 'OPEN' header and zero risk of ERR_GEN_ZLIB_2!",
        "ja": "\n[検証合格] 全アーカイブが 'OPEN' ヘッダー付きで正常にインストールされ、ERR_GEN_ZLIB_2 のリスクはありません！",
        "pt": "\n[VERIFICAÇÃO APROVADA] Todos os arquivos foram instalados com sucesso, com cabeçalho 'OPEN' e zero risco de ERR_GEN_ZLIB_2!",
    },
    "repack.verify_warn": {
        "en": "\n[WARNING] Discrepancies found during verification. Check detailed logs.",
        "ja": "\n[警告] 検証中に不整合が検出されました。詳細ログを確認してください。",
        "pt": "\n[AVISO] Discrepâncias encontradas na verificação. Verifique os logs detalhados.",
    },
    "repack.fatal_error": {
        "en": "\n[FATAL DEPLOY ERROR] {error}",
        "ja": "\n[致命的デプロイエラー] {error}",
        "pt": "\n[FALHA FATAL NO DEPLOY] {error}",
    },
    "repack.cli_description": {
        "en": "Repack modded GTA V RPF archives with live progress bars and install into mods/",
        "ja": "改造済み GTA V RPF アーカイブを進捗バー付きで再パックし、mods/ にインストールします",
        "pt": "Repacota arquivos RPF modificados do GTA V com barra de progresso e instala em mods/",
    },
    "tests.cli_desc": {
        "en": "Automated validation suite for the vrc2gtav project",
        "ja": "vrc2gtav プロジェクトの自動検証テストスイート",
        "pt": "Suíte de testes automatizados do projeto vrc2gtav",
    },
}
