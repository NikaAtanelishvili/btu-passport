"use client";

// FE-22: register a student (Web App Design A2). The server generates the Passport ID; the
// first version is issued with the student's first skill. ?email= pre-fills the email
// (Unregistered check-ins on the event page, M7).
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { SelectField, TextField } from "@/components/form-fields";
import { FieldGroup } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { applyServerErrors } from "@/lib/forms";
import { queryKeys } from "@/lib/query-keys";
import { EDUCATION_LEVELS, type RegisterForm, registerSchema, STUDENT_STATUSES } from "@/lib/students";

export default function RegisterStudentPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full max-w-xl" />}>
      <RegisterStudent />
    </Suspense>
  );
}

function RegisterStudent() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const email = useSearchParams().get("email") ?? "";
  const programs = useQuery({
    queryKey: queryKeys.admin.programs,
    queryFn: async () => (await api.GET("/api/admin/programs")).data!,
  });
  const form = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      student_id: "",
      first_name: "",
      last_name: "",
      email,
      program: "",
      education_level: "BACHELOR",
      status: "ACTIVE",
    },
  });
  const register = useMutation({
    mutationFn: async (body: RegisterForm) => (await api.POST("/api/admin/students", { body })).data!,
    onSuccess: (student) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.all });
      toast.success(`Student registered — Passport ID ${student.passport.passport_id}`);
      router.push(`/admin/students/${student.profile.student_id}`);
    },
    onError: (error) => applyServerErrors(form, error),
  });

  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle className="font-display text-3xl font-black uppercase">Register student</CardTitle>
        <CardDescription>
          A Passport ID is generated on save. The first version is issued when the student gets their first skill.
        </CardDescription>
      </CardHeader>
      <form onSubmit={form.handleSubmit((body) => register.mutate(body))} noValidate>
        <CardContent>
          <FieldGroup>
            <TextField form={form} name="student_id" label="Student ID" placeholder="BTU-T-0001" />
            <div className="grid gap-4 sm:grid-cols-2">
              <TextField form={form} name="first_name" label="First name" />
              <TextField form={form} name="last_name" label="Last name" />
            </div>
            <TextField form={form} name="email" label="BTU email" type="email" />
            <TextField form={form} name="program" label="Program" list="programs" />
            <datalist id="programs">
              {(programs.data ?? []).map((p) => (
                <option key={p} value={p} />
              ))}
            </datalist>
            <div className="grid gap-4 sm:grid-cols-2">
              <SelectField form={form} name="education_level" label="Education level" items={EDUCATION_LEVELS} />
              <SelectField form={form} name="status" label="Status" items={STUDENT_STATUSES} />
            </div>
          </FieldGroup>
        </CardContent>
        <CardFooter className="mt-6 gap-2">
          <Button type="submit" disabled={register.isPending}>
            Register student
          </Button>
          <Button type="button" variant="ghost" onClick={() => router.back()}>
            Cancel
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
