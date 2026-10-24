# BTU AI Skills Passport — Requirements Analysis

Oct 21, 2026 · @Nikoloz Atanelishvili

## 1. Scope and stakeholders

The MVP has to prove four things end to end: a skill awarded through the admin panel becomes a new passport version without manual work; every issued version is anchored on a blockchain; a verifier can confirm both that the PDF is unaltered and that BTU issued it; and a student can log in and download their own passport. Everything else is secondary.

| Stakeholder | What they need from the system | Auth |
| --- | --- | --- |
| BTU administrator | Award verified skills through the admin panel and see each passport's issuance status and errors | Email code to a BTU address + admin role |
| Student | View and download the latest passport (and older versions) | Email code to a BTU address |
| Third-party verifier (employer) | Enter a verification code or upload a PDF and get a clear verdict | None |
| BTU (as issuer) | A publicly checkable identity bound to the signing key | Holds the issuer key |
| Hackathon jury / mentors | A live demo including a tamper test | n/a |

**In scope for the MVP:** admin panel (role-restricted forms for students, skills and awards), events with QR check-in, passport ID allocation, PDF rendering from BTU's template, versioning, on-chain anchoring, issuer identity proof, public verify page, student portal.

**Out of scope (state this explicitly to the jury):** skill approval workflow (the dataset says awards are already verified), production key custody (HSM), integration with BTU's own identity provider (SSO), mainnet deployment, mobile apps.

**Change on 2026-10-21:** the Google Sheet is only a picture of the database schema and the seed data, not a live data source. Administrators enter data through an admin panel that only they can reach; the Sheet's columns become database tables (section 7).

**Change on 2026-10-24:** sign-in is a passwordless one-time code emailed to the user's BTU address, built into the app. Keycloak, OIDC single sign-on and the staff second factor (MFA) are dropped; verifiers never sign in (section 6).

**How these requirements were gathered.** Elicitation so far is document analysis (the brief and the test dataset) plus mentor Q&A. User stories and use cases (sections 2–3) are the techniques used to *record and structure* what was elicited; the FR/NFR tables (sections 4–5) are derived from them, and every requirement points back to its story.

## 2. User stories

Twenty-two stories across four roles cover every mandatory brief requirement plus the admin-panel change. Format: *As a \[role\], I want \[goal\], so that \[reason\]*; the acceptance criteria are what a mentor would check in the demo.

| ID | Story | Acceptance criteria | Produces |
| --- | --- | --- | --- |
| US-01 | As an **admin**, I want to sign in with a one-time code sent to my BTU email, so that nobody without access to that inbox can issue passports. | A BTU user without the admin role gets 403 on every admin page and API call; a code works once and expires after 10 minutes. | FR-01, NFR-04, NFR-05 |
| US-02 | As an **admin**, I want to register a new student, so that they get a permanent passport. | Duplicate Student ID or email is rejected; Passport ID is generated once and never changes. | FR-02, FR-10 |
| US-03 | As an **admin**, I want to award a skill by picking it from the catalog, so that I never retype names or descriptions. | Name, category, badge and description come from the catalog; a future date or a skill the student already holds is rejected. | FR-03, FR-04, FR-17 |
| US-04 | As an **admin**, I want to award one skill to a whole group in one submission, so that a cohort of 200 takes minutes. | One submission creates exactly one new version per student. | FR-05, FR-13 |
| US-05 | As an **admin**, I want to see each passport's issuance status and retry failures, so that no student is silently stuck on an old version. | Failed issuances are listed with the error and a Retry button; a retry never duplicates a version. | FR-06, FR-14, FR-22 |
| US-06 | As a **super admin**, I want to grant and revoke admin access, so that staff turnover doesn't leave stale accounts. | Revocation takes effect on the next request, not at session expiry. | FR-08 |
| US-07 | As a **super admin**, I want to add or edit catalog skills, so that new courses can award new skills. | Editing a skill's text does not change any already issued version. | FR-07 |
| US-08 | As a **super admin**, I want a log of who awarded what and when, so that every skill is traceable to a person. | Each award, edit and role change shows actor, time and before/after values; log is read-only. | FR-09, NFR-10 |
| US-09 | As a **student**, I want to sign in with my BTU email and download my latest passport, so that I can attach it to job applications. | I can see only my own passport; changing an ID in the URL returns 403/404. | FR-25, NFR-05 |
| US-10 | As a **student**, I want my Passport ID to stay the same as I earn skills, so that links I've already shared keep working. | After a new award, the Passport ID is unchanged and the old link resolves to the latest version. | FR-10, FR-12, FR-15 |
| US-11 | As an **employer**, I want to enter the code printed on a passport without creating an account, so that I can check it in seconds. | Valid code shows name, Passport ID, version, issue date, skills and a verdict; no login prompt. | FR-18, FR-23 |
| US-12 | As an **employer**, I want to upload the PDF I received, so that I know nobody edited it. | An unmodified PDF → Valid; one changed character → Not valid. | FR-19, FR-20, FR-23 |
| US-13 | As an **employer**, I want to know if the version I hold is outdated, so that I can ask for the current one. | Older version → "Authentic, superseded by vN". | FR-15, FR-24 |
| US-14 | As an **employer**, I want proof that BTU itself issued the passport, so that a look-alike issuer can't fool me. | Verdict shows the issuer check separately and fails for an anchor from any non-BTU key. | FR-21 |

