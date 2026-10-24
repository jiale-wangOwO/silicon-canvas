---
name: silicon-canvas
description: Create and refine chip architecture, microarchitecture, algorithm/dataflow and semiconductor product images with Silicon Canvas and Image Gen. Use when the user wants a technical figure or product illustration, or explicitly requests Silicon Canvas.
---

Use the bundled Silicon Canvas MCP to turn the user's design into a source-backed Image Gen brief, then generate the actual image with the host's image tool.

Call `silicon_prepare` with the user's description. Infer useful defaults; do not require the user to choose a diagram category, supply node lists or fill out a specification. Preserve explicit visual choices. New figures use English labels by default, including when the description is Chinese.

Read the returned semantic messages and create the requested JSON specification using the host model. Call `silicon_compile` with the `preparation_id`. Keep supplied quantities, ownership, conditions and relationships; distinguish reasonable assumptions from known facts. No separate semantic-model API key is needed.

Generate with the returned prompt and actual input roles:

- An engineering view with `guide_role: target_structure` uses its corresponding guide. If that required guide is unavailable, adjust the view before claiming controlled structure.
- An algorithm view with `algorithm_flow_plan` uses the prompt and mathematical dependencies, without a hardware guide.
- A product or system illustration with an optional `composition_reference` can use the prompt alone. Logical regions and conceptual placement do not assert a measured die floorplan.

Use Image Gen when available. If the host has no image tool, deliver the compiled prompt and explain that image generation requires one. Do not substitute a hand-written SVG, draw.io diagram or another renderer for a requested Image Gen result. Do not rewrite the tool's art direction around a single example.

Inspect the actual image for its reading structure, labels, arrow endpoints, source ownership and visual consistency. Use `silicon_prepare_review` when its source-grounded review will help. A valid specification or layout preflight does not approve the generated bitmap. Use natural feedback through prepare/compile for revisions; preserve the current source when the user only wants an appearance change.

Show the resulting image and briefly identify any material limitation. Export the drawing bundle with `silicon_export` when the user needs the prompt, source or handoff files. Keep the workflow within the user's requested scope.
