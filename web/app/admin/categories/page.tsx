"use client";

// FE-51: categories and stamps (Web App Design A10). Admins read; super admins add, rename,
// archive, delete (only with no skills) and upload stamps. A stamp is stored by its SHA-256,
// so versions already issued keep the stamp they printed; a new one appears on future versions.
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontalIcon } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { applyServerErrors } from "@/lib/forms";
import { queryKeys } from "@/lib/query-keys";
import { hasRole, useSession } from "@/lib/session";
import { checkStampFile } from "@/lib/stamp-file";

type CategoryRow = components["schemas"]["CategoryRow"];

// Mirrors backend/app/services/catalog.py; the server checks again.
const NAME_MAX = 60;
const nameSchema = z.object({
  name: z.string().trim().min(1, "Required").max(NAME_MAX, `At most ${NAME_MAX} characters`),
});
type NameForm = z.infer<typeof nameSchema>;

type Dialogs =
  | { kind: "add" }
  | { kind: "rename"; category: CategoryRow }
  | { kind: "stamp"; category: CategoryRow }
  | { kind: "delete"; category: CategoryRow };

export default function CategoriesPage() {
  const session = useSession();
  const isSuper = session.data ? hasRole(session.data, "super_admin") : false;
  const queryClient = useQueryClient();
  const [includeArchived, setIncludeArchived] = useState(false);
  const [dialog, setDialog] = useState<Dialogs | null>(null);

  const categories = useQuery({
    queryKey: queryKeys.admin.categories(includeArchived),
    queryFn: async () =>
      (await api.GET("/api/admin/categories", { params: { query: { include_archived: includeArchived } } })).data!,
  });
  // Skills show their category's name and stamp, so they change too.
  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin", "categories"] }),
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.skills }),
    ]);

  const archive = useMutation({
    mutationFn: async ({ category, archived }: { category: CategoryRow; archived: boolean }) => {
      const path = { path: { category_id: category.category_id } };
      return archived
        ? (await api.POST("/api/admin/categories/{category_id}/archive", { params: path })).data!
        : (await api.POST("/api/admin/categories/{category_id}/unarchive", { params: path })).data!;
    },
    onSuccess: (row) => {
      toast.success(row.archived ? `${row.name} archived` : `${row.name} is active again`);
      void refresh();
    },
    onError: (error) => toast.error(error.message),
  });
  const remove = useMutation({
    mutationFn: async (category: CategoryRow) =>
      api.DELETE("/api/admin/categories/{category_id}", {
        params: { path: { category_id: category.category_id } },
      }),
    onSuccess: (_, category) => {
      toast.success(`${category.name} deleted`);
      void refresh();
    },
    onError: (error) => toast.error(error.message), // 409 in_use
  });

  const menu = (c: CategoryRow) => (
    <RowMenu
      category={c}
      onOpen={setDialog}
      onArchive={() => archive.mutate({ category: c, archived: !c.archived })}
    />
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Categories & stamps</h1>
        {isSuper && <Button onClick={() => setDialog({ kind: "add" })}>Add category</Button>}
      </div>
      {categories.isError && <ErrorAlert error={categories.error} />}
      <DataTable<CategoryRow>
        rows={categories.data}
        loading={categories.isPending}
        rowKey={(c) => c.category_id}
        empty="No categories yet."
        toolbar={
          <Label className="flex items-center gap-2">
            <Checkbox checked={includeArchived} onCheckedChange={(v) => setIncludeArchived(v === true)} />
            Include archived
          </Label>
        }
        mobileCard={(c) => (
          <div className="flex items-start justify-between gap-2">
            <div className="flex min-w-0 items-center gap-3">
              <Stamp category={c} />
              <div className="min-w-0">
                <p className="font-medium">{c.name}</p>
                <p className="text-muted-foreground">
                  {c.badge_code} · {c.skill_count} skill{c.skill_count === 1 ? "" : "s"} · <CategoryStatus category={c} />
                </p>
              </div>
            </div>
            {isSuper && menu(c)}
          </div>
        )}
        columns={[
          { header: "Stamp", cell: (c) => <Stamp category={c} /> },
          { header: "Name", cell: (c) => c.name, className: "whitespace-normal" },
          { header: "Badge code", cell: (c) => c.badge_code },
          { header: "Skills", cell: (c) => c.skill_count },
          { header: "Status", cell: (c) => <CategoryStatus category={c} /> },
          ...(isSuper ? [{ header: "", cell: menu }] : []),
        ]}
      />
      {(dialog?.kind === "add" || dialog?.kind === "rename") && (
        <NameDialog
          category={dialog.kind === "rename" ? dialog.category : null}
          onClose={() => setDialog(null)}
          onSaved={() => void refresh()}
        />
      )}
      {dialog?.kind === "stamp" && (
        <StampDialog category={dialog.category} onClose={() => setDialog(null)} onSaved={() => void refresh()} />
      )}
      <AlertDialog open={dialog?.kind === "delete"} onOpenChange={(open) => !open && setDialog(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {dialog?.kind === "delete" && dialog.category.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              It has no skills, so it can be removed for good. This can&apos;t be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogCancel
              variant="destructive"
              onClick={() => dialog?.kind === "delete" && remove.mutate(dialog.category)}
            >
              Delete
            </AlertDialogCancel>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function Stamp({ category }: { category: CategoryRow }) {
  if (!category.stamp_sha256) return <span className="text-muted-foreground">No stamp</span>;
  return (
    <span className="block shrink-0">
      <StampImage sha256={category.stamp_sha256} category={category.name} />
    </span>
  );
}

function CategoryStatus({ category }: { category: CategoryRow }) {
  return category.archived ? <Badge variant="outline">Archived</Badge> : <Badge variant="secondary">Active</Badge>;
}

function RowMenu({
  category,
  onOpen,
  onArchive,
}: {
  category: CategoryRow;
  onOpen: (d: Dialogs) => void;
  onArchive: () => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button variant="ghost" size="icon" aria-label={`Actions for ${category.name}`} />}>
        <MoreHorizontalIcon />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => onOpen({ kind: "stamp", category })}>Upload stamp</DropdownMenuItem>
        <DropdownMenuItem onClick={() => onOpen({ kind: "rename", category })}>Rename</DropdownMenuItem>
        <DropdownMenuItem onClick={onArchive}>{category.archived ? "Unarchive" : "Archive"}</DropdownMenuItem>
        {category.skill_count === 0 && (
          <DropdownMenuItem variant="destructive" onClick={() => onOpen({ kind: "delete", category })}>
            Delete
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function NameDialog({
  category,
  onClose,
  onSaved,
}: {
  category: CategoryRow | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const form = useForm<NameForm>({ resolver: zodResolver(nameSchema), defaultValues: { name: category?.name ?? "" } });
  const save = useMutation({
    mutationFn: async (body: NameForm) =>
      category
        ? (
            await api.PATCH("/api/admin/categories/{category_id}", {
              params: { path: { category_id: category.category_id } },
              body,
            })
          ).data!
        : (await api.POST("/api/admin/categories", { body })).data!,
    onSuccess: (row) => {
      toast.success(category ? `Renamed to ${row.name}` : `${row.name} added as ${row.badge_code}`);
      onSaved();
      onClose();
    },
    onError: (error) => applyServerErrors(form, error),
  });

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{category ? `Rename ${category.badge_code}` : "Add category"}</DialogTitle>
          <DialogDescription>
            {category
              ? "Passports already issued keep the name they printed."
              : "The badge code is assigned automatically. Upload its stamp afterwards."}
          </DialogDescription>
        </DialogHeader>
        <form id="category-form" onSubmit={form.handleSubmit((v) => save.mutate(v))} noValidate>
          <FieldGroup>
            <TextField form={form} name="name" label="Name" maxLength={NAME_MAX} />
          </FieldGroup>
        </form>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="category-form" disabled={save.isPending}>
            {category ? "Save" : "Add category"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function StampDialog({
  category,
  onClose,
  onSaved,
}: {
  category: CategoryRow;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const upload = useMutation({
    mutationFn: async (stamp: File) => {
      const body = new FormData();
      body.append("file", stamp);
      return (
        await api.POST("/api/admin/categories/{category_id}/stamp", {
          params: { path: { category_id: category.category_id } },
          // The generated type says string; openapi-fetch sends FormData as multipart as is.
          body: body as unknown as { file: string },
        })
      ).data!;
    },
    onSuccess: (row) => {
      toast.success(
        row.stamp_sha256 === category.stamp_sha256 ? "That is already the current stamp" : `New stamp for ${row.name}`,
      );
      onSaved();
      onClose();
    },
    onError: (error) => {
      if (error instanceof ApiError && error.fields.file) setProblem(error.fields.file);
      else toast.error(error.message);
    },
  });

  const choose = async (picked: File | null) => {
    setFile(picked);
    setProblem(picked ? await checkStampFile(picked) : null);
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Stamp for {category.name}</DialogTitle>
          <DialogDescription>A new stamp appears on future versions only.</DialogDescription>
        </DialogHeader>
        {category.stamp_sha256 && (
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <StampImage sha256={category.stamp_sha256} category={category.name} />
            Current stamp
          </div>
        )}
        <form
          id="stamp-form"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            if (!file) setProblem("Choose a file.");
            else if (!problem) upload.mutate(file);
          }}
        >
          <Field data-invalid={problem !== null}>
            <FieldLabel htmlFor="stamp-file">Image</FieldLabel>
            <Input
              id="stamp-file"
              type="file"
              accept="image/png,image/svg+xml,.png,.svg"
              aria-invalid={problem !== null}
              onChange={(e) => void choose(e.target.files?.[0] ?? null)}
            />
            <FieldDescription>PNG (square, at least 600×600 px) or SVG, at most 1 MB.</FieldDescription>
            {problem && <FieldError>{problem}</FieldError>}
          </Field>
        </form>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="stamp-form" disabled={upload.isPending || problem !== null}>
            Upload
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
