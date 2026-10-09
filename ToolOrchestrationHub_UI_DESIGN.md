---
version: alpha
name: MongoDB-design-analysis
description: MongoDB carries a strong dual-mode visual identity — dark deep-teal hero bands with bright MongoDB green ({colors.brand-green}) CTAs paired with stark white documentation surfaces. The signature green pill button is unmistakable across product, pricing, learning, and AI use-case surfaces. The system uses Euclid Circular A as its display face, anchors a 3-tier pricing comparison (Free / Flex / Dedicated), and presents extensive course catalogs in card grids with colored category tags. Coverage spans homepage, Atlas product page, Community Edition, MongoDB University, AI use cases, and pricing.

colors:
  primary: "#00ed64"
  primary-deep: "#00b545"
  primary-pressed: "#008c34"
  on-primary: "#001e2b"
  brand-green: "#00ed64"
  brand-green-dark: "#00684a"
  brand-green-mid: "#00a35c"
  brand-green-soft: "#c3f0d2"
  brand-teal-deep: "#001e2b"
  brand-teal: "#003d4f"
  brand-teal-mid: "#00684a"
  accent-purple: "#7b3ff2"
  accent-orange: "#fa6e39"
  accent-pink: "#f06bb8"
  accent-blue: "#3d4f9f"
  semantic-warning-bg: "#fff8e0"
  semantic-warning-text: "#946f3f"
  canvas: "#ffffff"
  canvas-dark: "#001e2b"
  surface: "#f9fbfa"
  surface-soft: "#f4f7f6"
  surface-feature: "#e3fcef"
  hairline: "#e1e5e8"
  hairline-soft: "#eceff1"
  hairline-strong: "#c1ccd6"
  hairline-dark: "#1c2d38"
  ink: "#001e2b"
  charcoal: "#1c2d38"
  slate: "#3d4f5b"
  steel: "#5c6c7a"
  stone: "#7c8c9a"
  muted: "#a8b3bc"
  on-dark: "#ffffff"
  on-dark-muted: "#a8b3bc"

typography:
  hero-display:
    fontFamily: Euclid Circular A
    fontSize: 72px
    fontWeight: 500
    lineHeight: 1.10
    letterSpacing: -1.5px
  display-lg:
    fontFamily: Euclid Circular A
    fontSize: 56px
    fontWeight: 500
    lineHeight: 1.15
    letterSpacing: -1px
  heading-1:
    fontFamily: Euclid Circular A
    fontSize: 48px
    fontWeight: 500
    lineHeight: 1.20
    letterSpacing: -0.5px
  heading-2:
    fontFamily: Euclid Circular A
    fontSize: 36px
    fontWeight: 500
    lineHeight: 1.25
    letterSpacing: -0.5px
  heading-3:
    fontFamily: Euclid Circular A
    fontSize: 28px
    fontWeight: 500
    lineHeight: 1.30
  heading-4:
    fontFamily: Euclid Circular A
    fontSize: 22px
    fontWeight: 500
    lineHeight: 1.35
  heading-5:
    fontFamily: Euclid Circular A
    fontSize: 18px
    fontWeight: 600
    lineHeight: 1.40
  subtitle:
    fontFamily: Euclid Circular A
    fontSize: 18px
    fontWeight: 400
    lineHeight: 1.50
  body-md:
    fontFamily: Euclid Circular A
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.55
  body-md-medium:
    fontFamily: Euclid Circular A
    fontSize: 16px
    fontWeight: 500
    lineHeight: 1.55
  body-sm:
    fontFamily: Euclid Circular A
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.50
  body-sm-medium:
    fontFamily: Euclid Circular A
    fontSize: 14px
    fontWeight: 500
    lineHeight: 1.50
  caption:
    fontFamily: Euclid Circular A
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.40
  caption-bold:
    fontFamily: Euclid Circular A
    fontSize: 13px
    fontWeight: 600
    lineHeight: 1.40
  micro:
    fontFamily: Euclid Circular A
    fontSize: 12px
    fontWeight: 500
    lineHeight: 1.40
  micro-uppercase:
    fontFamily: Euclid Circular A
    fontSize: 11px
    fontWeight: 600
    lineHeight: 1.40
    letterSpacing: 1px
  button-md:
    fontFamily: Euclid Circular A
    fontSize: 14px
    fontWeight: 600
    lineHeight: 1.30
  code-md:
    fontFamily: Source Code Pro
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.55

rounded:
  xs: 4px
  sm: 6px
  md: 8px
  lg: 12px
  xl: 16px
  xxl: 24px
  full: 9999px

spacing:
  xxs: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 20px
  xl: 24px
  xxl: 32px
  xxxl: 40px
  section-sm: 48px
  section: 64px
  section-lg: 96px
  hero: 120px

