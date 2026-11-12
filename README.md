# RBT-Public

Publicly accessible location for RBT published styles.

## Layout

- `current-release/styles/<STYLE>/`: the latest published release.
- `RBT_<x>_<y>_<z>/style/<STYLE>/`: each published release, for example `RBT_2_1_0/style/`.

Each style folder holds `style.json`, its sprites, and for the Maki-based styles (BROWN, GRAY,
LIGHT) the iconset and its `LICENSE.txt` and `README.txt`. `style.json` is set up for
TileServer GL: its sources are `mbtiles://{RBT}` and `mbtiles://{TERRAIN}`, the sprite is
`{styleJsonFolder}/sprite`, and glyphs are `{fontstack}/{range}.pbf`.

## Publishing a release

After a styles release, run the **Publish styles** workflow with the release version:

```bash
gh workflow run publish-styles.yml -R ReleasableBasemapTiles/RBT-Public -f version=2.1.0
```

It copies the release into `RBT_<x>_<y>_<z>/style/`, replaces `current-release/styles/` (unless
`update_current` is false), and opens a pull request to review and merge.
