# Input Bar Enhancements — Design Spec

## Goal

Enhance the input bar with attachment button, web search toggle, and responsive mobile polish.

## Components

### Attachment Button (`+` icon, left side of input)
- Opens file picker for property documents (PDFs, images, contracts)
- Files stored client-side as base64 for now (no backend upload endpoint yet)
- Shows attached file count badge
- Accepts: .pdf, .jpg, .png, .docx
- Max 5 files, 10MB each

### Web Search Toggle (globe icon)
- Toggles web search capability on/off
- When on: agent can search the web for property data
- Visual: globe icon, amber highlight when active
- Only visible in Agent mode (not Lookup)

### Responsive Polish
- Input bar stacks vertically on very small screens (< 380px)
- Mode toggle hides labels on mobile, shows icons only
- Attachment and web search buttons collapse to icon-only on mobile

## Files

| File | Action |
|------|--------|
| `src/components/InputBar.tsx` | Create — unified input bar with all controls |
| `src/app/page.tsx` | Modify — replace inline input with InputBar component |

## Non-Goals
- Backend file upload API (future)
- Actual web search integration (already exists in chat tools)
