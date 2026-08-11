# Changelog

Newest first. Every entry says what changed for somebody using the tool, not
what changed in the source. A refactor that moves four hundred lines and alters
no answer does not get an entry; a corrected coefficient does, because a rating
worked before it and a rating worked after it are different numbers and
somebody will have to explain why.

Entries that change an answer are marked **changes results**. Those are the
ones a rating engineer has to read.

## 0.25.0 - 2026-08-19

### Added

- `check_examples` holds the shipped example to what depends on it. It is
  the structure the README tells a reader to import, the one the smoke run
  takes end to end, and the one four test files read when they need a real
  four girder unit. If it stops importing, three things break and none of
  them says why.

## 0.24.0 - 2026-08-06

### Added

- The riding surface is recorded against the structure. It decides the
  dynamic allowance a legal rating uses and had nowhere to be written down,
  so every rating started from the default and an engineer who knew the deck
  was rough had to say so every time or come out eleven per cent high on the
  live load. `--surface` on `structure import` sets it; `--surface` on
  `rate` and `shear` overrides it for one run.
- Existing structures get `minor`, which is what the option defaulted to, so
  no rating already worked changes because of this.

## 0.23.0 - 2026-08-05

### Added

- `shearstud structure details --computed` adds the stress range the fatigue
  truck puts at each detail and orders by it. A category on its own does not
  say which detail is in trouble: a category E detail carrying two ksi
  outlives a category B one carrying twelve.

## 0.22.0 - 2026-07-30

### Added

- The structure report carries a computed fatigue line beside the measured
  one, always, even when they agree. They are different evidence and a
  reader who cannot tell them apart will quote whichever suits.


### Added

- A three girder unit rates. The distribution equations were fitted against
  four beams and more, and eleven stringer units on this inventory have
  three, so a rating there used to refuse rather than answer. It falls back
  to the lever rule, which is what the specification says to do and what an
  engineer did before the equations existed.
- The lever rule compares the lane arrangements and takes the worst real
  one. A second lane's wheels land beyond the hinge on a narrow spacing,
  where they unload the exterior girder; asking for two lanes on a seven and
  a half foot spacing came back negative.

## 0.21.0 - 2026-07-30

### Added

- `shearstud fatigue evaluate --computed` evaluates the ungauged details
  from the fatigue truck and prints them under their own heading. A detail
  that carries a gauge keeps its measurement: reporting both would invite
  somebody to take whichever number they liked.


### Added

- The computed stress range at a detail nobody has gauged, from the fatigue
  truck. Every evaluation until now started from a measured spectrum, which
  reaches the one detail in twelve that carries a gauge.
- The fatigue load is one truck in one lane at the fixed rear axle spacing,
  with the multiple presence factor taken back out, the fatigue dynamic
  allowance, and the short term composite section at every station. All four
  differ from the rating load and all four are easy to carry across by
  accident.

## 0.20.0 - 2026-07-26

### Added

- `shearstud book export` and `book import` move a whole book as JSON. The
  file carries the schema version it was written at, and a load into a book
  at a different version is refused. The target book has to be empty:
  merging two books is a different job with its own questions about which
  copy of a structure wins.

## 0.19.0 - 2026-07-25

### Added

- `check_dataclasses` fails the build on a value type that is not frozen or
  has no slots. Everything in this package is a fact about a bridge at a
  moment, and a fact that can be edited in place is one two callers can
  disagree about.

### Fixed

- The `--list` and `--counts` flags on four of the self checks did nothing
  from a command line. They read an argument list the entry point never
  filled in, so they only worked when a test called them.

## 0.18.1 - 2026-07-16

### Fixed

- **Changes results.** No number moved, but a date option that could not be
  parsed reached the user as a traceback ending in `Invalid isoformat
  string` rather than as an error. Eleven commands were each parsing dates
  for themselves; they share one parser now, and it names which option was
  wrong.

## 0.18.0 - 2026-06-30

### Added

