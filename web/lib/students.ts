// Student field vocabularies and rules shared by the register and edit forms (FE-22, FE-23).
// The rules mirror backend/app/services/students.py; the server checks them again.
import { z } from "zod";

export const EDUCATION_LEVELS = { BACHELOR: "Bachelor's", MASTER: "Master's", DOCTORAL: "Doctoral" } as const;
export const STUDENT_STATUSES = { ACTIVE: "Active", GRADUATE: "Graduate" } as const;

const name = z.string().trim().min(1, "Required").max(60, "At most 60 characters");

export const profileSchema = z.object({
  first_name: name,
  last_name: name,
  email: z.string().trim().email("Enter a valid email address"),
  program: z.string().trim().min(1, "Choose or type a program"),
  education_level: z.enum(["BACHELOR", "MASTER", "DOCTORAL"], { message: "Choose a level" }),
  status: z.enum(["ACTIVE", "GRADUATE"], { message: "Choose a status" }),
});

export const registerSchema = profileSchema.extend({
  // DEFAULT(Q16): the Student ID format of the test data.
  student_id: z
    .string()
    .trim()
    .regex(/^BTU-T-\d{4,}$/i, "Use the BTU format, e.g. BTU-T-0001"),
});

export type ProfileForm = z.infer<typeof profileSchema>;
export type RegisterForm = z.infer<typeof registerSchema>;
