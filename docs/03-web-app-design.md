# BTU AI Skills Passport — Web App Design

Oct 21, 2026 · @Nikoloz Atanelishvili

## 1. Overview

One web app, three areas, 19 pages. Skills now reach students mainly through **events**: a super admin creates an event for a skill, students scan a QR code at the end to check in, and marking the event done awards the skill to every confirmed participant. The direct award form stays for exceptions (a skill earned outside an event, a correction).

| Area           | URL                                       | Who                            | Purpose                                                                                                       |
| -------------- | ----------------------------------------- | ------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| Public         | `/`, `/verify`, `/v/{code}`, `/checkin/…` | Anyone; check-in needs sign-in | Verify passports; landing page for event check-in                                                             |
| Student portal | `/me/…`                                   | Signed-in students             | View and download own passport, see check-ins                                                                 |
| Admin panel    | `/admin/…`                                | Admin, Super admin             | Students, direct awards, issuance status; super admin also gets events, catalog, categories, roles, audit log |

**Navigation.** The admin panel has a left sidebar with two groups. _Operations_ (both roles): Dashboard, Students, Direct award, Issuance. _Super admin_ (hidden for Admins): Events, Skills, Categories & stamps, Admins & roles, Audit log. Admins can open Events read-only from the dashboard. The student portal has a top bar: My passport, History, My events. Public pages have a minimal header with "Verify a passport" and "Sign in".

**Conventions on every form:** required fields marked, server-side validation with errors shown under each field, a "Review" step before anything that issues passports or can't be undone, a success toast with a link to what changed, and every change written to the audit log.

## 2. Sitemap

&#91;embedded content: sitemap · 19 pages in 4 groups\]

The one link between the areas is the event QR: shown on the super admin's presenter view, it opens the public check-in page, and each check-in then appears in the Event detail participant list.

## 3. Events: how a skill reaches a student

Attendance decides who gets a skill: an event is tied to one catalog skill, its participants are whoever checked in by QR (plus anyone the super admin adds by hand), and nothing reaches a passport until the super admin reviews the list and marks the event done.

&#91;embedded content: event lifecycle · 4 states + delete\]

### End to end

1. **Create.** Super admin creates the event: name, skill, date and time, location, check-in window. Status _Draft_.
2. **Open check-in.** At the window's start time (or by pressing _Open check-in now_) the status becomes _Check-in open_. The organiser opens **Presenter view** on the room's screen: a full-screen QR and a live participant count.
3. **Scan.** A student scans the QR with their phone camera. It opens `/checkin/{event}?t={token}`.
4. **Sign in.** If not signed in, the email-code sign-in (P4), then straight back to the check-in page.
5. **Confirm.** The student sees the event name, the skill with its stamp, and the date, and taps **Check in**. They appear in the participant list within seconds.
6. **Close.** At the window's end (or _Close check-in now_) the status becomes _Check-in closed_. Late scans see "Check-in has closed".
7. **Review.** Super admin checks the list: removes anyone who wasn't there, adds anyone who couldn't scan, and registers or removes _Unregistered_ sign-ins.
8. **Mark as done.** A review dialog states who gets the skill and who is skipped. On confirm, one award per participant is created (date earned = event date) and each student's passport gets a new version through the normal issuance pipeline. Status _Completed_, read-only from then on.

### Rules that keep it honest

- **The QR changes every 30 seconds.** Its token is derived from the event's secret and the current 30-second window; the server accepts the current and the previous window only. A photo of the QR sent to someone at home stops working within a minute. It does not stop a friend forwarding the live code in real time, which is why step 7 (review) exists.
- **One check-in per student per event.** Scanning again just shows "You're checked in".
- **The skill is locked once someone has checked in**, so nobody checks in for one skill and receives another.
- **Unregistered sign-ins.** A BTU account with no student record (not yet imported) is still recorded, as _Unregistered_. The event can't be completed until each one is registered from the list or removed.
- **Already holds the skill.** The student can check in, is shown "You already have this skill", and is skipped at completion. No duplicate award, no needless new version.
- **Delete only before completion.** Draft, open and closed events can be deleted with their check-ins (logged). A completed event cannot: its skills are already anchored on the blockchain, which can't be undone.
- **Mark as done is idempotent.** The event itself is the idempotency key, so a double click or a retry creates nothing twice.

## 4. Public pages

Four pages need no admin rights; only check-in asks for sign-in. They must work well on a phone, since most traffic is an employer opening a link or a student scanning a QR.