**Added 2026-10-21: events and categories.** Events are now the main way a skill reaches a student; the direct award (US-03, US-04) stays for exceptions.

| ID | Story | Acceptance criteria | Produces |
| --- | --- | --- | --- |
| US-15 | As a **super admin**, I want to create an event tied to one skill, so that attendance decides who receives it. | Event saved as Draft with skill, date, location and check-in window; skill locked after the first check-in. | FR-26, FR-27 |
| US-16 | As a **student**, I want to scan a QR at the end of the event and sign in, so that I get the skill without paperwork. | Scan → sign in → Check in; I appear in the participant list within seconds; scanning twice changes nothing. | FR-29 |
| US-17 | As a **super admin**, I want the QR to change every 30 seconds, so that a photo sent to someone absent stops working. | A token older than 60 s is rejected with "Scan the code on the screen again". | FR-28 |
| US-18 | As a **super admin**, I want to review, remove and add participants before marking the event done, so that only real attendees get the skill. | Remove and manual add are logged; Mark as done is blocked while check-in is open or Unregistered rows remain. | FR-30, FR-31 |
| US-19 | As a **super admin**, I want marking an event done to award the skill to every participant at once, so that nobody is typed in by hand. | One award per participant, dated the event date; holders of the skill skipped; repeat click creates nothing. | FR-32 |
| US-20 | As a **super admin**, I want to delete an event created by mistake, so that lists stay clean. | Draft, open and closed events can be deleted; completed events cannot. | FR-27 |
| US-21 | As a **student**, I want to see my check-ins and their status, so that I know when the skill will appear. | Each check-in shows Waiting / Awarded in vN / Already held / Not confirmed / Event deleted. | FR-33 |
| US-22 | As a **super admin**, I want to manage categories and their stamp images, so that new badge types can be added. | Add, edit, archive; delete only if unused; a new stamp affects future versions only. | FR-34, FR-35 |

## 3. Use cases

Seven use cases carry the system: stories say *what* each role wants, use cases say *how the interaction runs*, including what happens when it goes wrong. Actors: Admin, Super admin, Student, Verifier (anonymous), and two system actors — the Signing service and the Blockchain.

### UC-01 Award skills and issue a new version

**Actor:** Admin · **Precondition:** admin signed in; student exists · **Trigger:** student completed a skill · **Covers:** US-03, US-04, US-05

1. Admin opens the award form and selects one or more students.
2. Admin picks a skill from the catalog and enters the date earned.
3. System validates: role, catalog skill exists, date ≤ today and ≥ first-issued date, skill not already held.
4. System saves the award(s) and shows a review screen: student, skill, badge, resulting version number.
5. Admin confirms.
6. System builds the new version (skills sorted by date earned), generates a verification code, renders the PDF from BTU's template and hashes it.
7. Signing service anchors the hash (batched) on the blockchain; system marks the version ANCHORED and makes it the latest.
8. Admin sees status "Issued vN".

**Alternatives:** 3a validation fails → form shows the field error, nothing is saved. 6a/7a render or anchoring fails → version stays RENDERED/FAILED, is not downloadable or verifiable, appears in the retry list (US-05). 5a admin cancels → awards discarded. **Postcondition:** same Passport ID, new anchored version, audit-log entry naming the admin.

### UC-02 Register a student and issue the first passport

**Actor:** Admin · **Covers:** US-02, US-10

1. Admin enters Student ID, first and last name, BTU email, program, level, status.
2. System rejects duplicates (Student ID or email), then creates the Passport ID and records the first-issued date.
3. Flow continues as UC-01 from step 2 for the first skill; that version is v1.

**Alternative:** 2a student already exists → system opens their record instead of creating a second passport. **Postcondition:** name, Passport ID and first-issued date are frozen.

