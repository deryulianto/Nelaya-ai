# Arsitektur singkat

- **apps/api**: FastAPI dengan healthcheck, siap dikembangkan (prediksi, ingest).
- **apps/web**: Streamlit sebagai landing/portal.
- **Docker**: Dua images (api, web) → push ke GHCR via workflow.
- **Docs**: MkDocs Material → GitHub Pages.
