"use client";

// FE-52: admins and roles (Web App Design A11), super admin only. A grant, change or revoke
// signs the person out on their next request (A12); the last super admin can't be revoked or
// demoted (the server says 409 last_super_admin and the trigger keep_a_super_admin agrees).
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { InfoIcon } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { DisplayHeading } from "@/components/display";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { DataTable } from "@/components/data-table";
import { ErrorAlert } from "@/components/error-alert";
import { SelectField, TextField } from "@/components/form-fields";
import { RequireRole } from "@/components/require-role";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FieldGroup } from "@/components/ui/field";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { formatDateTime } from "@/lib/format";
import { applyServerErrors } from "@/lib/forms";
import { queryKeys } from "@/lib/query-keys";
import { useSession } from "@/lib/session";

type RoleRow = components["schemas"]["RoleRow"];

const ROLE_LABELS: Record<string, string> = { SUPER_ADMIN: "Super admin", ADMIN: "Admin" };
const LAST_SUPER_ADMIN = "This is the last super admin. Make someone else a super admin first.";

const roleSchema = z.object({
  email: z.string().trim().toLowerCase().email("Enter an email address"),
  role: z.enum(["ADMIN", "SUPER_ADMIN"], { message: "Choose a role" }),
});
type RoleForm = z.infer<typeof roleSchema>;

export default function RolesPage() {
  return (
    <RequireRole role="super_admin">
      <Roles />
    </RequireRole>
  );
}

function Roles() {
  const session = useSession();
  const me = session.data?.user?.email;
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<RoleRow | "new" | null>(null);

  const roles = useQuery({
    queryKey: queryKeys.admin.roles,
    queryFn: async () => (await api.GET("/api/admin/roles")).data!,
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.admin.roles });

  const revoke = useMutation({
    mutationFn: async (row: RoleRow) =>
      api.DELETE("/api/admin/roles/{email}", { params: { path: { email: row.email } } }),
    onSuccess: (_, row) => {
      toast.success(`${row.email} is no longer an admin`);
      // Revoking yourself ends your own session: the guard sends you to sign in.
      if (row.email === me) void queryClient.invalidateQueries({ queryKey: queryKeys.session });
      else void refresh();
    },
    onError: (error) => toast.error(error.message), // 409 last_super_admin
  });

  const actions = (r: RoleRow) => (
    <div className="flex gap-2">
      <Button variant="outline" size="sm" onClick={() => setEditing(r)}>
        Change role
      </Button>
      {r.last_super_admin ? (
        <Tooltip>
          <TooltipTrigger render={<span tabIndex={0} />}>
            <Button variant="destructive" size="sm" disabled>
              Revoke
            </Button>
          </TooltipTrigger>
          <TooltipContent>{LAST_SUPER_ADMIN}</TooltipContent>
        </Tooltip>
      ) : (
        <ConfirmDialog
          trigger={<Button variant="destructive" size="sm" />}
          title={`Revoke ${r.email}?`}
          description="They will be signed out immediately and lose access to the admin pages."
          confirmLabel="Revoke"
          onConfirm={() => revoke.mutate(r)}
        >
          Revoke
        </ConfirmDialog>
      )}
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <DisplayHeading strong="Admins" light="& roles" />
        <Button onClick={() => setEditing("new")}>Add admin</Button>
      </div>
      {roles.isError && <ErrorAlert error={roles.error} />}
      <DataTable<RoleRow>
        rows={roles.data}
        loading={roles.isPending}
        rowKey={(r) => r.email}
        empty="No admins."
        mobileCard={(r) => (
          <>
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-medium break-all">{r.name ?? r.email}</p>
                {r.name && <p className="break-all text-muted-foreground">{r.email}</p>}
              </div>
              <RoleBadge role={r.role} />
            </div>
            <p className="text-muted-foreground">
              Granted {formatDateTime(r.granted_at)} by {r.granted_by_email ?? "system"} · last sign-in{" "}
              {r.last_login_at ? formatDateTime(r.last_login_at) : "never"}
            </p>
            <div className="pt-1">{actions(r)}</div>
          </>
        )}
        columns={[
          { header: "Name", cell: (r) => r.name ?? <span className="text-muted-foreground">Not signed in yet</span> },
          { header: "Email", cell: (r) => r.email },
          { header: "Role", cell: (r) => <RoleBadge role={r.role} /> },
          { header: "Granted by", cell: (r) => r.granted_by_email ?? "System" },
          { header: "Granted on", cell: (r) => formatDateTime(r.granted_at) },
          { header: "Last sign-in", cell: (r) => (r.last_login_at ? formatDateTime(r.last_login_at) : "Never") },
          { header: "", cell: actions },
        ]}
      />
      {editing && (
        <RoleDialog
          row={editing === "new" ? null : editing}
          me={me}
          onClose={() => setEditing(null)}
          onSaved={(row) => {
            if (row.email === me) void queryClient.invalidateQueries({ queryKey: queryKeys.session });
            else void refresh();
          }}
        />
      )}
    </div>
  );
}

function RoleBadge({ role }: { role: string }) {
  return <Badge variant={role === "SUPER_ADMIN" ? "default" : "secondary"}>{ROLE_LABELS[role] ?? role}</Badge>;
}

function RoleDialog({
  row,
  me,
  onClose,
  onSaved,
}: {
  row: RoleRow | null;
  me: string | undefined;
  onClose: () => void;
  onSaved: (row: RoleRow) => void;
}) {
  const form = useForm<RoleForm>({
    resolver: zodResolver(roleSchema),
    defaultValues: { email: row?.email ?? "", role: (row?.role as RoleForm["role"] | undefined) ?? "ADMIN" },
  });
  const save = useMutation({
    mutationFn: async ({ email, role }: RoleForm) =>
      (await api.PUT("/api/admin/roles/{email}", { params: { path: { email } }, body: { role } })).data!,
    onSuccess: (saved) => {
      toast.success(
        row ? `${saved.email} is now ${ROLE_LABELS[saved.role]}` : `${saved.email} added as ${ROLE_LABELS[saved.role]}`,
      );
      onSaved(saved);
      onClose();
    },
    onError: (error) => applyServerErrors(form, error),
  });
  // The last super admin keeps the role: demoting them is refused (409) anyway.
  const roleItems = row?.last_super_admin ? { SUPER_ADMIN: ROLE_LABELS.SUPER_ADMIN } : ROLE_LABELS;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{row ? `Change role for ${row.email}` : "Add admin"}</DialogTitle>
          <DialogDescription className="flex gap-2.5 rounded-xl bg-navy-soft p-3.5 text-foreground">
            <InfoIcon className="mt-0.5 size-4 shrink-0 text-stamp-navy" aria-hidden />
            {row?.last_super_admin
              ? LAST_SUPER_ADMIN
              : row?.email === me
                ? "Changing your own role signs you out."
                : "A change signs the person out; they sign in again with the new role."}
          </DialogDescription>
        </DialogHeader>
        <form id="role-form" onSubmit={form.handleSubmit((v) => save.mutate(v))} noValidate>
          <FieldGroup>
            <TextField
              form={form}
              name="email"
              label="BTU email"
              type="email"
              autoComplete="off"
              readOnly={row !== null}
            />
            <SelectField form={form} name="role" label="Role" items={roleItems} />
          </FieldGroup>
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="role-form" disabled={save.isPending || row?.last_super_admin}>
            {row ? "Save" : "Add admin"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