components:
  button-primary:
    backgroundColor: "{colors.brand-green}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button-md}"
    rounded: "{rounded.full}"
    padding: "10px 22px"
  button-primary-pressed:
    backgroundColor: "{colors.primary-pressed}"
    textColor: "{colors.on-primary}"
  button-primary-disabled:
    backgroundColor: "{colors.hairline}"
    textColor: "{colors.muted}"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.button-md}"
    rounded: "{rounded.full}"
    padding: "10px 22px"
    border: "1px solid {colors.hairline-strong}"
  button-on-dark:
    backgroundColor: "{colors.brand-green}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button-md}"
    rounded: "{rounded.full}"
    padding: "10px 22px"
  button-secondary-on-dark:
    backgroundColor: "transparent"
    textColor: "{colors.on-dark}"
    typography: "{typography.button-md}"
    rounded: "{rounded.full}"
    padding: "10px 22px"
    border: "1px solid {colors.hairline-dark}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.button-md}"
    rounded: "{rounded.md}"
    padding: "8px 12px"
  button-link:
    backgroundColor: "transparent"
    textColor: "{colors.brand-green-dark}"
    typography: "{typography.body-sm-medium}"
    padding: "0"
  card-base:
    backgroundColor: "{colors.canvas}"
    rounded: "{rounded.lg}"
    padding: "{spacing.xl}"
    border: "1px solid {colors.hairline}"
  card-feature:
    backgroundColor: "{colors.canvas}"
    rounded: "{rounded.lg}"
    padding: "{spacing.xxl}"
    border: "1px solid {colors.hairline}"
  card-product-deploy:
    backgroundColor: "{colors.canvas}"
    rounded: "{rounded.lg}"
    padding: "{spacing.xxl}"
    border: "1px solid {colors.hairline}"
  card-feature-dark:
    backgroundColor: "{colors.brand-teal-deep}"
    textColor: "{colors.on-dark}"
    rounded: "{rounded.lg}"
    padding: "{spacing.xxl}"
  card-course:
    backgroundColor: "{colors.canvas}"
    rounded: "{rounded.lg}"
    padding: "{spacing.xl}"
    border: "1px solid {colors.hairline}"
  card-cert:
    backgroundColor: "{colors.canvas}"
    rounded: "{rounded.lg}"
    padding: "{spacing.xl}"
    border: "1px solid {colors.hairline}"
  pricing-card:
    backgroundColor: "{colors.canvas}"
    rounded: "{rounded.lg}"
    padding: "{spacing.xxl}"
    border: "1px solid {colors.hairline}"
  pricing-card-featured:
    backgroundColor: "{colors.surface-feature}"
    rounded: "{rounded.lg}"
    padding: "{spacing.xxl}"
    border: "2px solid {colors.brand-green}"
  text-input:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body-md}"
    rounded: "{rounded.md}"
    padding: "{spacing.sm} {spacing.md}"
    border: "1px solid {colors.hairline-strong}"
    height: 44px
  text-input-focused:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    border: "2px solid {colors.brand-green-dark}"
  search-pill:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.steel}"
    typography: "{typography.body-md}"
    rounded: "{rounded.md}"
    padding: "{spacing.sm} {spacing.md}"
    height: 44px
    border: "1px solid {colors.hairline-strong}"
  search-pill-large:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.steel}"
    typography: "{typography.body-md}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
    height: 56px
    border: "1px solid {colors.hairline-strong}"
  pill-tab:
    backgroundColor: "transparent"
    textColor: "{colors.steel}"
    typography: "{typography.body-sm-medium}"
    rounded: "{rounded.full}"
    padding: "{spacing.xs} {spacing.md}"
    border: "1px solid {colors.hairline}"
  pill-tab-active:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-dark}"
    rounded: "{rounded.full}"
    border: "1px solid {colors.ink}"
  segmented-tab:
    backgroundColor: "transparent"
    textColor: "{colors.steel}"
    typography: "{typography.body-sm-medium}"
    padding: "{spacing.sm} {spacing.md}"
    border: "0 0 2px transparent solid"
  segmented-tab-active:
    backgroundColor: "transparent"
    textColor: "{colors.brand-green-dark}"
    typography: "{typography.body-sm-medium}"
    border: "0 0 2px {colors.brand-green-dark} solid"
  badge-green:
    backgroundColor: "{colors.brand-green}"
    textColor: "{colors.on-primary}"
    typography: "{typography.caption-bold}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  badge-green-soft:
    backgroundColor: "{colors.brand-green-soft}"
    textColor: "{colors.brand-green-dark}"
    typography: "{typography.caption-bold}"
    rounded: "{rounded.full}"
    padding: "4px 10px"
  badge-purple:
    backgroundColor: "{colors.accent-purple}"
    textColor: "{colors.on-dark}"
    typography: "{typography.caption-bold}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  badge-orange:
    backgroundColor: "{colors.accent-orange}"
    textColor: "{colors.on-dark}"
    typography: "{typography.caption-bold}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  badge-popular:
    backgroundColor: "{colors.brand-teal-deep}"
    textColor: "{colors.brand-green}"
    typography: "{typography.caption-bold}"
    rounded: "{rounded.full}"
    padding: "4px 10px"
  promo-banner:
    backgroundColor: "{colors.brand-teal-deep}"
    textColor: "{colors.on-dark}"
    typography: "{typography.body-sm-medium}"
    padding: "{spacing.sm} {spacing.md}"
  hero-band-dark:
    backgroundColor: "{colors.brand-teal-deep}"
    textColor: "{colors.on-dark}"
    rounded: "0"
    padding: "{spacing.hero}"
  hero-platform-card:
    backgroundColor: "{colors.brand-teal-mid}"
    textColor: "{colors.on-dark}"
    rounded: "{rounded.xl}"
    padding: "{spacing.xxl}"
  cta-banner-dark:
    backgroundColor: "{colors.brand-teal-deep}"
    textColor: "{colors.on-dark}"
    rounded: "{rounded.lg}"
    padding: "{spacing.section}"
  code-block:
    backgroundColor: "{colors.canvas-dark}"
    textColor: "{colors.on-dark}"
    typography: "{typography.code-md}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  code-mockup-card:
    backgroundColor: "{colors.canvas-dark}"
    textColor: "{colors.on-dark}"
    rounded: "{rounded.lg}"
    padding: "{spacing.lg}"
  comparison-table:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.md}"
    border: "1px solid {colors.hairline}"
  comparison-row:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    padding: "{spacing.md} {spacing.lg}"
    border: "0 0 1px {colors.hairline-soft} solid"
  service-tile:
    backgroundColor: "{colors.canvas}"
    rounded: "{rounded.lg}"
    padding: "{spacing.xl}"
    border: "1px solid {colors.hairline}"
  why-card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "{spacing.xl}"
  customer-testimonial-card:
    backgroundColor: "{colors.canvas}"
    rounded: "{rounded.lg}"
    padding: "{spacing.xxl}"
    border: "1px solid {colors.hairline}"
  logo-wall-item:
    backgroundColor: "transparent"
    textColor: "{colors.steel}"
    typography: "{typography.body-md-medium}"
    padding: "{spacing.lg}"
  faq-accordion-item:
    backgroundColor: "{colors.canvas}"
    rounded: "{rounded.md}"
    padding: "{spacing.xl}"
    border: "0 0 1px {colors.hairline} solid"
  footer-region:
    backgroundColor: "{colors.brand-teal-deep}"
    textColor: "{colors.on-dark}"
    typography: "{typography.body-sm}"
    padding: "{spacing.section} {spacing.xxl}"
  footer-link:
    backgroundColor: "transparent"
    textColor: "{colors.on-dark-muted}"
    typography: "{typography.body-sm}"
    padding: "{spacing.xxs} 0"
