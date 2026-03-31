"use client";

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageLoader } from "@/components/ui/spinner";
import { DataTable, Column } from "@/components/ui/data-table";
import { Modal } from "@/components/ui/modal";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import {
  Shield,
  Users,
  Activity,
  Settings,
  UserPlus,
  Server,
  CheckCircle,
  XCircle,
} from "lucide-react";

interface UserRecord {
  id: string;
  full_name: string;
  email: string;
  role: string;
  is_active: boolean;
  last_login_at?: string;
  created_at?: string;
  [key: string]: unknown;
}

export default function AdminPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [showInvite, setShowInvite] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteName, setInviteName] = useState("");
  const [inviteRole, setInviteRole] = useState("viewer");

  const { data: usersData, isLoading: usersLoading } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => adminApi.users().then((r) => r.data),
  });

  const { data: systemHealth } = useQuery({
    queryKey: ["system-health"],
    queryFn: () => adminApi.systemHealth().then((r) => r.data),
    retry: false,
  });

  const { data: businessRules } = useQuery({
    queryKey: ["business-rules"],
    queryFn: () => adminApi.businessRules().then((r) => r.data),
    retry: false,
  });

  const inviteMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      adminApi.inviteUser(data).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      toast.success("User invited", `Invitation sent to ${inviteEmail}`);
      setShowInvite(false);
      setInviteEmail("");
      setInviteName("");
      setInviteRole("viewer");
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail || "Failed to invite user";
      toast.error("Invite failed", msg);
    },
  });

  const users: UserRecord[] = Array.isArray(usersData?.users)
    ? usersData.users
    : Array.isArray(usersData)
    ? usersData
    : [];

  const userColumns: Column<UserRecord>[] = [
    {
      key: "full_name",
      header: "Name",
      render: (_: unknown, row: UserRecord) => (
        <div>
          <p className="font-medium text-slate-900">{row.full_name}</p>
          <p className="text-xs text-slate-500">{row.email}</p>
        </div>
      ),
    },
    {
      key: "role",
      header: "Role",
      render: (val: unknown) => (
        <Badge variant="info">{((val as string) || "viewer").replace("_", " ")}</Badge>
      ),
    },
    {
      key: "is_active",
      header: "Status",
      align: "center",
      render: (val: unknown) =>
        val ? (
          <Badge variant="success" dot>Active</Badge>
        ) : (
          <Badge variant="neutral" dot>Inactive</Badge>
        ),
    },
    {
      key: "last_login_at",
      header: "Last Login",
      render: (val: unknown) => (
        <span className="text-xs text-slate-500">{formatDate(val as string)}</span>
      ),
    },
  ];

  const healthStatus = systemHealth?.status || systemHealth?.overall;
  const services = systemHealth?.services || {};

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Administration</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            User management, system health, and business rules
          </p>
        </div>
        <Button
          icon={<UserPlus className="h-4 w-4" />}
          onClick={() => setShowInvite(true)}
        >
          Invite User
        </Button>
      </div>

      {/* System Health */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-blue-50 p-2">
              <Users className="h-4 w-4 text-blue-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-slate-900">{users.length}</p>
              <p className="text-xs text-slate-500">Users</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className={`rounded-lg p-2 ${healthStatus === "healthy" ? "bg-emerald-50" : "bg-amber-50"}`}>
              <Server className={`h-4 w-4 ${healthStatus === "healthy" ? "text-emerald-600" : "text-amber-600"}`} />
            </div>
            <div>
              <p className="text-lg font-bold capitalize text-slate-900">{healthStatus || "Unknown"}</p>
              <p className="text-xs text-slate-500">System Status</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-indigo-50 p-2">
              <Settings className="h-4 w-4 text-indigo-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-indigo-600">
                {Object.keys(businessRules || {}).length}
              </p>
              <p className="text-xs text-slate-500">Business Rules</p>
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
                {Object.values(services).filter((s: unknown) => s === "healthy" || (s as Record<string, unknown>)?.status === "healthy").length}/
                {Object.keys(services).length || "?"}
              </p>
              <p className="text-xs text-slate-500">Services Up</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Users Table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Team Members</CardTitle>
          <Badge variant="neutral">{users.length} users</Badge>
        </CardHeader>
        <div className="px-0">
          <DataTable
            columns={userColumns}
            data={users}
            loading={usersLoading}
            emptyMessage="No users found"
          />
        </div>
      </Card>

      {/* Invite User Modal */}
      <Modal
        open={showInvite}
        onClose={() => setShowInvite(false)}
        title="Invite User"
        description="Send an invitation to add a new team member"
        footer={
          <>
            <Button variant="outline" onClick={() => setShowInvite(false)}>Cancel</Button>
            <Button
              onClick={() =>
                inviteMutation.mutate({
                  email: inviteEmail,
                  full_name: inviteName,
                  role: inviteRole,
                })
              }
              loading={inviteMutation.isPending}
              disabled={!inviteEmail || !inviteName}
            >
              Send Invitation
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label="Full Name"
            placeholder="e.g. Ahmed Al Maktoum"
            value={inviteName}
            onChange={(e) => setInviteName(e.target.value)}
          />
          <Input
            label="Email Address"
            type="email"
            placeholder="ahmed@company.com"
            value={inviteEmail}
            onChange={(e) => setInviteEmail(e.target.value)}
          />
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">Role</label>
            <select
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value)}
            >
              <option value="viewer">Viewer</option>
              <option value="analyst">Analyst</option>
              <option value="collector">Collector</option>
              <option value="finance_manager">Finance Manager</option>
              <option value="tenant_admin">Tenant Admin</option>
            </select>
          </div>
        </div>
      </Modal>
    </div>
  );
}
