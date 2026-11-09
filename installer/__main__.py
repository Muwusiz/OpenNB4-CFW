import argparse
import hashlib
import sys

from .device import APP_BASE, Device, DeviceError

DEFAULT_BACKUP = 0x180000


def format_version(patch, major):
    if (patch >> 24) == 0x03:
        dev = (patch >> 16) & 0xFF
        release = patch & 0xFFFF
        return "3.0.%d-dev.%d" % (release, dev) if dev else "3.0.%d" % release
    return "%d.%d.%d" % ((major >> 16) & 0xFFFF, major & 0xFFFF, patch)


def cmd_info(args):
    with Device() as device:
        patch, major = device.version()
        info = device.info()
    print("version   %s" % format_version(patch, major))
    print("raw       patch 0x%08X  major 0x%08X" % (patch, major))
    print("info      %s" % info.hex())
    return 0


def cmd_backup(args):
    length = args.length
    with Device() as device:
        data = device.read(0, length)
    open(args.out, "wb").write(data)
    print("read      %d bytes from 0x%08X" % (len(data), APP_BASE))
    print("sha256    %s" % hashlib.sha256(data).hexdigest())
    print("wrote     %s" % args.out)
    return 0


def cmd_install(args):
    image = open(args.image, "rb").read()
    print("image     %d bytes" % len(image))
    print("sha256    %s" % hashlib.sha256(image).hexdigest())
    if not args.yes:
        print("refusing without --yes")
        return 1
    with Device() as device:
        device.erase_app()
        device.program(image)
        device.reset()
    print("installed")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="installer")
    sub = parser.add_subparsers(dest="command", required=True)

    info = sub.add_parser("info")
    info.set_defaults(func=cmd_info)

    backup = sub.add_parser("backup")
    backup.add_argument("--out", required=True)
    backup.add_argument("--length", type=lambda s: int(s, 0), default=DEFAULT_BACKUP)
    backup.set_defaults(func=cmd_backup)

    install = sub.add_parser("install")
    install.add_argument("--image", required=True)
    install.add_argument("--yes", action="store_true")
    install.set_defaults(func=cmd_install)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except DeviceError as error:
        print("error: %s" % error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
