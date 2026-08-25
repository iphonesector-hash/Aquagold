# Vendored browser dependencies

These exact, immutable browser builds are served from AquaGold itself so the field app does not depend on third-party CDNs at startup.

| Package | Version | Upstream |
|---|---:|---|
| Tailwind browser runtime | 3.4.17 | tailwindlabs/tailwindcss |
| Alpine.js | 3.14.9 | alpinejs/alpine |
| Leaflet | 1.9.4 | Leaflet/Leaflet |
| Chart.js | 4.4.7 | chartjs/Chart.js |
| html2canvas | 1.4.1 | niklasvh/html2canvas |
| Vazirmatn | 33.003 | rastikerdar/vazirmatn |

Upstream license texts are stored in `vendor/licenses/`.
Run `sha256sum -c vendor/SHA256SUMS` from the repository root to verify every runtime asset.
