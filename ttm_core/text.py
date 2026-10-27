# SPDX-License-Identifier: LGPL-2.1-or-later
"""Text normalization shared by matching and measurements."""

import re


def normalize(text):
    """Lower case, punctuation removed (decimal commas kept), single spaces."""
    text = text.lower()
    text = re.sub(r"(?<!\d),|,(?!\d)", " ", text)
    text = re.sub(r"[^\w\s,]|_", " ", text)
    return " ".join(text.split())
