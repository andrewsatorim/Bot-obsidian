---
name: seo
description: Use when adding meta tags, Open Graph data, structured data, sitemaps, robots.txt, or optimizing pages for search engines and social sharing.
---

# SEO & Web Presence

## Essential Meta Tags

```html
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Page Title — Brand (50-60 chars)</title>
  <meta name="description" content="Compelling description of the page. 150-160 characters." />
  <link rel="canonical" href="https://example.com/page" />
  <meta name="robots" content="index, follow" />
</head>
```

## Open Graph (Social Sharing)

```html
<meta property="og:type" content="website" />
<meta property="og:title" content="Page Title" />
<meta property="og:description" content="Description for social cards." />
<meta property="og:image" content="https://example.com/og-image.png" />
<meta property="og:url" content="https://example.com/page" />
<meta property="og:site_name" content="Brand Name" />

<!-- Twitter -->
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="Page Title" />
<meta name="twitter:description" content="Description." />
<meta name="twitter:image" content="https://example.com/twitter-image.png" />
```

**OG Image specs:** 1200x630px, < 8MB, PNG or JPG.

## Next.js Metadata API

```tsx
// app/page.tsx
export const metadata: Metadata = {
  title: "Page Title",
  description: "Description",
  openGraph: {
    title: "Page Title",
    description: "Description",
    images: [{ url: "/og-image.png", width: 1200, height: 630 }],
  },
  twitter: { card: "summary_large_image" },
  alternates: { canonical: "https://example.com/page" },
}
```

## Structured Data (JSON-LD)

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "Brand",
  "url": "https://example.com",
  "logo": "https://example.com/logo.png",
  "sameAs": [
    "https://twitter.com/brand",
    "https://github.com/brand"
  ]
}
</script>
```

### Common Schema Types

| Type | Use for |
|------|---------|
| `Organization` | Company/brand homepage |
| `Product` | E-commerce product pages |
| `Article` | Blog posts, news |
| `BreadcrumbList` | Navigation breadcrumbs |
| `FAQ` | FAQ pages (rich results) |
| `HowTo` | Tutorial/guide pages |
| `SoftwareApplication` | App/SaaS landing pages |
| `WebSite` | Site-wide search box |

## Technical SEO

### Sitemap (sitemap.xml)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://example.com/</loc>
    <lastmod>2026-01-01</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
```

### robots.txt

```
User-agent: *
Allow: /
Disallow: /api/
Disallow: /admin/
Sitemap: https://example.com/sitemap.xml
```

### Performance Impact on SEO

- **LCP < 2.5s** — Google ranking factor
- **Mobile-friendly** — responsive design required
- **HTTPS** — ranking signal
- **No CLS** — layout shifts hurt rankings
- **Fast TTFB** — server response < 600ms

## Content SEO Checklist

- [ ] One `<h1>` per page with target keyword
- [ ] Heading hierarchy: h1 → h2 → h3 (no skipping)
- [ ] Descriptive URLs: `/blog/how-to-deploy` not `/blog/post-123`
- [ ] Alt text on all images (descriptive, not keyword-stuffed)
- [ ] Internal links between related pages
- [ ] External links to authoritative sources
- [ ] Unique title and description per page
- [ ] Canonical URL set on every page
