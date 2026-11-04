# Tutor starter

Voice whiteboard tutors for a topic you teach. A tutor talks, writes on a board,
and checks the student's answers with tools. Every number it says comes from a
tool. This repo holds the engine and one finished example, the binomial option
pricing tutor. The `tutor` plugin builds new tutors in it for you.

## Start with the plugin

In Claude Code:

```
/plugin marketplace add kerryback/kerryback-public
/plugin install tutor@kerryback-public
```

Start a new session, and say "make a tutor for <topic>", pointing at your slides,
notebooks, or code. The skill clones this repo to `~/repos/tutors`, builds the
tutor, and takes you through a review page, a local try, evals, and the deploy.
It waits for your approval at each.

## What is here

| Folder | What it holds |
|---|---|
| `engine/` | The app every tutor runs: the sign-in check, the voice, the whiteboard page, the tutor loop, and the tools every tutor has (`calculate`, `save_progress`, `start_module`, `show_plot`) |
| `home/` | The site's accounts (username and 4-digit passcode), sign-in pages, and the landing page that lists the tutors |
| `instructions/` | The shared start of every tutor's prompt: `teaching.md` and `voice.md` |
| `evals/` | The eval harness and the scenarios every tutor gets |
| `scripts/` | Setup, tests, running locally, the review page, evals, and deploys |
| `review/` | The review page: a local app for reading and editing a tutor as it is built |
| `binomial/` | The example tutor |
| `site.toml` | Your domain, your email rule, your mail server, and your model |

## Running it without the plugin

```
scripts/setup.sh                 # once: creates .venv and installs everything
scripts/test.sh                  # tests for every tutor
scripts/run.sh binomial          # run a tutor here, with voice, in the browser
scripts/review.sh binomial       # open the review page
scripts/eval.sh binomial         # behavior evals against the real model (about $0.50)
```

The scripts run on macOS, Linux, and Windows. On Windows, run them in Git Bash,
the shell that Claude Code uses there. Setup needs Python 3.11 or later.

`run.sh` and `eval.sh` need `ANTHROPIC_API_KEY` in the shell. The voice uses the
espeak-ng that comes with the `kokoro-onnx` package, so there is nothing else to
install. The speech models download into `<tutor>/data/models` the first time.

`voice` in `site.toml` chooses who speaks: `"kokoro"` (free, runs with the tutor)
or `"elevenlabs"` (paid; needs `ELEVENLABS_API_KEY`). An ElevenLabs key in your
shell is not used unless `voice = "elevenlabs"`. `TUTOR_VOICE` overrides the file. A local run needs no sign-in or mail server:
you are a local test student. Student data stays in `<tutor>/data`, which Git ignores.

## What a tutor folder holds

| File | What it is |
|---|---|
| `tutor.toml` | Its name, title and subtitle, words for Whisper, the order of its teaching scripts, and its Railway project and region |
| `content/topic.md` | The topic section of the prompt: routing, tools, conventions, mistakes, and notation |
| `content/module-intros.md` | The Introduction and each module's spoken intro, board items, and learning objectives |
| `content/*.md` | The teaching scripts and the problem bank |
| `topic.py` | The tutor's own tools and plots |
| `tests/` | Its tests, including a pinned hash of its full prompt |
| `evals.py` | Its eval scenarios |
| `snapshot/` | Frozen data for the lessons, with its source and dates |

The prompt is built in this order: `instructions/teaching.md`, `content/topic.md`,
the teaching scripts, the learning objectives, then `instructions/voice.md`.

A change to `engine/` or `instructions/` reaches every tutor on its next deploy.
A change to the instructions fails each tutor's pinned prompt test until you run
that tutor's evals and update its hash. `scripts/deploy-all.sh` tests every tutor
and deploys only if all pass.

## Deploying

Local use needs none of this. The tutors run on [Railway](https://railway.com).
Each tutor is its own Railway project, built from the shared `Dockerfile`, with
one service (`web`) on port 8000, one instance in EU West (Amsterdam,
`europe-west4-drams3a`), and a volume at `/data` for the student records and
the speech models. The home app is one more project, `tutors-home`.

1. Install the Railway CLI, version 5 or later, and sign in:

   | macOS | Linux | Windows |
   |---|---|---|
   | `brew install railway` | `bash <(curl -fsSL railway.com/install.sh)` | `npm i -g @railway/cli` (needs Node 16 or later), or `scoop install railway` |

   `npm i -g @railway/cli` also works on macOS and Linux. Then run
   `railway login`, and check it with `railway whoami`.
2. Set `site.toml`: your domain, the email rule, the mail server, and the model.
3. Put the secrets in `deploy.env` in this folder. Git ignores this file. The
   deploy scripts send each secret to a Railway project the first time that
   project needs it, and leave it alone after that.

   ```
   ANTHROPIC_API_KEY=sk-ant-...     # the tutors' model calls
   TUTORS_SECRET=...                # a long random string, shared by the home app and every tutor
   TUTORS_PEPPER=...                # a long random string, part of every passcode hash
   SMTP_PASSWORD=...                # your mail service's password or key, for sign-in emails
   # ELEVENLABS_API_KEY=...         # only with voice = "elevenlabs" in site.toml
   ```

   `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` makes a
   long random string. To change a secret later, run
   `railway variable set NAME --stdin` in that project.
4. Deploy the home app, then each tutor:

   ```
   scripts/deploy-home.sh           # the accounts and landing page, at your domain
   scripts/deploy.sh binomial       # one tutor, at binomial.<your domain>
   ```

   The first deploy of each prints two DNS records, a CNAME and a TXT. Add
   both at your DNS provider; Railway needs both. Then
   `railway domain status <domain>` shows when the domain is verified. With
   Cloudflare's proxy on, set its SSL/TLS mode to Full.

`scripts/deploy.sh binomial --trial` deploys to a separate project at a
Railway address, with no DNS. Sign-in does not work there, but
`https://<address>/api/config` shows whether the tutor and its voice are up.
Delete the trial with `railway delete --project binomial-voice-trial --yes`.

`[deploy]` in a tutor's `tutor.toml` names its Railway project and its
region. Railway's region IDs are `europe-west4-drams3a` (Amsterdam),
`us-east4-eqdc4a` (Virginia), `us-west2` (California) and
`asia-southeast1-eqsg3a` (Singapore).

What it costs: the Hobby plan is $5 a month and includes $5 of usage. After
that Railway bills what a service uses: $10 per GB of RAM per month, $20 per
vCPU per month, and $0.15 per GB of volume per month
([railway.com/pricing](https://railway.com/pricing)). A tutor holds its speech
models in memory, about 0.9 GB, and stores about 0.5 GB on its volume, so one
tutor uses about $10 to $12 a month, and the home app about $1. The $5 fee
covers the first $5 of that, so one tutor and the home app come to about $11
to $13 a month in all, and each more tutor adds about $10 to $12. The model calls are billed to your Anthropic key. On Hobby, a
volume holds at most 5 GB, and a service has at most 2 custom domains. A new
account's 30-day trial (1 GB of RAM, a 0.5 GB volume) is too small for a tutor.

Students sign in once at your domain. Signing in sets one cookie on that domain,
signed with `TUTORS_SECRET`, and each tutor checks it. Student records are kept
under the account number, and no tutor sees an email address.

## License

MIT. See `LICENSE`.
