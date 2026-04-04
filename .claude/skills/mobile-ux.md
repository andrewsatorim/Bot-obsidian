---
name: mobile-ux
description: Use when designing or building mobile interfaces, handling touch interactions, implementing gestures, following iOS/Android platform patterns, or optimizing for small screens.
---

# Mobile UX

## Platform Patterns

### iOS vs Android Conventions
| Element | iOS | Android (Material) |
|---------|-----|-----|
| **Navigation** | Tab bar (bottom) | Bottom nav or drawer |
| **Back** | Edge swipe left | System back button / gesture |
| **Title** | Large title that collapses | Top app bar |
| **Primary action** | Top-right button | FAB (Floating Action Button) |
| **Alerts** | Center modal | Snackbar (bottom) |
| **Settings** | Push navigation | Full screen or dialog |
| **Segmented control** | iOS UISegmentedControl | Tabs |
| **Pull to refresh** | Native spinner | Circular progress |
| **Swipe actions** | Swipe cell for actions | Swipe cell or long press |
| **Haptics** | Light, medium, heavy | Subtle vibration |

### Universal Mobile Patterns (Use for Web)
```
Bottom tab bar — 4-5 items max
├── Home (filled icon when active)
├── Search
├── Create (+) — center, prominent
├── Activity / Notifications
└── Profile
```

## Touch Targets

### Size Requirements
| Standard | Minimum | Recommended |
|----------|---------|-------------|
| Apple HIG | 44 × 44 pt | 44 × 44 pt |
| Material Design | 48 × 48 dp | 48 × 48 dp |
| WCAG 2.5.8 | 24 × 24 px | 44 × 44 px |

```css
/* Ensure minimum touch target even for small visual elements */
.icon-button {
  width: 24px;
  height: 24px;
  /* Expand touch area without changing visual size */
  padding: 10px;
  margin: -10px;
}

/* Tailwind */
<button class="p-3 -m-1">  /* 12px padding on 24px icon = 48px touch target */
  <Icon class="h-6 w-6" />
</button>
```

### Spacing Between Targets
- Minimum 8px gap between touchable elements
- Prefer 12-16px on mobile
- No adjacent destructive actions (delete next to edit)

## Gestures

| Gesture | Use for | Implementation |
|---------|---------|----------------|
| **Tap** | Primary action | `onClick` / `onPress` |
| **Long press** | Context menu, reorder | `onContextMenu` + custom timer |
| **Swipe horizontal** | Delete, archive, actions | `drag="x"` (Framer Motion) |
| **Swipe vertical** | Pull to refresh, dismiss | Native or custom |
| **Pinch** | Zoom image/map | `touch-action: manipulation` |
| **Double tap** | Like, zoom | Custom handler with timer |
| **Edge swipe** | Back navigation (iOS) | Don't interfere with this! |

### Swipe Actions (React)
```tsx
import { motion, useMotionValue, useTransform } from "framer-motion"

function SwipeableCard({ onDelete }: { onDelete: () => void }) {
  const x = useMotionValue(0)
  const bg = useTransform(x, [-150, 0], ["#ef4444", "#ffffff"])

  return (
    <motion.div
      drag="x"
      dragConstraints={{ left: -150, right: 0 }}
      style={{ x }}
      onDragEnd={(_, info) => {
        if (info.offset.x < -100) onDelete()
      }}
    >
      <Card />
    </motion.div>
  )
}
```

## Mobile Navigation Patterns

### Bottom Sheet
```tsx
// Best for: filters, actions, secondary content
<BottomSheet
  snapPoints={[0.25, 0.5, 0.9]}  // 25%, 50%, 90% of screen
  initialSnap={0}
>
  <SheetContent />
</BottomSheet>
```

### Tab Bar (Bottom Navigation)
```tsx
// 4-5 items, icon + label, active state
<nav className="fixed bottom-0 inset-x-0 bg-white border-t safe-area-bottom">
  <div className="flex justify-around py-2">
    <TabItem icon={<Home />} label="Home" active />
    <TabItem icon={<Search />} label="Search" />
    <TabItem icon={<Plus />} label="Create" accent />
    <TabItem icon={<Bell />} label="Activity" badge={3} />
    <TabItem icon={<User />} label="Profile" />
  </div>
</nav>
```

### Safe Areas (Notch, Home Indicator)
```css
/* Respect device safe areas */
.bottom-nav {
  padding-bottom: env(safe-area-inset-bottom);
}

.top-bar {
  padding-top: env(safe-area-inset-top);
}

/* Tailwind: use safe-area plugin or custom values */
.pb-safe { padding-bottom: env(safe-area-inset-bottom); }
```

