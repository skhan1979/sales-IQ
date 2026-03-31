"use client";

import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { notificationApi } from "@/lib/api";
import { formatDateRelative } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { useToast } from "@/components/ui/toast";
import {
  Bell,
  CheckCheck,
  AlertTriangle,
  TrendingUp,
  CreditCard,
  Users,
  FileText,
  Info,
} from "lucide-react";

interface Notification {
  id: string;
  title?: string;
  message?: string;
  category?: string;
  severity?: string;
  is_read?: boolean;
  created_at?: string;
  entity_type?: string;
  entity_id?: string;
  [key: string]: unknown;
}

const categoryIcons: Record<string, React.ElementType> = {
  payment: CreditCard,
  invoice: FileText,
  customer: Users,
  collection: TrendingUp,
  dispute: AlertTriangle,
  credit: CreditCard,
  system: Info,
};

export default function NotificationsPage() {
  const queryClient = useQueryClient();
  const toast = useToast();

  const { data, isLoading } = useQuery({
    queryKey: ["notifications"],
    queryFn: () =>
      notificationApi.inbox({ limit: 50 }).then((r) => r.data),
    retry: false,
  });

  const markAllMutation = useMutation({
    mutationFn: () => notificationApi.markAllRead().then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
      toast.success("All marked as read");
    },
  });

  const markReadMutation = useMutation({
    mutationFn: (ids: string[]) =>
      notificationApi.markRead(ids).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  const notifications: Notification[] = Array.isArray(data?.items)
    ? data.items
    : Array.isArray(data?.notifications)
    ? data.notifications
    : Array.isArray(data)
    ? data
    : [];

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Notifications</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {unreadCount > 0
              ? `${unreadCount} unread notification${unreadCount > 1 ? "s" : ""}`
              : "You're all caught up"}
          </p>
        </div>
        {unreadCount > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => markAllMutation.mutate()}
            loading={markAllMutation.isPending}
            icon={<CheckCheck className="h-3.5 w-3.5" />}
          >
            Mark all read
          </Button>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardContent className="p-4">
                <div className="h-4 w-2/3 animate-pulse rounded bg-slate-100 mb-2" />
                <div className="h-3 w-1/2 animate-pulse rounded bg-slate-100" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : notifications.length === 0 ? (
        <EmptyState
          icon={Bell}
          title="No notifications"
          description="You'll see alerts here when important events occur — overdue invoices, SLA breaches, credit holds, and more."
        />
      ) : (
        <div className="space-y-2">
          {notifications.map((n) => {
            const Icon = categoryIcons[n.category || "system"] || Bell;
            return (
              <Card
                key={n.id}
                className={n.is_read ? "opacity-60" : ""}
                hover
              >
                <CardContent className="p-4">
                  <div className="flex items-start gap-3">
                    <div
                      className={`rounded-lg p-2 flex-shrink-0 ${
                        n.severity === "critical"
                          ? "bg-red-50 text-red-600"
                          : n.severity === "warning"
                          ? "bg-amber-50 text-amber-600"
                          : "bg-blue-50 text-blue-600"
                      }`}
                    >
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium text-slate-900">
                          {n.title || "Notification"}
                        </p>
                        {!n.is_read && (
                          <span className="h-2 w-2 rounded-full bg-blue-500 flex-shrink-0" />
                        )}
                      </div>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {n.message || "—"}
                      </p>
                      <p className="text-[10px] text-slate-400 mt-1">
                        {formatDateRelative(n.created_at)}
                      </p>
                    </div>
                    {!n.is_read && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          markReadMutation.mutate([n.id]);
                        }}
                        className="text-xs text-blue-600 hover:underline flex-shrink-0"
                      >
                        Mark read
                      </button>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
