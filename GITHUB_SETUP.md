# GitHub Setup Instructions

Follow these steps to create a GitHub repository and push the League Tonight code.

## Step 1: Create GitHub Repository

1. Go to https://github.com/new
2. Repository name: `league-tonight`
3. Description: `AI-powered fantasy football recaps and briefings`
4. Choose: **Public** (so Render can access it)
5. **DO NOT** initialize with README (we already have one)
6. Click "Create repository"

## Step 2: Clone Repository Locally

On your computer, open terminal/command prompt and run:

```bash
git clone https://github.com/YOUR_USERNAME/league-tonight.git
cd league-tonight
```

Replace `YOUR_USERNAME` with your actual GitHub username.

## Step 3: Copy Code Files

Download all these files from `/mnt/user-data/outputs/`:

**Python Files:**
- app.py
- database.py
- sleeper_client.py
- espn_client.py
- claude_helper.py
- external_data.py

**Config Files:**
- requirements.txt
- .gitignore
- .env.example
- README.md
- GITHUB_SETUP.md (this file)

**Templates (create `templates/` folder):**
- dashboard.html
- recap.html
- briefing.html

Your folder structure should look like:

```
league-tonight/
├── app.py
├── database.py
├── sleeper_client.py
├── espn_client.py
├── claude_helper.py
├── external_data.py
├── requirements.txt
├── .gitignore
├── .env.example
├── README.md
├── GITHUB_SETUP.md
└── templates/
    ├── dashboard.html
    ├── recap.html
    └── briefing.html
```

## Step 4: Create .env File (Local Only)

In the `league-tonight/` folder, create a `.env` file with your actual values:

```
DATABASE_URL=postgresql://user:password@host/dbname
CLAUDE_API_KEY=sk-ant-...
SLEEPER_LEAGUE_ID=your-id
FLASK_ENV=production
```

**IMPORTANT: Do NOT commit .env to GitHub.** The `.gitignore` file will prevent this.

## Step 5: Push Code to GitHub

In your terminal (in the `league-tonight/` folder), run:

```bash
git add .
git commit -m "Initial commit: League Tonight MVP"
git branch -M main
git push -u origin main
```

After this completes, your code is on GitHub!

## Step 6: Verify on GitHub

1. Go to https://github.com/YOUR_USERNAME/league-tonight
2. You should see all your files there
3. Check that `.env` is NOT listed (it should be ignored)

## Step 7: Connect to Render

Now that you have a GitHub repo:

1. Go to https://render.com
2. Click "New +" → "Web Service"
3. Select "Public Git Repository"
4. Paste: `https://github.com/YOUR_USERNAME/league-tonight`
5. Click "Connect"
6. Fill in configuration (see Render setup guide)
7. Click "Create Web Service"

Render will now automatically deploy your code!

## Troubleshooting

**"fatal: not a git repository"**
- Make sure you're in the `league-tonight/` folder
- Run `pwd` to check your location

**"Permission denied (publickey)"**
- You need to set up SSH keys: https://docs.github.com/en/authentication/connecting-to-github-with-ssh

**"Changes not detected on Render"**
- After pushing to GitHub, wait 1-2 minutes
- Render will automatically pull and redeploy

**"My .env file got pushed to GitHub"**
- Don't panic, delete it immediately:
  ```bash
  git rm .env
  git commit -m "Remove .env file"
  git push
  ```
- Regenerate your API keys and cookies
- Update them in Render environment variables

## Next Steps

After pushing to GitHub and connecting Render:

1. Go back to your Render deployment setup guide
2. Add environment variables in Render dashboard
3. Wait for deployment to complete
4. Run the health checks to verify everything works
