"""Command line interface: everything the web app can do, from a terminal.

Run ``hyperos --help`` (or ``python -m hyperos --help``) for an overview.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import time
from typing import Any, List, Optional

from . import (__version__, bootloaders, config, downloads, isos, kernels, resources, suggestions, system,
               templates, tips, toolchain)

# ---------------------------------------------------------------------------
# output helpers
# ---------------------------------------------------------------------------

_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def c(text: str, code: str) -> str:
    return f"\x1b[{code}m{text}\x1b[0m" if _COLOR else text


def table(rows: List[List[Any]], headers: List[str]) -> None:
    rows = [[str(x) for x in r] for r in rows]
    widths = [max([len(h)] + [len(r[i]) for r in rows]) for i, h in enumerate(headers)]
    print(c("  ".join(h.ljust(w) for h, w in zip(headers, widths)), "1"))
    for r in rows:
        print("  ".join(x.ljust(w) for x, w in zip(r, widths)))
    if not rows:
        print(c("(nothing here yet)", "2"))


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class Bar:
    def __init__(self, label: str):
        self.label, self.last = label, 0.0

    def __call__(self, done: int, total: int) -> None:
        now = time.time()
        if now - self.last < 0.1 and done != total:
            return
        self.last = now
        if total:
            pct = done / total
            bar = "#" * int(pct * 30)
            sys.stderr.write(f"\r{self.label} [{bar:<30}] {pct * 100:5.1f}% {human(done)}/{human(total)}")
        else:
            sys.stderr.write(f"\r{self.label} {human(done)}")
        sys.stderr.flush()

    def end(self) -> None:
        sys.stderr.write("\n")


def tip_line(topic: Optional[str] = None) -> None:
    if config.load_settings().get("show_tips", True) and sys.stdout.isatty():
        print(c("Tip: ", "33;1") + c(tips.random_tip(topic), "33"))


def colour(value: str) -> int:
    if value.isdigit():
        return int(value) & 15
    return system.COLORS.index(value.lower())


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_tip(a) -> None:
    if a.all:
        for t in tips.all_tips(a.topic):
            print(f"[{t['topic']}] {t['tip']}")
    else:
        print(c("Tip: ", "33;1") + tips.random_tip(a.topic))


def cmd_doctor(a) -> None:
    print(c(f"Hyper OS Creator {__version__}", "1") + f"  workspace: {config.home()}")
    for name, info in toolchain.status().items():
        mark = c("found  ", "32") if info["found"] else c("missing", "31")
        print(f"  {mark} {name:<18} {info['purpose']}")
    print("Building systems needs none of these - they unlock extra features.")


def cmd_serve(a) -> None:
    from . import server
    server.serve(a.host, a.port, open_browser=not a.no_browser)


def cmd_shell(a) -> None:
    try:
        import readline  # noqa: F401 - enables history/editing
        words = ["system", "bootloader", "kernel", "iso", "resources", "suggest", "tip", "doctor", "config",
                 "list", "new", "build", "run", "show", "preview", "download", "templates", "search", "get",
                 "publish", "help", "exit"]
        readline.set_completer(lambda text, state: ([w for w in words if w.startswith(text)] + [None])[state])
        readline.parse_and_bind("tab: complete")
    except ImportError:
        pass
    print(c("Hyper OS Creator shell", "1;36") + " - type a command without 'hyperos', 'help' or 'exit'.")
    tip_line()
    while True:
        try:
            line = input(c("hyperos> ", "36;1")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if line in ("exit", "quit"):
            return
        if not line:
            continue
        if line == "help":
            line = "--help"
        try:
            main(shlex.split(line))
        except SystemExit:
            pass


# -- systems -------------------------------------------------------------------

def cmd_system(a) -> None:
    act = a.action
    if act == "list":
        table([[s["slug"], s["name"], s["version"], "yes" if s["built"] else "no"] for s in system.list_systems()],
              ["SLUG", "NAME", "VERSION", "BUILT"])
    elif act == "new":
        if a.from_resource:
            slug = resources.new_system_from(a.from_resource, a.name)
        else:
            slug = system.create(a.name)
        print(f"Created system '{slug}' in {system.system_path(slug)}")
        print(f"Next: hyperos system build {slug}")
    elif act == "show":
        print(json.dumps(system.load(a.slug), indent=2))
    elif act == "preview":
        print(system.render_ansi(system.load(a.slug)))
    elif act == "build":
        try:
            res = system.build(a.slug)
            print(res["log"])
        except system.BuildError as exc:
            print(c(f"Build failed: {exc}", "31;1"))
            print(exc.log)
            sys.exit(1)
        tip_line("start")
    elif act == "run":
        base = system.system_path(a.slug) / "build"
        image = base / (f"{a.slug}.img" if a.floppy else f"{a.slug}.iso")
        if not image.exists() or a.rebuild:
            system.build(a.slug)
        toolchain.run_qemu(str(image), iso=not a.floppy).wait()
    elif act == "delete":
        system.delete(a.slug)
        print(f"Deleted {a.slug}")
    elif act == "set":
        data = system.load(a.slug)
        for pair in a.values:
            key, _, value = pair.partition("=")
            target = data
            parts = key.split(".")
            for p in parts[:-1]:
                target = target.setdefault(p, {})
            try:
                target[parts[-1]] = json.loads(value)
            except ValueError:
                target[parts[-1]] = value
        system.save(a.slug, data)
        print("Saved.")
    elif act == "cmd-add":
        data = system.load(a.slug)
        data["commands"] = [x for x in data["commands"] if x["name"] != a.name] + \
            [{"name": a.name, "output": a.output.replace("\\n", "\n")}]
        system.save(a.slug, data)
        print(f"Added command '{a.name}'. Rebuild to use it.")
    elif act == "cmd-rm":
        data = system.load(a.slug)
        data["commands"] = [x for x in data["commands"] if x["name"] != a.name]
        system.save(a.slug, data)
        print(f"Removed command '{a.name}'.")
    elif act == "text-add":
        data = system.load(a.slug)
        data["ui"]["elements"].append({"type": "text", "x": a.x, "y": a.y, "fg": colour(a.fg), "bg": colour(a.bg),
                                       "text": a.text})
        system.save(a.slug, data)
        print("Text added. Preview it with: hyperos system preview " + a.slug)
    elif act == "box-add":
        data = system.load(a.slug)
        data["ui"]["elements"].append({"type": "box", "x": a.x, "y": a.y, "w": a.w, "h": a.h, "fg": colour(a.fg),
                                       "bg": colour(a.bg), "style": a.style, "title": a.title})
        system.save(a.slug, data)
        print("Box added. Preview it with: hyperos system preview " + a.slug)


# -- bootloaders ------------------------------------------------------------

def cmd_bootloader(a) -> None:
    act = a.action
    if act == "list":
        print(c("Download from the internet:", "1"))
        table([[b["id"], b["name"], b["description"]] for b in bootloaders.catalog()], ["ID", "NAME", "DESCRIPTION"])
        print()
        print(c("Downloaded:", "1"))
        table([[d["file"], d["version"], human(d["size"])] for d in downloads.list_downloads("bootloader")],
              ["FILE", "VERSION", "SIZE"])
        print()
        print(c("Custom (library):", "1"))
        table([[b["name"], b["size"], b["path"]] for b in bootloaders.list_custom()], ["NAME", "BYTES", "PATH"])
    elif act == "templates":
        table([[t["id"], t["difficulty"], t["description"]] for t in templates.list_templates("bootloaders")],
              ["ID", "LEVEL", "DESCRIPTION"])
    elif act == "download":
        bar = Bar(a.id)
        item = bootloaders.download_url(a.id, progress=bar) if "://" in a.id else bootloaders.download(a.id, bar)
        bar.end()
        print(f"Saved {item['path']} ({human(item['size'])}) sha256={item['sha256'][:16]}...")
    elif act == "build":
        res = bootloaders.build_from_code(open(a.file).read(), a.name or os.path.splitext(os.path.basename(a.file))[0])
        print(res.get("log", ""))
        for w in res.get("warnings", []):
            print(c("warning: " + w, "33"))
        if "path" in res:
            print(f"Saved {res['path']} ({res['size']} bytes)")
        if not res["ok"]:
            sys.exit(1)
    elif act == "hyperboot":
        res = bootloaders.build_hyperboot(a.banner, colour(a.fg), colour(a.bg), a.wait_key, a.name)
        print(f"Saved {res['path']}")
    elif act == "splash":
        lines = [{"x": 2, "y": 2 + i * 2, "text": t, "fg": colour(a.fg)} for i, t in enumerate(a.text)]
        res = bootloaders.build_splash(lines, colour(a.fg), colour(a.bg), a.name)
        print(f"Saved {res['path']} and bootable floppy {res['image']}")
    elif act == "template":
        for name, text in templates.read_template("bootloaders", a.id).items():
            print(c(f"--- {name}", "1"))
            print(text)
    elif act == "use":
        print(json.dumps(templates.use_in_system("bootloaders", a.id, a.slug), indent=2))


# -- kernels ------------------------------------------------------------------

def cmd_kernel(a) -> None:
    act = a.action
    if act == "releases":
        table([[r["version"], r["moniker"], r["date"], "EOL" if r["eol"] else ""] for r in kernels.releases()],
              ["VERSION", "TYPE", "RELEASED", ""])
    elif act == "prebuilt":
        table([[p["id"], p["name"], p["description"]] for p in kernels.PREBUILT], ["ID", "NAME", "DESCRIPTION"])
    elif act == "download":
        bar = Bar(a.what)
        if "://" in a.what:
            items = [kernels.download_url(a.what, bar)]
        elif any(p["id"] == a.what for p in kernels.PREBUILT):
            items = kernels.download_prebuilt(a.what, bar)
        else:
            items = [kernels.download_source(a.what, bar)]
        bar.end()
        for it in items:
            print(f"Saved {it['path']} ({human(it['size'])})")
    elif act == "list":
        table([[d["file"], d["version"], d.get("type", ""), human(d["size"])] for d in downloads.list_downloads("kernel")],
              ["FILE", "VERSION", "TYPE", "SIZE"])
    elif act == "templates":
        table([[t["id"], t["difficulty"], t["description"]] for t in templates.list_templates("kernels")],
              ["ID", "LEVEL", "DESCRIPTION"])
    elif act == "template":
        for name, text in templates.read_template("kernels", a.id).items():
            print(c(f"--- {name}", "1"))
            print(text)
    elif act == "use":
        print(json.dumps(templates.use_in_system("kernels", a.id, a.slug), indent=2))
    elif act == "features":
        table([[k, v["label"]] for k, v in kernels.LINUX_FEATURES.items()], ["FEATURE", "DESCRIPTION"])
    elif act == "config":
        print(kernels.config_fragment(a.features))
    elif act == "build-linux":
        kernels.build_linux(a.tarball, a.features, base=a.base)
    elif act == "run":
        qemu = toolchain.which("qemu-system-x86_64") or toolchain.which("qemu-system-i386")
        if not qemu:
            sys.exit("QEMU is not installed")
        cmd = [qemu, "-m", "512", "-kernel", a.kernel] + (["-initrd", a.initrd] if a.initrd else [])
        os.execvp(cmd[0], cmd)


# -- ISOs -------------------------------------------------------------------------

def cmd_iso(a) -> None:
    act = a.action
    if act == "catalog":
        table([[i["id"], i["name"], i["size"], i["description"]] for i in isos.catalog()],
              ["ID", "NAME", "SIZE", "DESCRIPTION"])
    elif act == "download":
        bar = Bar(a.what)
        item = isos.download_url(a.what, a.sha256, bar) if "://" in a.what else isos.download(a.what, bar)
        bar.end()
        print(f"Saved {item['path']} ({human(item['size'])}), checksum verified" if item.get("sha256") else "")
        tip_line("iso")
    elif act == "list":
        table([[i["file"], i["source"], human(i["size"]), i["path"]] for i in isos.local_isos()],
              ["FILE", "SOURCE", "SIZE", "PATH"])
    elif act == "inspect":
        info = isos.inspect(a.iso)
        print(f"Volume: {info['volume_id']}  Rock Ridge: {info['rock_ridge']}  Joliet: {info['joliet']}")
        print(f"Files: {info['file_count']}  ({human(info['total_size'])})")
        for b in info["boot"]:
            print(f"Boot: {b['platform']:<5} {b['emulation']:<8} {b['file'] or '(hidden image)'}"
                  + ("  [boot info table]" if b["boot_info_table"] else ""))
        if not info["boot"]:
            print("Boot: not bootable")
    elif act == "ls":
        prefix = "/" + (a.path or "").strip("/")
        for f in isos.inspect(a.iso)["files"]:
            if f["path"].startswith(prefix.rstrip("/") + "/") or prefix == "/":
                depth = f["path"].count("/") - prefix.rstrip("/").count("/")
                if a.recursive or depth == 1:
                    print(f"{'d' if f['dir'] else '-'} {human(f['size']):>9}  {f['path']}")
    elif act == "cat":
        sys.stdout.buffer.write(isos.read_file(a.iso, a.path))
    elif act == "extract":
        n = isos.extract(a.iso, a.dest, a.only or None)
        print(f"Extracted {n} files to {a.dest}")
    elif act == "projects":
        table([[p["name"], os.path.basename(p["source"]), len(p["changes"]["added"]), len(p["changes"]["removed"])]
               for p in isos.Project.list_projects()], ["PROJECT", "SOURCE ISO", "ADDED", "REMOVED"])
    elif act == "project":
        if a.op == "new":
            p = isos.Project.create(a.name, a.args[0])
            print(f"Created ISO project '{p.name}'. Add files with: hyperos iso project add {p.name} /path/in/iso local-file")
            return
        p = isos.Project(a.name)
        if a.op == "add":
            p.add_local(a.args[0], a.args[1])
            print(f"Will add {a.args[1]} as {a.args[0]}")
        elif a.op == "rm":
            p.remove(a.args[0])
            print(f"Will remove {a.args[0]}")
        elif a.op == "build":
            res = p.build(use_xorriso=False if a.python else None)
            print(f"Built {res['iso']} ({human(res['size'])}) using {res['method']}")
        elif a.op == "show":
            print(json.dumps({**p.plan(), "changes": p.changes()}, indent=2))


# -- resources -------------------------------------------------------------------

def cmd_resources(a) -> None:
    act = a.action
    if act == "search":
        res = resources.search(a.query or "", a.type or "")
        table([[r["id"], r["type"], r.get("version", ""), r.get("author", ""), r["registry"][:40],
                r.get("description", "")[:50]] for r in res["results"]],
              ["ID", "TYPE", "VERSION", "AUTHOR", "REGISTRY", "DESCRIPTION"])
        for e in res["errors"]:
            print(c(f"(registry {e['registry']} unavailable: {e['error']})", "2"))
    elif act == "get":
        m = resources.get(a.id, a.registry)
        print(f"Installed {m['id']} {m['version']} ({m['type']}). Apply it with: hyperos resources apply {m['id']} <system>")
    elif act == "installed":
        table([[m["id"], m["type"], m["version"], m.get("description", "")[:60]] for m in resources.installed()],
              ["ID", "TYPE", "VERSION", "DESCRIPTION"])
    elif act == "apply":
        print(resources.apply(a.id, a.slug)["note"])
    elif act == "uninstall":
        resources.uninstall(a.id)
        print("Removed.")
    elif act == "create":
        data = resources.from_system(a.slug, a.type, {"name": a.name, "description": a.description or ""})
        out = a.out or f"{config.slugify(a.name or a.slug + '-' + a.type)}.hyperpkg"
        open(out, "wb").write(data)
        print(f"Wrote {out}. Publish it with: hyperos resources publish {out}")
    elif act == "pack":
        data = resources.package_from_files({"name": a.name, "type": a.type, "description": a.description or ""},
                                            a.files)
        out = a.out or f"{config.slugify(a.name)}.hyperpkg"
        open(out, "wb").write(data)
        print(f"Wrote {out}")
    elif act == "publish":
        data = open(a.file, "rb").read()
        res = resources.publish_remote(data, a.remote) if a.remote else resources.publish_local(data)
        print(json.dumps(res, indent=2))
    elif act == "install":
        m = resources.install(open(a.file, "rb").read())
        print(f"Installed {m['id']}")
    elif act == "index":
        import pathlib
        idx = resources.rebuild_index(pathlib.Path(a.dir))
        print(f"Indexed {len(idx['resources'])} resources in {a.dir}/index.json")


# -- suggestions -------------------------------------------------------------------

def cmd_suggest(a) -> None:
    act = a.action
    if act == "add":
        s = suggestions.add(a.title, a.description or "", a.category, a.author or "")
        print(f"Thanks! Saved suggestion {s['id']}. Share it with: hyperos suggest github {s['id']}")
    elif act == "list":
        table([[s["id"], s["votes"], s["status"], s["category"], s["title"][:60]]
               for s in suggestions.list_suggestions(category=a.category or "")],
              ["ID", "VOTES", "STATUS", "CATEGORY", "TITLE"])
    elif act == "vote":
        s = suggestions.vote(a.id, -1 if a.down else 1)
        print(f"'{s['title']}' now has {s['votes']} votes")
    elif act == "status":
        suggestions.set_status(a.id, a.status)
        print("Updated.")
    elif act == "github":
        print(suggestions.issue_url(a.id))
    elif act == "delete":
        suggestions.delete(a.id)
        print("Deleted.")


def cmd_config(a) -> None:
    s = config.load_settings()
    if a.action == "show":
        print(json.dumps(s, indent=2))
    elif a.action == "set":
        try:
            s[a.key] = json.loads(a.value)
        except ValueError:
            s[a.key] = a.value
        config.save_settings(s)
        print("Saved.")
    elif a.action == "add-registry":
        s["registries"] = [r for r in s["registries"] if r != a.value] + [a.value]
        config.save_settings(s)
        print("Registry added.")


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hyperos", description="Hyper OS Creator - build, remix and share operating systems.",
                                epilog="Run 'hyperos serve' to open the visual editor in your browser.")
    p.add_argument("--version", action="version", version=f"Hyper OS Creator {__version__}")
    sub = p.add_subparsers(dest="cmd", metavar="COMMAND")

    s = sub.add_parser("serve", help="start the web app (UI editor, code editor, ...)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8642)
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(fn=cmd_serve)

    sub.add_parser("shell", help="interactive Hyper OS console").set_defaults(fn=cmd_shell)
    sub.add_parser("doctor", help="check which optional tools are installed").set_defaults(fn=cmd_doctor)
    t = sub.add_parser("tip", help="show a tip")
    t.add_argument("--topic", choices=tips.TOPICS)
    t.add_argument("--all", action="store_true")
    t.set_defaults(fn=cmd_tip)

    # system
    sy = sub.add_parser("system", help="create, build and run custom systems").add_subparsers(dest="action", required=True)
    sy.add_parser("list")
    x = sy.add_parser("new")
    x.add_argument("name")
    x.add_argument("--from-resource", help="start from an installed system-template resource")
    for name in ("show", "preview", "build", "delete"):
        sy.add_parser(name).add_argument("slug")
    x = sy.add_parser("run")
    x.add_argument("slug")
    x.add_argument("--floppy", action="store_true", help="boot the .img instead of the .iso")
    x.add_argument("--rebuild", action="store_true")
    x = sy.add_parser("set", help="set values, e.g. version=2.0 shell.prompt='me> '")
    x.add_argument("slug")
    x.add_argument("values", nargs="+")
    x = sy.add_parser("cmd-add", help="add a custom shell command")
    x.add_argument("slug")
    x.add_argument("name")
    x.add_argument("output")
    x = sy.add_parser("cmd-rm")
    x.add_argument("slug")
    x.add_argument("name")
    x = sy.add_parser("text-add", help="add text to the desktop")
    x.add_argument("slug")
    x.add_argument("text")
    x.add_argument("--x", type=int, default=2)
    x.add_argument("--y", type=int, default=2)
    x.add_argument("--fg", default="white")
    x.add_argument("--bg", default="blue")
    x = sy.add_parser("box-add", help="add a window/box to the desktop")
    x.add_argument("slug")
    x.add_argument("--title", default="")
    for k, d in (("x", 10), ("y", 5), ("w", 30), ("h", 8)):
        x.add_argument(f"--{k}", type=int, default=d)
    x.add_argument("--fg", default="white")
    x.add_argument("--bg", default="blue")
    x.add_argument("--style", choices=list(system.BOX_STYLES), default="single")
    sub.choices["system"].set_defaults(fn=cmd_system)

    # bootloader
    b = sub.add_parser("bootloader", help="download or create bootloaders").add_subparsers(dest="action", required=True)
    b.add_parser("list")
    b.add_parser("templates")
    b.add_parser("download").add_argument("id", help="catalog id or a URL")
    x = b.add_parser("build", help="assemble a NASM boot sector")
    x.add_argument("file")
    x.add_argument("--name")
    x = b.add_parser("hyperboot", help="generate a HyperBoot loader (no tools needed)")
    x.add_argument("--banner", default="HyperBoot")
    x.add_argument("--fg", default="white")
    x.add_argument("--bg", default="blue")
    x.add_argument("--wait-key", action="store_true")
    x.add_argument("--name", default="hyperboot")
    x = b.add_parser("splash", help="generate a one-sector splash 'OS' (no tools needed)")
    x.add_argument("text", nargs="+")
    x.add_argument("--fg", default="yellow")
    x.add_argument("--bg", default="blue")
    x.add_argument("--name", default="splash")
    b.add_parser("template").add_argument("id")
    x = b.add_parser("use", help="use a template in a system")
    x.add_argument("id")
    x.add_argument("slug")
    sub.choices["bootloader"].set_defaults(fn=cmd_bootloader)

    # kernel
    k = sub.add_parser("kernel", help="download or create kernels").add_subparsers(dest="action", required=True)
    for name in ("releases", "prebuilt", "list", "templates", "features"):
        k.add_parser(name)
    k.add_parser("download").add_argument("what", help="kernel.org version, prebuilt id or URL")
    k.add_parser("template").add_argument("id")
    x = k.add_parser("use")
    x.add_argument("id")
    x.add_argument("slug")
    k.add_parser("config", help="print a Linux config fragment").add_argument("features", nargs="*")
    x = k.add_parser("build-linux")
    x.add_argument("tarball")
    x.add_argument("--features", nargs="*", default=["base", "serial", "vga", "virtio", "storage"])
    x.add_argument("--base", default="tinyconfig")
    x = k.add_parser("run", help="boot a Linux kernel in QEMU")
    x.add_argument("kernel")
    x.add_argument("--initrd")
    sub.choices["kernel"].set_defaults(fn=cmd_kernel)

    # iso
    i = sub.add_parser("iso", help="download, inspect and modify ISO images").add_subparsers(dest="action", required=True)
    i.add_parser("catalog")
    i.add_parser("list")
    x = i.add_parser("download")
    x.add_argument("what", help="catalog id or URL")
    x.add_argument("--sha256")
    i.add_parser("inspect").add_argument("iso")
    x = i.add_parser("ls")
    x.add_argument("iso")
    x.add_argument("path", nargs="?")
    x.add_argument("-r", "--recursive", action="store_true")
    x = i.add_parser("cat")
    x.add_argument("iso")
    x.add_argument("path")
    x = i.add_parser("extract")
    x.add_argument("iso")
    x.add_argument("dest")
    x.add_argument("--only", nargs="*")
    i.add_parser("projects")
    x = i.add_parser("project", help="new NAME ISO | add NAME ISO_PATH LOCAL | rm NAME ISO_PATH | build NAME | show NAME")
    x.add_argument("op", choices=["new", "add", "rm", "build", "show"])
    x.add_argument("name")
    x.add_argument("args", nargs="*")
    x.add_argument("--python", action="store_true", help="use the built-in builder even if xorriso exists")
    sub.choices["iso"].set_defaults(fn=cmd_iso)

    # resources
    r = sub.add_parser("resources", help="get, create and publish resources").add_subparsers(dest="action", required=True)
    x = r.add_parser("search")
    x.add_argument("query", nargs="?")
    x.add_argument("--type", choices=list(resources.TYPES))
    x = r.add_parser("get")
    x.add_argument("id")
    x.add_argument("--registry", default="local", help="'local' or a registry URL")
    r.add_parser("installed")
    x = r.add_parser("apply")
    x.add_argument("id")
    x.add_argument("slug")
    r.add_parser("uninstall").add_argument("id")
    r.add_parser("install").add_argument("file")
    x = r.add_parser("create", help="make a resource from a system")
    x.add_argument("slug")
    x.add_argument("--type", required=True, choices=["theme", "ui-layout", "command-pack", "system-template"])
    x.add_argument("--name")
    x.add_argument("--description")
    x.add_argument("--out")
    x = r.add_parser("pack", help="make a resource from files")
    x.add_argument("files", nargs="+")
    x.add_argument("--name", required=True)
    x.add_argument("--type", required=True, choices=list(resources.TYPES))
    x.add_argument("--description")
    x.add_argument("--out")
    x = r.add_parser("publish")
    x.add_argument("file")
    x.add_argument("--remote", help="registry URL (a 'hyperos serve' server or the GitHub registry)")
    r.add_parser("index", help="rebuild a registry index.json").add_argument("dir")
    sub.choices["resources"].set_defaults(fn=cmd_resources)

    # suggestions
    g = sub.add_parser("suggest", help="suggest features and vote").add_subparsers(dest="action", required=True)
    x = g.add_parser("add")
    x.add_argument("title")
    x.add_argument("-d", "--description")
    x.add_argument("-c", "--category", choices=suggestions.CATEGORIES, default="other")
    x.add_argument("--author")
    g.add_parser("list").add_argument("--category", choices=suggestions.CATEGORIES)
    x = g.add_parser("vote")
    x.add_argument("id")
    x.add_argument("--down", action="store_true")
    x = g.add_parser("status")
    x.add_argument("id")
    x.add_argument("status", choices=suggestions.STATUSES)
    g.add_parser("github", help="print a pre-filled GitHub issue link").add_argument("id")
    g.add_parser("delete").add_argument("id")
    sub.choices["suggest"].set_defaults(fn=cmd_suggest)

    cf = sub.add_parser("config", help="settings (author name, registries...)").add_subparsers(dest="action", required=True)
    cf.add_parser("show")
    x = cf.add_parser("set")
    x.add_argument("key")
    x.add_argument("value")
    cf.add_parser("add-registry").add_argument("value")
    sub.choices["config"].set_defaults(fn=cmd_config)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "fn", None):
        parser.print_help()
        print()
        print(c("Tip: ", "33;1") + tips.random_tip("start"))
        return 0
    try:
        args.fn(args)
    except (KeyError, ValueError, FileNotFoundError, FileExistsError, RuntimeError, OSError) as exc:
        msg = exc.args[0] if isinstance(exc, KeyError) and exc.args else exc
        print(c(f"error: {msg}", "31;1"), file=sys.stderr)
        return 1
    return 0
