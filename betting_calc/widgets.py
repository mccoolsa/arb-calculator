"""Reusable dark-theme Tk widgets: rounded cards, number fields, buttons.

Tk has no native rounded corners, so cards are drawn on a Canvas that sits
in the same grid cell as the content frame. The content frame drives the
cell size; the canvas stretches behind it and redraws on <Configure>.
"""

from __future__ import annotations

import tkinter as tk

from . import theme as T


def rounded_points(x1, y1, x2, y2, r):
    """Corner points for a smoothed rounded rectangle polygon."""
    return [
        x1 + r, y1, x2 - r, y1, x2, y1,
        x2, y1 + r, x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2, x1, y2,
        x1, y2 - r, x1, y1 + r, x1, y1,
    ]


class Card(tk.Frame):
    """A rounded, optionally outlined panel. Add children to ``.body``."""

    def __init__(self, master, bg=T.CARD, outline=T.BORDER_SOFT, radius=12,
                 padding=18, outline_width=1, **kw):
        parent_bg = kw.pop("parent_bg", None) or master.cget("bg")
        super().__init__(master, bg=parent_bg, **kw)
        self._bg = bg
        self._outline = outline
        self._radius = radius
        self._outline_width = outline_width

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # width/height of 1 so the body frame alone drives the card's size
        # (a default Canvas would impose a 378x266 floor).
        self._canvas = tk.Canvas(self, bg=parent_bg, highlightthickness=0,
                                 bd=0, width=1, height=1, takefocus=0)
        self._canvas.grid(row=0, column=0, sticky="nsew")

        self.body = tk.Frame(self, bg=bg)
        self.body.grid(row=0, column=0, sticky="nsew", padx=padding, pady=padding)

        self._canvas.bind("<Configure>", self._redraw)

    def set_outline(self, colour: str) -> None:
        self._outline = colour
        self._redraw()

    def _redraw(self, _event=None):
        c = self._canvas
        c.delete("card")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 4 or h < 4:
            return
        inset = self._outline_width
        pts = rounded_points(inset, inset, w - inset, h - inset, self._radius)
        c.create_polygon(pts, smooth=True, splinesteps=24, fill=self._bg,
                         outline=self._outline, width=self._outline_width,
                         tags="card")


