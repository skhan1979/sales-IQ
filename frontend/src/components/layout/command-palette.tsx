"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { Search, FileText, Users, BarChart3, Bot, Settings, ArrowRight } from "lucide-react";

interface CommandItem {
  id: string;
  label: string;
  description?: string;
  icon: React.ElementType;
  href: string;
  group: string;
}

const commands: CommandItem[] = [
  { id: "dashboard", label: "Dashboard", description: "Executive overview", icon: BarChart3, href: "/dashboard", group: "Pages" },
  { id: "customers", label: "Customers", description: "Customer portfolio", icon: Users, href: "/dashboard/customers", group: "Pages" },
  { id: "invoices", label: "Invoices", description: "Invoice management", icon: FileText, href: "/dashboard/invoices", group: "Pages" },
  { id: "payments", label: "Payments", description: "Payment tracking", icon: FileText, href: "/dashboard/payments", group: "Pages" },
  { id: "collections", label: "Collections", description: "Collection activities", icon: FileText, href: "/dashboard/collections", group: "Pages" },
  { id: "disputes", label: "Disputes", description: "Dispute management", icon: FileText, href: "/dashboard/disputes", group: "Pages" },
  { id: "chat", label: "AI Chat", description: "Ask questions about your data", icon: Bot, href: "/dashboard/chat", group: "Intelligence" },
  { id: "agents", label: "Agent Hub", description: "AI agent monitoring", icon: Bot, href: "/dashboard/agents", group: "Intelligence" },
  { id: "briefings", label: "Briefings", description: "AI executive briefings", icon: FileText, href: "/dashboard/briefings", group: "Intelligence" },
  { id: "cfo", label: "CFO Dashboard", description: "DSO, cash flow, write-offs", icon: BarChart3, href: "/dashboard/cfo", group: "Dashboards" },
  { id: "sales", label: "Sales Dashboard", description: "Churn, growth, reorders", icon: BarChart3, href: "/dashboard/sales", group: "Dashboards" },
  { id: "analytics", label: "Analytics", description: "KPI trends and reports", icon: BarChart3, href: "/dashboard/analytics", group: "Dashboards" },
  { id: "admin", label: "Admin", description: "Users, rules, system health", icon: Settings, href: "/dashboard/admin", group: "Admin" },
  { id: "demo-data", label: "Demo Data", description: "Generate or clear demo data", icon: Settings, href: "/dashboard/demo-data", group: "Admin" },
  { id: "settings", label: "Settings", description: "Profile and preferences", icon: Settings, href: "/dashboard/settings", group: "Admin" },
];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  const filtered = query
    ? commands.filter(
        (c) =>
          c.label.toLowerCase().includes(query.toLowerCase()) ||
          c.description?.toLowerCase().includes(query.toLowerCase())
      )
    : commands;

  const groups = filtered.reduce<Record<string, CommandItem[]>>((acc, item) => {
    if (!acc[item.group]) acc[item.group] = [];
    acc[item.group].push(item);
    return acc;
  }, {});

  const flatFiltered = Object.values(groups).flat();

  const navigate = useCallback(
    (href: string) => {
      setOpen(false);
      setQuery("");
      router.push(href);
    },
    [router]
  );

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
      if (e.key === "Escape") {
        setOpen(false);
        setQuery("");
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
      setSelectedIndex(0);
    }
  }, [open]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, flatFiltered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && flatFiltered[selectedIndex]) {
      navigate(flatFiltered[selectedIndex].href);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh]">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => { setOpen(false); setQuery(""); }} />
      <div className="relative w-full max-w-lg mx-4 rounded-xl bg-white shadow-2xl border border-slate-200 overflow-hidden">
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 border-b border-slate-100">
          <Search className="h-4 w-4 text-slate-400 flex-shrink-0" />
          <input
            ref={inputRef}
            type="text"
            placeholder="Search pages, features..."
            className="flex-1 bg-transparent py-3 text-sm text-slate-900 placeholder:text-slate-400 outline-none"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <kbd className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] text-slate-400">
            ESC
          </kbd>
        </div>
        {/* Results */}
        <div className="max-h-80 overflow-y-auto py-2">
          {Object.entries(groups).map(([group, items]) => (
            <div key={group}>
              <p className="px-4 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                {group}
              </p>
              {items.map((item) => {
                const globalIndex = flatFiltered.indexOf(item);
                return (
                  <button
                    key={item.id}
                    className={cn(
                      "flex w-full items-center gap-3 px-4 py-2 text-left transition-colors",
                      globalIndex === selectedIndex
                        ? "bg-blue-50 text-blue-700"
                        : "text-slate-700 hover:bg-slate-50"
                    )}
                    onClick={() => navigate(item.href)}
                    onMouseEnter={() => setSelectedIndex(globalIndex)}
                  >
                    <item.icon className="h-4 w-4 flex-shrink-0 opacity-50" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium">{item.label}</p>
                      {item.description && (
                        <p className="text-xs opacity-60 truncate">{item.description}</p>
                      )}
                    </div>
                    <ArrowRight className="h-3 w-3 opacity-30" />
                  </button>
                );
              })}
            </div>
          ))}
          {filtered.length === 0 && (
            <p className="px-4 py-6 text-center text-sm text-slate-400">
              No results for &quot;{query}&quot;
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
