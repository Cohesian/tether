# Contributor onboarding

This guide introduces a protocol v2 contributor. Tether connects identities
owned by K and the contributor without collapsing them into one id.

| Identity | Example | Authority |
|---|---|---|
| K node id $v$ | UUIDv4 | K |
| K rooted path | `T-math/L-division/F-01-introduction` | Derived from K grouping |
| Contributor id $c$ | `research` | K registry + contributor package |
| Hierarchy $H$ | `documents` or `media` | Contributor, admitted by K |
| Resource key $p$ | `md`, `loci-project`, `mp4` | Contributor, admitted by K |
| Protocol $q$ | `markdown-file@1` | Shared Tether registry |
| Digest $z$ | lowercase SHA-256 | Calculated under $q$ |
| Store id $s$ | `local`, `github`, `youtube` | Contributor |

A Git URL is a location, not contributor identity. The stable contributor name
lives in `[contributor].id`.

## 1. Scaffold the package

With Tether installed:

```bash
tether contributor init . \
  --id example \
  --hierarchy documents
```

The command creates `contributor.toml` and an empty hierarchy inventory. Add
further stores and inventories directly to the descriptor.

## 2. Prepare the bounded resource

Choose a versioned protocol matching the resource boundary. For example,
`markdown-file@1` owns one Markdown file while `loci-project@1` owns a bounded
project tree. Validate the shape and calculate its canonical digest:

```bash
tether resource digest ./F-01-paper.md --protocol markdown-file@1
```

The protocol—not ZIP metadata or a store—defines which bytes contribute to the
digest.

## 3. Register the accepted address in K

K owns the node UUID and admits the contributor id. Its node records the
accepted resource:

```yaml
id: 11111111-1111-4111-8111-111111111111
contributions:
  c_example:
    h_documents:
      r_md:
        protocol: markdown-file@1
        sha256: <canonical-digest>
```

This creates the immutable address:

$$
\bar a=(\operatorname{id}(v),\texttt{example},
        (\texttt{documents}),\texttt{md}).
$$

Acceptance is currently a coordinated manual change. A future proposal surface
may prepare requests, but K remains the authority for topology and acceptance.

## 4. Publish contributor-owned locations

The matching hierarchy inventory repeats the accepted protocol and digest and
lists physical locations:

```toml
version = 2
contributor = "example"
hierarchy = ["documents"]

[[resource]]
node_id = "11111111-1111-4111-8111-111111111111"
path = "T-example/L-example/F-01-paper"
key = "md"
protocol = "markdown-file@1"
sha256 = "<canonical-digest>"
locations = [
  { store = "local", relation = "exact", location = "storage/documents/local/T-example/L-example/F-01-paper.md" },
]
```

`exact` means the location reproduces the accepted digest. Use `publication`
for transformed or hosted representations such as a transcoded video.

## 5. Validate the join

```bash
tether contributor check .
tether resource list . --id 11111111-1111-4111-8111-111111111111
tether resource resolve . \
  --path T-example/L-example/F-01-paper \
  --hierarchy documents \
  --key md
```

Tether validates package structure, resource uniqueness, local exact bytes,
and protocol compatibility. K-to-contributor comparison additionally requires
the UUID, contributor, hierarchy, key, protocol, and digest to agree.

## 6. Materialize for a consumer

Materialization is explicit and does not mutate the contributor or K:

```bash
tether pull . \
  --hierarchy documents \
  --key md \
  --store local \
  --into ./snapshot \
  --layout dir
```

Use `dir` for exact transferable resources and `map` for URI-only projections.
Both create the snapshot described in
[`MATERIALIZATION.md`](MATERIALIZATION.md).

Protocol v1 onboarding is no longer used for active contributors. Its parser
and contract remain available as explicit legacy compatibility in
[`CONTRIBUTOR-PROTOCOL.md`](CONTRIBUTOR-PROTOCOL.md).