### P1 Verify `/verify` (also the home page)

| Section      | Contents                                                                                         |
| ------------ | ------------------------------------------------------------------------------------------------ |
| Code entry   | One input, format `XXXX-XXXX-XX`; dashes and lower case accepted; **Verify** button              |
| PDF upload   | Drop zone: "Or check the PDF you received". The file is hashed in the browser and never uploaded |
| How it works | Three short lines: BTU issues, the blockchain records a fingerprint, anyone can check            |

### P2 Verify result `/v/{code}` (also the QR target printed on each passport)

| Section        | Contents                                                                                                |
| -------------- | ------------------------------------------------------------------------------------------------------- |
| Verdict banner | One of: Valid · Authentic, superseded by vN · Not valid · Unknown code · Not issued by BTU · Revoked    |
| Two checks     | Document check ✓/✗ and Issuer check ✓/✗, each with one line of explanation                              |
| Official data  | Name, Passport ID, version, issue date, skills list (stamp, name, date earned)                          |
| Compare        | "Download the official copy" (PDF) so the verifier can compare it with what they were sent              |
| Proof          | Collapsed: transaction link on the block explorer, contract address, Merkle root, `proof.json` download |

### P3 Check-in `/checkin/{event}?t={token}`

One page with five states, in this order:

1. **Not signed in** → redirect to sign-in, return here afterwards.
2. **Confirm** — event name, skill + stamp, date, location; big **Check in** button. A separate tap prevents accidental check-ins from link previews.
3. **Checked in** — "You're checked in. The skill will appear on your passport once the organiser completes the event." Link: My events.
4. **Already holds the skill** — checked in, with the note "You already have this skill; your passport won't change."
5. **Problem** — one message per case: QR expired ("Scan the code on the screen again"), check-in not open yet / closed, event not found, or _Unregistered_ ("You're checked in, but your account isn't in BTU's student records yet. The organiser will add you.")

### P4 Sign in `/login`

Passwordless, two steps on one page. **Step 1:** an email field, a **Send code** button, and a **Continue as guest** link that just opens Verify (P1); guests never sign in. The server accepts only allowed domains (`@btu.edu.ge`) and otherwise shows "Use your BTU email". **Step 2:** a 6-digit code field, **Sign in**, and **Resend code** (disabled for 60 s). Errors: "Wrong code, n tries left" and "Code expired, send a new one". After sign-in: admins land on the Dashboard, students on My passport, and a check-in sign-in returns to the check-in page.

## 5. Student portal

Three read-only pages: a student never edits anything, they only see and download what BTU issued and track their check-ins.

### S1 My passport `/me`

| Section                            | Contents                                                                                                                              |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Header                             | Full name, Passport ID, first issued date                                                                                             |
| Status banner (only when relevant) | "Issuing version 4…" while a new version is in progress                                                                               |
| Current version card               | Version number, issue date, verification code with Copy button, QR, **Download PDF**, Copy verify link, Download `proof.json`         |
| Skills                             | One card per skill, by date earned: stamp, name, category, date, description, and where it came from (event name or "Awarded by BTU") |
| Empty state                        | "No passport yet. Attend a BTU event to earn your first skill."                                                                       |

### S2 Version history `/me/history`

Table, newest first: version · issue date · number of skills · what changed ("+ AI Data Analysis") · status (Current / Superseded) · Download. The seed data's legacy V1 is listed as "Legacy, not verifiable".

### S3 My events `/me/events`

Table, newest first: event · date · skill · status. Status is one of: _Waiting for organiser_ (checked in, event not completed), _Awarded in v4_ (links to S1), _Already held_, _Not confirmed_ (removed by the organiser), _Event deleted_.

## 6. Admin pages (Admin and Super admin)

Admins run day-to-day operations: keeping student records right, awarding skills earned outside events, and fixing failed issuances. Five pages.

### A1 Dashboard `/admin`

| Section         | Contents                                                                                                                                                    |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Needs action    | Counters that link to filtered lists: events with check-in open now · closed events waiting to be marked done · _Unregistered_ check-ins · failed issuances |
| Recent activity | Last 10 issued versions: student, version, time                                                                                                             |
| Quick actions   | Register student · Direct award · Create event (super admin only)                                                                                           |

### A2 Students `/admin/students`

Search by name, Student ID or email; filters: program, level, status, has passport. Table: Student ID · name · program · Passport ID · current version · issuance status. Buttons: **Register student**, **Import CSV** (Should).

