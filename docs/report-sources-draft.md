# Candidate sources of fishing reports and catch photos: draft for approval

**Draft, 28 November 2026. Nothing has been collected.** This is a list for the owner to approve, source by source, before any crawler is written. It covers web sources of dated recreational fishing reports and catch photos for Bream Bay and Urquharts Bay (Whangārei Harbour entrance, Bream Head, Ruakākā, Waipū, Bream Tail, Mangawhai, out to the Hen and Chickens / Taranga), plus open data that would help place them.

The intended use, as it would be described to a site owner: a free, non-commercial, open-source research site runs an open-weights language model on its own GPU over each report, keeps only extracted facts (date, place names, species, size, good or slow) and a link back, and never stores the text or the images. Photos matter only if the original file might still carry GPS EXIF.

**What was checked.** For each source, the HTML of the report pages, the site's `robots.txt` (fetched on 28 November 2026), and whatever terms, copyright or privacy page the site links. Image URLs were judged from the HTML alone.

**What was not checked.** No image, PDF, spreadsheet or other file was downloaded, so whether any photo still holds EXIF is unknown everywhere; the image columns are judgements from URL patterns. No login, sign-up or form. Three sites sit behind bot protection (Cloudflare or Incapsula) and could not be read; that protection was not worked around. No one has been asked for permission yet. This is not legal advice: "allowed" means the site's own published terms and `robots.txt` appear to permit this use, nothing more.

