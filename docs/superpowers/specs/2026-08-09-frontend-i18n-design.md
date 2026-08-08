# Frontend i18n Completion Design

## Goal

Replace user-visible Chinese hardcoded text in the React frontend with `react-i18next` translation lookups and expand the semantic resource library to English, Chinese, and French. On a first visit, the interface follows the browser language when it resolves to one of those language families. Unsupported languages fall back to English. A user-selected language, when present, takes priority on later visits.

## Scope

The migration covers user-visible text in `frontend/src`, including:

- Page and navigation titles
- Buttons, links, labels, placeholders, and tooltips
- Tables, charts, filters, pagination, and status labels
- Loading, empty, validation, confirmation, and error messages
- Accessibility labels and other user-facing attributes
- Text assembled from variables, counts, dates, and identifiers

The migration does not translate:

- Source-code comments
- Brand names, symbols, model names, route paths, API field names, and technical identifiers
- User-generated content or backend-provided domain data
- Backend error text that the frontend displays as raw diagnostic detail

## Architecture

The existing `i18next`, `react-i18next`, and `i18next-browser-languagedetector` integration remains the single localization mechanism.

- `frontend/src/i18n/index.ts` owns initialization and language detection.
- `frontend/src/i18n/locales/en.json` is the complete English resource and fallback.
- `frontend/src/i18n/locales/zh.json` mirrors the English key structure with Chinese values.
- `frontend/src/i18n/locales/fr.json` mirrors the English key structure with idiomatic French values.
- Components use `useTranslation()` and `t()` for rendered text.
- Non-component utilities that produce user-facing labels accept a translation function or return stable keys rather than importing UI-global state implicitly.

Translation keys are grouped by feature or shared concern, such as `common`, `nav`, `market`, `workflows`, and `ai`. Existing keys are retained where their meaning remains correct.

## Language Resolution

Language resolution follows this precedence:

1. Explicit query-string language, when supplied for testing or sharing
2. Previously saved language in local storage
3. Browser language (`navigator.language` / `navigator.languages`)
4. English fallback

Supported language families are English, Chinese, and French. Regional variants such as `en-US`, `zh-CN`, `zh-TW`, `fr-FR`, and `fr-CA` resolve to their base supported language. Unsupported languages resolve to English.

This design does not require adding a new language selector. If an existing or future selector calls `i18n.changeLanguage`, the selected language is persisted by the detector configuration.

## Migration Rules

- Every user-visible literal is replaced with a stable semantic translation key.
- Interpolated text uses i18next variables instead of string concatenation.
- Counts use i18next pluralization where English grammar requires it.
- Punctuation belongs in the translation value when its placement may vary by language.
- Status codes remain stable data values and map to localized display labels at the presentation boundary.
- English, Chinese, and French resources must contain matching key sets.
- French translations use natural product and quantitative-finance terminology rather than literal word-for-word translation; stable identifiers such as API, PDF, SQL, AI, ticker symbols, model IDs, and run IDs remain unchanged.
- Existing local modifications are preserved; edits are limited to localization-related lines and tests.

## Error Handling

- Missing or unsupported detected languages fall back to English.
- Missing translation keys are treated as test or development failures rather than intentionally displayed key names.
- Raw backend errors remain available for diagnostics, but surrounding frontend labels and generic fallbacks are localized.

## Testing and Verification

Behavioral tests will be added and observed failing before implementation changes. They will verify:

- A Chinese browser locale selects Chinese on first visit.
- An English browser locale selects English on first visit.
- A French browser locale selects French on first visit.
- An unsupported browser locale falls back to English.
- A saved supported language overrides browser detection.
- Representative components render localized text rather than hardcoded Chinese.
- English, Chinese, and French resource files have the same recursive key set.

Completion checks include the frontend test suite, TypeScript type checking, production build, and a source scan for Chinese characters outside the Chinese resource file. Remaining matches must be limited to non-user-visible comments or explicitly documented technical data.

## Success Criteria

- No user-visible Chinese text is hardcoded in React or TypeScript source.
- English is the fallback and the visible default for unsupported browser languages.
- First visits with a Chinese browser locale render Chinese.
- First visits with an English browser locale render English.
- First visits with a French browser locale render French.
- All three locale files are valid UTF-8 JSON with matching keys.
- Existing frontend behavior and the user's in-progress changes remain intact.