### UC-03 Verify a passport

**Actor:** Verifier (no account) · **Covers:** US-11 – US-14

1. Verifier opens the public verify page (or scans the QR on the PDF).
2. Verifier enters the verification code **or** uploads the PDF.
3. System finds the version (by code, or by the uploaded file's SHA-256).
4. System checks the Merkle proof against the on-chain root (document check) and that the root was written by BTU's published address (issuer check).
5. System shows the verdict and the official data: name, Passport ID, version, issue date, skills.

**Alternatives:** 3a no match for an uploaded file → "Not valid: this file does not match any passport BTU issued". 3b unknown code → "Unknown code" (rate-limited). 5a version is not the latest → "Authentic, superseded by vN". 4a issuer check fails → "Not issued by BTU".

### UC-04 Student views and downloads a passport

**Actor:** Student · **Covers:** US-09, US-10

1. Student signs in with their BTU email (one-time code).
2. System looks up the passport linked to that email.
3. Student sees the latest version and the version history; downloads a PDF.

**Alternatives:** 2a no passport yet → "No passport issued yet". 3a request for another student's passport → 404, attempt logged.

### UC-05 Manage admin access

**Actor:** Super admin · **Covers:** US-06, US-08

1. Super admin opens the access page and searches a BTU user.
2. Grants or revokes the Admin role.
3. System applies it on the user's next request and logs the change.

**Alternative:** 2a super admin tries to remove the last super admin → refused.

### UC-06 Check in at an event

**Actor:** Student · **Precondition:** event status Check-in open; QR shown in presenter view · **Covers:** US-16, US-17

1. Student scans the QR; it opens the check-in page with the current token.
2. If not signed in, the student signs in with a one-time email code and returns to the page.
3. System checks the token (current or previous 30 s window) and the event status.
4. System shows the event name, skill with stamp, and date; student taps Check in.
5. System records the check-in and the participant list updates.

**Alternatives:** 3a token expired → "Scan the code on the screen again". 3b check-in not open or closed → message, nothing recorded. 5a already checked in → success shown again, nothing new recorded. 5b signed-in email has no student record → recorded as Unregistered. 5c student already holds the skill → recorded and flagged; skipped at completion.

### UC-07 Complete an event

**Actor:** Super admin · **Precondition:** status Check-in closed · **Covers:** US-18, US-19

1. Super admin reviews the participant list; removes non-attendees, adds missing students, registers or removes Unregistered rows.
2. Super admin clicks Mark as done; system shows who receives the skill and who is skipped.
3. Super admin confirms.
4. System creates one award per eligible participant (date earned = event date) in one submission keyed by the event, and issues new versions as in UC-01 from step 6.
5. Event becomes Completed and read-only; the page shows each participant's issuance status.

**Alternatives:** 2a Unregistered rows remain → Mark as done disabled with the reason. 3a repeated confirm → nothing created twice. **Postcondition:** every eligible participant's passport has a new anchored version (or a Failed version in the retry list).

## 4. Functional requirements

35 testable requirements, grouped by module. "Source" is the brief section (§), the 2026-10-21 admin-panel change (*update*), or *derived* when needed to satisfy something else. The "Stories" column traces each one back to section 2.

| ID | Requirement (testable) | Source | Stories |
| --- | --- | --- | --- |
| **Admin panel** |  |  |  |
| FR-01 | Admin pages and admin APIs are reachable only by authenticated users holding an admin role; everyone else gets 403. | *update* | US-01 |
| FR-02 | Admin can register a student (Student ID, first/last name, BTU email, program, level, status); required fields and email format are validated; duplicate Student ID or email is rejected. | *update*, §1 | US-02 |
| FR-03 | Admin awards a skill by choosing it from the catalog; name, category, badge and description are filled from the catalog, not typed. | *update*, §4 | US-03 |
| FR-04 | Award validation: date earned is not in the future and not before the first-issued date; the student does not already hold the skill. | *derived* | US-03 |
| FR-05 | Admin can award one skill to many students in one submission. | *update*, §10 | US-04 |
| FR-06 | Admin sees each passport's status (Issuing / Issued / Failed), current version, last issued time and error, and can retry a failure. | *update* | US-05 |
| FR-07 | Super admin can create and edit catalog skills; edits never change already issued versions. | *update* | US-07 |
| FR-08 | Super admin can grant and revoke the Admin role; the last super admin cannot be removed. | *update* | US-06 |
| FR-09 | Every award, edit and role change is written to an append-only audit log (actor, time, before/after). | *derived* | US-08 |
| **Passport and versioning** |  |  |  |
| FR-10 | Each student has exactly one Passport ID, generated once, never changed or reused. | §1 | US-02, US-10 |
| FR-11 | First name, last name, Passport ID and first-issued date are frozen at creation; later edits to the student record do not change issued content and are flagged. | §1 | US-10 |
| FR-12 | A new award produces a new version of the existing passport, never a new passport. | §4, §8 | US-10 |
| FR-13 | All awards for one student confirmed in one submission produce one version, not several. | *derived* | US-04 |
| FR-14 | Issuance is idempotent: a resubmitted form or a retry never duplicates an award or a version. | *derived* | US-05 |
| FR-15 | The system returns the latest valid version for any Passport ID. | §8 | US-10, US-13 |
| **PDF** |  |  |  |
| FR-16 | Each version is one multi-page PDF rendered automatically from BTU's template. | §1, §3 | US-09 |
| FR-17 | Each skill entry shows name, badge/stamp, date earned and description; the badge is derived from the skill's category (3 stamps). | §4 | US-03 |
| FR-18 | Each version carries a unique verification code, printed as text and as a QR code. | §7 | US-11 |
| **Blockchain** |  |  |  |
| FR-19 | Every issued version's hash is anchored on a blockchain with a timestamp. | §5 | US-12 |
| FR-20 | Changing any byte of an issued PDF makes verification fail. | §5 | US-12 |
| FR-21 | Anchors can be written only by BTU's issuer key, and that key is publicly bound to BTU. | §6 | US-14 |
| FR-22 | A version that failed rendering or anchoring is not downloadable or verifiable and goes to a retry queue. | *derived* | US-05 |
| **Verification and student access** |  |  |  |
| FR-23 | Public verify page accepts a code or a PDF upload; no account or login. | §7 | US-11, US-12 |
| FR-24 | Verifying an older version returns "Authentic, superseded by vN". | §8 | US-13 |
| FR-25 | A student signs in with their BTU email and can view and download only their own passport and its versions. | §9 | US-09 |

**Events and catalog (added 2026-10-21)**

| ID | Requirement (testable) | Source | Stories |
| --- | --- | --- | --- |
| FR-26 | Super admin can create and edit an event: name, one skill, description, date and times, location, check-in window; the skill can't change after the first check-in. | *update* | US-15 |
| FR-27 | Event status runs Draft → Check-in open → Check-in closed → Completed (closed can reopen); delete is allowed before Completed only, and Completed is read-only. | *update* | US-15, US-20 |
| FR-28 | Presenter view shows a QR whose token changes every 30 s; the server accepts only the current and previous token. | *update* | US-17 |
| FR-29 | Check-in requires BTU sign-in, a valid token and an open window; one check-in per person per event. | *update* | US-16 |
| FR-30 | A signed-in user with no student record is recorded as Unregistered; the event can't be completed until each is registered or removed. | *derived* | US-18 |
| FR-31 | Super admin can add a participant manually and remove any participant before completion; both are logged. | *update* | US-18 |
| FR-32 | Mark as done creates one award per participant dated the event date, skips holders of the skill, uses the event as the idempotency key, and issues through FR-12 – FR-14. | *update* | US-19 |
| FR-33 | Students see their check-ins with status Waiting / Awarded in vN / Already held / Not confirmed / Event deleted. | *update* | US-21 |
| FR-34 | Super admin manages categories with a stamp image (PNG/SVG, square, ≤ 1 MB); replacing a stamp affects future versions only. | *update* | US-22 |
| FR-35 | A skill or category that was ever awarded or used is archived, not deleted; archived items are hidden from new events and awards. | *derived* | US-22 |

## 5. Non-functional requirements

The real load is versions, not passports. The test data averages 3.3 skills per student (60 awards / 18 students), so 5,000 passports a year is about 17,000 versions if each award is issued separately; the target below is 25,000 for headroom. One blockchain transaction per version does not scale on cost, hence batching.

| ID | Category | Requirement |
| --- | --- | --- |
| NFR-01 | Scalability | ≥ 5,000 passports and ≥ 25,000 versions per year; many version hashes anchored per transaction (Merkle root). |
| NFR-02 | Throughput | A bulk award to 500 students is issued in one background run, with no manual step per student. |
| NFR-03 | Privacy | No personal data on-chain — only hashes / Merkle roots. The verify page shows only name, Passport ID, version, issue date and skills. |
| NFR-04 | Security: authentication | Everyone signs in with a one-time code emailed to their BTU address; the app stores no passwords, only a hash of each code (10-minute expiry, single use, at most 5 attempts, rate-limited per email and per IP). Sessions expire after 8 h, or 30 min idle, for admins. |
| NFR-05 | Security: authorization | Checked on the server for every request, deny by default; role checks for admin actions and ownership checks for student data (no access by guessing an ID). |
| NFR-06 | Security: issuer key | The issuer private key lives only in the signing service's secret store; it is never in the repo, the database or any browser, and no admin can export it. |
| NFR-07 | Security: web | HttpOnly + Secure + SameSite cookies; CSRF tokens on every form; server-side validation of all input; rate limits on sign-in and on the verify endpoint. |
| NFR-08 | Integrity | Issued PDFs are immutable and stored by content hash; a re-render never overwrites an issued version. |
| NFR-09 | Availability | PDF-upload verification works from chain data alone if BTU's server is down. |
| NFR-10 | Auditability | Append-only issuance ledger (version, hash, tx, award IDs, time) and admin audit log; neither can be edited from the admin panel. |
| NFR-11 | Usability | Awarding one skill to one student takes under 30 s for a trained admin; the verifier gets a one-line verdict in under 3 s. |
| NFR-12 | Localisation | Georgian names and text render correctly in the PDF and the admin panel (embedded Georgian font, UTF-8 end to end). |
| NFR-13 | Determinism | Same data + template → byte-identical PDF (fixed metadata and timestamps), so hashes are reproducible in tests. |

## 6. Authentication and authorization (recommendation)

Sign everyone in with a one-time code emailed to their BTU address (passwordless, no external identity provider), keep roles in your own database (role-based access control), and keep the blockchain key in a separate signing service that no human session can reach. Authentication answers *who are you*; authorization answers *what may you do* — they are separate layers.

### Who signs in, and how

| Actor | Authentication | Authorization |
| --- | --- | --- |
| Super admin, Admin | 6-digit code emailed to the BTU address; no second factor (accepted trade-off: whoever controls the inbox controls the account) | Role from the app's `user_roles` table (an allowlist), re-checked on every request |
| Student | Same email code | Ownership only: can read the passport whose student email matches the session |
| Verifier | None. "Continue as guest" just opens the public Verify page; there is no guest session | Public, read-only, rate-limited endpoints that return the minimum data |
| Signing service | Service credential, not a user | Accepts signing jobs only from the issuance worker over an internal queue |

**Why roles can't come from the email domain:** every student also has a BTU address, so "signed in with @btu" proves membership, not admin rights. The allowlist table (later: BTU IT's directory groups, if SSO is ever added) is what makes someone an admin.

