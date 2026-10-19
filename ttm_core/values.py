"""Values spoken while a tool waits for them (DESIGN.md 6.5).

After the first corner of a rectangle, the sketcher asks for its width and height in fields in the
3D view. "50 mal 30", "Breite 50, Höhe 30", "5 cm", "Radius 20", "30 Grad" fill them. Names of
values and units come from the language pack:

    value_names     word → position of the value in the tool's order ("breite": 0, "höhe": 1)
    unit_factors    length unit word → factor to mm ("cm": 10)
    angle_names     a name before a value that makes it an angle ("winkel")
    angle_units     a unit after a value that makes it an angle ("grad", "°")
    radius_words    a name that makes the value a radius ("radius"): circles ask for a diameter
    number_values   number words ("zwölf": 12)
    negative_words  "minus"
    article_numbers number words that are articles as well ("ein"): a number only with a unit
                    after or a name before them
"""

import re

from ttm_core.langpack import pack

NUMBER = re.compile(r"^-?\d+(?:[.,]\d+)?$")


def parse_values(text, language):
    """[(position or None, value, kind)] in the order spoken, kind "length" (mm), "angle" (°) or
    "radius" (mm); [] if the text has no numbers."""
    p = pack(language)
    tokens = re.findall(r"-?\d+(?:[.,]\d+)?|°|[^\W\d_]+", text.lower())
    values, name, kind, negative = [], None, "length", False
    for i, token in enumerate(tokens):
        if token in p.article_numbers:
            following = tokens[i + 1] if i + 1 < len(tokens) else ""
            if name is None and kind == "length" and following not in p.unit_factors:
                continue                       # "ein Rechteck": an article
        if token in p.value_names or token in p.angle_names or token in p.radius_words:
            name = p.value_names.get(token, name)
            if token in p.angle_names:
                kind = "angle"
            elif token in p.radius_words:
                kind = "radius"
        elif token in p.negative_words:
            negative = True
        elif NUMBER.match(token) or token in p.number_values:
            number = float(token.replace(",", ".")) if NUMBER.match(token) else float(p.number_values[token])
            values.append([name, -number if negative else number, kind])
            name, kind, negative = None, "length", False
        elif values and token in p.angle_units:
            values[-1][2] = "angle"            # "30 Grad"
        elif values and token in p.unit_factors:
            values[-1][1] *= p.unit_factors[token]
    return [(position, round(value, 6), kind) for position, value, kind in values]


def only_values(text, language):
    """Whether text says nothing but values: numbers, their names and units, filler words
    ("Breite 50", "und die Höhe 30 mm"). While a tool waits, such a clause is never a command,
    however much it sounds like one ("Breite" ≈ "Part")."""
    p = pack(language)
    tokens = re.findall(r"-?\d+(?:[.,]\d+)?|°|[^\W\d_]+", text.lower())
    value_words = (set(p.value_names) | p.angle_names | p.radius_words | p.negative_words | p.angle_units
                   | set(p.unit_factors) | set(p.number_values) | p.article_numbers | p.stop_words | {"x"})
    return bool(parse_values(text, language)) and all(NUMBER.match(t) or t in value_words for t in tokens)
