"""The Hyper OS Creator web app: a JSON API plus the single page UI in web/.

Only standard library modules are used. By default the server listens on
127.0.0.1. When it listens on other interfaces (``--host 0.0.0.0``) other
computers can use it as a shared *registry* (browse/publish resources) and
suggestion box, but everything that changes your workspace stays limited to
this computer.
"""
from __future__ import annotations

import base64
import contextlib
import io
import ipaddress
import json
import mimetypes
import os
import pathlib
import re
import shlex
import threading
import traceback
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import (__version__, bootloaders, cli, config, downloads, isos, jobs, kernels, resources, suggestions, system,
               templates, tips, toolchain)

WEB = pathlib.Path(__file__).parent / "web"
MAX_BODY = 64 * 1024 * 1024
MAX_PACKAGE = 10 * 1024 * 1024
_console_lock = threading.Lock()

Route = Tuple[str, "re.Pattern[str]", Callable[..., Any], bool]
ROUTES: List[Route] = []


def route(method: str, pattern: str, public: bool = False):
    """Register a handler. ``public`` routes may be used by other computers."""
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn, public))
        return fn
    return deco


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _need(body: Dict[str, Any], *keys: str) -> List[Any]:
    missing = [k for k in keys if body.get(k) in (None, "")]
    if missing:
        raise ApiError(400, f"missing field(s): {', '.join(missing)}")
    return [body[k] for k in keys]


def _workspace_file(path: str) -> pathlib.Path:
    p = pathlib.Path(path)
    p = p if p.is_absolute() else config.home() / p
    p = p.resolve()
    if config.home().resolve() not in p.parents:
        raise ApiError(403, "only files inside the workspace can be accessed")
    return p


def _job(title: str, fn) -> Dict[str, Any]:
    def runner(job: jobs.Job):
        return fn(job.progress, lambda: job.cancelled)
    return jobs.start(title, runner).to_dict()


# ---------------------------------------------------------------------------
# general
# ---------------------------------------------------------------------------

@route("GET", "/api/status")
def api_status(q, b):
    return {"version": __version__, "workspace": str(config.home()), "tools": toolchain.status(),
            "tip": tips.random_tip(), "systems": len(system.list_systems()),
            "downloads": len(downloads.list_downloads()), "resources": len(resources.installed())}


@route("GET", "/api/tips")
def api_tips(q, b):
    return {"topics": tips.TOPICS, "tips": tips.all_tips(q.get("topic") or None)}


@route("GET", "/api/settings")
def api_settings(q, b):
    return config.load_settings()


@route("PUT", "/api/settings")
def api_settings_put(q, b):
    s = config.load_settings()
    for key in ("author", "registries", "show_tips", "suggestions_repo"):
        if key in b:
            s[key] = b[key]
    config.save_settings(s)
    return s


@route("GET", "/api/jobs")
def api_jobs(q, b):
    return jobs.all_jobs()


@route("GET", r"/api/jobs/(\w+)")
def api_job(q, b, jid):
    job = jobs.get(jid)
    if not job:
        raise ApiError(404, "no such job")
    return job.to_dict()


@route("POST", r"/api/jobs/(\w+)/cancel")
def api_job_cancel(q, b, jid):
    job = jobs.get(jid)
    if job:
        job.cancelled = True
    return {"ok": True}


@route("GET", "/api/downloads")
def api_downloads(q, b):
    return downloads.list_downloads(q.get("kind") or None)


@route("POST", "/api/console")
def api_console(q, b):
    line = (b.get("line") or "").strip()
    args = shlex.split(line)
    if args and args[0] == "hyperos":
        args = args[1:]
    if args and args[0] in ("serve", "shell"):
        return {"output": f"'{args[0]}' can only be used in a real terminal.", "code": 1}
    if len(args) >= 2 and args[:2] in (["system", "run"], ["kernel", "run"]):
        return {"output": "Use the Run button (or a real terminal) to start QEMU.", "code": 1}
    out = io.StringIO()
    with _console_lock, contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            code = cli.main(args or ["--help"])
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return {"output": re.sub(r"\x1b\[[0-9;]*m", "", out.getvalue()), "code": code}


