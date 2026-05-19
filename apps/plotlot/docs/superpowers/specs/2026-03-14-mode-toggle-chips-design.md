# Mode Toggle + Capability Chips — Design Spec

## Goal

Replace the standalone mode toggle with an in-bar toggle (Lookup / Agent) and add mode-aware capability chips on the welcome screen.

## Components

### `ModeToggle.tsx`
- Compact pill toggle: "Lookup" / "Agent"
- Fits inside the input bar, left of send button
- Lookup selected: dark bg pill. Agent selected: dark bg pill.
- Unselected: muted text, hover to secondary

### `CapabilityChips.tsx`
- Mode-aware quick-action buttons below input on welcome state
- Lookup chips: "Analyze Property", "Check Zoning", "View Map"
- Agent chips: "Analyze Property", "Generate Documents", "Search Comps", "Pro Forma", "Search Properties"
- Click fills input with template prompt (e.g., "Analyze 123 Main St, Miami, FL")
- Chips use existing design: rounded-full, border, hover effects

### `page.tsx` Changes
- Remove inline `ModeToggle` component definition
- Move toggle inside input bar (between AddressAutocomplete and send button)
- Rename modes: "quick" → "lookup", "chat" → "agent" (update AppMode type)
- Replace `WELCOME_SUGGESTIONS` with `CapabilityChips` on welcome
- Welcome state shows chips below input bar instead of above

## Non-Goals
- Backend tool masking changes (Phase B only changes frontend)
- File upload (Phase C)
