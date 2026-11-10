"""Tests for Hyper OS Creator. Run with:  python -m unittest discover tests"""
import base64
import contextlib
import io
import json
import os
import pathlib
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="hyperos-test-")
os.environ["HYPEROS_HOME"] = TMP

from hyperos import (cli, config, image, isos, kernels, net, prebuilt, resources, server,  # noqa: E402
                     suggestions, system, templates, toolchain)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


class ImageTests(unittest.TestCase):
    def test_floppy(self):
        img = image.make_floppy(prebuilt.HYPERBOOT, b"kernel")
        self.assertEqual(len(img), image.FLOPPY_SIZE)
        self.assertEqual(img[510:512], b"\x55\xaa")
        self.assertEqual(img[512:518], b"kernel")
        with self.assertRaises(ValueError):
            image.make_floppy(b"\x00" * 512)

    def test_iso_roundtrip_with_long_names_and_boot(self):
        with tempfile.TemporaryDirectory() as d:
            w = image.IsoWriter("TESTVOL")
            w.add_file("/boot/disk.img", image.make_floppy(prebuilt.HYPERBOOT))
            w.add_boot(image.BootEntry("/boot/disk.img", "floppy"))
            w.add_file("/A Very Long File Name With Spaces.txt", b"hello")
            w.add_file("/deep/er/still/file.bin", bytes(range(256)) * 20)
            w.add_file("/empty.txt", b"")
            for i in range(120):  # force a directory that spans several sectors
                w.add_file(f"/many/file-number-{i}.txt", f"{i}".encode())
            out = os.path.join(d, "t.iso")
            size = w.write(out)
            self.assertEqual(size % 2048, 0)
            with image.IsoReader(out) as r:
                self.assertTrue(r.rock_ridge)
                self.assertEqual(r.volume_id, "TESTVOL")
                self.assertEqual(r.read_file("/A Very Long File Name With Spaces.txt"), b"hello")
                self.assertEqual(r.read_file("/deep/er/still/file.bin"), bytes(range(256)) * 20)
                self.assertEqual(r.read_file("/empty.txt"), b"")
                self.assertEqual(r.read_file("/many/file-number-99.txt"), b"99")
                self.assertEqual(len([e for e in r.entries() if e.path.startswith("/many/")]), 120)
                boot = r.boot_info()
                self.assertEqual(len(boot), 1)
                self.assertEqual((boot[0].platform, boot[0].emulation, boot[0].file), ("bios", "floppy", "/boot/disk.img"))
                dest = os.path.join(d, "x")
                self.assertEqual(r.extract(dest, ["/deep"]), 1)
                self.assertTrue(os.path.exists(os.path.join(dest, "deep/er/still/file.bin")))

    def test_iso_no_emulation_boot_info_table_and_efi(self):
        with tempfile.TemporaryDirectory() as d:
            w = image.IsoWriter()
            loader = bytes(4096)
            w.add_file("/isolinux/isolinux.bin", loader)
            w.add_file("/efi.img", b"\x01" * 4096)
            w.add_boot(image.BootEntry("/isolinux/isolinux.bin", "none", 4, boot_info_table=True))
            w.add_boot(image.BootEntry("/efi.img", "efi"))
            out = os.path.join(d, "t.iso")
            w.write(out)
            with image.IsoReader(out) as r:
                info = r.boot_info()
                self.assertEqual([(b.platform, b.emulation) for b in info], [("bios", "none"), ("uefi", "none")])
                self.assertTrue(info[0].boot_info_table)
                patched = r.read_file("/isolinux/isolinux.bin")
                pvd, lba, length, _ = struct.unpack_from("<IIII", patched, 8)
                self.assertEqual((pvd, lba, length), (16, info[0].lba, 4096))

    def test_iso_validates_with_pycdlib_if_available(self):
        try:
            import pycdlib
        except ImportError:
            self.skipTest("pycdlib not installed")
        with tempfile.TemporaryDirectory() as d:
            w = image.IsoWriter("CHECK")
            w.add_file("/Hello World.txt", b"hi")
            w.add_file("/sub/dir/x.bin", b"x" * 5000)
            out = os.path.join(d, "t.iso")
            w.write(out)
            iso = pycdlib.PyCdlib()
            iso.open(out)
            self.assertTrue(iso.has_rock_ridge())
            names = [f for _, _, files in iso.walk(rr_path="/") for f in files]
            iso.close()
            self.assertIn("Hello World.txt", names)


