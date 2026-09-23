# DixitGenerator — printing, calibrating and cutting

Everything between "the PDF is written" and "the card is in a sleeve". Read
this once before your first batch; the two settings in
[Print dialog](#print-dialog-the-two-settings-that-matter) are the ones that
ruin a run if you get them wrong.

Printing at home is what this document is about. If you are sending the cards
to a press instead, skip to
[Sending cards to a press](#sending-cards-to-a-press) — none of the duplex,
calibration or cutting advice applies there.

## What the PDF contains

| | |
|---|---|
| Paper | A4, 210 × 297 mm, portrait |
| Cards per sheet | 4, in a 2 × 2 block |
| Card | 80 × 120 mm — the Dixit / "Magnum" sleeve size |
| Block | 160 × 240 mm, centred: 25 mm margins left and right, 28.5 mm top and bottom |
| Bleed | **none** — nothing is printed outside a cut line |
| Crop marks | hairlines in the margin, 1.5 mm clear of the block, 4 mm long |

Cards **touch**. That is deliberate: one cut of the guillotine serves two cards,
and a cut that lands a millimetre off still leaves both cards full-bleed — one
comes out 81 mm, its neighbour 79 mm, and neither shows a white edge.

**The cut card shows exactly what the grid tile showed**, and there is no bleed:
the printed area *is* the card, edge to edge, with nothing beyond the cut line.

That means the four outer edges of the block want a clean cut. Land the blade a
little outside and you get a hairline white sliver on that edge; a little inside
and the card is fractionally small, which nobody will notice. When in doubt, cut
a hair inside the mark. The interior cuts need no such care - they are shared
between two cards, so an off cut simply makes one 81 mm and its neighbour 79 mm,
both still full-bleed.

Pages come out interleaved — front, back, front, back — for automatic duplex.
In manual mode you get two files instead.

## Sending cards to a press

The export dialog's **Output** menu has two image formats beside the A4 PDF.
Both write one PNG per card into a single `.zip` in `out/`, plus one shared
`back.png` if you picked a back. Neither has a duplex pass or a calibration
offset, so those controls disappear when you choose one.

| Output | Per-card file | Use it for |
|---|---|---|
| **MakePlayingCards ready** | 1017 × 1489 px — the 80 × 120 mm card plus 36 px of bleed a side | Ordering from a press |
| **Cropped images only** | The trim crop at the source's own resolution, no bleed | Anything else: a different service, an archive, re-importing |

### The bleed is already in the file

Every file in an MPC archive carries its bleed. **Do not add bleed again in the
press's designer** — you would be bleeding the bleed, and the card would come
back showing about 6 mm less picture on each edge than you framed.

The archive contains a `README-mpc-dixit.txt` saying the same thing, with the
exact pixel size, so the file travels with its own instructions.

### What the bleed is made of

Bleed is taken from real source pixels wherever your artwork has spare material
outside the crop. Where it does not — and it usually does not on at least one
axis, because the crop keeps 100% of one dimension by construction — the edge is
**mirrored outward** instead.

That is standard prepress practice and it is invisible on a cut card, because
the mirrored strip is outside the trim line. It matters only if a press cuts
badly wrong: you would then see a narrow mirrored band rather than a white one,
which is the better failure.

### Read this before you order

**MakePlayingCards does not sell an 80 × 120 mm card.** Their sizes are mini,
bridge, poker (63 × 88 mm), tarot (2.75 × 4.75 in = 69.85 × 120.65 mm) and big.
Tarot is the closest to a Dixit card — the same height to within 0.65 mm, and
**10.15 mm narrower**.

This project exports its own 80 × 120 mm, deliberately, so that a card you order
matches a card you cut at home and fits a Dixit sleeve. The cost is that the
order has to go through MPC's custom-requirements path, and **they may decline
it**.

If they do, the fallback is recorded in [PROJECT.md](../PROJECT.md): move
*every* output to tarot together by pointing `SheetLayout.fit` at `TAROT_MPC`,
rather than letting the press files drift away from the sheets. The verify gate
already exports and measures that layout, so it is a one-line change. Your cards
would then no longer match a real Dixit deck or fill a Dixit sleeve — which is
why it is a decision and not a default.

### What you do not have to think about

Framing. A card is cropped once, by its trim rectangle, and the bleed is added
outside that. The card a press cuts, the card you cut off an A4 sheet and the
tile in the overview are the same picture — the verify gate asserts it on every
run, for sources wider than the card, taller than it, and at exactly its aspect.

## Print dialog: the two settings that matter

**1. Scale must be 100% / "Actual size".** Not "Fit to page", not "Shrink
oversized pages", not "Fit to printable area". Every one of those silently
resizes the sheet by a few percent, which makes each card the wrong size *and*
throws front/back registration out. This is the single most common way a batch
is wasted. In Adobe Reader the setting is **Page Sizing & Handling → Actual
size**; in a browser's print dialog it is **Scale: 100%** (default is often
"Fit to printable area" — change it).

**2. Duplex flip must match the flip you exported.** If you exported
`long-edge`, the printer must be set to **Flip on long edge** (sometimes
"Two-sided, book"). `short-edge` means **Flip on short edge** ("Two-sided,
tablet"/"notepad"). Get this wrong and the backs land on the wrong cards.

Worth setting too: best/photo quality, and the right paper type for your stock
(heavier paper with the wrong setting smears). Turn off any "borderless" mode —
this layout does not need it and it re-scales the page.

## Which flip does my printer use?

Most home printers default to **long-edge**, which is why that is
DixitGenerator's default. Rather than guess, calibrate once.

### Calibration: measure your printer's drift

Duplex drift of 1–2 mm is normal, is a property of *your* printer and paper
path, and is exactly the error that ruins a batch of 84 cards. Measure it once.

1. Export a small batch (4 cards is enough) with a back image, in the flip mode
   you intend to use.
2. Print it at 100%, double-sided, as above.
3. **Hold the printed sheet up to a bright light.** The crop marks print on the
   front page *and* on the back page at the same nominal positions — so if the
   two sets coincide, your registration is perfect and you are done.
4. If they do not coincide, measure the offset of the **back** marks relative to
   the **front** marks, in millimetres, with a steel rule. Note the sign: `+x`
   is to the right, `+y` is up, as you look at the *front* of the sheet.
5. Record it in `printer.local.json` at the repo root:

   ```json
   { "offset_x_mm": -0.8, "offset_y_mm": 1.2 }
   ```

   That file is **gitignored on purpose**. It describes one machine and one
   paper path; committing it would misregister someone else's printer, and
   machine-specific values in version control are a doctrine violation here
   regardless (see CLAUDE.md).

6. Re-print and confirm the marks now coincide.

The offset is applied to **back pages only** — the fronts are the reference.

> **Not built yet:** `tools/calibration_sheet.py` (a dedicated sheet with
> vernier-style rulers, which reads the offset off more precisely than a steel
> rule) and the wiring that reads `printer.local.json` automatically. Today the
> export takes the offset as its `offset_mm` argument. The hold-it-to-the-light
> method above works now and is good to about half a millimetre, which is well
> inside a hand-cut tolerance.

### Telling the two flips apart, if you must

Print one page with a big "TOP" written on it duplex, or simply export a
**one-card** batch. With one card the front sits top-left; under long-edge its
back lands top-**right**, under short-edge it lands **bottom**-left. Hold it to
the light and you can see which your printer did.

## Paper

Anything from 160 g/m² up behaves well. Below about 120 g/m² the front shows
through the back, which matters a lot for a game where the back must give
nothing away. If you are laminating, the lamination adds the stiffness, so a
lighter, photo-coated stock is fine and takes ink better.

Whatever you choose, print the calibration sheet on the **same** stock you will
use for the batch: a heavier sheet takes a different path through the duplexer
and can drift differently.

## Cutting

A guillotine or rotary trimmer, not scissors — the cards touch, so every cut is
a straight line across the whole sheet and a blade that follows a rule gives you
both cards at once.

Order that wastes the least:

1. Cut the **outer** block edges first, using the crop marks. This removes the
   margin and the 3 mm bleed skirt, leaving a clean 160 × 240 mm block.
2. Cut the block **in half vertically** (the shared edge between columns).
3. Cut each half **in half horizontally**.

Four cuts, four cards. Check the first sheet with a rule before committing the
rest of the stack: the cards should measure 80 × 120 mm.

If you cut a stack at once, keep it to a few sheets — more and the blade pushes
the lower sheets out of line.

## Laminating and finishing

- Laminate **after** cutting, with a small border, then trim the pouch back to
  the card edge — or laminate before cutting if you prefer a sealed edge and
  accept a slightly larger card. Either works; be consistent within a deck, or
  the cards are distinguishable from the back, which breaks the game.
- 80 micron pouches keep the card flexible enough to shuffle. 125 micron makes a
  rigid card that is pleasant but slow to shuffle and noticeably thicker in a
  sleeve.
- **Corners:** the PDF draws none, because a printed radius that is then cut
  square looks worse than no radius. Use a 3 mm corner punch after laminating if
  you want rounded corners.
- Sleeves: "Dixit" / "Magnum" size, 80 × 120 mm. That is the size this project
  prints to, so a laminated card is a firm fit — if it is too tight, trim a hair
  off the long edge rather than reprinting.

## Troubleshooting

| What you see | Cause | Fix |
|---|---|---|
| Cards measure smaller than 80 × 120 mm | The print dialog scaled the page | Set scale to 100% / "Actual size" and reprint |
| Backs are on the wrong cards | Exported flip ≠ printer's duplex setting | Match them; re-run the one-card test above to confirm which your printer does |
| Backs are upside down | Short-edge duplex without the 180° rotation, or an exported `long-edge` file printed short-edge | Export `short-edge` for a short-edge printer; the rotation is then applied for you |
| Backs are consistently a millimetre or two off | Normal printer drift | Calibrate and record `printer.local.json` |
| A thin white sliver on an **outer** card edge | The cut landed outside the block. There is no bleed to cover it, by design | Cut on the mark or a hair inside it. Interior edges are shared and cannot show a sliver |
| A card looks soft or pixellated | The source art was below 945 × 1417 px | The export warns about this by name — re-upload a larger source. It is a warning, not a block: a deliberately painterly source is your call |
| The whole sheet is shifted on the paper | "Borderless" or a custom paper size in the driver | Turn borderless off; set paper to plain A4 |
