# Cohesian Tether — agent guidance

## Purpose

Maintain Tether, the common dependency-free bridge between K resource targets
and contributor-owned stores.

Tether owns protocol interpretation, URI projection, and explicit
consumer-directed materialization. It does not own K topology, contributor
content, credentials, or persistent consumer storage.

## Read first

| Need | Read |
|---|---|
| Tool overview | [`README.md`](README.md) |
| Active contributor protocol | [`docs/CONTRIBUTOR-PROTOCOL-V2.md`](docs/CONTRIBUTOR-PROTOCOL-V2.md) |
| Legacy protocol v1 | [`docs/CONTRIBUTOR-PROTOCOL.md`](docs/CONTRIBUTOR-PROTOCOL.md) |
| Contributor onboarding | [`docs/CONTRIBUTOR-ONBOARDING.md`](docs/CONTRIBUTOR-ONBOARDING.md) |
| Pull layouts | [`docs/MATERIALIZATION.md`](docs/MATERIALIZATION.md) |
| K resource overlay | [`../k-graph/docs/RESOURCE-OVERLAY.md`](../k-graph/docs/RESOURCE-OVERLAY.md) |
| Mathematical contract | [`../../Organization/CONTRIBUTOR-STORE-RESOLUTION.md`](../../Organization/CONTRIBUTOR-STORE-RESOLUTION.md) |
| Research contributor | [`../research/contributor.toml`](../research/contributor.toml) |

## Invariants

- $a=(\sigma,c,H,p)$ is the active resource address.
- The immutable logical identity uses the K UUID, contributor, hierarchy, and
  resource key.
- Protocol and canonical SHA-256 define the accepted resource bytes.
- Exact and publication locations remain distinct.
- Relative package paths cannot escape the contributor workspace.
- Credentials never appear in protocols, inventories, or output.
- Resolution is informational and performs no content transfer.
- `pull` is the only transfer boundary and always names one store, destination,
  and layout explicitly.
- Contributor-specific layouts remain behind the common protocol.

Tether 0.3.0 implements protocol v2 as the active contract. Protocol v1 remains
an explicit compatibility adapter for historical packages; never reinterpret
it as v2 or extend its vocabulary with v2 semantics.

## Validation

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 \
  python -m unittest discover -s tests
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 \
  python -m tether.cli contributor check ../research
```
