# release-tracker

A self-hosted tracker that tells you when new episodes and chapters come out for the anime,
manga and TV shows you follow. Every person who uses it deploys their own copy into their
own AWS account, with one user per deployment.

| Kind  | Source                                     | Title ID used         |
|-------|--------------------------------------------|-----------------------|
| Anime | [AniList](https://anilist.co) GraphQL      | AniList media ID      |
| TV    | [TVmaze](https://www.tvmaze.com) REST      | TVmaze show ID        |
| Manga | [MangaDex](https://mangadex.org) REST      | MangaDex manga UUID   |

Titles are stored by source and source ID, so there is never any fuzzy title matching.

## Status

- [x] **Step 1**: SAM infrastructure, plus a checker that logs new releases to CloudWatch
- [x] **Step 2**: notification feed in DynamoDB (no Firebase or Google services)
- [ ] Step 3: HTTP API (watchlist CRUD, search, upcoming, notification feed)
- [ ] Step 4: Flutter Android app

## How it works

```
EventBridge cron (UTC) ──► Checker Lambda ──► AniList / TVmaze / MangaDex
                                │
                                ▼
          DynamoDB (watchlist + last-seen state + release log + notification feed)
                                ▲
     Android app ── polls 30 min after each check ──► HTTP API ─┘ ──► local notification
```

- **Schedule.** The default is `cron(0 4,16 * * ? *)`, which runs at 04:00 and 16:00 UTC
  (09:00 and 21:00 in Asia/Karachi). Change it with the `CheckSchedule` parameter.
- **Notifications without a push service.** Android push always goes through Google's FCM,
  even when it's sent from AWS (SNS, End User Messaging). So the checker writes one row per
  title into a feed instead. The app polls the feed once, 30 minutes after each check
  (`POLL_TIMES_UTC`, default `04:30,16:30`), and shows each row as a local notification.
  Each poll asks only for rows newer than the last one it saw, so a missed or late poll
  loses nothing. Feed rows expire after 90 days through DynamoDB TTL. If you change
  `CheckSchedule`, change `POLL_TIMES_UTC` in the app config to match.
- **Baseline.** When a title is added, its current latest release is recorded as already
  seen, so you aren't flooded with the back catalogue.
- **Never notified twice.** Before sending, the checker writes a row for that release, and
  the write only succeeds if the row doesn't exist yet. Retries, overlapping runs and state
  rewinds therefore can't send a release twice. A send that fails is retried up to 3 times.
  A crash in the middle of a send can lose that one notification, but it can never cause a
  duplicate.
- **Anime** releases count from the Japanese broadcast time (AniList `airingSchedule`).
- **TV** episodes are ordered by `airstamp`. A streaming season drop arrives as one
  notification.
- **Manga** chapters are matched by chapter number, not upload, because MANGA Plus and
  several scanlation groups often upload the same chapter. Chapters are English by default,
  official and fan translations alike; change this with `MangaLanguages`, e.g. `en,es-la`.
  MangaDex publishes no release schedule, so manga never show an upcoming date.
- All timestamps are stored in UTC.

## Deploy

Prerequisites: an AWS account, the [AWS CLI](https://aws.amazon.com/cli/),
[SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
and Python 3.12. On macOS: `brew install awscli aws-sam-cli python@3.12`.

### 1. Create the restricted deployer (once, with an admin profile)

```bash
python3.12 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements-dev.txt
backend/.venv/bin/python scripts/bootstrap_iam.py --admin-profile <your-admin-profile> --create-access-key
```

This creates the IAM user `release-tracker-deployer` and writes its access key into a local
AWS CLI profile named `release-tracker`. The user's permissions are scoped to resources named
`release-tracker-*`. It can only create Lambda roles that carry the `release-tracker-boundary`
permissions boundary, so neither the user nor its functions can escalate privileges. The
policies are in [`iam/`](iam/), and the script is safe to re-run after editing them.

### 2. Build and deploy

```bash
cd backend
sam build
sam deploy            # uses samconfig.toml: stack "release-tracker", profile "release-tracker"
```

Optional parameters, passed as `sam deploy --parameter-overrides Key=Value ...`:

| Parameter          | Default                | Meaning                                           |
|--------------------|------------------------|---------------------------------------------------|
| `CheckSchedule`    | `cron(0 4,16 * * ? *)` | When the checker runs, in UTC                     |
| `MangaLanguages`   | `en`                   | MangaDex translated languages                     |
| `BudgetAlertEmail` | *(empty: no budget)*   | Creates a monthly account-wide AWS Budget         |
| `BudgetLimitUsd`   | `5`                    | Budget amount; you're emailed at 80% actual and 100% forecast |

The DynamoDB table has `DeletionPolicy: Retain`, so `sam delete` keeps your watchlist.

### 3. Add titles (until the API and app exist)

```bash
export AWS_PROFILE=release-tracker
PY=backend/.venv/bin/python
$PY scripts/watchlist.py peek anilist 21                     # look at a title without saving it
$PY scripts/watchlist.py add anilist 21                      # One Piece (anime)
$PY scripts/watchlist.py add mangadex a1c7c817-4e59-43b7-9365-09675a149a6f   # One Piece (manga)
$PY scripts/watchlist.py add tvmaze 32158                    # FBI
$PY scripts/watchlist.py list
```

IDs are in each site's URLs: `anilist.co/anime/21`, `tvmaze.com/shows/32158/fbi`,
`mangadex.org/title/<uuid>`.

## Test the checker and feed

```bash
cd backend
sam remote invoke CheckerFunction                         # run a check now
sam logs -n CheckerFunction --start-time '10min ago'      # read the CloudWatch logs

# Make the next check see the last 2 releases as new:
.venv/bin/python ../scripts/watchlist.py rewind anilist 21 --by 2 --forget
sam remote invoke CheckerFunction                         # logs "NEW anime: ONE PIECE — Episode 1179/1180"
.venv/bin/python ../scripts/watchlist.py notifications    # one feed row: "Episode 1179, Episode 1180 are out"
sam remote invoke CheckerFunction                         # nothing new: already notified, no new feed row

# Rewind without --forget: the release log stops a second notification.
.venv/bin/python ../scripts/watchlist.py rewind anilist 21 --by 2
sam remote invoke CheckerFunction                         # logs "Already notified 2 release(s)"
```

## Keeping your API URL and token private

The repo is meant to be public, so nothing that identifies your deployment is committed.
That covers the API URL, the token, your account ID and your email. The app reads its
settings from `app/config.local.json`, which is gitignored (`*.local.json`), and they're
compiled into the APK at build time:

```bash
cp app/config.example.json app/config.local.json   # then fill in your API URL and token
flutter build apk --dart-define-from-file=config.local.json   # run inside app/
```

Don't publish an APK you've built this way, because it contains your token.

Unit tests run locally against an in-memory DynamoDB ([moto](https://github.com/getmoto/moto)):

```bash
cd backend && .venv/bin/pytest
```

## Cost

At two checks a day with a handful of titles, Lambda, DynamoDB on-demand, EventBridge and
CloudWatch all stay at or near $0. CloudWatch logs are kept for 30 days.

## Data sources and terms

This project does not host any content. It only reads public metadata.

- **AniList**: [API terms](https://docs.anilist.co/guide/terms-of-use) allow non-commercial use.
  The rate limit is 90 requests per minute.
- **TVmaze**: data is licensed [CC BY-SA](https://www.tvmaze.com/api#licensing). Anything
  that displays it must credit TVmaze.
- **MangaDex**: follow the [API rules](https://api.mangadex.org/docs/): credit MangaDex and
  the scanlation groups, and don't make money from it.

Requests send the User-Agent `release-tracker/0.1 (+https://github.com/izzangalaxybyte/release-tracker)`.
If you run a fork, change `USER_AGENT` in `backend/src/tracker/http.py`.

## License

[MIT](LICENSE)
