# A structure from the drawings to the worklist

This is the whole of it, in the order an office actually does it, on the
example that ships with the repository. Every command here is checked against
the command tree by `check_docs`, so a command that gets renamed breaks this
document rather than wasting somebody's afternoon.

## 1. Get the geometry in

```
shearstud init
shearstud structure import examples/salt-fork-creek.json --grade A36 --adtt 1200 --surface minor
shearstud structure show 18-SH-0473
```

The import is the only place the drawings are read. Everything after this works
off the book.

The four judgement fields go in here rather than being typed at every command
that needs them: the steel grade off the drawing, the truck traffic off the
count, the member condition and the riding surface off the last inspection. A
rating that started from the defaults because somebody forgot one of these
comes back plausible and low, which is the worst kind of wrong.

## 2. Rate it

```
shearstud rate 18-SH-0473 --stations 10 --save
shearstud shear 18-SH-0473 --ends-only
shearstud posting 18-SH-0473 --save
```

Moment and shear are separate runs because they are different problems: the
shear run rates the abutments, which the moment run skips, and takes its
capacity off the web rather than the section.

`--save` is not the default anywhere. A rating you have not looked at is not a
rating you want in the book of record.

## 3. Look at what the section actually is

```
shearstud structure section 18-SH-0473 G2 --station-ft 48
shearstud structure details 18-SH-0473 --computed
```

The section command reports all three composite stages, because a dead load
stress worked out on the short term section is worked out on a section that did
not exist when the load went on.

`--computed` puts the fatigue truck across every detail and orders by the
stress range. A category on its own does not say which detail is in trouble.

## 4. Put a meter on the corroded end

```
shearstud thickness import 18-SH-0473 G2 sheet.csv --measured 2026-04-02
shearstud thickness loss 18-SH-0473 G2
shearstud rate 18-SH-0473 --measured --save
```

The readings are remaining thickness, because that is what the meter reads. The
loss is worked against the plate on the drawing and is not stored, so a
corrected drawing does not leave every stored loss wrong with nothing to say
so.

## 5. Instrument it and count the cycles

```
shearstud gauge add G2-BF-01 18SH0473-G2-D1 --installed 2026-03-30
shearstud campaign add C-2026-04 18-SH-0473 --from 2026-04-01 --to 2026-04-14
shearstud record C-2026-04 G2-BF-01 strain.csv --rate-hz 100 --save
shearstud campaign show C-2026-04
```

`campaign show` is the one to read afterwards, because it lists the gauges that
did **not** report. A campaign that counted cycles on three of five channels
looks complete in any listing of what it has.

## 6. Evaluate the fatigue

```
shearstud fatigue evaluate 18-SH-0473 C-2026-04 --computed --save
```

Measured details get their measurement. The rest get the fatigue truck, printed
under their own heading, because the two are different evidence.

## 7. Put it on the programme

```
shearstud program record 18-SH-0473 --condition 6 --inspected 2026-03-12 --traffic 2600
shearstud program show 18-SH-0473
shearstud report structure 18-SH-0473 --silences
```

`--silences` is the shortest useful summary of a structure this tool produces:
the list of everything nobody has done to it.

## 8. Read the district's picture

```
shearstud program worklist
shearstud report inventory
shearstud report overdue
```

The worklist prints what it could not rank before what it could. A structure
with no inspection row or no stored rating is left off the ranking rather than
ranked on a default, because a structure ranked on a guess sits in the middle
of the list where nobody looks at it again.

## 9. Hand the book on

```
shearstud book counts
shearstud book export district7.json
```

Once a year, and the file carries the schema version it was written at.
