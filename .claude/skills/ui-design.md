---
name: ui-design
description: Use when building UI components, layouts, styling, responsive design, animations, or any frontend visual work. Applies to React, Next.js, HTML/CSS, Tailwind, and similar.
---

# UI / Web Design

## Core Principles

1. **Mobile-first** — start with the smallest breakpoint, layer up with `sm:`, `md:`, `lg:`, `xl:`.
2. **Semantic HTML** — use `<nav>`, `<main>`, `<section>`, `<article>`, `<aside>`, `<header>`, `<footer>`. Never `<div>` soup.
3. **Accessibility first** — every interactive element must be keyboard-navigable, have focus styles, and use ARIA labels where native semantics aren't enough. Color contrast minimum 4.5:1 (AA).
4. **Progressive enhancement** — core content works without JS. Animations and interactions are enhancements.
5. **Performance** — lazy-load images, use `loading="lazy"`, prefer CSS animations over JS, minimize layout shifts (CLS).

## Layout Patterns

- **Container** — max-width with auto margins: `max-w-7xl mx-auto px-4 sm:px-6 lg:px-8`
- **Stack** — vertical spacing with `space-y-*` or `gap-*` in flex/grid
- **Sidebar** — `grid grid-cols-[280px_1fr]` or flex with fixed sidebar
- **Holy Grail** — header/main(sidebar+content)/footer with `min-h-screen` and `flex flex-col`
- **Card Grid** — `grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6`
- **Sticky header** — `sticky top-0 z-40 backdrop-blur bg-white/80`

## Component Patterns

- **Button variants** — primary (filled), secondary (outline), ghost (transparent), destructive (red)
- **Input states** — default, focus (ring), error (red border + message), disabled (opacity)
- **Modal** — portal to body, focus trap, close on Escape, backdrop click
- **Toast/Notification** — fixed position, auto-dismiss, stack from bottom
- **Skeleton loading** — `animate-pulse bg-gray-200 rounded` matching content shape

## Tailwind Best Practices

- Extract repeated patterns into components, NOT `@apply` classes
- Use design tokens via `tailwind.config` (colors, spacing, fonts)
- Group utilities logically: layout → sizing → spacing → typography → colors → effects
- Use `clsx` or `cn()` (tailwind-merge) for conditional classes
- Prefer `gap-*` over margin for spacing between siblings

## Animation Guidelines

- Use `transition-*` for state changes (hover, focus, active)
- Use `animate-*` or `@keyframes` for autonomous animations
- Respect `prefers-reduced-motion`: wrap motion in `motion-safe:` or check `useReducedMotion()`
- Duration: micro-interactions 150-200ms, transitions 200-300ms, entrances 300-500ms
- Easing: `ease-out` for entrances, `ease-in` for exits, `ease-in-out` for ongoing

## Responsive Breakpoints

| Token | Min-width | Target |
|-------|-----------|--------|
| `sm`  | 640px     | Large phones |
| `md`  | 768px     | Tablets |
| `lg`  | 1024px    | Laptops |
| `xl`  | 1280px    | Desktops |
| `2xl` | 1536px    | Large screens |

## Color Usage

- **1 primary color** for CTAs and key actions
- **1 neutral scale** (gray) for text, borders, backgrounds
- **Semantic colors**: success (green), warning (amber), error (red), info (blue)
- Always define both light and dark mode variants
- Use opacity variants (`bg-black/50`) for overlays

## shadcn/ui + Radix Patterns

### Setup
```bash
npx shadcn@latest init
npx shadcn@latest add button input card dialog
```

### Component Usage
```tsx
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog"

<Dialog>
  <DialogTrigger asChild>
    <Button variant="outline">Open</Button>
  </DialogTrigger>
  <DialogContent>
    <h2>Dialog Title</h2>
    <p>Content here</p>
  </DialogContent>
</Dialog>
```

### cn() Utility (tailwind-merge + clsx)
```typescript
import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// Usage — safely merge conditional classes
<div className={cn("p-4 rounded-lg", isActive && "bg-primary text-white", className)} />
```

## Accessibility (a11y) Testing

### Automated Tools
```bash
# axe-core (most comprehensive)
npm install -D @axe-core/playwright
# In Playwright test:
import AxeBuilder from "@axe-core/playwright"
const results = await new AxeBuilder({ page }).analyze()
expect(results.violations).toEqual([])

# eslint-plugin-jsx-a11y (catch at lint time)
npm install -D eslint-plugin-jsx-a11y
```

### Manual Testing Checklist
- [ ] Navigate entire page with Tab only — logical order, visible focus
- [ ] All images have meaningful alt text (or `alt=""` for decorative)
- [ ] Color contrast ≥ 4.5:1 (text) / 3:1 (large text) — check with WebAIM contrast checker
- [ ] Screen reader reads content logically (test with VoiceOver / NVDA)
- [ ] Forms: every input has visible label, errors announced to screen reader
- [ ] Modals trap focus and close on Escape
- [ ] No content conveyed by color alone
- [ ] Touch targets ≥ 44x44px on mobile
- [ ] `prefers-reduced-motion` respected for animations
- [ ] `lang` attribute set on `<html>` tag

### ARIA Quick Reference
```html
<!-- Only use ARIA when native HTML can't express the semantics -->
<button aria-label="Close dialog">×</button>
<div role="alert">Error: invalid email</div>
<nav aria-label="Main navigation">...</nav>
<div aria-live="polite">3 results found</div>  <!-- dynamic content -->
<button aria-expanded="false" aria-controls="menu-1">Menu</button>
```

## Dark Mode Implementation

```tsx
// Tailwind: class-based dark mode
// tailwind.config.js: darkMode: "class"

// Theme toggle
function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">("light")
  
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark")
  }, [theme])
  
  return <button onClick={() => setTheme(t => t === "light" ? "dark" : "light")}>Toggle</button>
}

// Usage in components
<div className="bg-white dark:bg-gray-950 text-gray-900 dark:text-gray-50">
```

## UI Design Verification

- [ ] Responsive: works on 320px (small phone) to 2560px (ultrawide)
- [ ] Dark mode: all surfaces, text, borders have dark variants
- [ ] Loading states: skeleton or spinner for every async operation
- [ ] Empty states: helpful message + CTA when no data
- [ ] Error states: clear message + recovery action
- [ ] Focus visible on all interactive elements
- [ ] Touch targets ≥ 44px on mobile
- [ ] No horizontal scroll on any breakpoint
- [ ] Animations respect `prefers-reduced-motion`
