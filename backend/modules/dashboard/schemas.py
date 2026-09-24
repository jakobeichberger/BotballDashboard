"""Response models of the analytics, summary and calendar endpoints."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

# ── Shared ────────────────────────────────────────────────────────────────────


class BoxSummary(BaseModel):
    n: int = 0
    min: float | None = None
    q1: float | None = None
    median: float | None = None
    q3: float | None = None
    max: float | None = None
    mean: float | None = None


# ── Deadlines & timeline ──────────────────────────────────────────────────────


class DeadlineEntry(BaseModel):
    id: str
    title: str
    kind: str
    color: str
    start: date | datetime
    end: date | datetime | None = None
    all_day: bool
    season_id: str
    season_name: str
    event_id: str | None = None
    description: str | None = None
    done: bool | None = None


class TimelinePhase(BaseModel):
    id: str
    name: str
    phase_type: str
    starts_at: datetime | None
    ends_at: datetime | None
    status: str


class TimelineEvent(BaseModel):
    id: str
    name: str
    event_type: str
    color: str
    starts_at: datetime | None
    ends_at: datetime | None
    status: str
    phases: list[TimelinePhase]


class SeasonTimeline(BaseModel):
    season_id: str
    season_name: str
    season_year: int
    events: list[TimelineEvent]


class CalendarFeedStatus(BaseModel):
    active: bool
    created_at: datetime | None = None
    last_used_at: datetime | None = None


class CalendarFeedCreated(BaseModel):
    token: str
    #: Path below the API root, e.g. /api/dashboard/deadlines.ics?token=…
    path: str


# ── Summary ───────────────────────────────────────────────────────────────────


class SummaryTeamRef(BaseModel):
    team_id: str | None
    team_name: str | None


class SummaryScheduledMatch(BaseModel):
    id: str
    code: str
    round_number: int
    table_number: int | None
    scheduled_at: datetime | None
    status: str
    phase_name: str | None
    teams: list[SummaryTeamRef]


class SummaryUnconfirmedRun(BaseModel):
    match_id: str
    team_id: str
    team_name: str
    round_number: int
    total_score: float
    is_disqualified: bool
    created_at: datetime | None
    entered_by_name: str | None
    entered_by_team_member: bool


class SummaryScan(BaseModel):
    id: str
    team_id: str
    team_name: str
    status: str
    file_name: str
    created_at: datetime | None


class JurorSection(BaseModel):
    unconfirmed_count: int
    unconfirmed: list[SummaryUnconfirmedRun]
    upcoming_matches: list[SummaryScheduledMatch]
    open_scans_count: int
    open_scans: list[SummaryScan]


class MentorPaper(BaseModel):
    id: str
    title: str
    status: str
    submitted_at: datetime | None
    final_score: float | None


class MentorPrintJob(BaseModel):
    id: str
    file_name: str
    status: str
    created_at: datetime | None


class MentorPrintJobs(BaseModel):
    open: int
    completed: int
    recent: list[MentorPrintJob]


class MentorScore(BaseModel):
    match_id: str
    round_number: int
    total_score: float
    is_practice: bool
    is_disqualified: bool
    confirmed: bool
    created_at: datetime | None


class MentorTeam(BaseModel):
    team_id: str
    team_name: str
    seeding_rank: int | None
    seed_score: float | None
    seeding_teams: int
    next_matches: list[SummaryScheduledMatch]
    paper: MentorPaper | None
    print_jobs: MentorPrintJobs
    latest_scores: list[MentorScore]


class MentorSection(BaseModel):
    teams: list[MentorTeam]


class PrintQueueStatus(BaseModel):
    pending: int
    active: int
    completed: int
    failed: int


class AdminSection(BaseModel):
    teams_registered: int
    teams_checked_in: int
    teams_scored: int
    teams_with_paper: int
    papers_total: int
    reviews_pending: int
    official_runs: int
    practice_runs: int
    unconfirmed_runs: int
    de_results: int
    doc_scores: int
    print_queue: PrintQueueStatus
    generated_at: datetime


class DashboardSummary(BaseModel):
    event_id: str
    juror: JurorSection | None
    mentor: MentorSection | None
    admin: AdminSection | None
    deadlines: list[DeadlineEntry]


# ── Performance ───────────────────────────────────────────────────────────────


class PerformanceRun(BaseModel):
    match_id: str
    round_number: int
    created_at: datetime | None
    total_score: float
    is_practice: bool
    is_disqualified: bool
    phase: str
    phase_name: str | None
    notes: str | None
    confirmed: bool


class PerformanceSummary(BaseModel):
    official_runs: int
    official_avg: float | None
    official_best: float | None
    practice_runs: int
    practice_avg: float | None
    practice_best: float | None
    trend_per_run: float | None


class PerformanceField(BaseModel):
    key: str
    label: str
    team_avg: float | None
    field_avg: float | None
    field_best: float | None
    delta: float | None
    share_of_best: float | None


class PerformancePhase(BoxSummary):
    phase: str


class PerformanceSeasonEvent(BaseModel):
    event_id: str
    event_name: str
    event_type: str
    starts_at: datetime | None
    practice_runs: int
    practice_avg: float | None
    official_runs: int
    official_avg: float | None
    official_best: float | None


class RankingPreview(BaseModel):
    seeding_rank: int | None
    seeding_score: float | None
    seeding_teams: int
    points_to_next_rank: float | None
    overall_rank: int | None
    overall_score: float | None
    overall_teams: int


class TeamPerformance(BaseModel):
    event_id: str
    event_name: str
    team_id: str
    team_name: str
    category: str
    include_practice: bool
    runs: list[PerformanceRun]
    summary: PerformanceSummary
    fields: list[PerformanceField]
    strengths: list[str]
    weaknesses: list[str]
    phases: list[PerformancePhase]
    season_events: list[PerformanceSeasonEvent]
    ranking_preview: RankingPreview


class PerformanceOverviewRow(BaseModel):
    team_id: str
    team_name: str
    team_number: str | None
    official_runs: int
    official_avg: float | None
    official_best: float | None
    practice_runs: int
    practice_avg: float | None
    trend_per_run: float | None
    seeding_rank: int | None
    last_run_at: datetime | None


# ── Statistics ────────────────────────────────────────────────────────────────


class StatsOverview(BaseModel):
    runs: int
    disqualified: int
    teams: int
    unconfirmed: int
    total: BoxSummary | None


class RoundDistribution(BoxSummary):
    round_number: int


class FieldDistribution(BoxSummary):
    key: str
    label: str
    zero_share: float | None = None


class HeatmapField(BaseModel):
    key: str
    label: str


class HeatmapCell(BaseModel):
    key: str
    avg: float | None
    ratio: float | None


class HeatmapTeam(BaseModel):
    team_id: str
    team_name: str
    values: list[HeatmapCell]


class Heatmap(BaseModel):
    fields: list[HeatmapField]
    teams: list[HeatmapTeam]


class TrendRound(BaseModel):
    round_number: int
    mean: float | None
    median: float | None


class TrendPoint(BaseModel):
    round_number: int
    total_score: float
    match_id: str


class TrendTeam(BaseModel):
    team_id: str
    team_name: str
    points: list[TrendPoint]
    slope: float | None


class Trend(BaseModel):
    rounds: list[TrendRound]
    teams: list[TrendTeam]


class AnomalyReason(BaseModel):
    kind: str
    message: str
    severity: str
    score: float | None


class Anomaly(BaseModel):
    match_id: str
    team_id: str
    team_name: str
    round_number: int
    total_score: float
    is_practice: bool
    scheduled_match_id: str | None
    confirmed: bool
    created_at: datetime | None
    severity: str
    reasons: list[AnomalyReason]


class EventStatistics(BaseModel):
    event_id: str
    event_name: str
    include_practice: bool
    overview: StatsOverview
    rounds: list[RoundDistribution]
    fields: list[FieldDistribution]
    heatmap: Heatmap
    trend: Trend
    anomalies: list[Anomaly]


# ── History ───────────────────────────────────────────────────────────────────


class TeamHistoryRow(BaseModel):
    team_id: str
    team_name: str
    team_number: str | None
    season_id: str
    season_name: str
    season_year: int
    event_id: str
    event_name: str
    event_type: str
    starts_at: datetime | None
    category: str
    seeding_rank: int | None
    seeding_score: float | None
    seeding_teams: int
    best_score: float | None
    official_runs: int
    official_avg: float | None
    overall_rank: int | None
    overall_score: float | None
    overall_teams: int
    de_score: float | None
    doc_score: float | None
    paper_score: float | None
    practice_runs: int | None = None
    practice_avg: float | None = None
