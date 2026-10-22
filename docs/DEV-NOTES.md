# Developer notes

Notes that used to live only in HTML comments. The comments are still in the source (they explain each page), but
publishing strips them, so nothing internal reaches a visitor. This folder isn't published (`_config.yml`).

## Publishing

- Every push to `main` runs `.github/workflows/pages.yml`: Jekyll builds the site (honouring `_config.yml`'s
  exclude list), then `tools/3_publish_site/publish_site.py` strips every HTML comment and CSS comment, stamps every `?v=` with the
  commit's short hash, and writes `sitemap.xml`. The Pages source must be **GitHub Actions** (Settings > Pages).
- In the repo every asset reference is `?v=dev`: nothing to bump by hand. `script.js` passes the same `?v=` on to the
  data files it loads.
- Adding a page: run `python3 tools/3_publish_site/publish_site.py --sitemap .` so the repo's `sitemap.xml` lists it (the publish step
  rewrites it anyway). `404.html` uses absolute paths (`/styles.css`) so it works at any depth.
- Not published: `README.md`, `CHANGES.md`, `requirements.txt`, `tools/`, `docs/`, `media/exports/generated.json`
  (no page reads it at runtime).

## Placeholders still to fill

Anything not yet known is marked with a `data-placeholder` attribute; search the HTML for the token.

| Token | Where | What it needs |
| --- | --- | --- |
| `[[LINKEDIN_URL]]` | the hidden LinkedIn chip on every page | the profile address; then show the chip as a link |
| `[[QUOTE_1]]` | `about.html`, hidden testimonial slot | a client quote, with permission |
| `[[ANALYTICS_TOKEN]]` | `script.js` (ANALYTICS) | a cookieless analytics provider's token, script and event call (see below) |

## Switches

- **Prices:** `PRICES` and `SHOW_PRICES` in `script.js` ($110 an hour, $800 a day). Without JavaScript each price reads
  "Talk to me about pricing".
- **Analytics:** off. `ANALYTICS` in `script.js`: while `token` is a `[[TOKEN]]` nothing loads or sends. To switch on,
  set `token`, `src` (the provider's script) and `send(name, detail)`. Events come from `data-track` attributes:
  `numbers-check` (every "Ask for a free 20-minute numbers check" button, which goes to the contact page with the
  numbers check picked), `email` (mailto links), `export` (each download; detail = format) and `contact-submit` (sent once the form
  passes its checks; detail = the topic). New buttons only need the attribute.
- **Intro animation:** plays once per visit on the home page; skipped for reduced motion, automated tests, a link to a
  section, or `?intro=off`; `?intro=on` forces it; clicking the sheets beside the headline replays it.

## Copy rules worth remembering

- "CPA" isn't shown anywhere on the site.
- No employer is named anywhere; no client results are claimed; sample data is labelled as sample data.
- Technology agnostic: "spreadsheets" and "slides", not product names, except the Services "Can I have it in Excel? Yes."
  section and the list of tools worked in.
- Australian English; "cafe", not "café"; "gross margin", never "profit" for job margins.

## Contact form

Posts to FormSubmit (`https://formsubmit.co/ajax/<business email>`), which emails each enquiry as a table with the
subject "Website enquiry: <topic>, <organisation>". The very first send triggers FormSubmit's activation email: click it
once. Any service that takes a form POST and answers in JSON can replace it by changing the form's `action`. Bots that
fill the hidden trap field are told "thanks" but nothing is sent. `?topic=monthly&report=…&period=…&view=…` (from a report's Export menu) fills in the
request; the topic value `monthly` is shown as "Monthly reporting, done for me". Organisation, job title and phone are
required; phone must be an Australian number (mobile, landline, 13/1300/1800 or +61; spaces allowed).
