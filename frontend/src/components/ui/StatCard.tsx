import { type LucideIcon } from "lucide-react";
import { clsx } from "clsx";

type Props = {
  label: string;
  value: string | number;
  sub?: string;
  icon: LucideIcon;
  trend?: "up" | "down" | "neutral";
  accent?: "blue" | "green" | "yellow" | "red";
};

const accentMap = {
  blue:   { bg: "bg-sky-500/10",     icon: "text-sky-400",     border: "border-sky-500/20" },
  green:  { bg: "bg-emerald-500/10", icon: "text-emerald-400", border: "border-emerald-500/20" },
  yellow: { bg: "bg-amber-500/10",   icon: "text-amber-400",   border: "border-amber-500/20" },
  red:    { bg: "bg-red-500/10",     icon: "text-red-400",     border: "border-red-500/20" },
};

export default function StatCard({ label, value, sub, icon: Icon, accent = "blue" }: Props) {
  const a = accentMap[accent];
  return (
    <div className={clsx("card flex items-start gap-4 border", a.border)}>
      <div className={clsx("mt-0.5 rounded-lg p-2.5", a.bg)}>
        <Icon className={clsx("h-5 w-5", a.icon)} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium uppercase tracking-wider text-slate-500">{label}</p>
        <p className="mt-1 truncate text-2xl font-semibold text-slate-100">{value}</p>
        {sub && <p className="mt-0.5 text-xs text-slate-500">{sub}</p>}
      </div>
    </div>
  );
}
