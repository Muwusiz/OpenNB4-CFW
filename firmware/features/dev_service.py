import struct

import keystone

ID = "dev-service"
VERSION = 1
BIT = 0
CHANNEL = "dev"
REQUIRES = []
TOUCHED = [(0xB5400, 0xB5500)]

ADDRESS = 0x080BD400

ASM = """
    .syntax unified
    .thumb

    push {r0, r1, r2, r3, r4, r5, r6, r7, r12, lr}

    movw r4, #0x0000
    movt r4, #0xC07A
    ldr  r5, [r4]
    cmp  r5, #0
    beq  svc_exit

    movs r6, #0
    str  r6, [r4]
    cmp  r5, #1
    beq  svc_snapshot
    cmp  r5, #2
    beq  svc_call
    b    svc_done

svc_snapshot:
    movw r3, #0xB000
    movt r3, #0x4002
    movw r12, #0xFFFF
snap_wait:
    ldr  r1, [r3]
    tst  r1, #1
    beq  snap_idle
    subs r12, r12, #1
    bne  snap_wait
snap_idle:
    movw r2, #0x68AC
    movt r2, #0x4001
    ldr  r2, [r2]
    cmp  r2, #0
    beq  svc_done
    movw r3, #0x1000
    movt r3, #0xC07A
    movw r0, #0xB000
    movt r0, #0x0004
snap_copy:
    ldr  r1, [r2], #4
    str  r1, [r3], #4
    subs r0, r0, #4
    bne  snap_copy
    b    svc_done

svc_call:
    ldr  r6, [r4, #8]
    cmp  r6, #0
    beq  svc_done
    orr  r6, r6, #1
    ldr  r0, [r4, #0xC]
    ldr  r1, [r4, #0x10]
    ldr  r2, [r4, #0x14]
    ldr  r3, [r4, #0x18]
    blx  r6
    str  r0, [r4, #0x1C]

svc_done:
    ldr  r1, [r4, #4]
    adds r1, r1, #1
    str  r1, [r4, #4]

svc_exit:
    pop  {r0, r1, r2, r3, r4, r5, r6, r7, r12, lr}
    bx   lr
"""


def apply(ctx):
    ks = keystone.Ks(keystone.KS_ARCH_ARM, keystone.KS_MODE_THUMB)
    encoded, _ = ks.asm(ASM, addr=ADDRESS)
    if encoded is None:
        raise RuntimeError("dev-service handler did not assemble")
    ctx.place(ADDRESS, bytes(encoded))
