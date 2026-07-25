---
name: AnkiForge
description: JetBrains IDE-style AI flashcard creation & orchestration workbench
colors:
  primary: "#6366f1"
  primary-hover: "#4f46e5"
  neutral-bg: "#0f1115"
  sidebar-bg: "#16181d"
  panel-bg: "#1e2128"
  input-bg: "#1a1d24"
  border: "#2d313a"
  text-primary: "#f8fafc"
  text-secondary: "#94a3b8"
  text-muted: "#64748b"
  semantic-red: "#ef4444"
  semantic-green: "#10b981"
  semantic-yellow: "#f59e0b"
  semantic-blue: "#3b82f6"
typography:
  body:
    fontFamily: "Inter, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.4
  code:
    fontFamily: "Fira Code, monospace"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  sm: "6px"
  md: "10px"
  lg: "16px"
spacing:
  sm: "6px"
  md: "12px"
  lg: "16px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.sm}"
    height: "36px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-secondary:
    backgroundColor: "{colors.input-bg}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.sm}"
    height: "36px"
  button-danger:
    backgroundColor: "rgba(239, 68, 68, 0.12)"
    textColor: "{colors.semantic-red}"
    rounded: "{rounded.sm}"
    height: "36px"
---

# Design System: AnkiForge

## Overview

**Creative North Star: "The JetBrains Forge Workbench"**

AnkiForge delivers a high-density, professional desktop environment inspired by modern developer IDEs. Built natively on PySide6 and Qt WebEngine, the interface prioritizes speed, information density, and precise visual feedback for processing heavy educational datasets into Anki flashcards.

The aesthetic relies on deep charcoal and obsidian surfaces (`#0f1115`, `#16181d`, `#1e2128`) framed by sharp 1px structural borders (`#2d313a`) and targeted indigo accent glows (`#6366f1`). Visual clutter is strictly avoided so focus remains on card content, KaTeX math expressions, and batch AI orchestration.

**Key Characteristics:**
- High-density dark technical palette with indigo accent hierarchy.
- JetBrains-style multi-dock panel layouts with custom PySide6 splitters.
- Native Qt performance with live KaTeX/LaTeX rendering preview.
- Dynamic native drop-shadow effects (`QGraphicsDropShadowEffect`) on interactive hover states.

## Colors

Deep obsidian dark mode anchored by an electric indigo accent for primary actions and semantic feedback tones.

### Primary
- **Indigo Accent** (`#6366f1`): Used for primary action buttons, focused input borders, active table row indicators, and progress bars.
- **Indigo Hover** (`#4f46e5`): Hover state for primary buttons and active selections.

### Neutral
- **Main Canvas** (`#0f1115`): Root background for the application window.
- **Sidebar Surface** (`#16181d`): Secondary surface for navigation drawers and header sections.
- **Panel Surface** (`#1e2128`): Cards, table containers, dock panels, and popup menus.
- **Input Background** (`#1a1d24`): Recessed background for text edits, inputs, and comboboxes.
- **Border Structural** (`#2d313a`): 1px borders framing panels, tables, and inputs.
- **Text Primary** (`#f8fafc`): High-contrast white text for primary headings and body readability.
- **Text Secondary** (`#94a3b8`): Slate text for labels, descriptions, and secondary metadata.
- **Text Muted** (`#64748b`): Low-emphasis text for table headers, disabled states, and hints.

### Semantic
- **Error Red** (`#ef4444`): Destructive actions, validation errors, duplicate card warnings.
- **Success Green** (`#10b981`): Completed background tasks, Anki sync confirmations.
- **Warning Yellow** (`#f59e0b`): Unsaved changes, pending conflict merges.
- **Info Blue** (`#3b82f6`): Telemetry notices and informational badges.

### Named Rules
**The Rarity Rule.** The primary indigo accent (`#6366f1`) is applied to ≤10% of any given view to maintain high visual impact.

## Typography

**Body Font:** Inter (with system sans-fallback)  
**Code/Editor Font:** Fira Code (with monospace fallback)  

