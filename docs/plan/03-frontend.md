# Frontend

## 1. Setup

A Next.js app built entirely from stock shadcn/ui components. Visual design is out of scope: default theme, default spacing, no custom CSS beyond layout.

### FE-01 Scaffold (M0) — `web/` ✅

1. `pnpm create next-app web --ts --tailwind --eslint --app --import-alias "@/*"` (no `src/` folder).
2. `pnpm dlx shadcn@latest init` with defaults, then add: `button input label textarea select checkbox form card table badge tabs dialog alert-dialog alert dropdown-menu command popover separator skeleton sheet sonner tooltip`.
3. Libraries: `@tanstack/react-query`, `react-hook-form`, `@hookform/resolvers`, `zod`, `openapi-fetch`, `viem`, `@noble/hashes`. Dev: `openapi-typescript`, `vitest`, `@playwright/test` (M10).
4. If the current shadcn registry has replaced `form` with `field`, use `field` the same way. Dates and times use shadcn `Input` with `type="date"` and `type="datetime-local"` — no date-picker library.
5. `next.config.ts` rewrites, so the browser only ever talks to `localhost:3000`:

```ts
const api = process.env.API_ORIGIN ?? "http://localhost:8000";
export default {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${api}/api/:path*` },
      { source: "/auth/:path*", destination: `${api}/auth/:path*` },
      {
        source: "/.well-known/:path*",
        destination: `${api}/.well-known/:path*`,
      },
    ];
  },
};
```

6. `app/layout.tsx`: providers (`QueryClientProvider`, `Toaster` from sonner) and a minimal header ("BTU AI Skills Passport", Verify, Sign in / Sign out).
7. A temporary home page that calls `/api/healthz` and shows the result.

**Done when:** `make web` serves `localhost:3000`, the page shows `ok: true` from the API through the rewrite, `pnpm lint` and `pnpm tsc --noEmit` pass.

## 2. Structure, API client, session and CSRF

Every page is a client component that fetches through one typed API client with TanStack Query. There is no server-side data fetching, so the session cookie and CSRF handling live in exactly one place.

### Routes (`web/app/`)

| Route                                                                                 | Page              | Guard                                         | Task                |
| ------------------------------------------------------------------------------------- | ----------------- | --------------------------------------------- | ------------------- |
| `/verify`                                                                             | P1 Verify         | none                                          | FE-10               |
| `/` (alias: redirects to `/verify`)                                                   | P1 Verify         | none                                          | FE-10               |
| `/v/[code]`                                                                           | P2 Verify result  | none                                          | FE-11               |
| `/login`                                                                              | P4 Sign in        | none (signed in → redirect by role)           | FE-04               |
| `/checkin/[eventId]`                                                                  | P3 Check-in       | signed in                                     | FE-33               |
| `/me`, `/me/history`, `/me/events`                                                    | S1 – S3           | student                                       | FE-40, FE-41, FE-34 |
| `/admin`                                                                              | A1 Dashboard      | admin                                         | FE-21               |
| `/admin/students`, `/admin/students/new`, `/admin/students/[id]`                      | A2, A3            | admin                                         | FE-22, FE-23        |
| `/admin/awards/new`                                                                   | A4 Direct award   | admin                                         | FE-24               |
| `/admin/issuance`                                                                     | A5 Issuance       | admin                                         | FE-25               |
| `/admin/events`, `/admin/events/new`, `/admin/events/[id]`, `/admin/events/[id]/edit` | A6, A7            | admin (writes: super admin)                   | FE-30, FE-31        |
| `/admin/events/[id]/present`                                                          | A8 Presenter view | super admin                                   | FE-32               |
| `/admin/skills`, `/admin/categories`, `/admin/roles`, `/admin/audit`                  | A9 – A12          | super admin (skills, categories: admins read) | FE-50 – FE-53       |

Page codes (P1, S1, A7 …) are those of the Web App Design document; follow its section tables for what each page contains.

### FE-02 API client and types (M3) — `web/lib/` ✅

- `api-types.ts`: generated, never edited. `make types` runs `openapi-typescript http://localhost:8000/openapi.json -o web/lib/api-types.ts`.
- `api.ts`: an `openapi-fetch` client with `baseUrl: ""` (same origin) and `credentials: "include"`. A middleware adds `X-CSRF-Token` (read from the `csrf_token` cookie) to every POST, PUT, PATCH and DELETE, and turns non-2xx responses into `ApiError {status, error, message, fields}`. On 401 from a guarded page, redirect to `/login?next=<current path>`.
- `query-keys.ts`: one place for TanStack Query keys, so mutations invalidate the right lists.
- `forms.ts`: `applyServerErrors(form, apiError)` calls `form.setError(name, ...)` for each entry in `fields`, and shows `message` in a toast when there are no field errors.