### Permissions by role

| Permission | Super admin | Admin | Student | Verifier |
| --- | --- | --- | --- | --- |
| Grant / revoke roles | ✓ |  |  |  |
| Edit skill catalog | ✓ |  |  |  |
| Register / edit students | ✓ | ✓ |  |  |
| Award skills and issue versions | ✓ | ✓ |  |  |
| Retry failed issuance | ✓ | ✓ |  |  |
| View audit log | ✓ |  |  |  |
| View all passports | ✓ | ✓ |  |  |
| View / download own passport |  |  | ✓ |  |
| Verify a passport | ✓ | ✓ | ✓ | ✓ |
|  |  |  |  |  |

### Rules to implement

- Enforce every check in backend middleware or per-endpoint guards. Hiding a button in the UI is cosmetic, not security.
- Scope student queries by the session (`WHERE student_id = session.student_id`), never by an ID from the URL — this blocks the classic "change the number in the URL" attack (IDOR).
- Read the role from the database on each request (or cache ≤ 1 min) so a revoked admin is locked out immediately (US-06).
- Use server-side sessions in HttpOnly cookies rather than tokens in `localStorage`; add CSRF tokens to every admin form.
- **Email codes:** check the email domain on the server against an allowlist (`ALLOWED_EMAIL_DOMAINS`: `btu.edu.ge`, plus `example.org` in dev because the seed students use it). Store only a hash of the code; 10-minute expiry, single use, 5 wrong tries kill it, and rate-limit code requests per email and per IP.
- **Separate admin from signer.** An admin action only queues a job; the signing service holds the key and signs hashes produced by the issuance worker. A stolen admin session can create a wrong award (logged and revocable), but can never take BTU's key.
- Record the session's user ID on every privileged action in the audit log.
- *Could:* require a fresh sign-in (< 15 min) before confirming an issuance, since anchoring can't be undone; a second admin's approval for bulk awards above a threshold.

