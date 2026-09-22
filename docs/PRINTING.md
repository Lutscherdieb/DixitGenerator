# DixitGenerator — printing, calibrating and cutting

Everything between "the PDF is written" and "the card is in a sleeve". Read
this once before your first batch; the two settings in
[Print dialog](#print-dialog-the-two-settings-that-matter) are the ones that
ruin a run if you get them wrong.

## What the PDF contains

| | |
|---|---|
| Paper | A4, 210 × 297 mm, portrait |
| Cards per sheet | 4, in a 2 × 2 block |
| Card | 80 × 120 mm — the Dixit / "Magnum" sleeve size |
| Block | 160 × 240 mm, centred: 25 mm margins left and right, 28.5 mm top and bottom |
| Bleed | 3 mm, on the block's outer edges only |
| Crop marks | hairlines in the margin, 1.5 mm clear of the art, 4 mm long |

Cards **touch**. That is deliberate: one cut of the guillotine serves two cards,
and a cut that lands a millimetre off still leaves both cards full-bleed — one
comes out 81 mm, its neighbour 79 mm, and neither shows a white edge.

Pages come out interleaved — front, back, front, back — for automatic duplex.
In manual mode you get two files instead.

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
| A thin white sliver on one card edge | The cut landed outside the block, past the 3 mm bleed | Cut closer to the crop marks; the bleed is 3 mm, so anything within that is covered |
| A card looks soft or pixellated | The source art was below 945 × 1417 px | The export warns about this by name — re-upload a larger source. It is a warning, not a block: a deliberately painterly source is your call |
| The whole sheet is shifted on the paper | "Borderless" or a custom paper size in the driver | Turn borderless off; set paper to plain A4 |