---

## Overview

MongoDB carries a strong dual-mode visual identity — dark deep-teal hero bands with the unmistakable bright MongoDB green ({colors.brand-green}) CTA pill paired with stark white documentation and pricing surfaces. The homepage opens with "One data platform. Unlimited AI potential." headline over a deep navy hero, the green pill sitting at the visual center as the primary CTA. Lower on the page, embedded code mockup cards (terminal-aesthetic) sit on the dark hero band, breaking out into white feature cards below. The pricing page renders a 3-tier comparison (Free / Flex / Dedicated) with a featured tier highlighted in soft mint background and bright green border. The MongoDB University page presents a course catalog grid where each tile carries a colored category tag (orange, purple, green, teal) — these are MongoDB's category-encoding accent colors and are the only place outside the brand green where saturated color appears.

The system uses Euclid Circular A as its display face. The face is contemporary geometric — confident but not overly playful — and pairs naturally with both the developer-tool aesthetic of the database product and the educational positioning of the learning surfaces. Cards use `{rounded.lg}` (12px) corners; buttons use `{rounded.full}` pills universally. The brand-teal palette ({colors.brand-teal-deep}) anchors hero bands, footer, code mockups, and the dark CTA banners.

**Key Characteristics:**
- Deep navy/teal hero bands ({colors.brand-teal-deep}) with bright MongoDB green ({colors.brand-green}) CTA pills
- Stark white pricing/documentation surfaces with colored category tags for course tiles (purple, orange, green, teal)
- Euclid Circular A across every UI surface
- Pill-shaped buttons ({rounded.full}) and 12px-rounded cards
- 3-tier pricing comparison (Free / Flex / Dedicated) with featured-mint highlight tier
- Code mockup cards with terminal-aesthetic dark canvas

## Colors

> Source pages: mongodb.com/ (homepage), /products/platform/atlas-database (Atlas product), /products/self-managed/community-edition, learn.mongodb.com/ (MongoDB University), /solutions/use-cases/artificial-intelligence (AI), /pricing (3-tier comparison). Token coverage was identical across all six pages.

### Brand & Accent
- **MongoDB Green** ({colors.brand-green}): The brand's most recognizable signal — bright pill-CTA color
- **Green Dark** ({colors.brand-green-dark}): Inline link color, secondary green
- **Green Mid** ({colors.brand-green-mid}): Mid-spectrum green for atmospheric tints
- **Green Soft** ({colors.brand-green-soft}): Pale-mint background tint for success badges and featured pricing tier
- **Brand Teal Deep** ({colors.brand-teal-deep}): Deep navy-teal for hero bands, footer
- **Brand Teal** ({colors.brand-teal}): Mid-spectrum teal
- **Brand Teal Mid** ({colors.brand-teal-mid}): Lighter teal for hero platform cards

### Category Accent (Course Tags)
- **Accent Purple** ({colors.accent-purple}): Course tag for "Database & Security"
- **Accent Orange** ({colors.accent-orange}): Course tag for "Search"
- **Accent Pink** ({colors.accent-pink}): Course tag variant
- **Accent Blue** ({colors.accent-blue}): Course tag variant for atlas/cloud topics

### Surface
- **Canvas White** ({colors.canvas}): Page background and primary card surface
- **Canvas Dark** ({colors.canvas-dark}): Code-block backgrounds, dark mockup canvas
- **Surface** ({colors.surface}): Subtle section backgrounds, search-pill rest
- **Surface Soft** ({colors.surface-soft}): Quieter section divisions
- **Surface Feature** ({colors.surface-feature}): Pale mint background for featured pricing tier
- **Hairline** ({colors.hairline}): 1px borders and primary dividers
- **Hairline Soft** ({colors.hairline-soft}): Quieter dividers
- **Hairline Strong** ({colors.hairline-strong}): Stronger 1px border for inputs
- **Hairline Dark** ({colors.hairline-dark}): Border on dark surfaces

