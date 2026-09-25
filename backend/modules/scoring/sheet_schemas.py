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
    def validate_range(self) -> "SheetField":
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
    A result below 1 leaves the subtotal unchanged. With ``source`` (boolean
    only) the multiplier has no input: it is on when that field of the same
    section is at least 1, e.g. 2026 "Drum ×2" in the Lower Start Box.
    """

    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=_KEY, max_length=100)
    label: str = Field(min_length=1, max_length=255)
    type: Literal["boolean", "count", "number"] = "boolean"
    factor: float = 1.0
    offset: float = 0.0
    min_value: float | None = None
    max_value: float | None = None
    source: str | None = Field(default=None, pattern=_KEY, max_length=100)

    @model_validator(mode="after")
    def validate_source(self) -> "SheetMultiplier":
        if self.source and self.type != "boolean":
            raise ValueError(f"{self.key}: only a checkbox multiplier can follow a field")
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
    def validate_keys(self) -> "SheetDefinition":
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
        # Leave "source" out where it is unset, so definitions without derived
        # multipliers keep their exact stored shape.
        for section in data["sections"]:
            for multiplier in section["multipliers"]:
                for option in multiplier.get("either") or [multiplier]:
                    if option.get("source") is None:
                        option.pop("source", None)
        return data
