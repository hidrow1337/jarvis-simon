"""Stand-in for torch in tests: only what the voice-service touches.
STUB_CUDA=1 makes a GPU appear (12 GB, 3 GB of it in use)."""
import os


class cuda:
    @staticmethod
    def is_available():
        return os.environ.get("STUB_CUDA") == "1"

    @staticmethod
    def get_device_name(index=0):
        return "Stub GPU"

    @staticmethod
    def mem_get_info(index=0):
        """(free, total) bytes: a 12 GB card with 3 GB in use."""
        return 9 * 2**30, 12 * 2**30


def device(kind):
    return kind


class Tensor:
    """A 1-D float tensor, as far as turning audio into 16-bit PCM goes."""

    def __init__(self, values, dtype="float32"):
        self.values = list(values)
        self.dtype = dtype

    def cpu(self):
        return self

    def clamp(self, lo, hi):
        return Tensor(min(max(v, lo), hi) for v in self.values)

    def mul(self, k):
        return Tensor(v * k for v in self.values)

    def short(self):
        return Tensor((int(v) for v in self.values), "int16")

    def numpy(self):
        return self

    def tobytes(self):
        import array
        return array.array("h" if self.dtype == "int16" else "f", self.values).tobytes()
