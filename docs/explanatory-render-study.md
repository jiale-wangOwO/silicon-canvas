# Explanatory semiconductor rendering

Reviewed on 2026-10-11 using the two user-provided SoC references, the local official-reference collection, and the existing [art direction study](render-art-direction-study.md). The user references are review inputs only: their pixels, interface watermark and download control are not release assets.

## What the user references clarify

The desired image can communicate architecture while using perspective, materials and lighting. A commercial image is not necessarily a closed package hero. The two references use different levels of disclosure:

| Reference | What the reader learns | Useful visual mechanism |
|---|---|---|
| Intact SoC with perimeter descriptions and external devices | The product combines compute, memory, management and I/O; external memory and a host are part of its system context. | One dominant product, grouped capability callouts, two subordinate external roles, and a limited set of interface connections. |
| Perspective SoC with functional regions | Compute, memory and I/O belong to the same chip; a shared interconnect unifies them; external memory and a host lie beyond its boundary. | A common perspective plane, contiguous logical regions, a central shared resource, two-level labels, and a readable internal-to-external topology. |

The second image is a spatial functional map. Its coloured areas do not need to claim a measured die floorplan or separate chiplets. A declared conceptual overlay is a valid way to explain logical ownership and connectivity. Preventing invented manufacturing claims should not also remove useful architecture from the image.

These references are not flawless templates. The first depicts several literal-looking plugs and parallel gold connections whose shapes and counts could suggest unsupported packaging or lane details. The second puts some small text on a receding plane and uses prominent luminous traces. Transfer their hierarchy and explanatory topology, not every accessory, glow effect or microscopic pattern.

## Evidence from official visual practice

