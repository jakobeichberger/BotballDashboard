"""Score-sheet calculation: the single definition of how a sheet adds up.

The frontend mirrors this module line by line in
``frontend/src/modules/scoring/sheet/calculator.ts``; both are tested against the
same fixtures (``frontend/src/modules/scoring/sheet/__fixtures__``), so a change
here needs the same change there.

Two schema shapes are supported:

* **Flat** (the original format): a list of fields, total = Σ value × multiplier.
* **Structured** (``definition``): the layout of the real Botball sheets —

  .. code-block:: text

     side A ─┬─ section "Serving Station"
             │    fields:       Σ value × multiplier            = subtotal
             │    multipliers:  × boolean (checked → factor)
             │                  × derived (a field of the section ≥ 1 → factor)
             │                  × count   (value × factor + offset)
             │                  × either  (max of the alternatives)
             │                                                   = section total
             └─ …                                   Σ sections  = side total
     side B ─── (same sections, own values)                      = side total
                                                    Σ sides     = Total A + B

A *derived* multiplier (``source`` names a field of the same section) has no
input of its own: it is on when that field's value is at least 1. The 2026
Lower Start Box works that way — a Drum or Botguy scoring in the box doubles
the area ("Drum ×2", "Botguy ×2"), so the juror counts the piece once instead
of also ticking a box that could contradict the count.

Multipliers of one section multiply with each other (2026 Packaging Bin:
subtotal × (sorted baskets + 1) × returned baskets).

A multiplier whose value is below 1 (e.g. "# of sorted stations" = 0, or an
unchecked box) leaves the subtotal unchanged: on the paper sheets an empty
multiplier box means "no bonus", never "the area scores nothing".

Raw values of a two-sided sheet are keyed ``"<side>.<field key>"`` (``"A.potato"``),
single-sided sheets use the plain field key.
"""

from __future__ import annotations

from typing import Any

from core.exceptions import ValidationError

SIDE_SEPARATOR = "."


# ── Shape helpers ─────────────────────────────────────────────────────────────


def raw_key(side: str | None, key: str) -> str:
    return f"{side}{SIDE_SEPARATOR}{key}" if side else key


def is_structured(definition: Any) -> bool:
    return isinstance(definition, dict) and isinstance(definition.get("sections"), list)


def from_flat_fields(fields: list[dict]) -> dict:
    """Express a flat field list as a structured definition without multipliers.

    Fields keep their order; consecutive-or-not, fields sharing a ``section``
    label are grouped into one section, so the breakdown matches what the
    entry form shows. The total is unchanged: Σ value × multiplier.
    """
    sections: list[dict] = []
    by_label: dict[str, dict] = {}
    for field in fields:
        label = field.get("section") or ""
        section = by_label.get(label)
        if section is None:
            section = {
                "key": f"section_{len(sections) + 1}",
                "label": label,
                "fields": [],
                "multipliers": [],
            }
            by_label[label] = section
            sections.append(section)
        section["fields"].append(field)
    return {"sides": [], "sections": sections}


def normalize(fields: list[dict] | None, definition: dict | None) -> dict | None:
    """The structured definition for a schema, or None when nothing is configured."""
    if is_structured(definition):
        return definition
    if fields:
        return from_flat_fields(fields)
    return None


def is_derived(multiplier: dict) -> bool:
    """A multiplier switched on by a field of its section instead of an input."""
    return bool(multiplier.get("source"))


def _multiplier_inputs(multiplier: dict) -> list[dict]:
    if "either" in multiplier:
        return [o for o in multiplier.get("either") or [] if not is_derived(o)]
    return [] if is_derived(multiplier) else [multiplier]


def input_fields(definition: dict) -> list[dict]:
    """Every value a sheet asks for, with its raw key and bounds.

    Used for validation and to derive the flat ``fields`` list stored next to a
    structured definition (entry forms, OCR mapping, exports).
    """
    sides = definition.get("sides") or [None]
    out: list[dict] = []
    for side in sides:
        for section in definition.get("sections", []):
            section_label = section.get("label") or section.get("key") or ""
            for field in section.get("fields", []):
                out.append(
                    {
                        "key": raw_key(side, field["key"]),
                        "field_key": field["key"],
                        "side": side,
                        "section": section_label,
                        "section_key": section.get("key"),
                        "label": field.get("label", field["key"]),
                        "type": field.get("type", "count"),
                        "multiplier": float(field.get("multiplier", 1)),
                        "min_value": field.get("min_value", field.get("min")),
                        "max_value": field.get("max_value", field.get("max")),
                        "required": bool(field.get("required", False)),
                        "role": "field",
                    }
                )
            for multiplier in section.get("multipliers", []):
                for option in _multiplier_inputs(multiplier):
                    out.append(
                        {
                            "key": raw_key(side, option["key"]),
                            "field_key": option["key"],
                            "side": side,
                            "section": section_label,
                            "section_key": section.get("key"),
                            "label": option.get("label", option["key"]),
                            "type": option.get("type", "boolean"),
                            "multiplier": float(option.get("factor", 1)),
                            "min_value": option.get("min_value"),
                            "max_value": option.get("max_value"),
                            "required": False,
                            "role": "multiplier",
                            "group": multiplier.get("key") if "either" in multiplier else None,
                        }
                    )
    return out


