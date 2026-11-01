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

`run.sh` and `eval.sh` need `ANTHROPIC_API_KEY` in the shell. The voice needs
espeak-ng (`brew install espeak-ng`). The speech models download into
`<tutor>/data/models` the first time. A local run needs no sign-in or mail server:
you are a local test student. Student data stays in `<tutor>/data`, which Git ignores.

## What a tutor folder holds

| File | What it is |
|---|---|
| `tutor.toml` | Its name, title and subtitle, words for Whisper, the order of its teaching scripts, and its Koyeb app and volume |
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

Local use needs none of this. To put tutors online, set `site.toml`, create the
Koyeb secrets, and deploy the home app and then each tutor:

| Secret | What it is |
|---|---|
| `tutors-session-secret` | A long random string, shared by the home app and every tutor |
| `tutors-pepper` | A long random string, part of every passcode hash |
| `tutors-anthropic-key` | The key for the tutors' model calls |
| `tutors-smtp-password` | Your mail service's password or key, for sign-in emails |
| `elevenlabs-api-key` | Only with `elevenlabs = true` in `site.toml` |

```
scripts/deploy-home.sh           # the accounts and landing page, at your domain
scripts/deploy.sh binomial       # one tutor, at binomial.<your domain>
```

Each tutor is a Koyeb medium instance (about $21 a month) with a 5 GB volume.
Add each domain in Koyeb and a CNAME record at your DNS provider.

Students sign in once at your domain. Signing in sets one cookie on that domain,
signed with `TUTORS_SECRET`, and each tutor checks it. Student records are kept
under the account number, and no tutor sees an email address.

## License

MIT. See `LICENSE`.