### For the hackathon

Email-code login is built into the API (a few hundred lines), so there is no identity provider to set up. In development, Mailpit catches every outgoing email so you can read codes without a real mailbox; for the demo, send through an SMTP account (BTU mail, a Gmail app password, or Resend/Mailgun). Seed `user_roles`, and demo three users: super admin, admin, student, showing the student getting 403 on the admin panel.

## 7. Test dataset analysis (schema and seed data)

The Sheet is now the schema reference and seed data, not a live source. It is internally clean but encodes several states the system must handle: 60 skill records for 18 students, 16 catalog skills, 3 badges, 16 records SYNCED (V1) and 44 NOT SYNCED. No duplicate Record IDs, no student holds the same skill twice, and every student's personal fields and every skill's catalog fields are consistent across rows.

### Shape

| Fact | Value |
| --- | --- |
| Students / records | 18 / 60 |
| Records per student | 1 (4 students), 3 (6), 4 (5), 6 (3) |
| Catalog | SKL-001 … SKL-016 |
| Category → badge | AI Skill → BDG-AI-001 (5 skills); AI Applied Skill → BDG-AI-002 (6); AI Advanced Skill → BDG-AI-003 (5) |
| Student status | 16 Active, 2 Graduate (BTU-T-0009, BTU-T-0013) |
| Longest skill name / description | 36 / 76 characters |
| Sync status | 16 SYNCED (all V1, 2026-10-17 10:00 UTC), 44 NOT SYNCED, 0 errors |

