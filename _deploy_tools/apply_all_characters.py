#!/usr/bin/env python3
"""
apply_all_characters.py
=======================
Legacy convenience entrypoint that applies Universal Slot Replacement to all
three Grand Theft Auto V protagonists simultaneously:
  1. Michael  (player_zero) -> Shinano Eternal Reunion
  2. Franklin (player_one)  -> Shinano Casual / Uniform
  3. Trevor   (player_two)  -> Miltina Maid
"""

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

try:
    import apply_characters
    import vrc2gtav_i18n as project_i18n
except ImportError:
    from common_tools import apply_characters
    from common_tools import vrc2gtav_i18n as project_i18n


def main() -> None:
    """Apply compiled avatars for all three protagonists and report next step."""
    project_i18n.set_active_language()
    argument_parser = argparse.ArgumentParser(
        description=project_i18n.translate("apply.cli_description")
    )
    argument_parser.add_argument(
        "--lang",
        choices=["auto", "en", "ja", "pt"],
        default="auto",
        help=project_i18n.translate("common.language_option_help"),
    )
    parsed_arguments = argument_parser.parse_args()
    project_i18n.set_active_language(parsed_arguments.lang)

    all_protagonists = ["player_zero", "player_one", "player_two"]
    operation_success = apply_characters.apply_selected_characters(all_protagonists)
    if not operation_success:
        sys.exit(1)

    print(project_i18n.translate("apply.next_step_repack"))


if __name__ == "__main__":
    main()
