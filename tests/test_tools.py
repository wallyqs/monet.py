"""Tests for monet.tools — ported from Go test suite."""

from monet.tools import bash, edit, grep, list_dir, read, write


# ── read ─────────────────────────────────────────────────────────────


class TestRead:
    def test_basic(self, tmp_path):
        p = tmp_path / "test.txt"
        p.write_text("hello world")
        result = read(str(p))
        assert "hello world" in result

    def test_not_found(self):
        result = read("/nonexistent/file.txt")
        assert result.startswith("error:")

    def test_empty_path(self):
        result = read("")
        assert result.startswith("error:")

    def test_offset_and_limit(self, tmp_path):
        p = tmp_path / "lines.txt"
        p.write_text("aaa\nbbb\nccc\nddd\n")
        result = read(str(p), offset=1, limit=2)
        assert "bbb" in result
        assert "ccc" in result
        assert "aaa" not in result
        assert "ddd" not in result


# ── write ────────────────────────────────────────────────────────────


class TestWrite:
    def test_basic(self, tmp_path):
        p = tmp_path / "out.txt"
        result = write(str(p), "hello")
        assert "wrote" in result
        assert p.read_text() == "hello"

    def test_creates_dirs(self, tmp_path):
        p = tmp_path / "sub" / "dir" / "file.txt"
        result = write(str(p), "nested")
        assert "wrote" in result
        assert p.read_text() == "nested"

    def test_empty_path(self):
        result = write("", "content")
        assert result.startswith("error:")


# ── edit ─────────────────────────────────────────────────────────────


class TestEdit:
    def test_basic(self, tmp_path):
        p = tmp_path / "test.go"
        p.write_text('func main() {\n\tfmt.Println("hello")\n}\n')
        result = edit(str(p), '"hello"', '"world"')
        assert "edited" in result
        assert '"world"' in p.read_text()
        assert '"hello"' not in p.read_text()

    def test_diff_output(self, tmp_path):
        p = tmp_path / "test.txt"
        p.write_text("aaa\nbbb\nccc\n")
        result = edit(str(p), "bbb", "BBB")
        assert "edited" in result
        assert "--- " in result
        assert "+++ " in result
        assert "-bbb" in result
        assert "+BBB" in result

    def test_not_found_text(self, tmp_path):
        p = tmp_path / "test.txt"
        p.write_text("hello world\n")
        result = edit(str(p), "xyz", "abc")
        assert "not found" in result

    def test_duplicate_match(self, tmp_path):
        p = tmp_path / "test.go"
        p.write_text("foo\nbar\nfoo\n")
        result = edit(str(p), "foo", "baz")
        assert "2 locations" in result

    def test_missing_file(self):
        result = edit("/nonexistent/file.txt", "a", "b")
        assert result.startswith("error:")

    def test_empty_path(self):
        result = edit("", "a", "b")
        assert result.startswith("error:")


# ── bash ─────────────────────────────────────────────────────────────


class TestBash:
    def test_basic(self):
        result = bash("echo hello")
        assert result == "hello"

    def test_empty_command(self):
        result = bash("")
        assert result.startswith("error:")

    def test_nonzero_exit(self):
        result = bash("exit 1")
        assert "exit code" in result

    def test_stderr(self):
        result = bash("echo err >&2")
        assert "err" in result

    def test_timeout(self):
        result = bash("sleep 10", timeout=1)
        assert "timed out" in result


# ── grep ─────────────────────────────────────────────────────────────


class TestGrep:
    def test_basic(self, tmp_path):
        p = tmp_path / "test.go"
        p.write_text('func main() {\n\tfmt.Println("hi")\n}\n')
        result = grep("main", str(tmp_path))
        assert "main" in result

    def test_no_match(self, tmp_path):
        p = tmp_path / "test.go"
        p.write_text("package foo\n")
        result = grep("zzzznotfound", str(tmp_path))
        assert result == "no matches found"

    def test_single_file(self, tmp_path):
        p = tmp_path / "test.go"
        p.write_text("func hello() {}\n")
        result = grep("hello", str(p))
        assert "hello" in result

    def test_empty_pattern(self):
        result = grep("")
        assert result.startswith("error:")

    def test_missing_path(self):
        result = grep("foo", "/nonexistent/dir")
        assert result.startswith("error:")


# ── list_dir ─────────────────────────────────────────────────────────


class TestListDir:
    def test_basic(self, tmp_path):
        (tmp_path / "a.txt").write_text("")
        (tmp_path / "subdir").mkdir()
        result = list_dir(str(tmp_path))
        assert "a.txt" in result
        assert "subdir/" in result

    def test_empty_dir(self, tmp_path):
        result = list_dir(str(tmp_path))
        assert result == "(empty directory)"

    def test_not_a_dir(self, tmp_path):
        p = tmp_path / "file.txt"
        p.write_text("x")
        result = list_dir(str(p))
        assert "not a directory" in result

    def test_empty_path(self):
        result = list_dir("")
        assert result.startswith("error:")