### Entities the system needs

Student (Student ID, names, email, program, level, status) → Passport (Passport ID, first-issued date; 1 per student) → PassportVersion (version no., PDF hash, verification code, issued-at, tx/anchor ref, included Record IDs) → SkillAward (Record ID, Skill ID, date earned) → Skill catalog (Skill ID, name, category, description) → Badge (derived from category). The Sheet flattens Student + SkillAward + catalog into one row. Normalise them into separate tables and add what the Sheet doesn't show: PassportVersion, Anchor, User/UserRole and AuditLog. Columns Q–T (sync status, version, time, error) become fields of PassportVersion, not of the award.

### The four student scenarios hidden in the data

1. **Existing passport, update pending** — 8 students (BTU-AI-000125 … 000132) have a V1 plus NOT SYNCED rows → expect V2.
2. **Passport ID allocated, never issued** — 6 students (000133 … 000138) have an ID and a September first-issued date but no synced version at all.
3. **Brand-new passport** — 4 students (000139 … 000142, BTU-T-0021…0024) first issued 2026-10-17, one skill each earned 2026-10-18.
4. **Graduates still earning skills** — BTU-T-0009 and BTU-T-0013 are Graduate yet have NOT SYNCED awards dated October 2026.

### Findings that affect the design

- **Back-dated awards.** 12 NOT SYNCED records belong to students already at V1 and were earned *before* the V1 sync time (e.g. BTU-T-0002, REC-0030, earned 2026-09-18). So a new version is not "append to the end": skills must be sorted by Date Earned and inserted, and a row's arrival order ≠ its date.
- **Passport IDs already exist for unissued students** (scenario 2 and 3), while the dataset notes say the system creates the ID on initial issuance. Both cannot be true for the same row — see open question Q1.
- **SYNCED is simulated.** The notes say no blockchain transactions exist, so V1 cannot actually be verified. Treat V1 as legacy history and make the first version our system anchors the next number (V2), or re-baseline everyone as V1 — see Q2.
- **Row order is meaningless.** Record IDs REC-0049 … 0060 are interleaved between older rows. The one-off seed import keys on Record ID, never on row position.
- **Names collide.** First names Luka, Salome, Elene and surnames Japaridze, Kiknadze, Abashidze each belong to two different students. Match on Student ID only.
- **Sheet layout is not a plain table.** Rows 1–3 are title/banner, the header is row 4, and a notes block starts after a blank row. The seed importer must find the header and stop at the first empty Record ID.
- **No failure examples.** Column T is empty everywhere, so error-path tests (bad Student ID, unknown Skill ID, date earned before first-issued, missing description) must be written by us.

## 8. Hidden technical problems

The hardest parts are not the PDF or the admin form — they are what a hash on a chain can and cannot prove. These are the traps most teams will hit, with the recommended answer for each.

&#91;embedded content: issuance and verification flow · recommended architecture\]

The issuer check also confirms the signing address is the one BTU publishes on its own domain (T4); without that step the chain only proves "some wallet" issued it.

