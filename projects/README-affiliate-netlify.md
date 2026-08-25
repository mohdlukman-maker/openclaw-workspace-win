# Affiliate Netlify Publishing

Use one Netlify site for all affiliate experiments so the public URL stays the same.

## One-time setup

1. Log in to Netlify:

```powershell
npx --yes netlify-cli login
```

2. Create or choose one Netlify site in Netlify.

3. Save the site ID using one of these methods:

```powershell
$env:NETLIFY_SITE_ID = "your-site-id"
```

Or copy this file:

```text
C:\Users\mohdl\.openclaw\workspace\scripts\netlify-site.example.json
```

to:

```text
C:\Users\mohdl\.openclaw\workspace\scripts\netlify-site.local.json
```

Then replace `site_id` with the real Netlify site ID.

Do not put Netlify tokens in this file.

## Deploy

Publish the iPhone case site to the same Netlify URL:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\mohdl\.openclaw\workspace\scripts\deploy-affiliate-netlify.ps1 -Product iphone
```

Publish the WOW Spaghetti site to the same Netlify URL:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\mohdl\.openclaw\workspace\scripts\deploy-affiliate-netlify.ps1 -Product spaghetti
```

Draft deploy without replacing the public site:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\mohdl\.openclaw\workspace\scripts\deploy-affiliate-netlify.ps1 -Product iphone -Draft
```

## Notes

- The script deploys the selected folder to the same Netlify `site_id`.
- Each deploy folder is checked to ensure it contains exactly one HTML file.
- Replace `AFFILIATE_URL` inside the selected `index.html` before production publishing.