**Register student form**

| Field                 | Type   | Rules                                                                   |
| --------------------- | ------ | ----------------------------------------------------------------------- |
| Student ID            | Text   | Required, unique, BTU format (Q16)                                      |
| First name, Last name | Text   | Required, ≤ 60 characters each; frozen once the first version is issued |
| BTU email             | Email  | Required, unique, must be a BTU domain                                  |
| Program               | Select | Required, from the program list                                         |
| Education level       | Select | Bachelor's / Master's / Doctoral                                        |
| Status                | Select | Active / Graduate                                                       |

On save the Passport ID is generated. The first version is issued when the student gets their first skill.

### A3 Student detail `/admin/students/{id}`

| Section  | Contents                                                                                                                                                      |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Profile  | Editable fields; frozen ones (name, Passport ID, first issued) show a lock and the note "Printed on issued passports; changing them needs a reissue decision" |
| Passport | Versions table with status and download; Retry on a failed version                                                                                            |
| Skills   | Each award: skill, date earned, source (event link or direct award), awarded by                                                                               |
| Events   | Check-ins and their status                                                                                                                                    |

### A4 Direct award `/admin/awards/new`

For skills earned outside an event. Step 1, the form:

| Field       | Type                       | Rules                                                                                 |
| ----------- | -------------------------- | ------------------------------------------------------------------------------------- |
| Students    | Multi-select search        | At least 1                                                                            |
| Skill       | Select, with stamp preview | Active catalog skills only                                                            |
| Date earned | Date                       | Not in the future, not before the student's first issued date                         |
| Reason      | Text                       | Required, ≤ 300 characters, goes to the audit log ("Course completion", "Correction") |

Step 2, review: one row per student with the resulting version ("v3 → v4"), and rows that will be skipped (already hold the skill) greyed out. **Confirm and issue**.

### A5 Issuance `/admin/issuance`

Tabs: Failed · In progress · Recent. Table: student · Passport ID · version · status · error message · time. Actions: **Retry** per row and **Retry all failed**.

## 7. Super admin pages

Seven pages, hidden from Admins: everything that decides _what_ gets awarded (events, skills, categories) and _who_ can award it (roles). Things already printed on issued passports are archived, never deleted.

### A6 Events `/admin/events`

Tabs by status: Draft · Check-in open · Check-in closed · Completed. Table: name · skill · date · participants · status. Button: **Create event**. (Admins see this list read-only.)

**Create / edit event form**

| Field                    | Type                       | Rules                                                                      |
| ------------------------ | -------------------------- | -------------------------------------------------------------------------- |
| Name                     | Text                       | Required, ≤ 120 characters                                                 |
| Skill                    | Select, with stamp preview | Required; active skills only; locked after the first check-in              |
| Description              | Textarea                   | Optional, ≤ 500 characters; shown to students on the check-in page         |
| Date, start and end time | Date + times               | Required; end after start                                                  |
| Location                 | Text                       | Optional                                                                   |
| Check-in opens / closes  | Date-times                 | Defaults: 15 min before the end / 30 min after the end; closes after opens |

### A7 Event detail `/admin/events/{id}`

| Section      | Contents                                                                                                                                                                                                                                                                                                 |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Header       | Name, skill + stamp, date, location, status; **Edit**                                                                                                                                                                                                                                                    |
| Check-in     | Window times; **Open check-in now** / **Close check-in now** / **Reopen**; **Open presenter view**                                                                                                                                                                                                       |
| Participants | Live list (refreshes every few seconds): name · Student ID · time · method (QR / Manual) · flags (_Unregistered_, _Already holds skill_). Row actions: **Remove**, and for _Unregistered_ rows **Register student** (opens the A2 form pre-filled with the email). **Add participant** searches students |
| Complete     | **Mark as done**, disabled with a reason while check-in is open or _Unregistered_ rows remain                                                                                                                                                                                                            |
| Danger zone  | **Delete event**, hidden once completed                                                                                                                                                                                                                                                                  |

**Mark as done dialog:** "23 students will receive _AI Data Analysis_, dated 21 Oct 2026. 2 already hold it and will be skipped." Lists both groups, plus a checkbox "I checked the participant list". **Confirm**. Afterwards the page turns read-only and shows each participant's issuance status (Issuing / Issued v4 / Failed).

### A8 Presenter view `/admin/events/{id}/present`

