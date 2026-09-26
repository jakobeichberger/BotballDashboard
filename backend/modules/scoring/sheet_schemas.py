"""Request models for structured score-sheet definitions (see ``sheet.py``)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_KEY = r"^[a-z][a-z0-9_]*$"


class SheetField(BaseModel):
    """One itemised line: value × multiplier."""

    key: str = Field(pattern=_KEY, max_length=100)
    label: str = Field(min_length=1, max_length=255)
    type: Literal["count", "number", "boolean"] = "count"
    multiplier: float = 1.0
    min_value: float | None = None
    max_value: float | None = None
    required: bool = False

    @model_validator(mode="after")
    def validate_range(self) -> SheetField:
        if (
            self.min_value is not None
            and self.max_value is not None
            and self.max_value < self.min_value
        ):
            raise ValueError(f"{self.key}: max_value must be >= min_value")
        return self


class SheetSumInput(BaseModel):
    """One counted value of a ``sum`` multiplier, e.g. "Max Stack Height"."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=_KEY, max_length=100)
    label: str = Field(min_length=1, max_length=255)
    min_value: float | None = 0
    max_value: float | None = None

    @model_validator(mode="after")
    def validate_range(self) -> SheetSumInput:
        if (
            self.min_value is not None
            and self.max_value is not None
            and self.max_value < self.min_value
        ):
            raise ValueError(f"{self.key}: max_value must be >= min_value")
        return self


class SheetMultiplier(BaseModel):
    """A value applied to a section subtotal.

    boolean: checked → × factor. count/number: × (value × factor + offset).
    sum: × ((Σ inputs, or Π inputs with ``mode: "product"``) × factor + offset),
    e.g. AIRCER "Max Stack Height + # of Stacks".

    A result below 1 leaves the subtotal unchanged, unless ``allow_below_one``
    (a penalty such as the AIRCER Restricted Area rule, checked → × 0.5).
    ``zero_means: "zero"`` (count/number/sum) makes an entered 0 zero the area
    instead of the neutral × 1. With ``source`` (boolean only) the multiplier has
    no input: it is on when that field of the same section is at least 1, e.g.
    2026 "Drum ×2" in the Lower Start Box.
    """

    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=_KEY, max_length=100)
    label: str = Field(min_length=1, max_length=255)
    type: Literal["boolean", "count", "number", "sum"] = "boolean"
    factor: float = 1.0
    offset: float = 0.0
    min_value: float | None = None
    max_value: float | None = None
    source: str | None = Field(default=None, pattern=_KEY, max_length=100)
    inputs: list[SheetSumInput] | None = Field(default=None, min_length=1, max_length=10)
    mode: Literal["sum", "product"] = "sum"
    allow_below_one: bool = False
    zero_means: Literal["neutral", "zero"] = "neutral"

    @model_validator(mode="after")
    def validate_source(self) -> SheetMultiplier:
        if self.source and self.type != "boolean":
            raise ValueError(f"{self.key}: only a checkbox multiplier can follow a field")
        if self.type == "sum" and not self.inputs:
            raise ValueError(f"{self.key}: a sum multiplier needs at least one input")
        if self.type != "sum" and self.inputs:
            raise ValueError(f"{self.key}: only a sum multiplier has inputs")
        if self.type == "boolean" and self.zero_means != "neutral":
            raise ValueError(f"{self.key}: zero_means applies to counted multipliers only")
        return self


class SheetEitherMultiplier(BaseModel):
    """Alternatives of which only the best counts, e.g. "# full pom sets or # full trays ×2"."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=_KEY, max_length=100)
    label: str = Field(min_length=1, max_length=255)
    either: list[SheetMultiplier] = Field(min_length=2, max_length=10)


class SheetSection(BaseModel):
    key: str = Field(pattern=_KEY, max_length=100)
    label: str = Field(min_length=1, max_length=255)
    fields: list[SheetField] = Field(min_length=1, max_length=100)
    multipliers: list[SheetMultiplier | SheetEitherMultiplier] = Field(
        default_factory=list, max_length=20
    )


class SheetDefinition(BaseModel):
    """A structured score sheet: sections per side, "Total = A + B"."""

    sides: list[str] = Field(default_factory=list, max_length=4)
    sections: list[SheetSection] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_keys(self) -> SheetDefinition:
        for side in self.sides:
            if not side or len(side) > 8 or not side.isalnum():
                raise ValueError("sides must be short alphanumeric labels such as 'A'")
        if len(set(self.sides)) != len(self.sides):
            raise ValueError("sides must be unique")
        seen: set[str] = set()
        section_keys: set[str] = set()
        for section in self.sections:
            if section.key in section_keys:
                raise ValueError(f"Duplicate section key: {section.key}")
            section_keys.add(section.key)
            keys = [f.key for f in section.fields]
            field_keys = set(keys)
            for multiplier in section.multipliers:
                options = (
                    multiplier.either
                    if isinstance(multiplier, SheetEitherMultiplier)
                    else [multiplier]
                )
                for option in options:
                    if isinstance(multiplier, SheetEitherMultiplier) and option.type == "sum":
                        raise ValueError(
                            f"{option.key}: a sum multiplier cannot be an either-or alternative"
                        )
                    if option.inputs:
                        keys.extend(item.key for item in option.inputs)
                    if option.source and option.source not in field_keys:
                        raise ValueError(
                            f"{option.key}: source '{option.source}' is not a field of "
                            f"section '{section.key}'"
                        )
                if isinstance(multiplier, SheetEitherMultiplier):
                    keys.extend(option.key for option in multiplier.either)
                else:
                    keys.append(multiplier.key)
            for key in keys:
                if key in seen:
                    raise ValueError(f"Duplicate field key: {key}")
                seen.add(key)
        return self

    def to_dict(self) -> dict:
        data = self.model_dump(mode="json")
        # Leave the optional multiplier keys out where the definition did not
        # set them, so definitions without derived, sum or penalty multipliers
        # keep their exact stored shape. An explicitly given default (e.g.
        # "zero_means": "neutral" in a template) is kept, so the switch stays
        # visible in the JSON editor.
        for section_model, section in zip(self.sections, data["sections"], strict=True):
            for multiplier_model, multiplier in zip(
                section_model.multipliers, section["multipliers"], strict=True
            ):
                options = (
                    zip(multiplier_model.either, multiplier["either"], strict=True)
                    if isinstance(multiplier_model, SheetEitherMultiplier)
                    else [(multiplier_model, multiplier)]
                )
                for option_model, option in options:
                    for name in _OPTIONAL_MULTIPLIER_KEYS:
                        if name not in option_model.model_fields_set:
                            option.pop(name, None)
                    if option.get("source") is None:
                        option.pop("source", None)
                    if option.get("inputs") is None:
                        option.pop("inputs", None)
        return data


_OPTIONAL_MULTIPLIER_KEYS = ("source", "inputs", "mode", "allow_below_one", "zero_means")