The inspected [Arm cloud and data center visual](https://www.arm.com/products/cloud-datacenter) presents CPU, GPU, NPU and System IP as spatial capability symbols. Their graphic relationship communicates an integrated offer; their apparent arrangement is not itself a manufacturing specification. The [Arm investor presentation](https://investors.arm.com/static-files/9f3d67d7-d15d-4df2-8a70-bbf006880253), PDF page 19, explicitly contrasts separate IP with an integrated CSS graphic. This supports treating logical integration as valid visible content rather than suppressing it whenever the image has depth.

The locally inspected [Intel Core Ultra Series 2 media deck](https://download.intel.com/newsroom/2024/client-computing/Intel-Core-Ultra-Series-2-Media-Deck.pdf), PDF page 7, uses several explanatory treatments on one slide: package memory, an illuminated cache illustration, conceptual power-management overlays and a board-level power-delivery view. Each panel has its own message and scale. This suggests choosing the amount and kind of architectural disclosure from the message, instead of applying one closed-package rule to all commercial work.

These are visual-design observations. They do not authorize copying manufacturer product facts, performance claims, branding or geometries into a different chip's image.

## Select an explanatory treatment before styling

Keep purpose, representation and explanatory treatment separate. A BP can contain a hero cover, a subsystem explanation, or a platform illustration. The intended message should select a starting treatment automatically; natural-language instructions can revise it without requiring the user to learn a taxonomy.

| Treatment | Suitable intent | Visible content |
|---|---|---|
| Product hero | Identity, launch cover, material or product presence | One coherent product; optional title and very sparse supporting text. |
| Annotated product | Explain what the product offers while retaining its complete exterior | Product plus a few source-backed grouped callouts; selected external interface roles when relevant. |
| Functional map or conceptual cutaway | Explain subsystem structure and how it fits together | Logical regions on one coherent chip plane, shared resources, selected relationships and external context. |
| System context | Explain deployment, host/device interaction or platform membership | A dominant system subject and subordinate source-backed actors, with a limited interface story. |

These treatments are starting points, not fixed slots or a mandatory object count. The compiler should preserve the requested message and exclusions, then select content, hierarchy and relationships. Camera, lighting, background, material finish and crop remain flexible after that selection.

## Content should explain before it decorates

For an explanatory illustration, define a small visible-content contract:

1. State the one message the viewer must understand.
2. Select the visible functional roles and their source members. Merge closely related functions; preserve useful subsystem distinctions.
3. Give each role a visual level: dominant subject, internal region, shared resource, external actor or secondary annotation.
4. Select the relationships needed for that message, retaining endpoints, direction when needed, interface identity and ownership from the source.
5. Define a reading order that follows those relationships. Avoid arbitrary card placement and crossing paths.
6. Reserve legible text areas before adding surface texture or reflections.

A CPU/GPU/NPU inventory alone does not justify drawing three fabricated dies. It does justify showing three labelled functional regions on a clearly illustrative surface if the goal is subsystem explanation. Conversely, a closed-package hero does not have to expose every queue or source edge.

Common compositions may be proposed when they fit the source: a shared interconnect can occupy a connecting spine; compute and memory can be visually distinct peers; management can be a spanning band; external actors can sit outside the boundary. These are explanatory placement choices, not assertions of physical layout. Do not impose that composition on sources with different ownership or connectivity.

At normal slide size, the dominant product and major region titles should be readable first. Secondary member lists should be shorter and visibly subordinate. Detail textures, glowing routes and reflections must recede behind labels and topology. Colour should encode roles consistently; one emphasized route is often enough. Materials, camera and typography do more to establish quality than adding more hues.

## Symbolic context is not a fabricated BOM

Distinguish three claim levels in metadata and captions:

| Claim level | Allowed illustration | What it does not establish |
|---|---|---|
| Source-backed logical role or relation | A generic external DRAM symbol connected to the stated memory interface; a generic host symbol connected to the stated host interface. | A particular DRAM package count, pinout, cable, port shape, lane count, board layout or validated electrical routing. |
| Explicit physical assembly | The supplied quantities and membership of packages, boards, layers or devices. | Additional parts, unsupported dimensions or a different packaging topology. |
| Creative appearance or projection | Perspective, substrate finish, generic enclosure, conceptual region position and lighting. | A measured floorplan, manufactured photograph, process node or physical die partition. |

A source-supported symbolic peripheral is useful information. Do not ban all external devices solely because exact appearance is unavailable. Prefer modest generic role symbols over detailed realistic accessories when the source describes only an architectural role. Render one symbolic interface connection unless the source requires more; its line count should not imply lane or pin counts.

Incomplete descriptions may be completed by the normal architecture inference step, with the inferred facts marked as assumptions. Visual selection can use those facts while keeping their origin available in the brief. Appearance assumptions should not silently become verified engineering facts.

Keep disclosure proportional. A concise exported caption such as “Conceptual system illustration; functional regions and interfaces are symbolic” is usually sufficient for a generic explanatory image. Detailed known/assumed/unknown facts belong in the machine-readable brief and review record. Do not fill the artwork or main product UI with a list of every unknown manufacturing property.

## Rules that were overfitted in the previous strategy

Blanket prohibitions against function regions, internal relationships, interface actors, leaders and source-supported connectors reduce all commercial requests to nearly empty hero images. The restriction should depend on treatment: a hero may defer architecture; a functional map must communicate selected architecture.

Likewise, a two-pass workflow that always generates a closed package first and then adds only unboxed background headings prevents a functional cutaway from emerging. Retain this as an option for product identity or typography continuity. For a functional map, the first pass should establish the meaningful spatial regions and principal topology. Later editing can improve typography or material hierarchy while preserving that approved structure.

Do not replace the old prohibition with another blanket rule that every render must reveal internal blocks. The goal is adaptive information content, not an expanded fixed template.

## Validation must match the message

Source retention remains necessary but it does not prove that an image is informative. A passing render contract should state its selected visible roles and relationships. The actual Image Gen output then needs separate review:

- **Explanatory success:** can the intended viewer identify the main product, its major roles and the important relation without reading the entire caption? For a requested functional overview, an unlabelled metal lid is a failure even if the source ledger is complete.
- **Hierarchy:** are subject, internal peers, shared resources, external actors and secondary notes distinguishable? Does a coherent reading order replace arbitrary object placement?
- **Topology:** do visible connections target the correct roles and respect required direction and ownership? Does a shared resource appear shared? Do external actors remain outside the stated product boundary?
- **Visual quality:** do camera, perspective, illumination and materials belong to one scene? Are text and paths readable at document size, with texture and effects secondary?
- **Claim discipline:** are physical assemblies distinguished from symbolic regions and role icons? Are unsupported counts, branding, package technologies and specifications absent?

Update tests that require all render relations to be invisible, cap every illustration at an arbitrary label count, or forbid all region overlays. Replace them with purpose-sensitive semantic checks: heroes may omit architecture; explanatory treatments select source-backed visible roles and principal relations; declared logical projection never becomes a physical die claim; unsupported actors and interfaces remain excluded. Pixel review is still required for generated-image quality, since a valid prompt cannot certify the final aesthetic result.
