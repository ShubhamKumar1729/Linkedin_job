# LinkedIn Job Application Bot

This Python automation searches recent LinkedIn posts for configured roles,
extracts recruiter emails and direct company/ATS application links, and asks
Groq to evaluate candidate/job relevance before sending or saving an action.

## Workflow

1. Search LinkedIn posts for each configured role.
2. Extract the complete visible post, structured job details, recruiter email,
   direct company/ATS application links, recruiter name, and post URL.
3. Validate deterministic requirements: non-empty job text, valid action/link,
   and duplicate-send/save status.
4. Skip prior emails and direct-job links already recorded in output CSV files.
5. Send the complete job description, target role, candidate details, and
   extracted recruiter emails to Groq for the relevance decision.
6. Groq rejects wrong roles, non-US jobs, excessive experience, incompatible
   work authorization, and every staffing/third-party recruiting contact.
7. For approved direct employers, send verified corporate emails and save
   official ATS/company apply links to `output/direct_jobs.csv`.
8. Process 30 unique actionable posts per role and keep scrolling to the end
   when fewer than 30 are available.

Groq only evaluates relevance. Email generation, sending, and sent-application
tracking remain local to this project.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
playwright install chromium
cp .env.example .env             # Windows: copy .env.example .env
```

Edit `.env` with your Gmail app password, Groq API key, candidate information,
and desired roles. Put the configured resume PDF inside `output/`; its filename
must match `RESUME_FILENAME`.

Important AI settings:

```dotenv
GROQ_API_KEY=your-groq-api-key
GROQ_MODEL=openai/gpt-oss-120b
AI_RELEVANCE_THRESHOLD=70
AI_MATCH_MODE=role_location
RECRUITER_POLICY=direct_employer_only
GROQ_TIMEOUT_SECONDS=30
GROQ_MAX_RETRIES=2
GROQ_MAX_COMPLETION_TOKENS=1000
MAX_EXPERIENCE_YEARS=5
MAX_EMAILS_PER_RUN=100
POSTS_PER_ROLE=30
MAX_PASSES_PER_ROLE=30
NO_NEW_POST_PASSES=2
DELAY_BETWEEN_AI_REQUESTS=15
GROQ_RATE_LIMIT_COOLDOWN_SECONDS=60
GROQ_MAX_RATE_LIMIT_WAIT_SECONDS=300
MAX_EMAILS_PER_POST=5
MAX_JOB_DESCRIPTION_CHARS=12000
```

`AI_MATCH_MODE=role_location` checks target-role alignment, explicit US
location, a genuine application contact, candidate work authorization, and the
configured experience ceiling. With `MAX_EXPERIENCE_YEARS=5`, explicit job
requirements of 1-5 years may pass while 10-12 years are rejected. Candidate
skills are supplied for context but individual tool gaps are not a hard gate.

`RECRUITER_POLICY=direct_employer_only` rejects all staffing, placement,
consulting/vendor, third-party recruiting, OPT marketing, and résumé collection
companies. Approval requires a named end-employer plus an in-house recruiter,
hiring manager, or official corporate application email. Personal email-domain
contacts are rejected under this policy.

LinkedIn search always uses each `ROLE_N_SEARCH` value exactly as written in
`.env`. For direct employers, use short queries such as `Data Analyst hiring
USA`; adding `email` strongly biases results toward staffing agencies.

`POSTS_PER_ROLE=30` keeps each role active until 30 unique actionable posts
(with an email or apply link) have been processed. Corporate emails are sent;
official company/ATS links are saved for manual application. If fewer than 30
exist, scrolling continues until two consecutive passes load no new posts or
the safety pass limit is reached.

AI requests are spaced by `DELAY_BETWEEN_AI_REQUESTS`. If Groq returns HTTP
429, response reset headers (or `GROQ_RATE_LIMIT_COOLDOWN_SECONDS`) delay the
next unique request. Failed checks are cached for the rest of the run so later
scroll passes do not repeatedly call Groq for the same post.

`MAX_EMAILS_PER_POST` and `MAX_JOB_DESCRIPTION_CHARS` are technical DOM guards:
they reject accidental LinkedIn parent containers that combine many unrelated
posts and would otherwise cause an oversized Groq request. They do not perform
job relevance filtering.

`MAX_EMAILS_PER_ROLE` is accepted only as a backwards-compatible fallback when
`MAX_EMAILS_PER_RUN` is not present. New configurations should use
`MAX_EMAILS_PER_RUN`.

## Run

```bash
source .venv/bin/activate        # if not already active
python main.py
```

The first run may open LinkedIn's login page. Log in manually and press Enter
in the terminal when prompted. The persistent browser profile is stored in
`linkedin_profile_data/` and is ignored by Git.

## Data and operational notes

- The complete visible LinkedIn post, full configured candidate details,
  role-specific skills, preferred roles, and experience ceiling are sent to
  Groq. The résumé PDF itself is not uploaded or parsed.
- Sent emails are tracked in `output/sent_emails.csv`; approved direct-employer
  ATS/company links are deduplicated in `output/direct_jobs.csv`.
- A Groq timeout, rate limit, API error, or invalid response fails closed: that
  job is skipped and no email is sent.
- Model availability and API rate limits depend on the Groq account and plan.
  The default is `openai/gpt-oss-120b`; the former
  `llama-3.3-70b-versatile` model was retired for free/developer usage on
  August 16, 2026. Change `GROQ_MODEL` if the configured model is unavailable.
- LinkedIn UI/DOM changes can require selector updates.
- Use conservative sending limits and comply with LinkedIn, Gmail, privacy,
  anti-spam, and applicable legal requirements.
