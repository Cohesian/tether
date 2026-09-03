# Contributor protocol v2

Status: **frozen for implementation**

This document defines Tether's target contributor package. The current CLI
still implements protocol v1; protocol v2 becomes executable in the next
implementation phase. During migration, Tether must read both versions and
must never silently reinterpret one as the other.

The K-side authority is
[`RESOURCE-CONTRACT-V2.md`](../../k-graph/docs/RESOURCE-CONTRACT-V2.md).

## 1. Address

A resource query uses:

$$
a=(\sigma,c,H,p),
$$

where:

- $\sigma$ selects a K node by UUID, rooted path, or both;
- $c$ is the contributor id;
- $H=(h_1,\ldots,h_n)$ is a non-empty hierarchy path; and
- $p$ is a resource key local to $(\sigma,c,H)$.

The immutable logical identity is:

$$
\bar a=(\operatorname{id}(v),c,H,p).
$$

The protocol id and SHA-256 digest describe the accepted resource. Stores
describe where the contributor currently exposes it.

## 2. Package shape

One package describes one contributor:

```text
research/
├── contributor.toml
└── storage/
    ├── documents/
    │   └── resources.toml
    └── media/
        └── videos/
            └── resources.toml
```

The physical content may live beside these inventories or in remote stores.
The inventory hierarchy is a semantic projection and is not a copy of K's
graph.

## 3. Contributor descriptor

The v2 `contributor.toml` declares identity, stores, and one inventory per
hierarchy:

```toml
version = 2

[contributor]
id = "research"

[stores.local]
kind = "directory"
enabled = true
origin = "."

[stores.github]
kind = "remote"
enabled = true
origin = "https://raw.githubusercontent.com/Cohesian/research/main"

[stores.google-drive]
kind = "remote"
enabled = false

[stores.youtube]
kind = "publication"
enabled = true

[[inventory]]
hierarchy = ["documents"]
path = "storage/documents/resources.toml"

[[inventory]]
hierarchy = ["media", "videos"]
path = "storage/media/videos/resources.toml"
```

Rules:

- `version` is exactly `2`.
- `contributor.id` must match the admitted K contributor id.
- each `stores.<id>` key is unique inside the package;
- every inventory hierarchy is non-empty and unique;
- inventory paths are package-relative and cannot escape the package;
- credentials and tokens are never descriptor fields; and
- a disabled store remains declarable but does not participate in ordinary
  discovery.

Protocol v2 removes global domain-format bindings. Availability is declared
on each resource, where it can accurately differ by store.

## 4. Hierarchy inventory

Each `resources.toml` file represents exactly one contributor hierarchy. Its
header must agree with the corresponding `[[inventory]]` declaration:

```toml
version = 2
contributor = "research"
hierarchy = ["documents"]

[[resource]]
node_id = "ff647a5d-44f0-42af-9f01-abcadd04fb37"
path = "T-math/L-division/F-01-introduction"
key = "md"
protocol = "markdown-file@1"
sha256 = "7e40c9a693f4c3b118ed77c250f0dc037f291f2141f438abe7bda7e270e74b13"
locations = [
  { store = "local", relation = "exact", location = "storage/documents/local/T-math/L-division/F-01-introduction.md" },
  { store = "github", relation = "exact", uri = "https://raw.githubusercontent.com/Cohesian/research/main/storage/documents/local/T-math/L-division/F-01-introduction.md" },
]
```

Every `[[resource]]` record is self-contained. The flat `locations` array is
used deliberately: its entries belong visibly to that resource and do not
depend on the position of later TOML table headers.

### Required fields

| Field | Meaning |
|---|---|
| `node_id` | immutable K UUID |
| `key` | resource key $p$ |
| `protocol` | versioned resource protocol $q$ |
| `sha256` | canonical digest $z$ under $q$ |
| `locations` | zero or more contributor-owned store locations |

### Optional fields

| Field | Meaning |
|---|---|
| `path` | current rooted K path, used as a checked assertion and readable selector |
| `produced_by` | non-authoritative production provenance |

`node_id` is required even when `path` is present. Moving a K node changes the
path assertion, not resource identity. The combination:

```text
(node_id, contributor, hierarchy, key)
```

must be unique across the contributor package.

The inventory's `protocol` and `sha256` must equal K's accepted record for the
same address. A contributor may retain unaccepted work elsewhere, but it must
not expose that work as an accepted inventory record.

## 5. Locations

Each location names a declared `store` and a `relation`.

### Exact location

```toml
{ store = "local", relation = "exact", location = "storage/documents/local/..." }
```

or:

```toml
{ store = "github", relation = "exact", uri = "https://raw.githubusercontent.com/..." }
```

An exact location asserts that retrieving its bounded resource and applying
the declared protocol yields the resource's `sha256`.

### Publication location

```toml
{ store = "youtube", relation = "publication", uri = "https://www.youtube.com/watch?v=..." }
```

A publication may be transcoded or otherwise transformed by its host. It is
addressable and composable but cannot satisfy byte equality merely because it
was produced from the accepted resource.

Tether must report the relation in every resolved result. A consumer may ask
for publications, exact replicas, or both, but cannot silently treat one as
the other.

## 6. Resource protocol interface

A registered protocol provides these operations:

```text
validate(location) -> diagnostics
members(location)  -> ordered logical member set
digest(location)   -> sha256
describe(location) -> consumer-facing shape
```

For remote locations, `digest` may require materialization. URI resolution by
itself does not prove integrity.

Protocol ids follow:

```text
<name>@<positive-integer-version>
```

Changing resource boundaries, required members, canonicalization, or digest
rules requires a new protocol version.

## 7. Canonical SHA-256

### File resources

