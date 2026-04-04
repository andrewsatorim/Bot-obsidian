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

## International SEO (i18n)

### hreflang Tags
```html
<link rel="alternate" hreflang="en" href="https://example.com/page" />
<link rel="alternate" hreflang="ru" href="https://example.com/ru/page" />
<link rel="alternate" hreflang="x-default" href="https://example.com/page" />
```

### Next.js i18n
```typescript
// next.config.js
module.exports = {
  i18n: {
    locales: ["en", "ru", "es"],
    defaultLocale: "en",
  },
}
```

### URL Strategy
| Strategy | Example | Best for |
|----------|---------|----------|
| Subdirectories | `/ru/page` | Most projects (recommended) |
| Subdomains | `ru.example.com` | Large regional sites |
| ccTLDs | `example.ru` | Strong local presence needed |

## SPA / SSR SEO

### Problem: Client-side Rendering
Search engines may not execute JavaScript properly → empty content indexed.

### Solutions
| Approach | Framework | SEO quality |
|----------|-----------|-------------|
| **SSR** (Server-Side Render) | Next.js `getServerSideProps` | Excellent |
| **SSG** (Static Generation) | Next.js `generateStaticParams` | Excellent |
| **ISR** (Incremental Static) | Next.js `revalidate` | Excellent |
| **Prerendering** | prerender.io, Rendertron | Good |
| **CSR only** | Plain React/Vue | Poor |

**Rule:** Any page that needs to rank in search must be SSR or SSG.

## Google Search Console

### Key Reports
- **Performance** — clicks, impressions, CTR, position per query
- **Coverage** — indexed vs excluded pages, errors
- **Core Web Vitals** — field data for LCP, INP, CLS
- **Sitemaps** — submission status

### Common Issues to Fix
| Issue | Fix |
|-------|-----|
| "Crawled - currently not indexed" | Improve content quality, add internal links |
| "Duplicate without user-selected canonical" | Add `<link rel="canonical">` |
| "Page with redirect" | Fix redirect chains (max 1 hop) |
| "Soft 404" | Return proper 404 status code |
| "Mobile usability" | Fix viewport, tap targets, font size |

## SEO Verification Checklist

- [ ] Google Search Console connected and verified
- [ ] sitemap.xml submitted and no errors
- [ ] robots.txt allows crawling of important pages
- [ ] No broken links (use `npx broken-link-checker http://localhost:3000`)
- [ ] Page speed score > 90 (mobile and desktop)
- [ ] Structured data validates (Google Rich Results Test)
- [ ] OG tags render correctly (use ogimage.dev or metatags.io to preview)
- [ ] hreflang set for multi-language pages
- [ ] No duplicate content (canonical URLs set)
- [ ] Mobile-friendly (Google Mobile-Friendly Test)
