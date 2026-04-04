---
name: color-theory
description: Use when choosing color palettes, creating themes, ensuring contrast, working with gradients, or when colors "feel wrong." Also use for dark mode color mapping and brand color selection.
---

# Color Theory

## Color Psychology

| Color | Association | Best for |
|-------|------------|---------|
| **Blue** | Trust, stability, calm | Finance, SaaS, healthcare |
| **Green** | Growth, success, nature | Fintech, eco, health |
| **Purple** | Premium, creative, luxury | Design tools, premium products |
| **Red** | Energy, urgency, danger | Food, sales, error states |
| **Orange** | Friendly, warm, action | CTAs, community products |
| **Yellow** | Optimism, attention, warning | Highlights, warnings |
| **Black** | Luxury, power, sophistication | Fashion, premium brands |
| **White** | Clean, minimal, space | Most SaaS, content products |

## Palette Generation

### Method 1: HSL-Based (Recommended)
```
Pick ONE hue → Generate a scale by varying Saturation and Lightness

Primary: hsl(220, 90%, 56%)      → Blue
         hsl(220, 90%, 96%)      → 50  (lightest)
         hsl(220, 90%, 90%)      → 100
         hsl(220, 85%, 80%)      → 200
         hsl(220, 80%, 65%)      → 300
         hsl(220, 85%, 56%)      → 400
         hsl(220, 90%, 48%)      → 500 (primary)
         hsl(220, 90%, 40%)      → 600
         hsl(220, 85%, 32%)      → 700
         hsl(220, 80%, 24%)      → 800
         hsl(220, 75%, 16%)      → 900
         hsl(220, 70%, 8%)       → 950 (darkest)
```

### Method 2: OKLCH (Perceptually Uniform)
```css
/* Modern CSS — colors look equally bright across hues */
:root {
  --primary-50:  oklch(97% 0.01 250);
  --primary-100: oklch(93% 0.03 250);
  --primary-200: oklch(85% 0.06 250);
  --primary-300: oklch(75% 0.10 250);
  --primary-400: oklch(65% 0.15 250);
  --primary-500: oklch(55% 0.20 250);  /* primary */
  --primary-600: oklch(48% 0.18 250);
  --primary-700: oklch(40% 0.15 250);
  --primary-800: oklch(30% 0.10 250);
  --primary-900: oklch(22% 0.06 250);
  --primary-950: oklch(15% 0.03 250);
}
```

### Method 3: Tailwind Custom Colors
```javascript
// tailwind.config.js
colors: {
  brand: {
    50:  "#f0f7ff",
    100: "#e0efff",
    200: "#b8dbff",
    300: "#7ac0ff",
    400: "#36a3ff",
    500: "#0088ff",  // primary
    600: "#006dd4",
    700: "#0056ab",
    800: "#00478d",
    900: "#003c74",
    950: "#00254d",
  }
}
```

## Contrast & Accessibility

### WCAG Requirements
| Level | Ratio | For |
|-------|-------|-----|
| **AA** | 4.5:1 | Normal text (< 18px) |
| **AA** | 3:1 | Large text (≥ 18px bold or ≥ 24px) |
| **AA** | 3:1 | UI components (borders, icons) |
| **AAA** | 7:1 | Enhanced (for low-vision users) |

### Quick Contrast Check
```
White background (#fff):
  ✓ gray-600 (#525252) → 7.5:1 — passes AAA
  ✓ gray-500 (#737373) → 4.6:1 — passes AA
  ✗ gray-400 (#a3a3a3) → 2.6:1 — FAILS

Dark background (#0a0a0a):
  ✓ gray-300 (#d4d4d4) → 12:1 — passes AAA
  ✓ gray-400 (#a3a3a3) → 7.4:1 — passes AAA
  ✗ gray-500 (#737373) → 4.2:1 — borderline
```

### Tools
- **WebAIM Contrast Checker** — paste two colors, get ratio
- **Polypane Color Contrast** — test against WCAG
- **Figma A11y plugin** — check entire design
- **Chrome DevTools** → inspect element → contrast ratio shown

## Neutral Scale (Gray)

### Warm Gray (Friendly, Organic)
```css
--gray-50:  #fafaf9;  /* stone-50 */
--gray-500: #78716c;  /* stone-500 */
--gray-900: #1c1917;  /* stone-900 */
```

