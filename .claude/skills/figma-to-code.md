---
name: figma-to-code
description: Use when converting Figma designs, mockups, screenshots, or visual references into code. Also use when the user shares an image of a UI they want built.
---

# Figma to Code

## Workflow

1. **Analyze the visual** — identify layout structure, component hierarchy, spacing, colors, typography, and interactive elements.
2. **Map to components** — break the design into reusable React/HTML components. Name them by purpose, not appearance.
3. **Build structure first** — semantic HTML with correct nesting before any styling.
4. **Apply styles** — use Tailwind utilities or CSS matching the design tokens exactly.
5. **Add interactions** — hover states, focus rings, transitions, responsive behavior.
6. **Verify fidelity** — compare output against the original pixel by pixel.

## Reading a Design

When analyzing a screenshot or Figma export:

- **Spacing** — estimate in 4px increments (Tailwind: 1=4px, 2=8px, 3=12px, 4=16px, 6=24px, 8=32px)
- **Font sizes** — map to Tailwind scale: `text-xs`(12), `text-sm`(14), `text-base`(16), `text-lg`(18), `text-xl`(20), `text-2xl`(24)
- **Font weight** — normal(400), medium(500), semibold(600), bold(700)
- **Border radius** — none(0), sm(2), default(4), md(6), lg(8), xl(12), 2xl(16), full(9999)
- **Shadows** — `shadow-sm`, `shadow`, `shadow-md`, `shadow-lg`, `shadow-xl`
- **Colors** — extract hex values and map to nearest Tailwind color or define custom tokens

## Component Decomposition

```
Page
├── Header (sticky, blur backdrop)
│   ├── Logo
│   ├── Navigation
│   └── UserMenu
├── Main
│   ├── Hero / PageHeader
│   ├── ContentSection
│   │   ├── Card[]
│   │   └── EmptyState
│   └── Sidebar (optional)
└── Footer
```

## Translation Rules

| Figma concept | Code equivalent |
|---------------|----------------|
| Frame | `<div>` with flex/grid |
| Auto Layout (vertical) | `flex flex-col gap-*` |
| Auto Layout (horizontal) | `flex flex-row gap-*` |
| Fill container | `w-full` or `flex-1` |
| Hug contents | `w-fit` or default |
| Fixed size | `w-[Npx]` or `h-[Npx]` |
| Constraints (center) | `mx-auto` or `place-items-center` |
| Component instance | React component with props |
| Variants | Props or conditional classes |
| Prototype interaction | Event handler + state |

## Precision Checklist

- [ ] Spacing matches design (within 2px)
- [ ] Colors are exact hex matches
- [ ] Typography (family, size, weight, line-height) matches
- [ ] Border radius matches
- [ ] Shadows match
- [ ] Icons are correct (Lucide, Heroicons, or SVG)
- [ ] Responsive behavior is defined
- [ ] Hover/focus/active states exist
- [ ] Dark mode variant exists (if applicable)
