# Zarly BigFood — Design System

## Design Philosophy

Product register (design serves the product). The system has one coherent identity across customer-facing pages and internal admin tools. The reference aesthetic is the **landing page**: a warm, food-brand feel grounded in a dark hero, saturated amber accents, and light cream content panels — not generic SaaS blue/grey.

Anti-references: cold neutral greys, SaaS-cream `#f8fafc`, flat white `#fff`, hero-metric templates (big number + gradient accent), glassmorphism.

---

## Color System

All colors use **OKLCH**. Never use `#000` or `#fff` — tint every neutral toward the brand hue (hue ~52–66).

### Brand Palette

| Role | Value | Usage |
|---|---|---|
| Brand orange | `#ff9933` | Primary CTAs, prices, metric values, active accents |
| Brand orange dark | `oklch(70% 0.2 54)` | Hover state for orange elements |
| Dark hero panel | `oklch(14% 0.045 52)` | Hero sections, metric strip, dark CTAs, dark summary sidebar |
| Dark panel border | `oklch(28% 0.04 52)` | Dividers inside dark panels |
| Dark panel muted text | `oklch(58% 0.02 54)` | Labels on dark backgrounds |
| Dark panel body text | `oklch(68% 0.02 54)` | Paragraph text on dark backgrounds |
| Dark panel heading | `oklch(97% 0.012 58)` | Headings on dark backgrounds |
| Amber feature strip | `oklch(75% 0.195 57)` | Bold accent strips (feature row on landing page) |
| Amber strip divider | `oklch(65% 0.22 57 / 0.3)` | Dividers inside the amber strip |

### Light / Content Palette

| Role | Value | Usage |
|---|---|---|
| Sellers panel bg | `oklch(97% 0.016 62)` | Section panels, admin dash panels |
| Sellers panel border | `oklch(91% 0.03 62)` | Border on section panels |
| Product card bg | `oklch(99.5% 0.006 60)` | Product cards, table rows, light cards |
| Product card border | `oklch(90% 0.02 62)` | Border on product cards |
| Warm cream panel | `oklch(96% 0.028 66)` | Hero filter strips, category panels |
| Warm cream border | `oklch(88% 0.05 64)` | Border on warm cream panels |
| Warm near-white | `oklch(98.5% 0.018 65)` | Cart/order item cards, inner panels |
| Warm near-white border | `oklch(88% 0.045 64)` | Border on inner panels |
| Table header bg | `oklch(93% 0.022 62)` | Table `<thead>` rows |
| Table separator | `oklch(91% 0.025 62)` | Table row `border-bottom` |
| Table hover | `oklch(97% 0.022 62)` | Table row hover |
| High-value row | `oklch(97% 0.03 66)` | Flagged table rows |

### Text Colors

| Role | Value |
|---|---|
| Primary heading | `oklch(16% 0.04 52)` |
| Secondary heading / strong | `oklch(18% 0.04 52)` |
| Body text | `oklch(22% 0.04 52)` |
| Secondary text | `oklch(28% 0.04 52)` |
| Muted text | `oklch(42% 0.06 52)` |
| Very muted / labels | `oklch(48% 0.06 54)` |
| Price / category tag | `oklch(58% 0.2 54)` → same as brand on light bg |
| Category eyebrow | `oklch(62% 0.08 58)` |

---

## Typography

```css
/* Load order */
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&display=swap');
/* Inter is loaded globally via style.css */
```

| Element | Font | Size | Weight | Notes |
|---|---|---|---|---|
| Page heroes, section titles | DM Serif Display | `clamp(1.7rem, 3vw, 2.8rem)` | 400 | `letter-spacing: -0.02em` |
| Panel headings | DM Serif Display | `1.15rem–1.6rem` | 400 | `letter-spacing: -0.015em` |
| Card names, panel titles | Inter | `0.82rem–0.92rem` | 700–800 | |
| Table headers | Inter | `0.65rem` | 700 | Uppercase, `letter-spacing: .07em` |
| Labels / eyebrows | Inter | `0.68rem–0.72rem` | 700 | Uppercase, `letter-spacing: .06–.08em` |
| Body / sub-text | Inter | `0.82rem–0.88rem` | 400–500 | |
| Metric values | Inter | `1.6rem–1.8rem` | 900 | Color: `#ff9933` on dark panels |

