"""Disk image and ISO 9660 tools written in pure Python (no dependencies).

* ``make_floppy``  - build a 1.44 MB floppy image from a boot sector + payload.
* ``IsoWriter``    - write ISO 9660 images with Rock Ridge names and
                     El Torito boot entries (BIOS floppy emulation,
                     BIOS no-emulation with boot info table, and UEFI).
* ``IsoReader``    - read ISO 9660 images (Rock Ridge / Joliet aware):
                     list files, extract them and inspect boot records.
"""
from __future__ import annotations

import datetime as _dt
import os
import struct
from dataclasses import dataclass, field
from typing import BinaryIO, Dict, Iterable, Iterator, List, Optional, Tuple, Union

SECTOR = 2048
FLOPPY_SIZE = 1474560  # 1.44 MB
FLOPPY_SECTORS = FLOPPY_SIZE // 512


# ---------------------------------------------------------------------------
# Floppy images
# ---------------------------------------------------------------------------

def make_floppy(boot_sector: bytes, payload: bytes = b"") -> bytes:
    """Return a 1.44 MB floppy image: boot sector in sector 0, payload after."""
    if len(boot_sector) != 512:
        raise ValueError("boot sector must be exactly 512 bytes")
    if boot_sector[510:512] != b"\x55\xaa":
        raise ValueError("boot sector is missing the 0x55AA signature")
    if 512 + len(payload) > FLOPPY_SIZE:
        raise ValueError("payload does not fit on a 1.44 MB floppy")
    img = bytearray(FLOPPY_SIZE)
    img[0:512] = boot_sector
    img[512:512 + len(payload)] = payload
    return bytes(img)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _both16(v: int) -> bytes:
    return struct.pack("<H", v) + struct.pack(">H", v)


def _both32(v: int) -> bytes:
    return struct.pack("<I", v) + struct.pack(">I", v)


def _pad(text: str, size: int, fill: bytes = b" ") -> bytes:
    raw = text.encode("ascii", "replace")[:size]
    return raw + fill * (size - len(raw))


def _dir_date(when: _dt.datetime) -> bytes:
    return bytes([when.year - 1900, when.month, when.day, when.hour, when.minute, when.second, 0])


def _vd_date(when: Optional[_dt.datetime]) -> bytes:
    if when is None:
        return b"0" * 16 + b"\x00"
    return when.strftime("%Y%m%d%H%M%S").encode() + b"00\x00"


def _sectors(n: int) -> int:
    return (n + SECTOR - 1) // SECTOR


_DCHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


def _iso_name(name: str, is_dir: bool, used: set) -> str:
    """Map a real file name to a unique, relaxed ISO 9660 identifier."""
    up = name.upper()
    if is_dir:
        base, ext = up, ""
    else:
        base, _, ext = up.rpartition(".") if "." in up else (up, "", "")
    clean = lambda s: "".join(c if c in _DCHARS else "_" for c in s)  # noqa: E731
    base, ext = clean(base) or "_", clean(ext)[:8]
    limit = 31 if is_dir else 30 - len(ext)
    candidate = base[:limit]
    counter = 1
    while True:
        full = candidate if is_dir else f"{candidate}.{ext}"
        if full not in used:
            used.add(full)
            return full if is_dir else full + ";1"
        suffix = f"_{counter}"
        candidate = base[: limit - len(suffix)] + suffix
        counter += 1


_ER_ID = b"RRIP_1991A"
_ER_DES = b"THE ROCK RIDGE INTERCHANGE PROTOCOL PROVIDES SUPPORT FOR POSIX FILE SYSTEM SEMANTICS"
_ER_SRC = (b"PLEASE CONTACT DISC PUBLISHER FOR SPECIFICATION SOURCE.  SEE PUBLISHER IDENTIFIER IN PRIMARY "
           b"VOLUME DESCRIPTOR FOR CONTACT INFORMATION.")
