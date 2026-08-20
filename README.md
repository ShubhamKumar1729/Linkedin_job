# LinkedIn Job Application Bot

This Python automation searches recent LinkedIn posts for configured roles,
extracts recruiter email addresses, applies the existing job filters, and asks
Groq to evaluate candidate/job relevance before sending an application email.

## Workflow

1. Search LinkedIn posts for each configured role.
2. Extract the complete visible post, structured job details, recruiter email,
   recruiter name, and post URL.
3. Apply the existing bench-sales, job-signal, US-location, and email filters.
4. Skip email/post pairs already recorded in `output/sent_emails.csv`.
5. Send the complete job description and existing candidate configuration to
   Groq for a structured relevance decision.
6. Send an email only when Groq returns `relevant: true` and its score meets
   `AI_RELEVANCE_THRESHOLD`.
7. Stop after `MAX_EMAILS_PER_RUN` application emails have been sent
   successfully. Filtered, duplicate, failed, and irrelevant jobs do not count.

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
GROQ_TIMEOUT_SECONDS=30
GROQ_MAX_RETRIES=2
MAX_EMAILS_PER_RUN=50
```

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

- Candidate details and the complete visible LinkedIn post are sent to Groq.
- A Groq timeout, rate limit, API error, or invalid response fails closed: that
  job is skipped and no email is sent.
- Model availability and API rate limits depend on the Groq account and plan.
  The default is `openai/gpt-oss-120b`; the former
  `llama-3.3-70b-versatile` model was retired for free/developer usage on
  August 16, 2026. Change `GROQ_MODEL` if the configured model is unavailable.
- LinkedIn UI/DOM changes can require selector updates.
- Use conservative sending limits and comply with LinkedIn, Gmail, privacy,
  anti-spam, and applicable legal requirements.