**Character:** Technical, crisp, and readable at small pixel sizes for high-density IDE panes.

### Hierarchy
- **Headline** (700, 18px, 1.2): Section titles and topbar view headers.
- **Title** (600, 14px, 1.3): Panel headings and modal titles.
- **Body** (400, 13px, 1.4): Primary interface text and table content.
- **Small/Label** (600, 11px, uppercase): Table headers and status badges.
- **Code/Editor** (400, 12px, 1.5): Flashcard note source editor, HTML/Jinja2 markup, and KaTeX input.

### Named Rules
**The Monospace Scope Rule.** Monospace typography (Fira Code) is strictly reserved for code blocks, raw card field markup, math macros, and system log output.

## Layout

The layout follows a modular IDE multi-dock architecture:
- **Global Topbar:** Fixed height 28px for window controls and profile switching.
- **Navigation Sidebar:** Collapsible drawer switching between 260px expanded and 68px collapsed modes.
- **Dock Panes:** Flexible QSplitter boundaries (2px handle) allowing multi-panel workspace customization.
- **Internal Margins:** Standard 12px to 16px container padding with 6px component spacing.

## Elevation & Depth

AnkiForge uses flat surface hierarchy at rest separated by 1px borders (`#2d313a`). Depth is introduced dynamically on user interaction using native Qt drop shadows (`QGraphicsDropShadowEffect`).

### Shadow Vocabulary
- **Control Shadow** (`blur=10, y=0, color=rgba(99,102,241,0.4)`): Glowing indigo drop shadow under `PrimaryButton` on hover.
- **Panel Elevation** (`blur=12, y=4, color=rgba(0,0,0,0.5)`): Ambient shadow under floating menus, cards, and modal dialogs.

### Named Rules
**The Native Shadow Rule.** Shadow effects are applied exclusively via native Qt `QGraphicsDropShadowEffect` Python bindings, never via CSS `box-shadow` strings in QSS.

## Shapes

- **Small Radius** (`6px`): Buttons, inputs, comboboxes, and menu items.
- **Medium Radius** (`10px`): Panels, cards, and table containers.
- **Large Radius** (`16px`): Modal dialogs and overlay banners.

## Components

### Buttons
- **Shape:** 6px border radius, 36px fixed height.
- **Primary:** Background `#6366f1`, text `#f8fafc`, 600 weight, 10px-16px indigo glow on hover.
- **Secondary:** Background `#1a1d24`, 1px border `#2d313a`, text `#f8fafc`. Hover border `#4b5563`.
- **Danger:** Background `rgba(239, 68, 68, 0.12)`, 1px border `rgba(239, 68, 68, 0.25)`, text `#ef4444`. Hover background `rgba(239, 68, 68, 0.25)`.
- **Icon Button:** 32x32px transparent background, 6px radius, background `#2d313a` on hover.

### Inputs / Text Fields
- **Style:** Background `#1a1d24`, 1px border `#2d313a`, 6px radius, text `#f8fafc`.
- **Focus:** 1px border shift to `#6366f1`.

### Data Tables / Grids
- **Header:** Background `#16181d`, text `#64748b`, 11px uppercase bold, 1px bottom border `#2d313a`.
- **Row:** Background `#1e2128`, text `#f8fafc`, 8px 12px padding. Hover background `#2d313a`. Selected row background `#2d313a` with 2px indigo left accent border.

## Do's and Don'ts

### Do:
- **Do** maintain strict 1px border contrast (`#2d313a`) between dark panel surfaces.
- **Do** use native `QGraphicsDropShadowEffect` for hover state glow animations on primary buttons.
- **Do** keep font sizes compact (13px body, 12px editor) to maximize technical information density.

### Don't:
- **Don't** use inline CSS `box-shadow` in PySide6 QSS stylesheets.
- **Don't** use bright accent colors on plain surface panels; keep accents reserved for interactive controls and status badges.
- **Don't** hardcode static pixel layout heights when calculating flexible dock containers.
