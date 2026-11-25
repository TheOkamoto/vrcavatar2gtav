#!/usr/bin/env python3
"""
compute_release_version.py
==========================
Compute the next SemVer 2.0.0 (`vMAJOR.MINOR.PATCH`) release tag when at least 3
modifications (commits) have accumulated since the last release tag on the target branch,
OR immediately bypass the 3-commit wait when a GTA V deployment blocker fix (`hotfix:` /
`[release-blocker]` / `Release-Blocker: true`) is committed, while strictly blocking
any release if GTA V deployment validation fails.

Conventional Commits rules (international SemVer standard):
  - BREAKING CHANGE in body or `!:` in header -> bump MAJOR (`M+1.0.0`)
  - `feat:` or `feat(...):` header             -> bump MINOR (`M.m+1.0`)
  - `hotfix:` / `[release-blocker]` / `fix:`   -> bump PATCH (`M.m.p+1`)
  - First release (no reachable SemVer tag)    -> baseline `v1.0.0` (once >= 3 commits or blocker fix exist)
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

SEMVER_TAG_PATTERN = re.compile(r"^v([0-9]+)\.([0-9]+)\.([0-9]+)$")
BREAKING_HEADER_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+(?:\([^)]+\))?!:")
BREAKING_BODY_PATTERN = re.compile(r"(?im)^BREAKING[ -]CHANGE:")
FEAT_HEADER_PATTERN = re.compile(r"^feat(?:\([^)]+\))?:")
RELEASE_BLOCKER_SUBJECT_PATTERN = re.compile(
    r"^(?:hotfix(?:\([^)]+\))?(?:!)?:\s|.*\[(?:hotfix|release-blocker|deploy-blocker)\])",
    re.IGNORECASE,
)
RELEASE_BLOCKER_BODY_PATTERN = re.compile(
    r"(?im)^(?:Release|Deploy)-Blocker\s*:\s*(?:true|yes|1|gta[\s_-]*v)\b"
)
COMMITS_PER_RELEASE = 3


def parse_semver_tag(tag_name: str) -> Optional[Tuple[int, int, int]]:
    """Parse a strict `vMAJOR.MINOR.PATCH` tag into an integer tuple."""
    match_obj = SEMVER_TAG_PATTERN.fullmatch(str(tag_name or "").strip())
    if not match_obj:
        return None
    return (int(match_obj.group(1)), int(match_obj.group(2)), int(match_obj.group(3)))


def bump_semver(
    base_version: Tuple[int, int, int],
    commit_records: Sequence[Tuple[str, str, str]],
) -> Tuple[Tuple[int, int, int], str]:
    """Compute the next SemVer tuple and bump level from Conventional Commit messages."""
    major_num, minor_num, patch_num = base_version
    has_breaking = False
    has_feature = False
    for _sha, subject_line, body_text in commit_records:
        cleaned_subj = subject_line.strip()
        if BREAKING_HEADER_PATTERN.match(cleaned_subj) or BREAKING_BODY_PATTERN.search(body_text or ""):
            has_breaking = True
            break
        if FEAT_HEADER_PATTERN.match(cleaned_subj):
            has_feature = True

    if has_breaking:
        return (major_num + 1, 0, 0), "major"
    if has_feature:
        return (major_num, minor_num + 1, 0), "minor"
    return (major_num, minor_num, patch_num + 1), "patch"


def _run_git(repo_root: Path, git_args: Sequence[str]) -> str:
    """Execute a git subcommand inside `repo_root` and return stripped stdout."""
    proc = subprocess.run(
        ["git", *git_args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return proc.stdout


def _find_latest_reachable_semver_tag(repo_root: Path) -> Optional[Tuple[str, Tuple[int, int, int]]]:
    """Return `(tag_name, version_tuple)` for the highest SemVer tag reachable from HEAD."""
    raw_tags = _run_git(repo_root, ["tag", "--merged", "HEAD", "--list", "v*"])
    candidates: List[Tuple[Tuple[int, int, int], str]] = []
    for raw_line in raw_tags.splitlines():
        tag_str = raw_line.strip()
        parsed = parse_semver_tag(tag_str)
        if parsed is not None:
            candidates.append((parsed, tag_str))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    best_tuple, best_name = candidates[0]
    return best_name, best_tuple


def _read_commits_in_range(repo_root: Path, rev_range: str) -> List[Tuple[str, str, str]]:
    """Return list of `(short_sha, subject, body)` for commits matching `rev_range`."""
    raw_log = _run_git(
        repo_root,
        ["log", rev_range, "--no-merges", "--format=%h%x1f%s%x1f%b%x1e"],
    )
    records: List[Tuple[str, str, str]] = []
    for chunk in raw_log.split("\x1e"):
        if not chunk.strip():
            continue
        fields = chunk.split("\x1f", 2)
        if len(fields) < 2:
            continue
        short_sha = fields[0].strip()
        subject_line = fields[1].strip()
        body_text = fields[2].strip() if len(fields) > 2 else ""
        if short_sha and subject_line:
            records.append((short_sha, subject_line, body_text))
    return records


def has_release_blocker_commits(commit_records: Sequence[Tuple[str, str, str]]) -> bool:
    """Return True when any commit marks a GTA V deployment blocker / hotfix override."""
    for _sha, subject_line, body_text in commit_records:
        if RELEASE_BLOCKER_SUBJECT_PATTERN.match(subject_line.strip()):
            return True
        if RELEASE_BLOCKER_BODY_PATTERN.search(body_text or ""):
            return True
    return False


def compute_policy_decision(
    pending_count: int,
    commit_records: Sequence[Tuple[str, str, str]],
    *,
    force_release: bool = False,
    release_blocker: bool = False,
    deploy_check_passed: bool = True,
    commits_per_release: int = COMMITS_PER_RELEASE,
) -> Tuple[bool, str, bool]:
    """Return `(should_release, release_reason, release_blocked)` under 3-commit & blocker policy."""
    blocker_detected = has_release_blocker_commits(commit_records) or bool(release_blocker)
    if not deploy_check_passed:
        return False, "blocked_gta_deploy_failure", True
    if pending_count >= commits_per_release:
        return True, "three_commit_cadence", False
    if blocker_detected and pending_count >= 1:
        return True, "release_blocker_hotfix", False
    if force_release and pending_count >= 1:
        return True, "manual_force", False
    return False, "waiting_for_three_commits", False


def build_release_notes(
    tag_name: str,
    prev_tag: Optional[str],
    commit_records: Sequence[Tuple[str, str, str]],
    bump_level: str,
    *,
    release_reason: str = "three_commit_cadence",
) -> str:
    """Format standardized SemVer Markdown release notes for GitHub Releases."""
    version_str = tag_name.lstrip("v")
    pkg_filename = f"VRCAvatar2GTAV-{tag_name}.unitypackage"
    breaking_lines: List[str] = []
    feature_lines: List[str] = []
    other_lines: List[str] = []

    for short_sha, subject_line, body_text in commit_records:
        bullet = f"- {subject_line} (`{short_sha}`)"
        if BREAKING_HEADER_PATTERN.match(subject_line) or BREAKING_BODY_PATTERN.search(body_text or ""):
            breaking_lines.append(bullet)
        elif FEAT_HEADER_PATTERN.match(subject_line):
            feature_lines.append(bullet)
        else:
            other_lines.append(bullet)

    lines: List[str] = [
        f"## VRCAvatar2GTAV {tag_name}",
        "",
        f"- **Version**: `{version_str}` (SemVer 2.0.0 `{bump_level}` release after `{len(commit_records)}` commit(s){f' since `{prev_tag}`' if prev_tag else ''})",
        f"- **Artifact**: `{pkg_filename}`",
    ]
    if release_reason == "release_blocker_hotfix":
        lines.append("- **Policy**: Immediate Hotfix / Release Blocker (bypasses 3-commit wait because GTA V deployment was blocked)")
    lines.append("")
    if breaking_lines:
        lines.extend(["### Breaking Changes", *breaking_lines, ""])
    if feature_lines:
        lines.extend(["### Features", *feature_lines, ""])
    if other_lines:
        lines.extend(["### Fixes, Refactors & Maintenance", *other_lines, ""])

    lines.extend(
        [
            "### Installation (Unity Editor)",
            f"1. Download `{pkg_filename}` (and verify checksum via `SHA256SUMS.txt`).",
            "2. Open your VRChat Unity 2022.3 LTS project and drag & drop the `.unitypackage` into `Assets/` (or `Assets -> Import Package -> Custom Package...`).",
            "3. Open `Tools -> VRCAvatar2GTAV -> Export Avatar to GTA V`.",
            "",
        ]
    )
    return "\n".join(lines)


def evaluate_release_decision(
    repo_root: Path,
    *,
    force_release: bool = False,
    release_blocker: bool = False,
    deploy_check_passed: bool = True,
    commits_per_release: int = COMMITS_PER_RELEASE,
) -> Dict[str, str]:
    """Inspect repository tags and commits to decide whether to cut a new SemVer release."""
    latest = _find_latest_reachable_semver_tag(repo_root)
    if latest is None:
        total_commits = int(_run_git(repo_root, ["rev-list", "--count", "HEAD"]).strip() or "0")
        commit_records = _read_commits_in_range(repo_root, "HEAD~15..HEAD" if total_commits > 15 else "HEAD")
        should_release, release_reason, release_blocked = compute_policy_decision(
            total_commits,
            commit_records,
            force_release=force_release,
            release_blocker=release_blocker,
            deploy_check_passed=deploy_check_passed,
            commits_per_release=commits_per_release,
        )
        next_tag = "v1.0.0"
        if _run_git(repo_root, ["tag", "--list", next_tag]).strip():
            raise RuntimeError(f"Tag {next_tag} already exists in repository outside reachable HEAD history.")
        notes_text = (
            build_release_notes(next_tag, None, commit_records, "initial", release_reason=release_reason)
            if should_release
            else ""
        )
        return {
            "should_release": "true" if should_release else "false",
            "release_blocked": "true" if release_blocked else "false",
            "release_reason": release_reason,
            "version": "1.0.0",
            "tag": next_tag,
            "prev_tag": "",
            "bump_level": "initial",
            "commit_count": str(total_commits),
            "commits_required": str(commits_per_release),
            "commits_remaining": str(max(0, commits_per_release - total_commits)),
            "notes_markdown": notes_text,
        }

    prev_tag, prev_tuple = latest
    commit_records = _read_commits_in_range(repo_root, f"{prev_tag}..HEAD")
    pending_count = len(commit_records)
    should_release, release_reason, release_blocked = compute_policy_decision(
        pending_count,
        commit_records,
        force_release=force_release,
        release_blocker=release_blocker,
        deploy_check_passed=deploy_check_passed,
        commits_per_release=commits_per_release,
    )
    next_tuple, bump_level = bump_semver(prev_tuple, commit_records)
    next_version = f"{next_tuple[0]}.{next_tuple[1]}.{next_tuple[2]}"
    next_tag = f"v{next_version}"
    if should_release and _run_git(repo_root, ["tag", "--list", next_tag]).strip():
        raise RuntimeError(f"Computed release tag {next_tag} already exists.")

    notes_text = (
        build_release_notes(next_tag, prev_tag, commit_records, bump_level, release_reason=release_reason)
        if should_release
        else ""
    )
    return {
        "should_release": "true" if should_release else "false",
        "release_blocked": "true" if release_blocked else "false",
        "release_reason": release_reason,
        "version": next_version,
        "tag": next_tag,
        "prev_tag": prev_tag,
        "bump_level": bump_level,
        "commit_count": str(pending_count),
        "commits_required": str(commits_per_release),
        "commits_remaining": str(max(0, commits_per_release - pending_count)),
        "notes_markdown": notes_text,
    }


def run_self_tests() -> int:
    """Validate SemVer 3-commit cadence, GTA V blocker gate, and hotfix rules offline."""
    assert parse_semver_tag("v1.2.3") == (1, 2, 3)
    assert parse_semver_tag("1.2.3") is None
    assert bump_semver((1, 0, 0), [("aaa", "fix: seam", ""), ("bbb", "docs: readme", ""), ("ccc", "refactor: clean", "")]) == ((1, 0, 1), "patch")
    assert bump_semver((1, 0, 1), [("aaa", "fix: small", ""), ("bbb", "feat(ui): slider", ""), ("ccc", "docs: sync", "")]) == ((1, 1, 0), "minor")
    assert bump_semver((1, 2, 4), [("aaa", "feat!: drop legacy", ""), ("bbb", "fix: a", ""), ("ccc", "fix: b", "")]) == ((2, 0, 0), "major")
    assert bump_semver((1, 2, 4), [("aaa", "fix: cfg", "BREAKING CHANGE: key renamed"), ("bbb", "fix: ok", ""), ("ccc", "docs: ok", "")]) == ((2, 0, 0), "major")
    assert compute_policy_decision(1, [("aaa", "fix: small tweak", "")]) == (False, "waiting_for_three_commits", False)
    assert compute_policy_decision(1, [("aaa", "hotfix: import re before blender deploy", "")]) == (True, "release_blocker_hotfix", False)
    assert compute_policy_decision(1, [("aaa", "fix: deploy", "Release-Blocker: true")]) == (True, "release_blocker_hotfix", False)
    assert compute_policy_decision(3, [("aaa", "fix: a", ""), ("bbb", "fix: b", ""), ("ccc", "fix: c", "")], force_release=True, deploy_check_passed=False) == (False, "blocked_gta_deploy_failure", True)
    sample_notes = build_release_notes("v1.1.0", "v1.0.0", [("111aaaa", "hotfix: fix deploy blocker", "")], "patch", release_reason="release_blocker_hotfix")
    assert "VRCAvatar2GTAV-v1.1.0.unitypackage" in sample_notes and "Hotfix / Release Blocker" in sample_notes
    print("[PASS] compute_release_version.py SemVer, 3-commit cadence & GTA V release-blocker self-tests passed.")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint for GitHub Actions release version calculation."""
    parser = argparse.ArgumentParser(description="Compute SemVer release tag (every 3 commits or immediate GTA V deployment blocker fix).")
    parser.add_argument("--repo-root", default=".", help="Path to git repository root")
    parser.add_argument("--force-release", action="store_true", help="Force release even with < 3 commits since last tag")
    parser.add_argument("--release-blocker", action="store_true", help="Treat current build as immediate GTA V deployment blocker hotfix release")
    parser.add_argument("--deploy-failed", action="store_true", help="Block release strictly because GTA V deploy validation failed")
    parser.add_argument("--notes-out", default=None, help="Optional path to write Markdown release notes")
    parser.add_argument("--self-test", action="store_true", help="Run built-in unit checks and exit")
    parsed = parser.parse_args(argv)

    if parsed.self_test:
        return run_self_tests()

    force_env = os.environ.get("FORCE_RELEASE", "").strip().lower() in ("1", "true", "yes")
    blocker_env = os.environ.get("RELEASE_BLOCKER", "").strip().lower() in ("1", "true", "yes")
    deploy_env = os.environ.get("DEPLOY_CHECK_PASSED", "true").strip().lower() not in ("0", "false", "no")
    deploy_ok = deploy_env and not parsed.deploy_failed
    decision = evaluate_release_decision(
        Path(parsed.repo_root).resolve(),
        force_release=(parsed.force_release or force_env),
        release_blocker=(parsed.release_blocker or blocker_env),
        deploy_check_passed=deploy_ok,
    )

    if parsed.notes_out and decision["notes_markdown"]:
        notes_path = Path(parsed.notes_out)
        notes_path.parent.mkdir(parents=True, exist_ok=True)
        notes_path.write_text(decision["notes_markdown"], encoding="utf-8")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as out_handle:
            for key_name, val_str in decision.items():
                if key_name == "notes_markdown":
                    continue
                out_handle.write(f"{key_name}={val_str}\n")

    print(
        f"[SemVer CI] should_release={decision['should_release']} blocked={decision['release_blocked']} "
        f"reason={decision['release_reason']} tag={decision['tag']} prev_tag={decision['prev_tag'] or 'none'} "
        f"commits={decision['commit_count']}/{decision['commits_required']} bump={decision['bump_level']}"
    )
    return 1 if decision["release_blocked"] == "true" else 0


if __name__ == "__main__":
    raise SystemExit(main())
