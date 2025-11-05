# Custom Domain Setup for R2 Map (Option 2)

This guide walks you through connecting a custom domain to your R2 bucket and configuring automatic index.html serving at the root URL.

## Prerequisites

You need:
- A domain name you own (e.g., `yourdomain.com`)
- The domain must be added to Cloudflare as a site
- Cloudflare must be your nameserver (DNS proxying enabled)

If you don't have a domain in Cloudflare yet, see the "Adding a Domain to Cloudflare" section at the end.

---

## Step-by-Step Setup

### Step 1: Connect Custom Domain to R2 Bucket

1. Log into Cloudflare Dashboard: https://dash.cloudflare.com
2. Navigate to **R2** in the left sidebar
3. Click on your bucket: **map**
4. Click the **Settings** tab
5. Scroll to **Public Access** section
6. Click **Connect Domain**
7. Enter your subdomain (recommended):
   - Example: `map.yourdomain.com`
   - Or use root domain: `yourdomain.com`
8. Click **Continue**
9. Cloudflare will automatically:
   - Create a CNAME record pointing to your R2 bucket
   - Enable proxying (orange cloud)
   - Link the domain to the bucket

**Wait 1-2 minutes** for DNS propagation.

---

### Step 2: Verify Domain Connection

Test that your domain is serving files from R2:

```bash
curl -I https://map.yourdomain.com/index.html
```

You should see:
- **Status: 200 OK**
- **Content-Type: text/html**
- **cf-cache-status: HIT** (or MISS on first request)

If you get 404 or connection errors, wait a few more minutes for DNS to propagate.

---

### Step 3: Create Transform Rule for Index.html

Now configure automatic index.html serving at the root URL.

1. In Cloudflare Dashboard, go to your domain (not R2)
2. Click **Rules** in the left sidebar
3. Click **Transform Rules**
4. Click **Create Rule** (or **Modify Request URL** tab → **Create Rule**)
5. Fill in the rule details:

**Rule name:**
```
Serve index.html at root
```

**When incoming requests match:**
- Select: **Custom filter expression**
- Click **Edit expression**
- Enter this expression:
```
(http.request.uri.path eq "/")
```

**Then:**
- Select: **Rewrite to**
- Choose: **Dynamic**
- Enter this value:
```
concat("/index.html", http.request.uri.query_string)
```

Or if you prefer static (simpler):
- Choose: **Static**
- Enter: `/index.html`

6. Click **Deploy**

---

### Step 4: Test Your Setup

Visit your custom domain at the root URL:

```
https://map.yourdomain.com
```

The map should load automatically without needing `/index.html` in the URL.

**Verification checklist:**
- ✅ Map loads at root URL
- ✅ Flight tracks display correctly
- ✅ Waypoints appear on map
- ✅ VFR tiles load (check browser console for errors)
- ✅ Zoom and pan work smoothly

---

## Troubleshooting

### Domain shows 404 error

**Cause:** DNS not propagated or domain not connected properly

**Fix:**
1. Check DNS: `dig map.yourdomain.com`
2. Verify CNAME points to R2 bucket
3. Wait 5-10 minutes for propagation
4. Check R2 bucket settings to confirm domain is connected

---

### Map loads at /index.html but not at root

**Cause:** Transform rule not active or incorrect expression

**Fix:**
1. Go to Rules → Transform Rules
2. Check if rule is enabled (toggle should be ON)
3. Verify expression: `(http.request.uri.path eq "/")`
4. Check rule is not being overridden by other rules
5. Clear browser cache and test in incognito mode

---

### Tiles don't load (broken images)

**Cause:** HTML still uses R2.dev URL for tiles instead of relative paths

**Fix:**
Check your HTML source. Tile URLs should be relative:
```html
<!-- Good (relative) -->
vfr_tiles/tiles/{z}/{x}/{y}.png

<!-- Bad (absolute R2.dev) -->
https://pub-32af5705466c411d82c79b436565f4a9.r2.dev/vfr_tiles/tiles/{z}/{x}/{y}.png
```

If tiles use absolute R2.dev URLs, regenerate the map with relative paths:
```bash
python -m olc_downloader.cli map \
  --airport-code STERL1 \
  --output-file /Users/thomasvdv/GitHub/olc-weglide/downloads/STERL1_map.html \
  --deployment-mode github-pages
```

Then re-upload:
```bash
rclone copy /Users/thomasvdv/GitHub/olc-weglide/downloads/STERL1_map.html \
  r2:map/index.html --progress
```

---

### SSL certificate errors

**Cause:** Cloudflare SSL not fully provisioned for new domain

**Fix:**
1. Go to **SSL/TLS** in Cloudflare Dashboard
2. Ensure mode is set to **Full** or **Flexible**
3. Wait 10-15 minutes for SSL certificate to provision
4. Check SSL status at bottom of SSL/TLS page

---

## Benefits of Custom Domain + Transform Rules

- ✅ **Clean URLs**: `map.yourdomain.com` instead of long R2.dev subdomain
- ✅ **Full Cloudflare Features**: WAF, DDoS protection, caching, analytics
- ✅ **Better Performance**: Cloudflare's global CDN with edge caching
- ✅ **Professional**: Custom branding for your map
- ✅ **No URL Rewriting**: Transform rule happens server-side (cleaner than Worker)
- ✅ **Zero Cost**: No Worker execution costs (Transform Rules are free)

---

## Adding a Domain to Cloudflare (If Needed)

If you don't have a domain in Cloudflare yet:

### Option A: Transfer Existing Domain

1. Go to https://dash.cloudflare.com
2. Click **Add a Site**
3. Enter your domain name
4. Choose **Free** plan
5. Cloudflare will scan your DNS records
6. Update your domain's nameservers at your registrar to Cloudflare's nameservers
7. Wait 24-48 hours for nameserver propagation

### Option B: Buy a Domain

1. Use a registrar like:
   - Cloudflare Registrar (at-cost pricing)
   - Namecheap
   - Google Domains (now Squarespace)
2. After purchase, add it to Cloudflare (follow Option A)

### Option C: Use a Subdomain (If You Already Have a Domain)

If you own `yourdomain.com` and it's already in Cloudflare:
- Just use a subdomain like `map.yourdomain.com`
- No additional setup needed
- Cloudflare automatically handles subdomains

---

## Current Configuration

**R2 Bucket:** `map`
**Account ID:** `fcb17c4ac43e2ef4c3b34010fa521a81`
**R2.dev Domain:** `pub-32af5705466c411d82c79b436565f4a9.r2.dev`

**Files in R2:**
- `index.html` - 111MB (109 flights, 462 waypoints)
- `vfr_tiles/tiles/` - 16,887 PNG files (3.7GB)

---

## Next Steps After Setup

1. **Test thoroughly** - Try on different devices and networks
2. **Update bookmarks** - Use your custom domain going forward
3. **Share the link** - Send your clean custom domain URL to others
4. **Monitor performance** - Check Cloudflare Analytics for traffic and caching stats
5. **Consider Cloudflare Images** - If you want to optimize PNG tiles further

---

## Alternative: Keep R2.dev + Worker

If you prefer not to use a custom domain, you can still use Option 1 (Cloudflare Worker) with your R2.dev domain. See `R2_INDEX_SETUP.md` for Worker setup instructions.

---

## Support Resources

- Cloudflare R2 Docs: https://developers.cloudflare.com/r2/
- Transform Rules: https://developers.cloudflare.com/rules/transform/
- Custom Domains: https://developers.cloudflare.com/r2/buckets/public-buckets/#custom-domains
