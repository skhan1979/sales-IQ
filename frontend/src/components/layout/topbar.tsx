"use client";

import React from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { useWebSocket } from "@/lib/websocket";
import { Bell, Search, Globe, LogOut, Wifi, WifiOff } from "lucide-react";

export function Topbar() {
  const { user, logout } = useAuth();
  const { unreadCount, isConnected, resetUnread } = useWebSocket();

  return (
    <header className="flex h-14 items-center justify-between border-b border-slate-200 bg-white px-6">
      {/* Search - triggers Command Palette */}
      <button
        onClick={() =>
          window.dispatchEvent(
            new KeyboardEvent("keydown", { key: "k", metaKey: true })
          )
        }
        className="flex items-center gap-2 rounded-lg bg-slate-100 px-3 py-1.5 w-80 text-left hover:bg-slate-200/70 transition-colors"
      >
        <Search className="h-4 w-4 text-slate-400" />
        <span className="text-sm text-slate-400 flex-1">
          Search customers, invoices...
        </span>
        <kbd className="hidden sm:inline-flex items-center rounded border border-slate-300 bg-white px-1.5 py-0.5 text-[10px] font-medium text-slate-400">
          Ctrl+K
        </kbd>
      </button>

      {/* Right section */}
      <div className="flex items-center gap-1">
        {/* Connection indicator */}
        <div
          className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs"
          title={isConnected ? "Real-time connected" : "Real-time disconnected"}
        >
          {isConnected ? (
            <Wifi className="h-3.5 w-3.5 text-emerald-500" />
          ) : (
            <WifiOff className="h-3.5 w-3.5 text-slate-300" />
          )}
        </div>

        {/* Language toggle */}
        <button
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100 transition-colors"
          title="Switch language"
        >
          <Globe className="h-4 w-4" />
          <span className="text-xs font-medium">EN</span>
        </button>

        {/* Notifications */}
        <Link
          href="/dashboard/notifications"
          onClick={resetUnread}
          className="relative rounded-lg p-2 text-slate-600 hover:bg-slate-100 transition-colors"
          title="Notifications"
        >
          <Bell className="h-4 w-4" />
          {unreadCount > 0 ? (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white animate-in zoom-in duration-200">
              {unreadCount > 99 ? "99+" : unreadCount}
            </span>
          ) : (
            <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-red-500" />
          )}
        </Link>

        {/* User menu */}
        <Link
          href="/dashboard/settings"
          className="ml-2 flex items-center gap-2 rounded-lg px-2 py-1 hover:bg-slate-50 cursor-pointer transition-colors"
        >
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-600 text-white text-xs font-bold">
            {user?.full_name
              ?.split(" ")
              .map((n: string) => n[0])
              .join("")
              .toUpperCase() || "U"}
          </div>
          <div className="hidden sm:block">
            <p className="text-xs font-medium text-slate-700 leading-tight">
              {user?.full_name || "User"}
            </p>
            <p className="text-[10px] text-slate-400 leading-tight capitalize">
              {user?.role?.replace("_", " ") || "—"}
            </p>
          </div>
        </Link>

        {/* Logout */}
        <button
          onClick={logout}
          className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600 transition-colors"
          title="Sign out"
        >
          <LogOut className="h-4 w-4" />
        </button>
      </div>
    </header>
  );
}
