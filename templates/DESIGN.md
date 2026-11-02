---
version: alpha
name: NAME
# themes: [light, dark]  # then colors.primary-dark overrides colors.primary
# omitted: ["--a-*"]  # code names left out on purpose
colors:
  primary: "#1A1C1E"
typography:
  body-md:
    fontFamily: Public Sans
    fontSize: 1rem
rounded:
  md: 8px
---
<!-- Google's DESIGN.md format, @google/design.md 0.4.0 (alpha). Only a repo with a UI carries one.
bench/checks line: npx @google/design.md@0.4.0 lint DESIGN.md -->

## Overview
The product is X, told as Y; every screen leads with Z. Who it is for.

## Colors
What each color means, kept to a few; text stays ink unless a color says something.

## Typography
A few sizes, each named by its job.

## Layout
The grid and spacing, and how you move between levels: what opens what, and where it animates from.

## Elevation & Depth
How layers stack: shadows, borders, surfaces.

## Shapes
Corner radii and the shapes components use.

## Components
The one shape every unit takes, and the states each view designs: loading, refreshing, empty, error, first run.

## Do's and Don'ts
The few rules that keep the design consistent. Before calling a change done: walk the keyboard path (focus comes back), turn on reduced motion, check dark and 375px, force each state, and read every sentence aloud.
