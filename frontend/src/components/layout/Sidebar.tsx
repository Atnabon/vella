import { NavLink } from "react-router-dom";
import { clsx } from "clsx";
import {
  LayoutDashboard,
  FileText,
  ArrowLeftRight,
  Calculator,
  ShieldCheck,
  Clock,
  BookOpen,
} from "lucide-react";

const nav = [
  { to: "/",              label: "Overview",       icon: LayoutDashboard },
  { to: "/invoices",      label: "Invoices",       icon: FileText },
  { to: "/reconcile",     label: "Reconciliation", icon: ArrowLeftRight },
  { to: "/tax",           label: "Tax Estimates",  icon: Calculator },
  { to: "/review",        label: "Review Queue",   icon: Clock },
  { to: "/ledger",        label: "Audit Ledger",   icon: BookOpen },
  { to: "/documents",     label: "Documents",      icon: ShieldCheck },
];

export default function Sidebar() {
  return (
    <aside className="flex h-screen w-56 flex-shrink-0 flex-col border-r border-slate-800 bg-slate-950">
      {/* Logo */}
      <div className="flex h-14 items-center gap-2.5 border-b border-slate-800 px-5">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-sky-500 text-xs font-bold text-white">
          FO
        </div>
        <span className="text-sm font-semibold text-slate-100">vella Ops</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <ul className="space-y-0.5">
          {nav.map(({ to, label, icon: Icon }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={to === "/"}
                className={({ isActive }) =>
                  clsx(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-sky-500/15 text-sky-400"
                      : "text-slate-400 hover:bg-slate-800 hover:text-slate-100"
                  )
                }
              >
                <Icon className="h-4 w-4 flex-shrink-0" />
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      {/* Footer */}
      <div className="border-t border-slate-800 px-5 py-3">
        <p className="text-xs text-slate-600">v0.1.0 · US SMB</p>
      </div>
    </aside>
  );
}