class SystemTests(unittest.TestCase):
    def test_create_build_and_blob(self):
        slug = system.create("Unit Test OS", overwrite=True)
        data = system.load(slug)
        data["commands"].append({"name": "greet", "output": "hi\nthere"})
        system.save(slug, data)
        res = system.build(slug)
        self.assertTrue(res["ok"])
        img = pathlib.Path(res["image"]).read_bytes()
        self.assertEqual(img[3:7], b"HYPB")
        sectors = struct.unpack_from("<H", img, 7)[0]
        kernel = img[512:512 + sectors * 512]
        self.assertEqual(kernel[3:7], b"HYPK")
        blob_at = struct.unpack_from("<H", kernel, 7)[0]
        self.assertEqual(kernel[blob_at:blob_at + 4], b"HYPR")
        self.assertIn(b"greet\x00hi\r\nthere\x00", kernel)
        with image.IsoReader(res["iso"]) as r:
            self.assertEqual(r.read_file("/boot/hyperos.img"), img)
            self.assertEqual(json.loads(r.read_file("/system.json"))["name"], "Unit Test OS")

    def test_hyperboot_patch(self):
        sec = system.hyperboot_sector("Hello", fg=14, bg=4, wait_key=True, sectors=9)
        self.assertEqual(len(sec), 512)
        self.assertEqual(struct.unpack_from("<H", sec, 7)[0], 9)
        self.assertEqual(sec[9], 0x4E)
        self.assertEqual(sec[10], 1)
        self.assertEqual(sec[11:17], b"Hello\x00")

    def test_splash_limits(self):
        sec = system.splash_sector([{"x": 1, "y": 1, "text": "Hi"}])
        self.assertEqual(sec[510:], b"\x55\xaa")
        with self.assertRaises(ValueError):
            system.splash_sector([{"x": 0, "y": i, "text": "x" * 79} for i in range(10)])

    def test_render_desktop_matches_layout(self):
        screen = system.render_desktop({"ui": {"elements": [
            {"type": "fill", "fg": 7, "bg": 1},
            {"type": "box", "x": 2, "y": 3, "w": 10, "h": 4, "fg": 15, "bg": 2, "style": "double", "title": "T"},
            {"type": "text", "x": 5, "y": 5, "fg": 14, "bg": 2, "text": "ok"},
        ]}})
        self.assertEqual(screen[0][0], (" ", 0x17))
        self.assertEqual(screen[3][2], ("╔", 0x2F))
        self.assertEqual(screen[3][4], ("T", 0x2F))
        self.assertEqual(screen[6][11], ("╝", 0x2F))
        self.assertEqual(screen[5][5], ("o", 0x2E))

    def test_custom_asm_kernel_template(self):
        if not toolchain.which("nasm"):
            self.skipTest("nasm not installed")
        slug = system.create("Asm Kernel", overwrite=True)
        templates.use_in_system("kernels", "hello-kernel", slug)
        res = system.build(slug)
        self.assertTrue(res["ok"])
        self.assertIn("assembled kernel-hello-kernel.asm", res["log"])

    def test_build_error_reports_lines(self):
        if not toolchain.which("nasm"):
            self.skipTest("nasm not installed")
        slug = system.create("Broken", overwrite=True)
        (system.system_path(slug) / "src" / "bad.asm").write_text("bits 16\nmov ax,\n")
        data = system.load(slug)
        data["kernel"] = {"type": "custom-asm", "source": "bad.asm"}
        system.save(slug, data)
        with self.assertRaises(system.BuildError) as cm:
            system.build(slug)
        self.assertEqual(cm.exception.errors[0]["line"], 2)

    def test_prebuilt_is_up_to_date(self):
        if not toolchain.which("nasm"):
            self.skipTest("nasm not installed")
        proc = subprocess.run([sys.executable, str(ROOT / "tools" / "build_prebuilt.py"), "--check"])
        self.assertEqual(proc.returncode, 0, "run tools/build_prebuilt.py after editing hyperos/asm/")


class IsoProjectTests(unittest.TestCase):
    def test_remaster_python(self):
        slug = system.create("Remaster Me", overwrite=True)
        src = system.build(slug)["iso"]
        p = isos.Project.create("remaster-test", src)
        p.add_file("/extra/note.txt", b"added")
        p.remove("/system.json")
        res = p.build(use_xorriso=False, log=lambda _: None)
        with image.IsoReader(res["iso"]) as r:
            self.assertEqual(r.read_file("/extra/note.txt"), b"added")
            self.assertIsNone(r.find("/system.json"))
            self.assertEqual(r.boot_info()[0].file, "/boot/hyperos.img")


