# Affiliate Builder UI

Local UI for building one-page Shopee affiliate promo sites and publishing the generated HTML to the same Netlify URL.

## Start

From the workspace root:

```powershell
node C:\Users\mohdl\.openclaw\workspace\projects\affiliate-builder-ui\server.js
```

Open:

```text
http://localhost:8787
```

## Netlify Publishing

Publishing uses the existing site config:

```text
C:\Users\mohdl\.openclaw\workspace\scripts\netlify-site.local.json
```

The server needs Netlify auth in the local environment. Recommended:

```powershell
$env:NETLIFY_AUTH_TOKEN = "your-rotated-token"
node C:\Users\mohdl\.openclaw\workspace\projects\affiliate-builder-ui\server.js
```

Do not put the Netlify token in the generated website or committed files.

## Workflow

1. Search by category and period, or paste a product URL.
2. Paste an affiliate link, or leave it blank for testing.
3. Click `Generate HTML`.
4. Review the iframe preview.
5. Click `Publish to Netlify`.

Generated output is written to:

```text
C:\Users\mohdl\.openclaw\workspace\projects\affiliate-builder-ui\generated\site
```
