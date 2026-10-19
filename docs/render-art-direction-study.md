# Commercial semiconductor rendering: art direction study

Studied on 2026-10-11. This is a visual analysis of official examples, not a claim that generated images reproduce production hardware. The original references are retained in the ignored local `reference_images/architecture/` collection; they are not shipped as Silicon Canvas assets. Page numbers below are the PDF viewer's one-based page numbers.

## What the references actually show

| Official reference, inspected pixels | Visual observation | Transferable rule |
|---|---|---|
| [NVIDIA Blackwell product page](https://www.nvidia.com/en-us/data-center/technologies/blackwell-architecture/), product hero | A tangible package at an oblique angle, different surface finishes, fine patterned silicon and large surrounding darkness. This is an object with a silhouette, thickness and illumination. | Start with a product object, camera and material hierarchy; keep a deliberate area for surrounding editorial content. |
| [NVIDIA Blackwell technical brief](https://resources.nvidia.com/en-us-blackwell-architecture), PDF p. 6, Figure 1 | Several different devices share one board, with their placement, size, connectors and component texture showing a system. A uniform camera and light make them belong together. | A system rendering needs a physical support and coherent scale. Keep tiny board components as texture rather than many individually labelled functions. |
| Same brief, PDF p. 14, Figure 4 | A rack silhouette carries the system story, while two product details sit beside it. | Change scale through an explicit detail view or separate companion image instead of filling the whole rack with microscopic labels. |
| [AMD Advancing AI 2025 deck](https://www.amd.com/content/dam/amd/en/documents/corporate/events/advancing-ai-2025-distribution-deck.pdf), PDF p. 21 | A close package view accompanies a short set of product claims, with strong separation between picture and text. | A product overview can show a coherent whole and a few claims without exposing every internal function. |
| Same deck, PDF p. 25 | The multi-device board is one object. Regular repeated accelerator packages convey platform scale; devices and board details have different prominence. | Repeat confirmed physical instances consistently, and allow the board to unify the composition. |
| [AMD CDNA 3 white paper](https://www.amd.com/content/dam/amd/en/documents/instinct-tech-docs/white-papers/amd-cdna-3-white-paper.pdf), PDF p. 3, Figure 1 | An exploded package preserves the shared oblique view and aligned layers. Sparse leader lines identify groups outside the object. | Explode along a coherent assembly axis, preserve projected alignment and show only the layers needed for the explanation. |
| [Intel Core Ultra Series 2 media deck](https://download.intel.com/newsroom/2024/client-computing/Intel-Core-Ultra-Series-2-Media-Deck.pdf), PDF p. 2 | A rendered laptop and abstract illuminated contents tell an application story beside a short headline. | A business image may stage the chip in its application, when that better explains the offer than a bare package. |
| Same deck, PDF p. 7 | Memory layers, a package close-up and transparent functional overlays illustrate different benefits at different scales. | Separate a physical exploded layer from a conceptual capability overlay. Use a small number of illustrations rather than one tangled master view. |
| Same deck, PDF p. 82 | A package hero is surrounded by short, separately composed capability illustrations; some are literal parts and some visual metaphors. | Treat a multi-panel business composition as editorial panels with independent roles, not a graph where every panel needs a connector. |
| [Arm cloud and data center products](https://www.arm.com/products/cloud-datacenter), Neoverse CSS stack visual | CPU, GPU, NPU and System IP appear as floating coloured symbols in a lit scene, without a physically credible assembly. | This is a valid capability concept visual. Its apparent vertical stacking must not become a claim about dies or packaging. |

These examples cover product hero, board-level assembly, a system/detail composition, an exploded physical package, an application visual and conceptual capability artwork. They should remain different forms of expression. Giving a flowchart metallic edges does not supply an object, assembly, camera or product story.

## A flexible visual brief

Use purpose and content to assemble an art direction, rather than locking all business requests to one preset. A request for a BP cover may call for an object hero, while a BP technical page may call for a readable system diagram or an illustrated assembly with callouts. The explicit request for a commercial render should select a render route.

The reusable brief should describe the following independently:

- **Message and viewing conditions:** the one thing a reader should understand, whether the image accompanies slide text or stands alone, and the intended visual scale.
- **Subject and support:** the primary product, its real enclosing package or board when known, confirmed peripheral products, and any conceptual capability overlays.
- **Camera:** an intelligible view of the relevant faces, a coherent perspective or orthographic projection, and enough separation to keep important objects visible. A three-quarter view is a useful starting point, not a requirement for every image.
- **Staging:** object hierarchy, intentional empty space, visual weight and any application setting. A system assembly may use a board; an unconfirmed product should not acquire a complicated invented server.
- **Materials:** distinguish silicon, substrate, matte encapsulant, metal lid and connector surfaces when they are actually shown. Choose restrained plausible finishes rather than coating every function in the same glowing metal.
- **Lighting:** a broad key light, controlled fill, modest edge separation, contact shadows and consistent reflections. The subject must remain legible when reduced to slide size.
- **Assembly:** intact, exploded or selectively cut away according to the message. Exploded layers use a shared axis and camera. A cutaway does not imply that logical blocks are separate physical pieces.
- **Annotation:** labels are short and secondary; perimeter callouts should have clear targets. Hero imagery may omit labels altogether if adjacent text already explains the product. Rendered traces and arrows must not pretend to be exact routing unless it was supplied.
- **Continuity:** hold identity, physical claims and important material cues across revisions while permitting a new camera or crop when it improves the image.

The model can propose a novel composition within those constraints. A useful preset supplies an initial direction; it must not force the same slots, object count or arrow pattern on every input. Palette and mood are adjustable after the scene has a coherent subject.

## Physical facts, capabilities and creative assumptions

Keep three different kinds of information in the compiled result.

| Kind | Example | Allowed treatment |
|---|---|---|
| Supplied physical fact | Two confirmed packages mounted on a common board | Preserve the count, assembly membership and interface description. |
| Logical capability | CPU, NPU, SRAM, DMA and NoC in one SoC | Preserve the capability and relation in the engineering source. They may become a compact callout or a conceptual overlay; they must not automatically become five dies. |
| Creative visual assumption | Generic package finish or illustrative board support, when no exterior has been supplied | State it as concept art in the exported caption/brief. Use a coherent generic exterior without claiming a real package type, die count, manufacturing node or floorplan. |

Unknown exterior is not a reason to block an image. A generic product concept can still communicate a good visual story. It is also not a licence to borrow AMD or NVIDIA device counts, HBM topology, logos, marks, process technologies or specifications from the reference.

If physical detail is missing, choose a concept with a modest claim surface. For example, render one generic accelerator package as the hero and explain compute, memory access and connectivity in concise surrounding editorial elements. Do not convert every internal queue, cache and controller into a separately fabricated product.

## Acceptance and revision

Evaluate a rendering as a rendering. Node and edge coverage can audit the retained engineering source; it does not prove a commercial image communicates well.

1. At slide-thumbnail size, is there one legible primary subject and an immediate reading hierarchy?
2. Do object silhouettes, dimensions, camera, perspective and assembly layers agree?
3. Are important supplied facts intact, and are invented physical claims absent?
4. Do materials, illumination, shadows and small details suggest one designed product rather than unrelated clip art?
5. Can every visible label/callout be read and assigned to its target without ambiguity?
6. Does the image serve the requested message, with enough space for the actual document or slide?

If the image fails, identify the failed dimension and revise that part of the brief. A mechanical alignment failure needs a camera/assembly correction; a clutter failure needs a change in content hierarchy or annotation, not just a new colour. The compiler should report what can be checked from the source separately from the visual judgement that still requires inspecting the Image Gen output.

## Local collection inventory

The companion local metadata file `reference_images/render_art_direction_metadata.json` records the inspected references, source pages, saved relative paths and SHA-256 digests. All original manufacturer pixels remain outside Git tracking and release artifacts. The public document contains links and original art-direction analysis only.
