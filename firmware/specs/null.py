import struct

NAME = "null"
CHANNEL = "dev"
VERSION = 0x03010001
TOUCHED = [(0xF8C, 0xF90)]


def apply(body):
    struct.pack_into("<I", body, 0xF8C, VERSION)