# ---------------------------------------------------------------------------
# systems
# ---------------------------------------------------------------------------

@route("GET", "/api/systems")
def api_systems(q, b):
    return system.list_systems()


@route("POST", "/api/systems")
def api_system_new(q, b):
    (name,) = _need(b, "name")
    if b.get("resource"):
        slug = resources.new_system_from(b["resource"], name)
    else:
        slug = system.create(name)
    return {"slug": slug}


@route("GET", r"/api/systems/([\w-]+)")
def api_system_get(q, b, slug):
    return {"slug": slug, "system": system.load(slug), "colors": system.COLORS, "box_styles": list(system.BOX_STYLES)}


@route("PUT", r"/api/systems/([\w-]+)")
def api_system_put(q, b, slug):
    data = b.get("system")
    if not isinstance(data, dict) or not data.get("name"):
        raise ApiError(400, "invalid system")
    system.save(slug, data)
    return {"ok": True}


@route("DELETE", r"/api/systems/([\w-]+)")
def api_system_delete(q, b, slug):
    system.delete(slug)
    return {"ok": True}


@route("POST", r"/api/systems/([\w-]+)/build")
def api_system_build(q, b, slug):
    try:
        return system.build(slug)
    except system.BuildError as exc:
        return {"ok": False, "log": f"{exc}\n{exc.log}", "errors": exc.errors}


@route("POST", r"/api/systems/([\w-]+)/run")
def api_system_run(q, b, slug):
    base = system.system_path(slug) / "build"
    floppy = bool(b.get("floppy"))
    image = base / (f"{slug}.img" if floppy else f"{slug}.iso")
    if not image.exists():
        system.build(slug)
    try:
        toolchain.run_qemu(str(image), iso=not floppy)
    except RuntimeError as exc:
        raise ApiError(400, str(exc))
    return {"ok": True}


@route("GET", r"/api/systems/([\w-]+)/files")
def api_system_files(q, b, slug):
    src = system.system_path(slug) / "src"
    return [{"name": str(p.relative_to(src)).replace(os.sep, "/"), "size": p.stat().st_size}
            for p in sorted(src.rglob("*")) if p.is_file()]


@route("GET", r"/api/systems/([\w-]+)/file")
def api_system_file(q, b, slug):
    p = config.safe_join(system.system_path(slug) / "src", q.get("name", ""))
    return {"name": q.get("name"), "content": p.read_text(errors="replace")}


