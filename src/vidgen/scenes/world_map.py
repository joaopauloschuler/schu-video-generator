"""``map``: a world map (Natural Earth 1:110m countries, Equal Earth projection) with highlighted
countries, a choropleth with a colour-scale legend, pins and flight-path arcs, revealed step by
step, with an optional camera move onto a step.

Map data, lookups and the projection are the public helpers of ``vidgen.api`` (``MapView``,
``find_country``, ``world_countries``, ``view_box``, ``fit_view``).
"""

import logging
from collections.abc import Callable
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .actions import MoveCamera
from .pie import window

log = logging.getLogger("vidgen.scenes")

#: ``view`` values besides a box.
VIEW_NAMES: tuple[str, ...] = ("auto", *MAP_VIEWS)
#: Land is ``land_color`` at this opacity over the background (opaque).
LAND_MIX = 0.3
#: Stroke width of the borders (drawn in the background colour).
BORDER = 0.8
#: Opacity of the plates under labels.
PLATE_OPACITY = 0.88
#: Bend of an arc (radians of the circle it is part of): flight-path style.
ARC_ANGLE = TAU / 5
#: Leader lines lie under every label plate (z-index 4), above pins (3) and arcs (2).
LEADER_Z = 3.5
#: Land without a value on a choropleth: fainter than land on other maps, so it recedes.
NO_DATA_MIX = 0.18
#: Gap between the title and the map.
TITLE_GAP = 0.4


def _known_country(value: str) -> str:
    try:
        find_country(value)
    except VidgenError as e:
        raise ValueError(str(e)) from None
    return value


class MapCountry(SceneParams):
    """A highlighted country: its name or code, or ``{country, color, label}``."""

    also_accepts = (str,)

    country: str
    """Name or ISO 3166 code (alpha-2 or alpha-3): Germany, DE, DEU; aliases such as USA, UK, Holland work."""
    color: ThemeColor | None = None
    """Fill colour; default: the scene's highlight_color."""
    label: str | bool | None = None
    """Its label: a text, true (its name) or false (none); default: the scene's labels."""

    @model_validator(mode="before")
    @classmethod
    def _from_name(cls, data: Any) -> Any:
        return {"country": data} if isinstance(data, str) else data

    @field_validator("country")
    @classmethod
    def _check(cls, value: str) -> str:
        return _known_country(value)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A country's name or code alone is also a country (JSON Schema ``anyOf``)."""
        return {"anyOf": [handler(core_schema), {"type": "string", "minLength": 1}]}


class MapPin(SceneParams):
    """A pin: ``{lon, lat, label}``, or ``{country, label}`` (at the country's label point)."""

    lon: float | None = Field(default=None, ge=-180, le=180)
    """Longitude in degrees (east positive)."""
    lat: float | None = Field(default=None, ge=-90, le=90)
    """Latitude in degrees (north positive)."""
    country: str | None = None
    """Instead of lon / lat: put the pin in the middle of this country."""
    label: str = ""
    """Text beside the pin (arcs can start or end at a pin by its label)."""
    color: ThemeColor | None = None
    """Pin colour; default: the scene's pin_color."""

    @field_validator("country")
    @classmethod
    def _check(cls, value: str | None) -> str | None:
        return None if value is None else _known_country(value)

    @model_validator(mode="after")
    def _where(self) -> "MapPin":
        if self.country is not None and (self.lon is not None or self.lat is not None):
            raise ValueError("a pin has either lon and lat or a country, not both")
        if self.country is None and (self.lon is None or self.lat is None):
            raise ValueError("a pin needs lon and lat (degrees), or a country")
        return self

    def where(self) -> tuple[float, float]:
        """``(lon, lat)``."""
        if self.country is not None:
            return find_country(self.country).label
        return float(self.lon), float(self.lat)  # type: ignore[arg-type]


ArcEnd = str | list[float]


