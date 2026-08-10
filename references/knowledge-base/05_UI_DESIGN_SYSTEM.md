# UI Design System

## Design Language: "Ventriloc"

### Color Philosophy
The design system uses a carefully curated palette:

| Token | Usage | Hex |
|-------|-------|-----|
| signal-orange | Primary accent, CTAs | #ff682c |
| sienna-bronze | Secondary accent | warm bronze |
| carbon | Dark text, headings | near-black |
| graphite | Body text | dark gray |
| slate | Muted text | medium gray |
| fog | Borders, dividers | light gray |
| mist | Subtle backgrounds | very light gray |
| chalk | Card surfaces | off-white |
| paper | Primary card surface | #ffffff |

**Reusable Insight:** Define a limited color palette with clear usage rules. Every color should have a purpose. Avoid arbitrary color values.

### Runtime Brand Theming
The accent color is not hard-coded: `brand_color` is a platform setting (admin-editable, validated server-side against a strict `#RRGGBB` regex) injected as a CSS custom property via a `<style>` tag at render time. A whitelisted public-settings endpoint exposes it (plus site title / logo text / footer text) to the login page before authentication.

**Reusable Insight:** If tenants or operators can re-brand the UI, funnel the value through one validated setting and one CSS variable. Validation at the write path is what makes `dangerouslySetInnerHTML`-style injection of the variable safe.

### Theming and Dark Mode
- Dark mode via a `dark` class on `<html>`, toggled by a client component and persisted in `localStorage` (non-sensitive UI preference only)
- A tiny inline bootstrap script applies the stored theme before first paint to avoid a flash of the wrong theme

### Typography System

#### Font Pairing
- **Space Grotesk:** Display text, KPI numbers, headings
- **Inter:** Body text, labels, descriptions

#### Type Scale
- KPI numbers: 2.25rem, tight tracking, tabular-nums
- Headings: 1.5rem - 2rem, Space Grotesk
- Body: 0.875rem - 1rem, Inter
- Labels: 0.75rem, Inter, uppercase

**Reusable Insight:** Limit yourself to two fonts. One for display, one for body. Use weight and size for hierarchy, not additional fonts.

### Card Design Pattern

