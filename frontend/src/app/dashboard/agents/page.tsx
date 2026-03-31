"use client";

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { agentHubApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageLoader } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import { Bot, Play, Pause, Activity, Clock, CheckCircle, AlertCircle } from "lucide-react";

interface Agent {
  name: string;
  agent_name?: string;
  display_name?: string;
  description?: string;
  status?: string;
  last_run?: string;
  success_rate?: number;
  total_runs?: number;
  avg_duration_ms?: number;
  [key: string]: unknown;
}

export default function AgentsPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [triggeringAgent, setTriggeringAgent] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["agents"],
    queryFn: () => agentHubApi.agents().then((r) => r.data),
    retry: false,
  });

  const { data: dashboard } = useQuery({
    queryKey: ["agent-dashboard"],
    queryFn: () => agentHubApi.dashboard().then((r) => r.data),
    retry: false,
  });

  const triggerMutation = useMutation({
    mutationFn: (agentName: string) => agentHubApi.trigger(agentName),
    onMutate: (name) => setTriggeringAgent(name),
    onSuccess: (response) => {
      const msg = response?.data?.message || "Agent triggered successfully";
      toast.success("Agent triggered", msg);
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Failed to trigger agent. Check agent status and try again.";
      toast.error("Trigger failed", detail);
    },
    onSettled: () => {
      setTriggeringAgent(null);
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      queryClient.invalidateQueries({ queryKey: ["agent-dashboard"] });
    },
  });

  if (isLoading && !isError) return <PageLoader />;

  const agents: Agent[] = Array.isArray(data?.agents)
    ? data.agents
    : Array.isArray(data)
    ? data
    : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Agent Hub</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Monitor and control your AI agents
        </p>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-blue-50 p-2">
              <Bot className="h-4 w-4 text-blue-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-slate-900">{agents.length}</p>
              <p className="text-xs text-slate-500">Total Agents</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-emerald-50 p-2">
              <Activity className="h-4 w-4 text-emerald-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-emerald-600">
                {agents.filter((a) => a.status === "active" || a.status === "idle").length}
              </p>
              <p className="text-xs text-slate-500">Active</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-indigo-50 p-2">
              <CheckCircle className="h-4 w-4 text-indigo-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-indigo-600">
                {dashboard?.total_runs || 0}
              </p>
              <p className="text-xs text-slate-500">Total Runs</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-amber-50 p-2">
              <Clock className="h-4 w-4 text-amber-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-amber-600">
                {dashboard?.avg_duration ? `${dashboard.avg_duration}ms` : "—"}
              </p>
              <p className="text-xs text-slate-500">Avg Duration</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Agent Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {agents.map((agent) => (
          <Card key={agent.agent_name || agent.name} hover>
            <CardContent className="p-5">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 p-2.5">
                    <Bot className="h-5 w-5 text-white" />
                  </div>
                  <div>
                    <p className="font-semibold text-slate-900">
                      {agent.display_name || (agent.agent_name || agent.name || "").replace(/_/g, " ")}
                    </p>
                    <p className="text-xs text-slate-500 capitalize">
                      {agent.status || "idle"}
                    </p>
                  </div>
                </div>
                <Badge
                  variant={
                    agent.status === "active"
                      ? "success"
                      : agent.status === "paused"
                      ? "warning"
                      : agent.status === "error"
                      ? "danger"
                      : "neutral"
                  }
                  dot
                >
                  {agent.status || "idle"}
                </Badge>
              </div>
              <p className="text-xs text-slate-500 mb-4 line-clamp-2">
                {agent.description || "AI-powered automation agent"}
              </p>
              <div className="grid grid-cols-3 gap-2 mb-4">
                <div className="text-center rounded-lg bg-slate-50 py-2">
                  <p className="text-sm font-bold text-slate-900">
                    {agent.total_runs || 0}
                  </p>
                  <p className="text-[10px] text-slate-400">Runs</p>
                </div>
                <div className="text-center rounded-lg bg-slate-50 py-2">
                  <p className="text-sm font-bold text-slate-900">
                    {agent.success_rate != null
                      ? `${agent.success_rate}%`
                      : "—"}
                  </p>
                  <p className="text-[10px] text-slate-400">Success</p>
                </div>
                <div className="text-center rounded-lg bg-slate-50 py-2">
                  <p className="text-sm font-bold text-slate-900">
                    {agent.avg_duration_ms
                      ? `${agent.avg_duration_ms}ms`
                      : "—"}
                  </p>
                  <p className="text-[10px] text-slate-400">Avg Time</p>
                </div>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="flex-1"
                  icon={<Play className="h-3 w-3" />}
                  disabled={triggeringAgent === (agent.agent_name || agent.name)}
                  onClick={() => triggerMutation.mutate(agent.agent_name || agent.name)}
                >
                  {triggeringAgent === (agent.agent_name || agent.name) ? "Running..." : "Trigger"}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  icon={<Pause className="h-3 w-3" />}
                />
              </div>
            </CardContent>
          </Card>
        ))}
        {agents.length === 0 && (
          <div className="col-span-full text-center py-12 text-sm text-slate-400">
            No agents registered yet. Agents will appear once configured in the backend.
          </div>
        )}
      </div>
    </div>
  );
}