### FE-03 Session and guards (M3) ✅

- `useSession()` = query on `GET /api/session` (stale time 30 s).
- `<RequireRole role="student" | "admin" | "super_admin">` in the `me/` and `admin/` layouts: skeleton while loading; signed out → redirect to `/login?next=…`; wrong role → a shadcn `Alert` "You don't have access to this page" with a link home. The server enforces the same rules; this is only for a sensible screen.
- Header: "Sign in" links to `/login`; "Sign out" POSTs `/auth/logout` and then navigates to the home page.

### Shared components (`web/components/`)

| Component                  | Built from                  | Used for                                                                                                                                                                                                                     |
| -------------------------- | --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AdminShell`               | `sheet` (mobile), plain nav | Sidebar: Operations (Dashboard, Students, Direct award, Issuance) and Super admin (Events, Skills, Categories & stamps, Admins & roles, Audit log); Super admin group hidden for `ADMIN`, who sees Events from the dashboard |
| `DataTable`                | `table`, `button`           | Server-paginated lists with a search input and filter selects                                                                                                                                                                |
| `StatusBadge`              | `badge`                     | Version and event statuses; one fixed mapping of status → badge variant                                                                                                                                                      |
| `CodeDisplay`              | `button`, `tooltip`         | Shows `XXXX-XXXX-XX` with a copy button                                                                                                                                                                                      |
| `StampImage`               | `img`                       | `/api/stamps/{sha256}`, 48 px, with alt text = category                                                                                                                                                                      |
| `ConfirmDialog`            | `alert-dialog`              | Every destructive or irreversible action                                                                                                                                                                                     |
| `EmptyState`, `ErrorState` | `card`, `alert`             | Every list and detail page                                                                                                                                                                                                   |
| `StudentPicker`            | `command`, `popover`        | Multi-select search over `/api/admin/students?q=`                                                                                                                                                                            |

### FE-04 Sign in `/login` (M3) ✅

One client page, two steps (Web App Design P4), stock shadcn `Card`, `field`, `Input`, `InputOTP`, `Button`.

1. **Email step:** email `Input` + **Send code** → `POST /auth/request-code`. Errors under the field: 422 `email_domain_not_allowed` → "Use your BTU email"; 429 → "Too many codes requested, try again later". A **Continue as guest** link goes to `/verify`; guests never sign in.
2. **Code step:** "We sent a 6-digit code to {email}", a 6-slot `InputOTP`, **Sign in** → `POST /auth/verify-code` with `next` from the URL. 400 `code_invalid` → "Wrong code, {attempts_left} tries left"; 400 `code_expired` → "Code expired, send a new one" and back to step 1. **Resend code** is disabled for 60 s after each send; **Use a different email** returns to step 1.
3. On success, `window.location.assign(redirect)`: a full reload, so the new cookies and `useSession()` start fresh. Already signed in → redirect by role.

**Done when (M3):** each test user signs in with a code read from Mailpit and lands on the right page; a non-BTU email shows the domain error; a wrong code shows the tries left.

## 3. Public pages

These must work well on a phone: most visitors are an employer opening a link or a student scanning a QR.

### FE-10 Verify `/verify` (M5) ✅

The public verification page lives at `/verify`. `/` stays as an alias: a `redirects()` entry in `next.config.ts` (`permanent: false`) sends it to `/verify` (replacing the temporary FE-01 health page), so old links and the bare domain still land on Verify.

- `Card` "Verify a passport": `Input` for the code (placeholder `XXXX-XXXX-XX`, accepts any case and dashes) + `Button` Verify → `router.push("/v/" + normalized)`.
- `Card` "Or check the PDF you received": file `Input` (`accept="application/pdf"`) or drop zone. On select: `sha256File()` (BC-06) → `POST /api/verify/hash` → render `<VerifyResultView>` below, then run the independent check (FE-12). The note "Your file stays on your device; only its fingerprint is sent" sits under the input.
- Three lines of "How it works" text.

### FE-11 Verify result `/v/[code]` (M5) ✅

`GET /api/verify/{code}` → `<VerifyResultView>` (shared with FE-10):

| Section           | Component                                                         | Content                                                                                                                                                                  |
| ----------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Verdict           | `Alert` (default variant for VALID, destructive for the failures) | Wording below                                                                                                                                                            |
| Checks            | two rows with ✓ / ✗                                               | "Document unchanged since issue", "Issued by BTU"                                                                                                                        |
| Independent check | small text row                                                    | FE-12 result: "Also checked directly on the blockchain from your browser ✓", or "Couldn't reach the blockchain from your browser; the result above is from BTU's server" |
| Official data     | `Card`                                                            | Holder name, Passport ID, version, issue date; skills list with `StampImage`, name, date earned                                                                          |
| Compare           | `Button`                                                          | "Download the official copy" → `/api/verify/{code}/pdf`                                                                                                                  |
| Proof             | collapsible section                                               | Contract, Merkle root, transaction (link to `NEXT_PUBLIC_EXPLORER_TX_URL` when set), "Download proof.json"                                                               |

| Verdict             | Headline                                                                    |
| ------------------- | --------------------------------------------------------------------------- |
| `VALID`             | Valid — issued by BTU                                                       |
| `SUPERSEDED`        | Authentic, but superseded by version N — ask the holder for the current one |
| `NOT_FOUND`         | Not valid — this file doesn't match any passport BTU issued                 |
| `UNKNOWN_CODE`      | Unknown code — check it and try again                                       |
| `NOT_ISSUED_BY_BTU` | Not issued by BTU                                                           |
| `REVOKED`           | Revoked by BTU                                                              |

### FE-12 Independent check (M5) — `web/lib/verify.ts` ✅

`independentCheck(result)`: fetch `/.well-known/ai-passport-issuer.json`; recompute the root with `processProof(leaf, proof)`; create a `viem` public client on `NEXT_PUBLIC_RPC_URL` with the ABI from `shared/PassportRegistry.abi.json` (copied into `web/lib/` by `make chain-abi`); read `anchoredAt(root)` and `owner()`. Returns `{documentOk, issuerOk}` or `{unreachable: true}`. Never blocks the page: the server verdict shows first.

### FE-33 Check-in `/checkin/[eventId]?t=` (M7) ✅

1. `useSession()`; not signed in → `/login?next=<this URL including t>`.
2. `GET /api/checkin/{eventId}?t=` → one `Card` per state:

| State                 | Shows                                                                                                                                                                                                                                                                                                                       |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `CONFIRM`             | Event name, `StampImage` + skill name, date, location; large `Button` "Check in" → POST; then the CHECKED_IN card                                                                                                                                                                                                           |
| `CHECKED_IN`          | "You're checked in. The skill will appear on your passport once the organiser completes the event." Link to My events. Extra line when `unregistered` ("…your account isn't in BTU's student records yet; the organiser will add you") or `already_holds_skill` ("You already have this skill; your passport won't change") |
| `TOKEN_EXPIRED`       | "This code has expired. Scan the code on the screen again."                                                                                                                                                                                                                                                                 |
| `NOT_OPEN` / `CLOSED` | "Check-in hasn't opened yet" / "Check-in has closed"                                                                                                                                                                                                                                                                        |
| `REMOVED`             | "The organiser removed your check-in. Please talk to them."                                                                                                                                                                                                                                                                 |
| `NOT_FOUND`           | "Event not found"                                                                                                                                                                                                                                                                                                           |

## 4. Student portal

Three read-only pages under `app/me/`, with a top nav (My passport, History, My events) and `<RequireRole role="student">` in `me/layout.tsx`.

| Task       | Route         | API calls              | Content                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ---------- | ------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FE-40 (M8) ✅ | `/me`         | `GET /api/me/passport` | Header `Card`: name, Passport ID, first issued. `Alert` "Issuing version N…" when `issuing` is set (refetch every 5 s while it is). Current version `Card`: version, issue date, `CodeDisplay`, a "Copy verify link" button (the QR lives in the PDF, not on this page), buttons Download PDF and Download proof.json. Skills: one `Card` per skill (stamp, name, category, date earned, description, source). Empty state: "No passport yet. Attend a BTU event to earn your first skill." |
| FE-41 (M8) ✅ | `/me/history` | `GET /api/me/versions` | `Table`: version · issued · skills · what changed (`added_skills`) · `StatusBadge` (Current / Superseded / Legacy, not verifiable) · Download (ANCHORED only)                                                                                                                                                                                                                                                                                                                               |
| FE-34 (M7) ✅ | `/me/events`  | `GET /api/me/events`   | `Table`: event · date · skill · status (`Waiting for organiser`, `Awarded in vN` linking to `/me`, `Already held`, `Not confirmed`, `Event deleted`)                                                                                                                                                                                                                                                                                                                                        |

**Done when (M8):** signed in as `btu-t-0002@example.org`, the student sees only BTU-AI-000126 and can download its PDF; requesting another student's PDF URL returns 404 (A8).

## 5. Admin pages (M6)

The five pages both roles use, inside `AdminShell` with `<RequireRole role="admin">` in `admin/layout.tsx`. Each form uses react-hook-form + zod mirroring the server rules, and `applyServerErrors` for whatever the server rejects.

### FE-20 Admin shell ✅

`AdminShell` (§2) with the user's email and role in the sidebar footer and Sign out. Super admin group hidden for `ADMIN`.

### FE-21 Dashboard `/admin` ✅

`GET /api/admin/dashboard`, refetch every 15 s. Four `Card` counters, each a link to a filtered list: check-in open now → `/admin/events?status=CHECKIN_OPEN`; waiting to be marked done → `?status=CHECKIN_CLOSED`; Unregistered check-ins → events list; failed issuances → `/admin/issuance?tab=failed`. Recent activity `Table` (last 10 versions). Quick action buttons: Register student, Direct award, Create event (super admin only).

### FE-22 Students `/admin/students` and `/admin/students/new` ✅

- List: `DataTable` on `GET /api/admin/students` with search (debounced 300 ms) and selects for program (`GET /api/admin/programs`), level, status, has passport. Columns: Student ID · name · program · Passport ID · current version · `StatusBadge`. Row click → detail. Buttons: Register student; Import CSV shown disabled with a "Coming later" tooltip (Should-have, not in this plan).
- Register form (`/new`): fields and rules from Web App Design A2 (Student ID, first and last name ≤ 60, BTU email, program as a select with free entry, level, status). `POST /api/admin/students` → toast "Student registered — Passport ID BTU-AI-000143" → detail page. Pre-fill `email` from `?email=` (used by Event detail for Unregistered rows).

### FE-23 Student detail `/admin/students/[id]` ✅

`GET /api/admin/students/{id}`. Sections as `Card`s: Profile (edit inline with a form; frozen fields show a lock icon and the note "Printed on issued passports"; on `warnings: ["printed_name_differs"]` show an `Alert`), Passport (versions `Table` with `StatusBadge`, Download for ANCHORED, Retry for FAILED), Skills (`Table`: skill, date earned, source link, awarded by), Events (`Table`).

### FE-24 Direct award `/admin/awards/new` (right after M5) ✅

Two steps on one page:

1. **Form:** `StudentPicker` (at least 1; pre-fill from `?student=`), skill `Select` with stamp preview (active skills from `GET /api/admin/skills`), date earned (`type="date"`, default today, max today), reason `Textarea` (required, ≤ 300). "Review" → `POST /api/admin/awards/preview`.
2. **Review:** `Table` of rows; `SKIP_ALREADY_HELD` rows greyed out with "already holds this skill"; `NEW_VERSION` rows show `v2 → v3`. "Confirm and issue" → `POST /api/admin/awards` with an `Idempotency-Key` generated **once when the review step opens** (`crypto.randomUUID()`), so a double click or retry reuses it. Success → toast and redirect to `/admin/issuance?tab=in-progress`.

### FE-25 Issuance `/admin/issuance` ✅

`Tabs`: Failed · In progress (PENDING, RENDERED, ANCHORING) · Recent (ANCHORED, newest first). `DataTable` on `GET /api/admin/versions?status=…`, refetch every 5 s on In progress. Columns: student · Passport ID · version · `StatusBadge` · error · time. Retry per row; "Retry all failed" with `ConfirmDialog`.

**Done when (M6):** sign in as `admin@btu.test`, register a new student, award them a skill, watch it go PENDING → ANCHORED on the Issuance page, and verify their PDF on `/verify`; a form submitted with a future date shows the error under the date field (A9).

## 6. Super admin pages

Events (M7) first, because they are the main award path; then catalog, roles and audit (M9). Write controls are hidden for `ADMIN`, who gets read-only views of Events, Skills and Categories.

### FE-30 Events list and form (M7) — `/admin/events`, `/new`, `/[id]/edit` ✅

- List: `Tabs` by status (Draft · Check-in open · Check-in closed · Completed) on `GET /api/admin/events?status=`. Columns: name · skill · date · participants · `StatusBadge`. "Create event" for super admins.
- Form: fields from Web App Design A6. Inputs use local time (`datetime-local`), sent as UTC ISO. When the end time changes and the window fields are untouched, update their suggested values (end − 15 min, end + 30 min). On edit, the skill `Select` is disabled with the note "Locked: participants have checked in" when the server returns 409 `skill_locked` or the detail shows participants.

### FE-31 Event detail (M7) — `/admin/events/[id]` ✅

`GET /api/admin/events/{id}` plus `GET .../participants` polled every 3 s while the status is CHECKIN_OPEN (every 15 s otherwise).

| Section      | Contents and actions                                                                                                                                                                                                                                                                             |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Header       | Name, `StampImage` + skill, date, location, `StatusBadge`, Edit (hidden when COMPLETED)                                                                                                                                                                                                          |
| Check-in     | Window times; buttons by status: Open check-in now (DRAFT), Close check-in now (OPEN), Reopen (CLOSED); "Open presenter view" opens `/present` in a new tab                                                                                                                                      |
| Participants | `Table`: name · Student ID · time · method · flags as `Badge`s (Unregistered, Already holds skill). Row actions: Remove (`ConfirmDialog`); for Unregistered rows "Register student" → `/admin/students/new?email=…` in a new tab. "Add participant" opens `StudentPicker` (single select) → POST |
| Complete     | "Mark as done" — disabled with the blocker reasons from `complete_blockers` (e.g. "2 Unregistered participants")                                                                                                                                                                                 |
| Danger zone  | "Delete event" with `ConfirmDialog`; hidden when COMPLETED                                                                                                                                                                                                                                       |

**Mark as done dialog:** an `AlertDialog` that lists who will receive the skill and who is skipped (computed from the participant flags), states the date earned, and has a checkbox "I checked the participant list" that enables Confirm. Confirm → `POST .../complete`. Afterwards the page is read-only and shows the `completion` block from `EventDetail` (awarded students with their new version number, skipped students), each linking to the student's detail page, plus a link to the Issuance page for live status.

### FE-32 Presenter view (M7) — `/admin/events/[id]/present` ✅

Full-screen page with no shell: event name (large), the QR from `GET .../qr` (`svg` rendered with `dangerouslySetInnerHTML` — the SVG comes from our own server), the short URL as text, and "N checked in". Refetch `.../qr` when `refresh_in_seconds` runs out (and at least every 30 s); when status isn't CHECKIN_OPEN show "Check-in closed" instead of the QR.

### FE-50 Skills (M9) — `/admin/skills` ✅

`Table` with an "Include archived" `Checkbox`; columns: Skill ID · name · category (with stamp) · times awarded · status. "Add skill" and Edit open a `Dialog` form (name ≤ 80, category `Select`, description ≤ 300 with a character counter that warns past 150). Note in the form: "Changes apply to future passport versions only." Row menu (`dropdown-menu`): Archive / Unarchive, and Delete only when `times_awarded` is 0 (server 409 `in_use` shown as a toast otherwise).

### FE-51 Categories & stamps (M9) — `/admin/categories` ✅

`Table`: stamp · name · badge code · skills. "Add category" `Dialog` (name). Per row: Upload stamp (file `Input`, PNG/SVG, client checks ≤ 1 MB and longest side ≥ 300 px before `POST .../stamp`; the server re-checks), Rename, Archive, Delete (only with 0 skills). The note "A new stamp appears on future versions only" sits by the upload.

### FE-52 Admins & roles (M9) — `/admin/roles` ✅

`Table`: name · email · role · granted by · granted on · last sign-in. "Add admin" `Dialog`: BTU email + role `Select` → `PUT /api/admin/roles/{email}`. Row actions: Change role, Revoke (`ConfirmDialog`: "They will be signed out immediately"). The last super admin's Revoke button is disabled with a tooltip explaining why.

### FE-53 Audit log (M9) — `/admin/audit` ✅

`DataTable` on `GET /api/admin/audit` with filters: person (email), action (select), date range (two date inputs). Columns: time · who · action · entity (link where a page exists) · details. Details expand to show `before` and `after` as formatted JSON.

## 7. Frontend tests

Unit tests for the logic that could silently be wrong (hashing, proofs, code formatting); end-to-end tests for the flows the jury will see.

| Tool       | Location                   | Covers                                                                                                            | When        |
| ---------- | -------------------------- | ----------------------------------------------------------------------------------------------------------------- | ----------- |
| Vitest     | `web/tests/merkle.test.ts` | `processProof` and `leafFromPdfSha256` against `shared/merkle-vectors.json` (BC-05)                               | M1          |
| Vitest     | `web/tests/format.test.ts` | Code formatting and normalising (same cases as the Python tests), verdict → headline mapping, `applyServerErrors` | M5          |
| Playwright | `web/e2e/`                 | The flows below, against the full dev stack; sign-in codes are read from Mailpit's REST API                       | M10 (FE-60) |

### FE-60 End-to-end flows (M10)

1. **Thin slice:** sign in as `admin@btu.test` (code read from Mailpit) → direct award to BTU-T-0021 → wait for ANCHORED on the Issuance page → download the PDF → upload it on `/verify` → "Valid" → upload a copy with one byte changed → "Not valid".
2. **Event:** sign in as `superadmin@btu.test` → create an event → open check-in → a second browser context signed in as a student opens the check-in URL (fetch the current URL from `GET .../qr`) → checks in → the participant appears → close → Mark as done → the student's `/me/events` shows "Awarded in vN".
3. **Access:** a student opening `/admin` sees the no-access alert, and `GET /api/admin/students` returns 403.

Run with `make e2e`; the Infra tab lists the services it needs.
