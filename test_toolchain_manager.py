from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import toolchain_manager


class ToolchainManagerTests(unittest.TestCase):
    def test_normalize_bin_dir_accepts_toolchain_root_or_bin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "llvm"
            bin_dir = root / "bin"
            bin_dir.mkdir(parents=True)
            self.assertEqual(toolchain_manager.normalize_bin_dir(root), bin_dir)
            self.assertEqual(toolchain_manager.normalize_bin_dir(bin_dir), bin_dir)

    def test_merge_path_entry_is_idempotent(self) -> None:
        existing = r"C:\\Windows;C:\\LLVM\\bin"
        self.assertEqual(
            toolchain_manager.merge_path_entry(existing, r"c:\\llvm\\bin"),
            existing,
        )
        updated = toolchain_manager.merge_path_entry(existing, r"C:\\CompanionAI\\llvm\\bin")
        self.assertTrue(updated.startswith(r"C:\\CompanionAI\\llvm\\bin;"))

    def test_status_detects_clang_and_preserves_configured_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_file = Path(directory) / "toolchain.json"
            config_file.write_text(
                '{"install_dir":"C:/CompanionAI/toolchains/llvm","bin_dir":"C:/CompanionAI/toolchains/llvm/bin"}',
                encoding="utf-8",
            )
            with (
                patch.object(toolchain_manager, "CONFIG_FILE", config_file),
                patch.object(toolchain_manager.shutil, "which", side_effect=lambda name: r"C:\\LLVM\\bin\\clang++.exe" if name == "clang++" else ""),
            ):
                status = toolchain_manager.status()

        self.assertTrue(status["installed"])
        self.assertEqual(status["compiler"], r"C:\\LLVM\\bin\\clang++.exe")
        self.assertEqual(status["bin_dir"], "C:/CompanionAI/toolchains/llvm/bin")


if __name__ == "__main__":
    unittest.main()
