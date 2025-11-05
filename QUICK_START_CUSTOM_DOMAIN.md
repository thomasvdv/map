# Quick Start: Custom Domain Setup

## What You'll Get

Access your map at a clean URL like `https://map.yourdomain.com` without needing `/index.html` in the URL.

---

## Prerequisites

- A domain added to Cloudflare (with Cloudflare as nameserver)
- R2 bucket already set up with files (✅ Done - bucket: `map`)

---

## 5-Minute Setup

### 1. Connect Domain to R2

1. Open: https://dash.cloudflare.com
2. Go to: **R2** → **map** → **Settings**
3. Under **Public Access**, click **Connect Domain**
4. Enter subdomain: `map.yourdomain.com`
5. Click **Continue**

**Wait 2 minutes for DNS**

### 2. Test Domain

Visit: `https://map.yourdomain.com/index.html`

Should load your map ✅

### 3. Add Transform Rule

1. In Cloudflare, go to your domain (not R2)
2. Click: **Rules** → **Transform Rules** → **Create Rule**
3. Name: `Serve index at root`
4. Expression: `(http.request.uri.path eq "/")`
5. Then: **Rewrite to** → **Static** → `/index.html`
6. Click **Deploy**

### 4. Test Root URL

Visit: `https://map.yourdomain.com`

Map should load without `/index.html` ✅

---

## Benefits

- ✅ Clean, professional URL
- ✅ Full Cloudflare CDN + caching
- ✅ Better performance than R2.dev
- ✅ Free (no Worker execution costs)
- ✅ Easy to share and remember

---

## Need Help?

See `CUSTOM_DOMAIN_SETUP.md` for:
- Detailed step-by-step instructions
- Screenshots and examples
- Troubleshooting guide
- Adding a domain to Cloudflare

---

## Current Status

✅ VFR tiles uploaded (16,887 files, 3.7GB)
✅ Map HTML uploaded (`index.html`, 111MB)
✅ R2.dev public access enabled
⏳ Custom domain setup (you're here)

**Next:** Connect your domain using steps above
