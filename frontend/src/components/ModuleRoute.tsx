import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { PackageX } from "lucide-react";
import { EventLink } from "@/components/EventLink";
import { isModuleEnabled, useEventModules, type ModuleRequirement } from "@/hooks/useEventModules";

interface Props {
  module?: ModuleRequirement | readonly ModuleRequirement[];
  children: ReactNode;
}

/** Route guard: pages of a module switched off for the current event are not reachable. */
export default function ModuleRoute({ module, children }: Props) {
  const { t } = useTranslation();
  const { eventId } = useParams();
  const { data } = useEventModules(module ? eventId : undefined);
  if (isModuleEnabled(data, module)) return <>{children}</>;
  return (
    <div className="p-6">
      <div role="alert" className="card mx-auto max-w-lg p-8 text-center">
        <PackageX className="mx-auto mb-3 h-10 w-10 text-gray-400" aria-hidden="true" />
        <p className="mb-4">{t("moduleDisabled")}</p>
        <EventLink to="/dashboard" className="btn-secondary">{t("nav.dashboard")}</EventLink>
      </div>
    </div>
  );
}