Ruled out by the owner and not listed: Facebook, Instagram, TikTok, YouTube, X, Reddit, Google search and images, and discussion forums (including the fishing.net.nz forum and the Angler's Planet forums).

## Summary

| Source | Kind | Area | Photos | robots.txt | Terms | Verdict |
|---|---|---|---|---|---|---|
| 1. fishing.net.nz Bream Bay Fishing Report | Report column (NZ Fishing News site) | This area, by name | Own server; one file named `_source` | Allows `*`; no AI rules | © notice only; silent on reuse | ask first |
| 2. fishing.net.nz photo gallery | User-submitted catch photos | NZ-wide; some captions in this area | Own server; camera filenames behind a resizer, may be originals | Allows `*` | © notice only | ask first |
| 3. Local Matters fishing columns | Newspaper column (Mangawhai) | This area | WordPress uploads via Jetpack CDN, `-web` copies | Allows all | Reproduction without permission prohibited | ask first |
| 4. NZ Herald / Northern Advocate | Newspaper columns | Northland; often names this area | Resizer CDN | AI bots blocked; header bars LLM use | NZME terms | **not allowed** |
| 5. Angler's Planet Whangarei reports | Report column | This area | not checked | ClaudeBot, GPTBot, CCBot blocked; `ai-train=no` | not found | ask first |
| 6. Whangarei Deep Sea Anglers Club | Club leader board, gallery | Tutukaka (just north) | Resized CDN | Allows `/` | Shop terms only | ask first (low value) |
| 7. Marsden Cove Fishing Club | Club leader board, events | Whangārei Harbour entrance | Placeholders only | No robots.txt (404) | © notice only | ask first (low value) |
| 8. Mangawhai Boating & Fishing Club | Club site | Mangawhai | Wix CDN | Allows `/` | © notice only | ask first (little there) |
| 9. NZ Sport Fishing Council | Monthly club reports, results (PDF) | National, includes local clubs | PDFs, not read | AI bots blocked; `ai-train=no` | Non-commercial reuse allowed; ask before linking | ask first |
| 10. Fishmeister charters | Charter catch posts | Mangawhai, Sail Rock, Hen and Chicks | WordPress uploads; camera filenames | Allows all | Booking terms only | ask first |
| 11. FishingBooker reports | Charter catch reports | Could not read | Could not read | Allows `/reports/`, crawl-delay 15 | could not read | ask first |
| 12. NZ Fishing Competition | Online competition | NZ-wide | Could not read | Allows all | could not read | ask first |
| 13. LINZ NZ Place Names (NZGB) | Open data: gazetteer | NZ | n/a | Layer pages allowed; data paths blocked to crawlers | CC BY 4.0 | **allowed** |
| 14. Papers Past | Historic newspaper reports | NZ, includes Northern Advocate | n/a | Could not read (Incapsula) | Could not read; search summary only | ask first |
| 15. Global Fishing Watch | Open data: AIS effort, satellite detections | Global | n/a | Allows all (website) | CC BY-NC 4.0, token needed | **allowed** (little use for recreational boats) |

Already in use and not repeated here: OBIS (CC BY 4.0) and iNaturalist observations under CC0 or CC BY, through `scripts/fetch_habitat_points.py` ([data-sources.md](data-sources.md)).

---

## 1. fishing.net.nz Bream Bay Fishing Report

- **Pages:** the series at `https://www.fishing.net.nz/fishing-reports/saltwater-fishing-reports/`, for example `https://www.fishing.net.nz/fishing-reports/saltwater-fishing-reports/bream-bay-fishing-report-26-11-26/` (26 November 2026) and `.../bream-bay-fishing-report-12-11-26/`. Some earlier ones are titled "Whangarei Bream Bay", e.g. `.../whangarei-bream-bay-fishing-report-07-03-24/`. Older ones sit under `/fishing-news/`, e.g. `https://www.fishing.net.nz/fishing-news/bream-bay-fishing-report-170117/`.
- **What is there:** text reports, about every two weeks. The site's sitemap lists about 158 Bream Bay report pages, most from 2020 to 2026, roughly 14 to 25 a year. The 26 November 2026 report is by Grant Dixon (Mangawhai) and quotes local charter skippers. It names Bream Bay, Sail Rock, the Hen and Chicken Islands, Whangārei Harbour, Waipū and Mangawhai; species snapper, blue cod, john dory and kingfish; sizes ("fish to 73cm"); and the outcome (snapper bite dropping from very strong to moderate). Example place phrase: "between the Hen and Chicken Islands".
- **Area:** this area specifically. Also a separate "Northland" series.
- **Photos:** on the site's own server. The main report image is `/sites/default/cache/file/055C460D-C121-84DD-B26A373F81E4F03A_source.jpg`. The `_source` suffix suggests the uploaded file, but it sits in a `cache` folder, so it may be a re-encoded copy. Unknown until checked.
- **robots.txt** (`https://www.fishing.net.nz/robots.txt`): `User-agent: *` / `allow: /`, then disallows only `/admin/`, `/tasks/`, `/requirements/`, `/config/`, bite-time scripts and three `.cfm` pages. No AI-specific rules. Report pages may be crawled.
- **Terms** (`https://www.fishing.net.nz/terms-and-conditions/`): the only copyright line is "All information © 2026 The Fishing Website." The terms are issued by Fishing.net.nz Ltd (Ellerslie, Auckland) and are about shop orders, privacy and accounts; they say nothing on copying, automated access, scraping or data mining. No licence.
- **Verdict: ask first.** The most useful source on the list: dated, frequent, local and full of place names. Robots permits crawling, but the terms are silent and the content is copyright, so the owner should email Fishing.net.nz Ltd before an LLM reads it.
- **Checked again the same day:** a plain request that named itself as a script got HTTP 403 for both `robots.txt` and the report page. The site turns away automated clients that say what they are, whatever its `robots.txt` says (the research agent's fetcher got through, a plain one did not). That makes asking first a requirement, not a courtesy; nothing should be fetched from it, by any route, without their written agreement.

## 2. fishing.net.nz photo gallery

- **Pages:** `https://www.fishing.net.nz/photo-gallery/photos/`
- **What is there:** catch photos submitted by registered users and published by staff ("You must be logged in to submit a photo"). Each has a short caption and a place. No dates are shown, though some filenames hold dates (e.g. `2016-08-08 10.58.29.jpg`). Places on the first page include Whangarei Heads, Sail Rock, Marsden Cove and Mangawhai, among many outside the area. Example caption place: "Out from mangawhai". Species include snapper, kingfish, hapuku, bluenose.
- **Area:** NZ-wide; a minority of photos are in this area.
- **Photos:** on the site's own server. Thumbnails come through a resizer (`/img/174/174/pics//sites/default/assets/Image/gallery/55/IMG_0201_3.jpg`), but the path inside them points at `/sites/default/assets/Image/gallery/55/` with camera-style filenames (`IMG_0201_3.jpg`, `2016-08-08 10.58.29.jpg`, `050.JPG`). These look like the original uploads, so this is the most likely place on the list to find EXIF. Not fetched.
- **robots.txt:** as for source 1; `/sites/default/assets/` is not disallowed.
- **Terms:** as for source 1. Silent on reuse of user-submitted photos.
- **Personal data:** captions often name the angler, including children. Only the place, species and size would be kept; names must not be stored.
- **Verdict: ask first.** Copyright in each photo is the uploader's or the site's, and the terms do not say which. Ask Fishing.net.nz Ltd, in the same email as source 1.

## 3. Local Matters fishing columns (Grant Dixon)

- **Pages:** columns titled "On the Ocean – …" and "Fishing – …", listed at `https://www.localmatters.co.nz/profile/grant-dixon/shortcode/` (and `/page/2/`). Read: `https://www.localmatters.co.nz/opinion/on-the-ocean-tuna-run-a-welcome-surprise/` (13 February 2025). Seen in search results: `https://www.localmatters.co.nz/opinion/fish-your-feet-first/`, `https://www.localmatters.co.nz/opinion/fishing-negotiating-holiday-angling`.
- **What is there:** opinion and report columns in the Mangawhai/Kaiwaka local paper; how often and how far back was not established. The column read names Mangawhai, Bream Bay, Whangārei, Mangawhai harbour and "Hen and Chicks Islands"; species yellowfin tuna, striped marlin, snapper, kingfish, kahawai, trevally. Same author as source 1.
- **Area:** this area.
- **Photos:** WordPress uploads served through the Jetpack CDN, e.g. `https://i0.wp.com/www.localmatters.co.nz/wp-content/uploads/2025/02/COL-OTO-1-web.jpg?resize=819%2C1024&ssl=1`. The `-web` filenames suggest copies exported for the web, and the CDN resizes them; EXIF is probably gone.
- **robots.txt** (`https://www.localmatters.co.nz/robots.txt`): `User-agent: *` / `Disallow:` (empty, so everything allowed). No AI-specific rules.
- **Terms:** Copyright Notice (`/copyright-notice/`): "Articles, information and images on this site are copyright"; "reproduction without permission of the general manager, Local Matters 2005 Ltd, is prohibited." Terms of Service (`/terms-of-service-agreement/`): users agree not to "reproduce or redistribute the Local Matter's intellectual property". Nothing on scraping, data mining or AI. Copyright holder Local Matters 2005 Ltd; no licence.
- **Verdict: ask first.** Reading is not forbidden, but passing the text through a model makes a copy, and reproduction needs the general manager's permission. Worth asking, because the same author covers the area in source 1.

## 4. NZ Herald and Northern Advocate fishing columns

- **Pages:** Northern Advocate "Fishing tips & tales with John Vowless", e.g. `https://www.nzherald.co.nz/northern-advocate/news/fishing-tips-tales-with-john-vowless/NL4Y2SBZG3IAQPN3WGFDLAON5A` (1 September 2018), and others under `/northern-advocate/news/` and `/northern-advocate/lifestyle/`. NZ Herald national fishing reports (Geoff Thomas, Peter Jessup) under `/sport/`.
- **What is there:** weekly-ish text columns going back many years. The 2018 column names Whangārei Harbour, Bream Bay, Bream Head, the Fairway Buoy area and the Hen and Chicks; species snapper, gurnard, kahawai, school shark, tarakihi. Example: "the Glinks Gully area". Some articles are Premium.
- **Area:** Northland, frequently naming this area.
- **Photos:** resized through the site's resizer, e.g. `https://www.nzherald.co.nz/resizer/v2/NQWXB4QXAZKBP5HKLN66XUAYFQ.jpg?auth=…&width=1200&height=675&quality=70`. Re-encoded at quality 70; EXIF very likely stripped.
- **robots.txt** (`https://www.nzherald.co.nz/robots.txt`): the header says use is limited to its terms and that other uses are not permitted, including "for large language models (LLMs), machine learning and/or artificial intelligence-related purposes". `User-agent: *` does not disallow article paths. `ClaudeBot`, `GPTBot`, `Google-Extended` and `anthropic-ai` groups end in `Disallow: /` (only `/sponsored-stories/*` allowed); `CCBot`: `Disallow: /`.
- **Terms:** linked to NZME (`https://www.nzme.co.nz/about-nzme/terms-conditions/`), copyright NZME Holdings Limited. The page read does not itself contain the clauses on copying or automated access; they are in a linked "NZME Network Terms of Use" PDF, not opened.
- **Verdict: not allowed.** The robots.txt header expressly bars machine-learning and LLM use, which is exactly what is planned. Only a syndication licence would change this (the header names syndication@nzme.co.nz).

## 5. Angler's Planet (formerly NZ Fishing World) Whangarei reports

- **Pages:** `https://www.anglersplanet.com/reports-regions/whangarei` (`https://www.nzfishingworld.co.nz/` now redirects to `https://www.anglersplanet.com/`). Reports listed: `/reports/whangarei-report-24-04-2026`, `/reports/whangarei-report-by-nik-key-03-04-2026`, `/reports/whangarei-report-12-03-2026`.
- **What is there:** text reports by charter skipper Nik Key (Snap Fishing Ventures). The list shows three, March to April 2026; older ones may exist but were not found. They name Whangārei Harbour, Bream Bay and the Hen and Chicks. Example: "offshore action at the Hen and Chicks".
- **Area:** this area.
- **Photos:** not checked.
- **robots.txt** (`https://www.anglersplanet.com/robots.txt`, Cloudflare-managed): `User-agent: *` / `Content-Signal: search=yes,ai-train=no,use=reference` / `Allow: /`. `ClaudeBot`, `GPTBot`, `CCBot`, `Google-Extended`, `anthropic-ai` and others: `Disallow: /`. The file says a missing signal (here `ai-input`, feeding content into a model) neither grants nor restricts. A project crawler under its own name falls under `*`, but the intent against AI use is clear.
- **Terms:** not found (no terms or copyright page linked; a privacy statement sits at `/admin/privacy-statement`). Footer: "Angler's Planet 2022". The site also has forums, which are excluded.
- **Verdict: ask first,** leaning to no. Training is refused and the major AI crawlers are blocked; extraction by a model is not addressed. Only with the publisher's written permission.

## 6. Whangarei Deep Sea Anglers Club (wdsac.co.nz)

- **Pages:** `https://www.wdsac.co.nz/` (`www.sportfishing.co.nz` redirects here). Read: `/leader-board/`, `/gallery/`, `/catch-card-and-grid-map/`, `/shop/terms/`.
- **What is there:** the leader board is an HTML table of the heaviest catch per species for 2023–24 to 2025–26, with angler, weight, line class, date and boat, but **no place**. Mostly game fish (marlin, tuna, broadbill). The gallery "Members catch & captures" has about 40 photos with no captions, dates or places. The catch card and a club grid map (August 2026) are PDFs, not opened; a grid map could make reported catches placeable by grid square, which would be worth asking about.
- **Area:** Tutukaka, just north of the study box. Places are not given.
- **Photos:** resized crops on the Rocketspark CDN, e.g. `https://pictures.rs-cdn.com/CF-…/trim=…,fit=cover,width=337,height=337,…/ace5….jpg`. EXIF almost certainly stripped.
- **robots.txt** (`https://www.wdsac.co.nz/robots.txt`): `User-agent: *`, disallows `/admin`, `/users`, `/tools`, `/*.php$` and shop checkout paths, then `Allow: /`. No AI rules. Leader board and gallery may be crawled.
- **Terms:** only shop terms (`/shop/terms/`), which say nothing about copying, scraping or reuse; footer "Copyright © 2026". Copyright holder presumably Whangarei Deep Sea Anglers Club Inc. No licence.
- **Verdict: ask first** (low value as it stands). No places on the public pages. If the club would share grid-square catch records, that is a better request than crawling.

## 7. Marsden Cove Fishing Club

- **Pages:** `https://www.marsdencovefishingclub.co.nz/`, `/leaderboards`, event pages e.g. `/events/chics-the-chicks-2027`, `/events/offshore-boats-nz-small-boats-2027`.
- **What is there:** an Angler of the Year top-10 of names and points (no species, dates or places), with the full tally in an Excel file (`uploads/Angler of the year 2026-27.xlsx`, not downloaded). Event pages give dates, target species and rules booklets but no past results.
- **Area:** Marsden Cove, at the Whangārei Harbour entrance. The club's events ("Chics @ The Chicks") fish the Hen and Chickens, but no places are published.
- **Photos:** placeholders only (`/uploads/images/placeholder-4.jpg`).
- **robots.txt:** none (`/robots.txt` returns 404), so no restrictions are stated.
- **Terms:** none found; footer "© 2023, all rights reserved."
- **Verdict: ask first** (low value). Nothing placeable is public. A direct request for weigh-in records with places would be the useful ask.

## 8. Mangawhai Boating & Fishing Club

- **Pages:** `https://www.mangawhaiboatingfishing.co.nz/`; sitemap lists `/club-events`, `/blog`, `/club-members`, `/groups`, `/shop`.
- **What is there:** almost nothing for this purpose. The blog is empty ("Check back soon"). No results, weigh-ins or catch reports found. A local paper reported the club's competitions moving to measure-and-release with points, so records may exist off-site.
- **Area:** Mangawhai, the south edge of the study area.
- **Photos:** on the Wix CDN (`static.wixstatic.com`), normally resized.
- **robots.txt** (`https://www.mangawhaiboatingfishing.co.nz/robots.txt`, Wix default): `User-agent: *` / `Allow: /` / `Disallow: *?lightbox=`; PetalBot blocked. No AI rules.
- **Terms:** none found; footer "©2023 Mangawhai Boating & Fishing Club."
- **Verdict: ask first** (little there). Worth one email asking whether competition results with places are kept.

## 9. NZ Sport Fishing Council (NZSFC)

- **Pages:** `https://www.nzsportfishing.co.nz/monthly-club-reports/` (index of monthly club reports, May 2023 to October 2026, mostly PDFs such as `/wp-content/uploads/2026/10/NZSFC_32_Oct-Report_fv_web.pdf`; some on OneDrive). National tournament results PDFs, e.g. `/wp-content/uploads/2020/03/final-results-2019-.pdf`. Club listings: WDSAC `?p=363`, Mangawhai `?p=259`, Marsden Cove `?p=274`.
- **What is there:** unknown in detail, because the reports are PDFs and were not opened. They are newsletter-style club reports from affiliated clubs, which may include the three local clubs.
- **Area:** national; local clubs included.
- **Photos:** inside PDFs; not judged.
- **robots.txt** (`https://www.nzsportfishing.co.nz/robots.txt`, Cloudflare-managed): `User-agent: *` / `Content-Signal: search=yes,ai-train=no,use=reference` / `Allow: /`. `ClaudeBot`, `GPTBot`, `CCBot`, `Google-Extended`, `anthropic-ai` and many others: `Disallow: /`.
- **Terms** (`https://www.nzsportfishing.co.nz/terms-conditions/`): material is "the copyright of NZSFC Inc unless otherwise indicated"; "It may be reproduced free of charge in any format or medium" "provided it is used for noncommercial, informational purposes only", and "The source of the material must be identified". Third-party material needs its owner's permission. Also: "You must ask permission to link directly to pages hosted on this site." Nothing on scraping or AI.
- **Verdict: ask first.** The licence fits a non-commercial project, but the project's link-back needs permission, club reports are third-party material, and the robots file blocks AI crawlers. One email to NZSFC could settle all three.

## 10. Fishmeister charters (Mangawhai)

- **Pages:** `https://www.fishmeister.co.nz/news/`, with posts such as `https://www.fishmeister.co.nz/tara-iti-spring-snapper/` (22 October 2026), `/ollies-15lb-snapper/` (1 June 2026), `/great-autumn-fishing-mokes/` (26 May 2024), `/from-surfing-to-fishing/` (9 June 2022), back to April 2021. Also `/locations/`.
- **What is there:** short catch posts with photos, a few a year. They name the Hen & Chicks, Sail Rock and the Mokohinau Islands (the last outside the box); species snapper and kingfish, with weights. Example: "a trip to the Hen & Chicks".
- **Area:** this area in part (Mangawhai, Sail Rock, Hen and Chickens); also the outer Hauraki Gulf.
- **Photos:** on the site's own WordPress uploads, e.g. `https://www.fishmeister.co.nz/wp-content/uploads/2026/10/Scotties-snapper-225x300.jpg`, `.../2022/11/Dave-at-Sail-Rock-300x225.jpg`, `.../2017/04/20170320_130557-1024x576.jpg`. The size suffixes are WordPress thumbnails; WordPress normally also keeps the full upload at the name without the suffix. The `20170320_130557` name is a phone-camera filename, so some originals may still hold EXIF. Not fetched.
- **robots.txt** (`https://www.fishmeister.co.nz/robots.txt`): `User-agent: *` / `Disallow: /wp-admin/` / `Allow: /wp-admin/admin-ajax.php` / `Disallow: /author/`. No AI rules.
- **Terms** (`https://www.fishmeister.co.nz/terms/`): booking and cancellation conditions only; nothing on copyright or reuse. Footer "© Fishmeister 2017 - 2026".
- **Verdict: ask first.** Small but local, with possibly original photos. A one-person business; ask before fetching any full-size image.

## 11. FishingBooker charter reports

- **Pages:** `https://fishingbooker.com/reports/destination/nz/tutukaka`, `https://fishingbooker.com/reports/charter/39877`, and destination pages for Whangārei, Marsden Point and Mangawhai Heads (seen in search results). Local operators listed there include Audacious Charters (Marsden Cove), E C Fishing Charters (Marsden Cove), Snap Fishing Ventures and Eco Adventures (Mangawhai).
- **What is there:** **could not read.** WebFetch and a plain request both got HTTP 403 with a Cloudflare "Just a moment..." challenge. Search snippets describe dated charter reports with photos.
- **Photos:** could not read.
- **robots.txt** (`https://fishingbooker.com/robots.txt`): `User-agent: *` disallows only booking, ajax, `/ci/*`, `/api/*` and `/next-api/*` paths (in every language prefix), with `Crawl-delay: 15`. `/reports/` is not disallowed. A separate group for SemrushBot, Amazonbot, AhrefsBot and others applies its own rules. No ClaudeBot or GPTBot group.
- **Terms:** could not read (`/terms` returned 404; the real address was not found).
- **Verdict: ask first.** Robots permits `/reports/`, but the bot challenge shows they do not want automated readers, and the terms are unread. A commercial platform; ask before anything.

## 12. NZ Fishing Competition (fishingcomp.co.nz)

- **Pages:** `https://www.fishingcomp.co.nz/` (linked from fishing.net.nz as "NZ Fishing Competition").
- **What is there:** **could not read** (HTTP 403, Cloudflare challenge). Whether entries carry places, dates or photos is unknown.
- **robots.txt** (`https://www.fishingcomp.co.nz/robots.txt`): `User-agent: *` / `Allow: /`.
- **Terms:** could not read.
- **Verdict: ask first.** Could be asked about in the same email to Fishing.net.nz Ltd.

## 13. LINZ NZ Place Names (NZGB), the NZ Gazetteer

- **Pages:** layer 51681, `https://data.linz.govt.nz/layer/51681-nz-place-names-nzgb/`. The search front end at `https://gazetteer.linz.govt.nz/` is a JavaScript app; its text could not be read.
- **What is there:** about 54,700 official and unofficial place names as points, including bays, islands, harbours and undersea features, out to the continental shelf; last updated 18 November 2026. Whether small local marks (Sail Rock, Three Mile Reef, the Fairway Buoy) are in it was not checked. For turning report place names into positions, with a local list for marks it lacks.
- **Area:** all of New Zealand.
- **robots.txt** (`https://data.linz.govt.nz/robots.txt`): `User-agent: *` disallows `/admin/`, `/my/`, `/search/`, `/services`, layer `/data/` and `/history/` sub-pages and download paths. Data are meant to be taken through the export or the APIs, not crawled. `gazetteer.linz.govt.nz/robots.txt` has no rules.
- **Terms:** "Creative Commons Attribution 4.0 International"; attribute Land Information New Zealand, via LINZ Data Service. Commercial use is allowed. The project already uses a LINZ API key for other layers.
- **Verdict: allowed.** An open licence and an official API; attribute LINZ.

## 14. Papers Past (historic newspapers)

- **Pages:** e.g. `https://paperspast.natlib.govt.nz/newspapers/NA19480312.2.82` ("Exciting week at Hen Islands", Northern Advocate, 12 March 1948, going by the URL and search title), `.../NA19480316.2.22`, `.../NA19361202.2.85`.
- **What is there:** digitised historic newspapers, including the Northern Advocate's game-fishing and fishing news from the 1930s and 1940s. **Could not read:** the site and its `robots.txt` sit behind Incapsula bot protection, which returned a challenge page with `noindex,nofollow`.
- **Terms:** could not read (`https://paperspast.natlib.govt.nz/copyright` returned an empty page). From search-result summaries only, not verified: the National Library does not own copyright in the newspapers; an open dataset of 1839–1903 issues is out of copyright; Papers Past data through the DigitalNZ API is restricted to non-commercial use. 1930s–1940s items may still be in copyright.
- **Verdict: ask first.** Useful only as history (old marks and seasons). Read the terms in a browser first; the DigitalNZ API, not crawling, would be the way in.

## 15. Global Fishing Watch

- **Pages read:** `https://globalfishingwatch.org/our-apis/documentation`, `.../docs/license-rate-limits`, `.../docs/v3/general-api-doc/key-concepts`, `.../docs/v3/general-api-doc/data-caveats`, `https://globalfishingwatch.org/faqs/can-i-use-global-fishing-watch-apis-for-commercial-purposes/`, and the 31 May 2024 release note "New Vessel Detections Dataset in APIs".
- **What public data covers this area:** global datasets, so the box is covered in principle:
  - `public-global-fishing-effort`: AIS apparent fishing activity (4Wings API), 2012 to about 96 hours ago. It is built only from vessels "identified as known or possible commercial fishing vessels", and a vessel needs more than 500 positions a year to be classified.
  - `public-global-sar-presence`: Sentinel-1 SAR vessel detections, 2017 to 5 days ago, described as industrial vessels. These include vessels not broadcasting AIS (the "dark vessels" API).
  - `public-global-sentinel2-presence`: Sentinel-2 optical detections at 10 m, 2019 to about 96 hours ago.
  - Also AIS presence, encounter, loitering, fishing and port-visit events, and vessel identity.
- **Access:** REST API with SDKs for R (`gfwr`) and Python. Each request needs an API token from a registered account; GFW "may reject registration requests at its discretion". Up to five tokens per user, not to be shared. The pages read do not say who may register. Rate limits: "50,000 requests per day" and "1,500,000 requests per month", per user; beyond that, HTTP 429.
- **Licence and attribution:** "available for noncommercial use only in accordance with the CC BY-NC 4.0 license"; "each dataset carries its own license and restrictions" (no dataset-specific licence was found for fishing effort or SAR). Attribution: "Powered by Global Fishing Watch." linked to globalfishingwatch.org, carried on to downstream users. The FAQ says the APIs are "free to use for non-commercial purposes", "including for academic research". Commercial use needs a separate licence.
- **Small vessels:** for SAR, "we miss most vessels under 15 m in length", and detection under 25 m depends on sea state and wind. Nothing is classified "within 1 km of shore", and "Sentinel-1 SAR data does not sample most of the open ocean" (whether this box is imaged often was not checked). For Sentinel-2, "Vessels under 15 m may not be visually identifiable." AIS-based effort covers commercial fishing vessels only. Where pleasure craft are many, some "might be misclassified as fishing vessels".
- **Would 5–10 m recreational boats appear?** Almost certainly not. They are below the SAR and optical limits, mostly inside or near the 1 km shore exclusion, rarely carry AIS, and are left out of the fishing-effort layer by design.
- **robots.txt** (`https://globalfishingwatch.org/robots.txt`): `User-agent: *` / `Disallow: /wp-content/uploads/wpforms/`, then `User-agent: *` / `Disallow:` (empty). Not relevant to API use.
- **Verdict: allowed** (registration and attribution needed; non-commercial fits). Of little use for testing a recreational snapper index. At most it would show commercial fishing pressure (trawl and longline) offshore in Bream Bay and around the Hen and Chickens.

---

## Considered and excluded

| Source | Why excluded |
|---|---|
| fishing.net.nz forum; Angler's Planet forums; NZ Hunting & Shooting forums | Discussion forums, ruled out by the owner. |
| Fishbrain (`fishbrain.com/fishing-waters/…/bream-bay`) | A social network for anglers (user feeds and catches), so treated as social media. |
| Facebook pages of WDSAC, Marsden Cove club, charters | Social media, ruled out. |
| FishingReminder (`fishingreminder.com`), Windy fishing forecast (`windy.app/fishing/…`) | Forecasts and generic spot guides, not dated reports; also bite or solunar scores, which the project does not use. |
| Whangarei NZ "Fish Tutukaka" tips (`whangareinz.com`), Whangarei Online "Where to go fishing" | General guides, no dated catches. |
| Fish Tutukaka (`fishtutukaka.co.nz`) | No reports or gallery on its own site; Tutukaka coast, not the study area. |
| Eco Adventures (`ecoadventures.co.nz`) | Own site has no reports or catch gallery (robots allows `*`, crawl-delay 10). Its reports, if any, are on FishingBooker (source 11). |
| Snap Fishing Ventures, E C Fishing Charters, Audacious Charters | No own website found; they appear only on booking platforms. Nik Key's reports are covered through sources 1 and 5. |
| Tackle shops: Mangawhai Fish & Dive, Monster Fishing (Ruakākā), Hunting & Fishing Whangārei, Arthurs Emporium | No catch-report pages found on their own websites; only social media or shop listings turned up. |
| Clubs NZ national fishing tournament PDFs (`clubsnz.org.nz`) | PDFs (not opened); hosted in other regions; no sign of places. |
| 90 Mile Beach Snapper Bonanza, Doubtless Bay and Whangaroa contests | Outside the study area (Far North). |
| Northland Fish & Game "Reel Life" | Freshwater only. |
| PlaySport, Yellow, Localist, Cylex, Wanderlog, Rankers, TripAdvisor, newzealand.com listings | Directories and reviews; no catch reports. |
| WDSAC catch card, grid map, Marsden Cove AOTY spreadsheet, NZSFC report PDFs | Files; not downloaded under this task's rules. Could be read once permission is given. |
| MPI National Panel Survey of recreational fishers | Not checked. Thought to be published only in aggregate, not per trip; would need a request to MPI. |

## What to ask, if the owner approves

One email each would cover most of the useful material:

1. **Fishing.net.nz Ltd:** sources 1, 2 and 12. The best yield: two local reports a month since about 2020, plus gallery photos that may be originals.
2. **Local Matters 2005 Ltd (general manager):** source 3.
3. **NZ Sport Fishing Council:** source 9 (permission to link, and whether club reports may be read by a model).
4. **WDSAC, Marsden Cove and Mangawhai clubs:** weigh-in or grid-square catch records with places (sources 6–8). A direct data request is likely to give more than crawling.
5. **Fishmeister:** source 10, including whether full-size photos may be read for GPS.

NZ Herald / Northern Advocate (source 4) has refused this use in its robots.txt; leave it out unless NZME syndication says otherwise.