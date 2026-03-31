"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import {
  LayoutDashboard,
  Users,
  FileText,
  CreditCard,
  PhoneCall,
  AlertTriangle,
  Brain,
  MessageSquare,
  Newspaper,
  Bot,
  BarChart3,
  TrendingUp,
  ShoppingBag,
  Shield,
  Settings,
  ChevronDown,
  LogOut,
  Database,
  Bell,
  ShieldCheck,
  Upload,
  Landmark,
  Sparkles,
  Activity,
  Webhook,
} from "lucide-react";

interface NavItem {
  label: string;
  href: string;
  icon: React.ElementType;
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

const navigation: NavGroup[] = [
  {
    title: "Overview",
    items: [
      { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
      { label: "Notifications", href: "/dashboard/notifications", icon: Bell },
    ],
  },
  {
    title: "Receivables",
    items: [
      { label: "Customers", href: "/dashboard/customers", icon: Users },
      { label: "Invoices", href: "/dashboard/invoices", icon: FileText },
      { label: "Payments", href: "/dashboard/payments", icon: CreditCard },
      { label: "Collections", href: "/dashboard/collections", icon: PhoneCall },
      { label: "Disputes", href: "/dashboard/disputes", icon: AlertTriangle },
      { label: "Credit Limits", href: "/dashboard/credit-limits", icon: Landmark },
      { label: "Import", href: "/dashboard/import", icon: Upload },
    ],
  },
  {
    title: "Intelligence",
    items: [
      { label: "AI Chat", href: "/dashboard/chat", icon: MessageSquare },
      { label: "Copilot", href: "/dashboard/copilot", icon: Sparkles },
      { label: "Briefings", href: "/dashboard/briefings", icon: Newspaper },
      { label: "Agent Hub", href: "/dashboard/agents", icon: Bot },
      { label: "Data Quality", href: "/dashboard/data-quality", icon: ShieldCheck },
    ],
  },
  {
    title: "Dashboards",
    items: [
      { label: "CFO", href: "/dashboard/cfo", icon: TrendingUp },
      { label: "Sales", href: "/dashboard/sales", icon: ShoppingBag },
      { label: "Analytics", href: "/dashboard/analytics", icon: BarChart3 },
    ],
  },
  {
    title: "Administration",
    items: [
      { label: "Admin", href: "/dashboard/admin", icon: Shield },
      { label: "Performance", href: "/dashboard/performance", icon: Activity },
      { label: "Webhooks", href: "/dashboard/webhooks", icon: Webhook },
      { label: "Demo Data", href: "/dashboard/demo-data", icon: Database },
      { label: "Settings", href: "/dashboard/settings", icon: Settings },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [collapsed, setCollapsed] = React.useState<Record<string, boolean>>({});

  const toggleGroup = (title: string) => {
    setCollapsed((prev) => ({ ...prev, [title]: !prev[title] }));
  };

  const isActive = (href: string) => {
    if (href === "/dashboard") return pathname === "/dashboard";
    return pathname.startsWith(href);
  };

  return (
    <aside className="flex h-screen w-64 flex-col border-r border-slate-200 bg-white">
      {/* Brand */}
      <div className="flex h-16 items-center gap-3 border-b border-slate-100 px-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600">
          <Brain className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="text-base font-bold text-slate-900 leading-tight">
            SalesIQ
          </h1>
          <p className="text-[10px] text-slate-400 leading-tight">
            Revenue Intelligence
          </p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
        {navigation.map((group) => (
          <div key={group.title}>
            <button
              onClick={() => toggleGroup(group.title)}
              className="flex w-full items-center justify-between px-2 mb-1"
            >
              <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                {group.title}
              </span>
              <ChevronDown
                className={cn(
                  "h-3 w-3 text-slate-400 transition-transform",
                  collapsed[group.title] && "-rotate-90"
                )}
              />
            </button>
            {!collapsed[group.title] && (
              <ul className="space-y-0.5">
                {group.items.map((item) => (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={cn(
                        "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                        isActive(item.href)
                          ? "bg-blue-50 text-blue-700"
                          : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                      )}
                    >
                      <item.icon
                        className={cn(
                          "h-4 w-4 flex-shrink-0",
                          isActive(item.href)
                            ? "text-blue-600"
                            : "text-slate-400"
                        )}
                      />
                      {item.label}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </nav>

      {/* User footer */}
      <div className="border-t border-slate-100 p-3">
        <div className="flex items-center gap-3 rounded-lg px-3 py-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-100 text-blue-700 text-xs font-bold">
            {user?.full_name
              ?.split(" ")
              .map((n) => n[0])
              .join("")
              .toUpperCase() || "U"}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-900 truncate">
              {user?.full_name || "User"}
            </p>
            <p className="text-[10px] text-slate-400 truncate capitalize">
              {user?.role?.replace("_", " ") || "—"}
            </p>
          </div>
          <button
            onClick={logout}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors"
            title="Sign out"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}
