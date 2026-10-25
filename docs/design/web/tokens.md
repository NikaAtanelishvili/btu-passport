# Design tokens (from Claude Design)

## Base
- background #FFFFFF, foreground #000000
- muted surface #F4F4F5, muted text #5C5C66
- borders: cards and table rows 1px #E4E4E7; inputs, outline buttons, result panels and dialogs 1.5px #000
- focus ring #000; no shadows anywhere

## Primary
- primary #E6007E with white text (buttons 16px semibold or larger)
- pink links on white: #C4006B

## Stamp colors
coral #FF3F3F, violet #5E00FF, navy #07207E, orange #FF6A00,
mint #31F48E, cyan #00DBFF, magenta #CE2094, sticker pink #FF2490

## Status colors (fill with black text / soft tint for badges / dark text on white)
- VALID: #31F48E / #D6FCE8 / #00703C
- SUPERSEDED: #FF6A00 / #FFE6D4 / #B34700
- NOT VALID: #FF3F3F / #FFE0E0 / #C8102E
- Expired check-in code: coral + clock icon (failure, but not "not valid")

## Radius
base 1rem; steps 8, 12, 16, 24px; cards and result panels 24–28px

## Fonts
- Outfit: headings, weight 900 paired with 200
- Inter: body
- JetBrains Mono: IDs and codes