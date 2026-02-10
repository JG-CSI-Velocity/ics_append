"""Tests for organizer.py -- file organization by client ID."""

from ics_append.organizer import classify_files, list_client_dirs, organize_directory


class TestClassifyFiles:
    def test_client_prefix(self):
        result = classify_files(["1453-ref.xlsx", "1217-dm.xlsx"])
        assert result == {"1453": ["1453-ref.xlsx"], "1217": ["1217-dm.xlsx"]}

    def test_incoming_files(self):
        result = classify_files(["notes.txt", "readme.md"])
        assert result == {"incoming": ["notes.txt", "readme.md"]}

    def test_mixed(self):
        result = classify_files(["1453-ref.xlsx", "notes.txt", "1217-dm.xlsx"])
        assert "1453" in result
        assert "1217" in result
        assert "incoming" in result

    def test_empty(self):
        assert classify_files([]) == {}

    def test_multiple_files_same_client(self):
        result = classify_files(["1453-ref.xlsx", "1453-dm.xlsx"])
        assert len(result["1453"]) == 2


class TestOrganizeDirectory:
    def test_moves_files_to_client_folders(self, base_dir):
        (base_dir / "1453-ref.xlsx").touch()
        (base_dir / "1217-dm.xlsx").touch()

        moved = organize_directory(base_dir)

        assert "1453" in moved
        assert "1217" in moved
        assert (base_dir / "1453" / "1453-ref.xlsx").exists()
        assert (base_dir / "1217" / "1217-dm.xlsx").exists()
        assert not (base_dir / "1453-ref.xlsx").exists()

    def test_moves_non_client_to_incoming(self, base_dir):
        (base_dir / "notes.txt").write_text("test")

        moved = organize_directory(base_dir)

        assert "incoming" in moved
        assert (base_dir / "incoming" / "notes.txt").exists()

    def test_dry_run_no_moves(self, base_dir):
        (base_dir / "1453-ref.xlsx").touch()

        moved = organize_directory(base_dir, dry_run=True)

        assert "1453" in moved
        # File should still be in original location
        assert (base_dir / "1453-ref.xlsx").exists()
        assert not (base_dir / "1453" / "1453-ref.xlsx").exists()

    def test_empty_dir(self, base_dir):
        moved = organize_directory(base_dir)
        assert moved == {}

    def test_skips_directories(self, base_dir):
        (base_dir / "subdir").mkdir()
        moved = organize_directory(base_dir)
        assert moved == {}


class TestListClientDirs:
    def test_lists_client_dirs(self, base_dir):
        (base_dir / "1453").mkdir()
        (base_dir / "1217").mkdir()
        (base_dir / "incoming").mkdir()

        result = list_client_dirs(base_dir)
        assert result == ["1217", "1453"]

    def test_excludes_special_dirs(self, base_dir):
        (base_dir / "1453").mkdir()
        (base_dir / "log").mkdir()
        (base_dir / "trends").mkdir()
        (base_dir / "incoming").mkdir()

        result = list_client_dirs(base_dir)
        assert result == ["1453"]

    def test_empty_dir(self, base_dir):
        assert list_client_dirs(base_dir) == []
