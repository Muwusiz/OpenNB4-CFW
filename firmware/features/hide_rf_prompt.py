ID = "hide-rf-prompt"
VERSION = 1
BIT = 1
CHANNEL = "stable"
REQUIRES = []
TOUCHED = [(0x43CB0, 0x43CB4)]

SITE = 0x43CB0


def apply(ctx):
    ctx.body[SITE:SITE + 4] = b"\x00\xBF\x00\xBF"
