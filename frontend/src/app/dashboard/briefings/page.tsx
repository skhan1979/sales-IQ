"use client";

import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Newspaper, Plus, Mail, Clock, Eye } from "lucide-react";

interface Briefing {
  id: string;
  title?: string;
  briefing_type?: string;
  status?: string;
  created_at?: string;
  opened_at?: string;
  recipient_name?: string;
  [key: string]: unknown;
}

export default function BriefingsPage() {
  const router = useRouter();
  const { data, isLoading } = useQuery({
    queryKey: ["briefings"],
    queryFn: () => api.get("/briefings/", { params: { limit: 20 } }).then((r) => r.data),
    retry: false,
  });

  const briefings: Briefing[] = Array.isArray(data?.items)
    ? data.items
    : Array.isArray(data?.briefings)
    ? data.briefings
    : Array.isArray(data)
    ? data
    : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Briefings</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            AI-generated executive briefings and scheduled reports
          </p>
        </div>
        <Button icon={<Plus className="h-4 w-4" />}>Generate Briefing</Button>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i}>
              <CardContent className="p-5">
                <div className="space-y-3">
                  <div className="h-4 w-2/3 animate-pulse rounded bg-slate-100" />
                  <div className="h-3 w-1/2 animate-pulse rounded bg-slate-100" />
                  <div className="h-3 w-3/4 animate-pulse rounded bg-slate-100" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : briefings.length === 0 ? (
        <EmptyState
          icon={Newspaper}
          title="No briefings yet"
          description="Generate your first AI-powered executive briefing to get insights on your receivables portfolio."
          action={<Button icon={<Plus className="h-4 w-4" />}>Generate Briefing</Button>}
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {briefings.map((b) => (
            <Card
              key={b.id}
              hover
              className="cursor-pointer"
              onClick={() => router.push(`/dashboard/briefings/${b.id}`)}
            >
              <CardContent className="p-5">
                <div className="flex items-start justify-between mb-2">
                  <h3 className="text-sm font-semibold text-slate-900">
                    {b.title || `Briefing ${b.briefing_type || "Daily"}`}
                  </h3>
                  <Badge variant={b.opened_at ? "neutral" : "info"}>
                    {b.opened_at ? "Read" : "New"}
                  </Badge>
                </div>
                <p className="text-xs text-slate-500 mb-3 capitalize">
                  {(b.briefing_type || "daily").replace("_", " ")} briefing
                  {b.recipient_name ? ` for ${b.recipient_name}` : ""}
                </p>
                <div className="flex items-center gap-4 text-xs text-slate-400">
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {formatDate(b.created_at)}
                  </span>
                  {b.opened_at && (
                    <span className="flex items-center gap-1">
                      <Eye className="h-3 w-3" />
                      Viewed {formatDate(b.opened_at)}
                    </span>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
