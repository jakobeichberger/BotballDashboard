import { FileText, Clock, CheckCircle2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatDate } from "@/i18n/format";
import type { DashboardSummary } from "@/api/analytics";
import { UpcomingDeadlines } from "./roleSections";
import { StatGrid, SectionCard, ReviewQueue, AnnouncementsList } from "./widgets";
import { OPEN_REVIEW_STATUSES } from "@/modules/papers/paperMeta";

interface Props {
  papers?: Array<any>;
  season?: any;
  announcements?: Array<any>;
  summary?: DashboardSummary;
}

/** Final verdicts: nothing left for reviewers to do. */
const DONE_STATUSES = new Set(["accepted", "rejected", "disqualified_ai"]);

export default function ReviewerDashboard({ papers, season, announcements, summary }: Props) {
  const { t } = useTranslation("dashboard");
  const all = papers ?? [];
  // A paper sent back for revision waits for the team, not the reviewer; it
  // re-enters the queue as "resubmitted".
  const queue = all.filter((p) => OPEN_REVIEW_STATUSES.has(p.status));
  const done = all.filter((p) => DONE_STATUSES.has(p.status));

  const statItems = [
    { label: t("stat.toReview"), value: queue.length, icon: Clock },
    { label: t("stat.completed"), value: done.length, icon: CheckCircle2 },
    { label: t("stat.papersTotal"), value: all.length, icon: FileText },
  ];

  const deadline = season?.paper_submission_deadline;

  return (
    <div data-testid="reviewer-dashboard">
      <StatGrid items={statItems} ariaLabel={t("stat.reviewLabel")} />

      {deadline && (
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
          {t("paperDeadline")}{" "}
          <time dateTime={deadline} className="font-medium">
            {formatDate(deadline)}
          </time>
        </p>
      )}

      <SectionCard title={t("reviewQueue")} id="reviewer-queue">
        <ReviewQueue papers={queue} />
      </SectionCard>

      {summary && <UpcomingDeadlines deadlines={summary.deadlines} />}

      <SectionCard title={t("announcements")} id="reviewer-announcements">
        <AnnouncementsList announcements={announcements ?? []} />
      </SectionCard>
    </div>
  );
}
