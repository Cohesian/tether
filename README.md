# Cohesian Tether

Tether is the common bridge between K resource targets and contributor-owned
stores. Contributors expose one declarative package; they do not need a
dedicated bridge CLI.

The target remains:

$$
\tau=(\sigma,(c,d,f))
$$

The contributor protocol supplies the remaining storage relation:

$$
B_c\subseteq D_c\times S_c\times F
$$

Here, domains and stores are independent axes. Explicit bindings say which
formats from a domain are available in a store. Route inventories provide the
K selectors and any provider-controlled URI maps.

One logical resource leaf is:

$$
\rho=(v,c,d,f)
$$

It has no additional name in protocol version 1. Its query form is the target
$\tau=(\sigma,(c,d,f))$. Several stores may locate replicas of the same
resource. A resource leaf belongs to the contributor overlay and may attach to
any TLF node kind; it is not synonymous with a TLF `F` node.

The mathematical model is documented in
[`Organization/CONTRIBUTOR-STORE-RESOLUTION.md`](../../../Organization/CONTRIBUTOR-STORE-RESOLUTION.md).
K's canonical resource relation is documented in
[`k-graph/docs/RESOURCE-OVERLAY.md`](../../k-graph/docs/RESOURCE-OVERLAY.md).
The complete file contract is in
[`docs/CONTRIBUTOR-PROTOCOL.md`](docs/CONTRIBUTOR-PROTOCOL.md).
The frozen protocol v2 migration target is in
[`docs/CONTRIBUTOR-PROTOCOL-V2.md`](docs/CONTRIBUTOR-PROTOCOL-V2.md).
The identity and registration workflow is in
[`docs/CONTRIBUTOR-ONBOARDING.md`](docs/CONTRIBUTOR-ONBOARDING.md).
Consumer snapshots are defined in
[`docs/MATERIALIZATION.md`](docs/MATERIALIZATION.md).
Workspace guidance is in [`AGENTS.md`](AGENTS.md).

## Protocol versions

The released CLI currently implements protocol v1. Protocol v2 changes the
logical address to `(node, contributor, hierarchy, resource key)`, makes each
resource carry a versioned protocol and SHA-256 digest, and moves store
availability onto the resource record itself. Its specification is frozen,
but its parser and commands belong to the next implementation phase.

Until that implementation lands, the v1 examples below remain the executable
interface and must not be interpreted as v2 packages.

## Contributor package

Every contributor places `contributor.toml` at its workspace root:

```text
research/
├── contributor.toml
└── storage/
    ├── local/routes.toml
    └── google-drive/routes.toml
```

The current contributors are:

- [Research](../research/contributor.toml), with `documents`; and
- [Studio](../../studio/contributor.toml), with `scenes` and `videos`.

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
│   └── identify
├── store
│   └── list
├── pull
└── shell
```

`--output table|json|tree` changes only presentation. `--format` always means
the logical resource format such as `md`, `loci-project`, or `mp4`.

The original flat commands remain available as compatibility aliases while
the prototype migrates.

## Create a contributor

```bash
tether contributor init ../research \
  --id research \
  --domain documents \
  --format md \
  --format ipynb
```

The generated package contains `contributor.toml`, one local template store,
one binding, and an empty `storage/local/routes.toml`. Add other domains,
stores, and bindings directly in the protocol.

## Inspect and validate

```bash
tether contributor show ../research
tether contributor check ../research
tether store list ../research
```

`show` exposes the contributor identity and its independent domain, store, and
binding axes. `check` reports protocol-version compatibility before validating
the complete package. An older package requires migration; a newer package
requires an updated Tether.

## Query resources

List logical resources and the stores currently available for each target:

```bash
tether resource list ../research \
  --domain documents \
  --format md \
  --output tree
```

Every filter is optional. The same operation can select by:

- K node `--id` or `--path`;
- contributor `--domain`;
- content `--format`; or
- physical `--store`.

Because the contributor path already identifies $c$, no contributor flag is
needed inside the resource query.

Resolve matching resources directly to URIs:

```bash
tether resource resolve ../research \
  --path T-math/L-division/F-01-introduction \
  --format md \
  --output json
```

Omit the selector to resolve a whole domain or contributor inventory. The
result groups all physical store locations under each logical resource; it
does not download or mutate content.

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
