"use client";

// FE-50: skills catalog (Web App Design A9). Admins read; super admins add, edit, archive and
// delete (only skills never awarded). Changes apply to future passport versions only.
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontalIcon } from "lucide-react";
import { useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { DisplayHeading } from "@/components/display";
import { DataTable } from "@/components/data-table";
import { ErrorAlert } from "@/components/error-alert";
import { TextField } from "@/components/form-fields";
import { StampImage } from "@/components/stamp-image";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { applyServerErrors } from "@/lib/forms";
import { queryKeys } from "@/lib/query-keys";
import { hasRole, useSession } from "@/lib/session";

type SkillRow = components["schemas"]["SkillRow"];

// Mirrors backend/app/services/catalog.py; the server checks again.
const NAME_MAX = 80;
const DESCRIPTION_MAX = 300;
const DESCRIPTION_LONG = 150;
const skillSchema = z.object({
  name: z.string().trim().min(1, "Required").max(NAME_MAX, `At most ${NAME_MAX} characters`),
  category_id: z.string().min(1, "Choose a category"),
  description: z.string().trim().min(1, "Required").max(DESCRIPTION_MAX, `At most ${DESCRIPTION_MAX} characters`),
});
type SkillForm = z.infer<typeof skillSchema>;

export default function SkillsPage() {
  const session = useSession();
  const isSuper = session.data ? hasRole(session.data, "super_admin") : false;
  const queryClient = useQueryClient();
  const [includeArchived, setIncludeArchived] = useState(false);
  const [editing, setEditing] = useState<SkillRow | "new" | null>(null);
  const [deleting, setDeleting] = useState<SkillRow | null>(null);

  const skills = useQuery({
    queryKey: includeArchived ? queryKeys.admin.skillsAll : queryKeys.admin.skills,
    queryFn: async () =>
      (await api.GET("/api/admin/skills", { params: { query: { include_archived: includeArchived } } })).data!,
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.admin.skills });

  const archive = useMutation({
    mutationFn: async ({ skill, archived }: { skill: SkillRow; archived: boolean }) => {
      const path = { path: { skill_id: skill.skill_id } };
      return archived
        ? (await api.POST("/api/admin/skills/{skill_id}/archive", { params: path })).data!
        : (await api.POST("/api/admin/skills/{skill_id}/unarchive", { params: path })).data!;
    },
    onSuccess: (row) => {
      toast.success(row.archived ? `${row.name} archived` : `${row.name} is active again`);
      void refresh();
    },
    onError: (error) => toast.error(error.message),
  });
  const remove = useMutation({
    mutationFn: async (skill: SkillRow) =>
      api.DELETE("/api/admin/skills/{skill_id}", { params: { path: { skill_id: skill.skill_id } } }),
    onSuccess: (_, skill) => {
      toast.success(`${skill.name} deleted`);
      void refresh();
    },
    onError: (error) => toast.error(error.message), // 409 in_use
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <DisplayHeading strong="Skills" />
        {isSuper && <Button onClick={() => setEditing("new")}>Add skill</Button>}
      </div>
      {skills.isError && <ErrorAlert error={skills.error} />}
      <DataTable<SkillRow>
        rows={skills.data}
        loading={skills.isPending}
        rowKey={(s) => s.skill_id}
        empty="No skills yet."
        toolbar={
          <Label className="flex items-center gap-2">
            <Checkbox checked={includeArchived} onCheckedChange={(v) => setIncludeArchived(v === true)} />
            Include archived
          </Label>
        }
        mobileCard={(s) => (
          <>
            <div className="flex items-start justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <CategoryStamp skill={s} />
                <div className="min-w-0">
                  <p className="font-medium">{s.name}</p>
                  <p className="text-muted-foreground">
                    {s.skill_id} · {s.category.name}
                  </p>
                </div>
              </div>
              {isSuper && <RowMenu skill={s} onEdit={setEditing} onArchive={archive.mutate} onDelete={setDeleting} />}
            </div>
            <p className="text-muted-foreground">
              Awarded {s.times_awarded} time{s.times_awarded === 1 ? "" : "s"} · <SkillStatus skill={s} />
            </p>
          </>
        )}
        columns={[
          { header: "Skill ID", cell: (s) => <span className="font-mono">{s.skill_id}</span> },
          { header: "Name", cell: (s) => s.name, className: "whitespace-normal" },
          {
            header: "Category",
            cell: (s) => (
              <span className="flex items-center gap-2">
                <CategoryStamp skill={s} />
                {s.category.name}
              </span>
            ),
          },
          { header: "Times awarded", cell: (s) => s.times_awarded },
          { header: "Status", cell: (s) => <SkillStatus skill={s} /> },
          ...(isSuper
            ? [
                {
                  header: "",
                  cell: (s: SkillRow) => (
                    <RowMenu skill={s} onEdit={setEditing} onArchive={archive.mutate} onDelete={setDeleting} />
                  ),
                },
              ]
            : []),
        ]}
      />
      {editing && (
        <SkillDialog
          skill={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => void refresh()}
        />
      )}
      <AlertDialog open={deleting !== null} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {deleting?.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              It has never been awarded, so it can be removed for good. This can&apos;t be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogCancel variant="destructive" onClick={() => deleting && remove.mutate(deleting)}>
              Delete
            </AlertDialogCancel>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function CategoryStamp({ skill }: { skill: SkillRow }) {
  if (!skill.category.stamp_sha256) return null;
  return (
    <span className="shrink-0 [&_img]:size-8">
      <StampImage sha256={skill.category.stamp_sha256} category={skill.category.name} />
    </span>
  );
}

function SkillStatus({ skill }: { skill: SkillRow }) {
  return skill.archived ? <Badge variant="outline">Archived</Badge> : <Badge variant="secondary">Active</Badge>;
}

function RowMenu({
  skill,
  onEdit,
  onArchive,
  onDelete,
}: {
  skill: SkillRow;
  onEdit: (s: SkillRow) => void;
  onArchive: (v: { skill: SkillRow; archived: boolean }) => void;
  onDelete: (s: SkillRow) => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button variant="ghost" size="icon" aria-label={`Actions for ${skill.name}`} />}>
        <MoreHorizontalIcon />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => onEdit(skill)}>Edit</DropdownMenuItem>
        <DropdownMenuItem onClick={() => onArchive({ skill, archived: !skill.archived })}>
          {skill.archived ? "Unarchive" : "Archive"}
        </DropdownMenuItem>
        {skill.times_awarded === 0 && (
          <DropdownMenuItem variant="destructive" onClick={() => onDelete(skill)}>
            Delete
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function SkillDialog({ skill, onClose, onSaved }: { skill: SkillRow | null; onClose: () => void; onSaved: () => void }) {
  const categories = useQuery({
    queryKey: queryKeys.admin.categories(false),
    queryFn: async () => (await api.GET("/api/admin/categories")).data!,
  });
  const form = useForm<SkillForm>({
    resolver: zodResolver(skillSchema),
    defaultValues: {
      name: skill?.name ?? "",
      category_id: skill ? String(skill.category.category_id) : "",
      description: skill?.description ?? "",
    },
  });
  const save = useMutation({
    mutationFn: async (values: SkillForm) => {
      const body = { ...values, category_id: Number(values.category_id) };
      return skill
        ? (await api.PATCH("/api/admin/skills/{skill_id}", { params: { path: { skill_id: skill.skill_id } }, body }))
            .data!
        : (await api.POST("/api/admin/skills", { body })).data!;
    },
    onSuccess: (row) => {
      toast.success(skill ? `${row.name} saved` : `${row.name} added as ${row.skill_id}`);
      onSaved();
      onClose();
    },
    onError: (error) => applyServerErrors(form, error),
  });
  // An edited skill may sit in a category archived since; keep it choosable.
  const options = [
    ...(categories.data ?? []),
    ...(skill && !categories.data?.some((c) => c.category_id === skill.category.category_id)
      ? [{ ...skill.category, name: `${skill.category.name} (archived)` }]
      : []),
  ];
  const description = useWatch({ control: form.control, name: "description" });

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{skill ? `Edit ${skill.skill_id}` : "Add skill"}</DialogTitle>
          <DialogDescription>Changes apply to future passport versions only.</DialogDescription>
        </DialogHeader>
        <form id="skill-form" onSubmit={form.handleSubmit((v) => save.mutate(v))} noValidate>
          <FieldGroup>
            <TextField form={form} name="name" label="Name" maxLength={NAME_MAX} />
            <Controller
              name="category_id"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="category_id">Category</FieldLabel>
                  <Select
                    value={field.value || null}
                    onValueChange={(v) => field.onChange(v ?? "")}
                    items={Object.fromEntries(options.map((c) => [String(c.category_id), c.name]))}
                  >
                    <SelectTrigger id="category_id" aria-invalid={fieldState.invalid} className="w-full">
                      <SelectValue placeholder="Choose a category" />
                    </SelectTrigger>
                    <SelectContent>
                      {options.map((c) => (
                        <SelectItem key={c.category_id} value={String(c.category_id)}>
                          {c.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
                </Field>
              )}
            />
            <Controller
              name="description"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="description">Description</FieldLabel>
                  <Textarea {...field} id="description" aria-invalid={fieldState.invalid} />
                  <FieldDescription>
                    {description.length}/{DESCRIPTION_MAX}
                    {description.length > DESCRIPTION_LONG && " · Long descriptions may wrap on the passport PDF."}
                  </FieldDescription>
                  {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
                </Field>
              )}
            />
          </FieldGroup>
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="skill-form" disabled={save.isPending}>
            {skill ? "Save" : "Add skill"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
