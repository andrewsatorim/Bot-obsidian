---
name: motion-design
description: Use when adding animations, micro-interactions, page transitions, loading animations, or any motion to UI. Covers Framer Motion, CSS animations, GSAP, Lottie, and spring physics.
---

# Motion Design

## When to Animate

| Purpose | Example | Duration |
|---------|---------|----------|
| **Feedback** | Button press, toggle switch | 100-200ms |
| **State change** | Accordion open, tab switch | 200-300ms |
| **Entrance** | Card appears, modal opens | 300-500ms |
| **Exit** | Modal closes, toast disappears | 200-300ms |
| **Attention** | Notification pulse, error shake | 300-600ms |
| **Delight** | Success confetti, onboarding | 500-1000ms |
| **Navigation** | Page transition, route change | 300-500ms |

### Don't Animate
- Content the user is trying to read
- Things that happen frequently (every keystroke)
- Anything that blocks the user from acting
- Without respecting `prefers-reduced-motion`

## Framer Motion (React)

### Setup
```bash
npm install framer-motion
```

### Basic Animations
```tsx
import { motion } from "framer-motion"

// Fade in
<motion.div
  initial={{ opacity: 0 }}
  animate={{ opacity: 1 }}
  transition={{ duration: 0.3 }}
/>

// Slide up on enter
<motion.div
  initial={{ opacity: 0, y: 20 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 0.4, ease: "easeOut" }}
/>

// Scale on hover
<motion.button
  whileHover={{ scale: 1.05 }}
  whileTap={{ scale: 0.95 }}
  transition={{ type: "spring", stiffness: 400, damping: 17 }}
/>
```

### Page Transitions (Next.js App Router)
```tsx
// app/template.tsx — wraps every page
"use client"
import { motion } from "framer-motion"

export default function Template({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  )
}
```

### AnimatePresence (Exit Animations)
```tsx
import { AnimatePresence, motion } from "framer-motion"

<AnimatePresence mode="wait">
  {isVisible && (
    <motion.div
      key="modal"
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.2 }}
    />
  )}
</AnimatePresence>
```

### Layout Animations (Magic Move)
```tsx
// Elements auto-animate between positions
<motion.div layout layoutId="card-1" className="..." />

// Shared layout animation (card → detail view)
<motion.div layoutId={`card-${id}`}>
  <motion.h2 layoutId={`title-${id}`}>{title}</motion.h2>
</motion.div>
```

### Stagger Children
```tsx
const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.05 }
  }
}

const item = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0 }
}

<motion.ul variants={container} initial="hidden" animate="show">
  {items.map(i => (
    <motion.li key={i.id} variants={item}>{i.name}</motion.li>
  ))}
</motion.ul>
```

### Scroll Animations
```tsx
import { motion, useScroll, useTransform } from "framer-motion"

function ParallaxHero() {
  const { scrollY } = useScroll()
  const y = useTransform(scrollY, [0, 500], [0, -150])
  const opacity = useTransform(scrollY, [0, 300], [1, 0])

  return (
    <motion.div style={{ y, opacity }}>
      <h1>Hero Title</h1>
    </motion.div>
  )
}
```

## CSS Animations (No Library)

### Transitions
```css
/* Hover effect */
.button {
  transition: all 200ms ease-out;
}
.button:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

/* Skeleton loading */
.skeleton {
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}
@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
```

### Tailwind Animation Classes
```html
<!-- Built-in -->
<div class="animate-spin" />       <!-- loading spinner -->
<div class="animate-pulse" />      <!-- skeleton loading -->
<div class="animate-bounce" />     <!-- attention -->
<div class="animate-ping" />       <!-- notification dot -->

<!-- Custom in tailwind.config.js -->
animation: {
  "fade-in": "fadeIn 0.3s ease-out",
  "slide-up": "slideUp 0.4s ease-out",
  "scale-in": "scaleIn 0.2s ease-out",
}
keyframes: {
  fadeIn: { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
  slideUp: { "0%": { opacity: "0", transform: "translateY(10px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
  scaleIn: { "0%": { opacity: "0", transform: "scale(0.95)" }, "100%": { opacity: "1", transform: "scale(1)" } },
}
```