### Text
- **Ink** ({colors.ink}): Primary headlines and body text (deep navy-teal)
- **Charcoal** ({colors.charcoal}): Body emphasis
- **Slate** ({colors.slate}): Secondary text
- **Steel** ({colors.steel}): Tertiary text, captions
- **Stone** ({colors.stone}): Muted labels
- **Muted** ({colors.muted}): Disabled, placeholders
- **On Dark** ({colors.on-dark}): White text on dark surfaces
- **On Dark Muted** ({colors.on-dark-muted}): Reduced-opacity white

### Semantic
- **Warning Background** ({colors.semantic-warning-bg}): Pale yellow callout bg
- **Warning Text** ({colors.semantic-warning-text}): Warning state copy color

## Typography

### Font Family
**Euclid Circular A** (primary): MongoDB's geometric sans-serif. Fallbacks: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif.
**Source Code Pro** (code): Monospace for code mockups. Fallbacks: 'SF Mono', Menlo, Consolas, monospace.

### Hierarchy

| Token | Size | Weight | Line Height | Letter Spacing | Use |
|---|---|---|---|---|---|
| `{typography.hero-display}` | 72px | 500 | 1.10 | -1.5px | Hero ("One data platform") |
| `{typography.display-lg}` | 56px | 500 | 1.15 | -1px | Major section openers |
| `{typography.heading-1}` | 48px | 500 | 1.20 | -0.5px | Page-level headlines |
| `{typography.heading-2}` | 36px | 500 | 1.25 | -0.5px | Subsection headlines |
| `{typography.heading-3}` | 28px | 500 | 1.30 | 0 | Card titles |
| `{typography.heading-4}` | 22px | 500 | 1.35 | 0 | Feature tile titles |
| `{typography.heading-5}` | 18px | 600 | 1.40 | 0 | Smaller card titles, FAQ questions |
| `{typography.subtitle}` | 18px | 400 | 1.50 | 0 | Hero subtitle, lead body |
| `{typography.body-md}` | 16px | 400 | 1.55 | 0 | Primary body text |
| `{typography.body-sm}` | 14px | 400 | 1.50 | 0 | Secondary body, table cells |
| `{typography.body-sm-medium}` | 14px | 500 | 1.50 | 0 | Active sidebar, button labels |
| `{typography.caption-bold}` | 13px | 600 | 1.40 | 0 | Badge labels |
| `{typography.micro-uppercase}` | 11px | 600 | 1.40 | 1px | Section eyebrows, course category tags |
| `{typography.button-md}` | 14px | 600 | 1.30 | 0 | Pill button labels |
| `{typography.code-md}` | 14px | 400 | 1.55 | 0 | Code mockups |

### Principles
- Tight hero leading (1.10) on 72px display
- Negative letter-spacing on display sizes (-1.5px to -0.5px)
- 600 weight reserved for buttons and small emphasis (FAQ headings, badges)
- Generous body leading (1.55) for technical documentation readability

## Layout

### Spacing System
- **Base unit**: 4px (8px primary increment)
- **Tokens**: `{spacing.xxs}` (4px) through `{spacing.hero}` (120px)
- **Section rhythm**: Marketing pages use `{spacing.section-lg}` (96px); pricing tightens to `{spacing.section}` (64px)

### Grid & Container
- 1280px max-width with 32px gutters
- Pricing: 3-tier card row, dense feature comparison table below
- Learn catalog: 3-up course tile grid, 4-up certification grid
- AI use cases: 2-column hero with atmospheric illustration

### Whitespace Philosophy
Marketing surfaces give content generous breathing room — `{spacing.hero}` (120px) hero padding for deep teal bands. Pricing/learn surfaces tighten dramatically.

## Elevation & Depth

| Level | Treatment | Use |
|---|---|---|
| 0 (flat) | No shadow; `{colors.hairline}` border | Default cards, table rows |
| 1 (subtle) | `rgba(0, 30, 43, 0.04) 0px 1px 2px 0px` | Hover-elevated tiles |
| 2 (card) | `rgba(0, 30, 43, 0.08) 0px 4px 12px 0px` | Feature cards |
| 3 (mockup) | `rgba(0, 30, 43, 0.12) 0px 12px 24px -4px` | Code mockup over hero |
| 4 (modal) | `rgba(0, 30, 43, 0.16) 0px 16px 48px -8px` | Modals, dropdowns |

### Decorative Depth
- Dark teal hero bands carry atmospheric gradient depth
- Code mockup cards on hero use canvas-dark surface with terminal aesthetic
- Pale-mint pricing-feature tier uses brand-tinted shadow

## Shapes

### Border Radius Scale

| Token | Value | Use |
|---|---|---|
| `{rounded.xs}` | 4px | Course category tags |
| `{rounded.sm}` | 6px | Type badges, code chips |
| `{rounded.md}` | 8px | Inputs, search-pill, code blocks |
| `{rounded.lg}` | 12px | Cards, pricing tiers, course tiles |
| `{rounded.xl}` | 16px | Larger feature panels |
| `{rounded.xxl}` | 24px | Featured product showcases |
| `{rounded.full}` | 9999px | All buttons, status badges |

