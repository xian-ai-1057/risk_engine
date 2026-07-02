# Design reference

Drop the Claude Design export here:

```
web/design/風險分析Demo.dc.html
```

This is the **visual source of truth** for the interface. The Claude Design MCP
could not authenticate in the build session, so the front-end under
`web/static/` was implemented against the engine's **data contract** (see the
approved plan) with a clean default layout.

Once `風險分析Demo.dc.html` is present, its layout / components / colors /
typography should be reflected into `web/static/index.html` + `styles.css` to
match the mockup pixel-for-pixel. The data-binding (which engine field feeds
which element) does not change — only the presentation.
