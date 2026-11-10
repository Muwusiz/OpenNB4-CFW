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

    def reopen(self):
        try:
            self.handle.close()
        except Exception:
            pass
        entries = [e for e in hid.enumerate(VID, PID) if e["usage_page"] == USAGE_PAGE]
        if not entries:
            raise DeviceError("no NB4 found on USB")
        self.handle = hid.device()
        self.handle.open_path(entries[0]["path"])
        time.sleep(0.2)

    def transfer(self, opcode, address=0, length=0, mode=0, a4=0, data=b"", timeout=3000):
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
            struct.pack_into("<I", frame, 20, a4)
            frame[PAYLOAD:PAYLOAD + len(data)] = data
            self.handle.write(b"\x00" + bytes(frame))
            time.sleep(0.002)
            try:
                reply = bytes(self.handle.read(REPORT + 1, timeout))
            except OSError:
                self.reopen()
                continue
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

    def model_cmd(self, cmd, a1=0, a2=0, a3=0, a4=0, data=b""):
        return self.transfer(cmd, a1, a2, a3, a4, data)

    def model_handshake(self):
        self.model_cmd(0x6D)

    def model_session(self, mode):
        self.model_cmd(0x6C, 0, mode)

    def model_directory(self):
        data = self.model_cmd(0x64)[PAYLOAD:]
        return {
            "total": struct.unpack_from("<I", data, 4)[0],
            "directory": struct.unpack_from("<I", data, 8)[0],
            "count": struct.unpack_from("<I", data, 12)[0],
            "record": struct.unpack_from("<I", data, 16)[0],
        }

    def model_read(self, slot, length):
        out = bytearray()
        offset = 0
        while offset < length:
            n = min(0x100, length - offset)
            reply = self.model_cmd(0x69, 0, slot, offset, n)
            out += reply[PAYLOAD:PAYLOAD + n]
            offset += n
        return bytes(out)

    def model_write(self, slot, data):
        for offset in range(0, len(data), 0x100):
            block = data[offset:offset + 0x100]
            self.model_cmd(0x69, 1, slot, offset, len(block), block)

    def model_name(self, slot):
        return self.model_cmd(0x6A, 0, slot)[PAYLOAD:PAYLOAD + 0x14]

    def model_commit(self):
        self.model_cmd(0x6B)

    def model_backup(self):
        self.model_handshake()
        self.model_session(3)
        info = self.model_directory()
        directory = self.model_read(1, info["directory"])
        models = [self.model_read(slot + 2, info["record"]) for slot in range(info["count"])]
        names = [self.model_name(slot) for slot in range(info["count"])]
        self.model_session(1)
        return info, directory, models, names

    def model_restore(self, info, directory, models, names):
        self.model_handshake()
        self.model_session(4)
        self.model_cmd(0x64, 1, info["total"], info["directory"], info["record"])
        self.model_write(1, directory)
        for slot, record in enumerate(models):
            self.model_write(slot + 2, record)
        for slot, name in enumerate(names):
            self.model_cmd(0x6A, 1, slot, 0x14, 0, name)
        self.model_commit()
        self.model_session(1)