### Photography Geometry
- Hero illustrations sit on full-bleed dark backgrounds
- Course tile thumbnails use `{rounded.lg}` corners
- Customer logos wall: wordmarks at consistent 60–80px height

## Components

> Per the no-hover policy, hover states are NOT documented. Default and pressed/active states only.

### Buttons

**`button-primary`** — Bright MongoDB green pill primary CTA, the dominant action.
- Background `{colors.brand-green}`, text `{colors.on-primary}` (deep navy), typography `{typography.button-md}`, padding `10px 22px`, rounded `{rounded.full}`.
- Pressed state `button-primary-pressed` deepens to `{colors.primary-pressed}`.
- Disabled state `button-primary-disabled` uses `{colors.hairline}` background.

**`button-secondary`** — Outlined pill for secondary actions.
- Background transparent, text `{colors.ink}`, border `1px solid {colors.hairline-strong}`, typography `{typography.button-md}`, padding `10px 22px`, rounded `{rounded.full}`.

**`button-on-dark`** — Bright green pill on dark hero bands.
- Background `{colors.brand-green}`, text `{colors.on-primary}`, typography `{typography.button-md}`, padding `10px 22px`, rounded `{rounded.full}`.

**`button-secondary-on-dark`** — Outlined pill on dark backgrounds.
- Background transparent, text `{colors.on-dark}`, border `1px solid {colors.hairline-dark}`, typography `{typography.button-md}`, padding `10px 22px`, rounded `{rounded.full}`.

**`button-ghost`** — Quieter rectangular ghost button.
- Background transparent, text `{colors.ink}`, typography `{typography.button-md}`, padding `8px 12px`, rounded `{rounded.md}`.

**`button-link`** — Inline green text link.
- Background transparent, text `{colors.brand-green-dark}`, typography `{typography.body-sm-medium}`, padding `0`.

### Cards & Containers

**`card-base`** — Standard content card.
- Background `{colors.canvas}`, rounded `{rounded.lg}`, padding `{spacing.xl}`, border `1px solid {colors.hairline}`.

**`card-feature`** — Feature card with larger padding.
- Background `{colors.canvas}`, rounded `{rounded.lg}`, padding `{spacing.xxl}`, border `1px solid {colors.hairline}`.

**`card-product-deploy`** — Product deployment card ("MongoDB Atlas / Community").
- Background `{colors.canvas}`, rounded `{rounded.lg}`, padding `{spacing.xxl}`, border `1px solid {colors.hairline}`.

**`card-feature-dark`** — Dark teal feature card on hero band.
- Background `{colors.brand-teal-deep}`, text `{colors.on-dark}`, rounded `{rounded.lg}`, padding `{spacing.xxl}`.

**`card-course`** — MongoDB University course tile.
- Background `{colors.canvas}`, rounded `{rounded.lg}`, padding `{spacing.xl}`, border `1px solid {colors.hairline}`.
- Top: colored category tag. Below: title `{typography.heading-5}`, description `{typography.body-sm}`, "Get Started →" link.

**`card-cert`** — Certification card.
- Background `{colors.canvas}`, rounded `{rounded.lg}`, padding `{spacing.xl}`, border `1px solid {colors.hairline}`.

**`pricing-card`** — Standard pricing tier card.
- Background `{colors.canvas}`, rounded `{rounded.lg}`, padding `{spacing.xxl}`, border `1px solid {colors.hairline}`.

**`pricing-card-featured`** — Featured pricing tier (Flex tier, mint background + green border).
- Background `{colors.surface-feature}`, rounded `{rounded.lg}`, padding `{spacing.xxl}`, border `2px solid {colors.brand-green}`.

### Inputs & Forms

**`text-input`** — Standard text field.
- Background `{colors.canvas}`, text `{colors.ink}`, border `1px solid {colors.hairline-strong}`, rounded `{rounded.md}`, padding `{spacing.sm} {spacing.md}`, height 44px.

**`text-input-focused`** — Activated state.
- Border switches to `2px solid {colors.brand-green-dark}`.

**`search-pill`** — Standard 44px search bar.
- Background `{colors.surface}`, text `{colors.steel}`, typography `{typography.body-md}`, rounded `{rounded.md}`, height 44px, border `1px solid {colors.hairline-strong}`.

**`search-pill-large`** — Large 56px search bar (top of MongoDB University catalog).
- Background `{colors.canvas}`, text `{colors.steel}`, typography `{typography.body-md}`, rounded `{rounded.md}`, height 56px, border `1px solid {colors.hairline-strong}`.

### Tabs

**`pill-tab`** + **`pill-tab-active`** — Pill-style tab nav (top of pricing: "MongoDB Atlas / Enterprise Advanced").
- Inactive: text `{colors.steel}`, border `1px solid {colors.hairline}`, padding `{spacing.xs} {spacing.md}`, rounded `{rounded.full}`.
- Active: background `{colors.ink}`, text `{colors.on-dark}`.

**`segmented-tab`** + **`segmented-tab-active`** — Underline-style tab navigation.
- Inactive: text `{colors.steel}`, no border. Active: text `{colors.brand-green-dark}`, 2px bottom border in `{colors.brand-green-dark}`.

### Badges & Status

**`badge-green`** — Bright green badge for new product highlights.
- Background `{colors.brand-green}`, text `{colors.on-primary}`, typography `{typography.caption-bold}`, rounded `{rounded.sm}`, padding `2px 8px`.

