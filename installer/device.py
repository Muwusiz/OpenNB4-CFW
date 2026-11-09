import struct
import time

import hid

VID = 0x284E
PID = 0x8D00
USAGE_PAGE = 0xFF00
REPORT = 280
PAYLOAD = 24

OP_QUERY = 1
OP_READ = 2
OP_ERASE = 3
OP_SPI_ERASE = 4
OP_WRITE = 5
OP_CRC = 6
OP_RESET = 7
OP_VERIFY = 8

APP_BASE = 0x08008000
CHUNK = 0x100
ERASE_ALL = 0xF0000
INFO_LEN = 0x30
VERSION_OFFSET = 0x28


class DeviceError(Exception):
    pass


class Device:
    def __init__(self):
        entries = [e for e in hid.enumerate(VID, PID) if e["usage_page"] == USAGE_PAGE]
        if not entries:
            raise DeviceError("no NB4 found on USB")
        self.handle = hid.device()
        self.handle.open_path(entries[0]["path"])
        time.sleep(0.2)
        self.sequence = 0

    def close(self):
        self.handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _next(self):
        self.sequence = (self.sequence + 1) & 0xFFFFFFFF
        return self.sequence

    def transfer(self, opcode, address=0, length=0, mode=0, data=b"", timeout=3000):
        if len(data) > REPORT - PAYLOAD:
            raise DeviceError("payload too long")
        for _ in range(3):
            sequence = self._next()
            frame = bytearray(REPORT)
            struct.pack_into("<I", frame, 0, sequence)
            struct.pack_into("<I", frame, 4, opcode)
            struct.pack_into("<I", frame, 8, address)
            struct.pack_into("<I", frame, 12, length)
            struct.pack_into("<I", frame, 16, mode)
            frame[PAYLOAD:PAYLOAD + len(data)] = data
            self.handle.write(b"\x00" + bytes(frame))
            time.sleep(0.002)
            try:
                reply = bytes(self.handle.read(REPORT + 1, timeout))
            except OSError as error:
                raise DeviceError(str(error))
            if len(reply) >= PAYLOAD and struct.unpack_from("<I", reply, 0)[0] == sequence:
                return reply
        raise DeviceError("device did not answer")

    def send(self, opcode, address=0, length=0, mode=0, data=b""):
        if len(data) > REPORT - PAYLOAD:
            raise DeviceError("payload too long")
        sequence = self._next()
        frame = bytearray(REPORT)
        struct.pack_into("<I", frame, 0, sequence)
        struct.pack_into("<I", frame, 4, opcode)
        struct.pack_into("<I", frame, 8, address)
        struct.pack_into("<I", frame, 12, length)
        struct.pack_into("<I", frame, 16, mode)
        frame[PAYLOAD:PAYLOAD + len(data)] = data
        self.handle.write(b"\x00" + bytes(frame))

    def info(self):
        return self.transfer(OP_QUERY)[PAYLOAD:PAYLOAD + INFO_LEN]

    def version(self):
        info = self.info()
        return struct.unpack_from("<II", info, VERSION_OFFSET)

    def read(self, address, length):
        out = bytearray()
        while length:
            n = min(CHUNK, length)
            reply = self.transfer(OP_READ, address, n)
            out += reply[PAYLOAD:PAYLOAD + n]
            address += n
            length -= n
        return bytes(out)

    def write(self, address, data, mode=1):
        for offset in range(0, len(data), CHUNK):
            block = data[offset:offset + CHUNK]
            self.transfer(OP_WRITE, address + offset, len(block), mode, block)

    def erase(self, address, length):
        self.transfer(OP_ERASE, address, length)

    def verify(self, address, length):
        return self.transfer(OP_VERIFY, address, length)[PAYLOAD]

    def erase_app(self):
        self.transfer(OP_ERASE, ERASE_ALL, 0, timeout=30000)

    def program(self, image):
        for offset in range(0, len(image), CHUNK):
            block = image[offset:offset + CHUNK]
            self.transfer(OP_WRITE, offset, len(block), 1, block)

    def verify_image(self):
        reply = self.transfer(OP_VERIFY)
        return struct.unpack_from("<I", reply, 0x10)[0]

    def reset(self):
        self.send(OP_RESET)
