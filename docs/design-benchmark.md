# General figure design benchmark

Silicon Canvas is evaluated on different reader tasks, rather than one attractive
SoC or attention example. This set freezes twelve **original generic sources**
before reviewing their generated images. It contains no proprietary design,
manufacturer logo, or copied paper figure. Its facts are “given” within each
synthetic example; that does not make them measurements of a real product.

The sources live in `tests/fixtures/design_coverage/`. They are inputs, not golden
compiler outputs. Changes to the planner should improve these sources without
rewriting their facts to make a test pass. After a source has informed a fix it is
a regression case, not evidence of performance on unseen designs. New release
evaluation should add fresh domains and reserve additional Image Gen holdouts.

| Source | Nodes / edges | Reader task | Failure the case is designed to reveal |
| --- | ---: | --- | --- |
| `repeated-ingress` | 22 / 21 | Four private packet lanes feeding shared services | Count only macro boxes; hide the other instances; treat private copies as one shared resource |
| `heterogeneous-instrument` | 12 / 11 | Two unequal acquisition channels joining shared capture | Force different channels into an identical template; reparent external interfaces |
| `branched-tile-return` | 7 / 8 | Parallel private filtering and shared statistics, join and same-bank return | Serialize parallel branches; draw a second bank; lose a numeric selection label |
| `residual-projection` | 10 / 10 | Tensor operands, broadcast bias, projections and an identity skip | Treat every join as addition; lose shape; invent hardware stages |
| `retry-controller` | 6 / 12 | Conditions, reset, success priority and one retry | Drop hold loops; add loops to unconditional exits; reverse or detach a predicate |
| `ready-valid-trace` | 6 / 0 | Exact signal samples on eight shared rising edges | Invent cycles; accept a stalled beat; change data before acceptance |
| `elastic-pipeline` | 6 / 10 | Functional transformations and reverse backpressure | Turn FIFO capacity into latency; merge distinct data/ready senses; invent a schedule |
| `mesh-memory` | 12 / 24 | Four-router adjacency, local endpoints and memory boundary | Collapse the mesh to a bus; invent diagonal links; absorb off-chip memory |
| `commercial-context` | 10 / 12 | Product exterior plus supplied external context | Default to an empty package; invent use-case devices; bury the system relationships |
| `commercial-cutaway` | 10 / 12 | Logical functional regions and a coherent product perspective | Only change colors; use a decorative physical floorplan as technical evidence |
| `commercial-hero` | 10 / 12 | A quiet launch-cover product image | Force all engineering detail onto a cover; add marketing claims |
| `sparse-acquisition` | 5 / 4 | Useful generic system from a short request | Reject incomplete input; pretend proposed modules were supplied; invent exact specifications |

The three commercial cases deliberately use an identical source ledger and
different natural-language intentions. Their result should differ in the
explanatory task, not merely palette. The sparse case models an illustrative
completion: all proposed nodes and edges remain `origin=assumed`, with no false
source quotation. The fixture does not test a live provider's completion ability;
that needs a separate provider evaluation using the original sparse sentence.

## Independent technical checks

`tests/test_design_coverage.py` and `scripts/design_coverage.py` check facts that
are independent of any polished image:

- The canonical source, hash, ownership tree, exact labels, conditions and
  optional tensor metadata survive compilation and both entry points.
- Actual visible inventory includes nested children and repeated appearances.
  A same-hardware detail inset is an extra visual occurrence, not extra hardware.
  Reported leaf counts are recomputed from the selected display inventory.
- State transitions include all twelve exact edges and all four hold loops.
  The fixture predicates are exhaustively checked over their six Boolean inputs:
  each state has one applicable non-reset successor, and success beats timeout.
- The timing fixture independently evaluates `rst_n && valid && ready` at every
  supplied edge. Exactly A, B and C transfer at c4, c5 and c6. A stays stable through
  the c2/c3 stall and its c4 acceptance.
- Tensor operands enter their own consumers; the identity skip enters the final
  residual addition. Matrix multiply, bias broadcasting and residual addition
  remain different operations.
- Pipeline data/valid and ready relations retain separate directions and labels.
  The supplied two-entry FIFO is a capacity, with no invented latency.
- Mesh adjacency retains both directed senses on each actual neighbor link;
  there are no diagonal router links or invented coherence claims.
- Document typography does not shrink to force a busy picture onto one canvas.
  A plan may require a different source-backed perspective. It must describe that
  limitation honestly instead of reporting generated-image acceptance.

The ready/valid example uses the handshake rule and source stability requirement
in Arm's [AMBA AXI protocol specification](https://documentation-service.arm.com/static/63ff0ebd56ea36189d4e7ee7).
AMD's [READY/VALID handshake documentation](https://docs.amd.com/r/en-US/ug934_axi_videoIP/READY/VALID-Handshake)
also locates acceptance at a rising clock edge. The fixture is a **generic channel**,
not an AXI implementation or a protocol-conformance certification. The trace,
controller and all architecture choices were authored for this benchmark.

## Real Web and MCP checks

The focused checks use the actual Chromium Worker/Pyodide compiler and the actual
MCP STDIO executable. They do not replace these with an in-memory mock:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_design_coverage.py -v
.venv/Scripts/python.exe scripts/build_web.py
.venv/Scripts/python.exe scripts/verify_browser.py --design-only
.venv/Scripts/python.exe scripts/verify_mcp_executable.py PATH_TO_MCP_EXE --design-only --output REPORT.json
```

The default browser and executable verification runs include these twelve cases
alongside the earlier regression matrices. `--design-only` avoids repeating the
unchanged cases while iterating. Web comparison checks complete JSON, guide RGB
pixels when a guide exists, source-backed design plans, prompt/caption exports,
and review manifests. MCP comparison additionally checks resource/file/ZIP/image
content equality from a separate working directory with no provider call.

## Generated-image acceptance

A passing software contract is necessary but is not a judgment of the image's
beauty or correctness. For each actual Image Gen trial, keep the source, exact
tool-returned prompt, any supplied guide, and the original generated image. Check
three separate gates:

1. **Technical:** source ownership, counts, endpoints, directions, conditions,
   formulas and timing events. A reversed required arrow fails this gate even if
   the result looks good.
2. **Explanatory:** the requested reading task is apparent; independent branches,
   states, timeline or ownership can be traced without guessing. Optional details
   have an intentional place rather than being silently erased.
3. **Visual:** hierarchy, spacing, line routing, contrast and typography work at
   the intended document or slide size. Decorative depth, glow and color must not
   obscure the explanation.

Record failures and regenerate from canonical facts when needed. Do not promote
one attractive sample into a claim that every category or provider is excellent.
The main purpose of this benchmark is to expose that gap and make it testable.
