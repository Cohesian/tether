# Contributor onboarding

Tether connects identities that are owned in different places. It does not
collapse them into one id.

| Identity | Example | Authority |
|---|---|---|
| K node id $v$ | UUIDv4 | K |
| K rooted path | `T-math/L-division/F-01-introduction` | Derived from K grouping |
| Contributor id $c$ | `research` or `studio` | K contributor registry + contributor package |
| Domain $d$ | `documents`, `scenes`, `videos` | Contributor, admitted by K |
| Format $f$ | `md`, `loci-project`, `mp4` | Contributor, admitted by K |
| Store id $s$ | `local`, `github`, `youtube` | Contributor |

A repository can host one contributor package, but its Git URL is not the
contributor identity. The stable logical name in `[contributor].id` is.

## 1. Scaffold a contributor

With Tether installed:

```bash
tether contributor init . \
  --id example \
  --domain documents \
  --format md
```

The generated package declares contributor identity, one domain, one local
store, one binding, and an empty route inventory. Add further domains, stores,
and bindings directly to the TOML file.

## 2. Register its accepted language in K

K admits the contributor and its domain-format vocabulary in `k-graph.toml`:

```toml
[contributors.example.domains.documents]
formats = ["md"]
```

The contributor id in K and `[contributor].id` must match exactly.

## 3. Register a resource on a K node

K assigns and owns the node UUID. Tether never invents or changes it. The
node declares the accepted logical resource:

```yaml
id: 11111111-1111-4111-8111-111111111111
contributors:
  example:
    documents:
      - md
```

This creates the logical identity:

$$
\rho=(v,\texttt{example},\texttt{documents},\texttt{md})
$$

## 4. Expose a contributor-owned location

The contributor inventory uses the same K UUID and current rooted path:

```toml
version = 1

[[route]]
id = "11111111-1111-4111-8111-111111111111"
path = "T-example/L-example/F-01-paper"
format = "md"
location = "T-example/L-example/F-01-paper.md"
```

The surrounding binding supplies contributor, domain, and store. Together,
the route and binding form the complete target:

$$
\tau=(\sigma,(c,d,f))
$$

## 5. Validate and query

```bash
tether contributor check .
tether resource list . --id 11111111-1111-4111-8111-111111111111
tether resource resolve . --path T-example/L-example/F-01-paper
tether resource identify . --uri <resolved-uri>
```

- `contributor check` checks protocol compatibility, the contributor package,
  domains, stores, bindings, and route identities.
- `resource list` lists stores currently exposing matching resources.
- `resource resolve` returns their URIs.
- `resource identify` maps a known URI back to its K selector and `(c,d,f)`
  category.

## 6. Materialize for a consumer

Materialization is optional and does not change the contributor package. A
consumer chooses one store, destination, and layout explicitly:

```bash
tether pull . \
  --domain documents \
  --format md \
  --store local \
  --into ./snapshot \
  --layout dir
```

Use `dir` for directly readable files and `map` for provider-controlled URIs.
Both produce the common snapshot described in
[`MATERIALIZATION.md`](MATERIALIZATION.md).

K acceptance is currently manual. A future Tether proposal surface may prepare
or submit registration requests, but K remains responsible for node identity,
topology, and acceptance.
