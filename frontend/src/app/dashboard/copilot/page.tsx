"use client";

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { PageLoader } from "@/components/ui/spinner";
import {
  MessageSquare,
  Mail,
  Phone,
  Send,
  Sparkles,
  Clock,
  CheckCircle,
  AlertTriangle,
  HandshakeIcon,
} from "lucide-react";

export default function CollectionsCopilotPage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [draftCustomerId, setDraftCustomerId] = useState("");
  const [draftChannel, setDraftChannel] = useState("email");
  const [draftTone, setDraftTone] = useState("professional");
  const [generatedDraft, setGeneratedDraft] = useState<Record<string, unknown> | null>(null);

  const { data: ptpDashboard } = useQuery({
    queryKey: ["ptp-dashboard"],
    queryFn: () => api.get("/collections-copilot/ptp/dashboard").then((r) => r.data),
    retry: false,
  });

  const { data: disputeAging } = useQuery({
    queryKey: ["dispute-aging"],
    queryFn: () => api.get("/collections-copilot/disputes/aging").then((r) => r.data),
    retry: false,
  });

  const { data: messages } = useQuery({
    queryKey: ["copilot-messages"],
    queryFn: () => api.get("/collections-copilot/messages", { params: { limit: 10 } }).then((r) => r.data),
    retry: false,
  });

  const { data: customers } = useQuery({
    queryKey: ["customers-select-copilot"],
    queryFn: () => api.get("/customers/", { params: { limit: 50 } }).then((r) => r.data),
    retry: false,
  });

  const draftMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      api.post("/collections-copilot/draft", data).then((r) => r.data),
    onSuccess: (data) => {
      setGeneratedDraft(data);
      toast.success("Draft generated", "AI has composed a collection message");
    },
    onError: () => toast.error("Draft failed", "Could not generate message"),
  });

  const customerList = Array.isArray(customers?.items)
    ? customers.items
    : Array.isArray(customers?.customers)
    ? customers.customers
    : Array.isArray(customers)
    ? customers
    : [];

  const messageList = Array.isArray(messages?.messages)
    ? messages.messages
    : Array.isArray(messages)
    ? messages
    : [];

  const ptp = ptpDashboard || {};
  const dispute = disputeAging || {};

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Collections Copilot</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          AI-assisted collection messages, promise-to-pay tracking, and escalation management
        </p>
      </div>

      {/* PTP + Dispute summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-blue-50 p-2"><HandshakeIcon className="h-4 w-4 text-blue-600" /></div>
            <div>
              <p className="text-lg font-bold text-blue-600">{ptp.total || 0}</p>
              <p className="text-xs text-slate-500">Total PTPs</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-emerald-50 p-2"><CheckCircle className="h-4 w-4 text-emerald-600" /></div>
            <div>
              <p className="text-lg font-bold text-emerald-600">{ptp.fulfilled || 0}</p>
              <p className="text-xs text-slate-500">PTP Fulfilled</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-red-50 p-2"><AlertTriangle className="h-4 w-4 text-red-600" /></div>
            <div>
              <p className="text-lg font-bold text-red-600">{ptp.broken || 0}</p>
              <p className="text-xs text-slate-500">PTP Broken</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-indigo-50 p-2"><Sparkles className="h-4 w-4 text-indigo-600" /></div>
            <div>
              <p className="text-lg font-bold text-indigo-600">{messageList.length}</p>
              <p className="text-xs text-slate-500">Messages Sent</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* AI Draft Generator */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-indigo-600" />
              AI Message Drafter
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Customer</label>
              <select
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                value={draftCustomerId}
                onChange={(e) => setDraftCustomerId(e.target.value)}
              >
                <option value="">Select customer...</option>
                {customerList.map((c: { id: string; name: string }) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Channel</label>
                <select
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                  value={draftChannel}
                  onChange={(e) => setDraftChannel(e.target.value)}
                >
                  <option value="email">Email</option>
                  <option value="whatsapp">WhatsApp</option>
                  <option value="sms">SMS</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Tone</label>
                <select
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                  value={draftTone}
                  onChange={(e) => setDraftTone(e.target.value)}
                >
                  <option value="professional">Professional</option>
                  <option value="friendly">Friendly</option>
                  <option value="firm">Firm</option>
                  <option value="final_notice">Final Notice</option>
                </select>
              </div>
            </div>
            <Button
              className="w-full"
              onClick={() =>
                draftMutation.mutate({
                  customer_id: draftCustomerId,
                  channel: draftChannel,
                  tone: draftTone,
                })
              }
              loading={draftMutation.isPending}
              disabled={!draftCustomerId}
              icon={<Sparkles className="h-4 w-4" />}
            >
              Generate Draft
            </Button>
            {generatedDraft && (
              <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-4">
                <p className="text-xs font-medium text-indigo-700 mb-2">Generated Draft:</p>
                <p className="text-sm text-indigo-900 whitespace-pre-wrap">
                  {(generatedDraft.subject ? `Subject: ${generatedDraft.subject}\n\n` : "") +
                    ((generatedDraft.body as string) || (generatedDraft.message as string) || (generatedDraft.content as string) || "Message generated")}
                </p>
                <div className="flex gap-2 mt-3">
                  <Button size="sm" icon={<Send className="h-3 w-3" />}>Send</Button>
                  <Button size="sm" variant="outline">Edit & Send</Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent Messages */}
        <Card>
          <CardHeader>
            <CardTitle>Recent Messages</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {messageList.length > 0 ? (
              <div className="divide-y divide-slate-100">
                {messageList.slice(0, 8).map((msg: Record<string, unknown>, i: number) => {
                  const channel = (msg.channel as string) || "email";
                  const ChannelIcon = channel === "email" ? Mail : channel === "whatsapp" ? MessageSquare : Phone;
                  return (
                    <div key={i} className="flex items-center gap-3 px-6 py-3">
                      <ChannelIcon className="h-4 w-4 text-slate-400 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-900 truncate">
                          {(msg.customer_name as string) || "Customer"}
                        </p>
                        <p className="text-xs text-slate-500 truncate">
                          {(msg.subject as string) || (msg.snippet as string) || channel}
                        </p>
                      </div>
                      <span className="text-xs text-slate-400">{formatDate(msg.sent_at as string)}</span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="px-6 py-8 text-center text-sm text-slate-400">
                No messages sent yet. Use the AI drafter to compose your first collection message.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