class ResourceTests(unittest.TestCase):
    def test_package_roundtrip_and_safety(self):
        data = resources.make_package({"name": "My Theme", "type": "theme"}, {"theme.json": b"{}"})
        pkg = resources.read_package(data)
        self.assertEqual(pkg["manifest"]["id"], "my-theme")
        buf = io.BytesIO()
        import zipfile
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("manifest.json", json.dumps({"id": "evil", "type": "theme", "name": "x"}))
            z.writestr("../escape.txt", "x")
        with self.assertRaises(ValueError):
            resources.read_package(buf.getvalue())
        with self.assertRaises(ValueError):
            resources.make_package({"name": "x", "type": "nope"}, {})

    def test_publish_get_apply(self):
        slug = system.create("Res Target", overwrite=True)
        theme = resources.make_package({"name": "Reds", "type": "theme"}, {"theme.json": json.dumps({
            "desktop": {"fg": 15, "bg": 4}, "box": {"fg": 14, "bg": 4}, "text": {"fg": 15, "bg": 4},
            "shell": {"fg": 12, "bg": 0}, "banner": {"fg": 15, "bg": 4}}).encode()})
        resources.publish_local(theme)
        self.assertIn("reds", [r["id"] for r in resources.search("red")["results"]])
        resources.get("reds", "local")
        resources.apply("reds", slug)
        data = system.load(slug)
        self.assertEqual(data["ui"]["elements"][0]["bg"], 4)
        self.assertEqual(data["shell"]["fg"], 12)
        cmds = resources.make_package({"name": "Cmds", "type": "command-pack"},
                                      {"commands.json": json.dumps([{"name": "zz", "output": "z"}]).encode()})
        resources.install(cmds)
        resources.apply("cmds", slug)
        self.assertIn("zz", [c["name"] for c in system.load(slug)["commands"]])

    def test_system_template_and_bundled_registry(self):
        if not (resources.bundled_registry_dir() / "index.json").exists():
            self.skipTest("no bundled registry")
        resources.get("pocket-os", "bundled")
        slug = resources.new_system_from("pocket-os", "From Template")
        self.assertEqual(system.load(slug)["shell"]["prompt"], "pocket> ")
        self.assertTrue(system.build(slug)["ok"])


class SuggestionTests(unittest.TestCase):
    def test_flow(self):
        s = suggestions.add("Add mouse support", "please", "kernel")
        suggestions.vote(s["id"])
        self.assertEqual(suggestions.list_suggestions()[0]["votes"], 2)
        suggestions.set_status(s["id"], "planned")
        self.assertIn("issues/new?", suggestions.issue_url(s["id"]))
        with self.assertRaises(ValueError):
            suggestions.add("no")


