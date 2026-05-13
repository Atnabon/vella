import { type LucideIcon } from "lucide-react";

type Props = { icon: LucideIcon; title: string; description?: string };

export default function EmptyState({ icon: Icon, title, description }: Props) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="mb-4 rounded-2xl bg-slate-800 p-5">
        <Icon className="h-8 w-8 text-slate-500" />
      </div>
      <p className="text-base font-medium text-slate-300">{title}</p>
      {description && <p className="mt-1 max-w-xs text-sm text-slate-500">{description}</p>}
    </div>
  );
}
