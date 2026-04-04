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