### Cool Gray (Tech, Professional)
```css
--gray-50:  #f9fafb;  /* gray-50 */
--gray-500: #6b7280;  /* gray-500 */
--gray-900: #111827;  /* gray-900 */
```

### True Gray (Neutral, Minimal)
```css
--gray-50:  #fafafa;  /* neutral-50 */
--gray-500: #737373;  /* neutral-500 */
--gray-900: #171717;  /* neutral-900 */
```

### Tinted Gray (Brand-Aligned)
```css
/* Mix your primary hue into gray for cohesion */
/* If primary is blue (220°), add subtle blue tint to grays */
--gray-50:  hsl(220, 10%, 98%);
--gray-500: hsl(220, 5%, 45%);
--gray-900: hsl(220, 10%, 10%);
```

## Semantic Colors

```css
:root {
  /* Success */
  --success: #22c55e;           /* green-500 */
  --success-light: #f0fdf4;     /* green-50 */
  --success-text: #15803d;      /* green-700 */

  /* Warning */
  --warning: #f59e0b;           /* amber-500 */
  --warning-light: #fffbeb;     /* amber-50 */
  --warning-text: #b45309;      /* amber-700 */

  /* Error */
  --error: #ef4444;             /* red-500 */
  --error-light: #fef2f2;       /* red-50 */
  --error-text: #dc2626;        /* red-600 */

  /* Info */
  --info: #3b82f6;              /* blue-500 */
  --info-light: #eff6ff;        /* blue-50 */
  --info-text: #2563eb;         /* blue-600 */
}
```

## Gradients

### Natural Gradients (Hue Shift)
```css
/* Shift hue 20-40° for natural-feeling gradients */
.gradient-blue { background: linear-gradient(135deg, #3b82f6, #8b5cf6); }  /* blue → violet */
.gradient-sunset { background: linear-gradient(135deg, #f59e0b, #ef4444); }  /* amber → red */
.gradient-ocean { background: linear-gradient(135deg, #06b6d4, #3b82f6); }  /* cyan → blue */

/* Subtle gradient (backgrounds) */
.gradient-subtle { background: linear-gradient(180deg, #fafafa 0%, #f0f0f0 100%); }

/* Mesh gradient (modern, organic) */
.gradient-mesh {
  background:
    radial-gradient(at 20% 20%, #3b82f6 0%, transparent 50%),
    radial-gradient(at 80% 80%, #8b5cf6 0%, transparent 50%),
    radial-gradient(at 50% 50%, #06b6d4 0%, transparent 50%);
}
```

### Gradient Rules
- Shift hue 20-40° between stops (not complementary — that looks muddy)
- Use 2-3 color stops max
- `135deg` or `180deg` angles work best
- Add subtle noise texture on top to reduce banding
- Don't put text on gradients without overlay

## Dark Mode Color Mapping

```
Light                    →    Dark
white (#fff)             →    gray-950 (#0a0a0a)
gray-50 (#fafafa)        →    gray-900 (#171717)
gray-100 (#f5f5f5)       →    gray-800 (#262626)
gray-900 text (#171717)  →    gray-50 text (#fafafa)
gray-500 muted (#737373) →    gray-400 muted (#a3a3a3)
primary-500 (#3b82f6)    →    primary-400 (#60a5fa)    ← lighter in dark!
border gray-200          →    border gray-800
shadow (black/10%)       →    shadow (black/40%)
```

**Key rule:** Primary color gets 1-2 steps lighter in dark mode (500 → 400). Otherwise it feels too dim.

## Color Checklist

- [ ] One primary color with full 50-950 scale
- [ ] Neutral gray scale chosen (warm, cool, or tinted)
- [ ] Semantic colors defined (success, warning, error, info)
- [ ] All text passes WCAG AA contrast (4.5:1 minimum)
- [ ] Dark mode: all surfaces, text, and borders remapped
- [ ] Primary color adjusted for dark mode (lighter shade)
- [ ] No information conveyed by color alone (use icons, text too)
- [ ] Colors defined as CSS variables or Tailwind config (not hardcoded)
- [ ] Gradients use hue-shifted stops (not random colors)
- [ ] Tested with color blindness simulator (Sim Daltonism, Chrome DevTools)
