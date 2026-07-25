import { FileText, Clock, CheckCircle2 } from "lucide-react";
import { StatGrid, SectionCard, ReviewQueue, AnnouncementsList } from "./widgets";

interface Props {
  papers?: Array<any>;
  season?: any;
  announcements?: Array<any>;
}

/** Statuses that still need reviewer attention. */
const OPEN_STATUSES = new Set(["submitted", "under_review", "revision_requested"]);

export default function ReviewerDashboard({ papers, season, announcements }: Props) {
  const all = papers ?? [];
  const queue = all.filter((p) => OPEN_STATUSES.has(p.status));
  const done = all.filter((p) => p.status === "accepted" || p.status === "rejected");

  const statItems = [
    { label: "Zu begutachten", value: queue.length, icon: Clock },
    { label: "Abgeschlossen", value: done.length, icon: CheckCircle2 },
    { label: "Paper gesamt", value: all.length, icon: FileText },
  ];

  const deadline = season?.paper_submission_deadline;

  return (
    <div data-testid="reviewer-dashboard">
      <StatGrid items={statItems} ariaLabel="Review-Kennzahlen" />

      {deadline && (
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
          Einreichungsfrist Paper:{" "}
          <time dateTime={deadline} className="font-medium">
            {new Date(deadline).toLocaleDateString("de-DE")}
          </time>
        </p>
      )}

      <SectionCard title="Review-Warteschlange" id="reviewer-queue">
        <ReviewQueue papers={queue} />
      </SectionCard>

      <SectionCard title="Ankündigungen" id="reviewer-announcements">
        <AnnouncementsList announcements={announcements ?? []} />
      </SectionCard>
    </div>
  );
}
