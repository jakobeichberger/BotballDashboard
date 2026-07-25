from pydantic import BaseModel, Field


class FormulaBase(BaseModel):
    key: str = Field(
        ...,
        min_length=1,
        max_length=50,
        pattern=r"^[a-z_][a-z0-9_]*$",
        description="Identifier other formulas reference, e.g. seed_score",
    )
    expression: str = Field(..., min_length=1, description="e.g. 3/4 * ((n - rank(x) + 1) / n)")
    label: str | None = None
    description: str | None = None
    sort_order: int = 0
    is_active: bool = True


class FormulaResponse(FormulaBase):
    model_config = {"from_attributes": True}

    id: str
    season_id: str
    category: str


class FormulaSetUpdate(BaseModel):
    """Replaces every formula of one category at once."""

    formulas: list[FormulaBase]


class FormulaValidateRequest(BaseModel):
    formulas: list[FormulaBase]


class FormulaIssueResponse(BaseModel):
    key: str
    team_id: str | None = None
    message: str


class FormulaPreviewRow(BaseModel):
    team_id: str
    team_name: str | None = None
    rank: int | None = None
    values: dict[str, float] = {}


class FormulaPreviewResponse(BaseModel):
    """Result of running a candidate formula set against the season's real data."""

    ok: bool
    order: list[str] = []
    issues: list[FormulaIssueResponse] = []
    rows: list[FormulaPreviewRow] = []


class BracketWeightsUpdate(BaseModel):
    """Bracket -> weight, e.g. {"A": 1.0, "B": 0.5683760683760684}."""

    weights: dict[str, float]


class FormulaFunctionDoc(BaseModel):
    name: str
    signature: str
    description: str


class FormulaReferenceResponse(BaseModel):
    """Everything the editor needs to offer autocompletion and help."""

    inputs: dict[str, str]
    row_functions: list[FormulaFunctionDoc]
    scope_functions: list[FormulaFunctionDoc]
    defaults: dict[str, list[dict[str, str]]]
