import argparse
import hashlib
import importlib
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "firmware"))

from map import onb4_20116 as M
import core

MAGIC1 = 0xC87251CC
MAGIC2 = 0x92017EA0
OFF_MAGIC1 = 0xF80
OFF_MAGIC2 = 0xF84
OFF_LEN = 0xF88
OFF_VERSION = 0xF8C
OFF_VERSION_MAJOR = 0xF90
HEADER = (OFF_MAGIC1, OFF_VERSION_MAJOR + 4)
MAX_BODY = 0x000F7FFE
IMAGE_BASE = 0x08008000

CFW_INFO_OFFSET = core.CFW_INFO_ADDR - IMAGE_BASE
CFW_INFO_LEN = core.CFW_INFO_LEN

BASE_DIR = os.path.join(ROOT, "firmware", "base", "2.0.116")
BASE_CODE = os.path.join(BASE_DIR, "code.bin")
DIST_DIR = os.path.join(ROOT, "dist")
MANIFEST = os.path.join(ROOT, "MANIFEST.json")


class Context:
    def __init__(self, body, version, features):
        self.body = body
        self.version = version
        self.features = features

    def place(self, address, data):
        offset = address - IMAGE_BASE
        if offset < len(self.body):
            raise SystemExit("placement 0x%08X overlaps the image" % address)
        self.body.extend(b"\xFF" * (offset - len(self.body)))
        self.body.extend(data)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def encode_version(release, dev=0):
    return 0x03000000 | ((dev & 0xFF) << 16) | (release & 0xFFFF)


def decode_version(value):
    return (value >> 24) & 0xFF, (value >> 16) & 0xFF, value & 0xFFFF


def format_version(value):
    tag, dev, release = decode_version(value)
    if tag != 0x03:
        return "0x%08X" % value
    return "3.0.%d-dev.%d" % (release, dev) if dev else "3.0.%d" % release


def seal(body):
    body = bytearray(body)
    if len(body) > MAX_BODY:
        raise SystemExit("body %d exceeds the bootloader limit %d" % (len(body), MAX_BODY))
    struct.pack_into("<I", body, OFF_LEN, len(body))
    return bytes(body) + struct.pack("<H", crc16(bytes(body)))


def diff_ranges(a, b):
    n = max(len(a), len(b))
    out = []
    start = None
    last = None
    for i in range(n):
        x = a[i] if i < len(a) else 0xFF
        y = b[i] if i < len(b) else 0xFF
        if x != y:
            if start is None:
                start = i
            last = i
        elif start is not None:
            out.append((start, last + 1))
            start = None
    if start is not None:
        out.append((start, last + 1))
    return out


def allowed(offset, features):
    if HEADER[0] <= offset < HEADER[1]:
        return True
    if CFW_INFO_OFFSET <= offset < CFW_INFO_OFFSET + CFW_INFO_LEN:
        return True
    return any(lo <= offset < hi for f in features for lo, hi in f.TOUCHED)


def gate(img, base_body, features, version):
    errors = []
    body = img[:-2]
    if struct.unpack_from("<I", img, OFF_MAGIC1)[0] != MAGIC1:
        errors.append("magic1 damaged")
    if struct.unpack_from("<I", img, OFF_MAGIC2)[0] != MAGIC2:
        errors.append("magic2 damaged")
    if struct.unpack_from("<I", img, OFF_LEN)[0] != len(body):
        errors.append("length field does not match the body")
    if struct.unpack_from("<H", img, len(body))[0] != crc16(img[:len(body)]):
        errors.append("crc mismatch")
    for lo, hi in diff_ranges(base_body, body):
        for offset in range(lo, hi):
            if not allowed(offset, features):
                errors.append("unexpected change at 0x%X" % offset)
                break
    return errors


def load(name, package):
    return importlib.import_module(package + "." + name.replace("-", "_"))


def resolve(ids):
    features = []
    seen = set()

    def add(fid):
        if fid in seen:
            return
        seen.add(fid)
        module = load(fid, "features")
        if getattr(module, "DEPRECATED", False):
            raise SystemExit("feature %s is deprecated: %s"
                             % (module.ID, getattr(module, "REASON", "")))
        for requirement in module.REQUIRES:
            add(requirement)
        features.append(module)

    for fid in ids:
        add(fid)
    return features


def build(profile_name, release, dev, update_manifest=False, dry_run=False):
    profile = load(profile_name, "profiles")
    version = encode_version(release, dev)

    if dev and profile.CHANNEL == "stable":
        raise SystemExit("a stable profile cannot carry a dev version")

    features = resolve(profile.FEATURES)
    for feature in features:
        if feature.CHANNEL == "dev" and profile.CHANNEL == "stable":
            raise SystemExit("stable profile may not include dev feature %s" % feature.ID)

    base = open(BASE_CODE, "rb").read()
    if sha256(base) != M.BASE_SHA256:
        raise SystemExit("base image hash mismatch")

    base_body = base[:-2]
    body = bytearray(base_body)
    ctx = Context(body, version, features)

    for feature in features:
        feature.apply(ctx)

    core.apply(ctx)

    img = seal(body)
    errors = gate(img, base_body, features, version)
    if errors:
        print("gate failed:")
        for error in errors:
            print("  " + error)
        return 1

    changes = diff_ranges(base_body, img[:-2])
    changed = sum(hi - lo for lo, hi in changes)
    build_id = format_version(version)

    print("profile   %s (%s)" % (profile.NAME, profile.CHANNEL))
    print("version   %s (0x%08X)" % (build_id, version))
    print("features  %s" % (", ".join("%s@%d" % (f.ID, f.VERSION) for f in features) or "none"))
    print("image     %d bytes (0x%X)" % (len(img), len(img)))
    print("sha256    %s" % sha256(img))
    print("changed   %d bytes in %d ranges" % (changed, len(changes)))

    if dry_run:
        print("dry run, nothing written")
        return 0

    os.makedirs(DIST_DIR, exist_ok=True)
    out = os.path.join(DIST_DIR, build_id + ".bin")
    open(out, "wb").write(img)
    print("wrote     %s" % out)

    if update_manifest:
        manifest = json.load(open(MANIFEST))
        entry = {
            "id": build_id,
            "channel": profile.CHANNEL,
            "version": version,
            "profile": profile.NAME,
            "features": ["%s@%d" % (f.ID, f.VERSION) for f in features],
            "base_sha256": M.BASE_SHA256,
            "image_sha256": sha256(img),
            "image_len": len(img),
            "changed_bytes": changed,
            "changed_ranges": [[lo, hi] for lo, hi in changes],
        }
        manifest["builds"] = [b for b in manifest["builds"] if b["id"] != build_id]
        manifest["builds"].append(entry)
        open(MANIFEST, "w").write(json.dumps(manifest, indent=2) + "\n")
        print("manifest  updated")

    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--release", type=int, required=True)
    ap.add_argument("--dev", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--update-manifest", action="store_true")
    args = ap.parse_args()
    return build(args.profile, args.release, args.dev, args.update_manifest, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
