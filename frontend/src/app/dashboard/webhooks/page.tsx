"use client";

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { DataTable, Column } from "@/components/ui/data-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/ui/empty-state";
import { useToast } from "@/components/ui/toast";
import {
  Webhook,
  Plus,
  Trash2,
  Send,
  CheckCircle,
  XCircle,
  RefreshCw,
} from "lucide-react";

interface WebhookSub {
  id: string;
  url: string;
  event_types?: string[];
  is_active?: boolean;
  secret?: string;
  created_at?: string;
  last_triggered_at?: string;
  [key: string]: unknown;
}

export default function WebhooksPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newUrl, setNewUrl] = useState("");
  const [newEvents, setNewEvents] = useState("invoice.created,payment.received");

  const { data, isLoading } = useQuery({
    queryKey: ["webhooks"],
    queryFn: () => api.get("/integrations/webhooks").then((r) => r.data),
    retry: false,
  });

  const { data: eventTypes } = useQuery({
    queryKey: ["event-types"],
    queryFn: () => api.get("/integrations/event-types").then((r) => r.data),
    retry: false,
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api.post("/integrations/webhooks", payload).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["webhooks"] });
      toast.success("Webhook created");
      setShowCreate(false);
      setNewUrl("");
      setNewName("");
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail || "Failed to create webhook";
      toast.error("Failed", msg);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      api.delete(`/integrations/webhooks/${id}`).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["webhooks"] });
      toast.success("Webhook deleted");
    },
  });

  const testMutation = useMutation({
    mutationFn: (id: string) =>
      api.post(`/integrations/webhooks/${id}/test`).then((r) => r.data),
    onSuccess: () => toast.success("Test event sent"),
    onError: () => toast.error("Test failed"),
  });

  const webhooks: WebhookSub[] = Array.isArray(data?.items)
    ? data.items
    : Array.isArray(data?.webhooks)
    ? data.webhooks
    : Array.isArray(data)
    ? data
    : [];

  const availableEvents = Array.isArray(eventTypes?.event_types)
    ? eventTypes.event_types
    : Array.isArray(eventTypes)
    ? eventTypes
    : [];

  const columns: Column<WebhookSub>[] = [
    {
      key: "url",
      header: "Endpoint URL",
      render: (val: unknown) => (
        <span className="text-sm font-mono text-slate-700 truncate block max-w-xs">
          {(val as string) || "—"}
        </span>
      ),
    },
    {
      key: "event_types",
      header: "Events",
      render: (val: unknown) => (
        <div className="flex flex-wrap gap-1">
          {((val as string[]) || []).slice(0, 3).map((e) => (
            <Badge key={e} variant="neutral">{e}</Badge>
          ))}
          {((val as string[]) || []).length > 3 && (
            <Badge variant="neutral">+{((val as string[]) || []).length - 3}</Badge>
          )}
        </div>
      ),
    },
    {
      key: "is_active",
      header: "Status",
      align: "center",
      render: (val: unknown) =>
        val !== false ? (
          <Badge variant="success" dot>Active</Badge>
        ) : (
          <Badge variant="neutral" dot>Inactive</Badge>
        ),
    },
    {
      key: "last_triggered_at",
      header: "Last Triggered",
      render: (val: unknown) => (
        <span className="text-xs text-slate-500">{formatDate(val as string)}</span>
      ),
    },
    {
      key: "id",
      header: "Actions",
      align: "center",
      render: (_: unknown, row: WebhookSub) => (
        <div className="flex items-center gap-1 justify-center">
          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => { e.stopPropagation(); testMutation.mutate(row.id); }}
            icon={<Send className="h-3.5 w-3.5" />}
          >
            Test
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              if (confirm("Delete this webhook?")) deleteMutation.mutate(row.id);
            }}
            icon={<Trash2 className="h-3.5 w-3.5 text-red-500" />}
          />
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Webhooks</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Configure outbound webhooks for real-time event notifications
          </p>
        </div>
        <Button icon={<Plus className="h-4 w-4" />} onClick={() => setShowCreate(true)}>
          Add Webhook
        </Button>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-blue-50 p-2"><Webhook className="h-4 w-4 text-blue-600" /></div>
            <div>
              <p className="text-lg font-bold text-blue-600">{webhooks.length}</p>
              <p className="text-xs text-slate-500">Total Webhooks</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-emerald-50 p-2"><CheckCircle className="h-4 w-4 text-emerald-600" /></div>
            <div>
              <p className="text-lg font-bold text-emerald-600">
                {webhooks.filter((w) => w.is_active !== false).length}
              </p>
              <p className="text-xs text-slate-500">Active</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-indigo-50 p-2"><RefreshCw className="h-4 w-4 text-indigo-600" /></div>
            <div>
              <p className="text-lg font-bold text-indigo-600">{availableEvents.length}</p>
              <p className="text-xs text-slate-500">Event Types</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {!isLoading && webhooks.length === 0 ? (
        <EmptyState
          icon={Webhook}
          title="No webhooks configured"
          description="Add a webhook to receive real-time notifications when events occur in SalesIQ."
          action={<Button icon={<Plus className="h-4 w-4" />} onClick={() => setShowCreate(true)}>Add Webhook</Button>}
        />
      ) : (
        <DataTable columns={columns} data={webhooks} loading={isLoading} />
      )}

      {/* Create Modal */}
      <Modal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        title="Add Webhook"
        description="Configure an endpoint to receive event notifications"
        footer={
          <>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button
              onClick={() =>
                createMutation.mutate({
                  name: newName || newUrl,
                  url: newUrl,
                  events: newEvents.split(",").map((e) => e.trim()).filter(Boolean),
                })
              }
              loading={createMutation.isPending}
              disabled={!newUrl}
            >
              Create Webhook
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label="Webhook Name"
            placeholder="e.g. My ERP Integration"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <Input
            label="Endpoint URL"
            placeholder="https://your-app.com/webhooks/salesiq"
            value={newUrl}
            onChange={(e) => setNewUrl(e.target.value)}
          />
          <Input
            label="Event Types (comma-separated)"
            placeholder="invoice.created, payment.received"
            value={newEvents}
            onChange={(e) => setNewEvents(e.target.value)}
          />
          {availableEvents.length > 0 && (
            <div>
              <p className="text-xs text-slate-500 mb-2">Available events:</p>
              <div className="flex flex-wrap gap-1">
                {availableEvents.slice(0, 12).map((e: string) => (
                  <button
                    key={e}
                    className="text-[10px] rounded-full border border-slate-200 px-2 py-0.5 text-slate-500 hover:bg-slate-50"
                    onClick={() => {
                      const events = newEvents ? newEvents.split(",").map((s) => s.trim()) : [];
                      if (!events.includes(e)) setNewEvents([...events, e].join(", "));
                    }}
                  >
                    {e}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
}
