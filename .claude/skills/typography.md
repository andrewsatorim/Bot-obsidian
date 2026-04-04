---
name: typography
description: Use when choosing fonts, creating type hierarchy, pairing typefaces, setting line-height/tracking, or optimizing web font loading. Also use when text "doesn't look right."
---

# Typography

## Type Scale

### Recommended Scale (Major Third — 1.25 ratio)
| Name | Size | Tailwind | Use for |
|------|------|----------|---------|
| xs | 12px | `text-xs` | Captions, metadata, badges |
| sm | 14px | `text-sm` | Secondary text, labels |
| base | 16px | `text-base` | Body text (default) |
| lg | 18px | `text-lg` | Lead paragraphs, subtitles |
| xl | 20px | `text-xl` | Section titles (H3) |
| 2xl | 24px | `text-2xl` | Page sections (H2) |
| 3xl | 30px | `text-3xl` | Page title (H1) |
| 4xl | 36px | `text-4xl` | Hero headline |
| 5xl | 48px | `text-5xl` | Landing page hero |
| 6xl | 60px | `text-6xl` | Marketing splash |

**Rule:** Use 4-5 sizes max in a single UI. More = visual noise.

## Font Pairing

### Proven Combinations
| Display (headings) | Body (text) | Vibe |
|-------------------|-------------|------|
| **Inter** | Inter | Clean, modern, all-purpose |
| **Cal Sans** | Inter | SaaS, product |
| **Instrument Serif** | Inter | Elegant + modern |
| **Playfair Display** | Source Sans 3 | Editorial, luxury |
| **Space Grotesk** | DM Sans | Tech, developer |
| **Fraunces** | Commissioner | Warm, approachable |
| **Bricolage Grotesque** | Geist | Bold, contemporary |
| **Geist** | Geist | Vercel-style minimalism |
| **Sora** | Noto Sans | Global, multilingual |
| **System UI stack** | System UI stack | Maximum performance |

### System Font Stack (No downloads)
```css
font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
             Roboto, "Helvetica Neue", Arial, sans-serif;

/* Monospace */
font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo,
             Consolas, "Liberation Mono", monospace;
```

### Pairing Rules
1. **Max 2 fonts** — one display, one body (or one font for everything)
2. **Contrast** — serif + sans-serif, or different weights of same family
3. **Same x-height** — fonts should align visually at same size
4. **One personality** — display font can be expressive, body must be neutral
5. **Test with real content** — lorem ipsum hides readability issues

## Line Height (Leading)

| Content type | Line height | Tailwind |
|-------------|-------------|----------|
| Headings (large) | 1.1 - 1.2 | `leading-tight` |
| Headings (small) | 1.2 - 1.3 | `leading-snug` |
| Body text | 1.5 - 1.7 | `leading-relaxed` |
| UI labels / buttons | 1.0 - 1.2 | `leading-none` / `leading-tight` |
| Long-form reading | 1.6 - 1.8 | `leading-relaxed` / `leading-loose` |
| Code | 1.5 - 1.6 | `leading-normal` |

**Rule:** Longer lines need more line height. Short UI labels need less.

## Letter Spacing (Tracking)

| Context | Tracking | Tailwind |
|---------|----------|----------|
| Large headings (48px+) | -0.02em to -0.04em | `tracking-tighter` |
| Medium headings | -0.01em to -0.02em | `tracking-tight` |
| Body text | 0 (default) | `tracking-normal` |
| ALL CAPS text | 0.05em to 0.1em | `tracking-wide` / `tracking-wider` |
| Small text (12px) | 0.01em | `tracking-wide` |

**Rule:** Large text needs tighter tracking. Small text and ALL CAPS need looser.

## Font Weight

| Weight | Value | Use for |
|--------|-------|---------|
| Regular | 400 | Body text, paragraphs |
| Medium | 500 | Labels, navigation, emphasis |
| Semibold | 600 | Subheadings, button text, important labels |
| Bold | 700 | Headings, key values, prices |