def flat_fields(definition: dict) -> list[dict]:
    """The ``ScoringSchema.fields`` list stored alongside a structured definition."""
    fields = []
    for item in input_fields(definition):
        side = item["side"]
        fields.append(
            {
                "key": item["key"],
                "label": item["label"],
                "type": item["type"],
                "multiplier": item["multiplier"],
                "min_value": item["min_value"],
                "max_value": item["max_value"],
                "required": item["required"],
                "section": f"{side} · {item['section']}" if side else item["section"],
                "role": item["role"],
            }
        )
    return fields


# ── Calculation ───────────────────────────────────────────────────────────────


def _number(key: str, value: Any) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"Score for '{key}' must be a number") from None


def _value(raw: dict, key: str, spec: dict) -> float:
    number = _number(key, raw.get(key))
    max_value = spec.get("max_value")
    if max_value is not None and number > float(max_value):
        raise ValidationError(f"Score for '{key}' exceeds the maximum of {max_value}")
    return number


def _effective(raw: dict, side: str | None, spec: dict) -> float:
    """Factor one multiplier input contributes; below 1 counts as neutral (×1)."""
    if is_derived(spec):
        source = raw_key(side, spec["source"])
        return float(spec.get("factor", 1)) if _number(source, raw.get(source)) >= 1 else 1.0
    key = raw_key(side, spec["key"])
    value = _value(raw, key, spec)
    if spec.get("type", "boolean") == "boolean":
        factor = float(spec.get("factor", 1)) if value else 1.0
    else:
        factor = value * float(spec.get("factor", 1)) + float(spec.get("offset", 0))
    return factor if factor >= 1 else 1.0


def multiplier_factor(raw: dict, side: str | None, multiplier: dict) -> float:
    if "either" in multiplier:
        options = multiplier.get("either") or []
        return max((_effective(raw, side, option) for option in options), default=1.0)
    return _effective(raw, side, multiplier)


def compute_sheet(raw: dict, definition: dict | None) -> dict:
    """Total plus a per-side, per-section breakdown.

    With no definition at all, values are summed as-is — that is what a season
    without a configured schema has always meant.
    """
    if definition is None:
        total = sum(_number(key, value) for key, value in raw.items())
        return {"total": round(total, 2), "sides": []}

    sides_out = []
    grand_total = 0.0
    for side in definition.get("sides") or [None]:
        sections_out = []
        side_total = 0.0
        for section in definition.get("sections", []):
            subtotal = 0.0
            for field in section.get("fields", []):
                value = _value(raw, raw_key(side, field["key"]), field)
                subtotal += value * float(field.get("multiplier", 1))
            factor = 1.0
            for multiplier in section.get("multipliers", []):
                factor *= multiplier_factor(raw, side, multiplier)
            section_total = subtotal * factor
            side_total += section_total
            sections_out.append(
                {
                    "key": section.get("key"),
                    "label": section.get("label"),
                    "subtotal": round(subtotal, 2),
                    "multiplier": round(factor, 4),
                    "total": round(section_total, 2),
                }
            )
        grand_total += side_total
        sides_out.append({"side": side, "total": round(side_total, 2), "sections": sections_out})
    return {"total": round(grand_total, 2), "sides": sides_out}


def compute_total(raw: dict, fields: list[dict] | None, definition: dict | None = None) -> float:
    return float(compute_sheet(raw, normalize(fields, definition))["total"])


def validate(raw: dict, fields: list[dict] | None, definition: dict | None = None) -> None:
    """Reject unknown keys, non-numbers and out-of-range values.

    A configured schema is authoritative: a key it doesn't define is an error,
    otherwise a client could smuggle values past it.
    """
    normalized = normalize(fields, definition)
    errors: list[str] = []
    if normalized is None:
        for key, value in raw.items():
            try:
                _number(key, value)
            except ValidationError:
                errors.append(f"{key} must be numeric")
        if errors:
            raise ValidationError("; ".join(errors))
        return

    specs = {item["key"]: item for item in input_fields(normalized)}
    for key, spec in specs.items():
        if spec["required"] and key not in raw:
            errors.append(f"{key} is required")
    for key, value in raw.items():
        found = specs.get(key)
        if found is None:
            errors.append(f"{key} is not part of the active scoring schema")
            continue
        try:
            number = _number(key, value)
        except ValidationError:
            errors.append(f"{key} must be numeric")
            continue
        minimum = found.get("min_value")
        maximum = found.get("max_value")
        if minimum is not None and number < float(minimum):
            errors.append(f"{key} must be at least {minimum}")
        if maximum is not None and number > float(maximum):
            errors.append(f"{key} must be at most {maximum}")
    if errors:
        raise ValidationError("; ".join(errors))


def sheet_value(raw: dict, key: str, definition: dict | None) -> float:
    """A raw value summed over all sides (``A.x`` + ``B.x``), for tie-breakers."""
    sides = (definition or {}).get("sides") or []
    keys = [raw_key(side, key) for side in sides] if sides else [key]
    total = 0.0
    for candidate in keys:
        try:
            total += _number(candidate, raw.get(candidate))
        except ValidationError:
            continue
    return total