class Pill(tk.Canvas):
    """A small rounded badge with text."""

    def __init__(self, master, text, fg=T.ACCENT, bg=T.ACCENT_DIM,
                 font=None, padx=8, pady=3):
        font = font or T.FONT_XS
        super().__init__(master, bg=master.cget("bg"), highlightthickness=0,
                         bd=0, takefocus=0)
        self._text = text
        self._fg = fg
        self._bg = bg
        self._font = font
        self._padx = padx
        self._pady = pady
        self._measure()

    def _measure(self):
        tmp = self.create_text(0, 0, text=self._text, font=self._font, anchor="nw")
        x1, y1, x2, y2 = self.bbox(tmp)
        self.delete(tmp)
        w = (x2 - x1) + self._padx * 2
        h = (y2 - y1) + self._pady * 2
        self.configure(width=w, height=h)
        pts = rounded_points(0, 0, w - 1, h - 1, min(h // 2, 9))
        self.create_polygon(pts, smooth=True, splinesteps=16, fill=self._bg,
                            outline=self._bg)
        self.create_text(w / 2, h / 2, text=self._text, font=self._font,
                         fill=self._fg)

    def set_text(self, text, fg=None, bg=None):
        self._text = text
        if fg:
            self._fg = fg
        if bg:
            self._bg = bg
        self.delete("all")
        self._measure()


class Button(tk.Canvas):
    """A flat rounded button with hover / press / disabled states."""

    def __init__(self, master, text, command=None, kind="primary",
                 width=None, height=32, font=None):
        self._palette = {
            "primary": (T.ACCENT, T.ACCENT_HOVER, "#04121c"),
            "ghost": (T.CARD_ALT, "#243546", T.TEXT_DIM),
            "danger": ("#2a1a1e", "#3a2126", T.RED),
        }
        base, hover, fg = self._palette.get(kind, self._palette["primary"])
        self._base = base
        self._hover = hover
        self._fg = fg
        self._kind = kind
        self._text = text
        self._command = command
        self._enabled = True
        self._font = font or T.FONT_BOLD

        # A bare tk.Canvas requests 378px; buttons that stretch to fill their
        # container must not drag that default into the parent's requested
        # size, so always give one an explicit width.
        super().__init__(master, bg=master.cget("bg"), highlightthickness=0,
                         bd=0, height=height, width=width or 90, takefocus=0)
        self.bind("<Configure>", lambda e: self._draw(self._base))
        self.bind("<Enter>", lambda e: self._enabled and self._draw(self._hover))
        self.bind("<Leave>", lambda e: self._enabled and self._draw(self._base))
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.configure(cursor="hand2")

    def _draw(self, fill):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            return
        outline = T.BORDER if self._kind == "ghost" else fill
        if not self._enabled:
            fill, outline = T.CARD_ALT, T.BORDER_SOFT
        pts = rounded_points(1, 1, w - 1, h - 1, 8)
        self.create_polygon(pts, smooth=True, splinesteps=20, fill=fill,
                            outline=outline, width=1)
        self.create_text(w / 2, h / 2, text=self._text, font=self._font,
                         fill=self._fg if self._enabled else T.FAINT)

    def _on_press(self, _e):
        if self._enabled:
            self._draw(self._base)

    def _on_release(self, _e):
        if not self._enabled:
            return
        self._draw(self._hover)
        if self._command:
            self._command()

    def set_enabled(self, value: bool):
        self._enabled = bool(value)
        self.configure(cursor="hand2" if value else "arrow")
        self._draw(self._base)

    def set_text(self, text: str):
        self._text = text
        self._draw(self._base)


class NumberField(tk.Frame):
    """Bordered numeric input with an affix and up/down steppers.

    Set ``readonly=True`` for computed outputs - the field then renders in a
    dimmed style, matching the greyed-out payout boxes in the reference UI.
    """

    def __init__(self, master, variable, affix=None, affix_side="left",
                 step=0.1, minimum=0.0, maximum=None, decimals=2,
                 readonly=False, width=9, on_change=None, forbidden=None):
        super().__init__(master, bg=T.BORDER, padx=1, pady=1)
        self.var = variable
        self._step = step
        self._min = minimum
        self._max = maximum
        self._decimals = decimals
        self._forbidden = forbidden
        self._readonly = None
        self._on_change = on_change

        self._inner = tk.Frame(self, bg=T.FIELD)
        self._inner.pack(fill="both", expand=True)

        self._affixes = []
        if affix and affix_side == "left":
            lbl = tk.Label(self._inner, text=affix, bg=T.FIELD, fg=T.FAINT,
                           font=T.FONT_SM, padx=7)
            lbl.pack(side="left")
            self._affixes.append(lbl)

        self.entry = tk.Entry(
            self._inner, textvariable=variable, bg=T.FIELD, fg=T.TEXT,
            font=T.FONT_INPUT, relief="flat", bd=0, width=width,
            insertbackground=T.ACCENT, disabledbackground=T.CARD_ALT,
            disabledforeground=T.MUTED, justify="left",
            highlightthickness=0, selectbackground=T.ACCENT_DIM,
        )
        self.entry.pack(side="left", fill="x", expand=True,
                        padx=(0 if affix and affix_side == "left" else 9, 4),
                        pady=6)

        if affix and affix_side == "right":
            lbl = tk.Label(self._inner, text=affix, bg=T.FIELD, fg=T.FAINT,
                           font=T.FONT_SM, padx=6)
            lbl.pack(side="left")
            self._affixes.append(lbl)

        self._pinned = False
        self._custom_step = None
        self._steppers = self._build_steppers()
        self.entry.bind("<FocusIn>", lambda e: self._readonly
                        or self.configure(bg=T.ACCENT))
        self.entry.bind("<FocusOut>", lambda e: self.configure(bg=self._idle_bg()))
        self.entry.bind("<Up>", lambda e: (self._nudge(1), "break")[1])
        self.entry.bind("<Down>", lambda e: (self._nudge(-1), "break")[1])

        self.set_readonly(readonly)

    def _build_steppers(self):
        holder = tk.Frame(self._inner, bg=T.FIELD)
        for text, direction in (("▲", 1), ("▼", -1)):
            lbl = tk.Label(holder, text=text, bg=T.FIELD, fg=T.FAINT,
                           font=("Segoe UI", 6), cursor="hand2")
            lbl.pack(expand=True, fill="both")
            lbl.bind("<Button-1>", lambda e, d=direction: self._nudge(d))
            lbl.bind("<Enter>", lambda e, w=lbl: w.configure(fg=T.ACCENT))
            lbl.bind("<Leave>", lambda e, w=lbl: w.configure(fg=T.FAINT))
        return holder

    def _idle_bg(self):
        return T.ACCENT_DIM if self._pinned else T.BORDER

    def set_pinned(self, value: bool):
        """Accent the border to show this field is being held fixed.

        The field stays fully editable - pinning only marks it as the value
        other fields are calculated from.
        """
        self._pinned = bool(value)
        self.configure(bg=self._idle_bg())

    def set_readonly(self, value: bool):
        """Switch between an editable input and a dimmed computed output."""
        value = bool(value)
        if value == self._readonly:
            return
        self._readonly = value

        bg = T.CARD_ALT if value else T.FIELD
        self._inner.configure(bg=bg)
        for lbl in self._affixes:
            lbl.configure(bg=bg)
        self._steppers.configure(bg=bg)
        for lbl in self._steppers.winfo_children():
            lbl.configure(bg=bg)
        self.entry.configure(state="disabled" if value else "normal",
                             bg=bg, fg=T.MUTED if value else T.TEXT,
                             disabledbackground=bg)
        self.configure(bg=self._idle_bg())

        if value:
            self._steppers.pack_forget()
        else:
            self._steppers.pack(side="right", fill="y", padx=(0, 5))

    @property
    def readonly(self):
        return self._readonly

    def set_custom_step(self, fn):
        """Delegate stepping to ``fn(text, direction) -> text or None``.

        For values that are not plain numbers - fractional odds step along a
        price ladder, not by an arithmetic increment.
        """
        self._custom_step = fn

    def _nudge(self, direction):
        if self._readonly:
            return

        if getattr(self, "_custom_step", None):
            stepped = self._custom_step(self.var.get(), direction)
            if stepped is not None:
                self.var.set(stepped)
                if self._on_change:
                    self._on_change()
            return

        try:
            value = float(str(self.var.get()).strip().replace("$", "") or 0)
        except ValueError:
            value = 0.0
        value += direction * self._step

        # American odds have no legal values between -100 and +100; step over
        # the gap rather than landing inside it.
        if self._forbidden:
            lo, hi = self._forbidden
            if lo < value < hi:
                value = hi if direction > 0 else lo

        if self._min is not None:
            value = max(self._min, value)
        if self._max is not None:
            value = min(self._max, value)

        # Keep the fixed decimal places (odds read better as "1.80" than
        # "1.8"), but drop them entirely for whole numbers ("105", not
        # "105.00").
        text = ("{:.%df}" % self._decimals).format(value)
        rounded = float(text)
        if rounded == int(rounded):
            text = str(int(rounded))
        self.var.set(text)
        if self._on_change:
            self._on_change()

    def set_step(self, step, decimals=None):
        self._step = step
        if decimals is not None:
            self._decimals = decimals

    def set_bounds(self, minimum, maximum=None, forbidden=None):
        self._min = minimum
        self._max = maximum
        self._forbidden = forbidden

class CheckBox(tk.Frame):
    """A small themed tickbox with a clickable label."""

    def __init__(self, master, text, variable, command=None, bg=None,
                 fg=T.TEXT_DIM, font=None, size=15):
        bg = bg or master.cget("bg")
        super().__init__(master, bg=bg, cursor="hand2")
        self.var = variable
        self._command = command
        self._size = size

        self.box = tk.Canvas(self, width=size, height=size, bg=bg,
                             highlightthickness=0, bd=0, takefocus=0)
        self.box.pack(side="left")
        self.label = tk.Label(self, text=text, bg=bg, fg=fg,
                              font=font or T.FONT_SM, padx=7)
        self.label.pack(side="left")

        for widget in (self, self.box, self.label):
            widget.bind("<Button-1>", self._toggle)
        variable.trace_add("write", lambda *_: self._draw())
        self._draw()

    def _toggle(self, _event=None):
        self.var.set(not self.var.get())
        if self._command:
            self._command()

    def _draw(self):
        self.box.delete("all")
        checked = bool(self.var.get())
        s = self._size
        pts = rounded_points(1, 1, s - 1, s - 1, 4)
        self.box.create_polygon(
            pts, smooth=True, splinesteps=12,
            fill=T.ACCENT if checked else T.FIELD,
            outline=T.ACCENT if checked else T.BORDER, width=1)
        if checked:
            self.box.create_line(s * 0.28, s * 0.52, s * 0.44, s * 0.70,
                                 s * 0.74, s * 0.31, fill="#04121c", width=2,
                                 capstyle="round", joinstyle="round")


class SegmentedControl(tk.Frame):
    """Two or more mutually exclusive tabs."""

    def __init__(self, master, options, command=None, bg=None, font=None,
                 padx=18, pady=8):
        bg = bg or master.cget("bg")
        super().__init__(master, bg=bg)
        self._command = command
        self._buttons = {}
        self._value = options[0][0]
        font = font or T.FONT_BOLD

        for key, label in options:
            btn = tk.Label(self, text=label, bg=bg, fg=T.MUTED, font=font,
                           padx=padx, pady=pady, cursor="hand2")
            btn.pack(side="left")
            btn.bind("<Button-1>", lambda e, k=key: self.set(k, notify=True))
            self._buttons[key] = btn
        self.set(self._value)

    def get(self):
        return self._value

    def set(self, key, notify=False):
        self._value = key
        for k, btn in self._buttons.items():
            active = k == key
            btn.configure(fg=T.TEXT if active else T.MUTED,
                          bg=T.CARD_ALT if active else self.cget("bg"))
        if notify and self._command:
            self._command(key)


class Dropdown(tk.Frame):
    """A dark-theme dropdown: a labelled trigger that opens a list below it."""

    def __init__(self, master, options, command=None, bg=None, font=None,
                 min_width=132):
        bg = bg or master.cget("bg")
        super().__init__(master, bg=T.BORDER, padx=1, pady=1, cursor="hand2")
        self._items = list(options)
        self._command = command
        self._value = self._items[0][0]
        self._font = font or T.FONT_SM
        self._popup = None
        self._prev_grab = None

        inner = tk.Frame(self, bg=T.FIELD)
        inner.pack(fill="both", expand=True)
        self._label = tk.Label(inner, text=self._labelled(self._value),
                               bg=T.FIELD, fg=T.TEXT, font=self._font,
                               anchor="w", padx=10, pady=5, width=0,
                               cursor="hand2")
        self._label.pack(side="left", fill="x", expand=True)
        self._caret = tk.Label(inner, text="▾", bg=T.FIELD, fg=T.MUTED,
                               font=self._font, padx=8, cursor="hand2")
        self._caret.pack(side="right")

        self.configure(width=min_width)
        for widget in (self, inner, self._label, self._caret):
            widget.bind("<Button-1>", self._toggle)

    # -- value ------------------------------------------------------------

    def _labelled(self, key):
        return next((lbl for k, lbl in self._items if k == key), key)

    def get(self):
        return self._value

    def set(self, key, notify=False):
        self._value = key
        self._label.configure(text=self._labelled(key))
        if notify and self._command:
            self._command(key)

    # -- popup ------------------------------------------------------------

    def _toggle(self, _event=None):
        self._close() if self._popup else self._open()
        return "break"

    def _open(self):
        self.update_idletasks()
        popup = tk.Toplevel(self.winfo_toplevel())
        popup.overrideredirect(True)
        popup.configure(bg=T.BORDER)
        inner = tk.Frame(popup, bg=T.CARD_ALT)
        inner.pack(padx=1, pady=1, fill="both", expand=True)

        for key, label in self._items:
            active = key == self._value
            row = tk.Label(inner, text=label, bg=T.CARD_ALT,
                           fg=T.ACCENT if active else T.TEXT_DIM,
                           font=self._font, anchor="w", padx=12, pady=6,
                           cursor="hand2")
            row.pack(fill="x")
            row.bind("<Button-1>", lambda e, k=key: self._choose(k))
            row.bind("<Enter>", lambda e, w=row: w.configure(bg=T.FIELD_HOVER))
            row.bind("<Leave>", lambda e, w=row: w.configure(bg=T.CARD_ALT))

        popup.update_idletasks()
        width = max(self.winfo_width(), popup.winfo_reqwidth())
        popup.geometry("{}x{}+{}+{}".format(
            width, popup.winfo_reqheight(), self.winfo_rootx(),
            self.winfo_rooty() + self.winfo_height() + 2))
        popup.lift()
        popup.bind("<Escape>", lambda e: self._close())
        # With the grab in place, a click anywhere else in the app is
        # delivered here with coordinates outside the popup.
        popup.bind("<Button-1>", self._click_outside)
        # Taking the grab from a modal dialog would leave it non-modal once
        # the popup closes, so remember who had it and hand it back.
        self._prev_grab = popup.grab_current()
        popup.grab_set()
        self._popup = popup
        self._caret.configure(text="▴", fg=T.ACCENT)

    def _click_outside(self, event):
        if not (0 <= event.x < self._popup.winfo_width()
                and 0 <= event.y < self._popup.winfo_height()):
            self._close()

    def _choose(self, key):
        self._close()
        self.set(key, notify=True)
        return "break"

    def _close(self):
        if self._popup is not None:
            self._popup.grab_release()
            self._popup.destroy()
            self._popup = None
            if self._prev_grab is not None:
                try:
                    self._prev_grab.grab_set()
                except tk.TclError:
                    pass            # the previous grabber has gone away
                self._prev_grab = None
        self._caret.configure(text="▾", fg=T.MUTED)


class ScrollFrame(tk.Frame):
    """Vertically scrollable container. Add children to ``.inner``."""

    def __init__(self, master, bg=T.CARD, height=260):
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0,
                                height=height, width=1, takefocus=0)
        self.canvas.pack(side="left", fill="both", expand=True)

        self.scrollbar = tk.Scrollbar(self, orient="vertical",
                                      command=self.canvas.yview,
                                      width=8, bd=0, relief="flat",
                                      troughcolor=bg, bg=T.BORDER,
                                      activebackground=T.MUTED,
                                      highlightthickness=0)
        self.canvas.configure(yscrollcommand=self._on_scroll)

        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.inner,
                                                 anchor="nw")

        self.inner.bind("<Configure>", self._sync_region)
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self._window,
                                                             width=e.width))
        self._bind_wheel(self)

    def _on_scroll(self, first, last):
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.scrollbar.pack_forget()
        else:
            self.scrollbar.pack(side="right", fill="y")
        self.scrollbar.set(first, last)

    def _sync_region(self, _e=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _bind_wheel(self, widget):
        widget.bind_all("<MouseWheel>", self._wheel, add="+")

    def _wheel(self, event):
        if not self.winfo_exists():
            return
        x, y = self.winfo_pointerxy()
        under = self.winfo_containing(x, y)
        w = under
        while w is not None:
            if w is self:
                self.canvas.yview_scroll(int(-event.delta / 120), "units")
                return
            w = getattr(w, "master", None)


def label(master, text, fg=T.TEXT, font=None, **kw):
    return tk.Label(master, text=text, bg=master.cget("bg"), fg=fg,
                    font=font or T.FONT, **kw)


def divider(master, colour=T.BORDER_SOFT, pady=10):
    line = tk.Frame(master, bg=colour, height=1)
    line.pack(fill="x", pady=pady)
    return line
