# Tarot card assets

Technical tarot card data is stored in `app/data/i18n/cards.<locale>.json` as a single file per language.

Even though fields like `arcana/suit/rank/image_path` are language-neutral, they live in the locale file to keep the data model simple.

## Files
- `app/data/i18n/cards.<locale>.json`: 78-card catalog (Major + Minor arcana)

## Conventions (`cards.<locale>.json`)
- `id`
  - Numeric card identifier `0..77` (this is the primary key)
- `arcana`
  - `"major"` or `"minor"`
- `number`
  - For `"major"`: `0..21` (optional for `"minor"`)
- `suit`
  - For `"minor"`: `"wands"|"cups"|"swords"|"pentacles"` (optional for `"major"`)
- `rank`
  - For `"minor"`: `"ace".."ten"|"page"|"knight"|"queen"|"king"` (optional for `"major"`)
- `image_path`
  - Relative to `app/static/`
  - Major: `cards/major/{NN}_{slug}.webp`
  - Minor: `cards/minor/{suit}/{rank}.webp`

## Localized fields
- `name`
- `keywords` (`string[]`)
- `meaning_upright`
- `meaning_reversed`
- optional: `archetype`, `description`