@route("PUT", r"/api/systems/([\w-]+)/file")
def api_system_file_put(q, b, slug):
    name, content = b.get("name", ""), b.get("content", "")
    if not name:
        raise ApiError(400, "missing name")
    p = config.safe_join(system.system_path(slug) / "src", name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return {"ok": True}


@route("DELETE", r"/api/systems/([\w-]+)/file")
def api_system_file_delete(q, b, slug):
    p = config.safe_join(system.system_path(slug) / "src", q.get("name", ""))
    p.unlink()
    return {"ok": True}


@route("POST", r"/api/systems/([\w-]+)/template")
def api_system_template(q, b, slug):
    kind, tid = _need(b, "kind", "id")
    return templates.use_in_system(kind, tid, slug)


@route("GET", r"/api/systems/([\w-]+)/preview")
def api_system_preview(q, b, slug):
    return {"screen": [[[ch, a] for ch, a in row] for row in system.render_desktop(system.load(slug))]}


# ---------------------------------------------------------------------------
# code: templates + assembler
# ---------------------------------------------------------------------------

@route("GET", r"/api/templates/(bootloaders|kernels)")
def api_templates(q, b, kind):
    return templates.list_templates(kind)


@route("GET", r"/api/templates/(bootloaders|kernels)/([\w-]+)")
def api_template(q, b, kind, tid):
    return templates.read_template(kind, tid)


@route("POST", "/api/assemble")
def api_assemble(q, b):
    res = toolchain.assemble(b.get("source", ""))
    out = {"ok": res.ok, "log": res.log, "errors": res.errors, "size": len(res.output)}
    if res.ok:
        out["hex"] = res.output[:1024].hex()
        out["boot_signature"] = res.output[510:512] == b"\x55\xaa"
    return out


# ---------------------------------------------------------------------------
# bootloaders
# ---------------------------------------------------------------------------

@route("GET", "/api/bootloaders")
def api_bootloaders(q, b):
    return {"catalog": bootloaders.catalog(), "downloaded": downloads.list_downloads("bootloader"),
            "custom": bootloaders.list_custom(), "templates": templates.list_templates("bootloaders")}


@route("POST", "/api/bootloaders/download")
def api_bootloader_download(q, b):
    if b.get("url"):
        return _job(f"Download {b['url']}", lambda p, c: bootloaders.download_url(b["url"], b.get("name"), p, c))
    (bid,) = _need(b, "id")
    return _job(f"Download bootloader {bid}", lambda p, c: bootloaders.download(bid, p, c))


@route("POST", "/api/bootloaders/build")
def api_bootloader_build(q, b):
    source, name = _need(b, "source", "name")
    return bootloaders.build_from_code(source, name)


@route("POST", "/api/bootloaders/hyperboot")
def api_bootloader_hyperboot(q, b):
    return bootloaders.build_hyperboot(b.get("banner", "HyperBoot"), int(b.get("fg", 15)), int(b.get("bg", 1)),
                                       bool(b.get("wait_key")), b.get("name") or "hyperboot")


@route("POST", "/api/bootloaders/splash")
def api_bootloader_splash(q, b):
    try:
        return bootloaders.build_splash(b.get("lines", []), int(b.get("fg", 15)), int(b.get("bg", 1)),
                                        b.get("name") or "splash")
    except ValueError as exc:
        raise ApiError(400, str(exc))


# ---------------------------------------------------------------------------
# kernels
# ---------------------------------------------------------------------------

@route("GET", "/api/kernels")
def api_kernels(q, b):
    return {"prebuilt": kernels.PREBUILT, "downloaded": downloads.list_downloads("kernel"),
            "templates": templates.list_templates("kernels"),
            "features": {k: v["label"] for k, v in kernels.LINUX_FEATURES.items()}}


@route("GET", "/api/kernels/releases")
def api_kernel_releases(q, b):
    try:
        return kernels.releases()
    except Exception as exc:  # noqa: BLE001
        raise ApiError(502, f"could not reach kernel.org: {exc}")


@route("POST", "/api/kernels/download")
def api_kernel_download(q, b):
    if b.get("url"):
        return _job(f"Download {b['url']}", lambda p, c: kernels.download_url(b["url"], p, c))
    if b.get("prebuilt"):
        return _job(f"Download {b['prebuilt']} kernel", lambda p, c: kernels.download_prebuilt(b["prebuilt"], p, c))
    (version,) = _need(b, "version")
    return _job(f"Download Linux {version}", lambda p, c: kernels.download_source(version, p, c))


@route("POST", "/api/kernels/config")
def api_kernel_config(q, b):
    return {"config": kernels.config_fragment(b.get("features", []), b.get("extra", ""))}


@route("POST", "/api/kernels/build-linux")
def api_kernel_build_linux(q, b):
    (tarball,) = _need(b, "tarball")
    path = str(_workspace_file(tarball))

    def run(job: jobs.Job):
        lines: List[str] = []

        def log(line: str) -> None:
            lines.append(line)
            job.message = "\n".join(lines[-40:])
        return kernels.build_linux(path, b.get("features", []), b.get("extra", ""), b.get("base", "tinyconfig"),
                                   log=log)
    return jobs.start("Build Linux kernel", run).to_dict()


# ---------------------------------------------------------------------------
# ISOs
# ---------------------------------------------------------------------------

@route("GET", "/api/isos")
def api_isos(q, b):
    return {"catalog": isos.catalog(), "local": isos.local_isos(), "projects": isos.Project.list_projects(),
            "xorriso": bool(toolchain.which("xorriso"))}


@route("POST", "/api/isos/download")
def api_iso_download(q, b):
    if b.get("url"):
        return _job(f"Download {b['url']}", lambda p, c: isos.download_url(b["url"], b.get("sha256"), p, c))
    (iid,) = _need(b, "id")
    return _job(f"Download ISO {iid}", lambda p, c: isos.download(iid, p, c))


@route("POST", "/api/isos/inspect")
def api_iso_inspect(q, b):
    (path,) = _need(b, "path")
    return isos.inspect(str(_workspace_file(path)))


@route("POST", "/api/isos/read")
def api_iso_read(q, b):
    path, inner = _need(b, "path", "inner")
    data = isos.read_file(str(_workspace_file(path)), inner, 256 * 1024)
    try:
        return {"text": data.decode("utf-8"), "binary": False}
    except UnicodeDecodeError:
        return {"text": data[:4096].hex(), "binary": True}


@route("POST", "/api/isos/projects")
def api_iso_project_new(q, b):
    name, source = _need(b, "name", "source")
    p = isos.Project.create(name, str(_workspace_file(source)))
    return {"name": p.name}


@route("GET", r"/api/isos/projects/([\w-]+)")
def api_iso_project(q, b, name):
    p = isos.Project(name)
    plan = p.plan()
    return {"name": p.name, **plan, "changes": p.changes(), "source_info": isos.inspect(plan["source"])}


@route("POST", r"/api/isos/projects/([\w-]+)/file")
def api_iso_project_file(q, b, name):
    (path,) = _need(b, "path")
    data = base64.b64decode(b["data"]) if b.get("data") is not None else (b.get("text") or "").encode()
    isos.Project(name).add_file(path, data)
    return {"ok": True}


@route("POST", r"/api/isos/projects/([\w-]+)/remove")
def api_iso_project_remove(q, b, name):
    (path,) = _need(b, "path")
    isos.Project(name).remove(path)
    return {"ok": True}


@route("POST", r"/api/isos/projects/([\w-]+)/settings")
def api_iso_project_settings(q, b, name):
    p = isos.Project(name)
    plan = p.plan()
    if b.get("volume_id"):
        plan["volume_id"] = re.sub(r"[^A-Z0-9_]", "_", b["volume_id"].upper())[:32]
    p.save(plan)
    return plan


@route("POST", r"/api/isos/projects/([\w-]+)/build")
def api_iso_project_build(q, b, name):
    def run(job: jobs.Job):
        lines: List[str] = []

        def log(line: str) -> None:
            lines.append(line)
            job.message = "\n".join(lines[-40:])
        return isos.Project(name).build(use_xorriso=False if b.get("python") else None, log=log)
    return jobs.start(f"Build modified ISO {name}", run).to_dict()


# ---------------------------------------------------------------------------
# resources + registry
# ---------------------------------------------------------------------------

@route("GET", "/api/resources")
def api_resources(q, b):
    return {"installed": resources.installed(), "types": resources.TYPES,
            "registries": config.load_settings().get("registries", [])}


@route("GET", "/api/resources/search")
def api_resources_search(q, b):
    return resources.search(q.get("q", ""), q.get("type", ""))


@route("POST", "/api/resources/get")
def api_resources_get(q, b):
    (rid,) = _need(b, "id")
    return resources.get(rid, b.get("registry") or "local")


@route("POST", "/api/resources/apply")
def api_resources_apply(q, b):
    rid, slug = _need(b, "id", "slug")
    return resources.apply(rid, slug)


@route("POST", "/api/resources/new-system")
def api_resources_new_system(q, b):
    rid, name = _need(b, "id", "name")
    return {"slug": resources.new_system_from(rid, name)}


@route("DELETE", r"/api/resources/installed/([\w-]+)")
def api_resources_uninstall(q, b, rid):
    resources.uninstall(rid)
    return {"ok": True}


@route("POST", "/api/resources/publish")
def api_resources_publish(q, b):
    """Create a package (from a system, code or an uploaded file) and publish it."""
    meta = {"name": b.get("name", ""), "description": b.get("description", ""), "version": b.get("version") or "1.0.0",
            "tags": [t.strip() for t in (b.get("tags") or "").split(",") if t.strip()]}
    if b.get("author"):
        meta["author"] = b["author"]
    rtype = b.get("type", "")
    if b.get("package"):
        data = base64.b64decode(b["package"])
    elif b.get("slug"):
        data = resources.from_system(b["slug"], rtype, meta)
    elif b.get("files"):
        files = {f["name"]: base64.b64decode(f["data"]) if f.get("base64") else f["data"].encode()
                 for f in b["files"]}
        data = resources.make_package({**meta, "type": rtype}, files)
    else:
        raise ApiError(400, "nothing to publish")
    target = b.get("target", "local")
    if target == "local":
        res = resources.publish_local(data)
    elif target == "remote":
        res = resources.publish_remote(data, b.get("registry") or config.load_settings()["registries"][0])
    else:
        res = {"ok": True}
    if b.get("install", True):
        resources.install(data)
    return {**res, "package": base64.b64encode(data).decode() if target == "file" else None}


@route("GET", r"/registry/index\.json", public=True)
def registry_index(q, b):
    return resources.registry_index(resources.local_registry_dir())


@route("POST", "/api/registry/publish", public=True)
def registry_publish(q, b):
    (pkg,) = _need(b, "package")
    data = base64.b64decode(pkg)
    if len(data) > MAX_PACKAGE:
        raise ApiError(413, "package too large (max 10 MB)")
    return resources.publish_local(data)


# ---------------------------------------------------------------------------
# suggestions (public so a shared server works as a suggestion box)
# ---------------------------------------------------------------------------

@route("GET", "/api/suggestions", public=True)
def api_suggestions(q, b):
    return {"items": suggestions.list_suggestions(q.get("sort", "votes"), q.get("category", "")),
            "categories": suggestions.CATEGORIES, "statuses": suggestions.STATUSES}


@route("POST", "/api/suggestions", public=True)
def api_suggestion_add(q, b):
    return suggestions.add(b.get("title", ""), b.get("description", ""), b.get("category", "other"),
                           b.get("author", ""))


@route("POST", r"/api/suggestions/(\w+)/vote", public=True)
def api_suggestion_vote(q, b, sid):
    return suggestions.vote(sid, int(b.get("delta", 1)))


@route("POST", r"/api/suggestions/(\w+)/status")
def api_suggestion_status(q, b, sid):
    return suggestions.set_status(sid, b.get("status", ""))


@route("DELETE", r"/api/suggestions/(\w+)")
def api_suggestion_delete(q, b, sid):
    suggestions.delete(sid)
    return {"ok": True}


@route("GET", r"/api/suggestions/(\w+)/github", public=True)
def api_suggestion_github(q, b, sid):
    return {"url": suggestions.issue_url(sid)}


# ---------------------------------------------------------------------------
# HTTP plumbing
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = f"HyperOSCreator/{__version__}"

    def log_message(self, fmt, *args):  # quieter console
        if os.environ.get("HYPEROS_DEBUG"):
            super().log_message(fmt, *args)

    def _is_local(self) -> bool:
        try:
            return ipaddress.ip_address(self.client_address[0]).is_loopback
        except ValueError:
            return False

    def _send(self, status: int, body: bytes, ctype: str, extra: Optional[Dict[str, str]] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, data: Any) -> None:
        self._send(status, json.dumps(data, default=str).encode(), "application/json")

    def _handle(self, method: str) -> None:
        url = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(url.path)
        query = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query).items()}
        local = self._is_local()
        try:
            if method in ("POST", "PUT", "DELETE") and local:
                # basic CSRF protection: browsers send Origin on cross-site requests
                origin = self.headers.get("Origin")
                if origin and urllib.parse.urlsplit(origin).netloc != self.headers.get("Host"):
                    raise ApiError(403, "cross-origin request refused")
            for m, pattern, fn, public in ROUTES:
                match = pattern.match(path)
                if m == method and match:
                    if not local and not public:
                        raise ApiError(403, "this action is only available on the computer running Hyper OS Creator")
                    body: Dict[str, Any] = {}
                    if method in ("POST", "PUT"):
                        length = int(self.headers.get("Content-Length") or 0)
                        if length > MAX_BODY:
                            raise ApiError(413, "request too large")
                        raw = self.rfile.read(length) if length else b""
                        body = json.loads(raw or b"{}")
                    self._json(200, fn(query, body, *match.groups()))
                    return
            if method == "GET":
                self._static(path, query, local)
                return
            raise ApiError(404, "not found")
        except ApiError as exc:
            self._json(exc.status, {"error": str(exc)})
        except (KeyError, FileNotFoundError) as exc:
            self._json(404, {"error": str(exc.args[0] if exc.args else exc)})
        except (ValueError, FileExistsError, RuntimeError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

    def _static(self, path: str, query: Dict[str, str], local: bool) -> None:
        if path.startswith("/registry/packages/"):
            f = config.safe_join(resources.local_registry_dir() / "packages", path.rsplit("/", 1)[1])
            if f.is_file():
                self._send(200, f.read_bytes(), "application/zip")
                return
            raise ApiError(404, "no such package")
        if path == "/api/file":
            if not local:
                raise ApiError(403, "local only")
            f = _workspace_file(query.get("path", ""))
            if not f.is_file():
                raise ApiError(404, "no such file")
            self._send_file(f)
            return
        if not local and path not in ("/", "/index.html") and not path.startswith("/static/"):
            raise ApiError(403, "local only")
        rel = "index.html" if path in ("/", "/index.html") else path.removeprefix("/static/")
        f = config.safe_join(WEB, rel)
        if not f.is_file():
            raise ApiError(404, "not found")
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(200, f.read_bytes(), ctype)

    def _send_file(self, f: pathlib.Path) -> None:
        size = f.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Disposition", f'attachment; filename="{f.name}"')
        self.end_headers()
        with open(f, "rb") as fh:
            while chunk := fh.read(1 << 20):
                self.wfile.write(chunk)

    def do_GET(self):  # noqa: N802
        self._handle("GET")

    def do_HEAD(self):  # noqa: N802
        self._handle("GET")

    def do_POST(self):  # noqa: N802
        self._handle("POST")

    def do_PUT(self):  # noqa: N802
        self._handle("PUT")

    def do_DELETE(self):  # noqa: N802
        self._handle("DELETE")


def make_server(host: str = "127.0.0.1", port: int = 8642) -> ThreadingHTTPServer:
    config.home()
    return ThreadingHTTPServer((host, port), Handler)


def serve(host: str = "127.0.0.1", port: int = 8642, open_browser: bool = True) -> None:
    httpd = make_server(host, port)
    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0', '::') else host}:{port}/"
    print(f"Hyper OS Creator {__version__} is running at {url}")
    print(f"Workspace: {config.home()}")
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(f"Sharing mode: other computers can browse/publish resources at http://<this-computer>:{port}/registry "
              "and use the suggestion box.")
    print("Press Ctrl+C to stop.")
    print("Tip: " + tips.random_tip())
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nBye!")
    finally:
        httpd.server_close()
