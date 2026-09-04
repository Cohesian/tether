# Materialization layouts

URI resolution and content materialization are separate Tether operations.

`resource resolve` is a pure query: it projects logical resources to physical
store URIs without writing or downloading anything. `pull` explicitly consumes
that projection and creates a consumer-owned snapshot.

## Common input

Every pull selects one contributor package and exactly one store:

```bash
tether pull <contributor> \
  --hierarchy <hierarchy> \
  --key <resource-key> \
  --store <store> \
  --into <destination> \
  --layout <dir|map>
```

For example:

```bash
tether pull <contributor> \
  --hierarchy media \
  --key mp4 \
  --store <store> \
  --into <destination> \
  --layout <dir|map>
```

The node selector remains optional. Omitting `--id` and `--path` selects every
matching resource exposed by that contributor-store slice.

One explicit store is mandatory. This prevents replicas from different stores
from being downloaded or represented as if they were distinct resources.

## `dir`

`dir` materializes content at the K rooted path. File resources append their
logical format:

```text
<destination>/
├── T-math/
│   └── L-division/
│       └── E-01-introduction.md
└── tether-manifest.json
```

The location rule is:

$$
\operatorname{location}_{\mathrm{dir}}(\rho)
=
\operatorname{path}(v)\mathbin{+}\texttt{.}\mathbin{+}f
$$

For a package-local directory resource, the resource already owns its leaf
directory, so the location is instead:

$$
\operatorname{location}_{\mathrm{dir}}(\rho)
=
\operatorname{path}(v)
$$

Tether copies that directory recursively. For example, a Research
`media/loci-project` resource produced by Studio materializes its
`pyproject.toml`, `loci.toml`, `scene.toml`, entrypoint, and local dependency
closure together.

If an inventory has no rooted path, Tether uses the node UUID as a flat stem.
A collision is rejected rather than silently overwriting another logical
resource.

### Protocol v2 directory layout

Version 2 preserves the resource key explicitly:

```text
<destination>/<K rooted path>/<resource key><protocol suffix>
```

For example, `r_md` under `markdown-file@1` becomes:

```text
<destination>/T-math/L-division/E-01-introduction/md.md
```

Tree resources use the key as their directory. A `markdown-bundle@1` is
materialized in its canonical consumer shape:

```text
<destination>/<K rooted path>/md/
├── document.md
└── assets/
    └── ...
```

Python and Loci projects retain their protocol-relative project members below
the resource-key directory. Protocol exclusions prevent caches, local virtual
environments, generated Loci media, and `.DS_Store` files from entering that
snapshot.

Publication locations cannot use `dir`: a YouTube URI is not presented as the
accepted MP4 byte stream. Use `map` for publication projections.

The current transfer adapters accept:

- package-local `file:` URIs addressing files or directories;
- `http:` URIs; and
- `https:` URIs produced by deterministic template stores such as raw GitHub.

Mapped remote stores are not assumed to be downloadable. A YouTube page or a
Google Drive sharing URL may identify content without being a direct byte
stream, so those stores use `map` unless a future store adapter defines an
explicit transfer protocol.

## `map`

`map` performs no content transfer. It writes only
`tether-manifest.json`, preserving the selected resource targets and their
resolved source URIs. It fits provider-controlled locations such as YouTube or
Google Drive:

```json
{
  "version": 2,
  "contributor": "research",
  "layout": "map",
  "store": "youtube",
  "resources": [
    {
      "target": {
        "selector": {
          "id": "<uuid>",
          "path": "T-example/L-example/E-example"
        },
        "contribution": {
          "contributor": "research",
          "hierarchy": ["media"],
          "key": "mp4"
        }
      },
      "protocol": "mp4-file@1",
      "sha256": "<accepted-sha256>",
      "locations": [
        {
          "store": "youtube",
          "relation": "publication",
          "uri": "https://www.youtube.com/watch?v=..."
        }
      ]
    }
  ]
}
```

## The common manifest

Both layouts produce `tether-manifest.json`.

- `map` resources retain their source `locations` only.
- `dir` resources additionally contain `materialized.location` and the
  resulting local file URI.
- v2 resources retain `protocol`, `sha256`, and each location's `relation`.

The manifest is a snapshot for the consumer, not a new contributor protocol
and not an accepted K graph revision. Website can combine it with an
independently obtained K snapshot, choose how to render local documents, and
embed mapped media URIs.

The `dir` layout contains contributed resource files or project directories
only. It mirrors their K rooted addresses, but it is not the K Directory
projection and does not recreate node YAML, TLE kinds, or graph edges.

`--force` permits replacing existing destination files or project directories
and the manifest. With no flag, Tether rejects an existing destination before
transfer.
