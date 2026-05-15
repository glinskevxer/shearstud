# shearstud

Fatigue accounting and load rating for instrumented steel girder bridges.

This is the tool a state bridge management office uses to answer three
questions about a steel girder structure, in this order:

1. **can it carry the legal loads?** An AASHTO LRFR rating, station by station,
   girder by girder, against the legal fleet, with a posting decision if the
   answer is no.
2. **how much fatigue life is left in it?** Rainflow counting on the strain a
   gauge actually recorded, Miner damage against the detail's category, and a
   remaining life with the traffic growing.
3. **when does somebody go and look at it again?** The inspection interval that
   comes out of the first two answers together with the condition rating, and
   the office's worklist across the whole inventory.

The three are separate because they are answered by different people on
different clocks, and they are in one tool because the third one needs the
first two and does not get them anywhere else.

## What it is not

It is not a design tool. Nothing here proportions a girder; it takes girders
that exist and works out what they can do. It is not a finite element program:
the analysis is line girder, the influence lines are exact for the beam and the
distribution factors are AASHTO's. And it is not a data logger front end. It
reads cycle counts and strain records that something else recorded.

## Installing

Python 3.12 or 3.13.

```
python -m pip install -e ".[dev]" -c constraints.txt
```

`constraints.txt` pins every version. It is there because a rating is a number
somebody signs, and a number that changes when a dependency is upgraded is a
number nobody can defend.

## Getting started

```
shearstud init
shearstud structure import examples/salt-fork-creek.json
shearstud rate 18-SH-0473 --save
shearstud shear 18-SH-0473 --ends-only
shearstud posting 18-SH-0473
```

Moment and shear are separate commands because they are separate runs. The
shear run rates the abutments, which the moment run skips because moment there
is zero, and shear at an abutment is the largest it gets anywhere.

`shearstud --help` lists everything. The full command reference, generated from
the command tree itself, is in [docs/commands.md](docs/commands.md).

The `--book` option picks which book of record to work in, and it goes before
the command:

```
shearstud --book /var/lib/bridges/district7.sqlite3 structure list
```

An office runs several books, one per district, and a command that quietly
wrote into the wrong one would be a bad afternoon.

## Measurement and fatigue

```
shearstud gauge add G2-BF-01 18SH0473-G2-D1 --installed 2026-03-30
shearstud campaign add C-2026-04 18-SH-0473 --from 2026-04-01 --to 2026-04-14
shearstud record C-2026-04 G2-BF-01 strain.csv --rate-hz 20 --save
shearstud spectrum C-2026-04 G2-BF-01 counts.csv
shearstud fatigue evaluate 18-SH-0473 C-2026-04 --save
```

`record` takes a raw logger file the whole way: it looks for dropouts and rail
hits on the raw samples, conditions the record, counts the cycles, and pulls
the individual truck events out alongside. Defects are looked for first and on
purpose. A dropout is a flat run at whatever the logger writes when the bridge
is gone and a rail hit is a sample at the channel limit, and conditioning moves
both of those somewhere else. `spectrum` is the shorter road in, for when
something upstream has already done the counting.

The evaluation reports what it skipped as well as what it evaluated. A detail
with no gauge on it, a gauge that reads transverse strain, and a record too
noisy to trust are all reasons a detail is not evaluated, and all three are
silences unless something says so.

## The programme

```
shearstud program record 18-SH-0473 --condition 6 --inspected 2026-03-12
shearstud program worklist
shearstud program due
```

The worklist prints the structures it could **not** rank before the ones it
could. A structure with no inspection row or no stored rating is left off the
ranking rather than ranked on a default, because a structure ranked on a guess
sits in the middle of the list where nobody looks at it again.

Ranking is by band and not by score. A structure that cannot carry the legal
loads is in the first band whatever its traffic is; only inside a band does
traffic decide the order. Adding a consequence term to a condition term is what
lets a sound bridge on a busy road outrank a posted one, and no set of weights
fixes that, because the two terms answer different questions.

## Vehicles and permits

```
shearstud vehicle list --class legal
shearstud vehicle show TYPE3
shearstud vehicle envelope TYPE3 --span-ft 90
shearstud permit 18-SH-0473 TYPE3-3
```

