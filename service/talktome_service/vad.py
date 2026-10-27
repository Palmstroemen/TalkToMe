# SPDX-License-Identifier: LGPL-2.1-or-later
"""Streaming voice activity detection with the Silero VAD model bundled with faster-whisper."""

import os

import numpy as np

FRAME = 512          # samples per frame at 16 kHz, required by Silero
CONTEXT = 64         # samples of the previous frame the model expects in front


def default_model_path():
    import faster_whisper
    return os.path.join(os.path.dirname(faster_whisper.__file__), "assets", "silero_vad_v6.onnx")


class SileroVAD:
    def __init__(self, path=None):
        import onnxruntime
        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.log_severity_level = 4
        self.session = onnxruntime.InferenceSession(
            path or default_model_path(), providers=["CPUExecutionProvider"], sess_options=opts)
        self.reset()

    def reset(self):
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._context = np.zeros(CONTEXT, dtype=np.float32)

    def prob(self, frame):
        frame = np.asarray(frame, dtype=np.float32)
        if frame.shape != (FRAME,):
            raise ValueError("expected {} samples, got {}".format(FRAME, frame.shape))
        x = np.concatenate([self._context, frame])[None, :]
        out, self._h, self._c = self.session.run(None, {"input": x, "h": self._h, "c": self._c})
        self._context = frame[-CONTEXT:]
        return float(np.ravel(out)[0])