## GSAP (Complex Animations)

```bash
npm install gsap
```

```typescript
import gsap from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"

gsap.registerPlugin(ScrollTrigger)

// Scroll-triggered animation
gsap.from(".feature-card", {
  y: 60,
  opacity: 0,
  duration: 0.8,
  stagger: 0.15,
  scrollTrigger: {
    trigger: ".features-section",
    start: "top 80%",
  },
})

// Timeline (sequenced animations)
const tl = gsap.timeline()
tl.from(".hero-title", { y: 30, opacity: 0, duration: 0.6 })
  .from(".hero-subtitle", { y: 20, opacity: 0, duration: 0.5 }, "-=0.3")
  .from(".hero-cta", { y: 20, opacity: 0, duration: 0.4 }, "-=0.2")
```

## Lottie (After Effects → Web)

```bash
npm install lottie-react
```

```tsx
import Lottie from "lottie-react"
import successAnimation from "./success.json"

<Lottie
  animationData={successAnimation}
  loop={false}
  style={{ width: 120, height: 120 }}
/>
```

**Use for:** success states, onboarding illustrations, loading animations, empty states.
**Source:** LottieFiles.com (free library of animations).

## Easing Reference

| Easing | CSS | Use for |
|--------|-----|---------|
| **ease-out** | `cubic-bezier(0, 0, 0.2, 1)` | Entrances (element arriving) |
| **ease-in** | `cubic-bezier(0.4, 0, 1, 1)` | Exits (element leaving) |
| **ease-in-out** | `cubic-bezier(0.4, 0, 0.2, 1)` | Ongoing motion |
| **spring** | Framer Motion `type: "spring"` | Interactive elements (buttons, drags) |
| **linear** | `linear` | Progress bars, spinners only |

### Spring Physics (Framer Motion)
```tsx
// Bouncy (playful UI)
transition={{ type: "spring", stiffness: 300, damping: 15 }}

// Snappy (professional UI)
transition={{ type: "spring", stiffness: 400, damping: 25 }}

// Smooth (subtle UI)
transition={{ type: "spring", stiffness: 200, damping: 30 }}
```

## Micro-Interactions Catalog

| Interaction | Animation | Code hint |
|-------------|-----------|-----------|
| Button click | Scale down 0.95 → back | `whileTap={{ scale: 0.95 }}` |
| Toggle switch | Slide + color change | `layout` + `animate={{ x }}` |
| Like button | Scale up + color + particles | Keyframes + `scale(1.2)` → `scale(1)` |
| Pull to refresh | Spinner appears on pull | `useMotionValue` + threshold |
| Swipe to delete | Slide left reveals delete | `drag="x"` + `dragConstraints` |
| Notification dot | Ping + pulse | `animate-ping` + `animate-pulse` |
| Error shake | Horizontal shake 3x | `x: [0, -10, 10, -10, 10, 0]` |
| Success check | Draw SVG path | `pathLength` animation |
| Skeleton → content | Fade skeleton out, content in | `AnimatePresence` + cross-fade |
| Accordion | Height auto-animate | `layout` + `overflow: hidden` |

## Accessibility

```tsx
// Always respect reduced motion
const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches

// Framer Motion: automatic
<motion.div
  initial={{ opacity: 0, y: prefersReducedMotion ? 0 : 20 }}
  animate={{ opacity: 1, y: 0 }}
/>

// Tailwind: motion-safe / motion-reduce
<div class="motion-safe:animate-slide-up motion-reduce:animate-none" />
```

## Motion Checklist

- [ ] Every state change has a transition (not just snapping)
- [ ] Entrances use ease-out, exits use ease-in
- [ ] Interactive elements have hover + tap feedback
- [ ] Loading states are animated (skeleton, spinner)
- [ ] Page transitions are smooth (not blank → content)
- [ ] Stagger used for lists (not all items at once)
- [ ] `prefers-reduced-motion` respected everywhere
- [ ] No animation blocks user from acting
- [ ] Animations are consistent (same duration/easing family)
- [ ] Performance: use `transform` and `opacity` only (GPU-accelerated)