#### .card-ventriloc
- White surface (#ffffff)
- 8px border radius
- Subtle ghost elevation (box-shadow)
- Consistent padding (1.5rem)
- Clean hover states

**Reusable Insight:** Cards are the fundamental layout unit. Define a single card pattern and use it everywhere. Consistency builds trust.

### Navigation Pattern

#### Pill-Shaped Navigation
- Active state: pill shape (rounded-pill, 20px radius)
- Glass-header effect: sticky top bar with backdrop blur
- Hover states: subtle background change
- Active indicator: signal-orange accent

**Reusable Insight:** Navigation should feel tactile. Pill shapes and glass effects create a modern, polished feel.

## Animation Philosophy

### Purposeful Animation
- Staggered card entrances for visual hierarchy
- Animated counters for KPI updates
- Aurora background drift for ambient depth
- Smooth transitions for state changes

### Performance Constraints
- Respects `prefers-reduced-motion`
- Uses CSS transforms (GPU-accelerated)
- Avoids layout-triggering properties
- Framer Motion for complex sequences

**Reusable Insight:** Animation should enhance, not distract. Every animation should have a purpose: guide attention, provide feedback, or create delight.

### Aurora Background
Three radial gradients with slow drift animation (28–38s alternating keyframes):
- Creates ambient depth without distraction
- Disabled for users who prefer reduced motion
- Pure CSS, no JavaScript required
- Cards are opaque surfaces on top, so the blobs never reduce content contrast

### Canvas Particle Background (login)
The login page uses a canvas-based particle animation (`particles-bg.tsx`). It is a reference implementation of disciplined animation code:
- `requestAnimationFrame` cancelled, `ResizeObserver`/`MutationObserver` disconnected, and all mouse listeners removed in the effect cleanup
- A `disposed` flag prevents frame callbacks after unmount
- `prefers-reduced-motion` checked once — the animation is skipped entirely
- Particle count is capped so click-interactions can't grow memory unboundedly

**Reusable Insight:** Background effects should be subtle enough to ignore but present enough to notice. If an effect needs JavaScript, its cleanup path is part of the design — every observer, listener, and frame handle must die with the component.

## Responsive Design

### Breakpoint Strategy
- Mobile: 1 column
- Tablet: 2 columns
- Desktop: 3 columns
- Max content width: 1200px

### Grid System
- CSS Grid for layouts
- Flexbox for component internals
- Gap-based spacing (no margins)

**Reusable Insight:** Design mobile-first, but test desktop-first. Most dashboard users are on desktop, but the layout must work on mobile.

## Component Library: shadcn/ui

### Why shadcn/ui
- Not a component library, but a copy-paste pattern
- Full control over component code
- Built on Radix UI primitives (accessible)
- Tailwind CSS for styling
- Easy to customize

**Reusable Insight:** shadcn/ui gives you the best of both worlds: accessible primitives and full customization. You own the code.

### Component Organization
```
components/
├── ui/           # shadcn primitives (button, card, dialog, etc.)
├── charts/       # Recharts wrappers
├── admin/        # Admin-specific components
├── app-shell.tsx # Main layout shell
└── lazy-chart.tsx # Lazy-loaded chart wrapper
```

**Reusable Insight:** Separate primitives from composites. Primitives (button, input) are reusable everywhere. Composites (data table, chart panel) are feature-specific.

## Accessibility Standards

### Keyboard Navigation
- All interactive elements are focusable
- Focus order matches visual order
- Visible focus indicators
- Escape key closes modals

### Screen Reader Support
- Semantic HTML elements
- ARIA labels where semantics are insufficient
- Live regions for dynamic content
- Alt text for images and icons

### Color Contrast
- All text meets WCAG AA contrast ratios
- Color is never the only indicator
- Icons accompany color-coded status

**Reusable Insight:** Accessibility is not optional. Test with keyboard only. Test with a screen reader. Test with high contrast mode.

## Beyond This Dashboard

Design-system practice this project hasn't needed yet, useful when building the next one:

- **Design tokens as a build artifact:** tools like Style Dictionary or Tokens Studio compile a single token source (JSON) into CSS variables, Tailwind config, and native platform formats. Worth it the moment two surfaces (web + email templates, web + mobile) must share a palette.
- **Semantic token layering:** split tokens into *primitive* (`orange-500`), *semantic* (`color-accent`, `surface-raised`), and *component* (`button-bg`) tiers. This dashboard jumps straight from primitives to usage; the semantic tier is what makes dark mode and re-branding mechanical instead of a find-and-replace.
- **Component states as a contract:** document all interactive states (default / hover / focus-visible / active / disabled / loading / error) per component. Radix gives the behavior; the design system should pin the visuals for each state so new components don't improvise.
- **Density modes:** analytics users often want a "compact" table density. Implement density as a token multiplier (spacing scale × 0.75) rather than per-component overrides.
- **Data-visualization color systems:** chart palettes are a separate discipline from UI palettes — categorical palettes need perceptual distance (and colorblind-safe ordering, e.g. Okabe-Ito), sequential/diverging scales need monotonic lightness. Don't reuse UI accent colors as series colors beyond the first one or two.
- **Visual regression testing:** Storybook + Chromatic (or Playwright screenshot tests) catch unintended visual drift in a copy-owned component library like shadcn/ui, where there's no upstream to protect you.
- **Motion tokens:** standardize durations/easings (`--motion-fast: 150ms`, `--ease-out-quart`) the same way as colors, and gate every animated property behind `prefers-reduced-motion` at the token level rather than per component.
