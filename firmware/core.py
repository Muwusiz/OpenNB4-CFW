import struct

CFW_INFO_ADDR = 0x080BF000
CFW_INFO_MAGIC = 0x34424E4F
CFW_INFO_LEN = 16
OFF_VERSION = 0xF8C


def crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def apply(ctx):
    struct.pack_into("<I", ctx.body, OFF_VERSION, ctx.version)

    bitmap = 0
    for feature in ctx.features:
        bitmap |= 1 << feature.BIT

    info = struct.pack("<III", CFW_INFO_MAGIC, ctx.version, bitmap)
    info += struct.pack("<HH", crc16(info), 0xFFFF)
    ctx.place(CFW_INFO_ADDR, info)
