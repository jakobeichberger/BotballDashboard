import { useEffect, useState } from "react";
import { Bot as BotIcon } from "lucide-react";
import { api } from "@/lib/api";

/** Bot images are auth-protected, so a plain <img src> can't carry the bearer
 * token — fetch the blob and render it via an object URL instead. */
export default function BotImage({
  botId,
  imageName,
  className = "",
}: {
  botId: string;
  imageName: string | null;
  className?: string;
}) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    if (!imageName) return;
    let url: string | undefined;
    let cancelled = false;
    api
      .get(`/bots/${botId}/image`, { responseType: "blob" })
      .then((r) => {
        if (cancelled) return;
        url = URL.createObjectURL(r.data);
        setSrc(url);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [botId, imageName]);

  if (!imageName || !src) {
    return (
      <div className={`flex items-center justify-center bg-gray-100 dark:bg-gray-800 ${className}`}>
        <BotIcon className="w-10 h-10 text-gray-300 dark:text-gray-600" aria-hidden="true" />
      </div>
    );
  }
  return <img src={src} alt="" className={`object-cover ${className}`} />;
}
