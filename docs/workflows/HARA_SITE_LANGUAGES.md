# HARA Labs interface languages

The institutional site supports Portuguese (`pt-BR`) and English (`en-US`). The selector sits immediately after the Neon button on every content page. The two legacy legal aliases forward to the canonical legal pages.

## Selection and navigation

Language preference resolves in this order: a supported `?lang=pt|en` URL parameter, saved `hara-language` preference, supported browser preference, then Portuguese. Explicit URL choices are saved when storage is available. Switching works without storage and does not reload the current page.

Navigation between known institutional routes carries the chosen `lang` query parameter, including apex and `www` links. Links to the Commander home page can carry the same choice. Email, external destinations, authentication endpoints, API URLs and downloads remain unchanged. The legal aliases preserve the selected language, query and fragment; their original redirect remains available when JavaScript is disabled.

## Translation sources

- `public/assets/js/i18n-catalog.js` contains the shipped PT/EN catalog. Static keys correspond to explicit annotations in the HTML. Dynamic strings use their Portuguese source text as the key.
- `public/assets/js/i18n.js` applies annotations, updates accessible language state, remembers the choice and dispatches `hara:languagechange`. Titles use `html[data-i18n-page-title]` so canonical title and wordmark markup stay intact.
- `public/assets/css/i18n.css` places the selector beside Neon and adapts the header on small screens.
- `public/assets/js/script.js` localizes theme/Neon accessibility labels.
- `public/observabilidade/app.js` renders localized status labels and dates from the last snapshot. Language changes do not trigger a fetch or restart polling. Received counts, IDs, values and unknown names remain literal. Only explicitly known public editorial copy is localized.

Preserve message placeholders such as `{count}`, `{up}` and `{total}`. Keep company names, identifiers, URLs and factual dates unchanged. A missing catalog leaves the original Portuguese interface usable and disables unavailable English.

## Validation

Run `node scripts/test_site_i18n.mjs` to check catalog coverage, syntax, selector placement, brand/404 parity, language precedence, navigation and operational URL boundaries. The existing provenance workflow runs this alongside the unchanged structure, wordmark and public-sanitization checks.

The browser validation uses an isolated Chromium profile, intercepted requests and synthetic observability data. It covers all 17 HTML routes, legal redirects, English navigation, persistence, keyboard/ARIA behavior, 1440/390/320px viewports and browser errors. It does not authenticate or send production mutations.

Deployment continues through the existing reviewed branch, pull request, required checks and merge to `main`, followed by Cloudflare and public apex/`www` readback. A local test or branch URL does not establish production deployment.