_RRIP_ER = (b"ER" + bytes([8 + len(_ER_ID) + len(_ER_DES) + len(_ER_SRC), 1, len(_ER_ID), len(_ER_DES),
                          len(_ER_SRC), 1]) + _ER_ID + _ER_DES + _ER_SRC)

# A file source is bytes, a path on disk, or (path, offset, size) inside a
# larger file (used to copy files straight out of another ISO).
Source = Union[bytes, str, Tuple[str, int, int]]


def _source_size(src: Source) -> int:
    if isinstance(src, (bytes, bytearray)):
        return len(src)
    if isinstance(src, tuple):
        return src[2]
    return os.path.getsize(src)


def _iter_source(src: Source, chunk: int = 1 << 20) -> Iterator[bytes]:
    if isinstance(src, (bytes, bytearray)):
        yield bytes(src)
        return
    path, offset, size = (src if isinstance(src, tuple) else (src, 0, os.path.getsize(src)))
    with open(path, "rb") as fh:
        fh.seek(offset)
        left = size
        while left > 0:
            data = fh.read(min(chunk, left))
            if not data:
                raise IOError(f"unexpected end of file while reading {path}")
            left -= len(data)
            yield data


def _read_source(src: Source) -> bytes:
    return b"".join(_iter_source(src))


# ---------------------------------------------------------------------------
# ISO writer
# ---------------------------------------------------------------------------

@dataclass
class _Node:
    name: str
    is_dir: bool
    parent: Optional["_Node"] = None
    source: Optional[Source] = None
    mode: Optional[int] = None
    children: Dict[str, "_Node"] = field(default_factory=dict)
    iso_name: str = ""
    lba: int = 0
    size: int = 0
    dir_num: int = 0

    def path(self) -> str:
        parts = []
        node = self
        while node.parent is not None:
            parts.append(node.name)
            node = node.parent
        return "/" + "/".join(reversed(parts))


@dataclass
class BootEntry:
    """An El Torito boot entry.

    emulation: "floppy" (1.44 MB floppy image), "none" (no emulation, BIOS)
    or "efi" (UEFI El Torito image, e.g. an efiboot.img FAT image).
    """
    path: str
    emulation: str = "floppy"
    load_sectors: int = 4
    boot_info_table: bool = False