Italic emphasis in DM Serif Display: use `<em>` with `color: #ff9933` for brand-colored italic (landing page hero pattern).

---

## Components

### Dark Hero Panel

Used for: landing hero, metric strips on admin dashboard, order summary sidebar.

```css
background: oklch(14% 0.045 52);
border-radius: 1.25rem;   /* 1rem for smaller panels */
```

Text inside: headings `oklch(97% 0.012 58)`, body `oklch(68% 0.02 54)`, labels `oklch(58% 0.02 54)`, accents `#ff9933`.
Dividers: `oklch(28% 0.04 52)`.

---

### Light Content Panel (Section / Admin Panel)

Used for: "Best Sellers" section, admin dash panels, support/orders panels.

```css
background: oklch(97% 0.016 62);
border-radius: 1rem–1.1rem;
border: 1px solid oklch(91% 0.03 62);
box-shadow: 0 4px 24px oklch(70% 0.15 57 / 0.08);
```

Panel header border-bottom: `oklch(89% 0.03 62)`.

---

### Product / Inner Card

Used for: product cards, table rows, individual accepted-order items.

```css
background: oklch(99.5% 0.006 60);
border-radius: 0.875rem;
border: 1px solid oklch(90% 0.02 62);
```

Hover lift:
```css
box-shadow: 0 8px 28px oklch(70% 0.15 57 / 0.18);
transform: translateY(-2px);
```

---

### Stacked Card Shadow (checkout / cart pages only)

The dark card-behind-card treatment. Use only on checkout and cart — not system-wide.

```css
box-shadow: 6px 6px 0 0 #170400, 0 1px 6px oklch(9% 0.04 32 / 0.05);
/* No border — the shadow is the frame */
```

---

### Warm Cream Filter / Browse Panel

Used for: menu hero, filter controls, category pill areas.

```css
background: oklch(96% 0.028 66);   /* or oklch(96% 0.03 68) */
border-radius: 1.1rem–1.25rem;
border: 1px solid oklch(88% 0.05 64);
```

---

### Orange Badge (Landing Page Style)

Used for: "Fresh today" badge on landing, "New" status pill on admin.

```css
background: oklch(70% 0.18 55 / 0.15);
border: 1px solid oklch(70% 0.18 55 / 0.28);
color: #ff9933;
font-size: 0.7rem; font-weight: 700;
letter-spacing: 0.08em; text-transform: uppercase;
padding: 0.28rem 0.7rem;
border-radius: 999px;
```

With a dot prefix:
```css
.lp-badge::before {
  content: ''; display: block;
  width: 5px; height: 5px;
  border-radius: 50%; background: #ff9933;
}
```

---

### Buttons

**Primary (orange):**
```css
background: #ff9933;
color: oklch(13% 0.04 52);
font-weight: 700; font-size: 0.84rem;
padding: 0.58rem 1.35rem;
border-radius: 8px;
transition: background 0.15s, transform 0.1s;
```
Hover: `background: oklch(70% 0.2 54); transform: translateY(-1px);`

**Ghost (on dark bg):**
```css
color: oklch(72% 0.015 54);
font-size: 0.84rem; font-weight: 600;
```
Hover: `color: oklch(95% 0.012 58);`

---

### Quantity Stepper

Used in cart and product interactions.

```css
/* Track */
background: oklch(93% 0.025 64);
border-radius: 999px; padding: 0.2rem 0.3rem;

/* Button */
width: 28px; height: 28px; border-radius: 50%;
background: oklch(98.5% 0.018 65);
border: 1px solid oklch(84% 0.045 64);
```
Hover: `background: #ff9933; border-color: #ff9933; color: oklch(13% 0.04 52);`

