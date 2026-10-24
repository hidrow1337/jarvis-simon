"""Stand-in for torch in tests: only what the voice-service touches.
STUB_CUDA=1 makes a GPU appear."""
import os


class cuda:
    @staticmethod
    def is_available():
        return os.environ.get("STUB_CUDA") == "1"

    @staticmethod
    def get_device_name(index=0):
        return "Stub GPU"


def device(kind):
    return kind
