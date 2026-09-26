import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";
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
        <PackageX className="mx-auto mb-3 h-10 w-10 text-leise" aria-hidden="true" />
        <h1 className="mb-4 font-ui text-lg font-semibold text-fg">{t("moduleDisabled")}</h1>
        <EventLink to="/dashboard" className="btn-secondary">{t("nav.dashboard")}</EventLink>
      </div>
    </div>
  );
}
