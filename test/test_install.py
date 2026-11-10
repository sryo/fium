"""install.sh, run as `curl ... | bash` runs it (the script on stdin), with a temp HOME, FIUM_REPO
on a file:// clone of this repo and FIUM_BIN_DIR in the temp dir: the clone, the skill link and
the CLI link land, a second run changes nothing, an unwritable bin dir falls back to
~/.local/bin, and a directory or a link to somewhere else is left in place."""
import os, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Install(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.origin = Path(cls.tmpdir.name) / "origin.git"
        subprocess.run(["git", "clone", "--quiet", "--bare", str(ROOT), str(cls.origin)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def setUp(self):
        self.home = Path(tempfile.mkdtemp(dir=self.tmpdir.name))
        self.dir = self.home / "Documents" / "fium"
        self.link = self.home / ".claude" / "skills" / "fium"
        self.bin = self.home / "bin"
        self.bin.mkdir()

    def install(self, path=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("FIUM_", "GIT_"))}
        env.update(HOME=str(self.home), FIUM_REPO=f"file://{self.origin}", FIUM_BIN_DIR=str(self.bin))
        if path is not None:
            env["PATH"] = path
        p = subprocess.run(["bash"], input=(ROOT / "install.sh").read_text(), env=env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p.stdout

    def head(self):
        return subprocess.run(["git", "-C", str(self.dir), "rev-parse", "HEAD"], capture_output=True, text=True).stdout

    def test_installs_then_is_idempotent(self):
        self.install()
        self.assertTrue((self.dir / "SKILL.md").is_file())
        self.assertEqual(os.readlink(self.link), str(self.dir))
        self.assertEqual(os.readlink(self.bin / "fium"), str(self.dir / "fium"))
        head = self.head()
        out = self.install()
        self.assertIn("pulling latest", out)
        self.assertEqual(out.count("already links to"), 2)
        self.assertEqual(self.head(), head)
        self.assertEqual(sorted(os.listdir(self.bin)), ["fium"])

    def test_unwritable_bin_falls_back_to_local_bin(self):
        self.bin.chmod(0o555)
        try:
            out = self.install(path="/usr/bin:/bin")
        finally:
            self.bin.chmod(0o755)
        self.assertFalse((self.bin / "fium").exists())
        self.assertEqual(os.readlink(self.home / ".local" / "bin" / "fium"), str(self.dir / "fium"))
        self.assertIn("isn't writable", out)
        self.assertIn(f'export PATH="{self.home}/.local/bin:$PATH"', out)
        code = [l for l in (ROOT / "install.sh").read_text().splitlines() if not l.lstrip().startswith("#")]
        self.assertEqual([l for l in code if "sudo" in l], [])

    def test_leaves_what_it_finds_in_place(self):
        self.link.mkdir(parents=True)
        (self.bin / "fium").write_text("#!/bin/sh\n")
        out = self.install()
        self.assertFalse(self.link.is_symlink())
        self.assertFalse((self.bin / "fium").is_symlink())
        self.assertEqual(out.count("exists and isn't a link; leaving it"), 2)

    def test_leaves_a_link_elsewhere_in_place(self):
        other = self.home / "other" / "fium"
        (self.bin / "fium").symlink_to(other)
        out = self.install()
        self.assertEqual(os.readlink(self.bin / "fium"), str(other))
        self.assertIn(f"links to {other}, not {self.dir / 'fium'}; leaving it", out)

    def test_an_install_elsewhere_is_reused(self):
        other = self.home / "src" / "fium"
        other.mkdir(parents=True)
        (other / "SKILL.md").write_text("")
        self.link.parent.mkdir(parents=True)
        self.link.symlink_to(other)
        out = self.install()
        self.assertIn("already installed", out)
        self.assertFalse(self.dir.exists())
        self.assertEqual(os.readlink(self.bin / "fium"), str(other / "fium"))


if __name__ == "__main__":
    unittest.main()