| # | Problem | Why it bites | Recommended approach |
| --- | --- | --- | --- |
| T1 | A code alone cannot prove the *presented* PDF is unaltered | §7 asks for code entry, but §5 requires a tampered PDF to fail. Typing a code only proves a record exists. | Verify page has two modes: code lookup (shows the official data + official PDF to compare) and PDF upload (SHA-256 vs anchored hash). The QR should open the code lookup. |
| T2 | The code is printed inside the file that gets hashed | Circular if the code is derived from the hash. | Generate a random verification code first, render it into the PDF, then hash the final bytes. Never derive the code from the hash. |
| T3 | PDFs are fragile byte strings | Re-saving in a viewer, or an email gateway, changes bytes → a genuine passport shows "tampered". | Keep the strict file hash (it is what §5 asks for), and say in the verdict "use the official copy linked here". Optional: also sign the PDF (PAdES) so Adobe shows BTU's signature. |
| T4 | A transaction proves a key, not an institution | Anyone can create a wallet; §6 needs BTU's identity. | Registry smart contract where only BTU's issuer address can write; that address published on a BTU-controlled domain (e.g. a `.well-known` file / DID:web). Verifier checks both. |
| T5 | One transaction per version is expensive at scale | 25k+ versions/year. | Batch: hash all versions issued in a run into a Merkle tree, anchor the root once, store each version's Merkle proof. |
| T6 | "Latest valid version" needs state, not just hashes | Old versions stay genuine forever on-chain. | Registry maps Passport ID → latest version; verdict for older versions = "Authentic, superseded by vN". Add a revoked flag for wrongly awarded skills. |
| T7 | Double submissions and concurrent admins | A double-clicked Submit, or two admins awarding the same skill at once, creates duplicate awards or versions. | Idempotency key per form submission; unique constraint on (student, skill); build each version inside a transaction with a per-student lock. |
| T8 | Validation only in the browser | A "fancy form" can be bypassed with a direct API call. | Run the same validation schema on the server (FR-04) and return field-level errors to the form. |
| T9 | Edits to frozen fields | An admin fixing a name typo conflicts with "the name never changes". | Allow the edit on the student record but never on issued content; warn the admin and flag it for a reissue decision (Q4). |
| T10 | Code enumeration | Sequential codes let anyone scrape every student's skills without login. | ≥ 10 random base32 characters per code; rate-limit the verify endpoint. |
| T11 | Partial failure in the pipeline | Render OK but chain tx fails → a PDF exists that verifies as "unknown". | Version states: RENDERED → ANCHORED → PUBLISHED. Only ANCHORED versions are downloadable/valid; failures go to the retry queue (FR-22). |
| T12 | Template with variable length | 1 to 16 skills per student. | Convert BTU's design into an HTML/CSS template (Jinja + headless Chrome or WeasyPrint) with a repeating skill block that paginates, rather than stamping fixed PDF coordinates. |

## 9. Open questions for mentors / BTU

Ask these on day 1; each has a default so work isn't blocked while waiting.

| # | Question | Default if no answer |
| --- | --- | --- |
| Q1 | Who allocates Passport IDs — the admin in the form, or the system? The seed data already has IDs for students never issued a passport. | Import seed IDs as they are; for new students generate `BTU-AI-` + next number at registration. |
| Q2 | Is V1 ("SYNCED") a real issued document we must honour, or demo state? | Treat as legacy: our first anchored version for those 8 students is V2. |
| Q3 | Does a passport keep updating after graduation? | Yes — status shown on the passport, updates allowed. |
| Q4 | Can a name ever be corrected (typo, legal change)? | Admin may edit the student record; issued content is untouched and the change is flagged for a reissue decision. |
| Q5 | Which fields appear on the PDF? (Program, level and status are in the data; the brief only requires name, ID and skills.) | Follow the BTU design exactly; nothing extra. |
| Q6 | What does the verify page show publicly — full skill list, or only Valid/Invalid? | Name, Passport ID, version, issue date, skill list. No email, no program. |
| Q7 | What format is the visual design delivered in (Figma, PDF, AI)? | Rebuild in HTML/CSS. |
| Q8 | Any preference on blockchain network? Is a public testnet acceptable for the demo? | Public EVM testnet (e.g. Sepolia). |
| Q9 | Can an admin revoke an award? | Out of scope for MVP; registry supports a revoked flag. |
| Q10 | Should students be able to download older versions? | Yes, read-only, marked "superseded". |
| Q11 | Which identity provider does BTU use (Microsoft Entra ID or Google Workspace), and can we get a test tenant? | Decided 2026-10-24: no external provider; passwordless email-code login built into the app. SSO can be added later. |
| Q12 | Do admins need narrower scopes, e.g. a lecturer may award only their own course's skills? | Two global roles: Super admin and Admin. |
| Q13 | Is a CSV import of a whole cohort needed besides the form? | Should-have; the form comes first. |

