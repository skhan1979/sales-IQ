"use client";

import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { briefingApi } from "@/lib/api-extra";
import { formatDate } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageLoader } from "@/components/ui/spinner";
import { ArrowLeft, Clock, Eye, Newspaper, User } from "lucide-react";

interface BriefingDetail {
  id: string;
  title?: string;
  briefing_type?: string;
  status?: string;
  content?: string;
  summary?: string;
  html_content?: string;
  created_at?: string;
  opened_at?: string;
  recipient_name?: string;
  [key: string]: unknown;
}

export default function BriefingDetailPage() {
  const params = useParams();
  const router = useRouter();
  const briefingId = params.id as string;

  const { data: briefing, isLoading } = useQuery({
    queryKey: ["briefing", briefingId],
    queryFn: () =>
      briefingApi.get(briefingId).then((r) => r.data as BriefingDetail),
  });

  const { data: htmlData } = useQuery({
    queryKey: ["briefing-html", briefingId],
    queryFn: () => briefingApi.html(briefingId).then((r) => r.data),
    retry: false,
    enabled: !!briefingId,
  });

  if (isLoading) return <PageLoader />;

  if (!briefing) {
    return (
      <div className="text-center py-16">
        <Newspaper className="h-10 w-10 text-slate-300 mx-auto mb-3" />
        <p className="text-slate-500">Briefing not found</p>
        <Button
          variant="ghost"
          className="mt-4"
          onClick={() => router.push("/dashboard/briefings")}
        >
          Back to Briefings
        </Button>
      </div>
    );
  }

  const htmlContent =
    typeof htmlData === "string"
      ? htmlData
      : htmlData?.html || htmlData?.html_content || null;

  const textContent = briefing.content || briefing.summary || null;

  return (
    <div className="space-y-6">
      {/* Header with back button */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/dashboard/briefings")}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 transition-colors"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-xl font-bold text-slate-900">
              {briefing.title ||
                `${(briefing.briefing_type || "Daily").replace("_", " ")} Briefing`}
            </h1>
            <p className="text-sm text-slate-500 mt-0.5 capitalize">
              {(briefing.briefing_type || "daily").replace("_", " ")} briefing
            </p>
          </div>
        </div>
        <Badge variant={briefing.opened_at ? "neutral" : "info"}>
          {briefing.opened_at ? "Read" : "New"}
        </Badge>
      </div>

      {/* Metadata */}
      <Card>
        <CardContent className="p-5">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-slate-600">
            <span className="flex items-center gap-1.5">
              <Clock className="h-4 w-4 text-slate-400" />
              Created {formatDate(briefing.created_at)}
            </span>
            {briefing.recipient_name && (
              <span className="flex items-center gap-1.5">
                <User className="h-4 w-4 text-slate-400" />
                {briefing.recipient_name}
              </span>
            )}
            {briefing.opened_at && (
              <span className="flex items-center gap-1.5">
                <Eye className="h-4 w-4 text-slate-400" />
                Viewed {formatDate(briefing.opened_at)}
              </span>
            )}
            <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600 capitalize">
              {(briefing.briefing_type || "daily").replace("_", " ")}
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Briefing Content */}
      <Card>
        <CardHeader>
          <CardTitle>Briefing Content</CardTitle>
        </CardHeader>
        <CardContent>
          {htmlContent ? (
            <div
              className="prose prose-slate max-w-none prose-headings:text-slate-900 prose-p:text-slate-700 prose-a:text-blue-600 prose-strong:text-slate-900 prose-li:text-slate-700 prose-table:text-sm"
              dangerouslySetInnerHTML={{ __html: htmlContent }}
            />
          ) : textContent ? (
            <div className="space-y-4">
              {textContent.split("\n\n").map((para: string, i: number) => (
                <p key={i} className="text-sm text-slate-700 leading-relaxed">
                  {para}
                </p>
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-8 text-center">
              <Newspaper className="h-8 w-8 text-slate-300 mx-auto mb-2" />
              <p className="text-sm text-slate-400">
                No content available for this briefing yet.
              </p>
              <p className="text-xs text-slate-400 mt-1">
                Briefing content is generated when the AI agent runs.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
