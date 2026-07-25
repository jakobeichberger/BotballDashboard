"""Admin API for the per-season scoring formulas."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import require_permission
from core.database import get_db
from modules.scoring import formula_service as svc
from modules.scoring.formula_engine import DEFAULT_FORMULA_SETS, KNOWN_INPUTS
from modules.scoring.formula_schemas import (
    BracketWeightsUpdate,
    FormulaFunctionDoc,
    FormulaPreviewResponse,
    FormulaReferenceResponse,
    FormulaResponse,
    FormulaSetUpdate,
    FormulaValidateRequest,
)

router = APIRouter(prefix="/scoring/formulas", tags=["scoring", "formulas"])

_ROW_FUNCTION_DOCS = [
    ("avg", "avg(values)", "Mean of all values"),
    ("avg_best", "avg_best(values, k)", "Mean of the best k values (divides by what exists)"),
    ("sum", "sum(values)", "Sum of all values"),
    ("min", "min(a, b, ...)", "Smallest value"),
    ("max", "max(a, b, ...)", "Largest value"),
    ("count", "count(values)", "How many values there are"),
    ("abs", "abs(x)", "Absolute value"),
    ("round", "round(x, digits)", "Round to `digits` decimals"),
    ("floor", "floor(x)", "Round down"),
    ("ceil", "ceil(x)", "Round up"),
    ("sqrt", "sqrt(x)", "Square root"),
    ("clamp", "clamp(x, lo, hi)", "Limit x to the range lo..hi"),
    ("iif", "iif(condition, a, b)", "a when the condition holds, otherwise b"),
    ("safe_div", "safe_div(a, b, default)", "a / b, or `default` when b is 0"),
]

_SCOPE_FUNCTION_DOCS = [
    ("rank", "rank(column)", "Rank of this team by `column`, best first (ties share a rank)"),
    ("rank_asc", "rank_asc(column)", "Rank by `column`, smallest first"),
    ("max_all", "max_all(column)", "Largest value of `column` across the whole category"),
    ("min_all", "min_all(column)", "Smallest value of `column` across the whole category"),
    ("avg_all", "avg_all(column)", "Mean of `column` across the whole category"),
    ("sum_all", "sum_all(column)", "Sum of `column` across the whole category"),
    ("count_all", "count_all()", "Number of teams in the category"),
]


@router.get("/reference", response_model=FormulaReferenceResponse)
async def get_reference(_=Depends(require_permission("scoring:read"))):
    """Variables, functions and shipped defaults — drives the editor's help panel."""
    return FormulaReferenceResponse(
        inputs=KNOWN_INPUTS,
        row_functions=[
            FormulaFunctionDoc(name=n, signature=s, description=d) for n, s, d in _ROW_FUNCTION_DOCS
        ],
        scope_functions=[
            FormulaFunctionDoc(name=n, signature=s, description=d)
            for n, s, d in _SCOPE_FUNCTION_DOCS
        ],
        defaults={
            category: [{"key": k, "expression": e} for k, e in formulas]
            for category, formulas in DEFAULT_FORMULA_SETS.items()
        },
    )


@router.get("/seasons/{season_id}", response_model=list[FormulaResponse])
async def list_formulas(
    season_id: str,
    category: str | None = None,
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_formulas(db, season_id, category)


@router.get("/seasons/{season_id}/{category}/effective", response_model=list[dict])
async def get_effective_set(
    season_id: str,
    category: str,
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    """The formulas actually in use, falling back to the documented defaults."""
    pairs = await svc.get_formula_set(db, season_id, category)
    return [{"key": k, "expression": e} for k, e in pairs]


@router.put("/seasons/{season_id}/{category}", response_model=list[FormulaResponse])
async def replace_formula_set(
    season_id: str,
    category: str,
    body: FormulaSetUpdate,
    _=Depends(require_permission("scoring:formulas")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.replace_formula_set(
        db, season_id, category, [f.model_dump() for f in body.formulas]
    )


@router.post("/seasons/{season_id}/{category}/reset", response_model=list[FormulaResponse])
async def reset_formula_set(
    season_id: str,
    category: str,
    _=Depends(require_permission("scoring:formulas")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.reset_to_defaults(db, season_id, category)


@router.post("/events/{event_id}/{category}/preview", response_model=FormulaPreviewResponse)
async def preview_formula_set(
    event_id: str,
    category: str,
    body: FormulaValidateRequest,
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    """Run a candidate formula set against this event's real results, without saving."""
    run = await svc.preview_formula_set(
        db, event_id, category, [(f.key, f.expression) for f in body.formulas]
    )
    return FormulaPreviewResponse(
        ok=run.ok,
        order=run.order,
        issues=[{"key": i.key, "team_id": i.team_id, "message": i.message} for i in run.issues],
        rows=[
            {
                "team_id": r.get("team_id", ""),
                "team_name": r.get("team_name"),
                "rank": r.get("rank"),
                "values": {
                    k: float(v)
                    for k, v in r.items()
                    if isinstance(v, int | float) and not isinstance(v, bool)
                },
            }
            for r in run.rows
        ],
    )


@router.get("/seasons/{season_id}/{category}/bracket-weights", response_model=dict[str, float])
async def get_bracket_weights(
    season_id: str,
    category: str,
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.get_bracket_weights(db, season_id, category)


@router.put("/seasons/{season_id}/{category}/bracket-weights", response_model=dict[str, float])
async def set_bracket_weights(
    season_id: str,
    category: str,
    body: BracketWeightsUpdate,
    _=Depends(require_permission("scoring:formulas")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.set_bracket_weights(db, season_id, category, body.weights)