class IsoWriter:
    def __init__(self, volume_id: str = "HYPEROS", publisher: str = "", application: str = "HYPER OS CREATOR",
                 rock_ridge: bool = True):
        self.volume_id = volume_id.upper()[:32]
        self.publisher = publisher
        self.application = application
        self.rock_ridge = rock_ridge
        self.root = _Node("", True)
        self.boot: List[BootEntry] = []
        self.system_area: bytes = b""
        self.when = _dt.datetime.now().replace(microsecond=0)
        self._ce_lba = 0

    # -- building the tree --------------------------------------------------
    def _node_for(self, path: str, create_dirs: bool = True) -> _Node:
        node = self.root
        for part in [p for p in path.strip("/").split("/") if p]:
            child = node.children.get(part)
            if child is None:
                if not create_dirs:
                    raise KeyError(path)
                child = _Node(part, True, parent=node)
                node.children[part] = child
            node = child
        return node

    def add_dir(self, path: str, mode: Optional[int] = None) -> None:
        node = self._node_for(path)
        if mode is not None:
            node.mode = mode

    def add_file(self, path: str, source: Source, mode: Optional[int] = None) -> None:
        parts = [p for p in path.strip("/").split("/") if p]
        if not parts:
            raise ValueError("empty file path")
        parent = self._node_for("/".join(parts[:-1]))
        parent.children[parts[-1]] = _Node(parts[-1], False, parent=parent, source=source, mode=mode)

    def add_tree(self, local_dir: str, iso_dir: str = "/") -> None:
        for dirpath, dirnames, filenames in os.walk(local_dir):
            rel = os.path.relpath(dirpath, local_dir)
            base = iso_dir.rstrip("/") + ("" if rel == "." else "/" + rel.replace(os.sep, "/"))
            self.add_dir(base or "/")
            for fn in filenames:
                self.add_file(f"{base}/{fn}", os.path.join(dirpath, fn))

    def remove(self, path: str) -> None:
        parts = [p for p in path.strip("/").split("/") if p]
        parent = self._node_for("/".join(parts[:-1]), create_dirs=False)
        parent.children.pop(parts[-1], None)

    def add_boot(self, entry: BootEntry) -> None:
        self.boot.append(entry)

    # -- layout ---------------------------------------------------------------
    def _dirs_bfs(self) -> List[_Node]:
        out, queue = [], [self.root]
        while queue:
            node = queue.pop(0)
            out.append(node)
            queue.extend(sorted((c for c in node.children.values() if c.is_dir), key=lambda n: n.iso_name))
        return out

    def _assign_names(self, node: _Node) -> None:
        used: set = set()
        for child in sorted(node.children.values(), key=lambda n: n.name):
            child.iso_name = _iso_name(child.name, child.is_dir, used)
            if child.is_dir:
                self._assign_names(child)

    def _susp(self, node: _Node, kind: str) -> bytes:
        if not self.rock_ridge:
            return b""
        out = b""
        if node is self.root and kind == ".":
            out += b"SP\x07\x01\xbe\xef\x00"
            out += b"CE\x1c\x01" + _both32(self._ce_lba) + _both32(0) + _both32(len(_RRIP_ER))
        mode = node.mode if node.mode is not None else (0o40555 if node.is_dir else 0o100444)
        if node.is_dir and not mode & 0o40000:
            mode |= 0o40000
        links = 2 if node.is_dir else 1
        out += b"PX\x24\x01" + _both32(mode) + _both32(links) + _both32(0) + _both32(0)
        if kind == "name":
            raw = node.name.encode("utf-8")
            room = 255 - 33 - len(node.iso_name.encode()) - 1 - len(out) - 5
            out += b"NM" + bytes([5 + min(len(raw), room), 1, 0]) + raw[:room]
        return out

    def _record(self, node: _Node, ident: bytes, kind: str) -> bytes:
        su = self._susp(node, kind)
        size = node.size
        length = 33 + len(ident)
        pad = b"\x00" if len(ident) % 2 == 0 else b""
        length += len(pad) + len(su)
        if length % 2:
            su += b"\x00"
            length += 1
        flags = 0x02 if node.is_dir else 0x00
        return (bytes([length, 0]) + _both32(node.lba) + _both32(size) + _dir_date(self.when)
                + bytes([flags, 0, 0]) + _both16(1) + bytes([len(ident)]) + ident + pad + su)

    def _dir_records(self, node: _Node) -> List[bytes]:
        recs = [self._record(node, b"\x00", "."), self._record(node.parent or node, b"\x01", "..")]
        for child in sorted(node.children.values(), key=lambda n: n.iso_name):
            recs.append(self._record(child, child.iso_name.encode(), "name"))
        return recs

    @staticmethod
    def _pack_records(recs: List[bytes]) -> bytes:
        out = bytearray()
        for rec in recs:
            used = len(out) % SECTOR
            if used + len(rec) > SECTOR:
                out += b"\x00" * (SECTOR - used)
            out += rec
        if len(out) % SECTOR:
            out += b"\x00" * (SECTOR - len(out) % SECTOR)
        return bytes(out)

    def _path_table(self, dirs: List[_Node], big_endian: bool) -> bytes:
        out = bytearray()
        fmt = ">" if big_endian else "<"
        for d in dirs:
            ident = b"\x00" if d is self.root else d.iso_name.encode()
            parent_num = (d.parent or d).dir_num
            out += bytes([len(ident), 0]) + struct.pack(fmt + "IH", d.lba, parent_num) + ident
            if len(ident) % 2:
                out += b"\x00"
        return bytes(out)

    def _files(self) -> List[_Node]:
        out = []

        def walk(n: _Node) -> None:
            for c in sorted(n.children.values(), key=lambda x: x.iso_name):
                if c.is_dir:
                    walk(c)
                else:
                    out.append(c)
        walk(self.root)
        return out

    def _find(self, path: str) -> _Node:
        node = self.root
        for part in [p for p in path.strip("/").split("/") if p]:
            node = node.children[part]
        return node

    # -- writing --------------------------------------------------------------
    def write(self, out_path: str) -> int:
        """Write the image and return its size in bytes."""
        self._assign_names(self.root)
        dirs = self._dirs_bfs()
        for i, d in enumerate(dirs, 1):
            d.dir_num = i
        files = self._files()
        for f in files:
            f.size = _source_size(f.source)

        has_boot = bool(self.boot)
        lba = 16 + 1 + (1 if has_boot else 0) + 1
        # path tables need directory LBAs, but their own size does not depend on them
        pt_size = len(self._path_table(dirs, False))
        pt_l = lba
        lba += _sectors(pt_size)
        pt_m = lba
        lba += _sectors(pt_size)
        # directory sizes depend only on names, so compute them up front
        for d in dirs:
            d.size = len(self._pack_records(self._dir_records(d)))
        for d in dirs:
            d.lba = lba
            lba += d.size // SECTOR
        catalog_lba = 0
        if has_boot:
            catalog_lba = lba
            lba += 1
        if self.rock_ridge:
            self._ce_lba = lba
            lba += 1
        for f in files:
            f.lba = lba
            lba += max(1, _sectors(f.size)) if f.size else 0
            if not f.size:
                f.lba = 0
        total = lba

        boot_patches: Dict[int, bytes] = {}
        catalog = b""
        if has_boot:
            catalog, boot_patches = self._catalog()

        with open(out_path, "wb") as fh:
            sa = self.system_area[: 16 * SECTOR]
            fh.write(sa + b"\x00" * (16 * SECTOR - len(sa)))
            fh.write(self._pvd(total, pt_size, pt_l, pt_m, dirs[0]))
            if has_boot:
                fh.write(self._boot_record(catalog_lba))
            fh.write(b"\xffCD001\x01" + b"\x00" * (SECTOR - 7))
            for table in (self._path_table(dirs, False), self._path_table(dirs, True)):
                fh.write(table + b"\x00" * (_sectors(pt_size) * SECTOR - len(table)))
            for d in dirs:
                fh.write(self._pack_records(self._dir_records(d)))
            if has_boot:
                fh.write(catalog + b"\x00" * (SECTOR - len(catalog)))
            if self.rock_ridge:
                fh.write(_RRIP_ER + b"\x00" * (SECTOR - len(_RRIP_ER)))
            for f in files:
                if not f.size:
                    continue
                if id(f) in boot_patches:
                    fh.write(boot_patches[id(f)])
                else:
                    for chunk in _iter_source(f.source):
                        fh.write(chunk)
                rem = f.size % SECTOR
                if rem:
                    fh.write(b"\x00" * (SECTOR - rem))
            size = fh.tell()
        assert size == total * SECTOR, (size, total * SECTOR)
        return size

    def _pvd(self, total: int, pt_size: int, pt_l: int, pt_m: int, root: _Node) -> bytes:
        root_rec = (bytes([34, 0]) + _both32(root.lba) + _both32(root.size) + _dir_date(self.when)
                    + bytes([2, 0, 0]) + _both16(1) + b"\x01\x00")
        vd = bytearray(SECTOR)
        vd[0:8] = b"\x01CD001\x01\x00"
        vd[8:40] = _pad("LINUX", 32)
        vd[40:72] = _pad(self.volume_id, 32)
        vd[80:88] = _both32(total)
        vd[120:124] = _both16(1)
        vd[124:128] = _both16(1)
        vd[128:132] = _both16(SECTOR)
        vd[132:140] = _both32(pt_size)
        vd[140:144] = struct.pack("<I", pt_l)
        vd[148:152] = struct.pack(">I", pt_m)
        vd[156:190] = root_rec
        vd[190:318] = _pad("", 128)
        vd[318:446] = _pad(self.publisher, 128)
        vd[446:574] = _pad("", 128)
        vd[574:702] = _pad(self.application, 128)
        vd[702:813] = _pad("", 111)
        vd[813:830] = _vd_date(self.when)
        vd[830:847] = _vd_date(self.when)
        vd[847:864] = _vd_date(None)
        vd[864:881] = _vd_date(None)
        vd[881] = 1
        return bytes(vd)

    @staticmethod
    def _boot_record(catalog_lba: int) -> bytes:
        vd = bytearray(SECTOR)
        vd[0:7] = b"\x00CD001\x01"
        vd[7:39] = _pad("EL TORITO SPECIFICATION", 32, b"\x00")
        vd[71:75] = struct.pack("<I", catalog_lba)
        return bytes(vd)

    def _catalog(self) -> Tuple[bytes, Dict[int, bytes]]:
        patches: Dict[int, bytes] = {}
        bios = [b for b in self.boot if b.emulation != "efi"]
        efi = [b for b in self.boot if b.emulation == "efi"]
        first = bios[0] if bios else efi[0]

        def entry(b: BootEntry) -> bytes:
            node = self._find(b.path)
            if b.emulation == "floppy":
                if node.size != FLOPPY_SIZE:
                    raise ValueError(f"{b.path}: floppy emulation needs a 1.44 MB image")
                media, count = 2, 1
            else:
                media = 0
                count = b.load_sectors if b.emulation == "none" else min(0xFFFF, (node.size + 511) // 512)
            if b.boot_info_table:
                data = bytearray(_read_source(node.source))
                data[8:24] = struct.pack("<IIII", 16, node.lba, node.size, 0)
                csum = 0
                for i in range(64, len(data) - len(data) % 4, 4):
                    csum = (csum + struct.unpack_from("<I", data, i)[0]) & 0xFFFFFFFF
                data[20:24] = struct.pack("<I", csum)
                patches[id(node)] = bytes(data)
            return struct.pack("<BBHBBHI", 0x88, media, 0, 0, 0, count, node.lba) + b"\x00" * 20

        platform = 0xEF if first.emulation == "efi" else 0
        val = bytearray(struct.pack("<BBH", 1, platform, 0) + _pad("HYPER OS CREATOR", 24, b"\x00") + b"\x00\x00\x55\xaa")
        csum = (-sum(struct.unpack("<16H", bytes(val)))) & 0xFFFF
        val[28:30] = struct.pack("<H", csum)
        cat = bytes(val) + entry(first)
        rest = [b for b in self.boot if b is not first]
        for i, b in enumerate(rest):
            header = 0x91 if i == len(rest) - 1 else 0x90
            plat = 0xEF if b.emulation == "efi" else 0
            cat += struct.pack("<BBH", header, plat, 1) + b"\x00" * 28
            cat += entry(b)
        return cat, patches


# ---------------------------------------------------------------------------
# ISO reader
# ---------------------------------------------------------------------------

@dataclass
class IsoEntry:
    path: str
    is_dir: bool
    lba: int
    size: int
    mode: Optional[int] = None
    symlink: Optional[str] = None


@dataclass
class IsoBootInfo:
    platform: str
    emulation: str
    lba: int
    sectors: int
    file: Optional[str] = None
    boot_info_table: bool = False


class IsoReader:
    def __init__(self, path: str):
        self.path = path
        self.fh: BinaryIO = open(path, "rb")
        self.volume_id = ""
        self.catalog_lba: Optional[int] = None
        self.joliet_root: Optional[bytes] = None
        self.root: Optional[bytes] = None
        self.rock_ridge = False
        self._susp_skip = 0
        self._read_descriptors()
        self._entries: Optional[List[IsoEntry]] = None

    def close(self) -> None:
        self.fh.close()

    def __enter__(self) -> "IsoReader":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _sector(self, lba: int, count: int = 1) -> bytes:
        self.fh.seek(lba * SECTOR)
        return self.fh.read(count * SECTOR)

    def _read_descriptors(self) -> None:
        for lba in range(16, 64):
            vd = self._sector(lba)
            if len(vd) < SECTOR or vd[1:6] != b"CD001":
                raise ValueError(f"{self.path} is not an ISO 9660 image")
            kind = vd[0]
            if kind == 1:
                self.volume_id = vd[40:72].decode("ascii", "replace").strip()
                self.root = vd[156:190]
            elif kind == 0 and vd[7:30] == b"EL TORITO SPECIFICATION":
                self.catalog_lba = struct.unpack_from("<I", vd, 71)[0]
            elif kind == 2 and vd[88:91] in (b"%/@", b"%/C", b"%/E"):
                self.joliet_root = vd[156:190]
            elif kind == 255:
                break
        if self.root is None:
            raise ValueError("no primary volume descriptor found")
        # detect Rock Ridge from the SP entry of the root "." record
        root_lba = struct.unpack_from("<I", self.root, 2)[0]
        first = self._sector(root_lba)
        su = self._system_use(first[: first[0]])
        if su[:2] == b"SP" and su[4:6] == b"\xbe\xef":
            self.rock_ridge = True
            self._susp_skip = su[6]

    @staticmethod
    def _system_use(rec: bytes) -> bytes:
        name_len = rec[32]
        start = 33 + name_len + (1 if name_len % 2 == 0 else 0)
        return rec[start:rec[0]]

    def _rr(self, rec: bytes) -> Tuple[Optional[str], Optional[int], Optional[str]]:
        data = self._system_use(rec)[self._susp_skip:]
        name, mode, link = None, None, None
        guard = 0
        while data and guard < 32:
            guard += 1
            pos, cont = 0, None
            while pos + 4 <= len(data):
                sig, length = data[pos:pos + 2], data[pos + 2]
                if length < 4:
                    break
                body = data[pos + 4:pos + length]
                if sig == b"NM" and body:
                    name = (name or "") + body[1:].decode("utf-8", "replace")
                elif sig == b"PX" and len(body) >= 8:
                    mode = struct.unpack_from("<I", body, 0)[0]
                elif sig == b"SL" and body:
                    parts, p = [], 1
                    while p + 2 <= len(body):
                        flags, clen = body[p], body[p + 1]
                        comp = body[p + 2:p + 2 + clen].decode("utf-8", "replace")
                        parts.append("." if flags & 2 else ".." if flags & 4 else "" if flags & 8 else comp)
                        p += 2 + clen
                    link = (link + "/" if link else "") + "/".join(parts)
                elif sig == b"CE" and len(body) >= 24:
                    cont = struct.unpack_from("<I", body, 0)[0], struct.unpack_from("<I", body, 8)[0], \
                        struct.unpack_from("<I", body, 16)[0]
                elif sig == b"ST":
                    break
                pos += length
            if not cont:
                break
            blk, off, ln = cont
            self.fh.seek(blk * SECTOR + off)
            data = self.fh.read(ln)
        return name, mode, link

    def _walk(self, root: bytes, joliet: bool) -> List[IsoEntry]:
        out: List[IsoEntry] = []
        seen = set()

        def walk(lba: int, size: int, prefix: str) -> None:
            if lba in seen:
                return
            seen.add(lba)
            data = self._sector(lba, _sectors(size))[:size]
            pos = 0
            while pos < len(data):
                length = data[pos]
                if length == 0:
                    pos = (pos // SECTOR + 1) * SECTOR
                    continue
                rec = data[pos:pos + length]
                pos += length
                ident = rec[33:33 + rec[32]]
                if ident in (b"\x00", b"\x01"):
                    continue
                ext_lba = struct.unpack_from("<I", rec, 2)[0]
                ext_size = struct.unpack_from("<I", rec, 10)[0]
                is_dir = bool(rec[25] & 2)
                mode = link = None
                if joliet:
                    name = ident.decode("utf-16-be", "replace")
                else:
                    name = ident.decode("ascii", "replace")
                    if self.rock_ridge:
                        rr_name, mode, link = self._rr(rec)
                        name = rr_name or name
                if not is_dir and ";" in name:
                    name = name.split(";")[0]
                if not is_dir and name.endswith(".") and not self.rock_ridge:
                    name = name[:-1]
                path = f"{prefix}/{name}"
                out.append(IsoEntry(path, is_dir, ext_lba, ext_size, mode, link))
                if is_dir:
                    walk(ext_lba, ext_size, path)

        walk(struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0], "")
        return out

    def entries(self) -> List[IsoEntry]:
        if self._entries is None:
            if not self.rock_ridge and self.joliet_root is not None:
                self._entries = self._walk(self.joliet_root, True)
            else:
                self._entries = self._walk(self.root, False)
        return self._entries

    def find(self, path: str) -> Optional[IsoEntry]:
        want = "/" + path.strip("/")
        for e in self.entries():
            if e.path == want or e.path.lower() == want.lower():
                return e
        return None

    def read_file(self, path: str) -> bytes:
        e = self.find(path)
        if e is None or e.is_dir:
            raise FileNotFoundError(path)
        self.fh.seek(e.lba * SECTOR)
        return self.fh.read(e.size)

    def extract(self, dest: str, only: Optional[Iterable[str]] = None) -> int:
        """Extract the image (or the given paths) into ``dest``; returns file count."""
        wanted = {("/" + p.strip("/")).lower() for p in only} if only else None
        count = 0
        for e in self.entries():
            if wanted is not None and not any(e.path.lower() == w or e.path.lower().startswith(w + "/")
                                              for w in wanted):
                continue
            target = os.path.join(dest, e.path.lstrip("/"))
            if e.is_dir:
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if e.symlink:
                try:
                    os.symlink(e.symlink, target)
                except OSError:
                    pass
                continue
            with open(target, "wb") as out:
                for chunk in _iter_source((self.path, e.lba * SECTOR, e.size)):
                    out.write(chunk)
            count += 1
        return count

    def boot_info(self) -> List[IsoBootInfo]:
        if self.catalog_lba is None:
            return []
        cat = self._sector(self.catalog_lba)
        by_lba = {e.lba: e for e in self.entries() if not e.is_dir}
        out: List[IsoBootInfo] = []
        platforms = {0: "bios", 1: "ppc", 2: "mac", 0xEF: "uefi"}
        medias = {0: "none", 1: "floppy-1.2", 2: "floppy", 3: "floppy-2.88", 4: "harddisk"}
        platform = cat[1]

        def add(rec: bytes, plat: int) -> None:
            if rec[0] != 0x88:
                return
            lba = struct.unpack_from("<I", rec, 8)[0]
            count = struct.unpack_from("<H", rec, 6)[0]
            f = by_lba.get(lba)
            info = IsoBootInfo(platforms.get(plat, hex(plat)), medias.get(rec[1] & 0x0F, "?"), lba, count,
                               f.path if f else None)
            if f and plat == 0 and info.emulation == "none":
                head = self._sector(lba)[8:12]
                info.boot_info_table = struct.unpack("<I", head)[0] == 16
            out.append(info)

        add(cat[32:64], platform)
        pos = 64
        while pos + 32 <= len(cat) and cat[pos] in (0x90, 0x91):
            plat, n = cat[pos + 1], struct.unpack_from("<H", cat, pos + 2)[0]
            final = cat[pos] == 0x91
            pos += 32
            for _ in range(n):
                add(cat[pos:pos + 32], plat)
                pos += 32
            if final:
                break
        return out

    def system_area(self) -> bytes:
        return self._sector(0, 16)
