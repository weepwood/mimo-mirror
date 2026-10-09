# MiMo RL Mirror

This project mirrors the public website <https://mimo.xiaomi.com/rl/>.

## Source-first build

The GitHub Actions workflow downloads the original HTML, CSS, JavaScript, fonts, and the original static JSON data bundle from the page's own `data.04135c89/` directory. The upstream page's own JavaScript and chart implementation are retained rather than replaced by a separately written interface.

The static snapshots are from the latest successful workflow run. GitHub Pages cannot execute the upstream backend, but this page itself is a static build whose data is served from JSON files.

## Links

- Original: <https://mimo.xiaomi.com/rl/>
- Mirror: <https://weepwood.github.io/mimo-mirror/>
- [Workflow history](https://github.com/weepwood/mimo-mirror/actions)

## Notes

- Independent unofficial mirror; not affiliated with Xiaomi.
- The mirror job fetches the live upstream static files before deploying. If upstream paths or build hashes change, the workflow reports failures rather than silently substituting handcrafted demo data.