**`badge-green-soft`** — Pale-mint pill for success/free indicators.
- Background `{colors.brand-green-soft}`, text `{colors.brand-green-dark}`, typography `{typography.caption-bold}`, rounded `{rounded.full}`, padding `4px 10px`.

**`badge-purple`** — Purple course category tag.
- Background `{colors.accent-purple}`, text `{colors.on-dark}`, typography `{typography.caption-bold}`, rounded `{rounded.sm}`, padding `2px 8px`.

**`badge-orange`** — Orange course category tag.
- Background `{colors.accent-orange}`, text `{colors.on-dark}`, typography `{typography.caption-bold}`, rounded `{rounded.sm}`, padding `2px 8px`.

**`badge-popular`** — "Most Popular" tier indicator (dark teal pill with green text).
- Background `{colors.brand-teal-deep}`, text `{colors.brand-green}`, typography `{typography.caption-bold}`, rounded `{rounded.full}`, padding `4px 10px`.

**`promo-banner`** — Dark teal sticky promo strip ABOVE the top nav.
- Background `{colors.brand-teal-deep}`, text `{colors.on-dark}`, typography `{typography.body-sm-medium}`, padding `{spacing.sm} {spacing.md}`.

### Code

**`code-block`** — Code container.
- Background `{colors.canvas-dark}`, text `{colors.on-dark}`, typography `{typography.code-md}`, rounded `{rounded.md}`, padding `{spacing.md}`.

**`code-mockup-card`** — Embedded code mockup on hero band.
- Background `{colors.canvas-dark}`, text `{colors.on-dark}`, rounded `{rounded.lg}`, padding `{spacing.lg}`. Carries terminal-aesthetic code snippet.

### Tables

**`comparison-table`** — Pricing feature comparison table.
- Background `{colors.canvas}`, text `{colors.ink}`, typography `{typography.body-sm}`, rounded `{rounded.md}`, border `1px solid {colors.hairline}`.

**`comparison-row`** — Individual feature row.
- Background `{colors.canvas}`, text `{colors.ink}`, padding `{spacing.md} {spacing.lg}`, bottom border `1px solid {colors.hairline-soft}`.

### Documentation Components

**`service-tile`** — Tile in "Customize your deployment" 6-up grid.
- Background `{colors.canvas}`, rounded `{rounded.lg}`, padding `{spacing.xl}`, border `1px solid {colors.hairline}`.

**`why-card`** — "Loved by builders" feature card.
- Background `{colors.surface}`, rounded `{rounded.lg}`, padding `{spacing.xl}`.

**`customer-testimonial-card`** — Customer quote card.
- Background `{colors.canvas}`, rounded `{rounded.lg}`, padding `{spacing.xxl}`, border `1px solid {colors.hairline}`.

**`logo-wall-item`** — Customer logo wordmark cell.
- Background transparent, text `{colors.steel}`, typography `{typography.body-md-medium}`, padding `{spacing.lg}`.

**`faq-accordion-item`** — FAQ panel.
- Background `{colors.canvas}`, rounded `{rounded.md}`, padding `{spacing.xl}`, bottom border `1px solid {colors.hairline}`.

### Navigation

**Top Navigation (Marketing)** — Sticky white bar.
- Background `{colors.canvas}`, height ~64px, bottom border `1px solid {colors.hairline}`.
- Left: MongoDB leaf logo + "Solutions / Resources / Company / Pricing" links.
- Right: "Sign In" link + bright-green pill "Try Free" CTA.

### Signature Components

**`hero-band-dark`** — Deep teal hero band with embedded code mockup.
- Background `{colors.brand-teal-deep}`, text `{colors.on-dark}`, padding `{spacing.hero}`.
- Layout: centered headline `{typography.hero-display}`, subtitle, button row, `code-mockup-card` below.

**`hero-platform-card`** — Lighter-teal platform showcase card on dark hero.
- Background `{colors.brand-teal-mid}`, text `{colors.on-dark}`, rounded `{rounded.xl}`, padding `{spacing.xxl}`.

**`cta-banner-dark`** — Dark CTA banner at the bottom of feature pages.
- Background `{colors.brand-teal-deep}`, text `{colors.on-dark}`, rounded `{rounded.lg}`, padding `{spacing.section}`.

**`footer-region`** — Dark teal multi-column footer.
- Background `{colors.brand-teal-deep}`, padding `{spacing.section} {spacing.xxl}`.
- 6-column link grid.
- Section headings in `{typography.body-sm-medium}` `{colors.on-dark}`.

**`footer-link`** — Individual footer link.
- Background transparent, text `{colors.on-dark-muted}`, typography `{typography.body-sm}`, padding `{spacing.xxs} 0`.

## Do's and Don'ts

### Do
- Use `{colors.brand-green}` (bright MongoDB green) for primary CTAs everywhere
- Pair dark-teal hero bands with bright green CTA pills
- Apply `{rounded.full}` to every button, every status badge
- Apply `{rounded.lg}` (12px) to cards consistently
- Use category accent colors (purple, orange, green, teal) ONLY for course tags
- Maintain Euclid Circular A across every UI surface
- Use code mockup cards with terminal-aesthetic content for product showcases

### Don't
- Don't use the bright green for body text or large surfaces
- Don't introduce additional accent colors beyond the brand green and category-encoding palette
- Don't soften corners on buttons; the pill is a brand signature
- Don't replace deep teal hero bands with white hero bands
- Don't apply heavy shadows on flat documentation cards; reserve elevation for code mockups
- Don't use Source Code Pro for prose

