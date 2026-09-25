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
    A result below 1 leaves the subtotal unchanged.
    """

    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=_KEY, max_length=100)
    label: str = Field(min_length=1, max_length=255)
    type: Literal["boolean", "count", "number"] = "boolean"
    factor: float = 1.0
    offset: float = 0.0
    min_value: float | None = None
    max_value: float | None = None


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
            for multiplier in section.multipliers:
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
        return self.model_dump(mode="json")