class ParserTests(unittest.TestCase):
    def test_sha256sums(self):
        h = "a" * 64
        self.assertEqual(net.parse_sha256sums(f"{h}  debian-13.1.0-amd64-netinst.iso\n{h} *x.iso\nSHA256 (y.iso) = {h}"),
                         [("debian-13.1.0-amd64-netinst.iso", h), ("x.iso", h), ("y.iso", h)])

    def test_latest_from_index(self):
        html = '<a href="grub-2.06.tar.xz">x</a><a href="grub-2.12.tar.xz">x</a><a href="grub-2.2.tar.xz">'
        self.assertEqual(net.latest_from_index(html, r"grub-(\d+(?:\.\d+)+)\.tar\.xz"), ("2.12", "grub-2.12.tar.xz"))

    def test_alpine_yaml(self):
        text = """---
-
  title: "Virtual"
  flavor: alpine-virt
  file: alpine-virt-3.22.2-x86_64.iso
  version: 3.22.2
  sha256: abc
-
  flavor: alpine-standard
  file: alpine-standard-3.22.2-x86_64.iso
"""
        r = isos.parse_alpine_yaml(text, "alpine-virt")
        self.assertEqual(r["filename"], "alpine-virt-3.22.2-x86_64.iso")
        self.assertEqual(r["sha256"], "abc")

    def test_arch_and_kernel_json(self):
        r = isos.parse_arch_json({"releases": [{"version": "2026.11.01", "sha256_sum": "f" * 64, "available": True}]})
        self.assertTrue(r["url"].endswith("2026.11.01/archlinux-2026.11.01-x86_64.iso"))
        rel = kernels.parse_releases({"latest_stable": {"version": "6.20.1"}, "releases": [
            {"moniker": "stable", "version": "6.20.1", "iseol": False, "released": {"isodate": "2026-11-01"},
             "source": "https://cdn.kernel.org/linux-6.20.1.tar.xz"},
            {"moniker": "linux-next", "version": "next-1", "source": None}]})
        self.assertEqual(len(rel), 1)
        self.assertTrue(rel[0]["latest"])

    def test_linux_config_fragment(self):
        frag = kernels.config_fragment(["base", "network"], "CONFIG_FOO=y")
        self.assertIn("CONFIG_INET=y", frag)
        self.assertIn("CONFIG_FOO=y", frag)


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = cli.main(list(args))
        return code, out.getvalue()

    def test_commands(self):
        self.assertEqual(self.run_cli("system", "new", "Cli OS")[0], 0)
        self.assertEqual(self.run_cli("system", "cmd-add", "cli-os", "hey", "there")[0], 0)
        code, out = self.run_cli("system", "build", "cli-os")
        self.assertEqual(code, 0, out)
        self.assertIn("ISO image", out)
        code, out = self.run_cli("system", "preview", "cli-os")
        self.assertIn("HyperOS", out)
        self.assertEqual(self.run_cli("tip")[0], 0)
        self.assertEqual(self.run_cli("bootloader", "templates")[0], 0)
        code, out = self.run_cli("iso", "inspect", str(system.system_path("cli-os") / "build" / "cli-os.iso"))
        self.assertIn("bios", out)
        code, out = self.run_cli("system", "show", "does-not-exist")
        self.assertEqual(code, 1)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        cls.port = s.getsockname()[1]
        s.close()
        cls.httpd = server.make_server("127.0.0.1", cls.port)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def call(self, method, path, body=None, headers=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_api(self):
        code, body = self.call("GET", "/")
        self.assertEqual(code, 200)
        self.assertIn(b"Hyper OS Creator", body)
        code, body = self.call("POST", "/api/systems", {"name": "Web OS"})
        self.assertEqual(code, 200)
        slug = json.loads(body)["slug"]
        code, body = self.call("POST", f"/api/systems/{slug}/build")
        self.assertTrue(json.loads(body)["ok"])
        code, body = self.call("POST", "/api/console", {"line": "system list"})
        self.assertIn("web-os", json.loads(body)["output"])
        code, _ = self.call("POST", "/api/systems", {"name": "Evil"}, {"Origin": "http://evil.example"})
        self.assertEqual(code, 403)
        code, _ = self.call("GET", "/api/file?path=/etc/passwd")
        self.assertEqual(code, 403)
        code, _ = self.call("GET", f"/api/systems/{slug}/file?name=../../../../etc/passwd")
        self.assertEqual(code, 400)
        pkg = resources.make_package({"name": "Shared", "type": "snippet"}, {"a.asm": b"nop"})
        code, body = self.call("POST", "/api/registry/publish", {"package": base64.b64encode(pkg).decode()})
        self.assertEqual(code, 200)
        code, body = self.call("GET", "/registry/index.json")
        self.assertIn("shared", [r["id"] for r in json.loads(body)["resources"]])


@unittest.skipUnless(toolchain.which("qemu-system-i386") and os.environ.get("HYPEROS_QEMU_TEST", "1") == "1",
                     "QEMU not installed")
class BootTests(unittest.TestCase):
    """Boot real images in QEMU and read the text screen from VGA memory."""

    def boot_screen(self, image_path, iso=True, seconds=3.0):
        with tempfile.TemporaryDirectory() as d:
            sock = os.path.join(d, "mon")
            dump = os.path.join(d, "vga.bin")
            drive = ["-cdrom", image_path, "-boot", "d"] if iso else \
                ["-drive", f"format=raw,file={image_path},if=floppy", "-boot", "a"]
            proc = subprocess.Popen([toolchain.which("qemu-system-i386"), "-m", "32", "-display", "none",
                                     "-monitor", f"unix:{sock},server,nowait", *drive],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                time.sleep(seconds)
                s = socket.socket(socket.AF_UNIX)
                s.connect(sock)
                time.sleep(0.2)
                s.recv(4096)
                s.send(f'pmemsave 0xb8000 4000 "{dump}"\n'.encode())
                for _ in range(50):
                    time.sleep(0.1)
                    if os.path.exists(dump) and os.path.getsize(dump) == 4000:
                        break
                s.close()
                vga = open(dump, "rb").read()
            finally:
                proc.kill()
                proc.wait()
        return "".join(chr(vga[i]) if 32 <= vga[i] < 127 else " " for i in range(0, 4000, 2))

    def test_desktop_boots_from_iso_and_floppy(self):
        slug = system.create("Boot Test", overwrite=True)
        data = system.load(slug)
        data["ui"]["elements"].append({"type": "text", "x": 1, "y": 20, "fg": 15, "bg": 1, "text": "BOOT-MARKER-42"})
        system.save(slug, data)
        res = system.build(slug)
        self.assertIn("BOOT-MARKER-42", self.boot_screen(res["iso"], iso=True))
        self.assertIn("BOOT-MARKER-42", self.boot_screen(res["image"], iso=False))

    def test_splash_boots(self):
        slug = system.create("Splash Test", overwrite=True)
        data = system.load(slug)
        data["bootloader"] = {"type": "splash", "fg": 15, "bg": 1, "lines": [{"x": 3, "y": 3, "text": "SPLASH-OK"}]}
        system.save(slug, data)
        self.assertIn("SPLASH-OK", self.boot_screen(system.build(slug)["iso"]))


if __name__ == "__main__":
    unittest.main()