- `docs/rules.md`, generated: every threshold this package decides on, with
  the comment its author left on it. Coefficients out of a specification are
  left out on purpose; these are the numbers an agency changes.
- Three thresholds that had no explanation now carry one, which is what
  writing the document found.

## 0.17.0 - 2026-06-28

### Added

- `shearstud campaign show` reports a campaign and, for each gauge on the
  structure, whether it reported and how much of its record was usable. The
  gauges that did not report are the point: a campaign that counted cycles on
  three of five channels looks complete in any listing of what it has.

## 0.16.0 - 2026-06-26

### Added

- `shearstud shape list`, `shape show` and `shape compare`. The catalogue is
  what the older stringers are made of, and `shape compare` prints the shapes
  the three rectangle idealisation fits least well, which is the answer to
  the question somebody asks when a hand calculation disagrees by two per
  cent.

## 0.15.0 - 2026-06-25

### Fixed

- **Changes results.** A yield moment was taken at a nominated fibre even
  when the other one yields first. On a singly symmetric girder the two
  section moduli differ by a third, so the nominated one reported a moment
  the section cannot reach. A bare steel section is now rated at whichever
  fibre yields first; a composite one keeps its tension fibre, because the
  deck holds the other flange.
- **Changes results.** Sections near a pier on a continuous unit were rated
  as composite and driven for the sagging placement. The deck over a pier is
  in tension and cracked, so the capacity comes off the bare steel, and the
  governing placement is the one that hogs most.

## 0.14.0 - 2026-06-09

### Added

- `shearstud record --temperature` subtracts a companion temperature channel
  before the drift fit. The compensation was written and had nothing feeding
  it. The temperature channel may be logged far slower than the strain one.

### Changed

- The logger file parser is shared between the strain and temperature reads,
  so a temperature channel at a reading a minute is no longer held to the
  strain record's sample rate limits.

## 0.13.0 - 2026-06-01

### Added

- `check_constants` fails the build on a float literal buried in a function
  body in the domain layers. A rating is a number somebody signs, and the
  question asked about it two years later is where a coefficient came from.

### Changed

- The AASHTO distribution factor coefficients, the shear buckling limits, the
  design truck axles and the legacy overhang divisor are all named constants
  now, each with the clause it came from. Thirty numbers were written into
  expressions; none of the answers moved.

## 0.12.0 - 2026-05-27

### Added

- `shearstud studs` reports the fatigue pitch and the strength row count for
  a girder's shear connectors, taking the shear range from a shear run rather
  than from a number typed on the command line.

## 0.11.0 - 2026-05-15

### Added

- `shearstud structure section` reports the section properties at a station,
  as all three composite stages rather than one. A dead load stress worked
  out on the short term section is worked out on a section that did not
  exist when the load went on. `--measured` reads the reduced sections.

## 0.10.0 - 2026-05-14

### Added

- `shearstud vehicle list`, `vehicle show` and `vehicle envelope`.
- `shearstud permit` rates a permit vehicle at every level of control the
  permit allows and prints all of them, then names the loosest one that
  clears. A permit that cannot be issued is reported as an answer rather
  than as an error.

## 0.9.0 - 2026-05-11

### Added

- `shearstud thickness add`, `thickness import`, `thickness list`,
  `thickness loss` and `thickness rate`.
- `--measured` on `rate` and `shear` rates the sections the meter left rather
  than the ones on the drawing. Asking for it where there are no readings
  says so rather than quietly rating the drawing.

## 0.8.0 - 2026-05-05

### Added

- Ultrasonic thickness readings can be stored and read back as a reduced
  section. The table has been in the schema since version two with nothing
  writing to it; migration five gives it a note column and the unique index
  that makes a second reading of one place on one day an overwrite rather
  than a duplicate.
- A corrosion rate from an old reading and a new one at the same place. One
  reading gives nothing, which is the usual case and not an error.

## 0.7.0 - 2026-04-21

### Added