## Responsive Behavior

### Breakpoints
| Name | Width | Key Changes |
|---|---|---|
| Mobile (small) | < 480px | Single column. Hero 36px. Pricing 1-up. Course catalog 1-up. |
| Mobile (large) | 480 – 767px | Course tiles 2-up. Hero 48px. |
| Tablet | 768 – 1023px | 2-column feature grids. Hero 56px. |
| Desktop | 1024 – 1279px | 3-tier pricing card row. 3-up course catalog. Hero 64px. |
| Wide Desktop | ≥ 1280px | Full 72px hero presentation. |

### Touch Targets
- Pill buttons render at 40–44px effective height
- Form inputs render at 44px height
- Search pill (large) renders at 56px
- Pill tabs ~32px → 44px on mobile

### Collapsing Strategy
- **Promo banner** stays full-width; truncates at < 480px
- **Top nav** below 1024px collapses to hamburger
- **Hero band**: code mockup card moves below text on mobile
- **Pricing tiers**: 3-column → 2-column tablet → 1-column mobile
- **Course catalog**: 3-up → 2-up tablet → 1-up mobile
- **Hero typography**: 72px → 56px → 48px → 36px
- **Footer**: 6-column desktop → 3-column tablet → accordion mobile

### Image Behavior
- Atmospheric AI imagery uses 16:9 ratio with full-bleed scaling
- Code mockup card content remains readable across breakpoints
- Customer logo wall: wordmarks at consistent 60–80px height

## Iteration Guide

1. Focus on ONE component at a time
2. Reference component names and tokens directly
3. Run `npx @google/design.md lint DESIGN.md` after edits
4. Add new variants as separate `components:` entries
5. Default to `{typography.body-md}` for body
6. Keep `{colors.brand-green}` as the primary CTA across all surfaces
7. Pill-shaped buttons (`{rounded.full}`) always
8. Dark-teal hero bands frame primary CTAs

## Known Gaps

- Specific dark-mode token values for canvas/surface beyond hero bands not surfaced
- Animation/transition timings not extracted; recommend 150–200ms ease
- Form validation success state not explicitly captured
- Course-tile category color mappings are observation-based


## ダッシュボード固有の決めごと(2026-10 UI改善で追記)

[IMPROVEMENT_PLAN_2026-10.md](IMPROVEMENT_PLAN_2026-10.md) の Final Phase(「オフィスビューの配色・状態表現を追記する」)と、
[IMPROVEMENT_DESIGN_2026-10.md](IMPROVEMENT_DESIGN_2026-10.md) §3 の決めごと表(原則 P1)を実装した内容の記録。

> **このファイルの上のトークン(MongoDB風)は参考値で、実際のダッシュボードには使っていない。**
> 実装は `hub/dashboard/static/style.css` の Retool 系トークン(暗い地 `#151515` / 羊皮紙色の文字 `#e9ebdf`)で、
> 配色・書体・レイアウトの骨格は変えていない(原則 P2)。以下は、その上で決めたことだけを書く。

### 決めごと表(P1)

| 項目 | 決め | 実装の場所 |
|---|---|---|
| 言語 | 見出し・列名・状態は日本語。固有名詞・識別子・ボタンの動詞(Start / Sync / Snooze)だけ英字 | `templates/` |
| 記号 | 状態は文字記号の1セット(✓ ▲ ■ ○ –)。**絵文字は使わない**(🔕 ⚠ などは廃止) | `partials/_macros.html` |
| 状態 | 色だけにしない。必ず「記号 + 日本語の文字」を併記する | `state_pill` マクロ |
| 数字 | 半角。桁が揃う所は `font-variant-numeric: tabular-nums`(`.num`)。応答時間は右揃え | `style.css` |
| 開閉 / 遷移の矢印 | 開閉は下向き ▾(開くと上向き ▴)、遷移は右向き ▸ | `.runbook .chev` |
| 1行に詰める情報 | 1行に1つ。名前 + 灰色の副題の2段(ツール行・アラート行) | `.tool-row` `.alert-sub` |
| 操作 | 危険度の低い順に並べ、書き換える操作(Sync)は別の列に離して、押す前に確認を挟む | リポジトリ表 |

### 状態の表現(5状態)

| 状態 | 文字 | 記号 | 背景 / 文字(ダーク) | 意味 |
|---|---|---|---|---|
| 正常 | 正常 | ✓ | `--state-ok-bg` / `--state-ok-text` | 死活監視がupで、未解消のアラートが無い |
| 警告 | 警告 | ▲ | `--state-warn-bg` / `--state-warn-text` | 生きているが、別のアラートが未解消 |
| 停止 | 停止 | ■ | `--state-danger-bg` / `--state-danger-text` | 死活監視がdown、または死活監視由来のアラートが未解消 |
| 未確認 | 未確認 | ○ | 透明 / `--text-ash`(枠線のみ) | 死活監視の信号がまだ一度も無い |
| 対象外 | 対象外 | – | 透明 / `--text-ash`(枠線のみ) | registryで `category: excluded` |

- 計画書の3状態(正常・警告・停止)に、**「未確認」「対象外」の2つを足した**。ハートビートがまだ無いツールや監視対象外のツールを、
  「正常」と偽って緑にしないため。この2つは色を持たせず、枠線だけにする。