**Rule:** Use 2-3 weights max. More = visual confusion. Semibold (600) is often better than bold (700) for UI.

## Variable Fonts

```css
/* One file, all weights */
@font-face {
  font-family: "Inter";
  src: url("/fonts/Inter-Variable.woff2") format("woff2-variations");
  font-weight: 100 900;        /* range */
  font-display: swap;
}

/* Use any weight */
h1 { font-weight: 750; }       /* between bold and extrabold */
.caption { font-weight: 350; } /* between light and regular */
```

**Benefits:** Smaller file size (one file vs multiple), precise control, smooth transitions.

## Web Font Loading

### Next.js (Optimal)
```tsx
// app/layout.tsx
import { Inter, Instrument_Serif } from "next/font/google"

const inter = Inter({ subsets: ["latin", "cyrillic"], variable: "--font-inter" })
const serif = Instrument_Serif({ weight: "400", subsets: ["latin"], variable: "--font-serif" })

export default function Layout({ children }) {
  return (
    <html className={`${inter.variable} ${serif.variable}`}>
      <body className="font-sans">{children}</body>
    </html>
  )
}
```

### Self-Hosted (Maximum Control)
```css
@font-face {
  font-family: "CustomFont";
  src: url("/fonts/custom.woff2") format("woff2");
  font-weight: 400;
  font-display: swap;           /* show fallback immediately */
  unicode-range: U+0000-00FF;   /* latin only — smaller download */
}
```

### Performance Rules
- **woff2 only** — best compression, 95%+ browser support
- **font-display: swap** — prevents invisible text (FOIT)
- **Preload critical fonts** — `<link rel="preload" href="font.woff2" as="font" crossorigin>`
- **Subset** — only include character sets you use (latin, cyrillic)
- **2 fonts max** — each font file = extra network request
- **Variable font** if using 3+ weights (one file instead of many)

## Measure (Line Length)

| Context | Characters per line | Tailwind max-width |
|---------|--------------------|--------------------|
| **Body text** | 45-75 chars (ideal: 66) | `max-w-prose` (65ch) |
| **Wide content** | 75-90 chars | `max-w-3xl` |
| **Narrow column** | 30-45 chars | `max-w-sm` |
| **Headlines** | No limit, but shorter is better | — |

```html
<!-- Optimal reading width -->
<article class="max-w-prose mx-auto">
  <p>Long-form text that's comfortable to read...</p>
</article>
```

## Responsive Typography

```css
/* Fluid type — scales with viewport */
h1 {
  font-size: clamp(2rem, 5vw, 4rem);    /* min: 32px, max: 64px */
}

p {
  font-size: clamp(1rem, 1.5vw, 1.125rem); /* min: 16px, max: 18px */
}
```

### Tailwind Responsive
```html
<h1 class="text-3xl sm:text-4xl lg:text-5xl xl:text-6xl">
  Responsive Headline
</h1>
```

## Typographic Hierarchy Checklist

```
Page structure:
  H1 — 1 per page, largest, boldest               text-4xl font-bold
  H2 — Section headers                            text-2xl font-semibold
  H3 — Subsection headers                         text-xl font-semibold
  Body — Default reading text                      text-base font-normal
  Secondary — Supporting info, metadata            text-sm text-muted
  Caption — Smallest readable text                 text-xs text-muted
```

## Typography Checklist

- [ ] Max 2 font families loaded
- [ ] 4-5 font sizes used consistently (not arbitrary)
- [ ] Body text ≥ 16px (never smaller for reading)
- [ ] Line height 1.5-1.7 for body text
- [ ] Line length 45-75 characters (`max-w-prose`)
- [ ] Large headings have tight letter-spacing
- [ ] ALL CAPS text has wide letter-spacing
- [ ] Font weights: regular (400) + semibold (600) + bold (700) max
- [ ] `font-display: swap` on all web fonts
- [ ] Fonts preloaded or using Next.js font optimization
- [ ] Responsive: heading sizes scale down on mobile
- [ ] Sufficient contrast: body text vs background ≥ 4.5:1
