import struct

ID = "onb4-menu"
VERSION = 1
BIT = 2
CHANNEL = "dev"
REQUIRES = []
TOUCHED = [
    (0xB5500, 0xB55C0),
    (0xB55C0, 0xB55C8),
    (0x657B4, 0x657B8),
    (0x65B60, 0x65B64),
    (0x654EE, 0x654F0),
    (0x65B46, 0x65B4A),
    (0x7BF00, 0x7BF04),
    (0x7E280, 0x7E284),
    (0x80600, 0x80604),
]

BASE = 0x08008000
TABLE = 0x080818C8
NEW_TABLE = 0x080BD500
ROWS = 15
ROW = 12
LIT1 = 0x0806D7B4
LIT2 = 0x0806DB60
CNT1 = 0x0806D4EE
CNT2 = 0x0806DB46
RECS = (0x08083EFC, 0x0808627C, 0x080885FC)
STRING = 0x080BD5C0
LABEL = 0x346
HANDLER = 0x0806DDF5


def apply(ctx):
    table = bytearray(ctx.body[TABLE - BASE:TABLE - BASE + ROWS * ROW])
    table += struct.pack("<HHII", LABEL, 0, HANDLER, 0)
    ctx.place(NEW_TABLE, table)
    ctx.place(STRING, b"OpenNB4\x00")

    for lit in (LIT1, LIT2):
        ctx.body[lit - BASE:lit - BASE + 4] = struct.pack("<I", NEW_TABLE)

    ctx.body[CNT1 - BASE:CNT1 - BASE + 2] = b"\x10\x2c"
    ctx.body[CNT2 - BASE + 2:CNT2 - BASE + 4] = b"\x10\x0f"

    for rec in RECS:
        ctx.body[rec + 4 - BASE:rec + 8 - BASE] = struct.pack("<I", STRING)
