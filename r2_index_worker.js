// Cloudflare Worker to serve index.html at root URL for R2 bucket
// Deploy this at your R2.dev domain or custom domain

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // If requesting root path, rewrite to /index.html
    if (url.pathname === '/') {
      url.pathname = '/index.html';
    }

    // Construct R2 public URL
    const r2Url = `https://pub-32af5705466c411d82c79b436565f4a9.r2.dev${url.pathname}`;

    // Fetch from R2
    const response = await fetch(r2Url, {
      method: request.method,
      headers: request.headers,
    });

    // Return response with appropriate caching headers
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: {
        ...Object.fromEntries(response.headers),
        'Cache-Control': 'public, max-age=3600', // 1 hour cache
      },
    });
  }
}