For a file protocol, the digest is SHA-256 over the exact file bytes:

$$
z=\operatorname{SHA256}(b_0b_1\cdots b_n).
$$

Tether performs no newline, Unicode, JSON, notebook, or media normalization.
Editing metadata or line endings therefore changes the digest.

### Tree resources

For a bounded directory or compound protocol:

1. determine members according to the protocol;
2. reject symbolic links and paths escaping the resource boundary;
3. express each member as a protocol-relative POSIX path;
4. normalize path text to Unicode NFC;
5. sort paths by their UTF-8 byte sequence;
6. hash each member's exact bytes; and
7. hash the canonical manifest.

Each manifest record is encoded as UTF-8:

```text
<path> NUL <decimal-byte-length> NUL <lowercase-file-sha256> LF
```

The tree digest is SHA-256 over the concatenated manifest records. File mode,
owner, timestamps, ZIP metadata, and compression settings are excluded.

Ordinary ZIP bytes are not a canonical resource digest because entry order,
timestamps, permissions, and compression may change without changing the
logical resource.

All tree protocols ignore `.DS_Store`, `.git/`, `.venv/`, `__pycache__/`, and
`*.pyc`. A `.env` member is invalid rather than ignored. Other regular files
are included unless the concrete protocol narrows the boundary.

## 8. Initial protocol registry

### `markdown-file@1`

- Shape: one UTF-8 Markdown file.
- Boundary: the selected `.md` file only.
- Digest: exact file bytes.
- Consumer semantics: Markdown with no contributor-managed companion tree.

### `markdown-bundle@1`

- Shape: one `.md` entrypoint plus an optional sibling directory with the same
  stem.
- Boundary: entrypoint and every regular file below that companion directory.
- Logical member names: `document.md` for the entrypoint and
  `assets/<relative-path>` for companion members.
- Digest: canonical tree manifest.
- Consumer semantics: render `document.md`; resolve its relative companion
  references from `assets/` according to the materialized layout.

For example:

```text
F-04-experimental-laboratory.md
F-04-experimental-laboratory/
├── condition-comparison.png
└── energy-comparison.png
```

forms one `markdown-bundle@1` resource.

### `jupyter-notebook-file@1`

- Shape: one `.ipynb` JSON file.
- Boundary: the selected file only.
- Digest: exact notebook bytes.
- Consumer semantics: a notebook source; static, interactive, or hybrid
  rendering is a consumer projection rather than part of this protocol.

### `mp4-file@1`

- Shape: one MP4 file.
- Boundary: the selected file only.
- Digest: exact MP4 bytes.
- Consumer semantics: directly playable media when the location is exact; a
  publication URI may be embedded according to consumer policy.

### `python-project@1`

- Shape: a bounded Python project directory.
- Required member: `pyproject.toml`.
- Boundary: all regular project members after global exclusions.
- Digest: canonical tree manifest.
- Consumer semantics: source project; execution remains explicit and outside
  ordinary URI resolution.

### `loci-project@1`

- Shape: a bounded Loci project directory.
- Required members: `pyproject.toml`, `loci.toml`, and `scene.toml`.
- Boundary: all regular project members after global exclusions; generated
  render output under `media/` is excluded.
- Digest: canonical tree manifest.
- Consumer semantics: reproducible animation source; its rendered video is a
  separate resource.

## 9. K expression and contributor expression

For this contributor record:

```toml
version = 2
contributor = "research"
hierarchy = ["documents"]

[[resource]]
node_id = "ff647a5d-44f0-42af-9f01-abcadd04fb37"
path = "T-math/L-division/F-01-introduction"
key = "md"
protocol = "markdown-file@1"
sha256 = "7e40c9a693f4c3b118ed77c250f0dc037f291f2141f438abe7bda7e270e74b13"
locations = []
```

K contains only the accepted projection:

```yaml
contributions:
  c_research:
    h_documents:
      r_md:
        protocol: markdown-file@1
        sha256: 7e40c9a693f4c3b118ed77c250f0dc037f291f2141f438abe7bda7e270e74b13
```

The join is valid only when contributor, hierarchy, resource key, protocol,
and digest agree for the same K node UUID.

## 10. Tether responsibilities

Protocol v2 requires Tether to:

- parse and validate contributor descriptors and hierarchy inventories;
- reject duplicate resource addresses;
- interpret `c_`, `h_`, and `r_` K keys;
- validate protocol ids and SHA-256 syntax;
- calculate file and tree digests;
- compare contributor records with accepted K records;
- resolve exact and publication locations without conflating them;
- query by UUID, rooted path, hierarchy prefix, resource key, protocol, store,
  or relation; and
- preserve protocol v1 as an explicit compatibility adapter during migration.

Tether does not upload resources, mutate K, accept proposals, or decide how a
consumer composes Markdown, notebooks, images, and video.

## 11. Consumer projection

Materialization and presentation remain downstream choices. A consumer may
compose several resources attached to the same K node—for example a Markdown
bundle with a YouTube publication—without modifying either resource's logical
identity.

An interactive notebook render, static notebook render, HTML document, or
directory layout is a derived representation. The accepted source remains the
resource identified by its protocol and digest.

## 12. Version transition

Protocol v1 uses `(node, contributor, domain, format)` plus independent
bindings and route inventories. Protocol v2 uses:

```text
(node, contributor, hierarchy, resource key)
    -> protocol + digest + resource-local locations
```

The v2 implementation must:

1. detect the descriptor version before parsing;
2. keep v1 behavior unchanged for v1 packages;
3. never synthesize an accepted digest for v1 data;
4. expose v1 records as legacy descriptors, not pretend they are v2; and
5. remove v1 support only after K and every active contributor have migrated.
