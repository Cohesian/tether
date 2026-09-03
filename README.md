# Cohesian Tether

Tether is the common bridge between K resource targets and contributor-owned
stores. Contributors expose one declarative package; they do not need a
dedicated bridge CLI.

Protocol v2 addresses one resource as:

$$
a=(\sigma,c,H,p),
$$

where $\sigma$ selects the K node, $c$ is the contributor, $H$ is an
arbitrary-depth hierarchy, and $p$ is a resource key. K accepts a versioned
protocol and SHA-256 digest for that address. The contributor supplies its
physical locations:

$$
L_c(\bar a)=\{s\mapsto\lambda_s\}.
$$

An exact location must reproduce the accepted digest under the resource
protocol. A publication location, such as a transcoded YouTube video, remains
addressable without claiming byte equality.

Protocol v1 remains supported through its original target:

$$
\tau=(\sigma,(c,d,f)).
$$

Version detection is explicit; Tether never silently treats a v1 format as a
v2 resource key.

The mathematical model is documented in
[`Organization/CONTRIBUTOR-STORE-RESOLUTION.md`](../../Organization/CONTRIBUTOR-STORE-RESOLUTION.md).
K's v2 resource relation is documented in
[`k-graph/docs/RESOURCE-CONTRACT-V2.md`](../k-graph/docs/RESOURCE-CONTRACT-V2.md).
The v2 contributor contract is in
[`docs/CONTRIBUTOR-PROTOCOL-V2.md`](docs/CONTRIBUTOR-PROTOCOL-V2.md).
The implemented v1 contract remains in
[`docs/CONTRIBUTOR-PROTOCOL.md`](docs/CONTRIBUTOR-PROTOCOL.md).
The identity and registration workflow is in
[`docs/CONTRIBUTOR-ONBOARDING.md`](docs/CONTRIBUTOR-ONBOARDING.md).
Consumer snapshots are defined in
[`docs/MATERIALIZATION.md`](docs/MATERIALIZATION.md).
Workspace guidance is in [`AGENTS.md`](AGENTS.md).

## Protocol versions

Tether 0.3.0 reads both protocol v1 and v2 packages. Protocol v2 changes the
logical address to `(node, contributor, hierarchy, resource key)`, makes each
resource carry a versioned protocol and SHA-256 digest, and moves store
availability onto the resource record itself. Protocol v1 remains an explicit
compatibility path while existing contributors migrate.

## Contributor package

Every contributor places `contributor.toml` at its workspace root:

```text
research/
├── contributor.toml
└── storage/
    ├── documents/resources.toml
    └── media/videos/resources.toml
```

The current contributors are:

- [Research](../research/contributor.toml), with `documents`; and
- [Studio](../studio/contributor.toml), with `scenes` and `videos`.

TOML keeps the prototype dependency-free. The protocol itself could later be
encoded as YAML or JSON without changing its relations.

## Install

From this directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

## Command model

```text
tether
├── contributor
│   ├── init
│   ├── show
│   └── check
├── resource
│   ├── list
│   ├── resolve
│   ├── identify
│   ├── digest
│   └── verify
├── store
│   └── list
├── pull
└── shell
```

`--output table|json|tree` changes only presentation. Protocol v2 queries use
`--hierarchy`, `--key`, `--protocol`, `--store`, and `--relation`. The old
`--domain` and `--format` selectors remain available for v1 packages.

The original flat commands remain available as compatibility aliases while
the prototype migrates.

## Create a contributor

```bash
tether contributor init ../research \
  --id research \
  --hierarchy documents
```

The generated v2 package contains `contributor.toml`, one local store, and an
empty `storage/documents/resources.toml`. A nested hierarchy uses slash
notation, for example `--hierarchy media/videos`.

To scaffold a legacy package explicitly:

```bash
tether contributor init ../legacy \
  --id legacy \
  --protocol-version 1 \
  --domain documents \
  --format md
```

## Inspect and validate

```bash
tether contributor show ../research
tether contributor check ../research
tether store list ../research
```

`show` exposes contributor identity, hierarchy inventories, and stores for v2;
it preserves domains and bindings for v1. `check` validates compatibility,
structure, uniqueness, and every available local exact digest.

## Query resources

List logical resources and the stores currently available for each target:

```bash
tether resource list ../research \
  --hierarchy documents \
  --key md \
  --output tree
```

Every filter is optional. The same operation can select by:

- K node `--id` or `--path`;
- hierarchy prefix `--hierarchy`;
- resource `--key` or `--protocol`;
- exact/publication `--relation`; or
- physical `--store`.

Because the contributor path already identifies $c$, no contributor flag is
needed inside the resource query.

Resolve matching resources directly to URIs:

```bash
tether resource resolve ../research \
  --path T-math/L-division/F-01-introduction \
  --hierarchy documents \
  --key md \
  --output json
```

Omit the selector to resolve a whole domain or contributor inventory. The
result groups all physical store locations under each logical resource; it
does not download or mutate content.

Calculate or verify a protocol-defined digest before registering a resource:

```bash
tether resource digest ./paper.md --protocol markdown-file@1
tether resource verify ./paper.md \
  --protocol markdown-file@1 \
  --sha256 <accepted-digest>
```

Reverse projection searches every enabled binding in the contributor package:

```bash
tether resource identify ../research --uri <uri>
```

The lower-level `resolve`, `resolve-many`, and descriptor-based `identify`
commands remain available for callers that already hold explicit targets and
store descriptors.

## Materialize a consumer snapshot

Research documents from a local or raw-GitHub store can be materialized into
their K rooted-path tree:

```bash
tether pull ../research \
  --domain documents \
  --format md \
  --store github \
  --into ./site-content/research \
  --layout dir
```

Provider-controlled links such as YouTube are projected into a URI map without
pretending that the page itself is an MP4 download:

```bash
tether pull ../../studio \
  --domain videos \
  --format mp4 \
  --store youtube \
  --into ./site-content/videos \
  --layout map
```

Both layouts write `tether-manifest.json`. `dir` also copies or downloads the
selected files. Pull always requires one explicit store so replicated
locations cannot be confused with separate resources.

See [`docs/MATERIALIZATION.md`](docs/MATERIALIZATION.md) for the exact snapshot
contract.

## Contributor-scoped shell

```bash
tether shell ../research
```

The prompt retains only the contributor path for that process. It supports
`show`, `check`, `stores`, `resources`, `resolve`, `identify`, and `pull`; it
does not create hidden persistent state.

## Strategies

- `template` forms local, GitHub, or other deterministic URIs from fields such
  as `{path}` and `{format}`.
- `map` reads explicit provider URIs or package-relative directory locations
  from a binding inventory.

Resolution remains a pure address operation. `pull` is an explicit,
consumer-directed materialization step built on top of that projection.

Tether remains a read and projection bridge by default. Its opt-in `pull`
operation creates consumer-owned snapshots; it does not change contributor
storage or K. A future proposal surface may prepare or submit
resource-registration requests, but K remains the owner of validation and
acceptance.

For deterministic bindings, the contributor, domain, and store are already
localized. Resolution can therefore be as small as `(path, format) -> URI` or
`(id, format) -> URI`. Those categories remain part of logical identity even
when the physical path omits them.

## Validate the tool

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 \
  python -m unittest discover -s tests
```

## License

Tether is available under the [MIT License](LICENSE).