## Mobile-Specific UI Patterns

### Pull to Refresh
```tsx
function PullToRefresh({ onRefresh }: { onRefresh: () => Promise<void> }) {
  const [refreshing, setRefreshing] = useState(false)

  // Use native scroll event or touch events
  // Show spinner when pulled > 60px
  // Call onRefresh, wait for completion, hide spinner
}
```

### Infinite Scroll
```tsx
import { useInView } from "react-intersection-observer"

function InfiniteList() {
  const [ref, inView] = useInView()
  const { data, fetchNextPage } = useInfiniteQuery(...)

  useEffect(() => {
    if (inView) fetchNextPage()
  }, [inView])

  return (
    <>
      {data.pages.map(page => page.items.map(item => <Item key={item.id} />))}
      <div ref={ref} className="h-10" /> {/* trigger element */}
    </>
  )
}
```

### Sticky Header with Collapse
```tsx
function CollapsibleHeader() {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 50)
    window.addEventListener("scroll", handler, { passive: true })
    return () => window.removeEventListener("scroll", handler)
  }, [])

  return (
    <header className={cn(
      "fixed top-0 inset-x-0 z-50 transition-all",
      scrolled ? "h-12 bg-white/90 backdrop-blur shadow-sm" : "h-20 bg-transparent"
    )}>
      ...
    </header>
  )
}
```

## Mobile Form UX

### Input Types (Trigger Right Keyboard)
```html
<input type="email" />        <!-- @ and .com keys -->
<input type="tel" />           <!-- number pad -->
<input type="url" />           <!-- .com and / keys -->
<input type="number" inputMode="decimal" />  <!-- number pad with dot -->
<input type="search" />        <!-- search key on keyboard -->
<input inputMode="numeric" pattern="[0-9]*" />  <!-- PIN/code entry -->
```

### Form Rules
- One input visible above keyboard at all times
- Auto-focus first field on page load
- Auto-advance after OTP digit entry
- Show/hide password toggle
- Inline validation (don't wait for submit)
- Large submit button at bottom (thumb-reachable)
- Dismiss keyboard on tap outside input

### Thumb Zone
```
                EASY (bottom center)
               ╱                    ╲
    OK (bottom sides)          HARD (top corners)
```

- Primary actions: bottom half of screen
- Dangerous actions: top (harder to reach accidentally)
- FAB: bottom-right (right-handed) or bottom-center

## Responsive Breakpoints for Mobile

```css
/* Mobile-first approach */
.container { padding: 16px; }                    /* all screens */

@media (min-width: 640px) { /* sm — large phones */
  .container { padding: 24px; }
}

@media (min-width: 768px) { /* md — tablets */
  .container { padding: 32px; }
}
```

### Mobile-Specific Tailwind
```html
<!-- Show/hide by device -->
<div class="block sm:hidden">Mobile only</div>
<div class="hidden sm:block">Tablet+ only</div>

<!-- Stack on mobile, row on tablet+ -->
<div class="flex flex-col sm:flex-row gap-4">

<!-- Full-width button on mobile, auto on desktop -->
<button class="w-full sm:w-auto">
```

## Performance on Mobile

- **Target:** < 3s load on 3G, < 1.5s on 4G
- **Images:** use `srcset` + `sizes`, WebP/AVIF, lazy-load below fold
- **Fonts:** max 2, use `font-display: swap`
- **JS:** code-split routes, defer non-critical
- **Touch:** use `passive: true` on scroll listeners
- **Viewport:** `<meta name="viewport" content="width=device-width, initial-scale=1">`

## Mobile UX Checklist

- [ ] Touch targets ≥ 44px with 8px+ gaps
- [ ] Bottom navigation for primary actions (max 5 items)
- [ ] Safe areas respected (notch, home indicator)
- [ ] Correct input types trigger right keyboard
- [ ] Primary actions in thumb zone (bottom half)
- [ ] No hover-only interactions (everything works with tap)
- [ ] Pull to refresh on scrollable lists
- [ ] Swipe gestures don't conflict with system gestures
- [ ] Text readable without zooming (≥ 16px body)
- [ ] No horizontal scrolling on any page
- [ ] Loads < 3s on 3G connection
- [ ] Works offline or shows helpful offline state
- [ ] Back gesture / button works predictably
- [ ] Modals dismissible by swipe down or tap outside
