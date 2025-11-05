# Configuring Index Document Serving for R2

Your map is successfully uploaded to R2, but R2.dev domains don't automatically serve `index.html` at the root URL. Here are three solutions to fix this:

## Current Status

- ✅ VFR tiles uploaded: 16,887 files (3.7GB)
- ✅ Map HTML uploaded: `index.html` (111MB)
- ✅ Public access enabled: `https://pub-32af5705466c411d82c79b436565f4a9.r2.dev`
- ❌ Root URL doesn't serve index.html automatically

## Solution Options

### Option 1: Cloudflare Worker (Recommended for R2.dev)

This works with your existing R2.dev domain without requiring a custom domain.

**Steps:**

1. Log into Cloudflare Dashboard: https://dash.cloudflare.com
2. Go to **Workers & Pages** → **Create Application** → **Create Worker**
3. Name it: `r2-map-index-handler`
4. Click **Deploy**, then **Edit Code**
5. Replace the code with the contents of `r2_index_worker.js` (in this directory)
6. Click **Save and Deploy**
7. Go to **Settings** → **Triggers** → **Add Route**
8. Add route pattern: `pub-32af5705466c411d82c79b436565f4a9.r2.dev/*`

**Result:** Your map will be accessible at:
- https://pub-32af5705466c411d82c79b436565f4a9.r2.dev (root)
- https://pub-32af5705466c411d82c79b436565f4a9.r2.dev/index.html (explicit)

---

### Option 2: Custom Domain + Transform Rules (Best for Production)

If you have a domain managed by Cloudflare (e.g., `map.yourdomain.com`), this is the cleanest solution.

**Steps:**

1. In Cloudflare Dashboard, go to your R2 bucket: **R2** → **map**
2. Click **Settings** → **Public Access** → **Connect Domain**
3. Enter your custom domain (e.g., `map.yourdomain.com`)
4. Cloudflare will create the necessary DNS records automatically
5. Go to **Rules** → **Transform Rules** → **Rewrite URL**
6. Create rule:
   - **When incoming requests match:** Custom filter expression
   - Expression: `(http.request.uri.path eq "/")`
   - **Rewrite to:** Static value: `/index.html`
7. Deploy the rule

**Result:** Your map will be accessible at:
- https://map.yourdomain.com (root)
- Clean, professional URL

---

### Option 3: Redirect Rule in Cloudflare Dashboard (Simple)

A quick workaround if you just want a redirect (shows `/index.html` in the browser).

**Steps:**

1. Set up a custom domain (as in Option 2, steps 1-4)
2. Go to **Rules** → **Redirect Rules** → **Create Rule**
3. Rule name: `Redirect root to index`
4. When incoming requests match: `(http.request.uri.path eq "/")`
5. URL redirect:
   - Type: **Static**
   - URL: `/index.html`
   - Status code: **301** (permanent)
6. Deploy the rule

**Result:** Visiting the root redirects to `/index.html`

---

## Recommended Approach

For immediate results with your R2.dev domain: **Use Option 1 (Cloudflare Worker)**

For production/permanent setup: **Use Option 2 (Custom Domain + Transform Rules)**

---

## Testing

After deploying any solution:

1. Visit the root URL (without `/index.html`)
2. The map should load automatically
3. Check browser console for any tile loading errors
4. Verify flight tracks and waypoints display correctly

---

## Troubleshooting

**Worker not intercepting requests:**
- Check the route pattern includes `/*`
- Verify the Worker is deployed and active
- Check Cloudflare Dashboard → Workers → Metrics for traffic

**Transform rule not working:**
- Ensure the custom domain is proxied (orange cloud in DNS)
- Verify the rule is enabled and deployed
- Check rule order (should be processed first)

**Tiles don't load:**
- Check browser console for CORS errors
- Verify VFR tiles are accessible at: `https://pub-32af5705466c411d82c79b436565f4a9.r2.dev/vfr_tiles/tiles/10/307/372.png`

---

## File Locations

- **Worker Script:** `r2_index_worker.js` (this directory)
- **R2 Bucket:** `map`
- **R2.dev Domain:** `pub-32af5705466c411d82c79b436565f4a9.r2.dev`
- **Account ID:** `fcb17c4ac43e2ef4c3b34010fa521a81`
