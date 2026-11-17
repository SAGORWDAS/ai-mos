# Public page indexing

The workspace is private software. Its HTML and API responses use `noindex, nofollow`; authentication remains the access control. Robots directives do not protect confidential data. Only explicitly published, currently grounded service pages are eligible for indexing.

## Connect a public domain later

1. Complete the production deployment gates and runbooks. The beta's production startup gate remains; these settings alone do not approve deployment.
2. Configure `PUBLIC_API_URL` as the real HTTPS API origin, including any proxy prefix before `/v1`. It supplies canonicals and provider callbacks. Verify generated URLs resolve through the actual proxy. Local, example and IP hosts are not accepted as public site identity.
3. Keep `PUBLIC_INDEXING_ENABLED=false` locally and on staging. Enable it only on the intended public deployment after reviewing public content.
4. Enter facts inside Brand Brain, review and publish. Inspect title, description, canonical, social metadata and robots headers on the real HTTPS page.
5. Integrations shows `{PUBLIC_API_URL}/v1/public/{workspace_id}/sitemap.xml`. Only published, grounded pages appear. Large feeds use paginated child feeds. Submit through the verified Search Console property and inspect a page URL.

Frontend `/robots.txt` permits `/api/v1/public/` and disallows other API routes. Private HTML remains noindex. Verify any other host/proxy's robots rules: crawlers need access to read noindex. Do not blanket-block public routes while expecting indexing.

Metadata uses actual approved facts and generic WebPage microdata. No invented ratings, reviews, addresses or prices. Changed brand facts withdraw affected pages and invalidate outstanding approvals; review and republish. Unchanged saves preserve publication.

Local checks establish technical foundations, not rankings. Before launch, measure real HTTPS page speed/Core Web Vitals, inspect mobile rendering, verify duplicate URLs/domain/proxy settings and Search Console crawl status. Indexing and client acquisition are not guaranteed.

References: [Google canonical guidance](https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls), [noindex](https://developers.google.com/search/docs/crawling-indexing/block-indexing), [mobile indexing](https://developers.google.com/search/docs/crawling-indexing/mobile/mobile-sites-mobile-first-indexing).