- `shearstud book prune`, `book vacuum`, `book orphans` and `book counts`.
  Retention was already written and had no way to reach it. The prune takes
  two separate agreements: `--yes`, and a cutoff outside the ten year policy,
  which the store refuses on its own.

## 0.6.0 - 2026-04-21

### Added

- `shearstud record` reads a raw logger file and takes it through to a
  spectrum: defects on the raw samples, then conditioning, then counting,
  with the truck events pulled out alongside. Until now a cycle count had to
  arrive from somewhere else.
- Gauges can be looked up one at a time, which is how the channel limit
  reaches the rail hit check.

## 0.5.0 - 2026-04-20

### Added

- `shearstud report structure`, `report inventory` and `report overdue`. A
  structure report writes an absence out as a line rather than leaving the line
  out, and `--silences` prints only those.
- A lightweight structure summary in the store, read by the listing and the
  reports.

### Changed

- `shearstud structure list` reads summaries rather than whole structures. It
  used to load every plate of every section run to print one line each.

## 0.4.0 - 2026-04-13

### Added

- `shearstud shear` rates a structure in shear. It is a separate run from the
  moment rating and not an option on it: it rates the abutments, which the
  moment run skips, and shear at an abutment is the largest it gets anywhere.
  `--ends-only` prints just those stations.
- Shear ratings are stored alongside moment ratings in the book, under their
  own load effect, so a structure can carry both.

### Changed

- The rating run can write itself into the book. It used to be the command
  line that knew how, which meant nothing else could store a run, and the
  programme ranking reads the book rather than the run.

## 0.3.0 - 2026-03-22

### Added

- The programme layer: inspection intervals, priority banding and the office
  worklist. `shearstud program record`, `program show`, `program worklist` and
  `program due`.
- A `programme` table for what an inspection found: condition rating, traffic,
  detour and whether a limit is posted. It is the one table in the book that
  is overwritten rather than appended to, because there is no such thing as
  last year's current condition rating.
- Truck event extraction from a strain record, with a two level trigger so a
  signal hovering near the threshold does not become a hundred events.
- `check_wiring`, which fails the build on a public function nothing calls,
  and `check_readme`, which checks the commands the README tells you to run.

### Changed

- **Changes results.** The fatigue re-evaluation interval is gone and the
  inspection interval rule has replaced it. The old rule divided the remaining
  life by four; the new one is the twelve, twenty four or forty eight months
  the regulation allows, decided by the condition rating, the posting and the
  fatigue life together.
- An unmeasured structure is credited a hundred years of fatigue life rather
  than being treated as unknown. Not knowing is not the same as knowing it is
  bad, and putting every ungauged structure in the retrofit band buries the
  ones that are cracking.
- Limited redundancy is now recorded as its own word and treated as non
  redundant everywhere a rule acts on it.

## 0.2.0 - 2026-02-06

### Added

- Continuous unit analysis by the three moment equation, with exact moving
  load traversal.
- Fatigue evaluation end to end: rainflow counting checked against the worked
  example in ASTM E1049, Miner damage, infinite life truncation and remaining
  life with the traffic growing.
- The book of record: numbered migrations, digest locked, with the inventory,
  measurement and assessment schemas.
- Continuous integration, and `check.sh` to run the same gates locally.

### Fixed

- **Changes results.** Temperature compensation now runs before the drift fit
  and not after it. With a measured companion channel the subtraction is exact
  and has to come first; doing the drift fit first lets it swallow part of the
  thermal ramp, which the later subtraction then removes twice.
- **Changes results.** The Fatigue I stud coefficient was 38, which is the
  Category A detail constant. AASHTO gives 5.5.
- **Changes results.** Two rolled shape catalogue rows had the wrong flange
  width. Caught by the self consistency test against the published areas.
- Correcting a campaign's seasonal factor no longer destroys every cycle count
  on it. The save was a delete and insert, and the delete cascaded.

## 0.1.0 - 2025-01-14

### Added

- Section properties from a plate idealisation, the three stage composite
  stack, effective flange width under both the current and the pre 2008 rules,
  and the section schedule along a girder.
