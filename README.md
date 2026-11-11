# Job Watcher

Checks company career pages every hour, for free, using GitHub Actions.
When a new job matching your keywords appears, it sends you a phone
notification and/or an email.

---

## Step 1: Set up phone notifications (ntfy, free)
1. Install the **ntfy** app (Android: Play Store; iPhone: App Store).
2. Tap **+**, then subscribe to a topic name that only you know, such as
   `nick-jobs-7f3k9q`. Anyone who knows the name can read the alerts,
   so make it hard to guess.
3. Keep that name handy for Step 3.

## Step 2 (optional): Set up email alerts (Gmail)
1. Turn on 2-Step Verification on your Google account.
2. Go to **myaccount.google.com/apppasswords**, create an app password
   named "Job Watcher", and copy the 16-character password.

## Step 3: Put the project on GitHub
1. Sign up at **github.com** (free).
2. Click **New repository**, name it `job-watcher`, choose **Public**
   (public repos get unlimited free minutes), then click **Create**.
3. Click **uploading an existing file** and upload everything in this
   folder, including the `.github/workflows/job-watcher.yml` file.
   - Tip: on a computer, unzip the folder and drag its whole contents
     into the upload box. That keeps the `.github` folder structure.
4. Go to **Settings → Secrets and variables → Actions → New repository secret**
   and add:

   | Secret name      | Value                                   |
   |------------------|-----------------------------------------|
   | `NTFY_TOPIC`     | your ntfy topic name from Step 1        |
   | `EMAIL_FROM`     | your Gmail address (optional)           |
   | `EMAIL_TO`       | where to send alerts (optional)         |
   | `EMAIL_PASSWORD` | the Gmail app password (optional)       |

   Secrets stay hidden even though the repo is public.

## Step 4: Add your companies
Edit `config.yaml` on GitHub (click the file, then the pencil icon). Add each
company's name and careers-page link, plus the job keywords you want.
Click **Commit changes**.

## Step 5: Test it
Go to the **Actions** tab, click **Job Watcher**, then **Run workflow**.
After about a minute you should get a notification for any matching jobs
currently posted. From then on it runs every hour and only alerts you
about NEW postings.

---

## Good to know
- **Schedule:** runs at 7 minutes past every hour. GitHub can sometimes
  start it a few minutes late.
- **Logs:** Actions tab → click any run to see what it found or what failed.
- **GitHub emails you if a run fails**, so you'll know if something breaks.
- **60-day rule:** GitHub pauses schedules in repos with no activity for 60
  days. The bot's own commits count as activity, but if no new jobs show up
  for two months, open the Actions tab and re-enable the schedule.
- **A company shows "scanned 0 items" or misses jobs:** its page probably loads
  jobs with JavaScript. Tell Claude which site it is and it can adjust that one.
- **Some companies post only on LinkedIn or CaribbeanJobs:** use the job
  board's search-results page as that company's `url`.
- **Start over:** delete `seen_jobs.json` from the repo, and the next run
  will report every current match again.

## Running on your own computer instead
```bash
pip install -r requirements.txt
python job_watcher.py          # one check
python job_watcher.py --loop   # check every hour while the computer is on
```