Full screen, made for a projector: event name, a large QR that refreshes every 30 s, the short link as text for anyone whose camera fails, and a live counter "37 checked in". Shows "Check-in closed" instead of the QR outside the window.

### A9 Skills `/admin/skills`

Table: Skill ID · name · category (with stamp) · times awarded · status (Active / Archived). **Add skill**.

| Field       | Type           | Rules                                                                                                              |
| ----------- | -------------- | ------------------------------------------------------------------------------------------------------------------ |
| Skill ID    | Auto (SKL-017) | Read-only                                                                                                          |
| Name        | Text           | Required, unique, ≤ 80 characters                                                                                  |
| Category    | Select         | Required                                                                                                           |
| Description | Textarea       | Required, ≤ 300 characters; printed on the passport (a length counter warns past 150, where the layout gets tight) |

Editing a name or description affects future versions only; the form says so. **Delete** appears only for skills never awarded and not used by any event; otherwise **Archive** (hidden from new events and awards, kept on existing passports).

### A10 Categories & stamps `/admin/categories`

Table: stamp image · category · badge code · number of skills. **Add category**.

| Field       | Type              | Rules                                                                                       |
| ----------- | ----------------- | ------------------------------------------------------------------------------------------- |
| Name        | Text              | Required, unique ("AI Skill", "AI Applied Skill", …)                                        |
| Badge code  | Auto (BDG-AI-004) | Read-only                                                                                   |
| Stamp image | Upload            | PNG or SVG, square, at least 600 × 600 px, ≤ 1 MB; preview shown on a passport page mock-up |

Replacing a stamp affects future versions only. **Delete** only when no skill uses the category, else **Archive**.

### A11 Admins & roles `/admin/roles`

Table: name · email · role · granted by · granted on · last sign-in. **Add admin**.

| Field     | Type   | Rules                                                   |
| --------- | ------ | ------------------------------------------------------- |
| BTU email | Email  | Required, BTU domain; the person needs no prior sign-in |
| Role      | Select | Admin / Super admin                                     |

Row actions: **Change role**, **Revoke**. Revoke asks for confirmation, takes effect on the next request and signs the person out. The last super admin can't be revoked or demoted, and the button says why.

### A12 Audit log `/admin/audit`

Read-only table, newest first: time · who · action · what (link) · details (before/after for edits). Filters: person, action type, date range. Export CSV (Could).

## 8. Permissions by page

The server enforces every row of this table; hiding a menu item is only a convenience. "View" means read-only.

| Page                           | Public           | Student       | Admin                                   | Super admin                                 |
| ------------------------------ | ---------------- | ------------- | --------------------------------------- | ------------------------------------------- |
| P1–P2 Verify, result           | ✓                | ✓             | ✓                                       | ✓                                           |
| P3 Check-in                    | sign-in required | ✓             | ✓ (as a participant, if also a student) | ✓                                           |
| S1–S3 Student portal           |                  | own data only |                                         |                                             |
| A1 Dashboard                   |                  |               | ✓                                       | ✓                                           |
| A2–A3 Students, register, edit |                  |               | ✓                                       | ✓                                           |
| A4 Direct award                |                  |               | ✓                                       | ✓                                           |
| A5 Issuance, retry             |                  |               | ✓                                       | ✓                                           |
| A6–A7 Events                   |                  |               | view                                    | create, edit, delete, open/close, mark done |
| A8 Presenter view              |                  |               |                                         | ✓                                           |
| A9 Skills                      |                  |               | view                                    | add, edit, archive, delete                  |
| A10 Categories & stamps        |                  |               | view                                    | add, edit, archive, delete                  |
| A11 Admins & roles             |                  |               |                                         | ✓                                           |
| A12 Audit log                  |                  |               |                                         | ✓                                           |

## 9. Open questions

Each has a default so building can start now.

| #   | Question                                                                                       | Default                                                        |
| --- | ---------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| Q14 | Should Admins also run events, or only super admins?                                           | Only super admins, as specified; Admins view events read-only  |
| Q15 | Can one event award more than one skill?                                                       | One skill per event in the MVP                                 |
| Q16 | What is the real Student ID format, and can BTU's registrar give a CSV of students?            | Format from the test data (BTU-T-0001); CSV import as a Should |
| Q17 | Is the default check-in window (15 min before the end to 30 min after) right for BTU's events? | Yes, editable per event                                        |
| Q18 | Should students be able to browse upcoming events?                                             | No in the MVP; events are announced outside the app            |