---

### Cart FAB (Floating Action Button)

Fixed bottom-right. Hover reveals a dark tooltip panel (count + total).

```css
/* FAB */
position: fixed; bottom: 1.75rem; right: 1.5rem;

/* Tooltip */
background: oklch(14% 0.045 52);
border: 1px solid oklch(28% 0.04 52);
border-radius: 10px;
/* Total: color: #ff9933; font-weight: 800; */
/* Count: color: oklch(62% 0.02 54); */
```

---

### Dark Hover Tooltip (Navbar Cart)

Same dark panel, appears below the navbar icon.

```css
background: oklch(14% 0.045 52);
border: 1px solid oklch(28% 0.04 52);
border-radius: 10px;
z-index: 2000;
```

---

### Loyalty Strip

Horizontal strip (not a card). Replaces hero-metric loyalty panels.

```css
/* Container */
background: oklch(14% 0.045 52);
border-radius: 0.875rem;
padding: 0.875rem 1.25rem;
display: flex; align-items: center; gap: 1.25rem;

/* Progress bar track */
background: oklch(24% 0.04 52);
border-radius: 999px; height: 5px;

/* Dividers */
background: oklch(28% 0.04 52);
width: 1px; height: 2.5rem;
```

Tier colors: Bronze `#cd7f32`, Silver `oklch(62% 0.005 58)`, Gold `#f4b400`, Platinum `#a78bfa`.

---

## Page-Level Patterns

### Customer Menu (Product List)
- `.menu-hero` — warm cream `oklch(96% 0.028 66)` with DM Serif Display title + inline filters
- `.menu-browse-panel` — warm cream `oklch(96% 0.03 68)` wrapping category pills + product grid
- Category pills — near-white `oklch(98.5% 0.018 65)` with amber border, active pill uses dark `oklch(14% 0.045 52)` + orange text

### Cart Page
- Header — warm cream panel with DM Serif "Your order"
- Items wrapped in `.crt-card`: near-white `oklch(99.5% 0.006 60)`, `2px solid #170400` border, `6px 6px 0 0 #170400` shadow
- Total row inside the same card

### Checkout Page
- Section cards (`.co-card`) and summary card: near-white `oklch(99.5% 0.006 60)`, `2px solid #170400` border, `6px 6px 0 0 #170400` shadow
- Leaflet map: `position: relative; z-index: 0` to contain internal layer z-indices below the navbar

### Customer Orders
- Loyalty strip at top (dark panel, horizontal)
- Two separate subsections: "Awaiting Payment" (amber header) and "In Progress" (blue header)
- Order cards: warm near-white `oklch(98.5% 0.018 65)`

### Sales Admin Dashboard
- Metric strip: dark hero panel `oklch(14% 0.045 52)`, metric values in `#ff9933`
- Data panels: light section panel `oklch(97% 0.016 62)`
- Table rows: near-white `oklch(99.5% 0.006 60)`
- "New" pill: orange badge style; "High value" pill: dark panel style

---

## Banned Patterns

- `border-left` or `border-right` > 1px as colored accent (side-stripe borders)
- `background-clip: text` with gradient (gradient text)
- Hero-metric template: big number + small muted label + gradient/colored accent background
- Pure `#000` or `#fff` — always tint
- Identical card grids everywhere — vary structure
- Bootstrap `col-*` inside CSS Grid parents (they don't span full width)
- Django `{% with var="{% if ... %}" %}` — template tags cannot be nested inside `{% with %}` string values

---

## Context Processors

`customers.context_processors.cart_context` — registered in settings, provides `cart_count` and `cart_total` to every template. Used by the navbar cart tooltip in `base.html`.

`admins.context_processors.unread_notifications` — provides `unread_notification_count` globally.