`permit` rates the vehicle at every level of control the permit allows and
prints all of them, not only the one that clears. An engineer deciding whether
to escort a load needs to see that escorting would have made it issuable, and
an agency that always answers "escorted" is charging for margin it does not
need.

## Section loss

```
shearstud thickness import 18-SH-0473 G1 sheet.csv --measured 2026-04-02
shearstud thickness loss 18-SH-0473 G1
shearstud thickness rate 18-SH-0473
shearstud rate 18-SH-0473 --measured
```

Readings are remaining thickness, because that is what the meter reads, and
the loss is worked out against the plate on the drawing rather than stored. A
location measured twice is a corrosion rate; measured once it is a number, and
`thickness rate` says which of those it has.

`--measured` rates the reduced sections. The reduction is run by run, so
corrosion under a leaking joint at one end does not take a sixteenth off the
heavy section over the pier. Asking for it on a structure nobody has measured
is not an error and does not silently rate the drawing either: it says which it
did.

## Reports

```
shearstud report structure 18-SH-0473
shearstud report structure 18-SH-0473 --silences
shearstud report inventory
shearstud report overdue
```

A structure report writes out what is missing as a line rather than leaving the
line out. `--silences` prints only those lines, which is the shortest useful
summary this tool produces: it is the list of everything nobody has done to the
structure.

## How it is laid out

Imports run one way through the package, and
[docs/architecture.md](docs/architecture.md) has the table the build enforces.
Briefly, from the bottom up: `geometry` for sections and composite stages,
`loads` and `signals` above it, then `fatigue` and `structure`, then `rating`,
then `program`, then `store`, then `analysis`, and `cli` on top.

`program` sitting below `store` reads backwards until you look at what the
store does. Every repository imports the types it persists and none of them is
imported by one, so a programme type the book has a table for has to be
underneath the book.

## The book of record

One SQLite file. Conclusions are append only: a rating from 2019 is not
corrected when a better one is worked in 2026, both are kept and dated, and the
newest one is the answer. That is not a preference. It is what the record has
to look like when a structure posted in 2019 and unposted in 2026 comes up in a
claim.

The schema is in [docs/schema.md](docs/schema.md), generated from the
migrations. Migrations are numbered, applied in order, and frozen once applied:
each one's digest is recorded in `migrations.lock` and the build fails if an
applied migration is edited. The remedy for a wrong migration is always another
migration.

## Looking after the book

```
shearstud book counts
shearstud book prune --before 2014-01-01
shearstud book prune --before 2014-01-01 --yes --vacuum
```

Pruning is the only thing this tool deletes on purpose, and it takes two
separate agreements. `--yes` is one. The other is the cutoff itself: the store
refuses any cutoff inside the ten year retention policy, whatever the command
line says. Each structure keeps its newest rating and posting and each detail
keeps its newest evaluation, so a structure last rated in 1998 loses nothing.

## Checking the repository

```
./check.sh
```

That runs everything CI runs: the linter, the type checker, every `check_*`
self check, every generated document in `--check` form, the whole suite, and
the end to end smoke run.

The self checks are the unusual part and they are worth explaining. They walk
this repository's own source and fail the build on things a linter has no
opinion about: an import that runs the wrong way through the layers, a float
parameter with no unit in its name, a public function nothing calls, a test
that asserts nothing, SQL outside the store, a module with no test file. Every
one of them was written after it found a real defect in this code, and several
of them found more than one.

## Units

Every dimensioned name carries its unit: `station_ft`, `range_ksi`,
`peak_ue`, `detour_mi`, `capacity_kipft`. This is checked rather than intended,
by `check_units`, because the alternative is `length` meaning feet in one
module and inches in the next, and because a fatigue calculation that mixes ksi
and psi is off by a factor of a million and still returns a plausible looking
number of years.

## What changed and when

[CHANGELOG.md](CHANGELOG.md), newest first. Entries that alter a number are
marked **Changes results**, and those are the ones a rating engineer has to
read: a rating worked before one of those and a rating worked after it are
different numbers, and somebody will have to explain why.

## Licence

Not licensed for redistribution.
