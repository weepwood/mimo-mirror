# MiMo RL Mirror

This repository mirrors the public MiMo RL page at <https://mimo.xiaomi.com/rl/>.

## How the mirror is built

The GitHub Actions workflow downloads the current upstream HTML, CSS, JavaScript, and referenced static assets directly from the official page. It also saves the public JSON responses used by the original front end under `origin-data/` and injects a small fetch adapter so the original front-end code can read those snapshots from GitHub Pages, which is a static host.

The goal is to retain the original UI and interactions rather than maintain a separately designed imitation. Since GitHub Pages cannot run the original API, run data is a snapshot captured by the last successful workflow. Run **Actions → Mirror official MiMo RL website → Run workflow** to refresh it.

## Links

- Original: <https://mimo.xiaomi.com/rl/>
- Mirror: <https://weepwood.github.io/mimo-mirror/>
- [Latest workflow runs](https://github.com/weepwood/mimo-mirror/actions)

## Notes

- Independent, unofficial mirror; not affiliated with Xiaomi.
- Public source assets and API responses are fetched directly from the origin. This repository does not include private backend services.
- The mirror workflow deploys from the same successful run that fetches the source assets.