## 10. Priorities and acceptance scenarios

Everything the brief calls mandatory is a Must; the jury will weigh automation and the tamper demo most.

- **Must:** FR-01 – FR-04, FR-10 – FR-12, FR-14 – FR-21, FR-23 – FR-25; NFR-03 – NFR-07 (privacy and all security items).
- **Should:** FR-05 bulk award, FR-06 status + retry, FR-09 audit log, FR-13 one version per submission, FR-22 retry queue, NFR-01 Merkle batching, NFR-12 Georgian font, QR code on the PDF.
- **Could:** FR-07 catalog editing UI and FR-08 role-management UI (a seed script covers the demo), PAdES signature, fresh sign-in before issuing, second-admin approval, CSV cohort import.
- **Won't (this week):** mainnet, HSM key custody, BTU's real identity provider, award approval workflow.

Events FR-26 – FR-32 are **Must**: they are now the main way skills are awarded. FR-33 – FR-35 are **Should**. Event-related open questions (Q14 – Q18) are in the Web App Design doc.

### Acceptance scenarios (use the real test rows)

| # | Given | When | Then |
| --- | --- | --- | --- |
| A1 | Luka Japaridze (BTU-T-0021) has no issued passport | Admin awards his first skill in the form | Passport BTU-AI-000139 issued as one PDF, anchored; admin sees "Issued" |
| A2 | Mariam Beridze (BTU-T-0002) is at V1 with 2 pending awards, one dated before V1 | Admin confirms both in one submission | One new version (not two), Passport ID BTU-AI-000126 unchanged, skills in date order |
| A3 | An award form was just submitted | Admin double-clicks or resubmits | No duplicate award, version or transaction |
| A4 | An issued PDF | Verifier uploads it unmodified | "Valid — issued by BTU", version, date |
| A5 | Same PDF with one date or letter changed | Verifier uploads it | "Not valid — does not match any issued version" |
| A6 | Old version of BTU-AI-000126 | Verifier enters its code | "Authentic, superseded by vN" + link to latest |
| A7 | Anchor written from a non-BTU wallet | Verifier checks it | Fails the issuer check |
| A8 | Student signs in as btu-t-0002@example.org | Opens the portal | Sees only BTU-AI-000126; can download it |
| A9 | Award with a future or missing date | Submitted via the form, then sent straight to the API | Form shows the field error; API returns 400; nothing saved |
| A10 | All 18 seed students | Admin bulk-awards one skill to all | 18 new versions, batched anchoring, no per-student step |
| A11 | Signed in as a student | Opens the admin panel or calls an admin API | 403 on both |
| A12 | An admin's role is revoked by the super admin | That admin makes the next request | 403, logged in the audit log |

| # | Given | When | Then |
| --- | --- | --- | --- |
| A13 | A photo of the event QR taken 2 minutes ago | A student scans it | "Scan the code on the screen again"; no check-in |
| A14 | A student checked in but has no student record | Super admin clicks Mark as done | Button disabled until the row is registered or removed |
| A15 | 20 participants, 2 already hold the skill | Super admin marks the event done, then clicks again | 18 awards and 18 new versions; the second click creates nothing |
| A16 | A completed event | Super admin tries to delete it via UI or API | No delete button; API returns 409 |

## 11. Process: lightweight Scrum, not full Scrum

Full Scrum (two-week sprints, separate planning, review and retro meetings, a dedicated Scrum Master) is overkill for seven days. Keep the parts that prevent errors — a prioritised backlog, short iterations with a working increment, and a review with the mentor — and drop the ceremony.

1. **Day 1 — Analysis + design (this doc).** Database schema from the seed Sheet, auth provider choice, chain and PDF stack. Get Q1, Q2 and Q11 answered first.
2. **Sprint 1 (days 2–3) — the thin end-to-end slice.** Admin login → award form → one PDF → hash anchored → verify by upload. Ugly but complete; this de-risks the whole project.
3. **Sprint 2 (days 4–5) — make it right.** Versioning, issuer identity, verification codes/QR, idempotency, role checks, student portal, BTU template fidelity.
4. **Sprint 3 (day 6) — scale and polish.** Bulk award, Merkle batching, audit log, error paths A9–A12, form polish.
5. **Day 7 — freeze.** No new features: demo script, tamper demo rehearsal, README, slides.

Each sprint ends with a mentor review against the acceptance scenarios in section 10; a 10-minute daily standup is enough. The backlog is the user stories (section 2), each sized by the FRs it produces, ordered by the MoSCoW split.