- 警告は「重大度が warn」ではなく「停止ではない未解消アラートがある」で決める。視覚回帰の失敗(critical)のように、ツールは動いているが
  問題がある状態を「停止 ■」と見せないため。重大度は各アラートの行に別途出す(■ 重大 / ▲ 警告 / ○ 情報。同じ記号体系)。
- 区分(能動監視 / 受動監視)は状態ではないので、色を持たせず枠線だけにした(以前は能動監視が緑で「正常」と紛らわしかった)。

### ツールの丸い記号(U3)

- registry.yaml の `symbol`(1〜2文字)と `color`(#rrggbb)で固定する。**12ツールは全て明示指定**し、記号・色とも重複しない。
- 丸の背景は彩度 0.26 に抑えた色で、文字色 `#e9ebdf` とのコントラストは 4.6:1 以上(全色相で検証)。状態色(緑 / 橙 / 赤)と取り違えにくいよう、鮮やかにしない。
- 同じ記号を、ツール一覧・オフィス・詳細・アラート行・サマリの直近アラートの全てで使う。
- 台帳に新しく足したツールで `symbol` / `color` を省くと、tool_id から自動生成する(同じIDなら常に同じ値)。記号の重複までは防がない(色と名前で見分ける)。

### オフィスビュー(H1)の配色・状態表現

一覧の代替ビュー(「オフィス」チップで切り替え。既定は一覧)。1席 = 独立した小さなSVGなので、ツール数が増えても並べ方はCSSグリッドの自動配置に任せられる。

| 部品 | ダーク | ライト |
|---|---|---|
| 机の天板 / 左面 / 右面 | `#3a3b37` / `#2c2d2a` / `#323330` | `#d8d6c8` / `#c3c1b2` / `#cdcbbd` |
| モニター本体 | `#1b1c1a` | `#3a3b37` |
| 人物(頭 / 体・腕) | `#b6b8af` / `#94958e` | `#6f7167` / `#8d8f84` |
| 床の影 | `rgba(0,0,0,.35)` | `rgba(0,0,0,.12)` |

人物は無彩色で、**状態は「モニターの画面の色と記号」と「人物の動き」**で表す(色は状態色のトークンをそのまま使う)。

| 状態 | 画面 | 人物の動き |
|---|---|---|
| 正常 | 緑の画面に ✓ | ゆっくりタイプする(両腕が交互に小さく上下) |
| 警告 | 橙の画面に ▲ | 右手を振る |
| 停止 | 赤の画面に ■ | うなだれて動かない |
| 未確認 | 暗い画面に ○ | 頭に「?」。動かない |
| 対象外 | 暗い画面に –(机ごと薄く) | 人物なし(空の椅子) |

- 状態は、SVGとは別にタイルの下へ「記号 + 文字」でも必ず出す(SVGは装飾。`aria-hidden`)。
- 動きは `prefers-reduced-motion: reduce` で全て止まる。通常画面(一覧)は静かに保つ(P8)。

### アラート履歴スライダー(Phase 3)

- 元データは SQLite のアラート履歴(1行 = 1つの発生→解消)。選んだ時刻に未解消だったアラートから、ツールの状態を再構成する。
- 履歴に残っているのは「アラートの発生・解消」だけで、死活監視の結果そのものは残らない(設計書 §6 のリスクの確認結果)。
  そのため過去の時刻では「未解消のアラートが無いツール = 正常」とみなす近似になり、**Hubが止まっていた期間は再現できない**。この注記を、過去を見ている間は常にバナーで出す(P9)。
- 目盛り: 発生は塗りつぶしの丸、解消は白抜きの丸(色だけでなく形でも区別)。再生は、時間を均等に進めずに、発生・解消の出来事を1つずつ辿る。
- 過去を見ている間は自動更新を止め、カードの枠を点線にする。「いま」で戻る。

### 遊びごころの置き場所(P8)

通常画面は静かに保ち、次の3か所にだけ入れる。全て `prefers-reduced-motion` で止まる。

| 場所 | 内容 |
|---|---|
| 空状態(アラートが1件も未解消でない) | 「現在アラートはありません。」+ チェックを描く小さな動き(そのタブで最初の1回だけ描き、自動更新後は静止) |
| 解消の瞬間 | 前回の読み込みで未解消だったアラートが解消されたとき、右サマリの上に小さな紙吹雪(14片 / 約1秒) |
| 404 | 「この席には、誰もいません」+ 空の机を歩く人物。ブラウザでの404のみ(API・静的ファイルは従来どおりJSON) |

計画書 H7 の「新規アラート時のタップ波紋」は入れていない。設計書 §4.2 が「通知の演出は解消時のみ、通常時は静か」とし、P8 の置き場所にも「問題が起きた瞬間」が無いため。

### テーマ(P10)

- ダーク(既定)とライト。トークンの差し替えで切り替え、右上の ☾ / ☀ で手動に切り替える。選択は localStorage に保存。
- ダークの配色は変えない(P2)ため、OSの `prefers-color-scheme` には**自動では追従しない**(ライトのOSで開くと突然配色が変わるのを避ける)。追従させたい場合は、`style.css` のライトのトークンを `@media (prefers-color-scheme: light) { :root:not([data-theme]) { ... } }` にも複製する。
- 狭い画面(〜960px)は1列(サマリ → 一覧 → 詳細)に畳み、表はカードの中だけで横スクロールする(ページ全体は横に動かさない)。