class MapArc(SceneParams):
    """An arc: ``{from, to, label, color}`` or ``"A -> B"``; an end is a pin label, a country or
    ``[lon, lat]``."""

    also_accepts = (str,)

    start: ArcEnd = Field(alias="from")
    """Where it starts: a pin's label, a country (its middle) or [lon, lat]."""
    to: ArcEnd
    """Where it ends (the arrowhead): a pin's label, a country or [lon, lat]."""
    label: str = ""
    """Text at the top of the arc."""
    color: ThemeColor | None = None
    """Arc colour; default: the scene's arc_color."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        if isinstance(data, str):
            parts = [p.strip() for p in data.split("->")]
            if len(parts) != 2 or not all(parts):
                raise ValueError(f"an arc written as text is 'A -> B', got {data!r}")
            return {"from": parts[0], "to": parts[1]}
        return data

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """``"A -> B"`` is also an arc (JSON Schema ``anyOf``)."""
        return {"anyOf": [handler(core_schema), {"type": "string", "pattern": "^.+->.+$"}]}

    @field_validator("start", "to")
    @classmethod
    def _point(cls, value: ArcEnd) -> ArcEnd:
        if isinstance(value, list):
            if len(value) != 2 or not (-180 <= value[0] <= 180 and -90 <= value[1] <= 90):
                raise ValueError(f"an arc end as coordinates is [lon, lat] in degrees, got {value}")
        elif not value.strip():
            raise ValueError("an arc end cannot be empty")
        return value


class MapStep(SceneParams):
    """A step: ``{countries, pins, arcs, focus}``, or a list of countries, or one country."""

    also_accepts = (list, str)

    countries: list[MapCountry] = []
    """Countries highlighted at this step."""
    pins: list[MapPin] = []
    """Pins dropped at this step."""
    arcs: list[MapArc] = []
    """Arcs drawn at this step."""
    focus: bool | float = False
    """Move the camera in on this step's countries, pins and arcs (labels stay readable); a number is the magnification (more than 1, up to 4), true: as close as fits, up to focus_scale."""

    @model_validator(mode="before")
    @classmethod
    def _shorthand(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"countries": data}
        if isinstance(data, str):
            return {"countries": [data]}
        return data

    @field_validator("focus")
    @classmethod
    def _check_focus(cls, value: bool | float) -> bool | float:
        if not isinstance(value, bool) and not 1 < value <= 4:
            raise ValueError("a focus magnification is more than 1 and at most 4 (or true: as close as fits)")
        return value

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A list of countries, or one country, is also a step (JSON Schema ``anyOf``)."""
        full = handler(core_schema)
        countries = handler.resolve_ref_schema(full)["properties"]["countries"]
        return {"anyOf": [full, countries, countries["items"]]}

    def empty(self) -> bool:
        """Whether the step adds nothing."""
        return not (self.countries or self.pins or self.arcs)


def _hits(a: Region, b: Region, air: float = 0.04) -> bool:
    return not (a.x1 + air <= b.x0 or b.x1 + air <= a.x0 or a.y1 + air <= b.y0 or b.y1 + air <= a.y0)


def _shape(polygons: list[list[np.ndarray]]) -> VMobject:
    """A VMobject of polygons (rings of scene points; holes stay open with a non-zero fill
    because they run the other way), each ring a closed subpath of straight segments."""
    chunks = []
    for poly in polygons:
        for ring in poly:
            pts = np.vstack([ring, ring[:1]])
            a, b = pts[:-1], pts[1:]
            chunks.append(np.stack([a, a + (b - a) / 3, a + 2 * (b - a) / 3, b], axis=1).reshape(-1, 3))
    shape = VMobject()
    if chunks:
        shape.set_points(np.concatenate(chunks))
    return shape


@scene("map")
class WorldMap(NarratedScene):
    """Beat 1 draws the map (a sweep from west to east, a choropleth's colours with it), the
    legend, the countries / pins / arcs given outside ``steps`` and then step 1; step *i* (an
    entry of ``steps``) highlights its countries, drops its pins and draws its arcs at beat *i*.
    A step with ``focus`` moves the camera in on its items (the next step without it moves back;
    labels built for another view fade). More steps than beats are spread evenly; extra beats
    hold.

    Action targets: ``title``, ``map`` (every country), ``legend``, ``country:<code>`` (a
    highlighted or valued country, by its alpha-3 code, alpha-2 code or name), ``pin<N>``,
    ``pin:<label>``, ``arc<N>``, ``step<N>`` (a step's items).
    """

    outro = 0.5
    target_patterns = ("title", "map", "legend", "country:<code>", "pin<N>", "pin:<label>", "arc<N>", "step<N>")

    class Params(SceneParams):
        title: str = ""
        """Heading above the map."""
        view: str | list[float] = "auto"
        """What the map shows: auto (fits the countries, pins and arcs; the world when there are none), world, europe, africa, asia, middle_east, north_america, south_america, oceania, or [lon_min, lat_min, lon_max, lat_max] (lon_max < lon_min crosses the date line)."""
        countries: list[MapCountry] = []
        """Countries highlighted with the map in beat 1."""
        pins: list[MapPin] = []
        """Pins shown with the map in beat 1."""
        arcs: list[MapArc] = []
        """Arcs drawn with the map in beat 1."""
        steps: list[MapStep] = []
        """Step i at beat i: {countries, pins, arcs, focus}, a list of countries, or one country."""
        values: dict[str, float] = {}
        """Choropleth: a value per country ({Germany: 83, FR: 68}); countries are coloured by a colour scale with a legend."""
        labels: bool = True
        """Write the name of each highlighted country (a country's label overrides it)."""
        highlight_color: Literal["palette"] | ThemeColor = "accent"
        """Fill of highlighted countries, or 'palette' (one theme palette colour per country); on a choropleth, the outline colour."""
        land_color: ThemeColor = "dim"
        """Colour of the land (shown faint over the background)."""
        pin_color: ThemeColor = "highlight"
        """Default pin colour."""
        arc_color: ThemeColor = "highlight"
        """Default arc colour."""
        antarctica: bool = False
        """Draw Antarctica (the world view then reaches the South Pole)."""
        scale: Literal["auto", "sequential", "diverging"] = "auto"
        """Choropleth colour scale: sequential (low to high), diverging (two colours either side of center); auto: diverging when the values have both signs around center."""
        color: ThemeColor = "primary"
        """Sequential scale: the colour of the highest values."""
        low_color: ThemeColor = "primary"
        """Diverging scale: the colour below center."""
        high_color: ThemeColor = "accent"
        """Diverging scale: the colour above center."""
        center: float = 0.0
        """Diverging scale: the neutral middle value."""
        scale_min: float | None = None
        """Value at the low end of the scale; default: the data's minimum (diverging: symmetric around center)."""
        scale_max: float | None = None
        """Value at the high end of the scale; default: the data's maximum."""
        value_format: str | None = None
        """Python format for the legend ticks, e.g. '{:.1f}'; default: the decimals the values need."""
        unit: str = ""
        """Appended to the legend ticks."""
        legend: bool = True
        """Show the choropleth's colour scale as a bar below the map."""
        legend_label: str = ""
        """Title over the legend bar (what the colour means)."""
        label_size: ThemeSize = "caption"
        """Size of country, pin and arc labels (never below the readable size)."""
        focus_scale: float = Field(default=3.0, gt=1.0, le=4.0)
        """Largest magnification of focus: true."""
        caption: str = ""
        """Note under the map (e.g. the data source)."""
        caption_size: ThemeSize = "caption"
        """Caption text size."""
        caption_color: ThemeColor = "dim"
        """Caption color."""
        title_size: ThemeSize = "heading"
        """Title size (1.3x in a portrait frame)."""
        title_color: ThemeColor = "text"
        """Title color."""

        @field_validator("view")
        @classmethod
        def _view(cls, value: str | list[float]) -> str | list[float]:
            if isinstance(value, str):
                if value not in VIEW_NAMES:
                    raise ValueError(f"unknown view {value!r}; use {', '.join(VIEW_NAMES)} or [lon_min, lat_min, lon_max, lat_max]")
                return value
            if len(value) != 4:
                raise ValueError(f"a view box is [lon_min, lat_min, lon_max, lat_max], got {len(value)} numbers")
            lon0, lat0, lon1, lat1 = value
            if not all(-180 <= v <= 180 for v in (lon0, lon1)) or not all(-90 <= v <= 90 for v in (lat0, lat1)):
                raise ValueError(f"view box {value}: longitudes are -180..180 and latitudes -90..90")
            if lat1 <= lat0:
                raise ValueError(f"view box {value}: lat_max must be greater than lat_min")
            if lon0 == lon1:
                raise ValueError(f"view box {value}: lon_min and lon_max must differ")
            return value

        @field_validator("values")
        @classmethod
        def _values(cls, value: dict[str, float]) -> dict[str, float]:
            seen: dict[str, str] = {}
            for name in value:
                code = find_country(_known_country(name)).a3
                if code in seen:
                    raise ValueError(f"values: {name!r} and {seen[code]!r} are the same country")
                seen[code] = name
            return value

        @field_validator("value_format")
        @classmethod
        def _format(cls, v: str | None) -> str | None:
            return None if v is None else check_format(v)

        @model_validator(mode="after")
        def _consistent(self) -> SceneParams:
            seen: dict[str, str] = {}
            for k, step in enumerate(self.stages()):
                where = "countries" if k == 0 else f"steps[{k - 1}]"
                for item in step.countries:
                    code = find_country(item.country).a3
                    if code in seen:
                        raise ValueError(f"{where}: {item.country!r} is already highlighted ({seen[code]}); highlight a country once")
                    seen[code] = where
            labels = [p.label for _, p in self.all_pins() if p.label.strip()]
            dupes = sorted({x for x in labels if labels.count(x) > 1})
            if dupes:
                raise ValueError(f"pin labels must be unique: {', '.join(dupes)}")
            for _, arc in self.all_arcs():
                a, b = self.arc_end(arc.start), self.arc_end(arc.to)
                if np.allclose(a, b):
                    raise ValueError(f"arc from {arc.start!r} to {arc.to!r}: the ends are the same point")
            if self.values:
                if self.scale_min is not None and self.scale_max is not None and self.scale_max <= self.scale_min:
                    raise ValueError("scale_max must be greater than scale_min")
                if self.kind() == "diverging":
                    lo = self.scale_min if self.scale_min is not None else -np.inf
                    hi = self.scale_max if self.scale_max is not None else np.inf
                    if not lo < self.center < hi:
                        raise ValueError(f"center {self.center:g} must lie between scale_min and scale_max")
            for k, step in enumerate(self.steps):
                if step.focus and step.empty():
                    raise ValueError(f"steps[{k}]: focus needs countries, pins or arcs to move in on")
            return self

        def stages(self) -> list[MapStep]:
            """The items shown with the map (stage 0), then ``steps`` (stage i = step i)."""
            return [MapStep(countries=self.countries, pins=self.pins, arcs=self.arcs), *self.steps]

        def all_pins(self) -> list[tuple[int, MapPin]]:
            """Every pin with its stage, in order (``pin<N>`` numbering)."""
            return [(k, p) for k, s in enumerate(self.stages()) for p in s.pins]

        def all_arcs(self) -> list[tuple[int, MapArc]]:
            """Every arc with its stage, in order (``arc<N>`` numbering)."""
            return [(k, a) for k, s in enumerate(self.stages()) for a in s.arcs]

        def highlighted(self) -> list[tuple[int, MapCountry, Country]]:
            """Every highlighted country with its stage, in order."""
            return [(k, c, find_country(c.country)) for k, s in enumerate(self.stages()) for c in s.countries]

        def valued(self) -> dict[str, float]:
            """The choropleth values by alpha-3 code."""
            return {find_country(name).a3: float(v) for name, v in self.values.items()}

        def target_countries(self) -> list[Country]:
            """Countries with a ``country:`` target: highlighted ones, then valued ones."""
            out = {c.a3: c for _, _, c in self.highlighted()}
            for name in self.values:
                c = find_country(name)
                out.setdefault(c.a3, c)
            return list(out.values())

        def arc_end(self, end: ArcEnd) -> tuple[float, float]:
            """``(lon, lat)`` of an arc end: a pin's label, else a country, else coordinates."""
            if isinstance(end, list):
                return float(end[0]), float(end[1])
            for _, pin in self.all_pins():
                if pin.label.strip() and pin.label == end:
                    return pin.where()
            try:
                return find_country(end).label
            except VidgenError:
                raise ValueError(f"arc end {end!r} is neither a pin label nor a country") from None

        def kind(self) -> str:
            """The choropleth's ``sequential`` or ``diverging`` scale (``auto`` resolved)."""
            if self.scale != "auto":
                return self.scale
            known = list(self.values.values())
            return "diverging" if known and min(known) < self.center < max(known) else "sequential"

        def points(self) -> list[tuple[float, float]]:
            """Lon/lat points the ``auto`` view fits: the main box corners of highlighted and
            valued countries, pins and arc ends."""
            pts: list[tuple[float, float]] = []
            for c in [c for _, _, c in self.highlighted()] + [find_country(n) for n in self.values]:
                x0, y0, x1, y1 = c.main
                pts += [(x0, y0), (x1, y1)]
            pts += [p.where() for _, p in self.all_pins()]
            for _, a in self.all_arcs():
                pts += [self.arc_end(a.start), self.arc_end(a.to)]
            return pts

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``title`` (if any), ``map``, ``legend`` (choropleth), ``country:<a3>`` /
        ``country:<a2>`` / ``country:<name>`` per highlighted or valued country, ``pin<N>`` (+
        ``pin:<label>``), ``arc<N>``, ``step<N>`` per step with items."""
        names = (["title"] if params.title else []) + ["map"] + (["legend"] if params.values and params.legend else [])
        for c in params.target_countries():
            names += cls._country_names(c)
        for n, (_, pin) in enumerate(params.all_pins(), start=1):
            names += [f"pin{n}"] + ([f"pin:{pin.label}"] if pin.label.strip() else [])
        names += [f"arc{n}" for n in range(1, len(params.all_arcs()) + 1)]
        return names + [f"step{k + 1}" for k, step in enumerate(params.steps) if not step.empty()]

    @staticmethod
    def _country_names(c: Country) -> list[str]:
        return list(dict.fromkeys(f"country:{x}" for x in (*c.codes, c.name)))

    # ----- construct ---------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, color=p.title_color)
            body = body.below(title, gap=TITLE_GAP)
        cap = None
        if p.caption:
            cap = chart_caption(p.caption, body, size=p.caption_size, color=p.caption_color)
            body = body.above(cap, gap=0.3)
        self._body = body
        self._size = chart_label_size(p.label_size)
        self._scale = None
        bar = None
        if p.values:
            values = list(p.values.values())
            self._scale = color_scale(values, kind=p.kind(), color=p.color, low_color=p.low_color, high_color=p.high_color, center=p.center, lo=p.scale_min, hi=p.scale_max)
            if p.legend:
                bar = color_bar(self._scale, min(body.width * 0.6, 5.0), vertical=False, size=self._size, title=p.legend_label, fmt=p.value_format, unit=p.unit)
        self._view = self._fit(body, bar)
        if bar is not None:
            m = self._view.region
            bar.move_to([m.center[0], m.y0 - 0.3 - bar.height / 2, 0])
        self._countries = self._base()
        self._panel = None
        if self._view.cropped:  # a regional view: the map is a panel with the sea in it
            r = self._view.region
            self._panel = Rectangle(width=r.width, height=r.height).move_to(r.center)
            self._panel.set_fill(self.theme.color("surface"), opacity=1).set_stroke(self.theme.color("dim"), width=1.5, opacity=0.6).set_z_index(-1)
        self._cameras = [self._camera(k) for k in range(len(p.stages()))]
        self._build_items()
        self._register(title, bar)
        self._camera_at: tuple[float, tuple[float, float]] | None = None

        def intro() -> list[Animation]:
            anims = self.entrance("map")
            for name in ("title", "legend"):
                if self.find_targets(name):
                    anims += self.entrance(name)
            if cap is not None and not self.on_screen_parts(cap):
                anims.append(FadeIn(cap))
            return anims + self._arrive(0, start=0.45)

        steps: list[Callable[[], list[Animation]]] = [(lambda k=k: self._step(k)) for k in range(1, len(p.stages()))]
        plan = distribute(len(steps), len(self.beats))
        for i, d in self.timeline():
            self.play_steps(d, ([intro] if i == 0 else []) + [steps[k] for k in plan[i]], fraction=0.6, cap=1.6)
        self.finish()

    # ----- layout ------------------------------------------------------------------------------

    def _fit(self, body: Region, bar: Mobject | None) -> MapView:
        """The map view in ``body`` (above the legend), the map and legend centred together."""
        p = self.params
        box = fit_view(p.points()) if p.view == "auto" else view_box(p.view, p.antarctica)
        if p.view == "auto" and box == MAP_VIEWS["world"] and p.antarctica:
            box = view_box("world", True)
        if self.is_portrait and p.view in ("auto", "world") and box[2] - box[0] >= 359.0:
            box = self._portrait_world(box)
        below = bar.height + 0.3 if bar is not None else 0.0
        area = Region(body.x0, body.y0 + below, body.x1, body.y1)
        view = MapView(box, area, antarctica=p.antarctica)
        if below:
            h = view.region.height
            top = body.center[1] + (h + below) / 2
            view = MapView(box, Region(body.x0, top - h, body.x1, top), antarctica=p.antarctica)
        return view

    #: A world view in a vertical frame keeps only the longitudes of its items (with this share
    #: of their span added on each side, at least :attr:`portrait_world_min` degrees): the
    #: whole world is a thin strip across a 9:16 frame.
    portrait_world_pad = 0.12
    portrait_world_min = 140.0

    def _portrait_world(self, box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        """``box`` (the world) narrowed to the longitudes of the map's items, all latitudes
        kept; unchanged when they span (almost) the whole world or there are none."""
        lons = [lon for lon, _ in self.params.points()]
        if not lons:
            return box
        spans = [(min(lons), max(lons)), (min(x + 360.0 if x < 0 else x for x in lons), max(x + 360.0 if x < 0 else x for x in lons))]
        lo, hi = min(spans, key=lambda s: s[1] - s[0])
        width = max((hi - lo) * (1 + 2 * self.portrait_world_pad), self.portrait_world_min)
        if width >= 300.0:
            return box
        middle = (lo + hi) / 2
        return middle - width / 2, box[1], middle + width / 2, box[3]

    def _base(self) -> dict[str, VMobject]:
        """Every country in view as a filled shape (land colour, or its choropleth colour) with
        borders in the background colour."""
        p = self.params
        land = mix_colors(self.theme.color(p.land_color), self.theme.background, NO_DATA_MIX if p.values else LAND_MIX)
        valued = p.valued()
        shapes: dict[str, VMobject] = {}
        for c in world_countries(p.antarctica):
            polys = self._view.polygons(c)
            if not polys:
                continue
            fill = self._scale(valued[c.a3]) if c.a3 in valued and self._scale is not None else land
            shape = _shape(polys).set_fill(fill, opacity=1).set_stroke(self.theme.background, width=BORDER)
            shapes[c.a3] = shape
        return shapes

    def _item_regions(self, step: MapStep) -> list[Region]:
        """Scene rectangles of a step's items (countries' main boxes, pins, arc ends)."""
        p = self.params
        view = self._view
        out = []
        for item in step.countries:
            r, m = view.box_region(find_country(item.country).main), view.region
            x0, y0 = min(max(r.x0, m.x0), m.x1), min(max(r.y0, m.y0), m.y1)
            out.append(Region(x0, y0, max(min(r.x1, m.x1), x0), max(min(r.y1, m.y1), y0)))
        pts = [view.point(*pin.where()) for pin in step.pins]
        for arc in step.arcs:
            pts += [view.point(*p.arc_end(arc.start)), view.point(*p.arc_end(arc.to))]
        out += [Region(float(q[0]) - 0.05, float(q[1]) - 0.05, float(q[0]) + 0.05, float(q[1]) + 0.05) for q in pts]
        return out

    def _camera(self, k: int) -> tuple[float, tuple[float, float]] | None:
        """Camera (width, centre) of stage ``k``'s focus, or ``None`` (the whole frame)."""
        p = self.params
        step = p.stages()[k]
        if not step.focus:
            return None
        regions = self._item_regions(step)
        x0, x1 = min(r.x0 for r in regions), max(r.x1 for r in regions)
        y0, y1 = min(r.y0 for r in regions), max(r.y1 for r in regions)
        fw, fh = self.frame_width, self.frame_height
        limit = p.focus_scale if step.focus is True else float(step.focus)
        m = min(limit, 0.6 * fw / max(x1 - x0, 1e-6), 0.6 * fh / max(y1 - y0, 1e-6))
        if m < 1.05:
            log.warning("scene '%s': step %d: its items already fill the frame; no focus", self.spec.id, k)
            return None
        w, h = fw / m, fh / m
        x = float(np.clip((x0 + x1) / 2, (w - fw) / 2, (fw - w) / 2))
        y = float(np.clip((y0 + y1) / 2, (h - fh) / 2, (fh - h) / 2))
        return w, (x, y)

    def _bounds(self, k: int) -> tuple[Region, float]:
        """Where stage ``k``'s labels may go and the scale they are built at (1 / magnification)."""
        camera = self._cameras[k]
        if camera is None:
            return self._body, 1.0
        w, (x, y) = camera
        s = w / self.frame_width
        h = self.frame_height * s
        return Region(x - w / 2 + self.margin_x * s, y - h / 2 + self.margin_y * s, x + w / 2 - self.margin_x * s, y + h / 2 - self.margin_y * s), s

    # ----- items -------------------------------------------------------------------------------

    def _plate(self, text: str, s: float) -> VGroup:
        """A label: text on a rounded plate of the background colour."""
        t = self.text(text, size=self._size * s, color="text")
        pad = 0.08 * s
        plate = RoundedRectangle(width=t.width + 2.5 * pad, height=t.height + 2 * pad, corner_radius=pad * 1.5)
        plate.set_fill(self.theme.background, opacity=PLATE_OPACITY).set_stroke(width=0).move_to(t)
        return VGroup(plate, t).set_z_index(4)

    def _place(self, label: VGroup, anchor: Region, bounds: Region, taken: list[Region], gaps: tuple[float, ...]) -> Region:
        """Move ``label`` next to ``anchor`` clear of ``taken`` (inside ``bounds``); returns its box."""
        spot = label_spot((label.width, label.height), anchor, bounds=bounds, avoid=taken, gaps=gaps)
        label.move_to(spot.center)
        return spot

    def _build_items(self) -> None:
        """Highlights, pins, arcs and labels of every stage (labels avoid each other, the pins
        and the arcs' ends of the same view)."""
        p = self.params
        view = self._view
        bg = self.theme.background
        self._items: list[dict[str, list[tuple[Any, Mobject]]]] = []
        self._labels: list[list[Mobject]] = []
        country_k = 0
        taken: list[Region] = []   # labels of this view
        marks: list[Region] = []   # pins of this view
        for k, step in enumerate(p.stages()):
            bounds, s = self._bounds(k)
            if k > 0 and self._cameras[k] != self._cameras[k - 1]:
                taken, marks = [], []
            items: dict[str, list[tuple[Any, Mobject]]] = {"countries": [], "pins": [], "arcs": []}
            labels: list[Mobject] = []
            pin_at = [view.point(*pin.where()) for pin in step.pins]
            mine = [Region(float(q[0]) - 0.1 * s, float(q[1]) - 0.1 * s, float(q[0]) + 0.1 * s, float(q[1]) + 0.1 * s) for q in pin_at]
            marks += mine
            # countries
            for item in step.countries:
                country = find_country(item.country)
                color = self._highlight_color(item, country_k)
                country_k += 1
                base = self._countries.get(country.a3)
                if base is None:
                    log.warning("scene '%s': %s is outside the map's view", self.spec.id, country.name)
                    items["countries"].append((country, VGroup()))
                    continue
                overlay = base.copy()
                if p.values:
                    overlay.set_fill(opacity=0).set_stroke(color, width=3.5 * s)
                else:
                    overlay.set_fill(color, opacity=1).set_stroke(bg, width=1.6 * BORDER * s)
                overlay.set_z_index(1)
                parts: list[Mobject] = [overlay]
                text = item.label if isinstance(item.label, str) else (country.name if (item.label if item.label is not None else p.labels) else "")
                if text.strip():
                    label = self._plate(text.strip(), s)
                    lead = self._country_label(label, country, bounds, taken, marks, s)
                    labels.append(label)
                    parts.append(label)
                    if lead is not None:
                        labels.append(lead)
                        parts.append(lead)
                items["countries"].append((country, VGroup(*parts)))
            # arcs
            for arc in step.arcs:
                color = self.theme.color(arc.color or p.arc_color)
                a, b = view.point(*p.arc_end(arc.start)), view.point(*p.arc_end(arc.to))
                ends = [q for q in pin_at] + [self._view.point(*pin.where()) for _, pin in p.all_pins()]
                trim = [0.13 * s if any(np.allclose(q, r) for r in ends) else 0.0 for q in (a, b)]
                curve = self._arc(a, b, color, s, trim)
                parts = [curve]
                for q in (a, b):
                    if not any(np.allclose(q, r) for r in pin_at):
                        parts.append(Dot(q, radius=0.05 * s, color=color).set_z_index(2))
                if arc.label.strip():
                    label = self._plate(arc.label.strip(), s)
                    top = curve.point_from_proportion(0.5)
                    anchor = Region(float(top[0]) - 0.05 * s, float(top[1]) - 0.05 * s, float(top[0]) + 0.05 * s, float(top[1]) + 0.05 * s)
                    taken.append(self._place(label, anchor, bounds, taken + marks, (0.06 * s, 0.25 * s)))
                    labels.append(label)
                    parts.append(label)
                items["arcs"].append((arc, VGroup(*parts)))
            # pins (on top of arcs)
            for pin, q, own in zip(step.pins, pin_at, mine):
                color = self.theme.color(pin.color or p.pin_color)
                dot = Dot(q, radius=0.085 * s, color=color).set_stroke(bg, width=2.5 * s ** 0.5, background=True).set_z_index(3)
                parts = [dot]
                if pin.label.strip():
                    label = self._plate(pin.label.strip(), s)
                    anchor = Region(float(q[0]) - 0.09 * s, float(q[1]) - 0.09 * s, float(q[0]) + 0.09 * s, float(q[1]) + 0.09 * s)
                    spot = self._place(label, anchor, bounds, taken + [m for m in marks if m is not own], (0.05 * s, 0.25 * s, 0.5 * s))
                    taken.append(spot)
                    labels.append(label)
                    parts.append(label)
                    lead = self._leader(q, spot, s, 0.09 * s)
                    if lead is not None:
                        labels.append(lead)
                        parts.append(lead)
                items["pins"].append((pin, VGroup(*parts)))
            self._items.append(items)
            self._labels.append(labels)

    def _highlight_color(self, item: MapCountry, n: int) -> str:
        p = self.params
        if item.color:
            return self.theme.color(item.color)
        if p.highlight_color == "palette":
            return self.theme.palette_color(n)
        return self.theme.color(p.highlight_color)

    def _country_label(self, label: VGroup, country: Country, bounds: Region, taken: list[Region], marks: list[Region], s: float) -> Mobject | None:
        """Put a country's label on its label point when it fits inside the country, else beside
        it with a leader line (returned)."""
        q = self._view.point(*country.label)
        inside = self._view.box_region(country.main)
        box = Region(float(q[0]) - label.width / 2, float(q[1]) - label.height / 2, float(q[0]) + label.width / 2, float(q[1]) + label.height / 2)
        fits = label.width <= inside.width * 0.9 and label.height <= inside.height * 0.9
        within = bounds.x0 <= box.x0 and box.x1 <= bounds.x1 and bounds.y0 <= box.y0 and box.y1 <= bounds.y1
        if fits and within and not any(_hits(box, t) for t in taken + marks):
            label.move_to(q)
            taken.append(box)
            return None
        anchor = Region(float(q[0]) - 0.04 * s, float(q[1]) - 0.04 * s, float(q[0]) + 0.04 * s, float(q[1]) + 0.04 * s)
        spot = self._place(label, anchor, bounds, taken + marks, (0.3 * s, 0.6 * s, 1.0 * s))
        taken.append(spot)
        lead = self._leader(q, spot, s, 0.0)
        assert lead is not None
        return lead.add(Dot(q, radius=0.035 * s, color=self.theme.color("text")))

    def _leader(self, q: np.ndarray, spot: Region, s: float, start: float) -> VGroup | None:
        """A thin line from ``q`` (``start`` units out) to the label box ``spot``, or ``None``
        when the label is right beside it."""
        end = np.array([np.clip(q[0], spot.x0, spot.x1), np.clip(q[1], spot.y0, spot.y1), 0.0])
        gap = float(np.linalg.norm(end - q))
        if gap <= start + 0.12 * s:
            return None
        begin = q + (end - q) * (start / gap)
        line = Line(begin, end, stroke_width=2 * s ** 0.5, color=self.theme.color("text")).set_opacity(0.8)
        return VGroup(line).set_z_index(LEADER_Z)

    def _arc(self, a: np.ndarray, b: np.ndarray, color: str, s: float, trim: list[float]) -> VMobject:
        """A flight-path arc from ``a`` to ``b`` bending upwards (downwards when the top would
        leave the map), with an arrowhead at ``b``; ``trim`` shortens it at each end (units; it
        stops short of a pin)."""
        angle = -ARC_ANGLE if b[0] >= a[0] else ARC_ANGLE
        curve = ArcBetweenPoints(a, b, angle=angle)
        if curve.get_top()[1] > self._view.region.y1:
            curve = ArcBetweenPoints(a, b, angle=-angle)
        length = abs(angle) * float(np.linalg.norm(b - a)) / (2 * np.sin(abs(angle) / 2))
        t0, t1 = trim[0] / length, 1 - trim[1] / length
        if 0 < t0 < t1 < 1 or (t0 == 0 and t1 < 1):
            curve.pointwise_become_partial(curve.copy(), t0, t1)
        curve.set_stroke(color, width=4 * s ** 0.5)
        curve.add_tip(tip_length=0.2 * s, tip_width=0.18 * s)
        curve.tip.set_fill(color, opacity=1).set_stroke(width=0)
        return curve.set_z_index(2)

    # ----- targets -----------------------------------------------------------------------------

    def _register(self, title: Mobject | None, bar: Mobject | None) -> None:
        p = self.params
        if title is not None:
            self.target("title", title, entrance=lambda: [FadeIn(title, shift=DOWN * 0.1)])
        base = VGroup(*([self._panel] if self._panel is not None else []), *self._countries.values())
        self.target("map", base, entrance=self._sweep)
        if bar is not None:
            self.target("legend", bar, entrance=lambda: [FadeIn(bar, shift=UP * 0.1)])
        done: set[str] = set()
        for k, items in enumerate(self._items):
            for country, group in items["countries"]:
                self.target(self._country_names(country), group, entrance=lambda k=k, g=group: self._item_entrance(k, g))
                done.add(country.a3)
        for c in p.target_countries():
            if c.a3 not in done and c.a3 in self._countries:
                shape = self._countries[c.a3]
                self.target(self._country_names(c), shape, entrance=lambda m=shape: [FadeIn(m)])
        n_pin = n_arc = 0
        for k, items in enumerate(self._items):
            for pin, group in items["pins"]:
                n_pin += 1
                names = [f"pin{n_pin}"] + ([f"pin:{pin.label}"] if pin.label.strip() else [])
                self.target(names, group, entrance=lambda k=k, g=group: self._item_entrance(k, g))
            for _, group in items["arcs"]:
                n_arc += 1
                self.target(f"arc{n_arc}", group, entrance=lambda k=k, g=group: self._item_entrance(k, g))
            if k > 0 and not p.steps[k - 1].empty():
                self.target(f"step{k}", Group(*self._parts(k)), entrance=lambda k=k: self._arrive(k))

    def _parts(self, k: int) -> list[Mobject]:
        items = self._items[k]
        return [g for kind in ("countries", "arcs", "pins") for _, g in items[kind]]

    # ----- animation ---------------------------------------------------------------------------

    def _sweep(self) -> list[Animation]:
        """The map from west to east: each country fades in at its turn."""
        m = self._view.region
        anims: list[Animation] = [FadeIn(self._panel, rate_func=window(0.0, 0.4))] if self._panel is not None else []
        for shape in self._countries.values():
            a = 0.5 * float(np.clip((shape.get_center()[0] - m.x0) / max(m.width, 1e-6), 0, 1))
            anims.append(FadeIn(shape, rate_func=window(a, a + 0.5)))
        return anims

    def _item_entrance(self, k: int, group: Mobject) -> list[Animation]:
        """One item alone; one of a focus step comes with its step (the camera, then all)."""
        if self._cameras[k] != self._camera_at:
            return self._arrive(k)
        return self._appear(group, 0.0)

    def _appear(self, group: Mobject, start: float) -> list[Animation]:
        """The animations of an item: a highlight fades in, an arc grows, a pin drops in; labels
        follow."""
        anims: list[Animation] = []
        span = 1.0 - start
        for part in group.submobjects:
            if self.on_screen_parts(part):
                continue
            if isinstance(part, ArcBetweenPoints):
                anims.append(Create(part, rate_func=window(start, start + 0.6 * span)))
            elif isinstance(part, Dot) and part.z_index == 3:
                anims.append(FadeIn(part, shift=DOWN * 0.25 * part.width / 0.17, scale=0.5, rate_func=window(start, start + 0.45 * span)))
            elif part.z_index >= LEADER_Z:
                anims.append(FadeIn(part, rate_func=window(start + 0.45 * span, 1.0)))
            else:
                anims.append(FadeIn(part, rate_func=window(start, start + 0.6 * span)))
        return anims

    def _step(self, k: int) -> list[Animation]:
        """Stage ``k`` at its beat; nothing when an action revealed all its items already."""
        parts = self._parts(k)
        if parts and all(self.on_screen_parts(m) for m in parts) and self._cameras[k] == self._camera_at:
            return []
        return self._arrive(k)

    def _arrive(self, k: int, start: float = 0.0) -> list[Animation]:
        """Stage ``k``: the camera moves (labels built for another view fade), then its items
        appear (after the camera, when it moved)."""
        anims: list[Animation] = []
        camera = self._cameras[k]
        if camera != self._camera_at:
            for j, labels in enumerate(self._labels):
                if self._cameras[j] != camera:
                    anims += [FadeOut(m) for m in labels if self.on_screen_parts(m)]
            width, center = camera or (self.frame_width, (0.0, 0.0))
            anims.append(MoveCamera(self, width, np.array([*center, 0.0])))
            self._camera_at = camera
            start = max(start, 0.45)
        for group in self._parts(k):
            anims += self._appear(group, start)
        return anims
